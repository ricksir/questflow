from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from core.mobile_foundation import MobileFoundationService
from core.storage import QuestFlowDatabase
from core.study import StudyRepository
from web_api import QuestFlowWebApi

ROOT = Path(__file__).resolve().parents[1]


class CorrectionsSplit6181Tests(unittest.TestCase):
    def test_web_names_and_two_separate_areas_are_present(self) -> None:
        html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
        js = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        self.assertIn("Correções e Matérias não Estudadas", html)
        self.assertIn('id="editorialCorrectionsTable"', html)
        self.assertIn('id="notStudiedCorrectionsTable"', html)
        self.assertIn("Matérias ainda não estudadas", html)
        self.assertIn("state.corrections.filter((item) => item.item_type !== 'not_studied')", js)
        self.assertIn("state.corrections.filter((item) => item.item_type === 'not_studied')", js)
        self.assertIn("correctionRowsHtml(editorial, 'correction')", js)
        self.assertIn("correctionRowsHtml(notStudied, 'not_studied')", js)

    def test_api_preserves_combined_contract_and_exposes_split_sections(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            db = QuestFlowDatabase(root / "questflow.sqlite")
            study = StudyRepository(db)
            mobile = MobileFoundationService(db, study, control_plane_path=root / "mobile_control.sqlite")
            api = QuestFlowWebApi(database_path=root / "questflow.sqlite", config_path=root / "config.json", taxonomy_path=root / "missing.json")
            api._ensure_core = lambda *args, **kwargs: None  # type: ignore[method-assign]
            api.study = study
            api.mobile_foundation = mobile
            result = api.list_corrections("ativas")
            self.assertIn("items", result)
            self.assertIn("corrections", result)
            self.assertIn("not_studied", result)
            self.assertEqual({str(x.get("id")) for x in result["items"]}, {str(x.get("id")) for x in result["corrections"] + result["not_studied"]})
            self.assertEqual(result["summary"]["total"], len(result["items"]))


if __name__ == "__main__":
    unittest.main()
