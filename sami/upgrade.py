"""Run the installer from the latest release to update the registered installation."""
from __future__ import annotations

import argparse
import json
import os
from importlib import metadata
import re
import shutil
import subprocess
import sys

_RELEASE = "https://github.com/dramirezbe/sami-pdf2md-tool/releases/latest/download"
_PACKAGE = "sami-pdf2md-tool"
_CURL_UPGRADE = """\
set -euo pipefail
installer=$(curl -fsSL --connect-timeout 15 --max-time 60 "$SAMI_UPGRADE_SCRIPT")
exec bash -s -- update <<< "$installer"
"""
_IRM_UPGRADE = """\
$ErrorActionPreference = 'Stop'
try {
    $installer = irm -Uri $env:SAMI_UPGRADE_SCRIPT -TimeoutSec 60
    foreach ($processId in ($env:SAMI_UPGRADE_WAIT_FOR -split ',')) {
        $running = Get-Process -Id $processId -ErrorAction SilentlyContinue
        if ($running) {
            Wait-Process -InputObject $running -Timeout 30
        }
    }
    & ([scriptblock]::Create($installer))
} catch {
    [Console]::Error.WriteLine("[sami] Upgrade failed. $($_.Exception.Message)")
    exit 1
}
"""


def _installation() -> dict:
    try:
        contents = metadata.distribution(_PACKAGE).read_text("direct_url.json")
        return json.loads(contents) if contents else {}
    except (metadata.PackageNotFoundError, ValueError):
        return {}


def _cuda_index() -> str:
    """Keep the current PyTorch channel available if a dependency needs updating."""
    try:
        variant = metadata.version("torch").partition("+")[2].split(".")[0]
    except metadata.PackageNotFoundError:
        return ""
    if re.fullmatch(r"cu[0-9]+", variant):
        return f"https://download.pytorch.org/whl/{variant}"
    return ""


def _windows_processes() -> str:
    """Wait for the Windows launcher as well as its Python process to release files."""
    import psutil

    current = psutil.Process()
    pids = [str(current.pid)]
    for parent in current.parents():
        try:
            if parent.name().casefold() != "sami.exe":
                break
            pids.append(str(parent.pid))
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            break
    return ",".join(pids)


def upgrade_command(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="sami upgrade",
        description="Update the SAMI CLI and desktop app to the latest release.",
    )
    parser.parse_args(argv)

    if _installation().get("dir_info", {}).get("editable"):
        parser.error("this is an editable SAMI installation. Update its Git checkout.")
    if sys.prefix == sys.base_prefix:
        parser.error("upgrade requires SAMI to be installed in a virtual environment, such as with uv tool install.")

    windows = os.name == "nt"
    required = ("uv", "powershell.exe") if windows else ("uv", "bash", "curl")
    for command in required:
        if shutil.which(command) is None:
            print(f"[sami] Upgrade requires {command} on PATH.", file=sys.stderr)
            return 1

    script_name = "install.ps1" if windows else "install.sh"
    env = dict(
        os.environ,
        SAMI_UPGRADE_SCRIPT=f"{_RELEASE}/{script_name}",
        SAMI_UPGRADE_INDEX=_cuda_index(),
    )
    try:
        if windows:
            env["SAMI_UPGRADE_WAIT_FOR"] = _windows_processes()
            subprocess.Popen(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", _IRM_UPGRADE],
                env=env, creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
            )
            print("[sami] Upgrade started. Wait for the installer result in this window.", flush=True)
            return 0
        return subprocess.run(["bash", "-c", _CURL_UPGRADE], env=env).returncode
    except OSError as exc:
        print(f"[sami] Could not start the upgrade. {exc}", file=sys.stderr)
        return 1
