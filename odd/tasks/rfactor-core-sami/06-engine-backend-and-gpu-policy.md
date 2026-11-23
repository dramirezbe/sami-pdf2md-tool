# 06 — Engine backend and GPU policy (implementation decision)

Date: 2026-11-23, America/Bogota. Status: **decision, authorized to implement**.
Branch: `refactor/0_2_0_sami_cli`. Binds into [01 — engines](01-cli-contracts-engines-outputs.md) (U01), [02 — runtime/installation](02-cli-diagnostics-runtime-installation.md) (U03–U05), and the [index requirements](2026-11-18_10-31-38_sami-refactor-plan.md).
Read first: [index](2026-11-18_10-31-38_sami-refactor-plan.md) and [U00/U01 evidence](U00-U01-evidence.md).

## Why this document exists

Plans 01–02 specify the engines generically ("server binary", "where the actual VLM executes"). U00 evidence showed two concrete problems this decision closes:

- The default Marker VLM path attempted `docker run vllm/vllm-openai:v0.20.1` and stalled; it only ran after the backend was forced to local llama.cpp by hand. Docker + NVIDIA Container Toolkit **does not exist on native Windows** (only WSL2, which U00 marks as not Windows-native evidence). A Docker-based heavy mode is therefore not Windows-portable.
- `sami/engines/marker.py:_resolve_mode()` auto-switches the public mode to `fast` when VRAM < 8 GB. This **contradicts plan 02 U04** ("Warn, use CPU in the **same mode**") and silently changes the user's requested output engine.

Decision: standardize **all** heavy inference on local `llama.cpp` (llama-server + GGUF), drive GPU/CPU purely through the Torch device and a VRAM-scaled `-ngl` layer count, and never change the public mode on account of hardware. This is the one configuration that is keyless, fully local, and byte-for-byte identical on Windows 11 and Debian-based Linux.

## D1 — Backend is llama.cpp GGUF; Docker/vllm is prohibited

- The only inference backend for Marker's VLM layout is `llama-server` (llama.cpp) with GGUF weights (`datalab-to/surya-ocr-2-gguf`). Configure it explicitly at engine startup so Marker/Surya never fall back to vllm or Docker.
- Bake the backend selection into the adapter, not into ad-hoc environment variables the operator must remember. The equivalent of `SURYA_INFERENCE_BACKEND=llamacpp` plus the local GGUF/mmproj paths and the layer count must be set by `sami` itself before Marker loads.
- `LLAMA_CPP_BINARY` continues to override the server path. No `docker`, no `vllm`, no network inference. A machine without Docker must run every mode.

## D2 — Per-mode backend and device matrix

| Public mode | Engine | Layout backend | Inference server | Device policy |
|---|---|---|---|---|
| `fast` | Fast engine | PyMuPDF heuristics | none | CPU only; no Torch models, no server provisioning. |
| `balanced` (**default**) | Marker, internal `fast` | RF-DETR (Torch) | **none** | Torch device = CUDA if usable, else CPU. Fully portable with no inference server. |
| `quality` | Marker, internal `balanced` | VLM | llama-server + GGUF | VLM runs on llama.cpp with `-ngl` scaled to VRAM (see D3); CPU = `-ngl 0`. |

Consequence: only `quality` needs the inference server. `balanced` (the default) needs Torch but **no server**, so the common path has no server dependency on either OS. Measured baselines (5-page PDFs, CPU, from U00): `fast` 0.08–1.3 s; `balanced` ~15 s; `quality` ~153–174 s. GPU offload reduces `quality` substantially.

## D3 — GPU autodetection: scaled offload, never a mode switch

Replace the binary 8 GB cutoff in `_resolve_mode()` with a VRAM-to-`-ngl` ladder applied **only** to the `quality` VLM server. The public mode the user asked for is never changed by hardware.

| Detected VRAM (free, with headroom) | `quality` VLM offload | Effect |
|---|---|---|
| ≥ 8 GB | Full offload (`-ngl` = all layers) | Fast `quality`. |
| ~4–8 GB | Partial offload (`-ngl` = N layers that fit) | `quality` still runs, slower; emit a `warning` with the chosen layer count. |
| No usable GPU / < ~4 GB | CPU (`-ngl 0`) | `quality` runs on CPU; emit `GPU_FALLBACK_CPU`. |

- `balanced` (RF-DETR) uses the Torch device directly: CUDA if `torch.cuda.is_available()` and VRAM is sufficient for the detector, else CPU. It never requires the ladder above.
- A GPU failure during startup or inference follows plan 02 U04: stop the owned GPU worker, emit `job_retrying`, retry the document **once** on CPU in the **same mode**. No CPU↔GPU loop, no silent mode downgrade.
- Detect the GPU as plan 02 U03 requires (physical GPU / driver / runtime / engine as four separate facts). `torch.cuda` alone is evidence of a Torch CUDA runtime, not of a working VLM; validation must confirm where the VLM actually executed.

## D4 — Windows + Linux parity requirements

1. **llama-server Windows binary.** Today `install.sh` fetches `llama-b*-bin-ubuntu-x64.tar.gz`. `install.ps1` (plan 02 U05) must fetch the matching `llama-*-bin-win-*` build and register `llama-server.exe`, honoring `LLAMA_CPP_BINARY`. **This is the #1 blocker for `quality` on native Windows.**
2. **Torch wheel by OS/accelerator.** The runtime manifest (plan 02) selects the correct Torch wheel (CUDA vs CPU) per platform; the installer must not let a generic resolver swap GPU Torch for CPU Torch or vice versa (already required by plan 02; this decision makes it apply to the Windows path too).
3. **Models precached at install.** All three modes work offline after installation: RF-DETR detector models and the surya GGUF/mmproj for `quality`. A missing model is an incomplete installation, never a first-run download (plan 02 U04).
4. **No POSIX-only assumptions in process control.** Owned-process cancellation uses the Windows process-tree mechanism, not `SIGKILL` (already in plan 02 U04); the backend decision adds no new POSIX dependency.
5. **Update CLAUDE.md GPU section.** The current "≥ 8 GB VRAM → VLM via Docker + NVIDIA Container Toolkit" guidance is superseded by D1–D3 and must be rewritten when the code lands (not a plan file, tracked here so it is not forgotten).

## Implementation order (start here)

1. **`sami/engines/marker.py`** — remove the mode-switching `_resolve_mode()`; keep VRAM detection but use it only to compute the `quality` `-ngl` layer count (D3). Set the llama.cpp backend + local GGUF paths explicitly before `create_model_dict()` (D1). `balanced` selects the Torch device without touching the ladder.
2. **`sami/hardware.py` (plan 02 U03)** — expose total/free VRAM and the four-part GPU evidence used by the ladder; persist it in the profile.
3. **`sami/runtime.py` / `packaging/runtime-manifest.json` (plan 02 U04)** — pin the GGUF identities, the llama-server build per OS, and the Torch wheel per accelerator; precache at install.
4. **`install.ps1` (plan 02 U05)** — Windows llama-server binary + PATH registration (D4.1).
5. **CLAUDE.md** — rewrite the GPU section per D1–D3 (D4.5).

## Tests to add (bind into existing unit suites)

- `quality` VLM is configured for llama.cpp with the local GGUF paths and **never** invokes Docker/vllm (assert the backend config; no network/Docker call).
- VRAM ladder: ≥8 / 4–8 / <4 GB (and no GPU) produce full / partial / zero `-ngl` respectively, and in every case the **public mode is unchanged** and a `GPU_FALLBACK_CPU` or partial-offload `warning` is emitted when degraded.
- `balanced` builds its converter with **no** inference server started and selects CPU when CUDA is unavailable.
- A simulated GPU startup failure yields exactly one CPU retry in the same mode and one terminal `JobResult` (plan 01 U01 / plan 02 U04).
- Windows process-tree cancellation of an owned llama-server with a child/grandchild (plan 02 U04), using fake processes.

## Out of scope for 0.2.0 (recorded, not now)

- An `auto` mode that measures output fidelity and escalates `fast → balanced → quality` only when needed. The notebook's independent-QC layer (PyMuPDF/pdfminer) is the measurement that would drive it. The index freezes the three modes as explicit, so auto-escalation is a 0.3.0+ follow-up, not a 0.2.0 engine change.
- Replacing any engine with the notebook's PyMuPDF converter. The `fast` engine already covers that niche; adding it as a fourth engine violates the fixed "preserve Marker, fast engine as `fast`" requirement.
