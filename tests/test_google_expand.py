from __future__ import annotations

import unittest

from core.google_browser import _expand_google_answer
from core.enrichment import parse_google_search_page


class _Body:
    def __init__(self, driver):
        self.driver = driver

    @property
    def text(self):
        return self.driver.body_text


class _ExpandElement:
    def __init__(self, driver):
        self.driver = driver

    def is_displayed(self):
        return not self.driver.expanded

    def click(self):
        self.driver.expanded = True
        self.driver.body_text = self.driver.expanded_text


class _FakeDriver:
    def __init__(self, collapsed_text: str, expanded_text: str):
        self.body_text = collapsed_text
        self.expanded_text = expanded_text
        self.expanded = False
        self.element = _ExpandElement(self)

    def find_element(self, by, value):
        if by == "tag name" and value == "body":
            return _Body(self)
        raise LookupError(value)

    def find_elements(self, by, value):
        if "Mostrar mais" in value and not self.expanded:
            return [self.element]
        return []

    def execute_script(self, script, *args):
        if "click" in script and args:
            args[0].click()


class GoogleExpandTests(unittest.TestCase):
    def test_clicks_show_more_and_returns_expanded_text(self):
        collapsed = "Q2228512\nInformações Gerais\nAno: 2023\nBanca: CESPE / CEBRASPE\nMostrar mais"
        expanded = """
        Q2228512
        Informações Gerais
        Ano: 2023
        Banca: CESPE / CEBRASPE
        Órgão: SEFIN Fortaleza
        Enunciado
        A extinção de passivos por transferência de recursos pode resultar em benefícios econômicos para a entidade.
        Gabarito
        ERRADO
        Justificativa
        A afirmativa está incorreta segundo o CPC 00.
        Mostrar menos
        """
        driver = _FakeDriver(collapsed, expanded)
        result = _expand_google_answer(driver)
        self.assertTrue(result["expanded"])
        self.assertEqual(result["click_count"], 1)
        self.assertIn("Gabarito", result["text"])
        self.assertIn("Justificativa", result["text"])

    def test_expanded_google_text_is_fully_parsed(self):
        question = {
            "codigo_origem": "Q2228512",
            "enunciado": "A extinção de passivos por transferência de recursos pode resultar em benefícios econômicos para a entidade.",
            "banca": "CESPE / CEBRASPE",
            "ano": 2023,
        }
        expanded = """
        Q2228512
        Informações Gerais
        Ano: 2023
        Banca: CESPE / CEBRASPE
        Órgão: SEFIN Fortaleza
        Enunciado
        A extinção de passivos por transferência de recursos pode resultar em benefícios econômicos para a entidade.
        Gabarito
        ERRADO
        Justificativa
        A afirmativa está incorreta segundo o CPC 00.
        """
        candidate = parse_google_search_page(
            expanded,
            "<html></html>",
            question,
            search_url="https://www.google.com/search?q=Q2228512",
        )
        self.assertTrue(candidate["verified"])
        self.assertEqual(candidate["gabarito"], "E")
        self.assertIn("CPC 00", candidate["justificativa"])


if __name__ == "__main__":
    unittest.main()
