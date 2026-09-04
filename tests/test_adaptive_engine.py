from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from core.adaptive_engine import (
    MemoryState,
    OnlineRecallModel,
    adaptive_priority_score,
    forgetting_curve,
    interval_for_retention,
    update_memory_state,
)
from core.storage import QuestFlowDatabase
from core.study import StudyRepository


class AdaptiveEngineTests(unittest.TestCase):
    def test_forgetting_curve_is_monotonic(self) -> None:
        values = [forgetting_curve(day, 10.0) for day in (0, 2, 5, 10, 20)]
        self.assertEqual(values[0], 1.0)
        self.assertTrue(all(a >= b for a, b in zip(values, values[1:])))
        self.assertAlmostEqual(forgetting_curve(10, 10), 0.9, places=5)

    def test_retention_target_changes_interval(self) -> None:
        high = interval_for_retention(20.0, 0.95)
        normal = interval_for_retention(20.0, 0.88)
        low = interval_for_retention(20.0, 0.80)
        self.assertLess(high, normal)
        self.assertLess(normal, low)

    def test_memory_update_rewards_recall_and_penalizes_lapse(self) -> None:
        state = MemoryState(difficulty=5.0, stability_days=5.0)
        correct, correct_interval = update_memory_state(
            state, correct=True, elapsed_days=5.0, response_seconds=20
        )
        wrong, wrong_interval = update_memory_state(
            state, correct=False, elapsed_days=5.0, response_seconds=20
        )
        self.assertGreater(correct.stability_days, state.stability_days)
        self.assertLess(wrong.stability_days, state.stability_days)
        self.assertLess(correct.difficulty, state.difficulty)
        self.assertGreater(wrong.difficulty, state.difficulty)
        self.assertGreater(correct_interval, wrong_interval)

    def test_online_model_learns_direction(self) -> None:
        model = OnlineRecallModel.default()
        state = MemoryState(difficulty=6.0, stability_days=2.0)
        features = model.features(
            state=state,
            elapsed_days=3.0,
            historical_accuracy=0.5,
            response_seconds=40,
            is_new=False,
            autoapproved=False,
        )
        before = model.predict(features)
        for _ in range(30):
            model.update(features, True)
        after_success = model.predict(features)
        self.assertGreater(after_success, before)
        for _ in range(60):
            model.update(features, False)
        after_failure = model.predict(features)
        self.assertLess(after_failure, after_success)

    def test_priority_prefers_low_recall_and_overdue(self) -> None:
        easy = adaptive_priority_score(
            predicted_recall=0.95,
            retrievability=0.95,
            overdue_days=0,
            is_new=False,
            sent_count=5,
        )
        risky = adaptive_priority_score(
            predicted_recall=0.35,
            retrievability=0.30,
            overdue_days=12,
            is_new=False,
            sent_count=5,
        )
        self.assertGreater(risky, easy)

    def test_repository_dashboard_and_model_migration(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            db = QuestFlowDatabase(Path(folder) / "adaptive.sqlite")
            study = StudyRepository(db)
            summary = study.adaptive_dashboard()
            self.assertEqual(summary["total"], 0)
            self.assertEqual(summary["model"]["version"], "qf-adaptive-1")
            self.assertAlmostEqual(study.set_target_retention(0.91), 0.91)


if __name__ == "__main__":
    unittest.main()
