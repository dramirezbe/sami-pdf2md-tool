from __future__ import annotations

import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from sami.cli import main
from sami.contracts import AccelerationError, EngineResult
from sami.outputs import make_staging_dir


class UIContractTests(unittest.TestCase):
    def run_json(self, root, args, convert, *, device="cpu", converter=None):
        stdout, stderr = io.StringIO(), io.StringIO()
        with (
            patch.dict(os.environ, {"SAMI_HOME": str(root / "sami")}),
            patch("sami.cli._effective_device", return_value=device),
            patch("sami.engines.convert", side_effect=convert),
            patch("sami.engines.marker.build_converter", side_effect=converter),
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            result = main(["convert", "--json", *map(str, args)])
        return result, [json.loads(line) for line in stdout.getvalue().splitlines()]

    def test_invalid_arguments_have_structured_terminal_error(self):
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            self.assertEqual(main(["convert", "paper.pdf", "--mode", "unknown", "--json"]), 2)
        event = json.loads(stdout.getvalue())
        self.assertEqual(event["event"], "run_finished")
        self.assertEqual(event["data"]["error"]["code"], "INVALID_ARGUMENTS")
        self.assertIn("invalid choice", stderr.getvalue())

    def test_recursive_mixed_lot_keeps_order_and_finishes_valid_pdfs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "PDFs"
            child = source / "subfolder"
            child.mkdir(parents=True)
            a, b, c = source / "a.pdf", source / "b.PDF", child / "c.pdf"
            for pdf in (a, b, c):
                pdf.touch()
            hidden = source / ".abandoned-sami-cache"
            hidden.mkdir()
            (hidden / "staged.pdf").touch()
            result, events = self.run_json(
                root, [b, source, root / "missing.pdf", "--recursive", "--mode", "fast"],
                lambda *_a, **_kw: EngineResult(markdown="# converted", processed_pages=1),
            )
            self.assertEqual(result, 1)
            resolved = events[1]["data"]
            self.assertEqual(resolved["inputs"], list(map(str, (b, a, c))))
            self.assertEqual(resolved["issues"][0]["code"], "INPUT_NOT_FOUND")
            self.assertEqual(events[-1]["data"]["totals"]["succeeded"], 3)
            self.assertTrue((child / "c" / "c.md").exists())

    def test_gpu_retry_reuses_mode_and_keeps_cpu_for_next_document(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pdfs = [root / "one.pdf", root / "two.pdf"]
            for file in pdfs:
                file.touch()
            attempts = []

            def converter(*_, **__):
                return SimpleNamespace(sami_vlm_cuda=os.environ.get("TORCH_DEVICE") != "cpu")

            def convert(request, stage_logger, **_):
                attempts.append((request.mode, request.device, request.attempt))
                stage_logger(request.input_path.name, "layout")
                if request.device == "cuda":
                    (request.staging_dir / "failed-attempt.png").touch()
                    raise AccelerationError("CUDA allocation failed")
                self.assertEqual(os.environ["FAST_DETECTOR_DEVICE"], "cpu")
                return EngineResult(markdown="CPU result", processed_pages=1)

            result, events = self.run_json(root, pdfs, convert, converter=converter, device="cuda")
            self.assertEqual(result, 0)
            self.assertEqual(attempts, [("balanced", "cuda", 1), ("balanced", "cpu", 2), ("balanced", "cpu", 1)])
            terminals = [e for e in events if e["event"] == "job_finished"]
            retry, = [e for e in events if e["event"] == "job_retrying"]
            self.assertEqual(retry["job_id"], terminals[0]["job_id"])
            self.assertEqual(retry["attempt"], 2)
            self.assertEqual(terminals[0]["data"]["result"]["warnings"][0]["code"], "GPU_FALLBACK_CPU")
            progress_jobs = [e["job_id"] for e in events if e["event"] == "job_progress"]
            self.assertEqual(progress_jobs[-1], terminals[1]["job_id"])
            self.assertFalse(list(root.rglob("failed-attempt.png")))

    def test_partial_output_is_published_with_a_nonzero_exit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pdf = root / "partial.pdf"
            pdf.touch()
            result, events = self.run_json(
                root, [pdf, "--mode", "fast"],
                lambda *_args, **_kwargs: EngineResult(
                    markdown="Partial output", gaps=({"code": "CONTENT_GAP", "message": "missing page"},),
                ),
            )
            self.assertEqual(result, 1)
            self.assertTrue((root / "partial" / "partial.md").exists())
            self.assertEqual(events[-1]["data"]["totals"]["partial"], 1)

    def test_interrupt_while_creating_staging_leaves_no_directory(self):
        def create_then_interrupt(*args):
            created = make_staging_dir(*args)
            signal.raise_signal(signal.SIGINT)
            return created

        with patch("sami.cli.make_staging_dir", side_effect=create_then_interrupt):
            self._interrupted_conversion()

    def test_repeated_interrupt_during_cleanup_leaves_no_directory(self):
        remove = shutil.rmtree

        def interrupt_then_remove(path, *args, **kwargs):
            if "-sami-" in Path(path).name:
                signal.raise_signal(signal.SIGINT)
            remove(path, *args, **kwargs)

        with patch("sami.cli.shutil.rmtree", side_effect=interrupt_then_remove):
            self._interrupted_conversion()

    def _interrupted_conversion(self):
        def convert(*_args, **_kwargs):
            signal.raise_signal(signal.SIGINT)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pdf = root / "one.pdf"
            pdf.touch()
            result, events = self.run_json(root, [pdf, "--mode", "fast"], convert)
            self.assertEqual(result, 130)
            self.assertEqual(events[-1]["data"]["totals"]["cancelled"], 1)
            self.assertEqual(list(root.glob(".*-sami-*")), [])

    def test_stdin_cancel_finishes_active_and_queued_documents(self):
        self._cancel_batch(use_stdin=True)

    @unittest.skipIf(os.name == "nt", "POSIX process signal")
    def test_sigint_finishes_active_and_queued_documents(self):
        self._cancel_batch(use_stdin=False)

    def _cancel_batch(self, *, use_stdin: bool):
        worker = """
import sys
import time
from unittest.mock import patch
from sami.cli import main
def slow(*args, **kwargs):
    until = time.monotonic() + 10
    while time.monotonic() < until:
        time.sleep(0.025)
    raise RuntimeError("cancel timed out")
with patch('sami.engines.convert', side_effect=slow):
    raise SystemExit(main(sys.argv[1:]))
"""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pdfs = [root / "one.pdf", root / "two.pdf"]
            for file in pdfs:
                file.touch()
            args = [sys.executable, "-c", worker, "--json", "--mode", "fast", *map(str, pdfs)]
            if use_stdin:
                args.append("--control-stdin")
            with subprocess.Popen(
                args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, encoding="utf-8", env=dict(os.environ, SAMI_HOME=str(root / "sami")),
            ) as worker:
                started = [json.loads(worker.stdout.readline()) for _ in range(3)]
                self.assertEqual(started[-1]["event"], "job_started")
                if use_stdin:
                    command = {"protocol_version": 1, "command": "cancel", "run_id": started[0]["run_id"]}
                    worker.stdin.write(json.dumps({**command, "run_id": "other-run"}) + "\n")
                    line = json.dumps(command) + "\n"
                    worker.stdin.write(line[:16])
                    worker.stdin.flush()
                    worker.stdin.write(line[16:])
                    worker.stdin.flush()
                else:
                    worker.send_signal(signal.SIGINT)
                out, err = worker.communicate(timeout=8)
                self.assertEqual(worker.returncode, 130, err)
                remaining = [json.loads(line) for line in out.splitlines()]
            self.assertEqual([event["event"] for event in remaining], ["job_finished", "job_finished", "run_finished"])
            self.assertEqual(remaining[-1]["data"]["totals"]["cancelled"], 2)
            self.assertEqual(remaining[0]["job_id"], started[-1]["job_id"])
            self.assertFalse(list(root.rglob("*.md")))
            self.assertFalse(list(root.glob(".*-sami-*")))
