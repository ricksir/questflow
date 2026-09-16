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


class StudioV1ControlledGenerationReadTests(unittest.TestCase):
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
        draft = self.api.engines.governance.create_generation_draft(
            seed_question_uid=None,
            subject="Direito Tributário",
            topic="Crédito tributário",
            board_style="CEBRASPE",
            question_type="multipla_escolha",
            generator_model="modelo de teste",
            prompt_text="Gere uma questão de teste.",
            sources=[],
            error_profile={},
            draft={"codigo_origem": "QFLOW-TESTE"},
        )
        self.draft_id = str(draft["id"])

    def tearDown(self) -> None:
        self.api.shutdown()
        self.temp.cleanup()

    def test_contract_exposes_controlled_generation_reads_as_non_mutating(self) -> None:
        definitions = {
            item["name"]: item
            for item in self.api.get_studio_contract_v1()["operations"]
        }
        expected_modules = {
            "generation.workspace.get": "ai",
            "generation.drafts.get": "governance",
        }
        for operation, module in expected_modules.items():
            with self.subTest(operation=operation):
                self.assertEqual(definitions[operation]["module"], module)
                self.assertFalse(definitions[operation]["mutating"])

    def test_dispatcher_matches_existing_controlled_generation_facades(self) -> None:
        legacy_workspace = self.api.get_stage5_workspace("")
        studio_workspace = self.api.dispatch_studio_v1(
            "generation.workspace.get",
            {"uid": ""},
        )
        self.assertTrue(studio_workspace["ok"])
        self.assertEqual(
            studio_workspace["data"],
            {"workspace": legacy_workspace["workspace"]},
        )

        legacy_draft = self.api.get_generation_draft(self.draft_id)
        studio_draft = self.api.dispatch_studio_v1(
            "generation.drafts.get",
            {"draft_id": self.draft_id},
        )
        self.assertTrue(studio_draft["ok"])
        self.assertEqual(studio_draft["data"], {"draft": legacy_draft["draft"]})

    def test_missing_draft_id_returns_validation_error(self) -> None:
        result = self.api.dispatch_studio_v1("generation.drafts.get", {})

        self.assertFalse(result["ok"])
        self.assertEqual(result["code"], "validation_error")
        self.assertEqual(result["status"], 400)

    def test_authenticated_get_routes_return_controlled_generation_reads(self) -> None:
        server = QuestFlowLocalServer(
            self.api,
            Path(__file__).resolve().parents[1] / "web",
            preferred_port=0,
        )
        server.start()
        try:
            cases = (
                (
                    "/api/v1/studio/generation/workspace?"
                    + urllib.parse.urlencode({"uid": ""}),
                    "generation.workspace.get",
                    "workspace",
                ),
                (
                    "/api/v1/studio/generation/drafts/"
                    + urllib.parse.quote(self.draft_id),
                    "generation.drafts.get",
                    "draft",
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

        self.assertIn("`generation/workspace?${query.toString()}`", javascript)
        self.assertIn("'get_stage5_workspace'", javascript)
        self.assertIn("`generation/drafts/${encodeURIComponent(state.stage5DraftId)}`", javascript)
        self.assertIn("'get_generation_draft'", javascript)
        for method in ("get_stage5_workspace", "get_generation_draft"):
            self.assertNotIn(f"bridge.call('{method}'", javascript)


if __name__ == "__main__":
    unittest.main()
