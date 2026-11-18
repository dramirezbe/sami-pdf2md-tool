from __future__ import annotations

import unittest
from pathlib import Path
import tempfile
from unittest.mock import patch

from sami.contracts import ConversionOptions, ConversionRequest
from sami.engines import select_engine
from sami.engines.fast import Options, convert


REPOSITORY = Path(__file__).resolve().parents[1]


class CasteFastEngineTests(unittest.TestCase):
    def test_reference_profile_is_high_with_ocr_and_images_disabled(self) -> None:
        options = Options(
            quality="high", ocr=False, images=False, markers=True,
            table_style="pipe", max_pages=None,
        ).resolve()
        self.assertEqual(options.quality, "high")
        self.assertFalse(options.ocr)
        self.assertFalse(options.images)
        self.assertTrue(options.markers)
        self.assertEqual(options.table_style, "pipe")
        self.assertIsNone(options.max_pages)

    def test_text_and_tables_convert_without_entering_ocr_path(self) -> None:
        pdf = REPOSITORY / "test-pdfs" / "test_document.pdf"
        request = ConversionRequest(
            job_id="caste-fast-fixture",
            input_path=pdf.resolve(),
            mode="fast",
            options=ConversionOptions(device="auto"),
            staging_dir=(Path(tempfile.gettempdir()) / "sami-caste-stage").resolve(),
            device="cpu",
        )
        with patch("sami.engines.fast.run_ocr_on_page", side_effect=AssertionError("OCR ran")):
            result = convert(request)

        self.assertEqual(result.processed_pages, 5)
        self.assertEqual(result.metrics["tables"], 5)
        self.assertEqual(result.metrics["images"], 0)
        self.assertIn("# Chapter 1: Kinematics", result.markdown)
        self.assertIn("| Variable | Symbol | Unit | Value |", result.markdown)
        self.assertEqual(select_engine("fast").engine, "caste")


if __name__ == "__main__":
    unittest.main()
