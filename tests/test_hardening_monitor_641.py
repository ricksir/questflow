from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import app_shared
from core import ai_providers
from core.update_monitor import UpdateMonitor, cycle_for
from web_api import QuestFlowWebApi
from web_server import ALLOWED_API_METHODS


class Hardening641Tests(unittest.TestCase):
    def test_version_has_single_release_value(self):
        root = Path(__file__).resolve().parents[1]
        version = (root / "VERSION.txt").read_text(encoding="utf-8").strip()
        project = (root / "pyproject.toml").read_text(encoding="utf-8")
        self.assertEqual(version, "6.23.2")
        self.assertEqual(app_shared.APP_VERSION, version)
        self.assertIn('version = "6.23.2"', project)

    def test_privacy_first_ai_defaults_and_capabilities(self):
        self.assertEqual(app_shared.DEFAULT_CONFIG["ai_active_provider"], "local")
        self.assertFalse(ai_providers._anthropic_supports_sampling("claude-opus-4-7"))
        self.assertFalse(ai_providers._anthropic_supports_sampling("claude-sonnet-5"))
        self.assertTrue(ai_providers._anthropic_supports_sampling("claude-sonnet-4-6"))

    def test_openai_and_gemini_are_stateless_and_new_claude_omits_temperature(self):
        calls = []

        def fake_post(url, payload, headers, **kwargs):
            calls.append((url, payload, headers, kwargs))
            if "openai" in url:
                return {"id": "o1", "output_text": "ok"}
            if "googleapis" in url:
                return {"id": "g1", "output_text": "ok"}
            return {"id": "c1", "content": [{"type": "text", "text": "ok"}]}

        with tempfile.TemporaryDirectory() as d, \
             patch.object(ai_providers, "load_keys", return_value={"openai": "k", "gemini": "k", "anthropic": "k"}), \
             patch.object(ai_providers, "_post", side_effect=fake_post):
            cfg = {}
            ai_providers.generate("openai", "x", config=cfg, config_path=Path(d), model="gpt-test")
            ai_providers.generate("gemini", "x", config=cfg, config_path=Path(d), model="gemini-test")
            ai_providers.generate("anthropic", "x", config=cfg, config_path=Path(d), model="claude-opus-4-7")

        openai_payload = calls[0][1]
        gemini_payload = calls[1][1]
        claude_payload = calls[2][1]
        self.assertIs(openai_payload["store"], False)
        self.assertIs(gemini_payload["store"], False)
        self.assertNotIn("temperature", claude_payload)

    def test_transient_errors_are_retryable_but_bad_request_is_not(self):
        from urllib.error import HTTPError, URLError
        self.assertTrue(ai_providers._should_retry(URLError("offline")))
        self.assertTrue(ai_providers._should_retry(HTTPError("u", 429, "rate", {}, None)))
        self.assertTrue(ai_providers._should_retry(HTTPError("u", 503, "busy", {}, None)))
        self.assertFalse(ai_providers._should_retry(HTTPError("u", 400, "bad", {}, None)))
        self.assertFalse(ai_providers._should_retry(HTTPError("u", 401, "auth", {}, None)))

    def test_monitor_is_consent_first_twice_monthly_and_offline_safe(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            config = {"update_monitor_enabled": True, "update_monitor_days": [1, 15]}
            monitor = UpdateMonitor(config=config, state_path=root / "monitor.json")
            # First half is due from day 1 until explicitly resolved.
            status = monitor.status(datetime(2026, 8, 13, 12, 0).astimezone())
            self.assertTrue(status["due"])
            self.assertEqual(status["days"], [1, 15])
            # The status/scheduler does no network work and creates no SQLite file.
            self.assertFalse((root / "questions.sqlite").exists())

            with patch.object(monitor, "_fetch_one", side_effect=OSError("offline")):
                result = monitor.run(timeout=0.01)
            self.assertFalse(result["ok"])
            self.assertTrue(result["summary"]["offline_or_blocked"])
            self.assertIn("Nada foi alterado no banco", result["message"])
            # Offline does not resolve the current cycle, so it can be tried later.
            self.assertTrue(monitor.status(datetime(2026, 8, 13, 12, 5).astimezone())["due"])
            self.assertFalse((root / "questions.sqlite").exists())

    def test_skip_and_snooze_are_local_state_only(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "monitor.json"
            monitor = UpdateMonitor(config={"update_monitor_enabled": True, "update_monitor_days": [1, 15]}, state_path=path)
            now = datetime(2026, 8, 15, 12, 0).astimezone()
            skipped = monitor.defer("skip", now=now)
            self.assertFalse(skipped["due"])
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload["resolved_cycle"], cycle_for(now, (1, 15))[0])

    def test_monitor_api_is_allowlisted_and_uses_background_task(self):
        expected = {
            "get_update_monitor_status",
            "save_update_monitor_settings",
            "defer_update_monitor",
            "start_update_monitor_check",
        }
        self.assertTrue(expected <= set(ALLOWED_API_METHODS))
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            api = QuestFlowWebApi(database_path=root / "q.sqlite", config_path=root / "config.json")
            try:
                status = api.get_update_monitor_status()
                self.assertTrue(status["ok"])
                started = api.start_update_monitor_check()
                self.assertTrue(started["ok"])
                self.assertIn("task_id", started)
            finally:
                api.shutdown()

    def test_monitor_status_is_reachable_over_real_local_http(self):
        import urllib.request
        from web_server import QuestFlowLocalServer

        class DummyApi:
            def get_update_monitor_status(self):
                return {"ok": True, "enabled": True, "days": [1, 15], "due": False}

        root = Path(__file__).resolve().parents[1]
        server = QuestFlowLocalServer(DummyApi(), root / "web", preferred_port=0)
        server.start()
        try:
            payload = json.dumps({"method": "get_update_monitor_status", "args": []}).encode("utf-8")
            request = urllib.request.Request(
                f"{server.base_url}/api/call",
                data=payload,
                headers={"Content-Type": "application/json", "X-QuestFlow-Token": server.token},
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=5) as response:
                result = json.loads(response.read().decode("utf-8"))
            self.assertTrue(result["ok"])
            self.assertEqual(result["result"]["days"], [1, 15])
        finally:
            server.stop()

    def test_telegram_token_is_never_written_to_config_json(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            config_path = root / "config.json"
            api = QuestFlowWebApi(
                database_path=root / "q.sqlite",
                config_path=config_path,
                config={"telegram_bot_token": "123:VERY_SECRET", "telegram_chat_id": "999"},
            )
            try:
                api._persist_config()
                text = config_path.read_text(encoding="utf-8")
                self.assertNotIn("VERY_SECRET", text)
                self.assertNotIn("telegram_bot_token", text)
                self.assertEqual(api.config["telegram_bot_token"], "123:VERY_SECRET")
            finally:
                api.shutdown()


if __name__ == "__main__":
    unittest.main()
