from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from core.enrichment import enrich_question
from core.engines import EngineRegistry
from core.question_services import QuestionCommandService, QuestionQueryService
from core.storage import QuestFlowDatabase
from core.study import StudyRepository


class GoogleCommentaryHotfix3Tests(unittest.TestCase):
    @staticmethod
    def question() -> dict:
        return {
            "codigo_origem": "Q1040341",
            "enunciado": "Os investidores existentes e potenciais estão entre os usuários primários dos relatórios financeiros de propósito geral.",
            "banca": "CEBRASPE",
            "ano": 2019,
            "gabarito": "C",
        }

    def test_exact_code_query_accepts_clean_ai_answer_without_repeating_metadata(self) -> None:
        page = (
            "A alternativa correta é C. Isso porque investidores existentes e potenciais, "
            "credores por empréstimos e outros credores são usuários primários dos relatórios "
            "financeiros de propósito geral, conforme a Estrutura Conceitual."
        )
        def fake_visible(query: str, **kwargs):
            return {
                "query": query,
                "search_url": "https://www.google.com/search?q=Q1040341&udm=50",
                "browser": "Chrome",
                "search_text": page,
                "search_html": "<html></html>",
                "blocked": False,
                "ai_mode_activated": True,
                "ai_answer_stable": True,
                "google_answer_expanded": True,
                "google_expand_clicks": 0,
                "google_expand_labels": [],
                "google_expand_errors": [],
            }
        with patch("core.enrichment.run_visible_google_ai_search", side_effect=fake_visible):
            result = enrich_question(self.question(), max_results=6)
        self.assertTrue(result["verified_match"])
        self.assertTrue(result["justification_confirmed"])
        self.assertEqual(result["search_stage_used"], "codigo")
        explanation = result["structured_question"]["explicacao"]
        self.assertIn("investidores existentes", explanation)
        self.assertNotIn("Q1040341", explanation)
        self.assertNotIn("Banca", explanation)

    def test_inline_justification_after_gabarito_is_not_lost(self) -> None:
        page = (
            "Gabarito: C. Isso porque a Estrutura Conceitual identifica investidores existentes "
            "e potenciais e credores como usuários primários dos relatórios de propósito geral."
        )
        def fake_visible(query: str, **kwargs):
            return {
                "query": query, "search_url": "https://www.google.com/ai", "browser": "Chrome",
                "search_text": page, "search_html": "<html></html>", "blocked": False,
                "ai_mode_activated": True, "ai_answer_stable": True, "google_answer_expanded": True,
                "google_expand_clicks": 0, "google_expand_labels": [], "google_expand_errors": [],
            }
        with patch("core.enrichment.run_visible_google_ai_search", side_effect=fake_visible):
            result = enrich_question(self.question(), max_results=6)
        self.assertTrue(result["justification_confirmed"])
        self.assertIn("Estrutura Conceitual", result["structured_question"]["explicacao"])

    def test_low_confidence_verified_commentary_is_filled_with_warning_instead_of_discarded(self) -> None:
        with tempfile.TemporaryDirectory(prefix="qf-680-hf3-") as tmp:
            db = QuestFlowDatabase(Path(tmp) / "q.sqlite")
            study = StudyRepository(db)
            queries = QuestionQueryService(db)
            commands = QuestionCommandService(db)
            engines = EngineRegistry.build(database=db, queries=queries, commands=commands, study=study)
            engines.ai.api = SimpleNamespace(config={"ai_privacy_mode": "balanced"})
            uid = db.create_manual_question(None)
            q = db.get_question(uid); assert q
            q.update(self.question())
            db.update_question(uid, q)
            enrichment = {
                "structured_question": {
                    "gabarito": "C",
                    "explicacao": "A alternativa está correta porque os usuários primários incluem investidores e credores interessados na informação financeira de propósito geral.",
                },
                "best_candidate": {"verified": True, "score": 0.78},
                "verified_match": True,
                "confidence": 0.78,
                "explanation_confidence": 0.34,
                "explanation_method": "semantic_sentence",
                "noise_removed": 5,
                "errors": [],
                "results": [],
                "search_mode": "google_modo_ia_pagina_renderizada",
            }
            with patch("core.enrichment.enrich_question", return_value=enrichment):
                result = engines.ai.research_google_commentary(uid)
            self.assertTrue(result["ok"])
            self.assertIn("usuários primários", result["explanation"])
            self.assertTrue(any("34%" in warning for warning in result["warnings"]))

    def test_editor_groups_google_action_and_shortens_review_buttons(self) -> None:
        root = Path(__file__).resolve().parents[1]
        html = (root / "web" / "index.html").read_text(encoding="utf-8")
        js = (root / "web" / "app.js").read_text(encoding="utf-8")
        css = (root / "web" / "styles.css").read_text(encoding="utf-8")
        self.assertIn('class="explanation-ai-bar"', html)
        self.assertIn('Status da revisão', html)
        self.assertIn('Ações', html)
        self.assertIn("approveButton.textContent = 'Concluir revisão';", js)
        self.assertIn("saveButton.textContent = 'Salvar rascunho';", js)
        self.assertIn('.editor-action-buttons #approveQuestion', css)


if __name__ == "__main__":
    unittest.main()
