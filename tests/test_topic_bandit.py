from __future__ import annotations

import unittest

from core.topic_bandit import TopicState, topic_priority, rank_topics


class TopicBanditTests(unittest.TestCase):
    def test_weak_topic_has_higher_priority(self) -> None:
        weak = TopicState("A", "fraco", correct=1, wrong=6, exposures=7, last_seen_days=20)
        strong = TopicState("A", "forte", correct=10, wrong=1, exposures=11, last_seen_days=2)
        self.assertGreater(
            topic_priority(weak, total_exposures=30, predicted_recall=0.35),
            topic_priority(strong, total_exposures=30, predicted_recall=0.90),
        )

    def test_unseen_topic_receives_exploration_bonus(self) -> None:
        unseen = TopicState("A", "novo")
        seen = TopicState("A", "visto", correct=2, wrong=2, exposures=20)
        self.assertGreater(
            topic_priority(unseen, total_exposures=100, predicted_recall=0.5),
            topic_priority(seen, total_exposures=100, predicted_recall=0.5),
        )

    def test_ranking_is_reproducible(self) -> None:
        states = [TopicState("A", str(i), correct=i, wrong=5-i, exposures=5) for i in range(5)]
        first = [item.topic for _score, item in rank_topics(states, total_exposures=25, seed=42)]
        second = [item.topic for _score, item in rank_topics(states, total_exposures=25, seed=42)]
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
