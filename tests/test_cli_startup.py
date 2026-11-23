from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPOSITORY = Path(__file__).resolve().parents[1]


class CliStartupTests(unittest.TestCase):
    def _environment(self, app_home: Path) -> dict[str, str]:
        env = os.environ.copy()
        env["SAMI_HOME"] = str(app_home)
        env.pop("HF_HOME", None)
        env.pop("TORCH_HOME", None)
        return env

    def test_import_has_no_engine_home_environment_or_signal_side_effects(self) -> None:
        with tempfile.TemporaryDirectory(prefix="sami import test ") as temp_dir:
            app_home = Path(temp_dir) / "app home"
            script = r'''
import os, signal, sys
before_handlers = {name: signal.getsignal(getattr(signal, name)) for name in ("SIGINT", "SIGTERM")}
before_env = dict(os.environ)
import sami.cli
after_handlers = {name: signal.getsignal(getattr(signal, name)) for name in ("SIGINT", "SIGTERM")}
assert before_handlers == after_handlers
assert os.environ == before_env
assert "torch" not in sys.modules
assert "marker" not in sys.modules
assert "surya" not in sys.modules
'''
            completed = subprocess.run(
                [sys.executable, "-c", script], cwd=REPOSITORY,
                env=self._environment(app_home), capture_output=True, text=True, timeout=20,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertFalse(app_home.exists())

    def test_help_and_version_do_not_initialize_app_home_or_engines(self) -> None:
        with tempfile.TemporaryDirectory(prefix="sami cli test ") as temp_dir:
            app_home = Path(temp_dir) / "app home"
            env = self._environment(app_home)
            from sami import __version__
            for argument, expected in (("--help", "usage: sami"), ("--version", f"sami {__version__}")):
                with self.subTest(argument=argument):
                    completed = subprocess.run(
                        [sys.executable, "-m", "sami.cli", argument],
                        cwd=REPOSITORY, env=env, capture_output=True, text=True, timeout=20,
                    )
                    self.assertEqual(completed.returncode, 0, completed.stderr)
                    self.assertIn(expected, completed.stdout)
                    self.assertFalse(app_home.exists())


if __name__ == "__main__":
    unittest.main()
