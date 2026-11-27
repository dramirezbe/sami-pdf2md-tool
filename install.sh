#!/usr/bin/env bash
# SAMI_UPGRADE_V1
set -euo pipefail

REPOSITORY=dramirezbe/sami-pdf2md-tool
ACTION="${1:-install}"

# CLIs up to 0.3.7 run `upgrade <python> <git source> <index>`. They now get the
# latest release too, so only the package index is still honored.
if [[ "$ACTION" == "upgrade" ]]; then
    export SAMI_UPGRADE_INDEX="${4:-}"
    set -- update
    ACTION=update
fi

component=all
if [[ ( "$ACTION" == "install" || "$ACTION" == "update" ) && $# -gt 0 ]]; then
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

# The latest release publishes this helper with its versions and checksum stamped in.
# The copy under packaging/ is only the template, so it is never used here.
helper="$(mktemp "${TMPDIR:-/tmp}/sami-cli-install.XXXXXX")"
trap 'rm -f "$helper"' EXIT
echo '[sami] Fetching the installation steps from the latest release...'
curl -fsSL --connect-timeout 15 --max-time 60 \
    "https://github.com/$REPOSITORY/releases/latest/download/cli-install-linux.sh" -o "$helper"

bash "$helper" --component "$component"
