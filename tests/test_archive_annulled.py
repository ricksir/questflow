from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from core.storage import QuestFlowDatabase


class ArchiveAnnulledTests(unittest.TestCase):
    def test_annulled_question_leaves_active_bank_and_is_not_reimported(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            database = QuestFlowDatabase(Path(temp) / "questions.sqlite")
            question = {
                "id": "Q1",
                "codigo_origem": "Q1",
                "fingerprint": "fingerprint-q1",
                "materia": "CONTABILIDADE PÚBLICA",
                "assuntos": ["Balanço financeiro"],
                "enunciado": "Questão de teste",
                "alternativas": [
                    {"chave": "A", "texto": "Sim"},
                    {"chave": "B", "texto": "Não"},
                ],
                "gabarito": "A",
                "tipo": "multipla_escolha",
                "fonte": {"arquivo": "teste.pdf"},
                "revisao": {"status": "pendente", "confianca": 0.5, "alertas": []},
            }
            result = database.import_extraction({"source_file": "teste.pdf", "questions": [question]})
            self.assertEqual(result["inserted"], 1)
            uid = database.list_questions()[0]["uid"]
            self.assertTrue(database.archive_question(uid, kind="anulada", reason="Banca anulou"))
            self.assertEqual(database.stats()["total"], 0)
            self.assertEqual(database.excluded_count("anulada"), 1)
            result_again = database.import_extraction({"source_file": "teste.pdf", "questions": [question]})
            self.assertEqual(result_again["inserted"], 0)
            self.assertEqual(result_again["duplicates"], 1)


if __name__ == "__main__":
    unittest.main()
