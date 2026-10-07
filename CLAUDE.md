# sami — Smart Automated Markdown Interpreter

Standalone PDF-to-Markdown converter using Marker. Opensource tool, local, keyless, no API needed.

## Project Structure

- `sami/cli.py` — main converter (entry point: `main()`)
- `sami/__init__.py` — package version
- `pyproject.toml` — packaging, entry point `sami = "sami.cli:main"`
- `setup.sh` — full installer (micromamba, CUDA/CPU detection, shell config)
- `install.sh` — one-line installer (`curl | bash`)
- `cpu_monitor.py` — dev-only CPU telemetry helper
- `test-pdfs/` — test PDFs and generator script

## Install

```bash
# One-line (end user, no clone needed):
curl -fsSL https://raw.githubusercontent.com/dramirezbe/sami-pdf2md-tool/main/install.sh | bash

# From clone (dev):
uv tool install --python 3.12 -e .

# With GPU support:
bash setup.sh install
```

## Usage

```bash
sami paper.pdf                        # -> paper/paper.md + figures
sami paper.pdf -o out/                # custom output dir
sami a.pdf b.pdf                      # batch convert
sami paper.pdf --mode fast            # RF-DETR layout, faster
sami paper.pdf --mode balanced        # VLM layout, more accurate
sami paper.pdf --no-strip-refs        # keep references section
sami paper.pdf --flat                 # no subfolder per PDF
sami paper.pdf -q                     # quiet mode
```

## Conversion Modes

| Mode | Layout Engine | Speed | Quality |
|------|--------------|-------|---------|
| auto (default) | Marker picks by device | varies | varies |
| `--mode fast` | RF-DETR | fast | good |
| `--mode balanced` | VLM | slower | better |

## Exit Codes

- 0: success
- 1: at least one PDF failed
- 2: usage error

## App Home (`~/.sami/`)

Auto-created on first run:
- `bin/llama-server` — auto-downloaded from llama.cpp releases
- `config/defaults.yaml` — user default CLI flags
- `cache/huggingface/` — surya-ocr models
- `cache/torch/` — torch hub cache
- `logs/`

Override location with `SAMI_HOME` env var.

## Key Dependencies

- `marker-pdf==2.0.0` — PDF conversion engine
- `surya-ocr` — OCR backend (uses llama-server for table processing)
- `psutil>=5.9` — CPU detection, process management
- `PyYAML>=6.0`
- Python `>=3.11,<3.14` (Pillow compatibility)

## Verified Test Results (2026-10-07)

### Machine 1: ASUS Vivobook M3504YA (local)
- **OS**: Arch Linux, kernel 7.2.5-3-omarchy
- **CPU**: 8 cores (7 threads used)
- **Install**: `curl | bash` → 102 packages, ~2s resolve
- **llama-server**: auto-downloaded `llama-b11476-bin-ubuntu-x64.tar.gz` to `~/.sami/bin/`
- **test_document.pdf**: 5 pages, 5 figures, 3.4 KB md, 2.3s (0.5s/page)
- **radio_env_5pages.pdf**: 5 pages, 3 figures, 25.9 KB md, 44.9s (9.0s/page) — includes 41s table OCR via llama-server
- **Summary**: 2 converted, 0 failed, 10 pages, 65.5s total

### Machine 2: nexus-rf (remote, clean install)
- **OS**: Ubuntu 24.04, kernel 7.1.5-76070105-generic
- **CPU**: 4 cores (3 threads used)
- **Install**: `curl | bash` on clean machine (no uv, no sami, no ~/.sami) → installed uv 0.12.23 + 102 packages
- **llama-server**: auto-downloaded on first `sami --help`
- **test_document.pdf**: 5 pages, 5 figures, 3.4 KB md, 59.1s (11.8s/page) — slower due to first-run model downloads
- **Summary**: 1 converted, 0 failed, 5 pages, 73.9s total

### Test PDFs

| File | Pages | Figures | Markdown | Notes |
|------|-------|---------|----------|-------|
| `test_document.pdf` | 5 | 5 | 3.4 KB | Text + tables + figures, no OCR needed |
| `radio_env_5pages.pdf` | 5 | 3 | 25.9 KB | Complex tables trigger llama-server OCR |

## Dev Notes

- `llama-server` is auto-provisioned into `~/.sami/bin/` if not found on PATH
- `LLAMA_CPP_BINARY` env var overrides the llama-server path
- `HF_HOME` and `TORCH_HOME` are redirected to `~/.sami/cache/`
- Process cleanup kills orphaned llama-server processes on exit
