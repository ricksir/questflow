from __future__ import annotations

import unittest
from pathlib import Path


class LayoutDensityScroll524Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = Path(__file__).resolve().parents[1]
        cls.css = (cls.root / "web" / "styles.css").read_text(encoding="utf-8")
        cls.js = (cls.root / "web" / "app.js").read_text(encoding="utf-8")
        cls.html = (cls.root / "web" / "index.html").read_text(encoding="utf-8")

    def test_global_external_gaps_are_compacted(self) -> None:
        self.assertIn("--layout-section-gap:", self.css)
        self.assertIn("--layout-control-gap:", self.css)
        self.assertIn(".dashboard-grid,", self.css)
        self.assertIn(".editor-content { gap: var(--layout-section-gap); }", self.css)

    def test_question_table_has_dedicated_horizontal_scrollbar(self) -> None:
        self.assertIn('id="questionHorizontalScroll"', self.html)
        self.assertIn('id="questionHorizontalScrollTrack"', self.html)
        self.assertIn("syncQuestionHorizontalGeometry", self.js)
        self.assertIn("syncQuestionHorizontalPosition", self.js)
        self.assertIn("Shift + roda do mouse", self.html)

    def test_all_managed_tables_support_horizontal_navigation(self) -> None:
        self.assertIn("wrap.scrollWidth <= wrap.clientWidth", self.js)
        self.assertIn("overflow-x: auto !important", self.css)
        self.assertIn("width: max-content", self.css)

    def test_question_code_field_is_editable_and_audited(self) -> None:
        self.assertIn("{ key: 'codigo_origem', label: 'Código da questão', type: 'code' }", self.js)
        self.assertNotIn("{ key: 'codigo_origem', label: 'Código da questão', readonly: true }", self.js)
        self.assertIn("referências e histórico sincronizados", self.js)


if __name__ == "__main__":
    unittest.main()
