"""Live progress for the local vision model used by the Marker engine.

Surya sends every request of a stage as one batch and returns only when all of
them finish. This module observes that batch and follows the llama-server log, so
the wait can be reported as it happens. Everything here is best effort: if Surya
or the log format changes, conversion continues with less detail.
"""
from __future__ import annotations

import contextlib
import re
import sys
import threading
from pathlib import Path

# Surya hardcodes this location when it spawns llama-server.
LLAMA_LOG = Path("~/.cache/datalab/surya/llamacpp_server.log")

PHASE_LABELS = {
    "model_loading": "Loading the vision model",
    "model_reading": "Vision model: reading images",
    "model_writing": "Vision model: writing text",
    "model_done": "Vision model: finished",
}

_PAGE_PROMPTS = frozenset({"layout", "ocr", "ocr_with_boxes", "high_accuracy_bbox"})
_GENERATED = re.compile(r"\btask\s+(\d+)\s+\|\s+n_gen\s*=\s*(\d+),\s+tg\s*=\s*([\d.]+)\s+t/s")
_RELEASED = re.compile(r"\brelease:.*\btask\s+(\d+)\s+\|\s+stop processing")


class ModelProgress:
    """Track one conversion's model requests and report snapshots of them."""

    def __init__(self, report, log_path: Path | None = None, cancel_event=None) -> None:
        self._report = report
        self._log_path = (log_path or LLAMA_LOG).expanduser()
        self._cancel = cancel_event
        self._lock = threading.RLock()
        self._offset = self._log_size()
        self._partial = b""
        self._loading = False
        self._active = False
        self._completed = 0
        self._total = 0
        self._unit = "page"
        self._tasks: dict[str, tuple[int, float, bool]] = {}

    def loading(self, active: bool) -> None:
        with self._lock:
            self._loading = active
            if active:
                self.tick()

    def begin(self, total: int, unit: str) -> None:
        with self._lock:
            self._read_log()  # Discard lines that belong to earlier batches.
            self._tasks.clear()
            self._active, self._completed, self._total, self._unit = True, 0, total, unit
            self.tick()

    def item_done(self) -> None:
        with self._lock:
            if self._active:
                self._completed = min(self._completed + 1, self._total)
                self.tick()

    def end(self) -> None:
        with self._lock:
            if self._active:
                self.tick(done=True)
                self._active = False

    def tick(self, done: bool = False) -> None:
        with self._lock:
            if not (self._active or self._loading):
                return
            if self._cancel is not None and self._cancel.is_set():
                return
            self._read_log()
            running = [rate for _tokens, rate, alive in self._tasks.values() if alive]
            tokens = sum(tokens for tokens, _rate, _alive in self._tasks.values())
            if self._loading:
                phase = "model_loading"
            elif done:
                phase = "model_done"
            else:
                # A released task whose result has not arrived is still wrapping up.
                pending = len(self._tasks) - len(running) > self._completed
                phase = "model_writing" if running or pending else "model_reading"
            snapshot = {
                "phase": phase,
                "completed": None if self._loading else self._completed,
                "total": None if self._loading else self._total,
                "unit": self._unit,
                "tokens": tokens,
                "tokens_per_second": round(sum(running), 1),
            }
            # Reporting must never break a conversion.
            with contextlib.suppress(Exception):
                self._report(snapshot)

    def _log_size(self) -> int:
        try:
            return self._log_path.stat().st_size
        except OSError:
            return 0

    def _read_log(self) -> None:
        size = self._log_size()
        if size < self._offset:
            self._offset, self._partial = 0, b""
        if size == self._offset:
            return
        try:
            with self._log_path.open("rb") as stream:
                stream.seek(self._offset)
                chunk = stream.read(size - self._offset)
        except OSError:
            return
        self._offset += len(chunk)
        *lines, self._partial = (self._partial + chunk).split(b"\n")
        for raw in lines:
            line = raw.decode("utf-8", errors="replace")
            if match := _GENERATED.search(line):
                self._tasks[match[1]] = (int(match[2]), float(match[3]), True)
            elif (match := _RELEASED.search(line)) and match[1] in self._tasks:
                tokens, rate, _alive = self._tasks[match[1]]
                self._tasks[match[1]] = (tokens, rate, False)


def _unit_for(batch) -> str:
    prompts = {getattr(item, "prompt_type", None) for item in batch}
    return "page" if prompts <= _PAGE_PROMPTS else "block"


@contextlib.contextmanager
def _surya_hooks(progress: ModelProgress):
    from surya.inference.backends import llamacpp, openai_client

    backend = llamacpp.LlamaCppBackend
    originals = (llamacpp.chat_completions_batch, openai_client.BatchOutputItem, backend.start)
    run_batch, output_item, start = originals

    def observed_batch(batch, *args, **kwargs):
        progress.begin(len(batch), _unit_for(batch))
        try:
            return run_batch(batch, *args, **kwargs)
        finally:
            progress.end()

    def observed_item(*args, **kwargs):
        # Surya builds this once per request, after its retries.
        result = output_item(*args, **kwargs)
        progress.item_done()
        return result

    def observed_start(self):
        if self.handle is not None:
            return start(self)
        progress.loading(True)
        try:
            return start(self)
        finally:
            progress.loading(False)

    llamacpp.chat_completions_batch = observed_batch
    openai_client.BatchOutputItem = observed_item
    backend.start = observed_start
    try:
        yield
    finally:
        llamacpp.chat_completions_batch, openai_client.BatchOutputItem, backend.start = originals


@contextlib.contextmanager
def monitor_model(report, *, cancel_event=None, log_path: Path | None = None, interval: float = 1.0):
    """Report model progress through ``report`` while the block runs."""
    # Surya reads its environment on import, so never be the first to import it.
    if "surya.settings" not in sys.modules:
        yield
        return
    progress = ModelProgress(report, log_path=log_path, cancel_event=cancel_event)
    hooks = _surya_hooks(progress)
    try:
        hooks.__enter__()
    except (ImportError, AttributeError):
        yield
        return
    stopped = threading.Event()

    def poll() -> None:
        while not stopped.wait(interval):
            progress.tick()

    poller = threading.Thread(target=poll, name="sami-progress", daemon=True)
    poller.start()
    try:
        yield
    finally:
        stopped.set()
        poller.join()
        hooks.__exit__(None, None, None)
