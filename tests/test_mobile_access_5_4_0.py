from __future__ import annotations

import json
import sys
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))

from web_server import QuestFlowLocalServer  # noqa: E402


class DummyApi:
    def bootstrap_shell(self):
        return {"ready": True, "version": "5.4.0"}


class MobileAccessTests(unittest.TestCase):
    def test_mobile_lan_server_keeps_api_token_protected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "index.html").write_text("<!doctype html><meta name='viewport' content='width=device-width,initial-scale=1'><title>QF</title>", encoding="utf-8")
            server = QuestFlowLocalServer(DummyApi(), root, bind_host="0.0.0.0")
            server.start()
            try:
                # Static UI may be downloaded, but API data requires the random session token.
                with urllib.request.urlopen(server.base_url + "/index.html", timeout=2) as response:
                    self.assertEqual(response.status, 200)
                body = json.dumps({"method": "bootstrap_shell", "args": []}).encode()
                request = urllib.request.Request(server.base_url + "/api/call", data=body, method="POST", headers={"Content-Type": "application/json"})
                with self.assertRaises(urllib.error.HTTPError) as error:
                    urllib.request.urlopen(request, timeout=2)
                self.assertEqual(error.exception.code, 401)

                request = urllib.request.Request(
                    server.base_url + "/api/call",
                    data=body,
                    method="POST",
                    headers={"Content-Type": "application/json", "X-QuestFlow-Token": server.token},
                )
                with urllib.request.urlopen(request, timeout=2) as response:
                    payload = json.loads(response.read())
                self.assertTrue(payload["ok"])
                self.assertTrue(payload["result"]["ready"])
            finally:
                server.stop()

    def test_mobile_urls_are_only_exposed_when_lan_mode_is_enabled(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); (root / "index.html").write_text("ok", encoding="utf-8")
            local = QuestFlowLocalServer(DummyApi(), root, bind_host="127.0.0.1")
            self.assertEqual(local.mobile_urls(), [])

    def test_web_ui_declares_responsive_viewport_and_mobile_breakpoints(self):
        html = (BASE / "web" / "index.html").read_text(encoding="utf-8")
        css = (BASE / "web" / "styles.css").read_text(encoding="utf-8")
        self.assertIn("width=device-width", html)
        self.assertIn("@media", css)
        self.assertIn("max-width", css)


if __name__ == "__main__":
    unittest.main()
