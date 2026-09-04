from __future__ import annotations

import unittest

from core.gamification import calculate_reward, level_from_xp


class GamificationTests(unittest.TestCase):
    def test_level_curve_is_monotonic(self) -> None:
        previous = 0
        for xp in range(0, 5000, 25):
            level, progress = level_from_xp(xp)
            self.assertGreaterEqual(level, previous)
            self.assertGreaterEqual(progress, 0.0)
            self.assertLessEqual(progress, 1.0)
            previous = level

    def test_correct_hard_question_rewards_more(self) -> None:
        easy = calculate_reward(
            correct=True, difficulty=2, response_seconds=25, streak=1,
            first_attempt=False, total_xp_before=100,
        )
        hard = calculate_reward(
            correct=True, difficulty=9, response_seconds=25, streak=1,
            first_attempt=False, total_xp_before=100,
        )
        self.assertGreater(hard.xp, easy.xp)

    def test_error_still_produces_small_learning_feedback(self) -> None:
        reward = calculate_reward(
            correct=False, difficulty=7, response_seconds=60, streak=0,
            first_attempt=True, total_xp_before=0,
        )
        self.assertGreater(reward.xp, 0)
        self.assertLess(reward.xp, 14)


if __name__ == "__main__":
    unittest.main()
