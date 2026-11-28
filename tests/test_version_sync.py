import importlib.util
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("sync_version", ROOT / "scripts/sync_version.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
FILES = (
    "VERSION", "ui/package.json", "ui/package-lock.json",
    "packaging/runtime-manifest.json", "packaging/linux/cli-install.sh",
    "packaging/windows/cli-install.ps1",
)


class VersionSyncTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        for name in FILES:
            destination = self.root / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / name, destination)
        self.root_patch = patch.object(module, "ROOT", self.root)
        self.root_patch.start()
        self.addCleanup(self.root_patch.stop)

    def test_sync_propagates_version_and_is_idempotent(self):
        (self.root / "VERSION").write_text("1.2.3\n")
        module.sync(module.version())
        before = {name: (self.root / name).read_bytes() for name in FILES}
        module.sync(module.version())
        self.assertEqual(before, {name: (self.root / name).read_bytes() for name in FILES})
        for name in FILES:
            self.assertIn(b"1.2.3", before[name])

    def test_rejects_invalid_version(self):
        (self.root / "VERSION").write_text("0.4.3;unsafe")
        with self.assertRaises(ValueError):
            module.version()

    def test_mismatched_tag_is_rejected(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts/sync_version.py"), "--tag", "v9.9.9"],
            text=True, capture_output=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("does not match VERSION", result.stderr)


if __name__ == "__main__":
    unittest.main()
