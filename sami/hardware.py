"""Hardware inventory for sami — GPU/VRAM detection without hard-importing Torch.

Returns four-part GPU evidence (physical device, driver, Torch CUDA runtime,
and inference engine capability) used by the engine adapters to decide the
llama.cpp -ngl offload layer count. All queries have bounded failure modes:
a missing tool or import returns None/unknown, never raises.
"""
from __future__ import annotations

import os
import subprocess
import sys
from typing import Any


# ---------------------------------------------------------------------------
# VRAM ladder for llama.cpp -ngl selection (quality VLM only)
# ---------------------------------------------------------------------------

_NGL_FULL_VRAM_GB = 8.0    # >= this: full offload
_NGL_PARTIAL_VRAM_GB = 4.0  # >= this, < _NGL_FULL: partial offload
# < _NGL_PARTIAL_VRAM_GB or no GPU: -ngl 0 (CPU)


def compute_ngl(vram_free_gb: float | None) -> tuple[int, str]:
    """Return (ngl_value, tier_label) for the quality VLM offload.

    tier_label is one of: "full", "partial", "cpu"
    ngl_value is -1 for full (meaning "all layers"), 0 for CPU, or a fixed
    partial count for the middle tier.

    Callers that need a concrete integer for --ngl should use:
        ngl if ngl >= 0 else 999   (or Marker's own "all layers" constant)
    """
    if vram_free_gb is None or vram_free_gb < _NGL_PARTIAL_VRAM_GB:
        return 0, "cpu"
    if vram_free_gb >= _NGL_FULL_VRAM_GB:
        return -1, "full"
    # 4–8 GB: partial offload. 20 layers is a reasonable estimate for
    # surya-ocr-2 at 4 GB; the caller may refine with model metadata.
    return 20, "partial"


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
    """Return four-part GPU evidence.

    Keys:
      physical_gpu     str | None   — GPU name from nvidia-smi, or None
      driver_version   str | None   — driver version from nvidia-smi, or None
      torch_cuda       bool | None  — True if torch.cuda.is_available()
      vram_total_gb    float | None — total VRAM in GiB (from nvidia-smi or Torch)
      vram_free_gb     float | None — free VRAM in GiB (from nvidia-smi); None if unknown
      ngl              int          — computed -ngl value (0 = CPU; -1 = full offload)
      ngl_tier         str          — "full" | "partial" | "cpu"
      source           str          — which probe provided VRAM data

    All fields are present. Missing data is None, not absent.
    A vram_free_gb of None does NOT mean no GPU: it means free VRAM is unknown;
    in that case ngl is computed from vram_total_gb (conservative).
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

    # Use free VRAM for the ngl ladder when available; fall back to total
    # (conservative: total includes already-loaded models).
    ngl_basis = vram_free_gb if vram_free_gb is not None else vram_total_gb
    ngl, ngl_tier = compute_ngl(ngl_basis)

    return {
        "physical_gpu": physical_gpu,
        "driver_version": driver_version,
        "torch_cuda": torch_cuda,
        "vram_total_gb": vram_total_gb,
        "vram_free_gb": vram_free_gb,
        "ngl": ngl,
        "ngl_tier": ngl_tier,
        "source": source,
    }


def describe_gpu(info: dict[str, Any]) -> str:
    """One-line human description of the GPU state for log output."""
    if info["physical_gpu"] is None and not info["torch_cuda"]:
        return "No GPU detected — CPU inference"
    name = info["physical_gpu"] or "GPU"
    vram = (
        f"{info['vram_free_gb']:.1f} GB free / {info['vram_total_gb']:.1f} GB total"
        if info["vram_free_gb"] is not None and info["vram_total_gb"] is not None
        else f"{info['vram_total_gb']:.1f} GB total"
        if info["vram_total_gb"] is not None
        else "VRAM unknown"
    )
    tier_msg = {
        "full": "full offload",
        "partial": f"partial offload (-ngl {info['ngl']})",
        "cpu": "CPU inference (-ngl 0)",
    }[info["ngl_tier"]]
    return f"{name} — {vram} — {tier_msg}"
