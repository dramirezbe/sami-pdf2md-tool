# U00/U01 Runtime and Contract Evidence

Recorded 2026-11-18 on branch `refactor/0_2_0_sami_cli`. This report records evidence collected during implementation; U00 and U01 remain incomplete.

## Source and reproducible environment

The plan baseline is `6452f12`; the branch base is `43007b591e34109311d71c33dd2f7c6be1164e53`. The production files in scope are identical:

```sh
git diff --exit-code 6452f12 43007b5 -- sami pyproject.toml requirements.txt
```

Exit status: 0 (no diff). The commit IDs differ, but the compared production paths do not.

Chosen reproducible environment: private project `.venv`, created from uv-managed CPython 3.12.13, pinned by `uv.lock` (SHA-256 `4d3b32c90657f6637cc9af0c947924a8edfaa1908eaaed633908de0a76a0a445`). Tool: uv 0.12.1. Relevant exact packages: Marker 2.0.0, Surya 0.22.1, Torch 2.15.0 (CUDA 13.2 build), Transformers 5.23.0, torchvision 0.29.2, pypdfium2 5.10.1, pdfplumber 0.11.9, PyMuPDF 2.1, PyYAML 6.0.3, onnxruntime 1.32.0. Run `uv sync --locked --no-dev` to reproduce the runtime install from this lock; it completed successfully without broad dependency re-resolution. The default host Python 3.14.4 is outside the project's declared `<3.14` range.

Host: Ubuntu 26.04.1 x86_64 in WSL2, 12 logical / 6 physical CPU cores, 7.6 GiB RAM, NVIDIA RTX 3050 Laptop GPU with 4096 MiB VRAM, driver 621.24. This is one WSL environment, not native Windows evidence and not a Debian/Ubuntu support matrix.

Models used from local caches:

- Surya GGUF repository `datalab-to/surya-ocr-2-gguf`, revision `6a3a4c30e5e74446d4f8b6afd05b2f2da970f470`: `surya-2.gguf` (1,266,400,864 bytes), `surya-2-mmproj.gguf` (204,986,688 bytes).
- `surya_layout2` revision `0aee81d5fd9275c0582e545bf3a56944b1e75679`.
- `surya-ocr-2` revision `3b3d4cdf88d6928b0acdc75181b13206ea67c4a3`.
- S3 OCR error model version `2025_02_18`.

The first run downloaded the 259 MiB OCR error model. The later CPU comparisons reused the local cache. Model/cache contents are outside the repository; GGUF files are under `/home/javastral/.sami/cache/huggingface/hub`, and the additional model cache under `/home/javastral/.cache/datalab/models`.

## Backend startup and CPU verification

The initial legacy Marker fast run of `test_document.pdf`, with normal CUDA visibility, completed in 15.7 seconds (five pages, 31 layout blocks, five figures, 3.4 KB Markdown). This is a Marker fast result, not Caste. The first legacy fast run on `radio_env_5pages.pdf` reached `LLMTableProcessor` and stalled while attempting `docker run vllm/vllm-openai:v0.20.1`; `docker image inspect vllm/vllm-openai:v0.20.1` found no local image. This run was interrupted after a bounded wait. A subsequent run with downloaded models still tried the VLM server. Logs from the early attempt are in the session's runtime logs; the successful repeat comparisons below used an explicitly configured local llama.cpp backend.

CPU run environment (paths shown exactly as used):

```sh
export HOME=/tmp/sami-runtime-evidence/cpu-home
export SAMI_HOME=/tmp/sami-runtime-evidence/cpu-home/.sami
export HF_HOME=/home/javastral/.sami/cache/huggingface
export HF_HUB_CACHE=/home/javastral/.sami/cache/huggingface/hub
export MODEL_CACHE_DIR=/home/javastral/.cache/datalab/models
export LLAMA_CPP_BINARY=/home/javastral/.sami/bin/llama-server
export SURYA_GGUF_LOCAL_MODEL_PATH=/home/javastral/.sami/cache/huggingface/hub/models--datalab-to--surya-ocr-2-gguf/snapshots/6a3a4c30e5e74446d4f8b6afd05b2f2da970f470/surya-2.gguf
export SURYA_GGUF_LOCAL_MMPROJ_PATH=/home/javastral/.sami/cache/huggingface/hub/models--datalab-to--surya-ocr-2-gguf/snapshots/6a3a4c30e5e74446d4f8b6afd05b2f2da970f470/surya-2-mmproj.gguf
export CUDA_VISIBLE_DEVICES=
export TORCH_DEVICE=cpu
export FAST_DETECTOR_DEVICE=cpu
export SURYA_INFERENCE_BACKEND=llamacpp
export LLAMA_CPP_NGL=0
export SURYA_INFERENCE_PARALLEL=1
# Surya layout/OCR/VLM startup timeouts were each bounded at 60 seconds.
```

Preflight showed `torch.cuda.is_available() == False`, `TORCH_DEVICE_MODEL=cpu`, `FAST_DETECTOR_DEVICE=cpu`, backend `llamacpp`, and `LLAMA_CPP_NGL=0`. Server logs show the pinned local GGUF and mmproj loaded, llama-server 0.6.0-dev (build 11485, commit `bd4eeaa04`) listened on its local port, and an inference completed at about 23.23 tokens/s. The server process arguments included `-ngl 0`; its process environment had CUDA hidden and CPU selected. `nvidia-smi --query-compute-apps` showed no compute processes during this server run. This verifies CPU execution for these Linux/WSL runs; it does not establish Windows CPU feasibility.

Commands used for the bounded CLI comparisons were:

```sh
.venv/bin/python -m sami.cli --mode fast test-pdfs/test_document.pdf
.venv/bin/python -m sami.cli --mode fast test-pdfs/radio_env_5pages.pdf
.venv/bin/python -m sami.cli --mode balanced test-pdfs/test_document.pdf
.venv/bin/python -m sami.cli --mode balanced test-pdfs/radio_env_5pages.pdf
```

The legacy checkout was materialized without creating a Git branch using `git archive 6452f12 sami | tar -x -C /tmp/sami-runtime-evidence/baseline-6452`; the same locked `.venv`, model cache, and CPU environment ran those four commands with the old source. Each invocation used a 420-second process timeout. Both modes completed on both inputs, with 0 failures. Each PDF has five pages.

| Mode and input | Legacy source total | Extracted CLI total | Legacy/extracted Markdown SHA-256 | Comparison |
|---|---:|---:|---|---|
| Marker fast, `test_document.pdf` | 15.3 s CPU run (the separate GPU-visible initial run was 15.7 s) | 15.3 s | `7c2fbc09f7232d2d232d3d6687b4be6d6f56d71f846a509303e8e00b7d6a45c8` | byte-identical |
| Marker fast, `radio_env_5pages.pdf` | included in 65.9 s two-file batch | included in 65.9 s two-file batch | `9f64f462a6ef00703b15c1c3b103ff06efdb6991d2651c571389ea0d927405f2` | byte-identical |
| Marker balanced, `test_document.pdf` | 153.5 s pipeline; 167.1 s CLI total | 153.5 s pipeline; 153.5 s CLI total | `85ff0017783691504268add3c9e7098bd106f9222eb9640d2809e2ae7f68dec3` | byte-identical |
| Marker balanced, `radio_env_5pages.pdf` | 153.2 s pipeline; 153.4 s CLI total | 160.6 s CLI total | `0dd4442ea0f890bc94b2e57e94c1e44e77ce6b13cd8e1d68fe161345966cdd09` | byte-identical |

Logs and Markdown/figure artifacts are under `/tmp/sami-runtime-evidence/{legacy-source-fast,legacy-source-balanced,cpu-fast-test_document,cpu-fast-radio,cpu-balanced-test_document,cpu-balanced-radio}`. Per-run logs have matching directory names with `.log` suffix. These results show adapter preservation on this two-file corpus; they are not a content-quality study.

## Caste fast comparison

The extracted Caste adapter ran its declared profile `quality=high, ocr=false, images=false, markers=true, table_style=pipe, max_pages=None` on the same two PDFs, in the same `.venv`. Artifacts and `run-summary.txt` are in `/tmp/sami-runtime-evidence/caste-results`.

- `test_document.pdf`: 5 pages; adapter elapsed 0.080 s (conversion before output file write); 2,805 Markdown bytes; SHA-256 `43ec7cf4628543a20f21eeb5a8df8d99f560c29166f8101b3c66af962e7cff66`; five tables, no images, 15 warnings.
- `radio_env_5pages.pdf`: 5 pages; adapter elapsed 1.304 s (conversion before output file write); 24,623 Markdown bytes; SHA-256 `911000fb44eeaec257ae4b44e5004e522ed89f54f327719b12d210834f80052a`; no tables or images detected, nine warnings.

These timings exclude output writing and are not directly comparable with end-to-end CLI totals. Caste produced materially different output; no claim of equivalent content quality is made. The old 15.7-second result is Marker fast and is not Caste performance evidence.

## Automated checks and current implementation

Run:

```sh
.venv/bin/python -m unittest discover -s tests -v
git diff --check
```

Outcome before CLI integration: 21 tests passed in 0.260 s. Latest suite after integration: 25 tests passed in 0.324 s; whitespace check clean. Tests exercise request/result/event wire round trips, Unicode and spaced paths, nested path values, optional and required field validation, unsupported values and nonfinite numbers, additive fields, sequence increments, JSONL framing with multiple messages and fragmented UTF-8 input, mode dispatch laziness, JSON CLI success, conversion failure, engine startup failure, publication, effective-device selection, and CLI import/help/version side effects. CLI startup checks confirm no app-home creation, downloads, heavy engine imports, or signal handler mutation for import, `--help`, or `--version`.

Framing boundary: `Event.to_json_line()` emits one JSON record without a line terminator; `encode_jsonl()` appends LF per record; `JsonlEventDecoder` owns byte buffering and record splitting for fragmented streams. The tests cover fragmented UTF-8 and multiple records.


## Public CLI integration added after the baseline runs

The CLI maps `fast` to Caste, `balanced` to Marker internal `fast`, and `quality` to Marker internal `balanced`; default is `balanced`. Its effective device field reports Caste as CPU and accounts for explicit Torch/detector settings and llama.cpp layer offload. It creates a `ConversionRequest` per unique resolved input, adapts `EngineResult` into a `JobResult`, and emits `run_started`, `inputs_resolved`, `job_started`, Marker `job_progress`, warnings, `job_finished`, and `run_finished` events. In `--json` mode dependency stdout is redirected to stderr and events use the original stdout stream. `--no-strip-refs` remains accepted but reference stripping is no longer applied. Caste fast startup skips llama-server provisioning.

`tests/test_cli_json.py` mocks the engine and checks deduplication, no llama provisioning for Caste, backend-aware effective device, output publication, Unicode, increasing sequence numbers, JSON-only stdout, and dependency chatter redirected to stderr. Actual CLI integration runs used the CPU environment with 60/90/240 second timeouts:

```sh
timeout 60s env HOME=/tmp/sami-runtime-evidence/cpu-home SAMI_HOME=/tmp/sami-runtime-evidence/cpu-home/.sami HF_HOME=/home/javastral/.sami/cache/huggingface HF_HUB_CACHE=/home/javastral/.sami/cache/huggingface/hub MODEL_CACHE_DIR=/home/javastral/.cache/datalab/models LLAMA_CPP_BINARY=/home/javastral/.sami/bin/llama-server TORCH_DEVICE=cpu CUDA_VISIBLE_DEVICES= .venv/bin/python -m sami.cli --mode fast --json --output /tmp/sami-runtime-evidence/cli-json-caste-verified test-pdfs/test_document.pdf
timeout 90s env HOME=/tmp/sami-runtime-evidence/cpu-home SAMI_HOME=/tmp/sami-runtime-evidence/cpu-home/.sami HF_HOME=/home/javastral/.sami/cache/huggingface HF_HUB_CACHE=/home/javastral/.sami/cache/huggingface/hub MODEL_CACHE_DIR=/home/javastral/.cache/datalab/models LLAMA_CPP_BINARY=/home/javastral/.sami/bin/llama-server TORCH_DEVICE=cpu FAST_DETECTOR_DEVICE=cpu SURYA_INFERENCE_BACKEND=llamacpp LLAMA_CPP_NGL=0 SURYA_INFERENCE_PARALLEL=1 CUDA_VISIBLE_DEVICES= .venv/bin/python -m sami.cli --mode balanced --json --output /tmp/sami-runtime-evidence/cli-json-balanced test-pdfs/test_document.pdf
timeout 240s env HOME=/tmp/sami-runtime-evidence/cpu-home SAMI_HOME=/tmp/sami-runtime-evidence/cpu-home/.sami HF_HOME=/home/javastral/.sami/cache/huggingface HF_HUB_CACHE=/home/javastral/.sami/cache/huggingface/hub MODEL_CACHE_DIR=/home/javastral/.cache/datalab/models LLAMA_CPP_BINARY=/home/javastral/.sami/bin/llama-server TORCH_DEVICE=cpu FAST_DETECTOR_DEVICE=cpu SURYA_INFERENCE_BACKEND=llamacpp LLAMA_CPP_NGL=0 SURYA_INFERENCE_PARALLEL=1 CUDA_VISIBLE_DEVICES= .venv/bin/python -m sami.cli --mode quality --json --output /tmp/sami-runtime-evidence/cli-json-quality test-pdfs/test_document.pdf
```

All runs exited 0 and wrote five-page outputs. Fast took about 0.17 s and emitted 20 valid events. Balanced took 12.2 s total, emitted 41 valid events including 36 `job_progress` events, and matched legacy Marker fast byte-for-byte (Markdown SHA-256 `7c2fbc09f7232d2d232d3d6687b4be6d6f56d71f846a509303e8e00b7d6a45c8`). Quality took 174.3 s total and matched legacy Marker balanced byte-for-byte (SHA-256 `85ff0017783691504268add3c9e7098bd106f9222eb9640d2809e2ae7f68dec3`). Quality ran before the progress-relay fix; balanced was rerun after it to verify stage events. Artifacts are under `/tmp/sami-runtime-evidence/cli-json-{caste-verified,balanced,quality}`. Captured streams are `/tmp/sami-runtime-evidence/cli-json-caste.stdout.jsonl`, `cli-json-caste.stderr.log`, `cli-json-balanced.stdout.jsonl`, `cli-json-balanced.stderr.log`, `cli-json-quality.stdout.jsonl`, and `cli-json-quality.stderr.log`.

## Remaining acceptance gaps and next actions

### U00 — still incomplete

- Native Windows 11 CPU conversion and inference-server evidence. WSL is not evidence of native Windows support.
- Testing on defined Debian/Ubuntu releases with an explicit platform/architecture/backend matrix.
- Clean-cache startup, complete model-download behavior, readiness timing, and RAM limits. The successful warm-cache reruns do not establish this.
- Broader corpus/content review for figures, tables, equations, references/links, and scans. Preserve different expectations for Caste and Marker; byte parity on two PDFs is not a quality study.
- Complete inference-service startup and failure-path evidence, including failed downloads/readiness, timeouts, process cleanup, and recovery. Initial Marker fast exposed a VLM/Docker startup dependency; the successful local llama.cpp reruns do not close those failure paths.

Collect bounded startup/inference evidence on supported target hosts. Record unavailable native Windows or distribution evidence as unavailable, not passed.

### U01 — still incomplete

- Guarantee a terminal `cancelled` `JobResult` and `run_finished` on interruption, with process/staging cleanup. The existing signal-handler path does not guarantee them.
- Collision-safe naming/publication is not yet implemented; current output may overwrite existing files. This is planned for U02 and remains an outstanding integration dependency.
- Complete error events for failures before job processing, including app-home and runtime setup.
- Implement the planned `health --json` and `--control-stdin` interfaces in their scheduled units and verify their public integration.
- Review output beyond byte-for-byte Marker parity on the two test PDFs.

CLI modes, job/result conversion, and JSONL lifecycle events are connected, but those partial successes do not close U01.

### U02 and later units

Caste is extracted and smoke-tested, but its content behavior needs broader corpus review. Numbered outputs, safe publication, diagnostics persistence, the fast health check, full CPU fallback/supervision, complete installation, remaining CLI behavior, and release acceptance remain planned work. UI `0.3.0` remains a separate later delivery.

### Resume and evidence preservation

Read the [implementation index and gap checklist](2026-11-18_10-31-38_sami-refactor-plan.md) before continuing. Re-run the focused test suite and record the current SHA/environment; do not infer that this report's earlier runs cover future changes. Artifacts under `/tmp` and user caches are local-only; Git preserves this written evidence and source, not the runtime artifacts/models. Regenerate missing evidence or state its absence explicitly.

No U00/U01 completion claim is made here. No UI, release, merge, or new branch was created.

## Handoff verification

Before saving the handoff, reran `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest discover -s tests -v`: **25 tests passed in 0.242 s**. `git diff --check` and the planning documents' local-link/fence checks passed. No additional model downloads, conversions, platform tests, or inference-service failure tests were run for this handoff. The remaining acceptance gaps above are unchanged.
