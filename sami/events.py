"""Protocol 1 JSONL event envelopes and UTF-8 stream framing."""
from __future__ import annotations

import codecs
import json
from dataclasses import dataclass
from itertools import count
from typing import Any, Iterable

from sami.contracts import _integer, _object, _string, json_value


PROTOCOL_VERSION = 1


def write_json_line(stream, line: str) -> None:
    """Write UTF-8 even when the Windows process uses a legacy code page."""
    binary = getattr(stream, "buffer", None)
    if binary is not None:
        binary.write((line + "\n").encode("utf-8"))
        binary.flush()
    else:
        stream.write(line + "\n")
        stream.flush()


def _reject_constant(value: str) -> None:
    raise ValueError(f"invalid JSON numeric constant: {value}")


@dataclass(frozen=True, slots=True)
class Event:
    event: str
    seq: int
    run_id: str
    data: dict[str, Any]
    job_id: str | None = None
    attempt: int | None = None
    protocol_version: int = PROTOCOL_VERSION

    def __post_init__(self) -> None:
        if type(self.protocol_version) is not int or self.protocol_version != PROTOCOL_VERSION:
            raise ValueError(f"unsupported protocol version: {self.protocol_version!r}")
        _string(self.event, "event")
        _string(self.run_id, "run_id")
        _integer(self.seq, "seq", minimum=1)
        if self.job_id is not None:
            _string(self.job_id, "job_id")
        if self.attempt is not None:
            _integer(self.attempt, "attempt", minimum=1)
        _object(self.data, "data")
        json_value(self.data, "data")

    def to_wire(self) -> dict[str, Any]:
        envelope: dict[str, Any] = {
            "protocol_version": self.protocol_version,
            "event": self.event,
            "seq": self.seq,
            "run_id": self.run_id,
        }
        if self.job_id is not None:
            envelope["job_id"] = self.job_id
        if self.attempt is not None:
            envelope["attempt"] = self.attempt
        envelope["data"] = json_value(self.data, "data")
        return envelope

    # Kept as a source-level convenience for callers of the initial draft API.
    def to_dict(self) -> dict[str, Any]:
        return self.to_wire()

    def to_json_line(self) -> str:
        """Return one JSONL record without its LF delimiter."""
        return json.dumps(self.to_wire(), ensure_ascii=False, allow_nan=False, separators=(",", ":"))

    @classmethod
    def from_wire(cls, value: Any) -> "Event":
        obj = _object(value, "event")
        required = ("protocol_version", "event", "seq", "run_id", "data")
        missing = [key for key in required if key not in obj]
        if missing:
            raise ValueError(f"event is missing required field(s): {', '.join(missing)}")
        protocol_version = _integer(obj["protocol_version"], "protocol_version", minimum=1)
        if protocol_version != PROTOCOL_VERSION:
            raise ValueError(f"unsupported protocol version: {protocol_version}")
        if "job_id" in obj:
            job_id = _string(obj["job_id"], "job_id")
        else:
            job_id = None
        if "attempt" in obj:
            attempt = _integer(obj["attempt"], "attempt", minimum=1)
        else:
            attempt = None
        return cls(
            protocol_version=protocol_version,
            event=_string(obj["event"], "event"),
            seq=_integer(obj["seq"], "seq", minimum=1),
            run_id=_string(obj["run_id"], "run_id"),
            job_id=job_id,
            attempt=attempt,
            data=_object(obj["data"], "data"),
        )

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "Event":
        """Compatibility alias; unknown additive fields are ignored."""
        return cls.from_wire(value)

    @classmethod
    def from_json_line(cls, line: str) -> "Event":
        if not isinstance(line, str):
            raise ValueError("event line must be text")
        value = json.loads(line, parse_constant=_reject_constant)
        return cls.from_wire(value)


class EventSequencer:
    """Assign positive, increasing sequence numbers within one run."""

    def __init__(self, run_id: str) -> None:
        self.run_id = _string(run_id, "run_id")
        self._sequence = count(1)

    def create(
        self,
        event: str,
        data: dict[str, Any],
        *,
        job_id: str | None = None,
        attempt: int | None = None,
    ) -> Event:
        return Event(
            event=event,
            seq=next(self._sequence),
            run_id=self.run_id,
            job_id=job_id,
            attempt=attempt,
            data=data,
        )


def encode_jsonl(events: Iterable[Event]) -> bytes:
    """Encode records with one LF after every event, ready for pipe writes."""
    return "".join(event.to_json_line() + "\n" for event in events).encode("utf-8")


class JsonlEventDecoder:
    """Decode fragmented UTF-8 pipe bytes into complete JSONL events.

    Framing is LF-delimited. An unterminated final record is accepted by
    ``finish()``, as permitted by JSON Lines; blank records are rejected.
    """

    def __init__(self) -> None:
        self._utf8 = codecs.getincrementaldecoder("utf-8")("strict")
        self._buffer = ""
        self._finished = False

    def feed(self, chunk: bytes) -> list[Event]:
        if self._finished:
            raise ValueError("cannot feed a finished JSONL decoder")
        if not isinstance(chunk, bytes):
            raise TypeError("JSONL decoder consumes UTF-8 bytes")
        self._buffer += self._utf8.decode(chunk, final=False)
        return self._drain_lines()

    def finish(self) -> list[Event]:
        if self._finished:
            return []
        self._buffer += self._utf8.decode(b"", final=True)
        self._finished = True
        if not self._buffer:
            return []
        line, self._buffer = self._buffer, ""
        return [self._parse_line(line)]

    def _drain_lines(self) -> list[Event]:
        events: list[Event] = []
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            if line.endswith("\r"):
                line = line[:-1]
            events.append(self._parse_line(line))
        return events

    @staticmethod
    def _parse_line(line: str) -> Event:
        if not line:
            raise ValueError("JSONL stream contains a blank record")
        return Event.from_json_line(line)
