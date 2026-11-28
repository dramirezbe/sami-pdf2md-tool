# sami — Smart Automated Markdown Interpreter

Convert PDF files to Markdown with extracted figures. Local, keyless, no API needed.

**[Website](https://dramirezbe.github.io/sami-pdf2md-tool/)** · **[Getting Started](https://dramirezbe.github.io/sami-pdf2md-tool/getting-started.html)** · **[Releases](https://github.com/dramirezbe/sami-pdf2md-tool/releases)**

For each PDF, SAMI creates a folder containing:

- `<name>.md` — text with LaTeX equations and Markdown tables
- Figure images referenced by the Markdown

Powered by [Marker](https://github.com/VikParuchuri/marker).

## Desktop app

SAMI Desktop lets you add several PDFs or folders, review the list, and start a conversion with **Convert**. It shows the active document, elapsed time, batch progress, and an estimated percentage for the current file. When available, live model details include the current phase, completed pages or blocks, tokens, and processing speed. The fast mode reports completed pages.

The file percentage is an estimate, not a precise measurement. It uses timings from earlier conversions on the same machine, never moves backwards, and stays below 100% until the file is published. When a result is available, you can preview its PDF and Markdown, open the output folder, or export the document with its figures. The desktop version is visible next to the SAMI name and in Settings, where you can also choose English or Spanish and light or dark appearance.

The desktop distribution targets native Windows with a per-user installer and Linux with an AppImage and `.deb` package. Setup prepares or reuses the matching CLI automatically.

With the desktop release available, the quick installers below prepare the CLI and install the desktop app. Windows adds SAMI to **Installed apps**, **Start**, and the desktop. Linux adds SAMI to the application menu.

On Arch Linux, install the `openssl-3` runtime package if your system has OpenSSL 4 only. The llama.cpp runtime used by SAMI links against OpenSSL 3.

To run the desktop app from a development checkout, first prepare the installed CLI with `sami setup`, then use Node.js 24 and npm.

```bash
cd ui
npm ci
npm start
```

`npm test` runs the desktop module tests. `npm run build` followed by `npm run test:desktop` runs the graphical workflow tests from a graphical session. On Linux CI, run the desktop tests under Xvfb.

## Quick Install

```bash
curl -fsSL https://github.com/dramirezbe/sami-pdf2md-tool/releases/latest/download/install.sh | bash
```

This installs `uv` if needed, registers the CLI, and prepares the local models. To install only the CLI, pass `--component cli` after `bash -s --`. When the NVIDIA driver and available VRAM support it, SAMI downloads and verifies the CUDA build of `llama-server` and its matching runtime libraries.

### Windows PowerShell

Install from PowerShell 5.1 or later:

```powershell
irm https://github.com/dramirezbe/sami-pdf2md-tool/releases/latest/download/install.ps1 | iex
```

Verify the installation and convert a PDF:

```powershell
sami --version
sami setup
sami paper.pdf --mode balanced
```

For CLI-only installation, run the downloaded `install.ps1` with `-Component cli`. On x64 with an NVIDIA driver that supports CUDA 13.2 or later, the installer downloads the PyTorch CUDA wheel directly from PyTorch and verifies its SHA-256. To install a local wheel, run `install.ps1` with `-Source` followed by the wheel path.

The graphical installer shows installation details and writes a log to `%LOCALAPPDATA%\SAMI\installer.log`. If installation fails, share the relevant error from that log when requesting support. Each installer run replaces the previous log.

### Upgrade SAMI

```shell
sami upgrade
```

The command runs the installer from the latest release and updates the CLI and the desktop app together. It updates SAMI in its existing Python environment and reuses compatible dependencies, including PyTorch. Model caches stay in place. On Windows, wait for the installer to report completion before starting another SAMI command.

### Other install methods

<details>
<summary>uv (manual)</summary>

Download the wheel from the [latest release](https://github.com/dramirezbe/sami-pdf2md-tool/releases/latest), then run:

```bash
uv tool install --python 3.12 ./sami_pdf2md_tool-<version>-py3-none-any.whl
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
sami paper.pdf -o out/             # -> out/paper/paper.md + figures
sami a.pdf b.pdf                   # batch convert
sami convert a.pdf reports/ --recursive -o out/
sami paper.pdf --mode fast         # faster, lower quality
sami paper.pdf --device cpu        # keep the selected mode on CPU
sami paper.pdf --no-strip-refs     # compatibility option; references are preserved
sami paper.pdf --flat              # no subfolder, output beside the PDF
sami paper.pdf -q                  # quiet mode
```

Folder inputs include their direct PDFs by default. Use `--recursive` to include subfolders. The batch deduplicates inputs and reports invalid selections while continuing with the valid PDFs.

Repeated conversions get numbered names such as `paper_2.md`. With `--flat`, a document's figures are published under its own `<name>_assets/` directory.

The CLI reports conversion stages and live model progress when available. For integrations, `job_progress` events carry the estimated file percentage and can include page or block counts and model activity. If model progress details are unavailable, conversion continues without them.

## Conversion Modes

| Mode | Flag | Layout Engine | Best for |
|------|------|--------------|----------|
| fast | `--mode fast` | PyMuPDF and pdfplumber on CPU | Speed |
| balanced | `--mode balanced` *(default)* | RF-DETR on CUDA when available, with llama.cpp for OCR as needed | General use |
| quality | `--mode quality` | llama.cpp VLM with GPU offload according to free VRAM | Layout quality |

At model load, llama.cpp fits VLM layers to the free VRAM and the memory required for the current model and context. When an accelerator fails during conversion, SAMI retries the current document once on CPU with the same mode and continues the batch on CPU. Set `LLAMA_CPP_NGL` to an explicit layer count, or set it to `0` to run the VLM on CPU.

## Installation status and desktop integration

```shell
sami health --json
sami setup
sami doctor --json
sami convert reports/ --recursive --json --control-stdin
```

Read the absolute `executable` path and `installation_id` from `installation.json` in SAMI home. Launch the executable directly and check `health --json` for the CLI version, protocol version, matching installation ID, and per-mode status. Health reads local metadata and cached assets. `setup` downloads missing runtime files and verifies the CPU path for every mode, and it checks GPU acceleration when available. `doctor` includes the installation record and the last compatibility report. Run setup again after upgrading to refresh the validation for that version.

Conversion writes UTF-8 JSON Lines to stdout and human-readable progress to stderr. Read `run_started` for the run ID and `inputs_resolved` for the ordered input list and any selection issues. Use `job_finished.data.result` for terminal status and published output paths. During a retry, `job_retrying` carries the same job ID with the next attempt number. `run_finished` reports the totals and exit code.

To cancel from a controller, send a newline-terminated command through the CLI's stdin pipe using the active run ID. Use Ctrl+C in an interactive terminal.

```json
{"protocol_version":1,"command":"cancel","run_id":"<active run ID>"}
```

Cancellation reports terminal results for the active and queued jobs. Previously published results remain available.

## Exit codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | A PDF failed, has partial output, or a mixed batch had invalid inputs |
| 2 | Usage error or no valid PDF input |
| 3 | `health` or `doctor` found an installation that requires repair |
| 130 | Conversion cancelled |

## App home (`~/.sami/`)

sami creates `~/.sami/` on first run:

```
~/.sami/
  bin/cpu/                    # CPU llama.cpp runtime
  bin/cuda/                   # CUDA llama.cpp runtime, when available
  config/defaults.yaml        # default CLI flags
  installation.json           # installation ID and absolute CLI launcher path
  compatibility.json          # results from the latest setup validation
  cache/huggingface/          # downloaded models (surya-ocr, etc.)
  cache/torch/                # torch hub cache
  cache/progress.json         # local timing estimates for file progress
  logs/
```

Override with `SAMI_HOME` environment variable.

## Development and releases

The CLI and desktop app share a release version. To prepare a release, update the root `VERSION` file and run `python3 scripts/sync_version.py --sync` (on Windows, `python scripts/sync_version.py --sync`). Review and commit the synchronized metadata along with `VERSION`.

After validating and merging the candidate into `main`, run `python3 scripts/tag_release.py` on the release commit. It checks that the working tree is clean and the metadata is synchronized before creating an annotated tag. The Git tag starts the release workflow, which checks that it matches `VERSION`, builds the artifacts, and creates a draft release. See [the release guide](docs/releasing.md) for validation and publishing details.

## Uninstall

To remove only the desktop app, use **Installed apps** in Windows or run `bash install.sh --uninstall-ui` with the downloaded installer on Linux. This keeps the CLI and your results.

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
- Linux, macOS, or Windows PowerShell 5.1+
