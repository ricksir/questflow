from __future__ import annotations

import unittest
from pathlib import Path


class CoverageRowClick554Tests(unittest.TestCase):
    def test_pending_row_is_single_click_target_and_import_column_is_removed(self) -> None:
        root = Path(__file__).resolve().parents[1]
        js = (root / "web" / "app.js").read_text(encoding="utf-8")
        css = (root / "web" / "styles.css").read_text(encoding="utf-8")
        html = (root / "web" / "index.html").read_text(encoding="utf-8")

        coverage_block = js[js.index("function renderCoverage()") : js.index("function normalizeTableColumn") ]
        bind_block = js[js.index("function bindCoverageImportActions") : js.index("function renderImportFiles") ]

        self.assertIn("rowInteractiveWhen: (item) => Boolean(item.needs_attention)", coverage_block)
        self.assertNotIn("{ label: 'Importar'", coverage_block)
        self.assertIn("row.addEventListener('click'", bind_block)
        self.assertNotIn("row.addEventListener('dblclick'", bind_block)
        self.assertIn("window.getSelection", bind_block)
        self.assertIn("table-row--interactive:hover", css)
        self.assertIn("Clique em qualquer ponto de uma linha pendente", html)

    def test_covered_rows_do_not_receive_interactive_row_class(self) -> None:
        root = Path(__file__).resolve().parents[1]
        js = (root / "web" / "app.js").read_text(encoding="utf-8")
        table_block = js[js.index("function tableHtml") : js.index("function tablePreferenceKey") ]
        self.assertIn("typeof options.rowInteractiveWhen !== 'function' || options.rowInteractiveWhen(item)", table_block)
        self.assertIn("if (rowCanInteract)", table_block)


if __name__ == "__main__":
    unittest.main()
