"""Tests for sami/outputs.py — numbered anti-collision output publication."""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from sami.outputs import (
    make_staging_dir,
    prepend_frontmatter,
    publish,
    read_sami_source,
    reserve_stem,
)


# ---------------------------------------------------------------------------
# Front-matter helpers
# ---------------------------------------------------------------------------

class TestFrontmatter(unittest.TestCase):

    def test_round_trip(self):
        src = Path("/some/path/paper.pdf")
        md = prepend_frontmatter("# Hello\n", source=src)
        result = read_sami_source_from_string(md)
        self.assertEqual(result, src.resolve().as_posix())

    def test_version_included_when_given(self):
        src = Path("/some/path/paper.pdf")
        md = prepend_frontmatter("body", source=src, version="0.2.0")
        self.assertIn("sami_version: 0.2.0", md)

    def test_version_omitted_when_empty(self):
        src = Path("/tmp/x.pdf")
        md = prepend_frontmatter("body", source=src)
        self.assertNotIn("sami_version", md)

    def test_body_preserved(self):
        src = Path("/tmp/x.pdf")
        md = prepend_frontmatter("# Title\n\nContent.", source=src)
        self.assertIn("# Title", md)
        self.assertIn("Content.", md)

    def test_no_frontmatter_returns_none(self):
        p = Path("/tmp/no_fm.md")
        p.write_text("# Just markdown\n")
        self.assertIsNone(read_sami_source(p))
        p.unlink()

    def test_missing_file_returns_none(self):
        self.assertIsNone(read_sami_source(Path("/tmp/nonexistent_sami_test.md")))

    def test_source_key_uses_posix_slashes(self):
        src = Path("/home/user/my/paper.pdf")
        md = prepend_frontmatter("body", source=src)
        self.assertIn("/", md)
        self.assertNotIn("\\", md.split("---\n")[1])  # inside front-matter block


def read_sami_source_from_string(md: str) -> str | None:
    """Write md to a temp file and use read_sami_source()."""
    with tempfile.NamedTemporaryFile(suffix=".md", mode="w", delete=False, encoding="utf-8") as f:
        f.write(md)
        path = Path(f.name)
    try:
        return read_sami_source(path)
    finally:
        path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# reserve_stem
# ---------------------------------------------------------------------------

class TestReserveStem(unittest.TestCase):

    def setUp(self):
        self.td = tempfile.mkdtemp()
        self.out = Path(self.td)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.td, ignore_errors=True)

    def _make_pdf(self, name: str) -> Path:
        p = self.out / name
        p.write_bytes(b"%PDF-1.4")
        return p

    def test_first_run_returns_base_stem(self):
        pdf = self._make_pdf("paper.pdf")
        stem = reserve_stem(pdf, self.out, flat=False)
        self.assertEqual(stem, "paper")

    def test_flat_first_run_returns_base_stem(self):
        pdf = self._make_pdf("paper.pdf")
        stem = reserve_stem(pdf, self.out, flat=True)
        self.assertEqual(stem, "paper")

    def test_second_run_same_pdf_reuses_stem(self):
        pdf = self._make_pdf("paper.pdf")
        # Simulate first run: create existing output with sami frontmatter
        dest = self.out / "paper"
        dest.mkdir()
        md = dest / "paper.md"
        md.write_text(prepend_frontmatter("body", source=pdf), encoding="utf-8")
        # Second run: should return "paper" (owns it)
        stem = reserve_stem(pdf, self.out, flat=False)
        self.assertEqual(stem, "paper")

    def test_different_pdf_same_stem_gets_numbered(self):
        pdf_a = self._make_pdf("paper.pdf")
        pdf_b = self.out.parent / "other" / "paper.pdf"
        pdf_b.parent.mkdir(exist_ok=True)
        pdf_b.write_bytes(b"%PDF-1.4")

        # Simulate first run with pdf_a owning "paper"
        dest = self.out / "paper"
        dest.mkdir()
        (dest / "paper.md").write_text(
            prepend_frontmatter("body", source=pdf_a), encoding="utf-8"
        )
        # pdf_b should get "paper_2"
        stem = reserve_stem(pdf_b, self.out, flat=False)
        self.assertEqual(stem, "paper_2")

    def test_claimed_set_prevents_collision_in_batch(self):
        pdf_a = self._make_pdf("paper.pdf")
        pdf_b = self.out.parent / "sub" / "paper.pdf"
        pdf_b.parent.mkdir(exist_ok=True)
        pdf_b.write_bytes(b"%PDF-1.4")

        claimed: set[str] = set()
        stem_a = reserve_stem(pdf_a, self.out, flat=False, claimed=claimed)
        stem_b = reserve_stem(pdf_b, self.out, flat=False, claimed=claimed)
        self.assertEqual(stem_a, "paper")
        self.assertEqual(stem_b, "paper_2")
        self.assertEqual(claimed, {"paper", "paper_2"})

    def test_flat_different_pdf_same_stem_numbered(self):
        pdf_a = self._make_pdf("report.pdf")
        pdf_b = Path(self.td) / "sub" / "report.pdf"
        pdf_b.parent.mkdir()
        pdf_b.write_bytes(b"%PDF-1.4")

        # Simulate pdf_a owning flat "report.md"
        md = self.out / "report.md"
        md.write_text(prepend_frontmatter("body", source=pdf_a), encoding="utf-8")

        stem = reserve_stem(pdf_b, self.out, flat=True)
        self.assertEqual(stem, "report_2")

    def test_no_frontmatter_treated_as_not_owned(self):
        """Existing .md without sami frontmatter is treated as foreign → next number."""
        pdf = self._make_pdf("doc.pdf")
        dest = self.out / "doc"
        dest.mkdir()
        (dest / "doc.md").write_text("# No frontmatter\n", encoding="utf-8")
        stem = reserve_stem(pdf, self.out, flat=False)
        self.assertEqual(stem, "doc_2")


# ---------------------------------------------------------------------------
# publish
# ---------------------------------------------------------------------------

class TestPublish(unittest.TestCase):

    def setUp(self):
        self.td = tempfile.mkdtemp()
        self.out = Path(self.td) / "output"
        self.out.mkdir()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.td, ignore_errors=True)

    def _make_staging(self, stem: str, contents: dict[str, bytes]) -> Path:
        staging = Path(tempfile.mkdtemp(prefix=f".{stem}-sami-", dir=self.out))
        for name, data in contents.items():
            p = staging / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(data)
        return staging

    def test_non_flat_publishes_md_in_subdir(self):
        staging = self._make_staging("paper", {"paper.md": b"# Hello"})
        result = publish(staging, "paper", self.out, flat=False)
        md = result["md_path"]
        self.assertEqual(md, self.out / "paper" / "paper.md")
        self.assertTrue(md.exists())
        self.assertEqual(md.read_bytes(), b"# Hello")

    def test_flat_publishes_md_in_output_dir(self):
        staging = self._make_staging("paper", {"paper.md": b"# Hello"})
        result = publish(staging, "paper", self.out, flat=True)
        md = result["md_path"]
        self.assertEqual(md, self.out / "paper.md")
        self.assertTrue(md.exists())

    def test_resources_published_before_md(self):
        staging = self._make_staging("paper", {
            "paper.md": b"# Hello",
            "figures/fig1.png": b"PNG",
        })
        result = publish(staging, "paper", self.out, flat=False)
        self.assertEqual(len(result["resource_paths"]), 1)
        fig = result["resource_paths"][0]
        self.assertTrue(fig.exists())
        self.assertTrue(fig.name.endswith("fig1.png"))

    def test_staging_dir_emptied_after_publish(self):
        staging = self._make_staging("paper", {"paper.md": b"body"})
        publish(staging, "paper", self.out, flat=False)
        # Staging should have no files left (all moved via os.replace)
        remaining = list(staging.rglob("*"))
        self.assertEqual(remaining, [])

    def test_error_when_no_md_in_staging(self):
        staging = self._make_staging("paper", {"notes.txt": b"text"})
        with self.assertRaises(FileNotFoundError):
            publish(staging, "paper", self.out, flat=False)

    def test_numbered_stem_creates_correct_subdir(self):
        staging = self._make_staging("paper_2", {"paper_2.md": b"# Second"})
        result = publish(staging, "paper_2", self.out, flat=False)
        md = result["md_path"]
        self.assertEqual(md.parent.name, "paper_2")
        self.assertEqual(md.name, "paper_2.md")


# ---------------------------------------------------------------------------
# make_staging_dir
# ---------------------------------------------------------------------------

class TestMakeStagingDir(unittest.TestCase):

    def test_staging_on_same_filesystem(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td)
            staging = make_staging_dir(out, "paper")
            try:
                # Must be inside out_dir (same filesystem for atomic rename)
                self.assertEqual(staging.parent, out)
                self.assertTrue(staging.name.startswith(".paper-sami-"))
                self.assertTrue(staging.is_dir())
            finally:
                staging.rmdir()

    def test_creates_output_dir_if_missing(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "new" / "nested"
            staging = make_staging_dir(out, "doc")
            try:
                self.assertTrue(out.is_dir())
            finally:
                staging.rmdir()


if __name__ == "__main__":
    unittest.main()
