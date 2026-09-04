from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from core.cloud_sync import CloudSyncEngine
from core.engines.learning_engine import LearningEngine
from core.storage import QuestFlowDatabase
from core.study import SelectionFilters, StudyRepository
from tests.test_cloud_sync_5_4_0 import FakeRemote


class CloudSyncRefresh662Tests(unittest.TestCase):
    def _make(self, root: Path):
        db = QuestFlowDatabase(root / "questflow.sqlite")
        study = StudyRepository(db)
        remote = FakeRemote()
        config = {
            "cloud_sync_enabled": True,
            "cloud_device_name": "REFRESH-TEST",
            "cloud_sync_interval_seconds": 30,
        }
        engine = CloudSyncEngine(
            db.path,
            config=config,
            config_path=root / "config.json",
            remote_client=remote,
            auth_token="unit",
        )
        learning = LearningEngine(db, study)
        return db, study, engine, learning

    @staticmethod
    def _seed(db: QuestFlowDatabase, study: StudyRepository, count: int = 24) -> list[str]:
        uids: list[str] = []
        for index in range(count):
            uid = db.create_manual_question()
            question = db.get_question(uid)
            question["materia"] = "DIREITO TRIBUTÁRIO"
            question["assunto"] = f"Assunto {index % 6}"
            question["aula_planilha"] = f"Aula {index % 4 + 1:02d}"
            question["banca"] = "CEBRASPE"
            question["enunciado"] = f"Questão de teste {index}"
            question["alternativas"] = ["Certo", "Errado"]
            question["correta"] = 0
            db.update_question(uid, question)
            uids.append(uid)
        study.sync_questions()
        with db.connect() as connection:
            connection.execute("UPDATE questions SET review_status='aprovado'")
            # Tornar a seleção adaptativa determinística o suficiente para ter candidatos.
            connection.execute(
                "UPDATE study_state SET due_at=?, sent_count=1, correct_count=1 WHERE question_uid IN (%s)"
                % ",".join("?" for _ in uids[:12]),
                (datetime(2026, 8, 1, tzinfo=timezone.utc).isoformat(), *uids[:12]),
            )
        return uids

    def test_transient_study_state_updates_do_not_enter_cloud_outbox(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            db, study, cloud, _learning = self._make(root)
            uid = self._seed(db, study, 1)[0]
            self.assertTrue(cloud.sync_until_idle()["ok"])
            self.assertEqual(cloud.pending_count(), 0)
            with db.connect() as connection:
                connection.execute(
                    """
                    UPDATE study_state
                    SET memory_retrievability=0.713, adaptive_prediction=0.688,
                        adaptive_priority=42.5, last_selection_reason='preview',
                        last_selection_bucket='2'
                    WHERE question_uid=?
                    """,
                    (uid,),
                )
            self.assertEqual(cloud.pending_count(), 0)

    def test_durable_study_state_update_still_enters_cloud_outbox(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            db, study, cloud, _learning = self._make(root)
            uid = self._seed(db, study, 1)[0]
            self.assertTrue(cloud.sync_until_idle()["ok"])
            with db.connect() as connection:
                connection.execute(
                    "UPDATE study_state SET correct_count=correct_count+1 WHERE question_uid=?",
                    (uid,),
                )
            queue = cloud.pending_details()
            self.assertEqual(queue["total"], 1)
            self.assertEqual(queue["groups"][0]["table_name"], "study_state")

    def test_recommendation_preview_after_sync_is_read_only(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            db, study, cloud, learning = self._make(root)
            self._seed(db, study, 24)
            self.assertTrue(cloud.sync_until_idle(max_rounds=10)["ok"])
            self.assertEqual(cloud.pending_count(), 0)

            first = learning.recommendation_dashboard(mode="equilibrado", limit=8)
            self.assertTrue(first["recommendations"])
            self.assertEqual(cloud.pending_count(), 0, cloud.pending_details())

            second = learning.recommendation_dashboard(mode="edital", limit=8)
            self.assertTrue(second["recommendations"])
            self.assertEqual(cloud.pending_count(), 0, cloud.pending_details())

    def test_operational_selection_can_persist_transient_scores_without_sync_noise(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            db, study, cloud, _learning = self._make(root)
            self._seed(db, study, 20)
            self.assertTrue(cloud.sync_until_idle(max_rounds=10)["ok"])
            result = study.select_questions(
                SelectionFilters(subjects=[], approved_only=True, strategy="adaptativo"),
                8,
                persist_state=True,
            )
            self.assertTrue(result)
            # A seleção operacional pode materializar scores locais, mas eles são
            # derivados e não representam alterações que precisam ir ao Turso.
            self.assertEqual(cloud.pending_count(), 0, cloud.pending_details())


if __name__ == "__main__":
    unittest.main()
