from __future__ import annotations

import subprocess
import sys
import unittest


class EngineDispatchTests(unittest.TestCase):
    def test_public_mode_table_is_correct_and_imports_are_deferred(self) -> None:
        script = r'''
import sys
from sami.engines import select_engine
assert select_engine("fast").engine == "fast"
assert select_engine("balanced").engine == "marker"
assert select_engine("balanced").profile == "fast"
assert select_engine("quality").engine == "marker"
assert select_engine("quality").profile == "balanced"
assert "sami.engines.fast" not in sys.modules
assert "marker" not in sys.modules
assert "torch" not in sys.modules
'''
        completed = subprocess.run(
            [sys.executable, "-c", script], capture_output=True, text=True, timeout=20,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_unknown_public_mode_is_rejected(self) -> None:
        from sami.engines import select_engine

        with self.assertRaises(ValueError):
            select_engine("draft")


if __name__ == "__main__":
    unittest.main()
