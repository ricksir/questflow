from __future__ import annotations

import unittest
from unittest.mock import patch

from core.google_browser import _wait_for_ai_answer
from core.enrichment import enrich_question


class _Clock:
    def __init__(self):
        self.value = 0.0
    def time(self):
        return self.value
    def sleep(self, seconds):
        self.value += float(seconds)


class GoogleCommentaryHotfix2Tests(unittest.TestCase):
    @staticmethod
    def question() -> dict:
        return {
            "codigo_origem": "Q1040341",
            "enunciado": (
                "Segundo o Comitê de Pronunciamentos Contábeis, os relatórios "
                "contábeis-financeiros objetivam fornecer informações úteis aos usuários em geral."
            ),
            "banca": "CEBRASPE",
            "ano": 2019,
            "gabarito": "E",
        }

    def test_focused_answer_can_finish_without_echoing_question_code(self) -> None:
        clock = _Clock()
        focused = {
            "text": (
                "Gabarito: E\nJustificativa: a Estrutura Conceitual prioriza investidores "
                "existentes e potenciais, credores por empréstimos e outros credores."
            ),
            "method": "semantic_dom_block",
            "score": 12.0,
            "candidate_count": 1,
        }
        with patch("core.google_browser._captcha_present", return_value=False), patch(
            "core.google_browser._visible_ai_answer_snapshot", return_value=focused
        ):
            result = _wait_for_ai_answer(
                object(),
                '"Q1040341" qual é o gabarito e a justificativa desta questão? Responda somente com o gabarito e a explicação, sem repetir enunciado.',
                wait_seconds=10,
                sleep_func=clock.sleep,
                time_func=clock.time,
            )
        self.assertTrue(result["stable"])
        self.assertEqual(result["ready_reason"], "focused_answer_stable")
        self.assertIn("Gabarito: E", result["text"])
        self.assertNotIn("Q1040341", result["text"])
        self.assertGreaterEqual(result["elapsed_seconds"], 5)
        self.assertLess(result["elapsed_seconds"], 8)

    def test_useful_first_capture_is_not_researched_only_because_stability_flag_is_false(self) -> None:
        calls = []
        page = """
        Q1040341
        Ano: 2019
        Banca: CEBRASPE
        Enunciado
        Segundo o Comitê de Pronunciamentos Contábeis, os relatórios contábeis-financeiros objetivam fornecer informações úteis aos usuários em geral.
        Gabarito: E
        Justificativa
        A alternativa E é correta porque os relatórios de propósito geral atendem especialmente às necessidades de investidores existentes e potenciais e demais provedores de capital.
        """
        def fake_visible(query: str, **kwargs):
            calls.append(query)
            return {
                "query": query,
                "search_url": "https://www.google.com/ai",
                "browser": "Chrome",
                "search_text": page,
                "search_html": "<html></html>",
                "blocked": False,
                "ai_mode_activated": True,
                "ai_answer_stable": False,
                "google_answer_expanded": True,
                "google_expand_clicks": 0,
                "google_expand_labels": [],
                "google_expand_errors": [],
            }
        with patch("core.enrichment.run_visible_google_ai_search", side_effect=fake_visible):
            result = enrich_question(self.question(), max_results=6)
        self.assertEqual(len(calls), 1)
        self.assertTrue(result["justification_confirmed"])
        self.assertIn("alternativa E", result["structured_question"]["explicacao"])

    def test_google_web_fallback_can_supply_verified_commentary(self) -> None:
        ai_calls = []
        fallback_calls = []
        ai_page = """
        Q1040341
        Ano: 2019
        Banca: CEBRASPE
        Enunciado
        Segundo o Comitê de Pronunciamentos Contábeis, os relatórios contábeis-financeiros objetivam fornecer informações úteis aos usuários em geral.
        Gabarito: E
        """
        def fake_visible(query: str, **kwargs):
            ai_calls.append(query)
            return {
                "query": query,
                "search_url": "https://www.google.com/ai",
                "browser": "Chrome",
                "search_text": ai_page,
                "search_html": "<html></html>",
                "blocked": False,
                "ai_mode_activated": True,
                "ai_answer_stable": True,
                "google_answer_expanded": True,
                "google_expand_clicks": 0,
                "google_expand_labels": [],
                "google_expand_errors": [],
            }
        verified_candidate = {
            "url": "https://example.org/q1040341",
            "provider": "Google",
            "source_kind": "page",
            "page_opened": True,
            "exact_code": True,
            "statement_similarity": 0.95,
            "statement_confirmed": True,
            "board_match": True,
            "year_match": True,
            "metadata_confirmed": True,
            "answer_on_page": True,
            "justification_on_page": True,
            "verified": True,
            "score": 0.98,
            "search_stage": "google_web_codigo",
            "statement": self.question()["enunciado"],
            "gabarito": "E",
            "justificativa": "A alternativa E é correta porque investidores existentes e potenciais são usuários primários do relatório financeiro de propósito geral.",
            "explanation_confidence": 0.89,
            "explanation_method": "heading_explicit",
            "noise_removed": 4,
        }
        def fake_search_stage(question, queries, *, stage, max_results):
            fallback_calls.append((stage, list(queries)))
            return {
                "stage": stage,
                "queries": list(queries),
                "results": [],
                "candidates": [dict(verified_candidate, search_stage=stage)],
                "verified_candidates": [dict(verified_candidate, search_stage=stage)],
                "attempted_links": [{"url": verified_candidate["url"], "opened": True, "verified": True}],
                "errors": [],
            }
        with patch("core.enrichment.run_visible_google_ai_search", side_effect=fake_visible), patch(
            "core.enrichment._search_stage", side_effect=fake_search_stage
        ):
            result = enrich_question(self.question(), max_results=6)
        self.assertGreaterEqual(len(ai_calls), 2)  # código + enunciado no Modo IA
        self.assertTrue(fallback_calls)
        self.assertTrue(result["justification_confirmed"])
        self.assertEqual(result["search_mode"], "google_web_fonte_publica_verificada")
        self.assertIn("investidores existentes", result["structured_question"]["explicacao"])

    def test_progress_callback_reports_fallback_state(self) -> None:
        messages = []
        def report(progress, message):
            messages.append((progress, message))
        def fake_visible(query: str, **kwargs):
            return {
                "query": query,
                "search_url": "https://www.google.com/ai",
                "browser": "Chrome",
                "search_text": "",
                "search_html": "",
                "blocked": True,
                "ai_mode_activated": False,
                "ai_answer_stable": False,
                "google_expand_errors": [],
            }
        def fake_search_stage(question, queries, *, stage, max_results):
            return {"stage": stage, "queries": list(queries), "results": [], "candidates": [], "verified_candidates": [], "attempted_links": [], "errors": []}
        with patch("core.enrichment.run_visible_google_ai_search", side_effect=fake_visible), patch(
            "core.enrichment._search_stage", side_effect=fake_search_stage
        ):
            enrich_question(self.question(), max_results=6, progress_callback=report)
        joined = " ".join(message for _, message in messages)
        self.assertIn("código", joined)
        self.assertIn("fonte pública", joined)


if __name__ == "__main__":
    unittest.main()
