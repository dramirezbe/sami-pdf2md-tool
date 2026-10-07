# sami — Smart Automated Markdown Interpreter

Convert PDF files to Markdown with extracted figures. Local, keyless, no API needed.

For each PDF, sami creates a folder containing:
- `<name>.md` — text with LaTeX equations and Markdown tables
- Figure images referenced by the Markdown

Powered by [Marker](https://github.com/VikParuchuri/marker).

## Quick Install

```bash
curl -fsSL https://raw.githubusercontent.com/dramirezbe/sami-pdf2md-tool/main/install.sh | bash
```

This installs `uv` (if missing) and `sami` globally. On first run, `llama-server` and OCR models are downloaded automatically into `~/.sami/`.

### Other install methods

<details>
<summary>uv (manual)</summary>

```bash
uv tool install --python 3.12 git+https://github.com/dramirezbe/sami-pdf2md-tool.git
```

</details>

<details>
<summary>setup.sh (handles CUDA/GPU acceleration)</summary>

```bash
git clone https://github.com/dramirezbe/sami-pdf2md-tool.git
cd sami-pdf2md-tool
bash setup.sh install            # auto-detects GPU
bash setup.sh install --cpu      # force CPU
bash setup.sh install --cuda     # force CUDA
```

This provisions a micromamba environment with the correct PyTorch build (CPU or CUDA) and adds `sami` to your PATH.

</details>

<details>
<summary>From local clone</summary>

```bash
git clone https://github.com/dramirezbe/sami-pdf2md-tool.git
cd sami-pdf2md-tool
uv tool install --python 3.12 -e .
```

</details>

## Usage

```bash
sami paper.pdf                     # -> paper/paper.md + figures
sami paper.pdf -o out/             # -> out/paper.md + figures
sami a.pdf b.pdf                   # batch convert
sami paper.pdf --mode fast         # faster, lower quality
sami paper.pdf --no-strip-refs     # keep the references section
sami paper.pdf --flat              # no subfolder, output beside the PDF
sami paper.pdf -q                  # quiet mode
```

## Exit codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | At least one PDF failed |
| 2 | Usage error |

## App home (`~/.sami/`)

sami creates `~/.sami/` on first run:

```
~/.sami/
  bin/llama-server            # auto-downloaded llama.cpp server
  config/defaults.yaml        # default CLI flags
  cache/huggingface/          # downloaded models (surya-ocr, etc.)
  cache/torch/                # torch hub cache
  logs/
```

Override with `SAMI_HOME` environment variable.

## Uninstall

```bash
uv tool uninstall sami-pdf2md-tool
rm -rf ~/.sami
```

Or if installed via setup.sh:

```bash
bash setup.sh uninstall
```

## Requirements

- Python >= 3.11, < 3.14 (Pillow/marker-pdf compatibility)
- Linux or macOS (Windows not yet supported)

## Windows support

Not available in v1. The core conversion works, but subprocess lifecycle management (`SIGTERM`/`SIGKILL` for llama-server cleanup) and the shell installer need Windows-specific implementations. Planned for v2.

## License

MIT
