"""Validated engine-independent contracts and their JSON wire forms."""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal


Mode = Literal["fast", "balanced", "quality"]
JobStatus = Literal["succeeded", "partial", "failed", "cancelled"]
MODES = ("fast", "balanced", "quality")
JOB_STATUSES = ("succeeded", "partial", "failed", "cancelled")
REQUESTED_DEVICES = ("auto", "cpu", "cuda", "rocm")
EFFECTIVE_DEVICES = ("cpu", "cuda", "rocm")
RUN_EXIT_CODES = (0, 1, 2, 3, 130)


def _object(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise ValueError(f"{name} must be an object with string keys")
    return value


def _string(value: Any, name: str, *, nonempty: bool = True) -> str:
    if not isinstance(value, str) or (nonempty and not value.strip()):
        requirement = "a nonempty string" if nonempty else "a string"
        raise ValueError(f"{name} must be {requirement}")
    return value


def _integer(value: Any, name: str, *, minimum: int | None = None) -> int:
    if type(value) is not int:
        raise ValueError(f"{name} must be an integer")
    if minimum is not None and value < minimum:
        raise ValueError(f"{name} must be at least {minimum}")
    return value


def _finite_number(value: Any, name: str, *, minimum: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite number")
    try:
        number = float(value)
    except OverflowError as exc:
        raise ValueError(f"{name} must be a finite number") from exc
    if not math.isfinite(number):
        raise ValueError(f"{name} must be a finite number")
    if minimum is not None and number < minimum:
        raise ValueError(f"{name} must be at least {minimum}")
    return number


def _path(value: Any, name: str, *, absolute: bool) -> Path:
    if not isinstance(value, Path):
        raise ValueError(f"{name} must be a pathlib.Path")
    if absolute and not value.is_absolute():
        raise ValueError(f"{name} must be absolute")
    if not value.parts:
        raise ValueError(f"{name} must not be empty")
    return value


def _path_from_wire(value: Any, name: str, *, absolute: bool) -> Path:
    raw = _string(value, name)
    path = Path(raw)
    if absolute and not path.is_absolute():
        raise ValueError(f"{name} must be absolute")
    return path


def json_value(value: Any, name: str = "value") -> Any:
    """Convert supported values to JSON primitives; reject implicit coercions."""
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{name} contains a nonfinite number")
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (list, tuple)):
        return [json_value(item, f"{name}[]") for item in value]
    if isinstance(value, dict):
        if any(not isinstance(key, str) for key in value):
            raise ValueError(f"{name} object keys must be strings")
        return {key: json_value(item, f"{name}.{key}") for key, item in value.items()}
    raise TypeError(f"{name} contains unsupported value type {type(value).__name__}")


def _json_line(value: dict[str, Any]) -> str:
    return json.dumps(json_value(value), ensure_ascii=False, allow_nan=False, separators=(",", ":"))


@dataclass(frozen=True, slots=True)
class ConversionOptions:
    """User-selected options. ``device`` is the requested device policy."""

    device: str = "auto"

    def __post_init__(self) -> None:
        if self.device not in REQUESTED_DEVICES:
            raise ValueError(f"unsupported requested device: {self.device}")

    def to_wire(self) -> dict[str, Any]:
        return {"device": self.device}

    @classmethod
    def from_wire(cls, value: Any) -> "ConversionOptions":
        obj = _object(value, "options")
        if "device" not in obj:
            raise ValueError("options.device is required")
        return cls(device=_string(obj["device"], "options.device"))


@dataclass(frozen=True, slots=True)
class ConversionRequest:
    """One attempt; ``device`` is the effective device chosen by the coordinator."""

    job_id: str
    input_path: Path
    mode: Mode
    options: ConversionOptions
    staging_dir: Path
    device: str
    attempt: int = 1

    def __post_init__(self) -> None:
        _string(self.job_id, "job_id")
        _path(self.input_path, "input_path", absolute=True)
        _path(self.staging_dir, "staging_dir", absolute=True)
        if self.mode not in MODES:
            raise ValueError(f"unsupported mode: {self.mode}")
        if not isinstance(self.options, ConversionOptions):
            raise ValueError("options must be ConversionOptions")
        if self.device not in EFFECTIVE_DEVICES:
            raise ValueError(f"unsupported effective device: {self.device}")
        _integer(self.attempt, "attempt", minimum=1)

    def to_wire(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "input_path": str(self.input_path),
            "mode": self.mode,
            "options": self.options.to_wire(),
            "staging_dir": str(self.staging_dir),
            "device": self.device,
            "attempt": self.attempt,
        }

    def to_json(self) -> str:
        return _json_line(self.to_wire())

    @classmethod
    def from_wire(cls, value: Any) -> "ConversionRequest":
        obj = _object(value, "request")
        required = ("job_id", "input_path", "mode", "options", "staging_dir", "device")
        missing = [key for key in required if key not in obj]
        if missing:
            raise ValueError(f"request is missing required field(s): {', '.join(missing)}")
        mode = _string(obj["mode"], "mode")
        if mode not in MODES:
            raise ValueError(f"unsupported mode: {mode}")
        return cls(
            job_id=_string(obj["job_id"], "job_id"),
            input_path=_path_from_wire(obj["input_path"], "input_path", absolute=True),
            mode=mode,  # type: ignore[arg-type]
            options=ConversionOptions.from_wire(obj["options"]),
            staging_dir=_path_from_wire(obj["staging_dir"], "staging_dir", absolute=True),
            device=_string(obj["device"], "device"),
            attempt=_integer(obj.get("attempt", 1), "attempt", minimum=1),
        )

    @classmethod
    def from_json(cls, raw: str) -> "ConversionRequest":
        value = json.loads(raw, parse_constant=_reject_json_constant)
        return cls.from_wire(value)


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"invalid JSON numeric constant: {value}")


@dataclass(frozen=True, slots=True)
class RecoveredReference:
    page: int | None
    label: str | None
    destination: str

    def __post_init__(self) -> None:
        if self.page is not None:
            _integer(self.page, "reference.page", minimum=1)
        if self.label is not None:
            _string(self.label, "reference.label", nonempty=False)
        _string(self.destination, "reference.destination")

    def to_wire(self) -> dict[str, Any]:
        return {"page": self.page, "label": self.label, "destination": self.destination}

    @classmethod
    def from_wire(cls, value: Any) -> "RecoveredReference":
        obj = _object(value, "reference")
        if "destination" not in obj:
            raise ValueError("reference.destination is required")
        page = obj.get("page")
        if page is not None:
            page = _integer(page, "reference.page", minimum=1)
        label = obj.get("label")
        if label is not None:
            label = _string(label, "reference.label", nonempty=False)
        return cls(page=page, label=label, destination=_string(obj["destination"], "reference.destination"))


@dataclass(frozen=True, slots=True)
class EngineResult:
    markdown: str
    resources: tuple[Path, ...] = ()
    references: tuple[RecoveredReference, ...] = ()
    processed_pages: int = 0
    warnings: tuple[dict[str, Any], ...] = ()
    gaps: tuple[dict[str, Any], ...] = ()
    metrics: dict[str, float | int | str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _string(self.markdown, "markdown", nonempty=False)
        _integer(self.processed_pages, "processed_pages", minimum=0)
        for path in self.resources:
            _path(path, "resource", absolute=False)
            if ".." in path.parts:
                raise ValueError("resources must remain inside staging")
        if any(not isinstance(item, RecoveredReference) for item in self.references):
            raise ValueError("references must contain RecoveredReference values")
        _object_sequence(self.warnings, "warnings")
        _object_sequence(self.gaps, "gaps")
        _metrics(self.metrics)

    def to_wire(self) -> dict[str, Any]:
        return {
            "markdown": self.markdown,
            "resources": [str(path) for path in self.resources],
            "references": [reference.to_wire() for reference in self.references],
            "processed_pages": self.processed_pages,
            "warnings": json_value(self.warnings, "warnings"),
            "gaps": json_value(self.gaps, "gaps"),
            "metrics": json_value(self.metrics, "metrics"),
        }

    def to_json(self) -> str:
        return _json_line(self.to_wire())

    @classmethod
    def from_wire(cls, value: Any) -> "EngineResult":
        obj = _object(value, "engine_result")
        if "markdown" not in obj:
            raise ValueError("engine_result.markdown is required")
        return cls(
            markdown=_string(obj["markdown"], "markdown", nonempty=False),
            resources=tuple(_path_from_wire(path, "resource", absolute=False) for path in _array(obj.get("resources", []), "resources")),
            references=tuple(RecoveredReference.from_wire(item) for item in _array(obj.get("references", []), "references")),
            processed_pages=_integer(obj.get("processed_pages", 0), "processed_pages", minimum=0),
            warnings=tuple(_object(item, "warning") for item in _array(obj.get("warnings", []), "warnings")),
            gaps=tuple(_object(item, "gap") for item in _array(obj.get("gaps", []), "gaps")),
            metrics=_metrics(_object(obj.get("metrics", {}), "metrics")),
        )

    @classmethod
    def from_json(cls, raw: str) -> "EngineResult":
        return cls.from_wire(json.loads(raw, parse_constant=_reject_json_constant))


@dataclass(frozen=True, slots=True)
class JobResult:
    job_id: str
    input_path: Path
    mode: Mode
    engine: str
    device: str
    status: JobStatus
    output_paths: tuple[Path, ...] = ()
    warnings: tuple[dict[str, Any], ...] = ()
    errors: tuple[dict[str, Any], ...] = ()
    duration_seconds: float = 0.0
    attempts: int = 1

    def __post_init__(self) -> None:
        _string(self.job_id, "job_id")
        _path(self.input_path, "input_path", absolute=True)
        _string(self.engine, "engine")
        if self.mode not in MODES:
            raise ValueError(f"unsupported mode: {self.mode}")
        if self.device not in EFFECTIVE_DEVICES:
            raise ValueError(f"unsupported effective device: {self.device}")
        if self.status not in JOB_STATUSES:
            raise ValueError(f"unsupported job status: {self.status}")
        for path in self.output_paths:
            _path(path, "output_path", absolute=True)
        _object_sequence(self.warnings, "warnings")
        _object_sequence(self.errors, "errors")
        _finite_number(self.duration_seconds, "duration_seconds", minimum=0)
        _integer(self.attempts, "attempts", minimum=1)

    def to_wire(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "input_path": str(self.input_path),
            "mode": self.mode,
            "engine": self.engine,
            "device": self.device,
            "status": self.status,
            "output_paths": [str(path) for path in self.output_paths],
            "warnings": json_value(self.warnings, "warnings"),
            "errors": json_value(self.errors, "errors"),
            "duration_seconds": _finite_number(self.duration_seconds, "duration_seconds", minimum=0),
            "attempts": self.attempts,
        }

    def to_json(self) -> str:
        return _json_line(self.to_wire())

    @classmethod
    def from_wire(cls, value: Any) -> "JobResult":
        obj = _object(value, "job_result")
        required = ("job_id", "input_path", "mode", "engine", "device", "status")
        missing = [key for key in required if key not in obj]
        if missing:
            raise ValueError(f"job_result is missing required field(s): {', '.join(missing)}")
        mode = _string(obj["mode"], "mode")
        status = _string(obj["status"], "status")
        if mode not in MODES:
            raise ValueError(f"unsupported mode: {mode}")
        if status not in JOB_STATUSES:
            raise ValueError(f"unsupported job status: {status}")
        return cls(
            job_id=_string(obj["job_id"], "job_id"),
            input_path=_path_from_wire(obj["input_path"], "input_path", absolute=True),
            mode=mode,  # type: ignore[arg-type]
            engine=_string(obj["engine"], "engine"),
            device=_string(obj["device"], "device"),
            status=status,  # type: ignore[arg-type]
            output_paths=tuple(_path_from_wire(path, "output_path", absolute=True) for path in _array(obj.get("output_paths", []), "output_paths")),
            warnings=tuple(_object(item, "warning") for item in _array(obj.get("warnings", []), "warnings")),
            errors=tuple(_object(item, "error") for item in _array(obj.get("errors", []), "errors")),
            duration_seconds=_finite_number(obj.get("duration_seconds", 0), "duration_seconds", minimum=0),
            attempts=_integer(obj.get("attempts", 1), "attempts", minimum=1),
        )

    @classmethod
    def from_json(cls, raw: str) -> "JobResult":
        return cls.from_wire(json.loads(raw, parse_constant=_reject_json_constant))


@dataclass(frozen=True, slots=True)
class RunResult:
    run_id: str
    results: tuple[JobResult, ...]
    exit_code: int

    def __post_init__(self) -> None:
        _string(self.run_id, "run_id")
        if any(not isinstance(result, JobResult) for result in self.results):
            raise ValueError("results must contain JobResult values")
        _integer(self.exit_code, "exit_code")
        if self.exit_code not in RUN_EXIT_CODES:
            raise ValueError(f"unsupported exit code: {self.exit_code}")

    @property
    def totals(self) -> dict[str, int]:
        counts = {status: 0 for status in JOB_STATUSES}
        for result in self.results:
            counts[result.status] += 1
        return counts

    def to_wire(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "results": [result.to_wire() for result in self.results],
            "exit_code": self.exit_code,
            "totals": self.totals,
        }

    def to_json(self) -> str:
        return _json_line(self.to_wire())

    @classmethod
    def from_wire(cls, value: Any) -> "RunResult":
        obj = _object(value, "run_result")
        required = ("run_id", "results", "exit_code")
        missing = [key for key in required if key not in obj]
        if missing:
            raise ValueError(f"run_result is missing required field(s): {', '.join(missing)}")
        return cls(
            run_id=_string(obj["run_id"], "run_id"),
            results=tuple(JobResult.from_wire(item) for item in _array(obj["results"], "results")),
            exit_code=_integer(obj["exit_code"], "exit_code"),
        )

    @classmethod
    def from_json(cls, raw: str) -> "RunResult":
        return cls.from_wire(json.loads(raw, parse_constant=_reject_json_constant))


def _array(value: Any, name: str) -> list[Any] | tuple[Any, ...]:
    if not isinstance(value, list):
        raise ValueError(f"{name} must be an array")
    return value


def _object_sequence(value: Any, name: str) -> None:
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"{name} must be a sequence of objects")
    for item in value:
        _object(item, f"{name} item")
        json_value(item, name)


def _metrics(value: Any) -> dict[str, float | int | str]:
    obj = _object(value, "metrics")
    converted: dict[str, float | int | str] = {}
    for key, item in obj.items():
        if isinstance(item, bool) or not isinstance(item, (str, int, float)):
            raise ValueError(f"metric {key!r} must be a string or finite number")
        if isinstance(item, float) and not math.isfinite(item):
            raise ValueError(f"metric {key!r} must be finite")
        converted[key] = item
    return converted


class SamiError(Exception):
    """Base class for errors suitable for structured CLI reporting."""

    code = "SAMI_ERROR"


class InputError(SamiError):
    code = "INPUT_ERROR"


class AccelerationError(SamiError):
    code = "ACCELERATION_ERROR"
