from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from core.calibration import brier_score, log_loss, calibration_report
from core.storage import QuestFlowDatabase
from core.study import StudyRepository, utc_now


class CalibrationTests(unittest.TestCase):
    def test_good_probabilities_score_better_than_inverted_probabilities(self) -> None:
        outcomes = [1, 1, 0, 0]
        good = [0.9, 0.8, 0.2, 0.1]
        bad = [0.1, 0.2, 0.8, 0.9]
        self.assertLess(brier_score(good, outcomes), brier_score(bad, outcomes))
        self.assertLess(log_loss(good, outcomes), log_loss(bad, outcomes))

    def test_report_contains_bins_and_ece(self) -> None:
        report = calibration_report([0.1, 0.2, 0.8, 0.9], [0, 0, 1, 1], bin_count=5)
        payload = report.to_dict()
        self.assertEqual(4, payload["samples"])
        self.assertGreaterEqual(payload["expected_calibration_error"], 0.0)
        self.assertTrue(payload["bins"])

    def test_repository_reads_persisted_predictions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = QuestFlowDatabase(Path(directory) / "questflow.sqlite")
            repository = StudyRepository(database)
            uid = database.create_manual_question()
            now = utc_now()
            with database.connect() as connection:
                connection.execute(
                    "INSERT INTO telegram_deliveries(id, cycle_id, question_uid, chat_id, sent_at) VALUES ('d1', 'c1', ?, '1', ?)",
                    (uid, now),
                )
                connection.execute(
                    """
                    INSERT INTO telegram_attempts(
                        id, delivery_id, question_uid, poll_id, user_id,
                        selected_indices_json, is_correct, answered_at,
                        predicted_probability, prediction_model_version, response_seconds
                    ) VALUES ('a1', 'd1', ?, 'p1', 'u1', '[0]', 1, ?, 0.8, 'test', 12.0)
                    """,
                    (uid, now),
                )
            report = repository.calibration_report()
            self.assertEqual(1, report["samples"])
            self.assertAlmostEqual(0.04, report["brier"], places=6)


if __name__ == "__main__":
    unittest.main()
