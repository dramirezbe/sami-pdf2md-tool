"""Mode table and deferred dispatch for conversion engine adapters."""
from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from typing import Any, Callable

from sami.contracts import ConversionRequest, EngineResult, MODES


@dataclass(frozen=True, slots=True)
class EngineSelection:
    engine: str
    module: str
    profile: str | None = None


MODE_TABLE = {
    "fast": EngineSelection("caste", "sami.engines.fast"),
    "balanced": EngineSelection("marker", "sami.engines.marker", "fast"),
    "quality": EngineSelection("marker", "sami.engines.marker", "balanced"),
}


def select_engine(mode: str) -> EngineSelection:
    """Resolve a public mode without importing its engine or model stack."""
    if mode not in MODES:
        raise ValueError(f"unsupported mode: {mode}")
    return MODE_TABLE[mode]


def convert(
    request: ConversionRequest,
    *,
    cpu_config: dict[str, Any] | None = None,
    logger: Callable[..., Any] | None = None,
    stage_logger: Callable[..., Any] | None = None,
    stage_done_logger: Callable[..., Any] | None = None,
    converter: Any | None = None,
    app_home: Any | None = None,
) -> EngineResult:
    """Import and run the adapter selected by the request's public mode."""
    selection = select_engine(request.mode)
    adapter = import_module(selection.module)
    if selection.engine == "caste":
        return adapter.convert(request)
    if cpu_config is None or logger is None or stage_logger is None or stage_done_logger is None:
        raise ValueError("Marker conversion requires CPU configuration and progress callbacks")
    return adapter.convert(
        request,
        marker_mode=selection.profile,
        cpu_config=cpu_config,
        logger=logger,
        stage_logger=stage_logger,
        stage_done_logger=stage_done_logger,
        converter=converter,
        app_home=app_home,
    )
