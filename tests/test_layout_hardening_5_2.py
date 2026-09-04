from __future__ import annotations

import unittest
from pathlib import Path


BASE = Path(__file__).resolve().parents[1]


class LayoutHardening52Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.css = (BASE / "web" / "styles.css").read_text(encoding="utf-8")
        cls.js = (BASE / "web" / "app.js").read_text(encoding="utf-8")

    def test_long_question_text_can_wrap_without_horizontal_overflow(self) -> None:
        self.assertIn(".virtual-row .cell-primary", self.css)
        self.assertIn("overflow-wrap: anywhere", self.css)
        self.assertIn("text-overflow: clip", self.css)
        self.assertIn("minmax(0, 1fr)", self.css)
        self.assertIn("overflow-x: hidden", self.css)

    def test_review_editor_and_actions_use_independent_scroll_regions(self) -> None:
        self.assertIn("container: question-list / inline-size", self.css)
        self.assertIn("container: editor / inline-size", self.css)
        self.assertIn(".editor-actions", self.css)
        self.assertIn("position: sticky", self.css)
        self.assertIn("@container editor (width < 36rem)", self.css)

    def test_flow_switches_are_not_styled_as_large_text_fields(self) -> None:
        self.assertIn('.form-field input:not([type="checkbox"])', self.css)
        self.assertIn(".switch-control", self.css)
        self.assertIn(".flow-value", self.css)

    def test_coverage_and_generic_tables_have_mobile_labels(self) -> None:
        self.assertIn("data-table--coverage", self.css)
        self.assertIn("data-table--responsive", self.css)
        self.assertIn("data-label", self.js)
        self.assertIn("coverage-status", self.js)

    def test_http_token_survives_reload_without_remaining_in_url(self) -> None:
        self.assertIn("sessionStorage.getItem('qf-http-token')", self.js)
        self.assertIn("sessionStorage.setItem('qf-http-token'", self.js)
        self.assertIn("history.replaceState", self.js)


if __name__ == "__main__":
    unittest.main()
