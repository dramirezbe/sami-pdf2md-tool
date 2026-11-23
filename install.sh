#!/usr/bin/env bash
# sami — one-line installer & updater
# Install: curl -fsSL https://raw.githubusercontent.com/dramirezbe/sami-pdf2md-tool/main/install.sh | bash
# Update:  curl -fsSL https://raw.githubusercontent.com/dramirezbe/sami-pdf2md-tool/main/install.sh | bash -s update
#
# sami is fully local and keyless. All three modes (fast/balanced/quality)
# run without Docker or API keys:
#   - fast:             CPU only.
#   - balanced (default): RF-DETR via Torch, CUDA if available else CPU.
#   - quality (VLM):    llama.cpp (GGUF); GPU offload scaled by VRAM, CPU otherwise.
# llama-server and OCR models are auto-provisioned on first run.
set -euo pipefail

REPO="git+https://github.com/dramirezbe/sami-pdf2md-tool.git"

info() { echo "[sami] $*"; }
error() { echo "[sami] ERROR: $*" >&2; exit 1; }

ACTION="${1:-install}"

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

# 3. Install or update sami (rewrites the global tool environment)
if [[ "$ACTION" == "update" ]]; then
    info "Updating sami..."
    uv tool install --python 3.12 --force --upgrade "$REPO"
else
    info "Installing sami..."
    uv tool install --python 3.12 "$REPO"
fi

# 4. Verify
if command -v sami &>/dev/null; then
    info "Done! Run: sami paper.pdf"
    info "On first run, llama-server and OCR models are downloaded automatically."
    info "Check readiness anytime with: sami health"
else
    # uv puts it in ~/.local/bin which might not be in PATH yet
    info "Done! Add ~/.local/bin to your PATH, then run: sami paper.pdf"
    info "  export PATH=\"\$HOME/.local/bin:\$PATH\""
fi
