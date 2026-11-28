#!/usr/bin/env python3
"""Synchronize repository version metadata and validate a proposed Git tag."""
import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def version():
    value = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    if not re.fullmatch(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)", value):
        raise ValueError("VERSION must contain a stable version such as 0.4.2")
    return value


def sync(v):
    for name in ("ui/package.json", "ui/package-lock.json"):
        path = ROOT / name
        data = json.loads(path.read_text(encoding="utf-8"))
        data["version"] = v
        if "packages" in data:
            data["packages"][""]["version"] = v
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    path = ROOT / "packaging/runtime-manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    changed = manifest["cli"]["version"] != v
    checksum = "0" * 64 if changed else manifest["cli"]["sha256"]
    manifest["cli"]["sha256"] = checksum
    manifest["sami_version"] = manifest["cli"]["version"] = manifest["ui"]["version"] = v
    manifest["cli"]["wheel"] = f"sami_pdf2md_tool-{v}-py3-none-any.whl"
    manifest["cli"]["url"] = f"https://github.com/dramirezbe/sami-pdf2md-tool/releases/download/v{v}/{manifest['cli']['wheel']}"
    manifest["ui"]["release_tag"] = f"v{v}"
    for platform in ("windows_x64", "linux_x64"):
        for key, value in manifest["ui"][platform].items():
            manifest["ui"][platform][key] = re.sub(r"(?<=SAMI-)\d+\.\d+\.\d+|(?<=/v)\d+\.\d+\.\d+", v, value)
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    for name, patterns in {
        "packaging/linux/cli-install.sh": {
            r"^CLI_VERSION=.*$": f"CLI_VERSION={v}",
            r"^UI_VERSION=.*$": f"UI_VERSION={v}",
            r"^CLI_WHEEL=.*$": f"CLI_WHEEL=sami_pdf2md_tool-{v}-py3-none-any.whl",
            r"^CLI_SHA256=.*$": f"CLI_SHA256={checksum}",
        },
        "packaging/windows/cli-install.ps1": {
            r"^\$cliVersion = .*$": f"$cliVersion = '{v}'",
            r"^\$wheelName = .*$": f"$wheelName = 'sami_pdf2md_tool-{v}-py3-none-any.whl'",
            r"^\$wheelSha256 = .*$": f"$wheelSha256 = '{checksum}'",
        },
    }.items():
        path = ROOT / name
        content = path.read_text(encoding="utf-8")
        for pattern, replacement in patterns.items():
            content, count = re.subn(pattern, lambda _: replacement, content, flags=re.MULTILINE)
            if count != 1:
                raise ValueError(f"Expected one match for {pattern} in {name}, found {count}")
        path.write_text(content, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", help="Validate a proposed release tag against VERSION")
    parser.add_argument("--sync", action="store_true", help="Update derived repository metadata")
    args = parser.parse_args()
    v = version()
    if args.tag and args.tag != f"v{v}":
        parser.error(f"tag {args.tag!r} does not match VERSION ({v}); update VERSION before tagging")
    if args.sync:
        sync(v)
    print(v)


if __name__ == "__main__":
    main()
