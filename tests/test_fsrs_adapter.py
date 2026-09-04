from __future__ import annotations

import sys
import types
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from core.fsrs_adapter import review_with_fsrs


class _FakeRating(int):
    pass


class _FakeCard:
    def __init__(self):
        self.due = datetime.now(timezone.utc)
        self.stability = 2.0
        self.difficulty = 4.5

    @classmethod
    def from_json(cls, _raw):
        return cls()

    def to_json(self):
        return '{"fake": true}'


class _FakeScheduler:
    def __init__(self, desired_retention=0.9):
        self.desired_retention = desired_retention

    def review_card(self, card, rating, review_datetime=None):
        card.due = (review_datetime or datetime.now(timezone.utc)) + timedelta(days=3)
        card.stability = 4.0
        card.difficulty = 4.0
        return card, object()

    def get_card_retrievability(self, card, current_datetime=None):
        return 0.91


class FSRSAdapterTests(unittest.TestCase):
    def test_safe_fallback_when_dependency_missing(self) -> None:
        with patch("importlib.import_module", side_effect=ImportError("missing")):
            self.assertIsNone(review_with_fsrs(
                None, correct=True, response_seconds=20, prior_accuracy=0.7,
                desired_retention=0.88,
            ))

    def test_uses_public_scheduler_api(self) -> None:
        module = types.SimpleNamespace(
            Scheduler=_FakeScheduler,
            Card=_FakeCard,
            Rating=_FakeRating,
            __version__="fake-6",
        )
        with patch("importlib.import_module", return_value=module):
            result = review_with_fsrs(
                None, correct=True, response_seconds=20, prior_accuracy=0.7,
                desired_retention=0.88,
                now=datetime(2026, 1, 1, tzinfo=timezone.utc),
            )
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.rating, 3)
        self.assertEqual(result.scheduler_version, "fake-6")
        self.assertGreater(result.stability, 2)


if __name__ == "__main__":
    unittest.main()
