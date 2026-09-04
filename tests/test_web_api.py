from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from app_shared import TAXONOMY_PATH
from core.storage import QuestFlowDatabase
from web_api import QuestFlowWebApi


class WebApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.db_path = self.root / "questions.sqlite"
        database = QuestFlowDatabase(self.db_path)
        question = {
            "id": "QWEB001",
            "codigo_origem": "QWEB001",
            "fingerprint": hashlib.sha256(b"qweb001").hexdigest(),
            "materia": "DIREITO TRIBUTÁRIO",
            "aula_planilha": "Aula 01",
            "assunto": "LIMITAÇÕES AO PODER DE TRIBUTAR",
            "assuntos": ["LIMITAÇÕES AO PODER DE TRIBUTAR"],
            "banca": "FGV",
            "ano": 2026,
            "orgao": "SEFAZ",
            "tipo": "multipla_escolha",
            "enunciado": "Assinale a alternativa correta.",
            "alternativas": [
                {"chave": "A", "texto": "Alternativa A"},
                {"chave": "B", "texto": "Alternativa B"},
            ],
            "gabarito": "A",
            "explicacao": "Explicação inicial.",
            "fonte": {"arquivo": "teste.pdf"},
            "classificacao_planilha": {"status": "classificado", "confianca": 1.0},
            "revisao": {"status": "pendente", "confianca": 0.7, "alertas": []},
        }
        result = database.import_extraction({"source_file": "teste.pdf", "questions": [question]})
        self.assertEqual(result["inserted"], 1)
        self.api = QuestFlowWebApi(
            self.db_path,
            config={"flow_target_retention": 0.88},
            config_path=self.root / "config.json",
            taxonomy_path=TAXONOMY_PATH,
        )

    def tearDown(self) -> None:
        self.api.shutdown()
        self.temp.cleanup()

    def test_bootstrap_and_virtual_list_payload(self) -> None:
        bootstrap = self.api.bootstrap()
        self.assertEqual(bootstrap["stats"]["total"], 1)
        listing = self.api.list_questions(limit=50)
        self.assertEqual(listing["total"], 1)
        self.assertEqual(listing["items"][0]["codigo"], "QWEB001")
        self.assertEqual(listing["items"][0]["materia"], "DIREITO TRIBUTÁRIO")

    def test_save_and_approve_question(self) -> None:
        uid = self.api.list_questions()["items"][0]["uid"]
        payload = {
            "materia": "DIREITO TRIBUTÁRIO",
            "aula_planilha": "Aula 01",
            "assunto": "LIMITAÇÕES AO PODER DE TRIBUTAR",
            "assuntos": "LIMITAÇÕES AO PODER DE TRIBUTAR | IMUNIDADES",
            "banca": "FGV",
            "ano": "2026",
            "orgao": "SEFAZ",
            "prova": "Auditor Fiscal",
            "cargo": "Auditor",
            "area": "Tributária",
            "especialidade": "",
            "turno": "Manhã",
            "tipo": "multipla_escolha",
            "gabarito": "B",
            "enunciado": "Enunciado revisado e completo.",
            "alternativas": [
                {"chave": "A", "texto": "Primeira"},
                {"chave": "B", "texto": "Segunda"},
            ],
            "explicacao": "Explicação revisada.",
        }
        result = self.api.save_question(uid, payload, True)
        self.assertTrue(result["ok"])
        self.assertEqual(result["question"]["gabarito"], "B")
        self.assertEqual(result["question"]["revisao"]["status"], "aprovado")
        self.assertIn("IMUNIDADES", result["question"]["assuntos"])

    def test_invalid_answer_is_rejected(self) -> None:
        uid = self.api.list_questions()["items"][0]["uid"]
        question = self.api.get_question(uid)["question"]
        question["gabarito"] = "Z"
        result = self.api.save_question(uid, question, False)
        self.assertFalse(result["ok"])
        self.assertIn("gabarito", result["error"].lower())

    def test_question_code_can_be_renamed_with_audit(self) -> None:
        uid = self.api.list_questions()["items"][0]["uid"]
        question = self.api.get_question(uid)["question"]
        question["codigo_origem"] = "QWEB-NOVO"
        result = self.api.save_question(uid, question, False)
        self.assertTrue(result["ok"])
        self.assertTrue(result["code_change"]["code_changed"])
        self.assertEqual(result["question"]["codigo_origem"], "QWEB-NOVO")
        self.assertEqual(result["question"]["historico_codigos"][0]["old_code"], "QWEB001")
        listing = self.api.list_questions(limit=50)
        self.assertEqual(listing["items"][0]["codigo"], "QWEB-NOVO")


if __name__ == "__main__":
    unittest.main()
