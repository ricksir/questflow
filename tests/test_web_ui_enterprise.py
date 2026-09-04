from __future__ import annotations

import re
import unittest
from pathlib import Path


BASE = Path(__file__).resolve().parents[1]


class EnterpriseWebUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.html = (BASE / "web" / "index.html").read_text(encoding="utf-8")
        cls.css = (BASE / "web" / "styles.css").read_text(encoding="utf-8")
        cls.js = (BASE / "web" / "app.js").read_text(encoding="utf-8")

    def test_required_responsive_css_capabilities(self) -> None:
        self.assertIn("display: grid", self.css)
        self.assertIn("display: flex", self.css)
        self.assertIn("container-type", self.css)
        self.assertIn("@container", self.css)
        self.assertIn("clamp(", self.css)
        self.assertIn("prefers-color-scheme", self.css)
        self.assertIn("prefers-reduced-motion", self.css)

    def test_design_tokens_are_centralized(self) -> None:
        token_count = len(re.findall(r"--[a-z0-9-]+\s*:", self.css))
        self.assertGreaterEqual(token_count, 80)
        self.assertIn("--space-4", self.css)
        self.assertIn("--radius-3", self.css)
        self.assertIn("--font-size-4", self.css)
        self.assertIn("--surface-panel", self.css)

    def test_accessibility_structure(self) -> None:
        self.assertIn('class="skip-link"', self.html)
        self.assertIn('aria-live="polite"', self.html)
        self.assertIn('role="dialog"', self.html)
        self.assertIn(':focus-visible', self.css)
        self.assertIn('aria-label="Lista de questões"', self.html)

    def test_interaction_states_and_virtualization(self) -> None:
        for state in (":hover", ":focus", ":active", ":disabled", ".is-loading", ".empty-state", ".skeleton"):
            self.assertIn(state, self.css)
        self.assertIn("class VirtualQuestionList", self.js)
        self.assertIn("waitForNativeMethod", self.js)
        self.assertIn("questionRequestId", self.js)
        self.assertIn("content-visibility: auto", self.css)
        self.assertIn('.form-field input:not([type="checkbox"])', self.css)
        self.assertIn(".switch-control", self.css)
        self.assertIn('value="sem_questoes"', self.html)
        self.assertIn('value="cobertura_parcial"', self.html)
        self.assertIn('loading="lazy"', self.html)

    def test_editor_uses_structured_alternatives_and_text_tools(self) -> None:
        self.assertIn('id="statementInput"', self.html)
        self.assertIn('id="alternativesList"', self.html)
        self.assertIn('id="explanationInput"', self.html)
        self.assertIn("renderAlternatives", self.js)
        self.assertIn("autoResizeAll", self.js)


if __name__ == "__main__":
    unittest.main()
