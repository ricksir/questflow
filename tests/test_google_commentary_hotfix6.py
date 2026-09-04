from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from core.google_browser import _wait_for_ai_answer


class _Clock:
    def __init__(self):
        self.now = 0.0

    def time(self):
        return self.now

    def sleep(self, seconds):
        self.now += float(seconds)


class GoogleCommentaryHotfix6Tests(unittest.TestCase):
    def test_wait_does_not_capture_during_short_streaming_pause(self):
        clock = _Clock()

        def snapshot(_driver, _query):
            t = clock.now
            if t < 1.2:
                text = "Modo IA pesquisando..."
            elif t < 5.8:
                # O Google já mostra parte da resposta, mas ainda vai completar.
                text = (
                    "Gabarito: CERTO\nExplicação:\n"
                    "O item está correto porque as normas brasileiras de auditoria "
                    "exigem conhecimento adequado do negócio auditado."
                )
            else:
                text = (
                    "Gabarito: CERTO\nExplicação:\n"
                    "O item está correto porque as normas brasileiras de auditoria "
                    "exigem conhecimento adequado do negócio auditado. Além disso, "
                    "o auditor pode recorrer a especialista quando a matéria exigir "
                    "conhecimento técnico de outra área."
                )
            return {"text": text, "method": "semantic_dom_block", "score": 30, "candidate_count": 1}

        with patch("core.google_browser._visible_ai_answer_snapshot", side_effect=snapshot), patch(
            "core.google_browser._captcha_present", return_value=False
        ), patch("core.google_browser._scroll_ai_page"):
            result = _wait_for_ai_answer(
                object(),
                "Q105746 qual é o gabarito e a explicação?",
                wait_seconds=20,
                sleep_func=clock.sleep,
                time_func=clock.time,
            )

        self.assertTrue(result["stable"])
        self.assertIn("recorrer a especialista", result["text"])
        self.assertGreaterEqual(result["elapsed_seconds"], 9.0)

    def test_default_wait_is_75_seconds_and_post_wait_is_at_least_30(self):
        source = (Path(__file__).resolve().parents[1] / "core" / "google_browser.py").read_text(encoding="utf-8")
        self.assertGreaterEqual(source.count("wait_seconds: int = 75"), 2)
        self.assertIn("wait_seconds=max(30, wait_seconds // 2)", source)
        self.assertIn("time.sleep(2.2)", source)
        enrichment = (Path(__file__).resolve().parents[1] / "core" / "enrichment.py").read_text(encoding="utf-8")
        self.assertIn("wait_seconds=75", enrichment)
        self.assertIn("wait_seconds=60", enrichment)
        self.assertNotIn("wait_seconds=24", enrichment)

    def test_dom_capture_always_scans_explicit_answer_nodes(self):
        source = (Path(__file__).resolve().parents[1] / "core" / "google_browser.py").read_text(encoding="utf-8")
        self.assertIn("const explicitNodes", source)
        self.assertIn("evaluateNodes(explicitNodes);", source)
        self.assertIn("document.querySelectorAll('div,section,article')", source)

    def test_compact_header_toggle_is_persistent(self):
        root = Path(__file__).resolve().parents[1]
        html = (root / "web" / "index.html").read_text(encoding="utf-8")
        js = (root / "web" / "app.js").read_text(encoding="utf-8")
        css = (root / "web" / "styles.css").read_text(encoding="utf-8")
        self.assertIn('id="toggleQuestionHeader"', html)
        self.assertIn("qf-question-header-collapsed", js)
        self.assertIn("applyQuestionHeaderCollapsed", js)
        self.assertIn(".question-editor.is-header-collapsed", css)
        self.assertIn('min-height: clamp(19rem, 43vh, 38rem)', css)


if __name__ == "__main__":
    unittest.main()
