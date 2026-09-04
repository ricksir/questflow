from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from core.health import collect_health
from core.storage import QuestFlowDatabase
from core.study import StudyRepository


class HealthTests(unittest.TestCase):
    def test_collects_database_health(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            path = Path(temp_name) / "health.sqlite"
            database = QuestFlowDatabase(path)
            StudyRepository(database)
            snapshot = collect_health(path)
            self.assertIn(snapshot.status, {"operacional", "atenção"})
            self.assertGreaterEqual(snapshot.database_latency_ms, 0)
            self.assertEqual(snapshot.failed_deliveries, 0)


if __name__ == "__main__":
    unittest.main()
