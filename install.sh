#!/usr/bin/env bash
# sami — one-line installer
# Usage: curl -fsSL https://raw.githubusercontent.com/dramirezbe/sami-pdf2md-tool/main/install.sh | bash
set -euo pipefail

info() { echo "[sami] $*"; }
error() { echo "[sami] ERROR: $*" >&2; exit 1; }

# 1. Check Python >= 3.11 exists
if ! command -v python3 &>/dev/null; then
    error "python3 not found. Install Python 3.11+ first."
fi

# 2. Ensure uv is available
if ! command -v uv &>/dev/null; then
    info "uv not found, installing..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
    if ! command -v uv &>/dev/null; then
        error "Failed to install uv. Install manually: https://docs.astral.sh/uv/"
    fi
    info "uv installed."
fi

# 3. Install sami
info "Installing sami..."
uv tool install --python 3.12 git+https://github.com/dramirezbe/sami-pdf2md-tool.git

# 4. Verify
if command -v sami &>/dev/null; then
    info "Done! Run: sami paper.pdf"
    info "On first run, llama-server and OCR models will be downloaded automatically."
else
    # uv puts it in ~/.local/bin which might not be in PATH yet
    info "Done! Add ~/.local/bin to your PATH, then run: sami paper.pdf"
    info "  export PATH=\"\$HOME/.local/bin:\$PATH\""
fi
