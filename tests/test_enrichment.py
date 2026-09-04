from __future__ import annotations

import unittest
from unittest.mock import patch

from core.enrichment import (
    SearchResult,
    _parse_bing_html,
    _parse_bing_rss,
    _parse_duckduckgo_html,
    _parse_duckduckgo_lite,
    _parse_google_html,
    apply_safe_suggestions,
    build_code_search_queries,
    build_search_queries,
    build_search_query,
    build_statement_search_queries,
    enrich_question,
    enrichment_from_candidate,
    parse_candidate_question,
    parse_google_search_page,
    score_results,
)


class EnrichmentTests(unittest.TestCase):
    def test_first_query_contains_only_code(self) -> None:
        question = {
            "codigo_origem": "Q12345",
            "enunciado": "Qual é o conceito de auditoria?",
            "banca": "FGV",
            "ano": 2025,
        }
        query = build_search_query(question)
        self.assertTrue(query.startswith('\"Q12345\"'))
        self.assertIn("qual é o gabarito e a justificativa desta questão?", query)
        self.assertIn("sem repetir enunciado, metadados ou menus", query)
        self.assertNotIn("auditoria", query.lower())
        self.assertNotIn("FGV", query)
        self.assertNotIn("2025", query)

    def test_code_and_statement_queries_are_never_combined(self) -> None:
        question = {
            "codigo_origem": "Q2534553",
            "enunciado": "Assinale a opção correta sobre princípios orçamentários.",
            "banca": "FGV",
            "ano": 2024,
            "orgao": "MF",
        }
        code_queries = build_code_search_queries(question)
        statement_queries = build_statement_search_queries(question)
        queries = build_search_queries(question)
        self.assertEqual(len(code_queries), 1)
        self.assertTrue(code_queries[0].startswith('\"Q2534553\"'))
        self.assertIn("gabarito e a justificativa", code_queries[0])
        self.assertTrue(statement_queries)
        self.assertEqual(queries[0], code_queries[0])
        self.assertTrue(all("Q2534553" not in item for item in statement_queries))
        self.assertTrue(
            all("FGV" not in item and "2024" not in item and "MF" not in item for item in statement_queries)
        )

    def test_invalid_local_code_uses_statement_first(self) -> None:
        question = {"codigo_origem": "ESTRATEGIA-123", "enunciado": "Texto completo da questão de auditoria."}
        self.assertEqual(build_code_search_queries(question), [])
        self.assertIn("Texto completo", build_search_query(question))

    def test_safe_suggestions_only_fill_empty_fields(self) -> None:
        question = {"banca": "FGV", "ano": None, "gabarito": ""}
        enrichment = {
            "safe_to_apply": True,
            "suggestions": {"banca": "FCC", "ano": 2024, "gabarito": "C"},
        }
        updated = apply_safe_suggestions(question, enrichment)
        self.assertEqual(updated["banca"], "FGV")
        self.assertEqual(updated["ano"], 2024)
        self.assertEqual(updated["gabarito"], "C")

    def test_scoring_exact_code(self) -> None:
        question = {"codigo_origem": "Q999", "enunciado": "Texto da questão", "banca": "CEBRASPE"}
        results = score_results(
            question,
            [SearchResult("Q999 CEBRASPE", "https://example.invalid", "Texto da questão")],
        )
        self.assertGreater(results[0].score, 0.4)

    def test_parse_duckduckgo_html(self) -> None:
        page = '''
        <div class="result results_links">
          <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fq">Questão Q123</a>
          <a class="result__snippet">Gabarito letra B.</a>
        </div>
        '''
        results = _parse_duckduckgo_html(page)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].url, "https://example.com/q")
        self.assertIn("Gabarito", results[0].snippet)

    def test_parse_duckduckgo_lite(self) -> None:
        page = '''
        <a rel="nofollow" class="result-link" href="https://example.com/lite">Resultado Lite</a>
        <td class="result-snippet">Questão de concurso.</td>
        '''
        results = _parse_duckduckgo_lite(page)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].provider, "DuckDuckGo Lite")

    def test_parse_bing_html(self) -> None:
        page = '''
        <li class="b_algo"><h2><a href="https://example.com/bing">Questão FGV</a></h2>
        <div class="b_caption"><p>Resposta correta letra C.</p></div></li>
        '''
        results = _parse_bing_html(page)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].provider, "Bing")
        self.assertIn("letra C", results[0].snippet)

    def test_google_parser(self) -> None:
        page = '''
        <div><a href="/url?q=https%3A%2F%2Fexample.com%2Fquestao&sa=U"><h3>Q2074384 FGV</h3></a>
        <div class="VwiC3b">Após o encerramento de um dado exercício financeiro.</div></div>
        '''
        results = _parse_google_html(page)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].provider, "Google")
        self.assertEqual(results[0].url, "https://example.com/questao")

    def test_parse_exact_question_and_answer_requires_board_and_year(self) -> None:
        question = {
            "codigo_origem": "Q2074384",
            "banca": "FGV",
            "ano": 2023,
            "enunciado": (
                "Após o encerramento de um dado exercício financeiro, o gestor de um ente público "
                "solicitou uma avaliação do montante de pagamentos de restos a pagar processados e não processados."
            ),
        }
        page = '''
        <div>Q2074384</div><div>Ano: 2023 Banca: FGV Órgão: TCE-ES Prova: Auditoria Governamental</div>
        <p>Após o encerramento de um dado exercício financeiro, o gestor de um ente público solicitou uma avaliação do montante de pagamentos de restos a pagar processados e não processados.</p>
        <div>Alternativas</div><div>A</div><div>balanço financeiro;</div><div>B</div><div>balanço orçamentário;</div>
        <div>Gabarito: A</div>
        <div>Justificativa: O balanço financeiro evidencia ingressos e dispêndios orçamentários e extraorçamentários.</div>
        '''
        parsed = parse_candidate_question(page, question, url="https://example.com/q", provider="Google")
        self.assertTrue(parsed["verified"])
        self.assertTrue(parsed["exact_code"])
        self.assertTrue(parsed["board_match"])
        self.assertTrue(parsed["year_match"])
        self.assertTrue(parsed["answer_on_page"])
        self.assertEqual(parsed["gabarito"], "A")

    def test_same_code_and_statement_wrong_board_is_rejected(self) -> None:
        question = {
            "codigo_origem": "Q2074384",
            "banca": "FGV",
            "ano": 2023,
            "enunciado": "Após o encerramento de um dado exercício financeiro, o gestor solicitou avaliação de restos a pagar.",
        }
        page = '''
        <div>Q2074384</div><div>Ano: 2023 Banca: FCC</div>
        <p>Após o encerramento de um dado exercício financeiro, o gestor solicitou avaliação de restos a pagar.</p>
        <div>Gabarito: D</div>
        '''
        parsed = parse_candidate_question(page, question)
        self.assertFalse(parsed["verified"])
        self.assertFalse(parsed["board_match"])

    def test_snippet_cannot_confirm_question_or_answer(self) -> None:
        question = {
            "codigo_origem": "Q2074384",
            "banca": "FGV",
            "ano": 2023,
            "enunciado": "Após o encerramento de um dado exercício financeiro.",
        }
        snippet = '<div>Q2074384 FGV 2023 Após o encerramento de um dado exercício financeiro. Gabarito: A</div>'
        parsed = parse_candidate_question(snippet, question, source_kind="snippet")
        self.assertFalse(parsed["verified"])
        self.assertFalse(parsed["answer_on_page"])


class GoogleVisibleSearchTests(unittest.TestCase):
    def _question(self) -> dict:
        return {
            "codigo_origem": "Q2228512",
            "enunciado": (
                "A extinção de passivos por transferência de recursos pode resultar em benefícios econômicos para a entidade."
            ),
            "banca": "CESPE / CEBRASPE",
            "ano": 2023,
            "orgao": "SEFIN Fortaleza",
            "gabarito": "",
            "explicacao": "",
        }

    def _google_text(self) -> str:
        return """
        Q2228512
        A questão Q2228512 trata da Estrutura Conceitual da Contabilidade.
        Informações da Questão
        Ano: 2023
        Banca: CESPE / CEBRASPE
        Órgão: Secretaria Municipal das Finanças (SEFIN) de Fortaleza - CE
        Cargo: Analista Fazendário Municipal – Área: Contabilidade
        Matéria: Contabilidade Geral
        Assunto: Estrutura Conceitual Básica
        Enunciado
        A extinção de passivos por transferência de recursos pode resultar em benefícios econômicos para a entidade.
        Gabarito
        ERRADO
        Justificativa
        A afirmativa está incorreta segundo o CPC 00. A extinção de passivos pode gerar benefícios econômicos de diferentes formas.
        """

    def test_google_page_parser_confirms_and_extracts(self) -> None:
        candidate = parse_google_search_page(
            self._google_text(),
            "<html></html>",
            self._question(),
            search_url="https://www.google.com/search?q=Q2228512",
        )
        self.assertTrue(candidate["verified"])
        self.assertTrue(candidate["exact_code"])
        self.assertTrue(candidate["board_match"])
        self.assertTrue(candidate["year_match"])
        self.assertEqual(candidate["gabarito"], "E")
        self.assertIn("CPC 00", candidate["justificativa"])

    def test_enrichment_uses_rendered_google_page_without_opening_links(self) -> None:
        calls: list[str] = []

        def fake_visible(query: str, **kwargs):
            calls.append(query)
            return {
                "query": query,
                "search_url": "https://www.google.com/search?q=Q2228512",
                "browser": "Google Chrome",
                "search_text": self._google_text(),
                "search_html": "<html></html>",
                "results": [],
                "opened_pages": [],
                "blocked": False,
                "ai_mode_activated": True,
                "ai_answer_stable": True,
                "google_answer_expanded": True,
                "google_expand_clicks": 1,
                "google_expand_labels": ["Mostrar mais"],
                "google_expand_errors": [],
            }

        with patch("core.enrichment.run_visible_google_ai_search", side_effect=fake_visible):
            result = enrich_question(self._question(), max_results=10)

        self.assertEqual(len(calls), 1)
        self.assertTrue(calls[0].startswith('"Q2228512"'))
        self.assertIn("gabarito e a justificativa", calls[0])
        self.assertTrue(result["verified_match"])
        self.assertTrue(result["google_search_page_read"])
        self.assertTrue(result["answer_confirmed"])
        self.assertTrue(result["justification_confirmed"])
        self.assertEqual(result["structured_question"]["gabarito"], "E")


    def test_verified_google_page_falls_back_when_commentary_is_missing(self) -> None:
        google_text = """
        Q2228512
        Informações da Questão
        Ano: 2023
        Banca: CESPE / CEBRASPE
        Órgão: SEFIN Fortaleza
        Enunciado
        A extinção de passivos por transferência de recursos pode resultar em benefícios econômicos para a entidade.
        """
        calls: list[str] = []

        def fake_visible(query: str, **kwargs):
            calls.append(query)
            return {
                "query": query,
                "search_url": "https://www.google.com/search?q=Q2228512",
                "browser": "Google Chrome",
                "search_text": google_text,
                "search_html": "<html></html>",
                "results": [{"title": "Resultado", "url": "https://example.com", "snippet": "", "provider": "Google"}],
                "opened_pages": [],
                "blocked": False,
                "ai_mode_activated": True,
                "ai_answer_stable": True,
                "google_answer_expanded": True,
                "google_expand_clicks": 1,
                "google_expand_labels": ["Mostrar mais"],
                "google_expand_errors": [],
            }

        with patch("core.enrichment.run_visible_google_ai_search", side_effect=fake_visible):
            result = enrich_question(self._question(), max_results=10)

        self.assertGreaterEqual(len(calls), 2)
        self.assertTrue(result["verified_match"])
        self.assertFalse(result["answer_confirmed"])
        self.assertFalse(result["justification_confirmed"])
        self.assertEqual(result["attempted_links"], [])
        self.assertTrue(result["statement_queries"])

    def test_ai_mode_page_extracts_alternatives(self) -> None:
        ai_text = """
        Modo IA
        Q2228512
        Informações Gerais
        Ano: 2023
        Banca: CESPE / CEBRASPE
        Órgão: SEFIN Fortaleza
        Enunciado da Questão
        A extinção de passivos por transferência de recursos pode resultar em benefícios econômicos para a entidade.
        Alternativas
        C) Certo
        E) Errado
        Gabarito
        ERRADO
        Justificativa
        A afirmativa está incorreta segundo o CPC 00.
        """
        candidate = parse_google_search_page(
            ai_text, "<html></html>", self._question(), search_url="https://www.google.com/ai"
        )
        self.assertTrue(candidate["verified"])
        self.assertEqual(candidate["gabarito"], "E")
        self.assertEqual([item["chave"] for item in candidate["alternatives"]], ["C", "E"])

    def test_selected_candidate_can_be_applied(self) -> None:
        candidate = parse_google_search_page(
            self._google_text(),
            "<html></html>",
            self._question(),
            search_url="https://www.google.com/search?q=Q2228512",
        )
        enrichment = enrichment_from_candidate(candidate, question_uid="uid-1")
        updated = apply_safe_suggestions(self._question(), enrichment)
        self.assertTrue(enrichment["safe_to_apply"])
        self.assertEqual(updated["gabarito"], "E")
        self.assertIn("CPC 00", updated["explicacao"])
        self.assertEqual(enrichment["question_uid"], "uid-1")

    def test_incomplete_ai_page_never_opens_external_links(self) -> None:
        calls: list[str] = []

        def fake_ai(query: str, **kwargs):
            calls.append(query)
            return {
                "query": query,
                "search_url": "https://www.google.com/ai",
                "browser": "Google Chrome",
                "search_text": "Resposta incompleta sem banca e sem ano.",
                "search_html": "<html></html>",
                "results": [],
                "opened_pages": [],
                "blocked": False,
                "ai_mode_activated": True,
                "ai_answer_stable": True,
                "google_answer_expanded": False,
                "google_expand_clicks": 0,
                "google_expand_labels": [],
                "google_expand_errors": [],
            }

        with patch("core.enrichment.run_visible_google_ai_search", side_effect=fake_ai):
            result = enrich_question(self._question(), max_results=10)

        self.assertEqual(len(calls), 3)  # código, enunciado exato e fallback amplo
        self.assertEqual(result["attempted_links"], [])
        self.assertFalse(result["verified_match"])
        self.assertEqual(result["search_mode"], "google_modo_ia_pagina_renderizada")

    def test_safe_application_fills_answer_and_explanation(self) -> None:
        with patch("core.enrichment.run_visible_google_ai_search", return_value={
            "query": "q",
            "search_url": "https://www.google.com/search?q=q",
            "browser": "Google Chrome",
            "search_text": self._google_text(),
            "search_html": "<html></html>",
            "results": [],
            "opened_pages": [],
            "blocked": False,
        }):
            enrichment = enrich_question(self._question(), max_results=10)
        updated = apply_safe_suggestions(self._question(), enrichment)
        self.assertEqual(updated["gabarito"], "E")
        self.assertIn("CPC 00", updated["explicacao"])

class BingRssTests(unittest.TestCase):
    def test_parse_bing_rss(self) -> None:
        page = """<?xml version="1.0"?><rss><channel><item><title>Q2096379 FGV</title>
        <link>https://example.com/q2096379</link><description>Questão e gabarito.</description></item></channel></rss>"""
        results = _parse_bing_rss(page)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].provider, "Bing RSS")
        self.assertEqual(results[0].url, "https://example.com/q2096379")

if __name__ == "__main__":
    unittest.main()
