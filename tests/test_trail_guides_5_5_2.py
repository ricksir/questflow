from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from core.spreadsheet_taxonomy import _detect_ciclo_columns, SpreadsheetTaxonomy
from core.trail_guides import (
    default_registry,
    ensure_registry,
    guide_status_for_tasks,
    import_guide_pdfs,
    trail_number,
)


class TrailGuides552Tests(unittest.TestCase):
    def test_default_registry_documents_trails_zero_through_five(self) -> None:
        status = guide_status_for_tasks([], default_registry())
        self.assertEqual(status["available_trails"], [0, 1, 2, 3, 4, 5])
        self.assertEqual(status["documented_through"], 5)
        self.assertEqual(status["next_expected_trail"], 6)
        self.assertEqual(status["missing_studied_trails"], [])

    def test_only_studied_task_triggers_missing_guide_warning(self) -> None:
        tasks = [
            {"trilha": "TRILHA 6", "tarefa": "151", "materia": "AUDITORIA", "estudado": False},
            {"trilha": "TRILHA 6", "tarefa": "152", "materia": "DIREITO TRIBUTÁRIO", "ch_efetiva_min": 90},
        ]
        status = guide_status_for_tasks(tasks, default_registry())
        self.assertEqual(status["studied_trails"], [6])
        self.assertEqual(status["missing_count"], 1)
        missing = status["missing_studied_trails"][0]
        self.assertEqual(missing["trail"], 6)
        self.assertEqual(missing["tasks"], ["152"])
        self.assertEqual(missing["subjects"], ["DIREITO TRIBUTÁRIO"])

    def test_missing_trail_groups_multiple_studied_subjects(self) -> None:
        tasks = [
            {"trilha": "TRILHA 7", "tarefa": "176", "materia": "AUDITORIA", "questoes_feitas": 10},
            {"trilha": "TRILHA 7", "tarefa": "177", "materia": "PORTUGUÊS", "data": "10/08/2026"},
        ]
        missing = guide_status_for_tasks(tasks, default_registry())["missing_studied_trails"]
        self.assertEqual(len(missing), 1)
        self.assertEqual(missing[0]["studied_contents"], 2)
        self.assertEqual(missing[0]["subjects"], ["AUDITORIA", "PORTUGUÊS"])

    def test_importing_next_pdf_resolves_that_trail_warning(self) -> None:
        try:
            import pymupdf  # type: ignore
        except Exception as error:  # pragma: no cover
            self.skipTest(f"PyMuPDF indisponível: {error}")
        with tempfile.TemporaryDirectory(prefix="questflow-guide-") as temp_dir:
            root = Path(temp_dir)
            registry_path = root / "trail_guides.json"
            ensure_registry(registry_path)
            pdf_path = root / "curso-trilha-06.pdf"
            document = pymupdf.open()
            page = document.new_page()
            page.insert_text((72, 72), "Trilha 06\nTAREFA 151\nAUDITORIA\nTAREFA 152\nDIREITO TRIBUTÁRIO")
            document.save(pdf_path)
            document.close()

            result = import_guide_pdfs([pdf_path], registry_path)
            self.assertEqual([item["trail"] for item in result["imported"]], [6])
            registry = ensure_registry(registry_path)
            tasks = [{"trilha": "TRILHA 6", "tarefa": "151", "materia": "AUDITORIA", "data": "10/08/2026"}]
            status = guide_status_for_tasks(tasks, registry)
            self.assertEqual(status["missing_studied_trails"], [])
            self.assertEqual(status["documented_through"], 6)
            self.assertEqual(status["next_expected_trail"], 7)

    def test_ciclo_header_detection_survives_reordered_columns(self) -> None:
        rows = [[
            "DISCIPLINA", "TAREFAS", "TRILHA", "TOT ACERTOS", "DATA",
            "TOT QUEST FEITAS", "CH (EFETIVA)", "TAREFA", "DESEMPENHO", "CH",
        ]]
        columns = _detect_ciclo_columns(rows)
        self.assertEqual(columns["subject"], 0)
        self.assertEqual(columns["description"], 1)
        self.assertEqual(columns["trail"], 2)
        self.assertEqual(columns["hits"], 3)
        self.assertEqual(columns["date"], 4)
        self.assertEqual(columns["questions"], 5)
        self.assertEqual(columns["effective_time"], 6)
        self.assertEqual(columns["task"], 7)
        self.assertEqual(columns["performance"], 8)
        self.assertEqual(columns["planned_time"], 9)

    def test_packaged_registry_and_taxonomy_report_current_missing_guides(self) -> None:
        registry_path = Path("data/trail_guides.json")
        taxonomy_path = Path("data/taxonomia_afrfb.json")
        self.assertTrue(registry_path.exists())
        self.assertTrue(taxonomy_path.exists())
        payload = json.loads(registry_path.read_text(encoding="utf-8"))
        available = sorted(item["trail"] for item in payload["guides"])
        # A pasta data é preservada entre updates e pode já conter guias novos.
        # O teste valida a baseline empacotada sem assumir que dados do usuário
        # continuam congelados em 0..5.
        self.assertTrue(set(range(6)).issubset(set(available)))
        taxonomy = SpreadsheetTaxonomy.load(taxonomy_path)
        status = guide_status_for_tasks(taxonomy.tasks, ensure_registry(registry_path))
        missing = [item["trail"] for item in status["missing_studied_trails"]]
        self.assertTrue(all(trail not in available for trail in missing))

    def test_trail_number_accepts_zero_and_labels(self) -> None:
        self.assertEqual(trail_number(0), 0)
        self.assertEqual(trail_number("TRILHA 05"), 5)
        self.assertEqual(trail_number("6"), 6)


if __name__ == "__main__":
    unittest.main()
