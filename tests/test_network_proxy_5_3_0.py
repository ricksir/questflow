from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.network import DEFAULT_BYPASS, NetworkManager, detect_system_proxy, should_bypass
from web_api import QuestFlowWebApi


class NetworkProxy530Tests(unittest.TestCase):
    def test_local_addresses_are_always_bypassed(self):
        for url in ("http://127.0.0.1:8000/", "http://localhost/", "http://[::1]/"):
            self.assertTrue(should_bypass(url, "" if url.endswith('/') else DEFAULT_BYPASS))

    def test_manual_proxy_is_resolved_without_exposing_password(self):
        config = {
            "network_mode": "manual",
            "network_proxy_host": "proxy.exemplo.local",
            "network_proxy_port": "8080",
            "network_proxy_bypass": DEFAULT_BYPASS,
            "network_proxy_auth": "none",
            "network_proxy_username": "",
        }
        manager = NetworkManager(config)
        result = manager.resolve("https://api.telegram.org/")
        self.assertEqual(result.proxy_url, "http://proxy.exemplo.local:8080")
        self.assertEqual(result.public()["proxy"], "proxy.exemplo.local:8080")
        self.assertNotIn("password", json.dumps(result.public()).lower().replace("password_configured", ""))

    def test_auto_uses_detected_windows_or_environment_proxy(self):
        detected = {
            "source": "windows",
            "https_proxy": "http://proxy.corp:3128",
            "http_proxy": "http://proxy.corp:3128",
            "pac_url": "",
            "auto_detect": False,
            "bypass": DEFAULT_BYPASS,
        }
        with patch("core.network.detect_system_proxy", return_value=detected):
            manager = NetworkManager({"network_mode": "auto", "network_proxy_bypass": DEFAULT_BYPASS})
            result = manager.resolve("https://www.google.com/", refresh=True)
        self.assertEqual(result.proxy_url, "http://proxy.corp:3128")
        self.assertEqual(result.source, "windows")

    def test_direct_mode_does_not_inherit_proxy(self):
        manager = NetworkManager({"network_mode": "direct", "network_proxy_bypass": DEFAULT_BYPASS})
        result = manager.resolve("https://www.google.com/")
        self.assertFalse(result.enabled)
        self.assertEqual(result.source, "direct")

    def test_api_saves_proxy_settings_and_preserves_local_bypass(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            config_path = root / "config.json"
            database_path = root / "db.sqlite"
            taxonomy_path = root / "taxonomy.json"
            api = QuestFlowWebApi(
                database_path,
                config={
                    "network_mode": "auto",
                    "network_proxy_host": "",
                    "network_proxy_port": "",
                    "network_pac_url": "",
                    "network_proxy_bypass": DEFAULT_BYPASS,
                    "network_proxy_auth": "none",
                    "network_proxy_username": "",
                },
                config_path=config_path,
                taxonomy_path=taxonomy_path,
            )
            try:
                result = api.save_network_settings({
                    "network_mode": "manual",
                    "network_proxy_host": "proxy.instituicao",
                    "network_proxy_port": "8080",
                    "network_proxy_bypass": "*.intraer",
                    "network_proxy_auth": "none",
                })
                self.assertTrue(result["ok"])
                saved = json.loads(config_path.read_text(encoding="utf-8"))
                self.assertEqual(saved["network_mode"], "manual")
                self.assertIn("127.0.0.1", saved["network_proxy_bypass"])
                self.assertIn("localhost", saved["network_proxy_bypass"])
                self.assertNotIn("network_proxy_password", saved)
            finally:
                api.shutdown()

    def test_system_detection_has_stable_shape(self):
        result = detect_system_proxy()
        for key in ("source", "https_proxy", "http_proxy", "pac_url", "auto_detect", "bypass"):
            self.assertIn(key, result)


if __name__ == "__main__":
    unittest.main()
