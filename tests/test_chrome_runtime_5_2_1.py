from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

import desktop_runtime


class ChromeOnlyRuntimeTests(unittest.TestCase):
    def test_command_disables_extensions_proxy_and_experimental_gpu_flags(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            browser = Path(temp) / "chrome.exe"
            browser.write_bytes(b"")
            with mock.patch.object(desktop_runtime, "DATA_DIR", Path(temp) / "data"):
                command = desktop_runtime._chrome_command(browser, "http://127.0.0.1:9999/")
        joined = " ".join(command).casefold()
        self.assertIn("--disable-extensions", joined)
        self.assertIn("--no-proxy-server", joined)
        self.assertIn("--proxy-bypass-list=*", joined)
        self.assertNotIn("enable-zero-copy", joined)
        self.assertNotIn("enable-gpu-rasterization", joined)
        self.assertNotIn("msedge", joined)

    def test_browser_candidates_never_accept_edge(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            chrome = root / "chrome.exe"
            edge = root / "msedge.exe"
            chrome.write_bytes(b"")
            edge.write_bytes(b"")
            with (
                mock.patch.object(desktop_runtime.os, "name", "posix"),
                mock.patch.object(desktop_runtime.shutil, "which", side_effect=lambda name: str(edge) if "chrome" in name else None),
            ):
                self.assertEqual(desktop_runtime.browser_candidates(), [])

            with (
                mock.patch.object(desktop_runtime.os, "name", "posix"),
                mock.patch.object(desktop_runtime.shutil, "which", side_effect=lambda name: str(chrome) if "chrome" in name else None),
            ):
                candidates = desktop_runtime.browser_candidates()
                self.assertEqual(candidates, [chrome.resolve()])

    def test_visible_google_research_has_no_edge_fallback(self) -> None:
        source = (Path(__file__).resolve().parents[1] / "core" / "google_browser.py").read_text(encoding="utf-8")
        self.assertNotIn("webdriver.Edge", source)
        self.assertNotIn("EdgeOptions", source)
        self.assertIn("webdriver.Chrome", source)


if __name__ == "__main__":
    unittest.main()
