import json
import tempfile
import threading
import unittest
from pathlib import Path

from sami.estimate import FileProgress


class Clock:
    now = 0.0

    def __call__(self):
        return self.now


class FileProgressTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.history = Path(directory.name) / "cache" / "progress.json"
        self.clock = Clock()
        self.seen = []

    def make(self, **options):
        values = {"pages": 2, "mode": "balanced", "device": "cpu", "clock": self.clock,
                  "history": self.history, **options}
        return FileProgress(self.seen.append, **values)

    def run_scanned(self, progress):
        progress.stage("Reading PDF pages...")
        self.clock.now += 20
        progress.stage("OCR (2/2 pages need it)...")
        self.clock.now += 100
        progress.model({"phase": "model_writing", "completed": 1, "total": 2, "tokens": 1500})
        self.clock.now += 100
        progress.stage("Structure building...")
        progress.stage("[24/24] DebugProcessor...")

    def test_percentage_never_goes_back_and_stays_below_complete(self):
        progress = self.make()
        self.run_scanned(progress)
        self.clock.now += 100_000
        progress.tick()
        values = [data["percent"] for data in self.seen]
        self.assertEqual(values, sorted(values))
        self.assertGreater(values[-1], 90)
        self.assertLessEqual(values[-1], 99)

    def test_fills_without_signals_and_faster_at_the_start(self):
        progress = self.make()
        progress.stage("OCR (2/2 pages need it)...")
        samples = []
        for _ in range(3):
            self.clock.now += 100
            samples.append(progress.percent)
        self.assertGreater(samples[0], samples[1] - samples[0])
        self.assertGreaterEqual(samples[1] - samples[0], samples[2] - samples[1])
        self.assertLess(samples[-1], 60)

    def test_unfinished_ocr_pages_cannot_reach_nearly_complete(self):
        progress = self.make(device="cuda")
        progress.stage("OCR (2/2 pages need it)...")
        progress.model({"phase": "model_writing", "unit": "page", "completed": 0, "total": 2, "tokens": 100000})
        self.clock.now += 100_000
        self.assertLess(progress.percent, 60)
        # A single-request batch is not the same as a whole-document page count.
        progress.model({"phase": "model_done", "unit": "page", "completed": 1, "total": 1, "tokens": 200000})
        self.assertLess(progress.percent, 60)
        self.assertEqual((self.seen[-1]["completed"], self.seen[-1]["total"]), (0, 2))
        progress.stage("OCR progress (1/2 pages completed; page 4)")
        self.assertLess(progress.percent, 95)
        self.assertGreater(progress.percent, 60)

    def test_table_processing_keeps_room_after_a_long_ocr(self):
        progress = self.make(pages=13, device="cuda")
        progress.stage("OCR (3/13 pages need it)...")
        self.clock.now += 100_000
        progress.stage("OCR progress (3/3 pages completed; page 11)")
        progress.stage("Structure building...")
        progress.stage("[14/24] TableProcessor...")
        progress.model({"phase": "model_writing", "unit": "block", "completed": 0, "total": 1})
        self.assertLess(progress.percent, 96)

    def test_slow_processor_does_not_claim_the_remaining_processors_are_done(self):
        progress = self.make()
        progress.stage("OCR (skipped, no pages need it)...")
        progress.stage("[6/24] EquationProcessor...")
        progress.model({"phase": "model_writing", "unit": "block", "completed": 0, "total": 3})
        self.clock.now += 100_000
        self.assertLess(progress.percent, 50)
        progress.stage("[24/24] DebugProcessor...")
        self.assertGreater(progress.percent, 90)

    def test_ticks_publish_only_changes(self):
        progress = self.make()
        progress.tick()
        self.assertEqual(self.seen, [])
        progress.stage("Reading PDF pages...")
        progress.tick()
        self.assertEqual(len(self.seen), 1)
        self.clock.now += 10
        progress.tick()
        self.assertEqual(len(self.seen), 2)
        self.assertEqual(self.seen[-1]["stage"], "Reading PDF pages...")

    def test_digital_files_move_past_preparation(self):
        progress = self.make(pages=5)
        progress.stage("Layout detection (fast/rf-detr, 5 pages)...")
        self.clock.now += 20
        self.assertGreaterEqual(progress.percent, 15)
        progress.stage("OCR (skipped, all pages have text)...")
        self.assertEqual(self.seen[-1]["percent"], 30)

    def test_page_engines_report_exact_progress(self):
        progress = self.make(pages=4, mode="fast")
        progress.pages_done(2, 4)
        self.assertEqual(self.seen[-1]["percent"], 49)

    def test_history_is_saved_and_reused(self):
        progress = self.make()
        self.run_scanned(progress)
        progress.save()
        saved = json.loads(self.history.read_text())["balanced:cpu"]
        self.assertEqual(saved, {"prepare": 10.0, "model": 100.0})
        self.history.write_text(json.dumps({"balanced:cpu": {"model": 1.0}}))
        quick = self.make()
        quick.stage("OCR (2/2 pages need it)...")
        self.clock.now += 5
        self.assertGreater(quick.percent, 30)  # Far ahead of the default rate.

    def test_bad_history_and_cancellation_are_tolerated(self):
        self.history.parent.mkdir(parents=True)
        self.history.write_text("not json")
        cancelled = threading.Event()
        cancelled.set()
        self.make(cancel_event=cancelled).stage("Reading PDF pages...")
        self.assertEqual(self.seen, [])


if __name__ == "__main__":
    unittest.main()
