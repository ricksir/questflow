from __future__ import annotations

import unittest

from core.enrichment import parse_google_search_page
from core.google_browser import _visible_ai_answer_snapshot


class _SemanticDriver:
    def execute_script(self, script, *args):
        if "const labels" in script:
            return [
                {
                    "text": (
                        "Q2247980\n📋 Informações Gerais\nAno: 2023\nBanca: FGV\n"
                        "📝 Enunciado da Questão\nTexto completo da questão.\n"
                        "Alternativas\nAlternativa A: Primeira.\nAlternativa B: Segunda.\n"
                        "Gabarito\nB\nJustificativa\nA alternativa B é correta."
                    ),
                    "score": 29.0,
                    "length": 240,
                    "labelHits": 7,
                    "termHits": 1,
                }
            ]
        return None


class GoogleAIOptimizedTests(unittest.TestCase):
    def test_semantic_dom_snapshot_prefers_answer_block(self):
        result = _visible_ai_answer_snapshot(_SemanticDriver(), '"Q2247980" quais as informações?')
        self.assertEqual(result["method"], "semantic_dom_block")
        self.assertIn("Gabarito", result["text"])
        self.assertGreater(result["score"], 20)

    def test_parser_accepts_icons_and_alternative_prefix(self):
        question = {
            "codigo_origem": "Q2247980",
            "enunciado": "Texto completo da questão.",
            "banca": "FGV",
            "ano": 2023,
        }
        page = """
        Q2247980
        📋 Informações Gerais
        • Ano: 2023
        • Banca: FGV
        • Órgão: SMF-RJ
        📝 Enunciado da Questão
        Texto completo da questão.
        📌 Alternativas
        Alternativa A: Primeira opção.
        Alternativa B: Segunda opção.
        ✅ Gabarito
        B
        💡 Justificativa
        A segunda alternativa é correta conforme a norma aplicável.
        """
        candidate = parse_google_search_page(page, "<html></html>", question, search_url="https://www.google.com/ai")
        self.assertTrue(candidate["verified"])
        self.assertEqual(candidate["gabarito"], "B")
        self.assertEqual([item["chave"] for item in candidate["alternatives"]], ["A", "B"])
        self.assertIn("segunda alternativa", candidate["justificativa"].lower())

    def test_parser_uses_banca_and_year_even_with_markdown_headings(self):
        question = {
            "codigo_origem": "Q2534553",
            "enunciado": "Assinale a opção correta sobre princípios orçamentários.",
            "banca": "FGV",
            "ano": 2024,
        }
        page = """
        ## Q2534553
        ### Informações da Questão
        Banca: Fundação Getulio Vargas (FGV)
        Ano: 2024
        ### Enunciado
        Assinale a opção correta sobre princípios orçamentários.
        ### Gabarito
        C
        """
        candidate = parse_google_search_page(page, "", question, search_url="https://www.google.com/ai")
        self.assertTrue(candidate["board_match"])
        self.assertTrue(candidate["year_match"])
        self.assertTrue(candidate["verified"])


if __name__ == "__main__":
    unittest.main()
