#!/usr/bin/env python3
"""Create an annotated release tag after validating committed version metadata."""
import subprocess
import sys

from sync_version import sync, version


def git(*args):
    return subprocess.run(["git", *args], check=True, text=True, capture_output=True).stdout.strip()


def main():
    if git("status", "--porcelain"):
        sys.exit("Commit or stash all changes before creating a release tag.")
    v = version()
    sync(v)
    if git("status", "--porcelain"):
        sys.exit("Version metadata was out of date. Review and commit the synchronized files before tagging.")
    tag = f"v{v}"
    if git("tag", "--list", tag):
        sys.exit(f"Tag {tag} already exists.")
    subprocess.run(["git", "tag", "-a", tag, "-m", f"SAMI {v}"], check=True)
    print(f"Created {tag}. Push it with: git push origin {tag}")


if __name__ == "__main__":
    main()
