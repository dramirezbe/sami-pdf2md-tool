#!/usr/bin/env bash
set -euo pipefail

CLI_VERSION=0.4.4
CLI_WHEEL=sami_pdf2md_tool-0.4.4-py3-none-any.whl
CLI_SHA256=0000000000000000000000000000000000000000000000000000000000000000
UI_VERSION=0.4.4
REPOSITORY=dramirezbe/sami-pdf2md-tool
APP_ID=com.dramirezbe.sami.desktop
ICON_NAME=com.dramirezbe.sami
sami_home="${SAMI_HOME:-$HOME/.sami}"
data_dir="${XDG_DATA_HOME:-$HOME/.local/share}"

info() { printf '[SAMI] %s\n' "$*" >&2; }
fail() { printf '[SAMI] ERROR: %s\n' "$*" >&2; exit 1; }

find_uv() {
    if command -v uv >/dev/null 2>&1; then command -v uv; return; fi
    local install_dir="${UV_INSTALL_DIR:-${XDG_BIN_HOME:-$HOME/.local/bin}}"
    local candidate="$install_dir/uv"
    if [[ -x "$candidate" ]]; then printf '%s\n' "$candidate"; return; fi
    info 'Installing uv and its managed Python runtime...'
    curl -LsSf --connect-timeout 15 --max-time 120 https://astral.sh/uv/install.sh | UV_INSTALL_DIR="$install_dir" sh >&2
    [[ -x "$candidate" ]] || fail 'Could not install uv.'
    printf '%s\n' "$candidate"
}

validate_cli() {
    local executable="$1" cli_python="$2"
    [[ -x "$executable" ]] || return 1
    "$executable" --version 2>/dev/null | grep -q "sami $CLI_VERSION$" || return 1
    "$executable" health --json >"$temporary_dir/health.json" 2>/dev/null || return 1
    "$cli_python" -c 'import json,sys
health=json.load(open(sys.argv[1], encoding="utf-8"))
assert health.get("cli_version") == sys.argv[2] and health.get("protocol_version") == 1
assert all(health["modes"][name]["available"] and health["modes"][name]["ready"] for name in ("fast","balanced","quality"))
' "$temporary_dir/health.json" "$CLI_VERSION" >/dev/null 2>&1
}

prepare_linux_runtime() {
    [[ "$(uname -s)" == Linux ]] || return 0
    "$1" -I - <<'PY'
import ctypes
import importlib.util
from pathlib import Path

try:
    ctypes.CDLL("libssl.so.3")
except OSError:
    if Path("/etc/arch-release").exists():
        raise SystemExit("SAMI needs the OpenSSL 3 runtime. Run sudo pacman -S --needed openssl-3, then retry.")
    raise SystemExit("SAMI needs the OpenSSL 3 runtime (libssl.so.3). Install your distribution's OpenSSL 3 compatibility package, then retry.")

try:
    ctypes.CDLL("libgomp.so.1")
except OSError:
    pass
else:
    raise SystemExit(0)

from sami.diagnostics import app_home
from sami.llama_runtime import ensure_server

torch = importlib.util.find_spec("torch")
openmp = Path(torch.origin).parent / "lib" / "libgomp.so.1" if torch and torch.origin else None
if openmp is None or not openmp.is_file():
    raise SystemExit("SAMI needs the OpenMP runtime libgomp.so.1. Install libgomp1 on Debian/Ubuntu and retry.")

home = app_home()
server, _ = ensure_server(home, want_cuda=False, logger=print)
if server is None:
    raise SystemExit("Could not provision the local llama-server.")
for variant in ("cpu", "cuda"):
    folder = home / "bin" / variant
    if (folder / "llama-server").is_file():
        library = folder / "libgomp.so.1"
        if not library.exists() and not library.is_symlink():
            library.symlink_to(openmp)
PY
}

install_cli() {
    local uv executable tool_dir cli_python registration python_record parser_python registered_python registered_executable wheel actual_wheel_hash
    local -a install_args
    uv="$(find_uv)"
    tool_dir="$("$uv" tool dir)"
    executable="$("$uv" tool dir --bin)/sami"
    cli_python="$tool_dir/sami-pdf2md-tool/bin/python"
    registration="${SAMI_HOME:-$HOME/.sami}/installation.json"

    if command -v sami >/dev/null 2>&1; then executable="$(command -v sami)"; fi
    if [[ -f "$registration" ]]; then
        parser_python="$cli_python"
        [[ -x "$parser_python" ]] || parser_python="$(command -v python3 || command -v python || true)"
        if [[ -x "$parser_python" ]]; then
            python_record="$("$parser_python" -c 'import json,sys; r=json.load(open(sys.argv[1],encoding="utf-8")); print(r.get("python_executable", ""), r.get("executable", ""), sep="\t")' "$registration" 2>/dev/null || true)"
            IFS=$'\t' read -r registered_python registered_executable <<<"$python_record"
            [[ -x "${registered_python:-}" ]] && cli_python="$registered_python"
            [[ -x "${registered_executable:-}" ]] && executable="$registered_executable"
        fi
    fi

    if [[ -x "$executable" ]] && "$executable" --version 2>/dev/null | grep -q "sami $CLI_VERSION$"; then
        info "Checking SAMI CLI $CLI_VERSION..."
    else
        wheel="$temporary_dir/$CLI_WHEEL"
        info "Downloading SAMI CLI $CLI_VERSION..."
        curl -fsSL --connect-timeout 15 --max-time 300 "https://github.com/$REPOSITORY/releases/download/v$CLI_VERSION/$CLI_WHEEL" -o "$wheel"
        if command -v sha256sum >/dev/null 2>&1; then
            actual_wheel_hash="$(sha256sum "$wheel" | cut -d' ' -f1)"
        else
            actual_wheel_hash="$(shasum -a 256 "$wheel" | cut -d' ' -f1)"
        fi
        [[ "$actual_wheel_hash" == "$CLI_SHA256" ]] || fail 'SAMI CLI wheel checksum verification failed.'
        if [[ -x "$cli_python" ]]; then
            info 'Updating the registered SAMI environment...'
            install_args=(pip install --python "$cli_python" --upgrade-package sami-pdf2md-tool)
            [[ -z "${SAMI_UPGRADE_INDEX:-}" ]] || install_args+=(--index "$SAMI_UPGRADE_INDEX")
            "$uv" "${install_args[@]}" "$wheel"
            if [[ ! -x "$executable" ]]; then executable="$(dirname "$cli_python")/sami"; fi
        else
            info 'Installing SAMI CLI...'
            install_args=(tool install --python 3.12 --force)
            if [[ "$(uname -s)" == Linux ]] && "$uv" tool install --help | grep -F -- '--torch-backend' >/dev/null; then
                install_args+=(--torch-backend "${UV_TORCH_BACKEND:-auto}")
            fi
            "$uv" "${install_args[@]}" "$wheel"
            executable="$("$uv" tool dir --bin)/sami"
            cli_python="$("$uv" tool dir)/sami-pdf2md-tool/bin/python"
        fi
        [[ -x "$executable" && -x "$cli_python" ]] || fail 'SAMI CLI installation did not create its launcher.'
        "$cli_python" -I -m sami.cli setup --register-only --executable "$executable"
    fi

    if ! validate_cli "$executable" "$cli_python"; then
        prepare_linux_runtime "$cli_python"
        info 'Preparing local models and verifying the CPU modes...'
        "$executable" setup --json
    fi
    validate_cli "$executable" "$cli_python" || fail 'SAMI CLI is not ready. Run sami doctor for details.'
    info "SAMI CLI $CLI_VERSION is ready."
}

install_ui() {
    local release_dir asset asset_url checksum_url expected actual install_dir appimage staged icon_dir desktop_tmp status
    release_dir="https://github.com/$REPOSITORY/releases/download/v$UI_VERSION"
    case "$(uname -s)" in
        Linux)
            if [[ "$(uname -m)" != x86_64 && "$(uname -m)" != amd64 ]]; then
                if [[ "$component" == all ]]; then
                    info 'The SAMI CLI is ready. The SAMI desktop AppImage currently supports Linux x64 only.'
                    return
                fi
                fail 'The SAMI desktop AppImage currently supports Linux x64 only.'
            fi
            asset="SAMI-$UI_VERSION-linux-x64.AppImage"
            asset_url="$release_dir/$asset"
            checksum_url="$release_dir/SHA256SUMS"
            install_dir="$sami_home/bin"
            mkdir -p "$install_dir"
            appimage="$install_dir/SAMI.AppImage"
            info 'Downloading the SAMI desktop app...'
            status="$(curl -sSL --connect-timeout 15 --max-time 300 -w '%{http_code}' "$asset_url" -o "$temporary_dir/$asset" || true)"
            if [[ "$status" == 404 && "$component" == all ]]; then
                rm -f "$temporary_dir/$asset"
                info "SAMI CLI is ready. The SAMI $UI_VERSION desktop release is not published yet."
                return
            fi
            [[ "$status" == 200 ]] || fail "Could not download the SAMI desktop app (HTTP $status)."
            expected="$(curl -fsSL --connect-timeout 15 --max-time 60 "$checksum_url" | awk -v name="$asset" '$2 == name { print $1 }')"
            [[ "$expected" =~ ^[[:xdigit:]]{64}$ ]] || fail 'Could not find the AppImage checksum in the release.'
            actual="$(sha256sum "$temporary_dir/$asset" | cut -d' ' -f1)"
            [[ "$actual" == "$expected" ]] || fail 'AppImage checksum verification failed.'
            curl -fsSL --connect-timeout 15 --max-time 60 "$release_dir/sami-icon-512.png" -o "$temporary_dir/icon.png"
            staged="$install_dir/.SAMI.AppImage.$$"
            install -m 755 "$temporary_dir/$asset" "$staged"
            mv -f "$staged" "$appimage"
            icon_dir="$data_dir/icons/hicolor/512x512/apps"
            mkdir -p "$icon_dir" "$data_dir/applications"
            install -m 644 "$temporary_dir/icon.png" "$icon_dir/$ICON_NAME.png"
            desktop_tmp="$temporary_dir/$APP_ID"
            cat >"$desktop_tmp" <<EOF
[Desktop Entry]
Type=Application
Name=SAMI
Comment=Smart Automated Markdown Interpreter
Exec="$appimage" --appimage-extract-and-run
Icon=$ICON_NAME
Terminal=false
Categories=Office;
StartupWMClass=sami
EOF
            install -m 644 "$desktop_tmp" "$data_dir/applications/$APP_ID"
            info 'SAMI was added to your application menu.'
            ;;
        *)
            if [[ "$component" == all ]]; then
                info 'The SAMI CLI is ready. A desktop installer is not currently available on this platform.'
                return
            fi
            fail 'The SAMI desktop app installer supports Linux x64.'
            ;;
    esac
}

refresh_menu() {
    if command -v update-desktop-database >/dev/null 2>&1 && [[ -d "$data_dir/applications" ]]; then
        update-desktop-database "$data_dir/applications" >/dev/null 2>&1 || true
    fi
}

uninstall_ui() {
    rm -f "$sami_home/bin/SAMI.AppImage" "$data_dir/applications/$APP_ID" \
        "$data_dir/icons/hicolor/512x512/apps/$ICON_NAME.png"
    refresh_menu
    info 'Removed the SAMI desktop app and its menu entry.'
}

check_existing_cli() {
    local registration executable cli_python
    registration="${SAMI_HOME:-$HOME/.sami}/installation.json"
    [[ -f "$registration" ]] || fail "UI-only installation requires a healthy SAMI CLI $CLI_VERSION. Install or repair the CLI, then retry."
    executable="$(sed -n 's/.*"executable"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$registration" | head -n 1)"
    cli_python="$(sed -n 's/.*"python_executable"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$registration" | head -n 1)"
    validate_cli "$executable" "$cli_python" || fail "UI-only installation requires healthy SAMI CLI $CLI_VERSION with protocol v1 and all modes ready. Run sami setup, then retry."
    info "Found healthy SAMI CLI $CLI_VERSION."
}

temporary_dir="$(mktemp -d "${TMPDIR:-/tmp}/sami-installer.XXXXXX")"
trap 'rm -rf "$temporary_dir"' EXIT

component=all
while (($#)); do
    case "$1" in
        --component)
            (($# >= 2)) || fail 'Pass cli, ui, or all after --component.'
            component="$2"
            shift 2
            ;;
        install)
            shift
            ;;
        *)
            fail "Unknown installer option: $1"
            ;;
    esac
done
if [[ "$component" == uninstall-ui ]]; then uninstall_ui; exit 0; fi
[[ "$component" == cli || "$component" == ui || "$component" == all ]] || fail 'Use --component cli, --component ui, or --component all.'
if [[ "$component" == cli || "$component" == all ]]; then install_cli; fi
if [[ "$component" == ui ]]; then check_existing_cli; fi
if [[ "$component" == ui || "$component" == all ]]; then install_ui; refresh_menu; fi
