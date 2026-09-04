from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from core.storage import QuestFlowDatabase
from core.study import (
    StudyRepository,
    adaptive_interval_days,
    bayesian_error_probability,
    recency_priority,
)


class StudyRetryMathTests(unittest.TestCase):
    def test_bayesian_error_probability(self) -> None:
        self.assertGreater(bayesian_error_probability(1, 4), bayesian_error_probability(4, 1))
        self.assertGreater(bayesian_error_probability(0, 0), 0.0)
        self.assertLess(bayesian_error_probability(0, 0), 1.0)

    def test_recency_priority(self) -> None:
        self.assertLess(recency_priority(1), recency_priority(30))

    def test_adaptive_interval(self) -> None:
        weak = adaptive_interval_days(streak=3, ease=1.5, correct=2, wrong=4)
        strong = adaptive_interval_days(streak=3, ease=3.0, correct=20, wrong=1)
        self.assertGreater(strong, weak)

    def test_failed_delivery_lifecycle(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            db = QuestFlowDatabase(Path(temp) / "db.sqlite")
            uid = db.create_manual_question(None)
            study = StudyRepository(db)
            delivery_id = study.record_delivery_error(
                uid,
                "123",
                "Timeout",
                "cycle-test",
                category="conexao_temporaria",
                retryable=True,
                next_retry_at=None,
                attempt_count=1,
            )
            failed = study.get_delivery(delivery_id)
            self.assertEqual(failed["status"], "erro")
            self.assertEqual(failed["error_category"], "conexao_temporaria")
            attempt = study.mark_retry_started(delivery_id)
            self.assertEqual(attempt, 2)
            study.restore_retry_error(
                delivery_id,
                "Ainda sem conexão",
                category="conexao_temporaria",
                retryable=True,
                next_retry_at=None,
            )
            self.assertEqual(study.get_delivery(delivery_id)["status"], "erro")


if __name__ == "__main__":
    unittest.main()
