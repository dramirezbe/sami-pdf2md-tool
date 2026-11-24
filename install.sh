#!/usr/bin/env bash
# SAMI_UPGRADE_V1
# sami — one-line installer & updater
# Install: curl -fsSL https://raw.githubusercontent.com/dramirezbe/sami-pdf2md-tool/main/install.sh | bash
# Update:  curl -fsSL https://raw.githubusercontent.com/dramirezbe/sami-pdf2md-tool/main/install.sh | bash -s update
#
# sami is fully local and keyless. All three modes (fast/balanced/quality)
# run without Docker or API keys:
#   - fast:             CPU only.
#   - balanced (default): RF-DETR via Torch, with llama.cpp for OCR as needed.
#   - quality (VLM):    llama.cpp (GGUF); GPU offload scaled by VRAM, CPU otherwise.
# llama-server and OCR models are auto-provisioned on first run.
set -euo pipefail

REPO="git+https://github.com/dramirezbe/sami-pdf2md-tool.git"

info() { echo "[sami] $*"; }
error() { echo "[sami] ERROR: $*" >&2; exit 1; }

ACTION="${1:-install}"

if [[ "$ACTION" == "upgrade" ]]; then
    python="${2:-}"
    source="${3:-}"
    index="${4:-}"
    [[ -n "$python" && -n "$source" ]] || error "Run sami upgrade from the installed CLI."
    args=(pip install --python "$python" --upgrade-package sami-pdf2md-tool)
    if [[ -n "$index" ]]; then
        args+=(--index "$index")
    fi
    info "Updating SAMI in its existing environment..."
    uv "${args[@]}" "$source"
    "$python" -I -m sami.cli setup --register-only
    info "SAMI upgraded."
    exit 0
fi

# 1. Ensure uv is available. It provisions Python for the tool environment.
if ! command -v uv &>/dev/null; then
    info "uv not found, installing..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
    if ! command -v uv &>/dev/null; then
        error "Failed to install uv. Install manually: https://docs.astral.sh/uv/"
    fi
    info "uv installed."
fi

# 2. Install or update sami (rewrites the global tool environment)
if [[ "$ACTION" == "update" ]]; then
    info "Updating sami..."
    uv tool install --python 3.12 --force --upgrade "$REPO"
else
    info "Installing sami..."
    uv tool install --python 3.12 "$REPO"
fi

# Register the stable launcher for desktop clients.
sami_launcher="$(uv tool dir --bin)/sami"
"$sami_launcher" setup --register-only --executable "$sami_launcher"

# 3. Verify
if command -v sami &>/dev/null; then
    info "Done! Run sami setup to prepare and verify all modes."
    info "Check readiness anytime with: sami health"
else
    # uv puts it in ~/.local/bin which might not be in PATH yet
    info "Done! Add ~/.local/bin to your PATH, then run: sami paper.pdf"
    info "  export PATH=\"\$HOME/.local/bin:\$PATH\""
fi
