"""Regression coverage for supplementary Unicode in Marker's PDF text."""
from pathlib import Path

import pytest

pytest.importorskip("pdftext")
import numpy as np
import pypdfium2 as pdfium
from pdftext.extraction import dictionary_output
from pdftext.pdf.chars import PageChars

from sami.engines import pdftext_unicode as repair

FIXTURE = Path(__file__).parent / "fixtures" / "unicode-control.pdf"


def text_from_pages(pages):
    return " ".join(span["text"] for page in pages for block in page["blocks"]
                    for line in block["lines"] for span in line["spans"])


def test_real_pdf_restores_math_symbols_and_restores_patch():
    import pdftext.pdf.pages as pages
    original = pages.get_chars
    with repair.repair_pdftext_unicode():
        text = text_from_pages(dictionary_output(str(FIXTURE), workers=1))
    assert "𝑁" in text and "𝑤" in text
    assert "\ufffd" not in text
    assert pages.get_chars is original


def test_multiprocess_extraction(tmp_path):
    source = pdfium.PdfDocument(str(FIXTURE))
    destination = pdfium.PdfDocument.new()
    destination.import_pages(source, [0] * 20)
    pdf = tmp_path / "multi.pdf"
    destination.save(str(pdf))
    destination.close()
    source.close()
    with repair.repair_pdftext_unicode():
        pages = dictionary_output(str(pdf), workers=2)
    assert len(pages) == 20
    assert all("𝑁" in text_from_pages([page]) and "\ufffd" not in text_from_pages([page])
               for page in pages)


def test_unpaired_surrogates_remain_replacements(monkeypatch):
    raw_codes = [0xD800, ord("A"), 0xDC00, 0xD835, 0xDC41, 0xFFFD]
    original_codes = [0xFFFD, ord("A"), 0xFFFD, 0xFFFD, 0xFFFD, 0xFFFD]
    n = len(raw_codes)
    chars = PageChars("".join(map(chr, original_codes)), np.array(original_codes, dtype=np.uint32),
                      np.zeros(n), np.array([[i, 0, i + 1, 1] for i in range(n)], dtype=float),
                      np.zeros(n, dtype=np.int32), [], np.arange(n))
    monkeypatch.setattr(repair, "_original_get_chars", lambda *args, **kwargs: chars)
    monkeypatch.setattr("pypdfium2.raw.FPDFText_GetUnicode", lambda _page, i: raw_codes[i])
    result = repair._get_chars(type("Page", (), {"raw": None})())
    assert result.text == "\ufffdA\ufffd𝑁\ufffd"
    assert result.char_indices.tolist() == [0, 1, 2, 3, 5]
    assert result.boxes[3].tolist() == [3, 0, 5, 1]
