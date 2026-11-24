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

This installs `uv` (if missing) and `sami` globally. On first use, SAMI downloads `llama-server` and OCR models into `~/.sami/`. When the NVIDIA driver and available VRAM support it, SAMI downloads and verifies the CUDA build of `llama-server` and its matching runtime libraries.

### Windows PowerShell

Install from PowerShell 5.1 or later:

```powershell
$repo = 'dramirezbe/sami-pdf2md-tool'
$ref = 'main'
$installer = irm "https://raw.githubusercontent.com/$repo/refs/heads/$ref/install.ps1"
& ([scriptblock]::Create($installer)) -Source "git+https://github.com/${repo}.git@$ref"
```

Verify the installation and convert a PDF:

```powershell
sami --version
sami paper.pdf --mode balanced
```

On x64 with an NVIDIA driver that supports CUDA 13.2 or later, the installer downloads the PyTorch CUDA wheel directly from PyTorch and verifies its SHA-256. For a local wheel, use its path as the value of `-Source`.

### Upgrade an installed CLI

```shell
sami upgrade
```

The command fetches the installer with `irm` on Windows or `curl` on Linux. It updates SAMI in its existing Python environment and reuses compatible dependencies, including PyTorch. Model caches stay in place.

By default, the command follows the installed Git ref, or `main` for a wheel install. To choose a different branch, tag, or commit, run `sami upgrade --ref <ref>`. On Windows, wait for the installer to report completion before starting another SAMI command.

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

## Conversion Modes

| Mode | Flag | Layout Engine | Best for |
|------|------|--------------|----------|
| fast | `--mode fast` | PyMuPDF and pdfplumber on CPU | Speed |
| balanced | `--mode balanced` *(default)* | RF-DETR on CUDA when available, with llama.cpp for OCR as needed | General use |
| quality | `--mode quality` | llama.cpp VLM with GPU offload according to free VRAM | Layout quality |

At model load, llama.cpp fits VLM layers to the free VRAM and the memory required for the current model and context. When CUDA or automatic fitting is unavailable, SAMI uses the CPU. Set `LLAMA_CPP_NGL` to an explicit layer count, or set it to `0` to run the VLM on CPU.

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
  bin/cpu/                    # CPU llama.cpp runtime
  bin/cuda/                   # CUDA llama.cpp runtime, when available
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
