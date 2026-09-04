from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pymupdf

from core.extractor import ExtractorConfig, extract_pdf
from core.spreadsheet_taxonomy import SpreadsheetTaxonomy
from core.storage import QuestFlowDatabase


class QConcursosNativePdf557Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="questflow-557-")
        self.root = Path(self.temp.name)
        self.pdf = self.root / "fluencia-dados_Aula01.pdf"
        self._build_qconcursos_pdf(self.pdf)
        self.taxonomy = SpreadsheetTaxonomy(
            {
                "schema": "questflow.taxonomy.v1",
                "source": {"title": "Planilha de Controle"},
                "materias": ["FLUÊNCIA EM DADOS"],
                "aliases": {"FLUENCIA EM DADOS": "FLUÊNCIA EM DADOS"},
                "regras_manuais": {},
                "tarefas_referencia": [],
            }
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    @staticmethod
    def _build_qconcursos_pdf(path: Path) -> None:
        document = pymupdf.open()
        page = document.new_page(width=595, height=842)
        page.insert_text((478, 45), "qconcursos.com", fontsize=8)

        # Headers are inserted first, mimicking the misleading content-stream order
        # found in browser-print QConcursos PDFs.
        page.insert_text((28, 80), "1 Q4193540 Banco de Dados > Banco de Dados Relacionais", fontsize=9)
        page.insert_text((28, 98), "Ano: 2026", fontsize=9)
        page.insert_text((185, 98), "Orgao: UFU-MG", fontsize=9)
        page.insert_text((90, 98.4), "Banca: UFU-MG", fontsize=9)
        page.insert_text((28, 115), "Prova: UFU-MG - 2026 - Tecnico de TI", fontsize=9)

        page.insert_text((28, 410), "2 Q4176330 Banco de Dados > Banco de Dados Relacionais", fontsize=9)
        page.insert_text((28, 428), "Ano: 2026", fontsize=9)
        page.insert_text((205, 428), "Orgao: Prefeitura X", fontsize=9)
        page.insert_text((90, 428.4), "Banca: CONSULPAM", fontsize=9)
        page.insert_text((28, 445), "Provas: CONSULPAM - 2026 - Cargo A |", fontsize=9)
        page.insert_text((64, 459), "CONSULPAM - 2026 - Cargo B", fontsize=9)

        # Bodies/options are added only after both headers. A naive text-stream
        # parser will scramble them, while the coordinate parser must not.
        page.insert_text((28, 150), "Enunciado completo da primeira questao para testar o parser nativo.", fontsize=9)
        for y, key, text in [
            (210, "A", "Alternativa um"),
            (245, "B", "Alternativa correta"),
            (280, "C", "Alternativa tres"),
            (315, "D", "Alternativa quatro"),
        ]:
            page.insert_text((37, y), key, fontsize=9)
            page.insert_text((58, y), text, fontsize=9)

        page.insert_text((28, 490), "Enunciado completo da segunda questao para testar metadados.", fontsize=9)
        for y, key, text in [
            (535, "A", "Resposta certa"),
            (570, "B", "Resposta errada"),
            (605, "C", "Outra resposta"),
            (640, "D", "Ultima resposta"),
        ]:
            page.insert_text((37, y), key, fontsize=9)
            page.insert_text((58, y), text, fontsize=9)

        page.insert_text((28, 700), "Respostas", fontsize=9)
        page.insert_text((28, 720), "1: B", fontsize=9)
        page.insert_text((65, 720), "2: A", fontsize=9)
        document.save(path)
        document.close()

    def test_native_qconcursos_parser_uses_layout_and_skips_ocr(self) -> None:
        with patch("core.extractor.configure_tesseract", side_effect=AssertionError("OCR should not run")):
            result = extract_pdf(
                self.pdf,
                ExtractorConfig(dpi=120),
                taxonomy=self.taxonomy,
                asset_dir=self.root / "assets",
            )
        self.assertEqual(result["extractor_mode"], "texto_nativo_qconcursos_layout")
        self.assertEqual(result["starts_found"], 2)
        self.assertEqual(result["answers_found"], 2)
        self.assertEqual(len(result["questions"]), 2)
        q1 = result["questions"][0]
        self.assertIn("Enunciado completo da primeira", q1["enunciado"])
        self.assertEqual([item["chave"] for item in q1["alternativas"]], list("ABCD"))
        self.assertEqual(q1["alternativas"][1]["texto"], "Alternativa correta")
        self.assertEqual(q1["gabarito"], "B")

    def test_filename_hints_apply_matter_and_lesson(self) -> None:
        result = extract_pdf(self.pdf, ExtractorConfig(dpi=120), taxonomy=self.taxonomy)
        q1 = result["questions"][0]
        self.assertEqual(q1["materia"], "FLUÊNCIA EM DADOS")
        self.assertEqual(q1["aula_planilha"], "Aula 01")
        self.assertEqual(q1["assunto"], "BANCO DE DADOS RELACIONAIS")
        self.assertEqual(q1["classificacao_planilha"]["metodo"], "nome_arquivo_qconcursos")

    def test_metadata_labels_do_not_need_fixed_internal_order(self) -> None:
        result = extract_pdf(self.pdf, ExtractorConfig(dpi=120), taxonomy=self.taxonomy)
        q2 = result["questions"][1]
        self.assertEqual(q2["banca"], "CONSULPAM")
        self.assertEqual(q2["orgao"], "Prefeitura X")
        self.assertIn("Cargo A", q2["prova"])
        self.assertIn("Cargo B", q2["prova"])

    def test_reimport_repairs_broken_old_qconcursos_record(self) -> None:
        result = extract_pdf(self.pdf, ExtractorConfig(dpi=120), taxonomy=self.taxonomy)
        good = copy.deepcopy(result["questions"][0])
        broken = copy.deepcopy(good)
        broken["enunciado"] = ""
        broken["alternativas"] = []
        broken["gabarito"] = ""
        broken["ocr"]["metodo"] = "ocr_visual_antigo"
        broken["revisao"] = {"status": "pendente", "confianca": 0.3, "alertas": ["incompleta"]}

        database = QuestFlowDatabase(self.root / "questions.sqlite")
        first = database.import_extraction({"source_file": self.pdf.name, "questions": [broken]})
        second = database.import_extraction({"source_file": self.pdf.name, "questions": [good]})
        self.assertEqual(first["inserted"], 1)
        self.assertEqual(second["repaired"], 1)
        self.assertEqual(second["duplicates"], 0)
        saved = database.all_questions()[0]
        self.assertIn("Enunciado completo", saved["enunciado"])
        self.assertEqual(len(saved["alternativas"]), 4)
        self.assertEqual(saved["gabarito"], "B")


if __name__ == "__main__":
    unittest.main()
