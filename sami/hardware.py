"""GPU, driver and VRAM inventory with an optional Torch probe."""
from __future__ import annotations

import subprocess
from typing import Any


# ---------------------------------------------------------------------------
# Physical GPU / driver probe (no Torch required)
# ---------------------------------------------------------------------------

def _probe_nvidia_smi() -> dict[str, Any] | None:
    """Query nvidia-smi for GPU name, total VRAM, and free VRAM (MiB)."""
    try:
        out = subprocess.run(
            ["nvidia-smi",
             "--query-gpu=name,memory.total,memory.free,driver_version",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5,
        )
        if out.returncode != 0:
            return None
        lines = [l.strip() for l in out.stdout.strip().splitlines() if l.strip()]
        if not lines:
            return None
        # Take first GPU only (device 0, matching torch.cuda.get_device_properties(0))
        parts = [p.strip() for p in lines[0].split(",")]
        if len(parts) < 4:
            return None
        name, mem_total, mem_free, driver = parts[:4]
        return {
            "name": name,
            "vram_total_mib": int(mem_total),
            "vram_free_mib": int(mem_free),
            "driver_version": driver,
        }
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Torch CUDA runtime probe (soft import)
# ---------------------------------------------------------------------------

def _probe_torch_cuda() -> dict[str, Any] | None:
    """Return Torch CUDA availability and device-0 properties, or None."""
    try:
        import torch  # noqa: PLC0415 — intentional deferred import
        if not torch.cuda.is_available():
            return {"available": False}
        props = torch.cuda.get_device_properties(0)
        return {
            "available": True,
            "device_name": props.name,
            "vram_total_mib": props.total_memory // (1024 * 1024),
        }
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def gpu_info() -> dict[str, Any]:
    """Return the GPU inventory used in diagnostics.

    Keys:
      physical_gpu     str | None   — GPU name from nvidia-smi, or None
      driver_version   str | None   — driver version from nvidia-smi, or None
      torch_cuda       bool | None  — True if torch.cuda.is_available()
      vram_total_gb    float | None — total VRAM in GiB (from nvidia-smi or Torch)
      vram_free_gb     float | None — free VRAM in GiB (from nvidia-smi); None if unknown
      source           str          — which probe provided VRAM data

    Missing readings are represented by None.
    """
    smi = _probe_nvidia_smi()
    torch_info = _probe_torch_cuda()

    physical_gpu: str | None = None
    driver_version: str | None = None
    vram_total_gb: float | None = None
    vram_free_gb: float | None = None
    source = "none"

    if smi:
        physical_gpu = smi["name"]
        driver_version = smi["driver_version"]
        vram_total_gb = smi["vram_total_mib"] / 1024.0
        vram_free_gb = smi["vram_free_mib"] / 1024.0
        source = "nvidia-smi"
    elif torch_info and torch_info.get("available"):
        physical_gpu = torch_info.get("device_name")
        vram_total_gb = torch_info["vram_total_mib"] / 1024.0
        source = "torch"

    torch_cuda: bool | None = None
    if torch_info is not None:
        torch_cuda = bool(torch_info.get("available", False))

    return {
        "physical_gpu": physical_gpu,
        "driver_version": driver_version,
        "torch_cuda": torch_cuda,
        "vram_total_gb": vram_total_gb,
        "vram_free_gb": vram_free_gb,
        "source": source,
    }


def describe_gpu(info: dict[str, Any]) -> str:
    """Format the available hardware readings for the CLI."""
    if info["physical_gpu"] is None and not info["torch_cuda"]:
        return "no GPU reported by nvidia-smi or Torch"
    name = info["physical_gpu"] or "GPU"
    vram = (
        f"{info['vram_free_gb']:.1f} GiB free / {info['vram_total_gb']:.1f} GiB total"
        if info["vram_free_gb"] is not None and info["vram_total_gb"] is not None
        else f"{info['vram_total_gb']:.1f} GiB total"
        if info["vram_total_gb"] is not None
        else "VRAM unknown"
    )
    return f"{name} — {vram}"
