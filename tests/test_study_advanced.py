from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from core.storage import QuestFlowDatabase
from core.study import StudyRepository


class StudyAdvancedTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="questflow-410-")
        self.db = QuestFlowDatabase(Path(self.temp.name) / "study.sqlite")
        self.study = StudyRepository(self.db)
        self.uid = self.db.create_manual_question(None)
        question = self.db.get_question(self.uid)
        assert question is not None
        question.update({
            "materia": "AUDITORIA",
            "aula_planilha": "Aula 01",
            "assunto": "Evidências",
            "enunciado": "Questão de teste avançado",
            "alternativas": [
                {"chave": "A", "texto": "Correta"},
                {"chave": "B", "texto": "Incorreta"},
            ],
            "gabarito": "A",
            "telegram": {"indice_correto": 0},
            "revisao": {"status": "aprovado", "confianca": 1.0, "alertas": []},
        })
        self.db.update_question(self.uid, question)
        self.study.sync_questions()

    def tearDown(self) -> None:
        self.temp.cleanup()

    @staticmethod
    def send_result() -> dict:
        return {"direct_poll": True, "poll": {"result": {"message_id": 1, "poll": {"id": "poll-410"}}}}

    def test_answer_updates_topic_and_profile(self) -> None:
        self.study.record_delivery(self.uid, "123", self.send_result(), "cycle")
        answer = self.study.record_poll_answer({
            "poll_id": "poll-410",
            "user": {"id": 1, "username": "teste"},
            "option_ids": [0],
        })
        self.assertIsNotNone(answer)
        assert answer is not None
        reward = answer["state"].get("reward")
        self.assertTrue(reward and reward["xp"] > 0)
        dashboard = self.study.adaptive_dashboard()
        self.assertGreater(dashboard["profile"]["total_xp"], 0)
        self.assertEqual(dashboard["topic_count"], 1)
        with self.db.connect() as connection:
            row = connection.execute(
                "SELECT exposure_count, correct_count FROM topic_learning_state WHERE subject = ? AND topic = ?",
                ("AUDITORIA", "Evidências"),
            ).fetchone()
        self.assertEqual(row["exposure_count"], 1)
        self.assertEqual(row["correct_count"], 1)

    def test_duplicate_answer_does_not_duplicate_xp(self) -> None:
        self.study.record_delivery(self.uid, "123", self.send_result(), "cycle")
        payload = {"poll_id": "poll-410", "user": {"id": 1}, "option_ids": [0]}
        self.study.record_poll_answer(payload)
        before = self.study.learner_profile()["total_xp"]
        self.study.record_poll_answer(payload)
        after = self.study.learner_profile()["total_xp"]
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
