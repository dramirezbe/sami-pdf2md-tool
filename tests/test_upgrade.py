from __future__ import annotations

import unittest
from unittest.mock import patch

from sami.cli import main
from sami import upgrade


class UpgradeTests(unittest.TestCase):
    def test_cli_dispatches_upgrade_without_conversion(self):
        with patch("sami.upgrade.upgrade_command", return_value=7) as command:
            self.assertEqual(main(["upgrade", "--ref", "test/ref"]), 7)
        command.assert_called_once_with(["--ref", "test/ref"])

    def test_linux_reuses_current_python_and_installed_git_ref(self):
        installed = {"vcs_info": {"requested_revision": "fix/windows"}}
        with (
            patch.object(upgrade, "_installation", return_value=installed),
            patch.object(upgrade.os, "name", "posix"),
            patch.object(upgrade.sys, "prefix", "test-venv"),
            patch.object(upgrade.shutil, "which", return_value="present"),
            patch.object(upgrade.metadata, "version", return_value="2.14.1+cu132"),
            patch.object(upgrade.subprocess, "run") as run,
        ):
            run.return_value.returncode = 7
            self.assertEqual(upgrade.upgrade_command([]), 7)

        command, = run.call_args.args
        env = run.call_args.kwargs["env"]
        self.assertEqual(command[:2], ["bash", "-c"])
        self.assertIn("curl -fsSL", command[2])
        self.assertTrue(env["SAMI_UPGRADE_SCRIPT"].endswith("/fix/windows/install.sh"))
        self.assertTrue(env["SAMI_UPGRADE_SOURCE"].endswith(".git@fix/windows"))
        self.assertEqual(env["SAMI_UPGRADE_PYTHON"], upgrade.sys.executable)
        self.assertEqual(env["SAMI_UPGRADE_INDEX"], "https://download.pytorch.org/whl/cu132")

    def test_windows_starts_irm_in_new_process_group_and_passes_launcher_pids(self):
        with (
            patch.object(upgrade, "_installation", return_value={}),
            patch.object(upgrade.os, "name", "nt"),
            patch.object(upgrade.sys, "prefix", "test-venv"),
            patch.object(upgrade.shutil, "which", return_value="present"),
            patch.object(upgrade, "_cuda_index", return_value=""),
            patch.object(upgrade, "_windows_processes", return_value="100,200"),
            patch.object(upgrade.subprocess, "CREATE_NEW_PROCESS_GROUP", 512, create=True),
            patch.object(upgrade.subprocess, "Popen") as start,
            patch("builtins.print"),
        ):
            self.assertEqual(upgrade.upgrade_command(["--ref", "next"]), 0)

        command, = start.call_args.args
        options = start.call_args.kwargs
        self.assertEqual(command[0], "powershell.exe")
        self.assertIn("irm -Uri", command[-1])
        self.assertIn("Wait-Process", command[-1])
        self.assertEqual(options["creationflags"], 512)
        self.assertEqual(options["env"]["SAMI_UPGRADE_WAIT_FOR"], "100,200")
        self.assertTrue(options["env"]["SAMI_UPGRADE_SCRIPT"].endswith("/next/install.ps1"))
