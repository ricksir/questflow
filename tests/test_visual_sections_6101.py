from __future__ import annotations

import unittest
from pathlib import Path


BASE = Path(__file__).resolve().parents[1]


class VisualSections6101Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.css = (BASE / "web" / "styles.css").read_text(encoding="utf-8")
        cls.questions = (BASE / "mobile" / "app" / "(tabs)" / "questions.tsx").read_text(encoding="utf-8")
        cls.progress = (BASE / "mobile" / "app" / "(tabs)" / "progress.tsx").read_text(encoding="utf-8")

    def test_studio_panels_have_persistent_section_identity(self) -> None:
        self.assertIn("QuestFlow 6.10.1 — blocos visuais persistentes", self.css)
        self.assertIn(".page article.panel:nth-of-type(6n + 2)", self.css)
        self.assertIn("--qf-block-accent", self.css)
        self.assertIn(".page article.panel > .panel-header::before", self.css)
        self.assertIn(".page article.panel > .panel-body", self.css)

    def test_question_editor_internal_sections_are_visually_separated(self) -> None:
        self.assertIn(".question-editor .editor-section", self.css)
        self.assertIn("border-inline-start: 4px solid var(--qf-inner-accent)", self.css)
        self.assertIn(".question-editor .editor-section:nth-of-type(6)", self.css)

    def test_mobile_summary_time_is_compact_and_responsive(self) -> None:
        self.assertIn("summaryTimeValueBox", self.questions)
        self.assertIn("adjustsFontSizeToFit", self.questions)
        self.assertIn("minimumFontScale={0.72}", self.questions)
        self.assertIn("formatDuration(summary.stats.active_seconds, { compact: true })", self.questions)
        self.assertIn("Pausas, troca de aba e tempo não elegível", self.questions)

    def test_progress_time_metric_uses_compact_duration(self) -> None:
        self.assertIn("`${Math.round(progress.summary.avg_active_response_seconds)}s`", self.progress)


if __name__ == "__main__":
    unittest.main()
