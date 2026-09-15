from __future__ import annotations

import json
import tempfile
import unittest
import urllib.parse
import urllib.request
from pathlib import Path

from app_shared import TAXONOMY_PATH
from web_api import QuestFlowWebApi
from web_server import QuestFlowLocalServer


class StudioV1GovernanceDashboardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.api = QuestFlowWebApi(
            self.root / "questflow.sqlite",
            config={},
            config_path=self.root / "config.json",
            taxonomy_path=TAXONOMY_PATH,
        )
        self.api.bootstrap()
        assert self.api.engines is not None
        self.api.engines.governance.record_provider_metric(
            provider="provedor de teste",
            model="modelo de teste",
            operation="tutor",
            status="ok",
            latency_ms=120,
            usage={"input_tokens": 100, "output_tokens": 20},
            structured_output=True,
        )

    def tearDown(self) -> None:
        self.api.shutdown()
        self.temp.cleanup()

    def test_contract_exposes_governance_dashboards_as_non_mutating(self) -> None:
        definitions = {
            item["name"]: item
            for item in self.api.get_studio_contract_v1()["operations"]
        }
        for operation in ("governance.gold.dashboard", "governance.ai.telemetry"):
            with self.subTest(operation=operation):
                self.assertEqual(definitions[operation]["module"], "governance")
                self.assertFalse(definitions[operation]["mutating"])

    def test_dispatcher_matches_existing_governance_facades(self) -> None:
        legacy_gold = self.api.get_gold_dashboard()
        studio_gold = self.api.dispatch_studio_v1("governance.gold.dashboard", {})
        self.assertTrue(studio_gold["ok"])
        self.assertEqual(
            studio_gold["data"],
            {"summary": legacy_gold["summary"], "items": legacy_gold["items"]},
        )

        legacy_telemetry = self.api.get_ai_telemetry(14)
        studio_telemetry = self.api.dispatch_studio_v1(
            "governance.ai.telemetry",
            {"days": 14},
        )
        self.assertTrue(studio_telemetry["ok"])
        self.assertEqual(
            studio_telemetry["data"],
            {"telemetry": legacy_telemetry["telemetry"]},
        )
        self.assertEqual(studio_telemetry["data"]["telemetry"]["calls"], 1)

    def test_authenticated_get_routes_return_governance_dashboards(self) -> None:
        server = QuestFlowLocalServer(
            self.api,
            Path(__file__).resolve().parents[1] / "web",
            preferred_port=0,
        )
        server.start()
        try:
            cases = (
                (
                    "/api/v1/studio/governance/gold/dashboard",
                    "governance.gold.dashboard",
                    "summary",
                ),
                (
                    "/api/v1/studio/governance/ai/telemetry?"
                    + urllib.parse.urlencode({"days": 14}),
                    "governance.ai.telemetry",
                    "telemetry",
                ),
            )
            for path, operation, data_key in cases:
                with self.subTest(operation=operation):
                    request = urllib.request.Request(
                        f"{server.base_url}{path}",
                        headers={"X-QuestFlow-Token": server.token},
                    )
                    with urllib.request.urlopen(request, timeout=5) as response:
                        payload = json.loads(response.read().decode("utf-8"))
                    self.assertTrue(payload["ok"])
                    self.assertEqual(payload["contract"], "questflow.studio.v1")
                    self.assertEqual(payload["operation"], operation)
                    self.assertIn(data_key, payload["data"])
        finally:
            server.stop()

    def test_frontend_uses_studio_get_with_legacy_fallbacks(self) -> None:
        javascript = (Path(__file__).resolve().parents[1] / "web" / "app.js").read_text(encoding="utf-8")

        gold_call = "bridge.studioGet('governance/gold/dashboard', 'get_gold_dashboard')"
        self.assertEqual(javascript.count(gold_call), 3)
        self.assertIn(
            "bridge.studioGet('governance/ai/telemetry?days=30','get_ai_telemetry',[30])",
            javascript,
        )
        for method in ("get_gold_dashboard", "get_ai_telemetry"):
            self.assertNotIn(f"bridge.call('{method}'", javascript)


if __name__ == "__main__":
    unittest.main()
