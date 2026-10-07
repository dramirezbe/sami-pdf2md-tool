# sami — Smart Automated Markdown Interpreter

Standalone PDF-to-Markdown converter using Marker. Opensource tool.

## Environment

- Package name: `sami-pdf2md-tool`
- CLI command: `sami`
- Python package: `sami/`
- App home: `~/.sami/` (config, cache, logs)
- Core dep: `marker-pdf==2.0.0` (local, keyless, no API needed)

## Install

```bash
# Recommended (handles CUDA/CPU):
bash setup.sh install

# Alternative (CPU-only, quick):
uv tool install -e .
```

## Usage

```
sami paper.pdf                     # -> paper/paper.md + figures
sami paper.pdf -o out/             # -> out/paper.md + figures
sami a.pdf b.pdf                   # batch convert
sami paper.pdf --mode fast         # faster, lower quality
sami paper.pdf --no-strip-refs     # keep the references section
sami paper.pdf --flat              # no subfolder, output beside the PDF
sami paper.pdf -q                  # quiet mode
```

## Origin

Extracted and decoupled from papersmith-ai's paper-ingestion skill (2026-10-07).
Original code: `~/papersmith-ai/skills/paper-ingestion/scripts/extract_pdf.py`
