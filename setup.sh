#!/usr/bin/env bash
# sami — Smart Automated Markdown Interpreter
# Installer: provisions a micromamba env with the correct PyTorch variant,
# installs sami as a console script, and injects PATH into the user's shell.
#
# Usage:
#   bash setup.sh install [--cpu|--cuda]
#   bash setup.sh uninstall

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_HOME="${SAMI_HOME:-$HOME/.sami}"
MAMBA_ROOT="$APP_HOME/.micromamba"
ENV_NAME="sami"
SENTINEL_BEGIN="# >>> sami >>>"
SENTINEL_END="# <<< sami <<<"

MICROMAMBA_URL="https://github.com/mamba-org/micromamba-releases/releases/latest/download/micromamba-"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

info()  { echo "[sami] $*"; }
error() { echo "[sami] ERROR: $*" >&2; }

detect_platform_asset() {
    local system machine
    system="$(uname -s)"
    machine="$(uname -m)"

    case "$system" in
        Linux)
            case "$machine" in
                aarch64|arm64) echo "linux-aarch64" ;;
                *)             echo "linux-64" ;;
            esac ;;
        Darwin)
            case "$machine" in
                arm64) echo "osx-arm64" ;;
                *)     echo "osx-64" ;;
            esac ;;
        *)
            error "Unsupported platform: $system $machine"
            exit 2 ;;
    esac
}

detect_cuda() {
    if command -v nvidia-smi &>/dev/null; then
        if nvidia-smi -L &>/dev/null; then
            return 0
        fi
    fi
    return 1
}

detect_shell_rc() {
    local shell_name
    shell_name="$(basename "${SHELL:-}")"

    case "$shell_name" in
        zsh)  echo "$HOME/.zshrc" ;;
        bash)
            if [[ "$(uname -s)" == "Darwin" ]] && [[ -f "$HOME/.bash_profile" ]]; then
                echo "$HOME/.bash_profile"
            else
                echo "$HOME/.bashrc"
            fi ;;
        fish) echo "$HOME/.config/fish/config.fish" ;;
        *)    echo "" ;;
    esac
}

find_micromamba() {
    # Check PATH first
    local on_path
    on_path="$(command -v micromamba 2>/dev/null || true)"
    if [[ -n "$on_path" ]]; then
        echo "$on_path"
        return 0
    fi

    # Check app-local
    local local_bin="$MAMBA_ROOT/bin/micromamba"
    if [[ -f "$local_bin" ]]; then
        echo "$local_bin"
        return 0
    fi

    # Check common locations
    for candidate in "$HOME/micromamba/bin/micromamba" "$HOME/.local/bin/micromamba"; do
        if [[ -f "$candidate" ]]; then
            echo "$candidate"
            return 0
        fi
    done

    return 1
}

bootstrap_micromamba() {
    local target="$MAMBA_ROOT/bin/micromamba"

    if [[ -f "$target" ]]; then
        echo "$target"
        return 0
    fi

    mkdir -p "$(dirname "$target")"
    local asset
    asset="$(detect_platform_asset)"
    local url="${MICROMAMBA_URL}${asset}"

    info "Downloading micromamba for $asset ..."
    curl -fsSL "$url" -o "$target"
    chmod +x "$target"
    info "micromamba ready at $target"
    echo "$target"
}

# ---------------------------------------------------------------------------
# Install
# ---------------------------------------------------------------------------

do_install() {
    local force_cpu=false
    local force_cuda=false

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --cpu)  force_cpu=true;  shift ;;
            --cuda) force_cuda=true; shift ;;
            *)      error "Unknown flag: $1"; exit 2 ;;
        esac
    done

    if $force_cpu && $force_cuda; then
        error "--cpu and --cuda are mutually exclusive"
        exit 2
    fi

    # 1. Create app home
    info "Creating app home: $APP_HOME"
    mkdir -p "$APP_HOME"/{config,cache,logs}

    # Write default config if not present
    if [[ ! -f "$APP_HOME/config/defaults.yaml" ]]; then
        cat > "$APP_HOME/config/defaults.yaml" <<'YAML'
# sami defaults (edit to taste)
mode: null        # auto | fast | balanced
strip_refs: true
quiet: false
YAML
        info "Wrote default config: $APP_HOME/config/defaults.yaml"
    fi

    # 2. Find or bootstrap micromamba
    local mamba
    if mamba="$(find_micromamba)"; then
        info "Using existing micromamba: $mamba"
    else
        mamba="$(bootstrap_micromamba)"
    fi

    # 3. Detect hardware
    local use_cuda=false
    if $force_cuda; then
        use_cuda=true
        info "CUDA forced by --cuda flag"
    elif $force_cpu; then
        use_cuda=false
        info "CPU forced by --cpu flag"
    elif detect_cuda; then
        use_cuda=true
        info "NVIDIA GPU detected, using CUDA PyTorch"
    else
        info "No NVIDIA GPU detected, using CPU PyTorch"
    fi

    # 4. Create conda environment
    export MAMBA_ROOT_PREFIX="$MAMBA_ROOT"

    local conda_pkgs="python>=3.11 pip psutil pyyaml llama.cpp"
    if $use_cuda; then
        conda_pkgs="$conda_pkgs pytorch-gpu torchvision"
    else
        conda_pkgs="$conda_pkgs pytorch-cpu torchvision"
    fi

    if "$mamba" env list 2>/dev/null | grep -q "$ENV_NAME"; then
        info "Environment '$ENV_NAME' already exists, updating..."
        # shellcheck disable=SC2086
        "$mamba" install -y -n "$ENV_NAME" -c conda-forge $conda_pkgs
    else
        info "Creating environment '$ENV_NAME' ..."
        # shellcheck disable=SC2086
        "$mamba" create -y -n "$ENV_NAME" -c conda-forge $conda_pkgs
    fi

    # 5. Install marker-pdf and sami via pip
    info "Installing marker-pdf and sami ..."
    "$mamba" run -n "$ENV_NAME" pip install marker-pdf==2.0.0
    "$mamba" run -n "$ENV_NAME" pip install -e "$SCRIPT_DIR"

    # 6. Verify the console script exists
    local sami_bin="$MAMBA_ROOT/envs/$ENV_NAME/bin/sami"
    if [[ ! -f "$sami_bin" ]]; then
        error "Console script not found at $sami_bin"
        error "pip install -e may have failed"
        exit 1
    fi
    info "sami installed at: $sami_bin"

    # 7. Inject PATH into shell rc
    local rc_file
    rc_file="$(detect_shell_rc)"

    if [[ -z "$rc_file" ]]; then
        info "Could not detect your shell. Add this to your shell config manually:"
        echo ""
        echo "  export PATH=\"$MAMBA_ROOT/envs/$ENV_NAME/bin:\$PATH\""
        echo "  export SAMI_HOME=\"$APP_HOME\""
        echo ""
    else
        # Remove old pdf2md aliases if present
        if grep -q "pdf2md-gcpds-rf\|alias pdf2md=" "$rc_file" 2>/dev/null; then
            info "Removing old pdf2md alias from $rc_file"
            sed -i.bak '/pdf2md-gcpds-rf\|alias pdf2md=/d' "$rc_file"
        fi

        # Check if sentinel already present
        if grep -qF "$SENTINEL_BEGIN" "$rc_file" 2>/dev/null; then
            info "PATH already configured in $rc_file (sentinel found)"
        else
            info "Adding PATH to $rc_file"

            local shell_name
            shell_name="$(basename "${SHELL:-}")"

            if [[ "$shell_name" == "fish" ]]; then
                cat >> "$rc_file" <<FISH
$SENTINEL_BEGIN
set -gx PATH "$MAMBA_ROOT/envs/$ENV_NAME/bin" \$PATH
set -gx SAMI_HOME "$APP_HOME"
$SENTINEL_END
FISH
            else
                cat >> "$rc_file" <<SHELL
$SENTINEL_BEGIN
export PATH="$MAMBA_ROOT/envs/$ENV_NAME/bin:\$PATH"
export SAMI_HOME="$APP_HOME"
$SENTINEL_END
SHELL
            fi

            info "Done. Run 'source $rc_file' or open a new terminal."
        fi
    fi

    echo ""
    info "Installation complete!"
    info "  App home:  $APP_HOME"
    info "  Env:       $MAMBA_ROOT/envs/$ENV_NAME"
    info "  Command:   sami --help"
    if $use_cuda; then
        info "  PyTorch:   CUDA (GPU-accelerated)"
    else
        info "  PyTorch:   CPU"
    fi
}

# ---------------------------------------------------------------------------
# Uninstall
# ---------------------------------------------------------------------------

do_uninstall() {
    info "Uninstalling sami ..."

    # Remove sentinel from shell rc
    local rc_file
    rc_file="$(detect_shell_rc)"

    if [[ -n "$rc_file" ]] && [[ -f "$rc_file" ]]; then
        if grep -qF "$SENTINEL_BEGIN" "$rc_file"; then
            info "Removing sami PATH from $rc_file"
            sed -i.bak "/$SENTINEL_BEGIN/,/$SENTINEL_END/d" "$rc_file"
        fi
    fi

    # Remove micromamba env
    if [[ -d "$MAMBA_ROOT/envs/$ENV_NAME" ]]; then
        info "Removing environment: $MAMBA_ROOT/envs/$ENV_NAME"
        rm -rf "$MAMBA_ROOT/envs/$ENV_NAME"
    fi

    # Ask before removing app home (has user config + cached models)
    if [[ -d "$APP_HOME" ]]; then
        echo ""
        read -rp "[sami] Remove $APP_HOME (config + cached models)? [y/N] " answer
        if [[ "$answer" =~ ^[Yy] ]]; then
            rm -rf "$APP_HOME"
            info "Removed $APP_HOME"
        else
            info "Kept $APP_HOME"
        fi
    fi

    info "Uninstall complete."
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

case "${1:-}" in
    install)   shift; do_install "$@" ;;
    uninstall) do_uninstall ;;
    *)
        echo "Usage: bash setup.sh install [--cpu|--cuda]"
        echo "       bash setup.sh uninstall"
        exit 2 ;;
esac
