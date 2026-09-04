from __future__ import annotations

import hashlib
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from core.storage import QuestFlowDatabase
from core.study import StudyRepository


class QuestionCodeRename524Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp.name) / "questions.sqlite"
        self.database = QuestFlowDatabase(self.db_path)
        self.study = StudyRepository(self.database)

    def tearDown(self) -> None:
        self.temp.cleanup()

    @staticmethod
    def question(code: str, *, fingerprint_seed: str | None = None) -> dict:
        seed = fingerprint_seed or code
        return {
            "id": code,
            "codigo_origem": code,
            "fingerprint": hashlib.sha256(seed.encode("utf-8")).hexdigest(),
            "materia": "DIREITO TRIBUTÁRIO",
            "aula_planilha": "Aula 01",
            "assunto": "LIMITAÇÕES AO PODER DE TRIBUTAR",
            "assuntos": ["LIMITAÇÕES AO PODER DE TRIBUTAR"],
            "banca": "FGV",
            "ano": 2026,
            "tipo": "multipla_escolha",
            "enunciado": "Enunciado sintético.",
            "alternativas": [
                {"chave": "A", "texto": "Alternativa A"},
                {"chave": "B", "texto": "Alternativa B"},
            ],
            "gabarito": "A",
            "fonte": {"arquivo": "teste.pdf", "codigo": code},
            "pesquisa": {"question_code": code, "query": "texto sem alteração"},
            "revisao": {"status": "pendente", "confianca": 0.8, "alertas": []},
        }

    def import_one(self, code: str, seed: str | None = None) -> str:
        result = self.database.import_extraction(
            {"source_file": "teste.pdf", "questions": [self.question(code, fingerprint_seed=seed)]}
        )
        self.assertEqual(result["inserted"], 1)
        with self.database.connect() as connection:
            return str(connection.execute("SELECT uid FROM questions WHERE source_code = ?", (code,)).fetchone()[0])

    def test_code_change_updates_all_identity_fields_and_preserves_uid_relations(self) -> None:
        uid = self.import_one("QANTIGO")
        with self.database.connect() as connection:
            connection.execute(
                "INSERT INTO study_state(question_uid, sent_count) VALUES (?, ?)",
                (uid, 3),
            )

        question = self.database.get_question(uid)
        assert question is not None
        question["codigo_origem"] = "QNOVO"
        result = self.database.update_question(uid, question, change_source="teste_automatizado")

        self.assertTrue(result["code_changed"])
        self.assertEqual(result["old_code"], "QANTIGO")
        self.assertEqual(result["new_code"], "QNOVO")

        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT uid, source_key, source_code, fingerprint, data_json FROM questions WHERE uid = ?",
                (uid,),
            ).fetchone()
            state = connection.execute(
                "SELECT sent_count FROM study_state WHERE question_uid = ?", (uid,)
            ).fetchone()
            audit = connection.execute(
                "SELECT old_code, new_code, changed_via FROM question_code_history WHERE question_uid = ?",
                (uid,),
            ).fetchone()

        self.assertEqual(row["uid"], uid)
        self.assertEqual(row["source_code"], "QNOVO")
        self.assertEqual(row["source_key"], "QNOVO")
        self.assertEqual(state["sent_count"], 3)
        payload = json.loads(row["data_json"])
        self.assertEqual(payload["codigo_origem"], "QNOVO")
        self.assertEqual(payload["id"], "QNOVO")
        self.assertEqual(payload["fonte"]["codigo"], "QNOVO")
        self.assertEqual(payload["pesquisa"]["question_code"], "QNOVO")
        self.assertEqual(payload["historico_codigos"][-1]["codigo_anterior"], "QANTIGO")
        self.assertEqual(payload["historico_codigos"][-1]["codigo_novo"], "QNOVO")
        self.assertEqual(audit["old_code"], "QANTIGO")
        self.assertEqual(audit["new_code"], "QNOVO")
        self.assertEqual(audit["changed_via"], "teste_automatizado")

    def test_duplicate_code_is_rejected_without_partial_update(self) -> None:
        first = self.import_one("Q001", seed="one")
        second = self.import_one("Q002", seed="two")
        question = self.database.get_question(second)
        assert question is not None
        question["codigo_origem"] = "q001"

        with self.assertRaisesRegex(ValueError, "Já existe outra questão"):
            self.database.update_question(second, question, change_source="teste")

        with self.database.connect() as connection:
            first_code = connection.execute("SELECT source_code FROM questions WHERE uid = ?", (first,)).fetchone()[0]
            second_code = connection.execute("SELECT source_code FROM questions WHERE uid = ?", (second,)).fetchone()[0]
            history_count = connection.execute("SELECT COUNT(*) FROM question_code_history").fetchone()[0]
        self.assertEqual(first_code, "Q001")
        self.assertEqual(second_code, "Q002")
        self.assertEqual(history_count, 0)

    def test_code_history_migration_is_present(self) -> None:
        with closing(sqlite3.connect(self.db_path)) as connection:
            table = connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='question_code_history'"
            ).fetchone()
        self.assertIsNotNone(table)


if __name__ == "__main__":
    unittest.main()
