"""Numbered, anti-collision output publication for sami.

Policy (plan 01 U02):
- paper.pdf → paper/paper.md (non-flat) or paper.md (flat)
- Same PDF converted again → paper_2/paper_2.md, paper_3/…
- Two PDFs with the same stem → distinct names deterministically
- Published outputs carry a YAML front-matter block with the absolute
  source path so future runs can tell which file owns which output.
- The staging directory is on the output filesystem. A directory result
  is renamed as a unit. Flat resources are published before the Markdown.

Front-matter is minimal YAML written without the pyyaml import
so the module loads fast (the import of yaml would pull in marker's
startup chain on Windows).
"""
from __future__ import annotations

from contextlib import contextmanager
import os
import re
import shutil
import tempfile
from pathlib import Path
from urllib.parse import quote


# ---------------------------------------------------------------------------
# Front-matter helpers
# ---------------------------------------------------------------------------

_FM_SEP = "---\n"
_SOURCE_KEY = "source"
_VERSION_KEY = "sami_version"


def prepend_frontmatter(markdown: str, *, source: Path, version: str = "") -> str:
    """Return markdown with a minimal YAML front-matter block prepended.

    The block contains only ``source`` (absolute path) and optionally
    ``sami_version``.  It is written without pyyaml to keep this module
    import-light.
    """
    # Normalise source to forward slashes so the path is readable on
    # Windows regardless of which separator the OS prefers.
    src_str = source.resolve().as_posix()
    lines = [_FM_SEP, f"{_SOURCE_KEY}: {src_str}\n"]
    if version:
        lines.append(f"{_VERSION_KEY}: {version}\n")
    lines.append(_FM_SEP)
    return "".join(lines) + markdown


def read_sami_source(md_path: Path) -> str | None:
    """Return the ``source`` field from the front-matter of *md_path*, or None.

    Reads only the first 4 KiB of the file to stay fast.  Returns None if
    the file has no sami front-matter or if reading fails.
    """
    try:
        with md_path.open(encoding="utf-8", errors="replace") as fh:
            head = fh.read(4096)
    except OSError:
        return None

    if not head.startswith(_FM_SEP):
        return None

    end = head.find(_FM_SEP, len(_FM_SEP))
    if end == -1:
        return None

    fm = head[len(_FM_SEP):end]
    for line in fm.splitlines():
        if line.startswith(f"{_SOURCE_KEY}:"):
            value = line[len(f"{_SOURCE_KEY}:"):].strip()
            return value if value else None
    return None


# ---------------------------------------------------------------------------
# Stem reservation
# ---------------------------------------------------------------------------

def _destinations(output_dir: Path, stem: str, flat: bool) -> tuple[Path, ...]:
    if flat:
        return output_dir / f"{stem}.md", output_dir / f"{stem}_assets"
    return (output_dir / stem,)


def _occupied(path: Path) -> bool:
    return path.exists() or path.is_symlink()


def reserve_stem(
    src: Path,
    output_dir: Path,
    flat: bool,
    *,
    claimed: set[str] | None = None,
) -> str:
    """Return the next available output stem for *src* in *output_dir*.

    Try the original stem and then numbered stems, preserving all prior
    outputs. Use `claim_stem` to hold the reservation across processes.

    Args:
        src:      absolute path of the source PDF.
        output_dir: directory where outputs will be written.
        flat:     True → flat output (no subdirectory per PDF).
        claimed:  mutable set shared across a batch run; modified in place.

    Returns:
        A stem string (e.g. ``"paper"`` or ``"paper_2"``).
    """
    if claimed is None:
        claimed = set()

    base = src.stem
    stem = base
    n = 1
    while (
        stem in claimed
        or _occupied(output_dir / f".{stem}-sami-claim")
        or any(_occupied(path) for path in _destinations(output_dir, stem, flat))
    ):
        n += 1
        stem = f"{base}_{n}"

    claimed.add(stem)
    return stem


@contextmanager
def claim_stem(src: Path, output_dir: Path, flat: bool):
    """Hold a cross-process claim until the caller finishes publishing."""
    while True:
        stem = reserve_stem(src, output_dir, flat)
        claim = output_dir / f".{stem}-sami-claim"
        try:
            claim.touch(exist_ok=False)
        except FileExistsError:
            continue
        try:
            if not any(_occupied(path) for path in _destinations(output_dir, stem, flat)):
                yield stem
                return
        finally:
            claim.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Atomic publication
# ---------------------------------------------------------------------------

def publish(
    staging_dir: Path,
    stem: str,
    output_dir: Path,
    flat: bool,
) -> dict[str, Path | list[Path]]:
    """Move files from *staging_dir* to their final destinations atomically.

    The staging directory must be on the same filesystem as the output.

    Returns:
        ``{"md_path": Path, "resource_paths": list[Path]}``

    Raises:
        FileNotFoundError: if no .md file is found in staging_dir.
        OSError: on filesystem errors during publication.
    """
    md_name = f"{stem}.md"
    staged_md = staging_dir / md_name

    if not staged_md.exists():
        # Fallback: accept any single .md in staging
        md_files = list(staging_dir.glob("*.md"))
        if not md_files:
            raise FileNotFoundError(f"No .md file found in staging dir: {staging_dir}")
        staged_md = md_files[0]
        md_name = staged_md.name

    # Collect resource files (everything except the .md)
    resources = sorted(
        p for p in staging_dir.rglob("*") if p.is_file() and p != staged_md
    )

    relative = [file.relative_to(staging_dir) for file in resources]
    if not flat:
        dest, = _destinations(output_dir, stem, flat)
        if _occupied(dest):
            raise FileExistsError(f"Output directory already exists: {dest}")
        staging_dir.rename(dest)
        return {"md_path": dest / md_name, "resource_paths": [dest / path for path in relative]}

    dest_md, namespace = _destinations(output_dir, stem, flat)
    if staged_md.name != dest_md.name:
        dest_md = output_dir / staged_md.name
    if _occupied(dest_md):
        raise FileExistsError(f"Markdown already exists: {dest_md}")
    if resources:
        markdown = staged_md.read_text(encoding="utf-8")
        targets = {}
        prefix = quote(namespace.name, safe="")
        for path in relative:
            raw = path.as_posix()
            escaped = quote(raw, safe="/")
            targets[raw] = targets[escaped] = f"{prefix}/{escaped}"
        names = "|".join(re.escape(name) for name in sorted(targets, key=len, reverse=True))
        markdown = re.sub(
            r"(\]\(<?)(" + names + r")(?=>?\)|\s+[\"'])",
            lambda match: match[1] + targets[match[2]],
            markdown,
        )
        staged_md.write_text(markdown, encoding="utf-8")
        namespace.mkdir()
    try:
        for file, path in zip(resources, relative):
            destination = namespace / path
            destination.parent.mkdir(parents=True, exist_ok=True)
            file.rename(destination)
        # Link atomically without replacing Markdown created after the reservation.
        os.link(staged_md, dest_md)
    except BaseException:
        if resources:
            shutil.rmtree(namespace, ignore_errors=True)
        raise
    return {"md_path": dest_md, "resource_paths": [namespace / path for path in relative]}


# ---------------------------------------------------------------------------
# Staged writing helper
# ---------------------------------------------------------------------------

def make_staging_dir(output_dir: Path, stem: str) -> Path:
    """Create and return a temporary staging directory on the same filesystem.

    The directory has a hidden dot-prefix so it is not mistaken for a valid
    sami output.  It is the caller's responsibility to remove it (success or
    failure) with ``shutil.rmtree(staging, ignore_errors=True)``.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix=f".{stem}-sami-", dir=output_dir))
