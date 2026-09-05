from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import app_shared
from core.engines import EngineRegistry
from core.question_services import QuestionCommandService, QuestionQueryService
from core.storage import QuestFlowDatabase
from core.study import StudyRepository
from web_server import ALLOWED_API_METHODS

BASE = Path(__file__).resolve().parents[1]


class GoogleCommentary672Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="qf-google-comment-672-")
        self.db = QuestFlowDatabase(Path(self.tmp.name) / "q.sqlite")
        self.study = StudyRepository(self.db)
        self.queries = QuestionQueryService(self.db)
        self.commands = QuestionCommandService(self.db)
        self.engines = EngineRegistry.build(
            database=self.db,
            queries=self.queries,
            commands=self.commands,
            study=self.study,
        )
        self.engines.ai.api = SimpleNamespace(config={"ai_privacy_mode": "balanced"})

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def make_question(self, *, explanation: str = "") -> str:
        uid = self.db.create_manual_question(None)
        question = self.db.get_question(uid); assert question
        question.update({
            "codigo_origem": "Q672-GOOGLE",
            "id": "Q672-GOOGLE",
            "materia": "DIREITO TRIBUTÁRIO",
            "aula_planilha": "Aula 02",
            "assunto": "Imunidade tributária",
            "enunciado": "A imunidade tributária:",
            "alternativas": [
                {"chave": "A", "texto": "é benefício fiscal revogável por decreto."},
                {"chave": "B", "texto": "decorre apenas de lei ordinária."},
                {"chave": "C", "texto": "constitui limitação constitucional ao poder de tributar."},
            ],
            "gabarito": "C",
            "explicacao": explanation,
            "banca": "CEBRASPE",
            "ano": 2026,
            "revisao": {"status": "aprovado", "confianca": 1.0, "alertas": []},
        })
        self.db.update_question(uid, question)
        return uid

    @staticmethod
    def google_result() -> dict:
        return {
            "structured_question": {
                "gabarito": "C",
                "explicacao": "A imunidade é limitação constitucional ao poder de tributar e atua no plano da competência tributária.",
            },
            "best_candidate": {
                "verified": True,
                "justificativa": "A imunidade é limitação constitucional ao poder de tributar e atua no plano da competência tributária.",
                "google_overview_text": "A imunidade tributária limita constitucionalmente a competência de tributar.",
            },
            "results": [
                {
                    "title": "Resposta exibida no Modo IA do Google",
                    "url": "https://www.google.com/search?q=Q672-GOOGLE",
                    "snippet": "A imunidade tributária é uma limitação constitucional ao poder de tributar.",
                    "score": 0.96,
                    "provider": "Google Modo IA",
                }
            ],
            "confidence": 0.96,
            "verified_match": True,
            "justification_source_url": "https://www.google.com/search?q=Q672-GOOGLE",
            "answer_source_url": "https://www.google.com/search?q=Q672-GOOGLE",
            "verified_source_url": "https://www.google.com/search?q=Q672-GOOGLE",
            "errors": [],
            "search_mode": "google_modo_ia_pagina_renderizada",
        }

    def test_google_research_returns_explanation_without_persisting_it(self) -> None:
        uid = self.make_question(explanation="")
        with patch("core.enrichment.enrich_question", return_value=self.google_result()):
            result = self.engines.ai.research_google_commentary(uid)
        self.assertTrue(result["ok"])
        self.assertEqual(result["provider"], "Google Modo IA")
        self.assertEqual(result["commentary_source"], "ia_assistida")
        self.assertTrue(result["verified_match"])
        self.assertTrue(result["explanation"].startswith("Gabarito: C."))
        self.assertIn("limitação constitucional", result["explanation"])
        # A função só devolve o rascunho; a persistência continua dependendo do usuário no editor.
        stored = self.db.get_question(uid); assert stored
        self.assertEqual(str(stored.get("explicacao") or ""), "")
        audit = self.engines.governance.interaction(result["interaction_id"])
        self.assertEqual(audit["interaction_type"], "google_commentary_research")
        self.assertEqual(audit["status"], "rascunho")

    def test_google_research_uses_unsaved_editor_draft_as_search_context(self) -> None:
        uid = self.make_question()
        captured = {}

        def fake_enrich(question: dict, *, max_results: int = 12) -> dict:
            captured.update(question)
            return self.google_result()

        with patch("core.enrichment.enrich_question", side_effect=fake_enrich):
            result = self.engines.ai.research_google_commentary(
                uid,
                question_override={
                    "codigo_origem": "Q672-EDITADO",
                    "enunciado": "Enunciado corrigido ainda não salvo.",
                    "gabarito": "C",
                    "alternativas": [{"chave": "C", "texto": "correta"}, {"chave": "E", "texto": "errada"}],
                    "materia": "DIREITO TRIBUTÁRIO",
                    "assunto": "Imunidade tributária",
                },
            )
        self.assertTrue(result["ok"])
        self.assertEqual(captured.get("codigo_origem"), "Q672-EDITADO")
        self.assertEqual(captured.get("enunciado"), "Enunciado corrigido ainda não salvo.")

    def test_google_research_never_overwrites_local_answer_on_disagreement(self) -> None:
        uid = self.make_question()
        result_data = self.google_result()
        result_data["structured_question"]["gabarito"] = "A"
        with patch("core.enrichment.enrich_question", return_value=result_data):
            result = self.engines.ai.research_google_commentary(uid)
        self.assertEqual(result["official_answer"], "C")
        self.assertEqual(result["suggested_answer"], "A")
        self.assertTrue(any("diferente do gabarito C" in item for item in result["warnings"]))
        stored = self.db.get_question(uid); assert stored
        self.assertEqual(stored.get("gabarito"), "C")

    def test_private_mode_blocks_google_research(self) -> None:
        uid = self.make_question()
        self.engines.ai.api = SimpleNamespace(config={"ai_privacy_mode": "private"})
        with self.assertRaisesRegex(ValueError, "modo Privado"):
            self.engines.ai.research_google_commentary(uid)

    def test_no_verified_explanation_is_not_silently_filled(self) -> None:
        uid = self.make_question()
        empty = {
            "structured_question": {}, "best_candidate": {}, "results": [], "confidence": 0,
            "verified_match": False, "errors": ["Nenhuma resposta verificável"],
        }
        with patch("core.enrichment.enrich_question", return_value=empty):
            with self.assertRaisesRegex(ValueError, "não retornou uma explicação verificável"):
                self.engines.ai.research_google_commentary(uid)

    def test_version_allowlist_and_editor_are_wired(self) -> None:
        self.assertEqual(app_shared.APP_VERSION, "6.24.0")
        self.assertIn("start_google_commentary_research", ALLOWED_API_METHODS)
        html = (BASE / "web" / "index.html").read_text(encoding="utf-8")
        js = (BASE / "web" / "app.js").read_text(encoding="utf-8")
        self.assertIn('id="researchGoogleCommentary"', html)
        self.assertIn("Pesquisar resposta no Google com IA", html)
        self.assertIn("bridge.call('start_google_commentary_research'", js)
        self.assertIn("sourceField.value = 'ia_assistida'", js)
        self.assertIn("researchGoogleCommentary", js)


if __name__ == "__main__":
    unittest.main()

class LocalHttpGoogleCommentary672Tests(unittest.TestCase):
    def test_google_research_method_is_reachable_over_real_local_http(self) -> None:
        import json
        import urllib.request
        from web_server import QuestFlowLocalServer

        class DummyApi:
            def start_google_commentary_research(self, uid="", question_draft=None):
                return {"ok": True, "task_id": "google-task", "uid": uid, "draft": question_draft or {}}

        server = QuestFlowLocalServer(DummyApi(), BASE / "web", preferred_port=0)
        server.start()
        try:
            payload = json.dumps({
                "method": "start_google_commentary_research",
                "args": ["uid-1", {"codigo_origem": "Q123", "enunciado": "Texto atual"}],
            }).encode("utf-8")
            request = urllib.request.Request(
                server.base_url + "/api/call",
                data=payload,
                headers={"Content-Type": "application/json", "X-QuestFlow-Token": server.token},
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=3) as response:
                body = json.loads(response.read().decode("utf-8"))
            self.assertEqual(response.status, 200)
            self.assertTrue(body["ok"])
            self.assertTrue(body["result"]["ok"])
            self.assertEqual(body["result"]["draft"]["codigo_origem"], "Q123")
        finally:
            server.stop()
