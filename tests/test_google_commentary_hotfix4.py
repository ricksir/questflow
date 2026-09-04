from __future__ import annotations

import unittest
from unittest.mock import patch

from core.enrichment import enrich_question, parse_google_search_page


class GoogleCommentaryHotfix4Tests(unittest.TestCase):
    @staticmethod
    def question() -> dict:
        return {
            "codigo_origem": "Q105746",
            "enunciado": (
                "Considerando normas vigentes no Brasil relativas à contabilidade de entidades "
                "fechadas de previdência complementar (EFPCs), julgue o item seguinte acerca "
                "dos aspectos gerais da auditoria independente."
            ),
            "banca": "CEBRASPE",
            "ano": 2024,
            "gabarito": "C",
        }

    @staticmethod
    def ai_answer() -> str:
        return (
            "Gabarito: CERTO\n"
            "Explicação:\n"
            "O item reflete as diretrizes de auditoria independente preconizadas pelas Normas "
            "Brasileiras de Contabilidade Técnicas de Auditoria (NBC TAs), especialmente quanto "
            "ao conhecimento do negócio e à limitação de especialidade.\n"
            "Embora o auditor deva compreender o ambiente da entidade para planejar seus testes, "
            "não se exige dele a expertise própria de profissionais qualificados em outras áreas.\n"
            "Desse modo, quando estimativas complexas dependem de outras ciências, o auditor avalia "
            "os impactos ou recorre ao trabalho de especialista."
        )

    def test_statement_query_context_accepts_visible_gabarito_and_explicacao_without_metadata_echo(self) -> None:
        calls: list[str] = []

        def fake_visible(query: str, **kwargs):
            calls.append(query)
            if "Q105746" in query:
                # Simula a primeira consulta pelo código sem comentário utilizável.
                text = "Modo IA\nNenhuma explicação específica foi exibida nesta tentativa."
            else:
                # Exatamente o padrão mostrado na captura do usuário: resposta correta,
                # sem repetir código, banca, ano nem enunciado.
                text = self.ai_answer()
            return {
                "query": query,
                "search_url": "https://www.google.com/search?udm=50",
                "browser": "Chrome",
                "search_text": text,
                "search_html": "<html></html>",
                "blocked": False,
                "ai_mode_activated": True,
                "ai_answer_stable": True,
                "google_answer_expanded": True,
                "google_expand_clicks": 0,
                "google_expand_labels": [],
                "google_expand_errors": [],
            }

        with patch("core.enrichment.run_visible_google_ai_search", side_effect=fake_visible), patch(
            "core.enrichment._search_stage"
        ) as web_fallback:
            result = enrich_question(self.question(), max_results=6)

        self.assertGreaterEqual(len(calls), 2)
        self.assertFalse(web_fallback.called, "Uma explicação já visível no Modo IA não deve cair no fallback web.")
        self.assertTrue(result["verified_match"])
        self.assertTrue(result["justification_confirmed"])
        self.assertTrue(str(result["search_stage_used"]).startswith("enunciado"))
        explanation = result["structured_question"]["explicacao"]
        self.assertIn("diretrizes de auditoria independente", explanation)
        self.assertIn("não se exige dele a expertise", explanation)
        self.assertNotIn("Q105746", explanation)
        self.assertNotIn("Banca", explanation)

    def test_explicit_google_answer_block_is_parsed_even_without_question_metadata(self) -> None:
        candidate = parse_google_search_page(
            self.ai_answer(),
            "<html></html>",
            self.question(),
            search_url="https://www.google.com/search?udm=50",
        )
        self.assertEqual(candidate["gabarito"], "C")
        self.assertTrue(candidate["justification_on_page"])
        self.assertIn("NBC TAs", candidate["justificativa"])
        # A validação por contexto da consulta ocorre em _google_browser_stage;
        # o parser isolado não inventa metadados que não apareceram na resposta.
        self.assertFalse(candidate["metadata_confirmed"])

    def test_low_confidence_verified_commentary_is_still_selected(self) -> None:
        def fake_visible(query: str, **kwargs):
            text = self.ai_answer() if "Q105746" not in query else "Sem comentário útil."
            return {
                "query": query,
                "search_url": "https://www.google.com/search?udm=50",
                "browser": "Chrome",
                "search_text": text,
                "search_html": "<html></html>",
                "blocked": False,
                "ai_mode_activated": True,
                "ai_answer_stable": True,
                "google_answer_expanded": True,
                "google_expand_clicks": 0,
                "google_expand_labels": [],
                "google_expand_errors": [],
            }

        with patch("core.enrichment.run_visible_google_ai_search", side_effect=fake_visible), patch(
            "core.enrichment._commentary_quality", return_value=0.12
        ), patch("core.enrichment._search_stage") as web_fallback:
            result = enrich_question(self.question(), max_results=6)

        self.assertFalse(web_fallback.called)
        self.assertTrue(result["justification_confirmed"])
        self.assertAlmostEqual(result["explanation_confidence"], 0.12)
        self.assertIn("diretrizes de auditoria", result["structured_question"]["explicacao"])

    def test_browser_capture_contains_compact_explicit_answer_priority(self) -> None:
        from pathlib import Path
        root = Path(__file__).resolve().parents[1]
        source = (root / "core" / "google_browser.py").read_text(encoding="utf-8")
        self.assertIn("compactAnswerBonus", source)
        self.assertIn("explicitAnswer", source)


if __name__ == "__main__":
    unittest.main()
