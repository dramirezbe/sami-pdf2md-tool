"""Tests for `sami health [--json]` subcommand."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch


class TestHealthCommand(unittest.TestCase):
    """sami health --json emits one valid JSON object; exit codes match status."""

    def _run(self, args: list[str], *, sami_home: Path | None = None, missing=None) -> tuple[int, dict | None]:
        """Run sami health subcommand; return (exit_code, parsed_json_or_None)."""
        from sami.cli import _health_command
        env = {}
        if sami_home is not None:
            env["SAMI_HOME"] = str(sami_home)

        captured = StringIO()
        with patch.dict(os.environ, env, clear=False), \
             patch("sami.diagnostics._missing_packages", return_value=missing or []), \
             patch("sys.stdout", captured):
            code = _health_command(args)

        output = captured.getvalue().strip()
        if "--json" in args and output:
            return code, json.loads(output)
        return code, None

    def test_json_flag_emits_valid_json(self):
        code, obj = self._run(["--json"])
        self.assertIsNotNone(obj)
        self.assertIsInstance(obj, dict)

    def test_json_has_required_keys(self):
        _, obj = self._run(["--json"])
        for key in ("protocol_version", "cli_version", "status", "modes", "warnings", "repair_reasons"):
            self.assertIn(key, obj, f"Missing key: {key}")

    def test_protocol_version_is_1(self):
        _, obj = self._run(["--json"])
        self.assertEqual(obj["protocol_version"], 1)

    def test_modes_has_all_three(self):
        _, obj = self._run(["--json"])
        for mode in ("fast", "balanced", "quality"):
            self.assertIn(mode, obj["modes"], f"Missing mode: {mode}")

    def test_status_values(self):
        _, obj = self._run(["--json"])
        self.assertIn(obj["status"], ("ready", "degraded", "repair_required"))

    def test_invalid_binary_leaves_installation_degraded(self):
        with tempfile.TemporaryDirectory() as td:
            sami_home = Path(td)
            binary = "llama-server.exe" if sys.platform == "win32" else "llama-server"
            (sami_home / "bin").mkdir()
            (sami_home / "bin" / binary).write_bytes(b"fake")
            with patch.dict(os.environ, {}, clear=True):
                code, obj = self._run(["--json"], sami_home=sami_home)
            self.assertEqual(code, 0)
            self.assertEqual(obj["status"], "degraded")
            self.assertIsNone(obj["paths"]["llama_server"])

    def test_cuda_only_install_is_discovered(self):
        with tempfile.TemporaryDirectory() as td:
            sami_home = Path(td)
            binary = "llama-server.exe" if sys.platform == "win32" else "llama-server"
            server = sami_home / "bin" / "cuda" / binary
            server.parent.mkdir(parents=True)
            server.write_bytes(b"MZ" if sys.platform == "win32" else b"\x7fELF")
            with patch.dict(os.environ, {}, clear=True):
                _, obj = self._run(["--json"], sami_home=sami_home)
            self.assertEqual(obj["status"], "degraded")
            self.assertEqual(obj["paths"]["llama_server"], str(server))

    def test_exit_0_when_degraded_quality_missing(self):
        with tempfile.TemporaryDirectory() as td:
            sami_home = Path(td)
            # No llama-server → degraded but not repair_required
            code, obj = self._run(["--json"], sami_home=sami_home)
            self.assertEqual(code, 0)
            # quality.available should be False
            self.assertFalse(obj["modes"]["quality"]["available"])

    def test_balanced_requires_local_models(self):
        with tempfile.TemporaryDirectory() as td, patch.dict(os.environ, {}, clear=True):
            _, obj = self._run(["--json"], sami_home=Path(td))
        self.assertTrue(obj["modes"]["fast"]["available"])
        self.assertFalse(obj["modes"]["balanced"]["available"])

    def test_fast_has_no_inference_server(self):
        _, obj = self._run(["--json"])
        self.assertFalse(obj["modes"]["fast"]["inference_server"])
        self.assertFalse(obj["modes"]["balanced"]["inference_server"])
        self.assertTrue(obj["modes"]["quality"]["inference_server"])

    def test_ready_verification_is_tied_to_launcher_and_assets(self):
        from sami import __version__
        from sami.diagnostics import register_installation

        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            launcher = home / "sami"
            launcher.touch()
            identity = register_installation(home, launcher)["installation_id"]
            self.assertEqual(register_installation(home, launcher)["installation_id"], identity)
            inventory = {
                "llama": launcher, "gguf": (launcher, launcher), "layout": (launcher,),
                "ocr": (launcher,), "hf_home": home, "fingerprint": {str(launcher): [10, 1]},
            }
            report = {
                "schema_version": 1, "installation_id": identity, "cli_version": __version__,
                "fingerprint": inventory["fingerprint"], "failures": [], "warnings": [],
                "modes": {mode: {"cpu": True, "device": "cpu"} for mode in ("fast", "balanced", "quality")},
            }
            (home / "compatibility.json").write_text(json.dumps(report), encoding="utf-8")
            with patch("sami.diagnostics._inventory", return_value=inventory):
                code, obj = self._run(["--json"], sami_home=home)
                self.assertEqual(code, 0)
                self.assertEqual(obj["status"], "ready")
                self.assertEqual(obj["installation_id"], identity)
                inventory["fingerprint"] = {str(launcher): [12, 2]}
                self.assertEqual(self._run(["--json"], sami_home=home)[1]["status"], "degraded")
                launcher.unlink()
                code, obj = self._run(["--json"], sami_home=home)
                self.assertEqual(code, 3)
                self.assertEqual(obj["status"], "repair_required")

    def test_missing_package_requires_repair(self):
        with tempfile.TemporaryDirectory() as td:
            code, obj = self._run(["--json"], sami_home=Path(td), missing=["pymupdf"])
        self.assertEqual(code, 3)
        self.assertEqual(obj["status"], "repair_required")

    def test_registration_does_not_prepare_models(self):
        from sami.cli import main

        with tempfile.TemporaryDirectory() as td:
            home = Path(td) / "sami-home"
            launcher = Path(td) / "sami"
            launcher.touch()
            captured = StringIO()
            with (patch.dict(os.environ, {"SAMI_HOME": str(home)}),
                  patch("sami.diagnostics.prepare") as prepare, patch("sys.stdout", captured)):
                code = main(["setup", "--register-only", "--executable", str(launcher), "--json"])
            prepare.assert_not_called()
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(captured.getvalue())["paths"]["executable"], str(launcher))


class TestHealthSubcommandDispatch(unittest.TestCase):
    """sami health dispatches before the PDF parser."""

    def test_health_in_argv_does_not_trigger_pdf_parser(self):
        from sami.cli import main
        # `sami health --json` must NOT fail with "unrecognized arguments"
        captured = StringIO()
        with patch("sys.stdout", captured), \
             patch.dict(os.environ, {}, clear=False):
            try:
                code = main(["health", "--json"])
            except SystemExit as e:
                self.fail(f"main raised SystemExit({e.code}) for health subcommand")
        self.assertIn(code, (0, 3))

    def test_no_health_arg_still_parses_pdf_normally(self):
        from sami.cli import main
        # Non-existent PDF → exit 2 (usage error), NOT health dispatch
        code = main(["nonexistent.pdf"])
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
