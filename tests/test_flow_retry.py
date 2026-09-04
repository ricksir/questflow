from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.flow import CyclicStudyEngine
from core.storage import QuestFlowDatabase
from core.study import StudyRepository


class FlowRetryTests(unittest.TestCase):
    def test_retry_resolves_failed_delivery(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            database = QuestFlowDatabase(Path(temp) / "retry.sqlite")
            uid = database.create_manual_question(None)
            study = StudyRepository(database)
            failed_id = study.record_delivery_error(
                uid,
                "123",
                "Falha temporária",
                "cycle-retry",
                category="conexao_temporaria",
                retryable=True,
                attempt_count=1,
            )
            events: list[tuple[str, dict]] = []
            engine = CyclicStudyEngine(
                database,
                study,
                lambda: {
                    "telegram_bot_token": "token",
                    "telegram_chat_id": "123",
                    "flow_question_retry_attempts": 3,
                    "flow_retry_minutes": 10,
                },
                lambda name, payload: events.append((name, payload)),
            )
            fake_result = {
                "ok": True,
                "direct_poll": True,
                "_attempt_count": 1,
                "poll": {"result": {"message_id": 7, "poll": {"id": "poll-retry"}}},
            }
            with patch("core.flow.send_quiz_with_retry", return_value=fake_result):
                result = engine._retry_delivery(failed_id, requested_via="teste")
            self.assertTrue(result["sent"])
            old = study.get_delivery(failed_id)
            self.assertEqual(old["status"], "reenviado")
            self.assertTrue(old["resolved_by_delivery_id"])
            self.assertTrue(any(name == "retry_sent" for name, _ in events))


if __name__ == "__main__":
    unittest.main()
