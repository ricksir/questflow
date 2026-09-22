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


class StudioV1AiAuditReadTests(unittest.TestCase):
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
        assert self.api.database is not None
        uid = self.api.database.create_manual_question(None)
        assert self.api.engines is not None
        self.interaction_id = self.api.engines.governance.record_interaction(
            question_uid=uid,
            interaction_type="tutor",
            mode="professor",
            provider="teste local",
            model="modelo de teste",
            prompt_text="Explique a questão.",
            response_text="Resposta auditável.",
            learner_context={},
            sources=[],
            diagnosis={},
        )

    def tearDown(self) -> None:
        self.api.shutdown()
        self.temp.cleanup()

    def test_contract_exposes_ai_audit_reads_as_non_mutating(self) -> None:
        definitions = {
            item["name"]: item
            for item in self.api.get_studio_contract_v1()["operations"]
        }
        for operation in ("governance.ai.audit.list", "governance.ai.interactions.get"):
            with self.subTest(operation=operation):
                self.assertEqual(definitions[operation]["module"], "governance")
                self.assertFalse(definitions[operation]["mutating"])
        self.assertEqual(definitions["governance.ai.interactions.review"]["module"], "governance")
        self.assertTrue(definitions["governance.ai.interactions.review"]["mutating"])

    def test_dispatcher_matches_existing_governance_facades(self) -> None:
        legacy_audit = self.api.get_ai_audit(10)
        studio_audit = self.api.dispatch_studio_v1("governance.ai.audit.list", {"limit": 10})
        self.assertTrue(studio_audit["ok"])
        self.assertEqual(
            studio_audit["data"],
            {"summary": legacy_audit["summary"], "items": legacy_audit["items"]},
        )

        legacy_interaction = self.api.get_ai_interaction(self.interaction_id)
        studio_interaction = self.api.dispatch_studio_v1(
            "governance.ai.interactions.get",
            {"interaction_id": self.interaction_id},
        )
        self.assertTrue(studio_interaction["ok"])
        self.assertEqual(
            studio_interaction["data"],
            {"interaction": legacy_interaction["interaction"]},
        )

    def test_missing_interaction_returns_validation_error(self) -> None:
        for operation in ("governance.ai.interactions.get", "governance.ai.interactions.review"):
            with self.subTest(operation=operation):
                result = self.api.dispatch_studio_v1(operation, {})
                self.assertFalse(result["ok"])
                self.assertEqual(result["code"], "validation_error")
                self.assertEqual(result["status"], 400)

    def test_dispatcher_reviews_ai_interaction(self) -> None:
        result = self.api.dispatch_studio_v1(
            "governance.ai.interactions.review",
            {"interaction_id": self.interaction_id, "decision": "aprovar", "note": "Revisão Studio v1."},
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["data"]["review"]["status"], "aprovado")

    def test_authenticated_get_routes_return_ai_audit_payloads(self) -> None:
        server = QuestFlowLocalServer(
            self.api,
            Path(__file__).resolve().parents[1] / "web",
            preferred_port=0,
        )
        server.start()
        try:
            cases = (
                (
                    "/api/v1/studio/governance/ai/audit?"
                    + urllib.parse.urlencode({"limit": 10}),
                    "governance.ai.audit.list",
                ),
                (
                    "/api/v1/studio/governance/ai/interactions/"
                    + urllib.parse.quote(self.interaction_id),
                    "governance.ai.interactions.get",
                ),
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

            review_request = urllib.request.Request(
                f"{server.base_url}/api/v1/studio/governance/ai/interactions/"
                f"{urllib.parse.quote(self.interaction_id)}/review",
                data=json.dumps({"decision": "rejeitar", "note": "Revisão HTTP."}).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "X-QuestFlow-Token": server.token,
                },
                method="POST",
            )
            with urllib.request.urlopen(review_request, timeout=5) as response:
                review = json.loads(response.read().decode("utf-8"))
            self.assertTrue(review["ok"])
            self.assertEqual(review["operation"], "governance.ai.interactions.review")
            self.assertEqual(review["data"]["review"]["status"], "rejeitado")
        finally:
            server.stop()

    def test_frontend_uses_studio_get_with_legacy_fallbacks(self) -> None:
        javascript = (Path(__file__).resolve().parents[1] / "web" / "app.js").read_text(encoding="utf-8")

        self.assertIn("bridge.studioGet('governance/ai/audit?limit=30', 'get_ai_audit', [30])", javascript)
        self.assertIn("`governance/ai/interactions/${encodeURIComponent(interactionId)}`", javascript)
        self.assertIn("'get_ai_interaction'", javascript)
        self.assertIn("`governance/ai/interactions/${encodeURIComponent(state.tutorInteractionId)}/review`", javascript)
        for method in ("get_ai_audit", "get_ai_interaction", "review_ai_interaction"):
            self.assertNotIn(f"bridge.call('{method}'", javascript)


if __name__ == "__main__":
    unittest.main()
