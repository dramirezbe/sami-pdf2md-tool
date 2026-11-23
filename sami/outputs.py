"""Numbered, anti-collision output publication for sami.

Policy (plan 01 U02):
- paper.pdf → paper/paper.md (non-flat) or paper.md (flat)
- Same PDF converted again → paper_2/paper_2.md, paper_3/…
- Two PDFs with the same stem → distinct names deterministically
- Published outputs carry a YAML front-matter block with the absolute
  source path so future runs can tell which file owns which output.
- Atomic publication: staging dir is on the same filesystem as the
  output directory; files are moved with os.replace so a partial write
  never leaves a corrupt output visible.

Win + Linux portable: uses pathlib, os.replace, and no POSIX-specific
APIs.  Front-matter is minimal YAML written without the pyyaml import
so the module loads fast (the import of yaml would pull in marker's
startup chain on Windows).
"""
from __future__ import annotations

import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Sequence


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

def _candidate_md_paths(output_dir: Path, stem: str, flat: bool) -> list[Path]:
    """Return the .md path(s) that would belong to *stem* in *output_dir*."""
    if flat:
        return [output_dir / f"{stem}.md"]
    return [output_dir / stem / f"{stem}.md"]


def _stem_is_available(
    stem: str,
    output_dir: Path,
    flat: bool,
    src: Path,
    *,
    claimed: set[str],
) -> bool:
    """True if *stem* can be used for a new output from *src*.

    A stem is available when:
    - It has not been claimed in this run (``claimed`` set).
    - No .md file already exists at that path, **or** every existing .md at
      that path was written by *src* (same absolute source path in front-matter).
    """
    if stem in claimed:
        return False

    for md_path in _candidate_md_paths(output_dir, stem, flat):
        if md_path.exists():
            existing_source = read_sami_source(md_path)
            src_posix = src.resolve().as_posix()
            if existing_source != src_posix:
                # Owned by another source or not a sami file → not available
                return False
    return True


def reserve_stem(
    src: Path,
    output_dir: Path,
    flat: bool,
    *,
    claimed: set[str] | None = None,
) -> str:
    """Return the next available output stem for *src* in *output_dir*.

    Tries ``src.stem``, then ``src.stem_2``, ``src.stem_3`` … until it
    finds one that is not claimed in this run and not owned by another
    source.  The returned stem is added to *claimed* so that a second call
    for a different PDF with the same stem in the same batch gets the next
    free number without reading the filesystem again.

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
    while not _stem_is_available(stem, output_dir, flat, src, claimed=claimed):
        n += 1
        stem = f"{base}_{n}"

    claimed.add(stem)
    return stem


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

    The staging directory must be on the same filesystem as *output_dir* so
    that ``os.replace`` is atomic.  Creates the destination directory if
    needed.

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

    if flat:
        dest_dir = output_dir
        dest_md = dest_dir / md_name
    else:
        dest_dir = output_dir / stem
        dest_md = dest_dir / md_name

    dest_dir.mkdir(parents=True, exist_ok=True)

    # Publish resources first (figures etc.) so the .md links are valid when
    # it appears.  If this fails mid-way, the .md hasn't been published yet
    # so no broken document is visible to the user.
    published_resources: list[Path] = []
    for res in resources:
        rel = res.relative_to(staging_dir)
        dest_res = dest_dir / rel
        dest_res.parent.mkdir(parents=True, exist_ok=True)
        os.replace(str(res), str(dest_res))
        published_resources.append(dest_res)

    # Publish the .md last — this is the visible commit point.
    os.replace(str(staged_md), str(dest_md))

    return {"md_path": dest_md, "resource_paths": published_resources}


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
