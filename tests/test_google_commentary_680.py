from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from core.enrichment import _SEARCH_DIRECTIVE, build_search_queries, enrich_question, parse_google_search_page
from core.engines import EngineRegistry
from core.question_services import QuestionCommandService, QuestionQueryService
from core.storage import QuestFlowDatabase
from core.study import StudyRepository


class GoogleCommentary680Tests(unittest.TestCase):
    @staticmethod
    def question() -> dict:
        return {
            "codigo_origem": "Q680001",
            "enunciado": "A imunidade tributária constitui limitação constitucional ao poder de tributar.",
            "banca": "CEBRASPE",
            "ano": 2026,
            "gabarito": "C",
        }

    def test_installer_diagnostic_tracks_current_answer_oriented_directive(self) -> None:
        queries = build_search_queries(self.question())
        self.assertGreaterEqual(len(queries), 2)
        self.assertIn(_SEARCH_DIRECTIVE, queries[0])
        self.assertTrue(queries[0].startswith('"Q680001"'))
        normalized = queries[0].casefold()
        for term in ("gabarito", "justificativa", "sem repetir enunciado"):
            self.assertIn(term, normalized)
        self.assertNotIn("Q680001", queries[1])

    def test_parser_keeps_only_answer_explanation_and_discards_google_noise(self) -> None:
        page = """
        Modo IA
        Q680001
        Informações da Questão
        Ano: 2026
        Banca: CEBRASPE
        Enunciado da Questão
        A imunidade tributária constitui limitação constitucional ao poder de tributar.
        Alternativas
        C) Certo
        E) Errado
        Gabarito: CERTO
        Justificativa
        A assertiva está correta porque a imunidade atua como limitação constitucional da competência tributária, impedindo a incidência nos casos protegidos pela Constituição.
        Fontes
        Saiba mais
        Pesquisas relacionadas
        outra coisa que não pertence à resposta
        """
        candidate = parse_google_search_page(page, "<html></html>", self.question(), search_url="https://www.google.com/ai")
        self.assertTrue(candidate["verified"])
        self.assertGreaterEqual(candidate["explanation_confidence"], 0.62)
        self.assertEqual(candidate["explanation_method"], "heading_explicit")
        explanation = candidate["justificativa"]
        self.assertIn("limitação constitucional", explanation)
        self.assertNotIn("Informações da Questão", explanation)
        self.assertNotIn("Banca:", explanation)
        self.assertNotIn("Pesquisas relacionadas", explanation)
        self.assertNotIn("outra coisa", explanation)

    def test_verified_page_without_commentary_uses_statement_fallback(self) -> None:
        calls = []
        code_page = """
        Q680001
        Informações da Questão
        Ano: 2026
        Banca: CEBRASPE
        Enunciado
        A imunidade tributária constitui limitação constitucional ao poder de tributar.
        Gabarito: CERTO
        """
        statement_page = """
        Q680001
        Informações da Questão
        Ano: 2026
        Banca: CEBRASPE
        Enunciado
        A imunidade tributária constitui limitação constitucional ao poder de tributar.
        Gabarito: CERTO
        Explicação
        A assertiva está correta porque a imunidade limita constitucionalmente a competência dos entes tributantes.
        """

        def fake_visible(query: str, **kwargs):
            calls.append(query)
            text = code_page if query.startswith('"Q680001"') else statement_page
            return {
                "query": query, "search_url": "https://www.google.com/ai", "browser": "Chrome",
                "search_text": text, "search_html": "<html></html>", "blocked": False,
                "ai_mode_activated": True, "ai_answer_stable": True, "google_answer_expanded": True,
                "google_expand_clicks": 0, "google_expand_labels": [], "google_expand_errors": [],
            }

        with patch("core.enrichment.run_visible_google_ai_search", side_effect=fake_visible):
            result = enrich_question(self.question(), max_results=10)
        self.assertGreaterEqual(len(calls), 2)
        self.assertTrue(result["justification_confirmed"])
        self.assertEqual(result["search_stage_used"], "enunciado")
        self.assertIn("limita constitucionalmente", result["structured_question"]["explicacao"])

    def test_unstable_capture_is_retried_once_before_giving_up(self) -> None:
        calls = []
        stable_page = """
        Q680001
        Ano: 2026
        Banca: CEBRASPE
        Enunciado
        A imunidade tributária constitui limitação constitucional ao poder de tributar.
        Gabarito: CERTO
        Justificativa
        A assertiva está correta porque a Constituição limita a competência tributária por meio da imunidade.
        """

        def fake_visible(query: str, **kwargs):
            calls.append(query)
            if len(calls) == 1:
                return {"query": query, "search_url": "https://www.google.com/ai", "browser": "Chrome", "search_text": "carregando", "search_html": "", "blocked": False, "ai_mode_activated": True, "ai_answer_stable": False, "google_expand_errors": []}
            return {"query": query, "search_url": "https://www.google.com/ai", "browser": "Chrome", "search_text": stable_page, "search_html": "<html></html>", "blocked": False, "ai_mode_activated": True, "ai_answer_stable": True, "google_answer_expanded": True, "google_expand_clicks": 0, "google_expand_labels": [], "google_expand_errors": []}

        with patch("core.enrichment.run_visible_google_ai_search", side_effect=fake_visible):
            result = enrich_question(self.question(), max_results=10)
        self.assertEqual(len(calls), 2)
        self.assertTrue(result["justification_confirmed"])
        self.assertEqual(result["search_stages"][0]["capture_retries"], 1)

    def test_ai_engine_never_uses_full_google_overview_as_commentary(self) -> None:
        with tempfile.TemporaryDirectory(prefix="qf-680-no-overview-") as tmp:
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
            noisy = {
                "structured_question": {"gabarito": "C"},
                "best_candidate": {"verified": True, "google_overview_text": "Informações da questão Banca Ano Enunciado menu menu menu"},
                "verified_match": True, "confidence": 0.95, "errors": [],
            }
            with patch("core.enrichment.enrich_question", return_value=noisy):
                with self.assertRaisesRegex(ValueError, "recusou preencher"):
                    engines.ai.research_google_commentary(uid)


if __name__ == "__main__":
    unittest.main()
