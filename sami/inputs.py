"""Ordered PDF discovery for the terminal and graphical clients."""
from __future__ import annotations

import os
from pathlib import Path


def discover_inputs(raw_paths: list[str], *, recursive: bool) -> tuple[list[Path], list[dict]]:
    pdfs: list[Path] = []
    issues: list[dict] = []
    identities: set[object] = set()

    def issue(path, code: str, message: str) -> None:
        issues.append({"path": str(path), "code": code, "message": message})

    def add_pdf(path: Path) -> None:
        try:
            resolved = path.resolve(strict=True)
            stat = resolved.stat()
            if not resolved.is_file():
                issue(path, "INPUT_NOT_PDF", "Expected a PDF file.")
                return
        except (OSError, RuntimeError) as exc:
            issue(path, "INPUT_UNREADABLE", str(exc))
            return
        identity = (stat.st_dev, stat.st_ino) if stat.st_ino else resolved
        if identity not in identities:
            identities.add(identity)
            pdfs.append(resolved)

    def walk_error(exc: OSError) -> None:
        issue(exc.filename, "INPUT_DIRECTORY_UNREADABLE", str(exc))

    for raw in raw_paths:
        try:
            path = Path(raw).expanduser().absolute()
            if path.is_dir():
                saw_pdf = False
                for folder, dirs, names in os.walk(path, followlinks=False, onerror=walk_error):
                    directory = Path(folder)
                    dirs[:] = sorted(d for d in dirs if not (directory / d).is_symlink()
                                     and not (d.startswith(".") and "-sami-" in d))
                    for name in sorted(names):
                        if Path(name).suffix.lower() == ".pdf":
                            saw_pdf = True
                            add_pdf(directory / name)
                    if not recursive:
                        break
                if not saw_pdf:
                    issue(path, "INPUT_DIRECTORY_EMPTY", "No PDF files found in this directory.")
            elif not path.exists():
                issue(path, "INPUT_NOT_FOUND", "Input does not exist.")
            elif path.suffix.lower() != ".pdf":
                issue(path, "INPUT_NOT_PDF", "Expected a PDF file.")
            else:
                add_pdf(path)
        except (OSError, ValueError, RuntimeError) as exc:
            issue(raw, "INPUT_UNREADABLE", str(exc))

    return pdfs, issues
