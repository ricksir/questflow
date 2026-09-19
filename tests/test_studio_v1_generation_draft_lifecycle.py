from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
import urllib.parse
import urllib.request
from pathlib import Path

from app_shared import TAXONOMY_PATH
from web_api import QuestFlowWebApi
from web_server import QuestFlowLocalServer


class StudioV1GenerationDraftLifecycleTests(unittest.TestCase):
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
        assert self.api.commands is not None and self.api.queries is not None
        question = {
            "id": "SRC-STUDIO-V1-GENERATION",
            "codigo_origem": "SRC-STUDIO-V1-GENERATION",
            "fingerprint": hashlib.sha256(b"SRC-STUDIO-V1-GENERATION").hexdigest(),
            "materia": "Direito Tributário",
            "assunto": "Suspensão da exigibilidade",
            "assuntos": ["Suspensão da exigibilidade"],
            "banca": "CEBRASPE",
            "ano": 2026,
            "orgao": "Órgão de teste",
            "prova": "Prova de teste",
            "tipo": "Múltipla escolha",
            "enunciado": "Considere as regras sobre suspensão da exigibilidade do crédito tributário.",
            "alternativas": [
                {"chave": "A", "texto": "A moratória suspende a exigibilidade do crédito tributário."},
                {"chave": "B", "texto": "A moratória sempre extingue o crédito tributário."},
                {"chave": "C", "texto": "A suspensão elimina a obrigação principal."},
                {"chave": "D", "texto": "A suspensão converte o crédito em obrigação natural."},
                {"chave": "E", "texto": "A suspensão impede qualquer lançamento futuro."},
            ],
            "gabarito": "A",
            "explicacao": (
                "A moratória é hipótese legal de suspensão da exigibilidade do crédito tributário. "
                "A suspensão não extingue o crédito e impede temporariamente sua exigência."
            ),
            "fonte": {"arquivo": "studio_v1_generation.pdf", "pagina_inicial": 1},
            "proveniencia": {"tipo": "oficial", "verificada": True},
            "revisao": {"status": "aprovado", "confianca": 1.0},
        }
        imported = self.api.commands.import_extraction({
            "source_file": "studio_v1_generation.pdf",
            "questions": [question],
        })
        self.assertEqual(imported["inserted"], 1)
        saved = self.api.queries.by_code(question["codigo_origem"])
        assert saved is not None and self.api.engines is not None
        self.source_uid = str(saved["database_uid"])
        retrieval = self.api.engines.knowledge.retrieve(self.source_uid, "", limit=8)
        self.source_chunk_ids = [str(item["id"]) for item in retrieval["items"]]
        self.assertTrue(self.source_chunk_ids)

    def tearDown(self) -> None:
        self.api.shutdown()
        self.temp.cleanup()

    def _generation_payload(self) -> dict:
        return {
            "seed_uid": self.source_uid,
            "source_chunk_ids": self.source_chunk_ids[:1],
            "question_type": "multipla_escolha",
            "board_style": "CEBRASPE",
            "subject": "Direito Tributário",
            "topic": "Suspensão da exigibilidade",
            "exam_date": "2026-08-13",
        }

    def _create_draft(self) -> dict:
        result = self.api.dispatch_studio_v1("generation.drafts.create", self._generation_payload())
        self.assertTrue(result["ok"])
        return result["data"]["draft"]

    def test_contract_exposes_lifecycle_operations_as_mutating(self) -> None:
        definitions = {
            item["name"]: item
            for item in self.api.get_studio_contract_v1()["operations"]
        }
        expected_modules = {
            "generation.drafts.create": "ai",
            "generation.drafts.review": "governance",
            "generation.drafts.publish": "ai",
        }
        for operation, module in expected_modules.items():
            with self.subTest(operation=operation):
                self.assertEqual(definitions[operation]["module"], module)
                self.assertTrue(definitions[operation]["mutating"])

    def test_dispatcher_runs_create_review_and_publish_lifecycle(self) -> None:
        draft = self._create_draft()
        draft_id = str(draft["id"])
        self.assertIsNone(draft["published_question_uid"])
        self.assertEqual(self.api.get_generation_draft(draft_id)["draft"], draft)

        reviewed = self.api.dispatch_studio_v1(
            "generation.drafts.review",
            {"draft_id": draft_id, "decision": "aprovar", "note": "Revisão humana de teste."},
        )
        self.assertTrue(reviewed["ok"])
        self.assertEqual(reviewed["data"]["draft"]["status"], "aprovado")

        published = self.api.dispatch_studio_v1(
            "generation.drafts.publish",
            {"draft_id": draft_id},
        )
        self.assertTrue(published["ok"])
        self.assertEqual(published["data"]["draft"]["status"], "publicado")
        code = published["data"]["published"]["question"]["codigo_origem"]
        assert self.api.queries is not None
        self.assertIsNotNone(self.api.queries.by_code(code))

    def test_lifecycle_validation_errors_use_studio_contract(self) -> None:
        cases = (
            ("generation.drafts.create", {}),
            ("generation.drafts.review", {"decision": "aprovar"}),
            ("generation.drafts.publish", {}),
        )
        for operation, payload in cases:
            with self.subTest(operation=operation):
                result = self.api.dispatch_studio_v1(operation, payload)
                self.assertFalse(result["ok"])
                self.assertEqual(result["code"], "validation_error")
                self.assertEqual(result["status"], 400)

    def test_authenticated_routes_run_full_lifecycle(self) -> None:
        server = QuestFlowLocalServer(
            self.api,
            Path(__file__).resolve().parents[1] / "web",
            preferred_port=0,
        )
        server.start()
        try:
            def post(path: str, payload: dict) -> dict:
                request = urllib.request.Request(
                    f"{server.base_url}{path}",
                    data=json.dumps(payload).encode("utf-8"),
                    headers={
                        "Content-Type": "application/json",
                        "X-QuestFlow-Token": server.token,
                    },
                    method="POST",
                )
                with urllib.request.urlopen(request, timeout=10) as response:
                    return json.loads(response.read().decode("utf-8"))

            created = post("/api/v1/studio/generation/drafts", self._generation_payload())
            self.assertTrue(created["ok"])
            self.assertEqual(created["operation"], "generation.drafts.create")
            draft_id = str(created["data"]["draft"]["id"])
            encoded_id = urllib.parse.quote(draft_id)

            reviewed = post(
                f"/api/v1/studio/generation/drafts/{encoded_id}/review",
                {"decision": "aprovar", "note": "Revisão HTTP de teste."},
            )
            self.assertTrue(reviewed["ok"])
            self.assertEqual(reviewed["operation"], "generation.drafts.review")

            published = post(
                f"/api/v1/studio/generation/drafts/{encoded_id}/publish",
                {},
            )
            self.assertTrue(published["ok"])
            self.assertEqual(published["operation"], "generation.drafts.publish")
            self.assertEqual(published["contract"], "questflow.studio.v1")
            self.assertEqual(published["data"]["draft"]["status"], "publicado")
        finally:
            server.stop()

    def test_frontend_uses_studio_post_with_legacy_fallbacks(self) -> None:
        javascript = (Path(__file__).resolve().parents[1] / "web" / "app.js").read_text(encoding="utf-8")

        self.assertIn("'generation/drafts'", javascript)
        self.assertIn("`generation/drafts/${encodeURIComponent(state.stage5DraftId)}/review`", javascript)
        self.assertIn("`generation/drafts/${encodeURIComponent(state.stage5DraftId)}/publish`", javascript)
        for method in (
            "generate_controlled_question",
            "review_generation_draft",
            "publish_generation_draft",
        ):
            self.assertIn(f"'{method}'", javascript)
            self.assertNotIn(f"bridge.call('{method}'", javascript)


if __name__ == "__main__":
    unittest.main()
