"""Temporary workaround for surrogate-pair loss in pdftext 0.7.1.

Remove once the pinned pdftext dependency preserves supplementary characters.
The wrapper repairs PageChars before pdftext groups characters into spans, and
installs itself in spawned extraction workers as well as the parent process.
"""
from __future__ import annotations

from contextlib import contextmanager
from importlib.metadata import version

_original_get_chars = None
_original_worker_init = None


def _get_chars(textpage, *args, **kwargs):
    import numpy as np
    import pypdfium2.raw as pdfium
    from pdftext.pdf.chars import PageChars

    chars = _original_get_chars(textpage, *args, **kwargs)
    candidates = np.flatnonzero(chars.codes == 0xFFFD)
    if not len(candidates):
        return chars

    # get_chars preserves a one-to-one mapping to PDFium indices at this point.
    # Inspect only replacements: ordinary text requires no extra PDFium calls.
    raw = {int(i): pdfium.FPDFText_GetUnicode(textpage.raw, int(chars.char_indices[i]))
           for i in candidates}
    keep = np.ones(len(chars), dtype=bool)
    codes = chars.codes.copy()
    boxes = chars.boxes.copy()
    changed = False
    for i, high in raw.items():
        low = raw.get(i + 1, 0)
        if (0xD800 <= high <= 0xDBFF and 0xDC00 <= low <= 0xDFFF
                and chars.char_indices[i + 1] == chars.char_indices[i] + 1):
            codes[i] = 0x10000 + ((high - 0xD800) << 10) + low - 0xDC00
            boxes[i, :2] = np.minimum(boxes[i, :2], boxes[i + 1, :2])
            boxes[i, 2:] = np.maximum(boxes[i, 2:], boxes[i + 1, 2:])
            keep[i + 1] = False
            changed = True
    if not changed:
        return chars
    codes = codes[keep]
    return PageChars("".join(map(chr, codes.tolist())), codes, chars.rotations[keep],
                     boxes[keep], chars.font_ids[keep], chars.fonts, chars.char_indices[keep])


def _install():
    global _original_get_chars
    import pdftext.pdf.pages as pages
    if pages.get_chars is not _get_chars:
        _original_get_chars = pages.get_chars
        pages.get_chars = _get_chars


def _worker_init(*args):
    # Windows uses spawn: patches made in the parent are not inherited.
    import pdftext.extraction as extraction
    worker_init = (_original_worker_init if extraction.worker_init is _worker_init
                   else extraction.worker_init)
    _install()
    worker_init(*args)


@contextmanager
def repair_pdftext_unicode():
    """Apply the workaround only while Marker extracts a document."""
    if version("pdftext") != "0.7.1":
        yield
        return
    import pdftext.extraction as extraction
    import pdftext.pdf.pages as pages

    global _original_worker_init
    old_get_chars, old_worker_init = pages.get_chars, extraction.worker_init
    _original_worker_init = old_worker_init
    _install()
    extraction.worker_init = _worker_init
    try:
        yield
    finally:
        pages.get_chars = old_get_chars
        extraction.worker_init = old_worker_init
