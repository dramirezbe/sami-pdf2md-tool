#!/usr/bin/env bash
# sami — one-line installer & updater
# Install: curl -fsSL https://raw.githubusercontent.com/dramirezbe/sami-pdf2md-tool/main/install.sh | bash
# Update:  curl -fsSL https://raw.githubusercontent.com/dramirezbe/sami-pdf2md-tool/main/install.sh | bash -s update
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

# 3. Install or update sami
if [[ "$ACTION" == "update" ]]; then
    info "Updating sami..."
    uv tool install --python 3.12 --force --upgrade "$REPO"
else
    info "Installing sami..."
    uv tool install --python 3.12 "$REPO"
fi

# 4. GPU Docker support (NVIDIA Container Toolkit)
setup_gpu_docker() {
    # Marker's balanced/VLM mode needs Docker with --runtime nvidia.
    command -v nvidia-smi &>/dev/null && nvidia-smi -L &>/dev/null || return 0
    command -v docker &>/dev/null || return 0
    docker info 2>/dev/null | grep -q "nvidia" && return 0

    [[ "$(uname -s)" == "Linux" ]] || return 0

    info "NVIDIA GPU detected. Setting up Docker GPU support for --mode balanced..."

    if ! command -v sudo &>/dev/null; then
        info "  sudo not available. To enable GPU Docker support manually:"
        info "    https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html"
        return 0
    fi

    if [[ ! -f /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg ]]; then
        curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey \
            | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg 2>/dev/null || {
            info "  GPG key setup failed. GPU Docker support skipped (use --mode fast)."
            return 0
        }
    fi

    if [[ ! -f /etc/apt/sources.list.d/nvidia-container-toolkit.list ]]; then
        curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list \
            | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' \
            | sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list > /dev/null || {
            info "  Apt repo setup failed. GPU Docker support skipped (use --mode fast)."
            return 0
        }
    fi

    sudo apt-get update -qq -o Dir::Etc::sourcelist="sources.list.d/nvidia-container-toolkit.list" \
        -o Dir::Etc::sourceparts="-" -o APT::Get::List-Cleanup="0" 2>/dev/null || true
    sudo apt-get install -y -qq nvidia-container-toolkit || {
        info "  nvidia-container-toolkit install failed. GPU Docker support skipped (use --mode fast)."
        return 0
    }

    sudo nvidia-ctk runtime configure --runtime=docker > /dev/null 2>&1 || {
        info "  Docker runtime config failed. GPU Docker support skipped (use --mode fast)."
        return 0
    }

    sudo systemctl restart docker 2>/dev/null || sudo service docker restart 2>/dev/null || {
        info "  Could not restart Docker. Run manually: sudo systemctl restart docker"
        return 0
    }

    info "  NVIDIA Container Toolkit installed. --mode balanced (VLM) is ready."
}
setup_gpu_docker

# 5. Verify
if command -v sami &>/dev/null; then
    info "Done! Run: sami paper.pdf"
    info "On first run, llama-server and OCR models will be downloaded automatically."
else
    # uv puts it in ~/.local/bin which might not be in PATH yet
    info "Done! Add ~/.local/bin to your PATH, then run: sami paper.pdf"
    info "  export PATH=\"\$HOME/.local/bin:\$PATH\""
fi
