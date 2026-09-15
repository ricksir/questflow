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


class StudioV1IntelligenceReadTests(unittest.TestCase):
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

    def tearDown(self) -> None:
        self.api.shutdown()
        self.temp.cleanup()

    def test_contract_exposes_read_only_intelligence_operations(self) -> None:
        contract = self.api.get_studio_contract_v1()
        definitions = {item["name"]: item for item in contract["operations"]}

        expected_modules = {
            "editorial.bank.summary": "editorial_bank",
            "editorial.curation.attention": "editorial_bank",
            "knowledge.semantic.summary": "knowledge",
        }
        for operation, module in expected_modules.items():
            with self.subTest(operation=operation):
                self.assertIn(operation, definitions)
                self.assertEqual(definitions[operation]["module"], module)
                self.assertFalse(definitions[operation]["mutating"])

    def test_dispatcher_matches_existing_legacy_implementations(self) -> None:
        cases = (
            ("editorial.bank.summary", {}, self.api.get_bank_intelligence()),
            ("editorial.curation.attention", {"kind": "curation", "limit": 5}, self.api.get_curation_attention("curation", 5)),
            ("knowledge.semantic.summary", {}, self.api.get_semantic_index_summary()),
        )

        for operation, request_payload, legacy in cases:
            with self.subTest(operation=operation):
                studio = self.api.dispatch_studio_v1(operation, request_payload)
                self.assertTrue(studio["ok"])
                self.assertEqual(studio["contract"], "questflow.studio.v1")
                self.assertEqual(studio["operation"], operation)
                self.assertEqual(studio["data"], {key: value for key, value in legacy.items() if key != "ok"})

    def test_invalid_attention_limit_returns_validation_error(self) -> None:
        result = self.api.dispatch_studio_v1(
            "editorial.curation.attention",
            {"kind": "curation", "limit": "not-a-number"},
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["code"], "validation_error")
        self.assertEqual(result["status"], 400)
        self.assertTrue(result["error"])

    def test_authenticated_get_routes_return_versioned_payloads(self) -> None:
        server = QuestFlowLocalServer(
            self.api,
            Path(__file__).resolve().parents[1] / "web",
            preferred_port=0,
        )
        server.start()
        try:
            cases = (
                ("/api/v1/studio/editorial/bank/summary", "editorial.bank.summary"),
                (
                    "/api/v1/studio/editorial/curation/attention?"
                    + urllib.parse.urlencode({"kind": "curation", "limit": 5}),
                    "editorial.curation.attention",
                ),
                ("/api/v1/studio/knowledge/semantic/summary", "knowledge.semantic.summary"),
            )
            for path, operation in cases:
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
                    self.assertIsInstance(payload["data"], dict)
        finally:
            server.stop()

    def test_frontend_uses_studio_get_with_legacy_fallbacks(self) -> None:
        javascript = (Path(__file__).resolve().parents[1] / "web" / "app.js").read_text(encoding="utf-8")

        self.assertIn("bridge.studioGet('editorial/bank/summary', 'get_bank_intelligence')", javascript)
        self.assertIn("`editorial/curation/attention?${query.toString()}`", javascript)
        self.assertIn("'get_curation_attention'", javascript)
        self.assertIn("bridge.studioGet('knowledge/semantic/summary', 'get_semantic_index_summary')", javascript)
        for method in ("get_bank_intelligence", "get_curation_attention", "get_semantic_index_summary"):
            self.assertNotIn(f"bridge.call('{method}'", javascript)


if __name__ == "__main__":
    unittest.main()
