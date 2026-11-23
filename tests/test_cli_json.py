from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sami.contracts import EngineResult
from sami.events import Event


class CliJsonTests(unittest.TestCase):
    def test_effective_device_accounts_for_engine_and_server_backend(self) -> None:
        from sami import cli

        with patch.dict("os.environ", {
            "TORCH_DEVICE": "cuda",
            "FAST_DETECTOR_DEVICE": "cuda",
            "SURYA_INFERENCE_BACKEND": "llamacpp",
            "LLAMA_CPP_NGL": "0",
        }):
            self.assertEqual(cli._effective_device("marker"), "cpu")
            self.assertEqual(cli._effective_device("fast"), "cpu")

    def test_fast_mode_emits_only_valid_jsonl_and_publishes_result(self) -> None:
        from sami import cli

        with tempfile.TemporaryDirectory(prefix="sami json test ") as temporary:
            root = Path(temporary)
            source = root / "Médical file.pdf"
            source.write_bytes(b"fixture")
            output = root / "output folder"
            stdout = io.StringIO()
            stderr = io.StringIO()
            calls = []

            def fake_convert(request, **kwargs):
                calls.append((request, kwargs))
                print("dependency chatter")
                return EngineResult(markdown="# Unicode résumé\n", processed_pages=2)

            with (
                patch.object(cli, "ensure_app_home") as app_home,
                patch.object(cli, "_install_signal_handlers"),
                patch.object(cli, "_configure_cpu", return_value={}),
                patch.object(cli, "_effective_device", return_value="cpu"),
                patch("sami.engines.convert", side_effect=fake_convert),
                contextlib.redirect_stdout(stdout),
                contextlib.redirect_stderr(stderr),
            ):
                exit_code = cli.main([
                    "--mode", "fast", "--json", "--output", str(output),
                    str(source), str(source),
                ])

            self.assertEqual(exit_code, 0)
            self.assertEqual(len(calls), 1)
            app_home.assert_called_once_with(require_llama_server=False)
            request, dispatch_kwargs = calls[0]
            self.assertEqual(request.mode, "fast")
            self.assertEqual(request.device, "cpu")
            self.assertIsNone(dispatch_kwargs["cpu_config"])
            self.assertTrue((output / source.stem / f"{source.stem}.md").is_file())
            self.assertIn("résumé", (output / source.stem / f"{source.stem}.md").read_text())

            lines = stdout.getvalue().splitlines()
            events = [Event.from_json_line(line) for line in lines]
            self.assertEqual([event.seq for event in events], list(range(1, len(events) + 1)))
            self.assertEqual(
                [event.event for event in events],
                ["run_started", "inputs_resolved", "job_started", "job_finished", "run_finished"],
            )
            self.assertEqual(events[1].data["count"], 1)
            finished = events[-2].data["result"]
            self.assertEqual(finished["status"], "succeeded")
            self.assertEqual(finished["mode"], "fast")
            self.assertEqual(json.loads(lines[-1])["data"]["exit_code"], 0)
            self.assertNotIn("sami:", stdout.getvalue())
            self.assertIn("sami: 1 file(s) queued", stderr.getvalue())
            self.assertIn("dependency chatter", stderr.getvalue())

    def test_engine_failure_still_emits_terminal_job_and_run_events(self) -> None:
        from sami import cli

        with tempfile.TemporaryDirectory(prefix="sami json failure ") as temporary:
            root = Path(temporary)
            source = root / "bad.pdf"
            source.write_bytes(b"fixture")
            stdout = io.StringIO()
            stderr = io.StringIO()

            with (
                patch.object(cli, "ensure_app_home"),
                patch.object(cli, "_install_signal_handlers"),
                patch.object(cli, "_configure_cpu", return_value={}),
                patch.object(cli, "_effective_device", return_value="cpu"),
                patch("sami.engines.convert", side_effect=RuntimeError("engine failure")),
                contextlib.redirect_stdout(stdout),
                contextlib.redirect_stderr(stderr),
            ):
                exit_code = cli.main(["--mode", "fast", "--json", str(source)])

            self.assertEqual(exit_code, 1)
            events = [Event.from_json_line(line) for line in stdout.getvalue().splitlines()]
            self.assertEqual(events[-2].event, "job_finished")
            self.assertEqual(events[-2].data["result"]["status"], "failed")
            self.assertEqual(events[-1].event, "run_finished")
            self.assertEqual(events[-1].data["totals"]["failed"], 1)
            self.assertIn("engine failure", stderr.getvalue())

    def test_marker_initialization_failure_finishes_every_job_and_run(self) -> None:
        from sami import cli

        with tempfile.TemporaryDirectory(prefix="sami init failure ") as temporary:
            root = Path(temporary)
            sources = [root / "one.pdf", root / "two.pdf"]
            for source in sources:
                source.write_bytes(b"fixture")
            stdout = io.StringIO()
            stderr = io.StringIO()

            with (
                patch.object(cli, "ensure_app_home"),
                patch.object(cli, "_install_signal_handlers"),
                patch.object(cli, "_configure_cpu", return_value={}),
                patch.object(cli, "_effective_device", return_value="cpu"),
                patch("sami.engines.marker.build_converter", side_effect=RuntimeError("model startup failed")),
                contextlib.redirect_stdout(stdout),
                contextlib.redirect_stderr(stderr),
            ):
                exit_code = cli.main(["--mode", "quality", "--json", *(str(p) for p in sources)])

            self.assertEqual(exit_code, 1)
            events = [Event.from_json_line(line) for line in stdout.getvalue().splitlines()]
            terminal = [event for event in events if event.event == "job_finished"]
            self.assertEqual(len(terminal), 2)
            self.assertTrue(all(event.data["result"]["status"] == "failed" for event in terminal))
            self.assertEqual(events[-1].event, "run_finished")
            self.assertEqual(events[-1].data["totals"]["failed"], 2)


if __name__ == "__main__":
    unittest.main()
