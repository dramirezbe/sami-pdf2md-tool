"""Approximate completion percentage for one file.

The model never says how much text is left, so the percentage is an estimate
shaped for perceived progress: each segment fills quickly at first and slows as
it approaches its end, real signals only push it forward, it never moves back,
and it stays below 100 until the file is published. Segment sizes come from the
time earlier conversions took on this machine.
"""
from __future__ import annotations

import contextlib
import json
import math
import re
import threading
import time
from pathlib import Path

CEILING = 99.0
# The first segment gets more room than its real time, so the bar starts briskly.
_PREPARE_END = 30.0
# Seconds per page, used until this machine has its own history.
DEFAULT_RATES = {
    "cpu": {"prepare": 8.0, "model": 140.0},
    "gpu": {"prepare": 2.0, "model": 15.0},
}
_TOKENS_PER_PAGE = 2000
_OCR = re.compile(r"^OCR \((\d+)/\d+ pages")
_STEP = re.compile(r"^\[(\d+)/(\d+)\]")


def _ease(ratio: float) -> float:
    """Front-loaded fill of a segment that never quite reaches its end."""
    return 0.97 * (1.0 - math.exp(-1.8 * max(ratio, 0.0)))


def _read(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


class FileProgress:
    """Turn stage names and model snapshots into a percentage, and publish it."""

    def __init__(self, publish, *, pages: int | None, mode: str, device: str,
                 history: Path | None = None, cancel_event=None, clock=time.monotonic) -> None:
        self._publish = publish
        self._clock = clock
        self._cancel = cancel_event
        self._history = history
        self._key = f"{mode}:{device}"
        self._pages = max(pages or 1, 1)
        self._rates = dict(DEFAULT_RATES["cpu" if device == "cpu" else "gpu"])
        saved = _read(history).get(self._key) if history else None
        for name, value in (saved.items() if isinstance(saved, dict) else ()):
            if name in self._rates and isinstance(value, (int, float)) and value > 0:
                self._rates[name] = float(value)
        self._lock = threading.RLock()
        self._shown = 0.0
        self._data: dict | None = None
        self._published: int | None = None
        self._durations: dict[str, float] = {}
        self._ocr_pages = 0
        self._real = 0.0
        self._segment = "prepare"
        self._since = clock()
        self._start = 0.0
        self._expected = 5.0 + self._rates["prepare"] * self._pages
        self._end = _PREPARE_END

    @property
    def percent(self) -> int:
        with self._lock:
            elapsed = self._clock() - self._since
            fraction = max(_ease(elapsed / self._expected), self._real)
            target = self._start + (self._end - self._start) * fraction
            self._shown = min(max(self._shown, target), CEILING)
            return int(self._shown)

    def stage(self, name: str) -> None:
        with self._lock:
            if (match := _OCR.match(name)) and self._segment == "prepare":
                self._ocr_pages = int(match[1])
                expected = self._rates["model"] * max(self._ocr_pages, 1)
                share = expected / (expected + self._finish_seconds())
                self._enter("model", self._end, share, expected)
            elif (
                name.startswith(("OCR (skipped", "Structure building"))
                and self._segment != "finish"
            ):
                # The previous segment is really over, so jump to its end.
                self._enter("finish", self._end, 1.0, self._finish_seconds())
            elif (match := _STEP.match(name)) and self._segment == "finish":
                self._real = max(self._real, 0.9 * int(match[1]) / max(int(match[2]), 1))
            self._emit({"stage": name, "completed": None, "total": None}, force=True)

    def model(self, data: dict) -> None:
        with self._lock:
            if self._segment == "model" and data.get("total"):
                done = 0.95 * data["completed"] / data["total"]
                written = data.get("tokens", 0) / (_TOKENS_PER_PAGE * max(self._ocr_pages, 1))
                self._real = max(self._real, done, 0.9 * min(written, 1.0))
            self._emit(data, force=True)

    def pages_done(self, completed: int, total: int) -> None:
        """Exact progress for engines that work page by page."""
        with self._lock:
            self._shown = max(self._shown, CEILING * completed / max(total, 1))
            self._emit({"stage": f"Reading page {completed} of {total}",
                        "phase": "pages", "completed": completed, "total": total}, force=True)

    def tick(self) -> None:
        with self._lock:
            if self._data is not None:
                self._emit(self._data)

    def save(self) -> None:
        """Remember how long this conversion took, to size the next ones."""
        if self._history is None:
            return
        with self._lock:
            self._close_segment()
            measured = {}
            if "prepare" in self._durations:
                measured["prepare"] = self._durations["prepare"] / self._pages
            if self._ocr_pages and "model" in self._durations:
                measured["model"] = self._durations["model"] / self._ocr_pages
            if "finish" not in self._durations or not measured:
                return
            records = _read(self._history)
            previous = records.get(self._key)
            entry = dict(previous) if isinstance(previous, dict) else {}
            for name, value in measured.items():
                old = entry.get(name)
                entry[name] = round((old + value) / 2 if isinstance(old, (int, float)) else value, 3)
            records[self._key] = entry
            with contextlib.suppress(OSError):
                self._history.parent.mkdir(parents=True, exist_ok=True)
                self._history.write_text(json.dumps(records, indent=2), encoding="utf-8")

    def _finish_seconds(self) -> float:
        return 2.0 + 0.5 * self._pages

    def _close_segment(self) -> None:
        now = self._clock()
        self._durations[self._segment] = self._durations.get(self._segment, 0.0) + now - self._since
        self._since = now

    def _enter(self, segment: str, start: float, share: float, expected: float) -> None:
        self._close_segment()
        self._segment, self._expected, self._real = segment, max(expected, 1.0), 0.0
        self._start = self._shown = max(self._shown, start)
        self._end = self._start + (CEILING - self._start) * share

    def _emit(self, data: dict, *, force: bool = False) -> None:
        if self._cancel is not None and self._cancel.is_set():
            return
        percent = self.percent
        if not force and percent == self._published:
            return
        self._data, self._published = data, percent
        self._publish({**data, "percent": percent})


@contextlib.contextmanager
def ticking(progress: FileProgress, interval: float = 1.0):
    """Keep the percentage moving while the block runs."""
    stopped = threading.Event()

    def poll() -> None:
        while not stopped.wait(interval):
            # Reporting must never break a conversion.
            with contextlib.suppress(Exception):
                progress.tick()

    poller = threading.Thread(target=poll, name="sami-percent", daemon=True)
    poller.start()
    try:
        yield progress
    finally:
        stopped.set()
        poller.join()
