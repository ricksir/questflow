from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import desktop_runtime


ROOT = Path(__file__).resolve().parents[1]


class PostUpdateStartup6152Tests(unittest.TestCase):
    def test_manager_closes_only_questflow_chrome_profile(self) -> None:
        source = (ROOT / "questflow_manager.ps1").read_text(encoding="utf-8")
        self.assertIn("data\\chrome_runtime_5_4_0", source)
        self.assertIn("$_.Name -ieq 'chrome.exe'", source)
        self.assertIn("$escapedChromeProfile", source)
        self.assertNotIn("Stop-Process -Name chrome", source)
        self.assertNotIn("taskkill /im chrome.exe", source.casefold())

    def test_runtime_has_transport_preflight_cleanup_and_retry(self) -> None:
        source = (ROOT / "desktop_runtime.py").read_text(encoding="utf-8")
        self.assertIn("_wait_for_server_transport(server, timeout=8.0)", source)
        self.assertIn("terminate_stale_questflow_chrome(wait_seconds=1.0)", source)
        self.assertIn("for attempt in range(2)", source)
        self.assertIn("QF_CHROME_PROFILE", source)
        self.assertIn("Get-CimInstance Win32_Process", source)

    def test_non_windows_cleanup_is_noop(self) -> None:
        with mock.patch.object(desktop_runtime.os, "name", "posix"):
            self.assertEqual(desktop_runtime.terminate_stale_questflow_chrome(), 0)

    def test_windows_cleanup_targets_dedicated_profile_through_environment(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            data = Path(temp) / "data"
            completed = SimpleNamespace(stdout="1\n", returncode=0)
            with (
                mock.patch.object(desktop_runtime.os, "name", "nt"),
                mock.patch.object(desktop_runtime, "DATA_DIR", data),
                mock.patch.object(desktop_runtime.shutil, "which", return_value="powershell.exe"),
                mock.patch.object(desktop_runtime.subprocess, "run", return_value=completed) as run,
                mock.patch.object(desktop_runtime.time, "sleep"),
            ):
                count = desktop_runtime.terminate_stale_questflow_chrome(wait_seconds=0.1)
        self.assertEqual(count, 1)
        kwargs = run.call_args.kwargs
        self.assertIn("QF_CHROME_PROFILE", kwargs["env"])
        self.assertTrue(kwargs["env"]["QF_CHROME_PROFILE"].endswith("chrome_runtime_5_4_0"))
        command = " ".join(run.call_args.args[0])
        self.assertIn("powershell", command.casefold())

    def test_transport_preflight_retries_until_loopback_accepts(self) -> None:
        server = SimpleNamespace(port=53155)
        connection = mock.MagicMock()
        connection.__enter__.return_value = connection
        with mock.patch.object(desktop_runtime.socket, "create_connection", return_value=connection) as connect:
            self.assertTrue(desktop_runtime._wait_for_server_transport(server, timeout=0.2))
        connect.assert_called_once_with(("127.0.0.1", 53155), timeout=0.35)


if __name__ == "__main__":
    unittest.main()
