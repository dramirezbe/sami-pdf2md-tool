"""The one-line installers must always follow the latest published release."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
LATEST = "https://github.com/dramirezbe/sami-pdf2md-tool/releases/latest/download/"

# Records the requested URL and "downloads" a helper that echoes its arguments.
FAKE_CURL = """#!/usr/bin/env bash
while (($#)); do
    case "$1" in
        -o) output="$2"; shift 2 ;;
        https://*) echo "$1" >>"$CURL_LOG"; shift ;;
        *) shift ;;
    esac
done
echo 'echo "helper $*"' >"$output"
"""


@unittest.skipIf(os.name == "nt", "bash installer")
class LinuxInstallerTests(unittest.TestCase):
    def run_installer(self, *args):
        with tempfile.TemporaryDirectory() as directory:
            curl = Path(directory, "curl")
            curl.write_text(FAKE_CURL)
            curl.chmod(0o755)
            log = Path(directory, "urls")
            env = dict(os.environ, PATH=f"{directory}{os.pathsep}{os.environ['PATH']}", CURL_LOG=str(log))
            # Run from the checkout, where the packaging/ template is also present.
            result = subprocess.run(
                ["bash", str(ROOT / "install.sh"), *args],
                env=env, capture_output=True, text=True, check=True,
            )
            return result.stdout, log.read_text().split()

    def test_install_and_update_use_the_latest_release_helper(self):
        for args in ((), ("install",), ("update",)):
            with self.subTest(args=args):
                output, urls = self.run_installer(*args)
                self.assertEqual(urls, [LATEST + "cli-install-linux.sh"])
                self.assertIn("helper --component all", output)

    def test_upgrade_from_an_older_cli_uses_the_latest_release(self):
        output, urls = self.run_installer("upgrade", "python", "git+https://example.invalid/sami", "")
        self.assertEqual(urls, [LATEST + "cli-install-linux.sh"])
        self.assertIn("helper --component all", output)

    def test_component_can_be_selected(self):
        output, _ = self.run_installer("update", "--component", "cli")
        self.assertIn("helper --component cli", output)


class WindowsInstallerTests(unittest.TestCase):
    def test_uses_the_latest_release_helper(self):
        script = (ROOT / "install.ps1").read_text()
        self.assertIn("releases/latest/download/cli-install-windows.ps1", script)
        self.assertNotIn("raw.githubusercontent.com", script)


if __name__ == "__main__":
    unittest.main()
