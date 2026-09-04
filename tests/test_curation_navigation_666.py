from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class CurationNavigation666Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        cls.css = (ROOT / "web" / "styles.css").read_text(encoding="utf-8")

    def test_critical_curation_requirements_have_editor_targets(self):
        expected = {
            "Enunciado íntegro": "#statementInput",
            "Gabarito consistente": "#field-gabarito",
            "Alternativas estruturadas": "#alternativesSection",
            "Matéria informada": "#field-materia",
            "Assunto informado": "#field-assunto",
        }
        for label, selector in expected.items():
            self.assertIn(repr(label), self.app)
            self.assertIn(repr(selector), self.app)

    def test_blockers_render_clickable_jump_and_failed_completion_exposes_actions(self):
        self.assertIn("data-curation-jump", self.app)
        self.assertIn("Ir ao campo →", self.app)
        self.assertIn("showEditorCurationBlockers(blockers)", self.app)
        self.assertIn("openCurationIssueForQuestion", self.app)
        self.assertIn("focusCurationIssue", self.app)

    def test_target_is_scrolled_focused_and_highlighted(self):
        self.assertIn("target.scrollIntoView({ behavior: 'smooth', block: 'center'", self.app)
        self.assertIn("target.focus", self.app)
        self.assertIn("curation-field-highlight", self.css)
        self.assertIn("curation-section-highlight", self.css)
        self.assertIn("prefers-reduced-motion", self.css)


if __name__ == "__main__":
    unittest.main()
