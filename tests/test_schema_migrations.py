from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from core.storage import QuestFlowDatabase
from core.study import StudyRepository


class SchemaMigrationTests(unittest.TestCase):
    def test_question_and_study_migrations_are_versioned_and_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = QuestFlowDatabase(Path(directory) / "questflow.sqlite")
            first = database.schema_history()
            self.assertEqual([1, 2, 3, 4, 5, 6, 7, 9], [item["version"] for item in first if item["component"] == "question_bank"])

            StudyRepository(database)
            after_study = database.schema_history()
            self.assertEqual([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12], [item["version"] for item in after_study if item["component"] == "study"])

            # Reabrir não pode repetir nem alterar o histórico.
            QuestFlowDatabase(database.path)
            StudyRepository(database)
            final = database.schema_history()
            keys = [(item["component"], item["version"]) for item in final]
            self.assertEqual(len(keys), len(set(keys)))
            self.assertEqual(after_study, final)

    def test_calibration_columns_exist_after_study_migration(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = QuestFlowDatabase(Path(directory) / "questflow.sqlite")
            StudyRepository(database)
            with database.connect() as connection:
                columns = {row[1] for row in connection.execute("PRAGMA table_info(telegram_attempts)")}
            self.assertTrue({"predicted_probability", "prediction_model_version", "response_seconds", "learner_predicted_probability", "learner_prediction_confidence", "learner_prediction_status", "learner_prediction_version", "response_wall_seconds", "response_idle_seconds", "timing_quality", "timing_source", "question_revision", "account_id", "tenant_id", "learner_id", "exam_project_id", "device_id", "session_id"}.issubset(columns))


if __name__ == "__main__":
    unittest.main()
