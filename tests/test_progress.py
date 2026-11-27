import sys
import tempfile
import threading
import types
import unittest
from pathlib import Path
from unittest import mock

from sami.progress import ModelProgress, monitor_model


def generated(task, tokens, rate):
    return f"0.1 I slot print_timing: id  7 | task {task} | n_gen = {tokens:6}, tg = {rate} t/s, tg_3s = 1.0 t/s\n"


def released(task):
    return f"0.2 I slot      release: id  7 | task {task} | stop processing: n_tokens = 9, truncated = 0\n"


class ModelProgressTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.log = Path(directory.name) / "server.log"
        self.log.write_text(generated(0, 999, 9.0))
        self.seen = []
        self.progress = ModelProgress(self.seen.append, log_path=self.log)

    def append(self, text):
        with self.log.open("a") as stream:
            stream.write(text)

    def test_reading_then_writing_then_done(self):
        self.progress.begin(2, "page")
        self.assertEqual(self.seen[-1]["phase"], "model_reading")
        self.assertEqual(self.seen[-1]["tokens"], 0)  # Older lines are ignored.
        self.append(generated(1, 100, 16.0) + generated(2, 50, 4.0))
        self.progress.tick()
        self.assertEqual(
            (self.seen[-1]["phase"], self.seen[-1]["tokens"], self.seen[-1]["tokens_per_second"]),
            ("model_writing", 150, 20.0),
        )
        self.append(released(1) + released(2))
        self.progress.tick()
        self.assertEqual(self.seen[-1]["phase"], "model_writing")  # Results not in yet.
        self.progress.item_done()
        self.progress.item_done()
        self.progress.end()
        self.assertEqual((self.seen[-1]["phase"], self.seen[-1]["completed"]), ("model_done", 2))

    def test_partial_lines_wait_for_the_rest(self):
        self.progress.begin(1, "page")
        line = generated(1, 100, 16.0)
        self.append(line[:30])
        self.progress.tick()
        self.assertEqual(self.seen[-1]["tokens"], 0)
        self.append(line[30:])
        self.progress.tick()
        self.assertEqual(self.seen[-1]["tokens"], 100)

    def test_missing_log_and_failing_reporter_are_tolerated(self):
        def fail(_snapshot):
            raise OSError("closed pipe")

        progress = ModelProgress(fail, log_path=self.log.with_name("absent.log"))
        progress.begin(1, "page")
        progress.item_done()
        progress.end()

    def test_idle_or_cancelled_reports_nothing(self):
        self.progress.tick()
        cancelled = threading.Event()
        cancelled.set()
        ModelProgress(self.seen.append, log_path=self.log, cancel_event=cancelled).begin(1, "page")
        self.assertEqual(self.seen, [])


class MonitorHookTests(unittest.TestCase):
    def fake_surya(self):
        client = types.ModuleType("surya.inference.backends.openai_client")
        client.BatchOutputItem = dict
        llamacpp = types.ModuleType("surya.inference.backends.llamacpp")
        llamacpp.chat_completions_batch = lambda batch: [client.BatchOutputItem() for _ in batch]

        class Backend:
            handle = None

            def start(self):
                self.handle = object()

        llamacpp.LlamaCppBackend = Backend
        backends = types.ModuleType("surya.inference.backends")
        backends.llamacpp, backends.openai_client = llamacpp, client
        modules = {
            "surya": types.ModuleType("surya"),
            "surya.settings": types.ModuleType("surya.settings"),
            "surya.inference": types.ModuleType("surya.inference"),
            "surya.inference.backends": backends,
        }
        return modules, llamacpp, client

    def test_counts_requests_and_restores_surya(self):
        modules, llamacpp, client = self.fake_surya()
        originals = (llamacpp.chat_completions_batch, client.BatchOutputItem, llamacpp.LlamaCppBackend.start)
        seen = []
        table = types.SimpleNamespace(prompt_type="block")
        with mock.patch.dict(sys.modules, modules):
            with monitor_model(seen.append, log_path=Path("absent.log"), interval=60):
                llamacpp.LlamaCppBackend().start()
                llamacpp.chat_completions_batch([table, table])
        self.assertEqual(seen[0]["phase"], "model_loading")
        self.assertEqual([s["completed"] for s in seen[1:]], [0, 1, 2, 2])
        self.assertEqual(seen[-1]["unit"], "block")
        self.assertEqual(
            (llamacpp.chat_completions_batch, client.BatchOutputItem, llamacpp.LlamaCppBackend.start),
            originals,
        )

    def test_without_surya_the_block_still_runs(self):
        with mock.patch.dict(sys.modules):
            sys.modules.pop("surya.settings", None)
            with monitor_model(self.fail):
                ran = True
        self.assertTrue(ran)


if __name__ == "__main__":
    unittest.main()
