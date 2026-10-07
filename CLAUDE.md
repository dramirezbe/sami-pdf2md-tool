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

## Dev Notes

- `llama-server` is auto-provisioned into `~/.sami/bin/` if not found on PATH
- `LLAMA_CPP_BINARY` env var overrides the llama-server path
- `HF_HOME` and `TORCH_HOME` are redirected to `~/.sami/cache/`
- Process cleanup kills orphaned llama-server processes on exit
