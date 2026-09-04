from __future__ import annotations

import hashlib
import queue
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

import pymupdf

import app as app_module
import app_classic as classic_module
from app import QuestFlowApp
from core.spreadsheet_taxonomy import SpreadsheetTaxonomy
from core.storage import QuestFlowDatabase


class DeepAnalysisIntegrationTests(unittest.TestCase):
    def test_pending_question_relocates_and_rereads_pdf(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            pdf_path = root / "lista_original.pdf"
            doc = pymupdf.open()
            page = doc.new_page()
            page.insert_textbox(
                pymupdf.Rect(45, 45, 550, 800),
                (
                    "LISTA DE QUESTÕES\n\n"
                    "1. (CEBRASPE / TCU - 2025) Julgue o item a seguir.\n"
                    "O controle interno auxilia o trabalho da auditoria.\n\n"
                    "GABARITO\n"
                    "1. CORRETO\n"
                ),
                fontsize=10,
            )
            doc.save(pdf_path)
            doc.close()

            database = QuestFlowDatabase(root / "questions.sqlite")
            fingerprint = hashlib.sha256(b"pending-reread").hexdigest()
            question = {
                "id": "QTESTE",
                "numero_origem": 1,
                "codigo_origem": "QTESTE",
                "fingerprint": fingerprint,
                "materia": "AUDITORIA",
                "assunto": "CONTROLE INTERNO",
                "assuntos": ["CONTROLE INTERNO"],
                "trilha_assuntos": ["AUDITORIA", "CONTROLE INTERNO"],
                "banca": "CEBRASPE",
                "ano": 2025,
                "orgao": "TCU",
                "prova": "",
                "tipo": "multipla_escolha",
                "enunciado": "Texto incompleto",
                "alternativas": [],
                "gabarito": "",
                "explicacao": "",
                "fonte": {
                    "arquivo": pdf_path.name,
                    "caminho_arquivo": r"C:\pasta-antiga\lista_original.pdf",
                },
                "classificacao_planilha": {"status": "classificado", "confianca": 1.0},
                "revisao": {"status": "pendente", "confianca": 0.2, "alertas": ["incompleta"]},
            }
            result = database.import_extraction({"source_file": pdf_path.name, "questions": [question]})
            self.assertEqual(result["inserted"], 1)
            uid = database.list_questions(status="pendente", limit=10)[0]["uid"]

            worker = object.__new__(QuestFlowApp)
            worker.database = database
            worker.taxonomy = SpreadsheetTaxonomy.load(app_module.TAXONOMY_PATH)
            worker.config_data = {
                "dpi": 180,
                "deep_analysis_dpi": 300,
                "languages": "por+eng",
                "tesseract_cmd": "",
                "markdown_force_ocr_pending": True,
                "web_enrichment_enabled": False,
                "web_enrichment_max_per_run": 0,
            }
            worker.deep_process_cancel_event = threading.Event()
            worker.event_queue = queue.Queue()

            with patch.object(classic_module, "QUESTION_IMAGE_DIR", root / "images"), patch.object(
                classic_module, "MARKDOWN_CACHE_DIR", root / "markdown"
            ):
                worker._deep_process_worker([uid], [str(root)])

            updated = database.get_question(uid)
            self.assertIsNotNone(updated)
            self.assertEqual(updated["tipo"], "certo_errado")
            self.assertEqual(updated["gabarito"], "C")
            self.assertEqual(len(updated["alternativas"]), 2)
            self.assertEqual(Path(updated["fonte"]["caminho_arquivo"]), pdf_path.resolve())
            events = []
            while not worker.event_queue.empty():
                events.append(worker.event_queue.get_nowait())
            done = [event for event in events if event[0] == "deep_done"]
            self.assertEqual(len(done), 1)
            self.assertEqual(done[0][1]["reread"], 1)
            self.assertEqual(done[0][1]["source_missing"], 0)


if __name__ == "__main__":
    unittest.main()
