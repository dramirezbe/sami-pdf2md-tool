#!/usr/bin/env bash
# SAMI_UPGRADE_V1
set -euo pipefail

REPOSITORY=dramirezbe/sami-pdf2md-tool
ACTION="${1:-install}"

if [[ "$ACTION" == "upgrade" ]]; then
    python="${2:-}"
    source="${3:-}"
    index="${4:-}"
    [[ -n "$python" && -n "$source" ]] || { echo '[sami] ERROR: Run sami upgrade from the installed CLI.' >&2; exit 1; }
    args=(pip install --python "$python" --upgrade-package sami-pdf2md-tool)
    [[ -z "$index" ]] || args+=(--index "$index")
    echo '[sami] Updating SAMI in its existing environment...'
    uv "${args[@]}" "$source"
    "$python" -I -m sami.cli setup --register-only
    echo '[sami] SAMI upgraded.'
    exit 0
fi

component=all
if [[ "$ACTION" == "update" ]]; then
    component=cli
    shift
elif [[ "$ACTION" == "install" && $# -gt 0 ]]; then
    shift
fi
while (($#)); do
    case "$1" in
        --component)
            (($# >= 2)) || { echo '[sami] ERROR: Pass cli, ui, or all after --component.' >&2; exit 2; }
            component="$2"
            shift 2
            ;;
        --uninstall-ui)
            component=uninstall-ui
            shift
            ;;
        *)
            echo "[sami] ERROR: Unknown installer option: $1" >&2
            exit 2
            ;;
    esac
done

helper=
if [[ -n "${BASH_SOURCE[0]:-}" ]]; then
    script_directory="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
    for candidate in "$script_directory/packaging/linux/cli-install.sh" "$script_directory/cli-install-linux.sh"; do
        if [[ -f "$candidate" ]]; then helper="$candidate"; break; fi
    done
fi
if [[ -z "$helper" ]]; then
    temporary_helper="$(mktemp "${TMPDIR:-/tmp}/sami-cli-install.XXXXXX")"
    trap 'rm -f "$temporary_helper"' EXIT
    helper_url="https://raw.githubusercontent.com/$REPOSITORY/main/packaging/linux/cli-install.sh"
    echo '[sami] Fetching the shared installation steps...'
    curl -fsSL --connect-timeout 15 --max-time 60 "$helper_url" -o "$temporary_helper"
    helper="$temporary_helper"
fi

bash "$helper" --component "$component"
