from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from core.flow import CyclicStudyEngine
from core.storage import QuestFlowDatabase
from core.study import SelectionFilters, StudyRepository


class CycleSafetyAndPriorityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="qf-3014-")
        self.db = QuestFlowDatabase(Path(self.temp.name) / "test.sqlite")
        self.study = StudyRepository(self.db)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def make_question(self, code: str, status: str, subject: str = "AUDITORIA") -> str:
        uid = self.db.create_manual_question(None)
        question = self.db.get_question(uid)
        assert question is not None
        question["codigo_origem"] = code
        question["id"] = code
        question["materia"] = subject
        question["aula_planilha"] = "Aula 01"
        question["assunto"] = "Assunto"
        question["enunciado"] = f"Enunciado {code}"
        question["alternativas"] = [
            {"chave": "A", "texto": "Certa"},
            {"chave": "B", "texto": "Errada"},
        ]
        question["gabarito"] = "A"
        question["telegram"] = {"indice_correto": 0}
        question["revisao"] = {"status": status, "confianca": 1.0, "alertas": []}
        self.db.update_question(uid, question)
        self.study.sync_questions()
        return uid

    @staticmethod
    def send_result(poll_id: str, message_id: int) -> dict:
        return {
            "direct_poll": True,
            "poll": {"result": {"message_id": message_id, "poll": {"id": poll_id}}},
        }

    def test_approved_precedes_autoapproved(self) -> None:
        approved = self.make_question("Q-APROVADA", "aprovado")
        automatic = self.make_question("Q-AUTO", "aprovado_automaticamente")
        filters = SelectionFilters(subjects=[], approved_only=True, strategy="auditor_inteligente")
        first = self.study.select_questions(filters, 1)
        self.assertEqual(first[0]["database_uid"], approved)
        both = self.study.select_questions(filters, 2)
        self.assertEqual(both[0]["database_uid"], approved)
        self.assertIn(automatic, [item["database_uid"] for item in both])

    def test_correction_suspends_then_reactivates_with_priority(self) -> None:
        corrected = self.make_question("Q-CORRIGIR", "aprovado")
        other = self.make_question("Q-OUTRA", "aprovado")
        request = self.study.create_review_request(corrected, user_id="1")
        with self.db.connect() as connection:
            state = connection.execute(
                "SELECT suspended, correction_priority FROM study_state WHERE question_uid = ?",
                (corrected,),
            ).fetchone()
        self.assertEqual(state["suspended"], 1)
        available = self.study.select_questions(
            SelectionFilters(subjects=[], approved_only=True, strategy="auditor_inteligente"), 1
        )
        self.assertEqual(available[0]["database_uid"], other)

        self.study.resolve_review_request(request["id"])
        with self.db.connect() as connection:
            state = connection.execute(
                "SELECT suspended, correction_priority FROM study_state WHERE question_uid = ?",
                (corrected,),
            ).fetchone()
        self.assertEqual(state["suspended"], 0)
        self.assertEqual(state["correction_priority"], 1)
        selected = self.study.select_questions(
            SelectionFilters(subjects=[], approved_only=True, strategy="auditor_inteligente"), 1
        )
        self.assertEqual(selected[0]["database_uid"], corrected)

    def test_old_unanswered_backlog_is_quarantined(self) -> None:
        uid = self.make_question("Q-ANTIGA", "aprovado")
        sent = self.study.record_delivery(uid, "123", self.send_result("poll-old", 1), "cycle")
        old = (datetime.now(timezone.utc) - timedelta(days=5)).replace(microsecond=0).isoformat()
        with self.db.connect() as connection:
            connection.execute("UPDATE telegram_deliveries SET sent_at = ? WHERE id = ?", (old, sent["delivery_id"]))
        config = {
            "telegram_bot_token": "token",
            "telegram_chat_id": "123",
            "flow_unanswered_resend_enabled": True,
            "flow_unanswered_resend_hours": 24,
            "flow_unanswered_max_resends": 2,
            "flow_background_startup_grace_minutes": 0,
            "flow_unanswered_batch_limit": 1,
            "flow_unanswered_daily_cap": 3,
            "flow_unanswered_session_cap": 3,
        }
        engine = CyclicStudyEngine(self.db, self.study, lambda: config)
        engine._session_started_at = datetime.now() - timedelta(minutes=1)
        with patch("core.flow.send_quiz_with_retry") as send_mock:
            engine._resend_due_unanswered(config, datetime.now())
        send_mock.assert_not_called()
        self.assertEqual(self.study.get_runtime("unanswered_policy_version"), "3.0.14")

    def test_question_under_correction_is_not_automatically_resent(self) -> None:
        uid = self.make_question("Q-SUSPENSA", "aprovado")
        sent = self.study.record_delivery(uid, "123", self.send_result("poll-suspended", 5), "cycle")
        old = (datetime.now(timezone.utc) - timedelta(hours=30)).replace(microsecond=0).isoformat()
        with self.db.connect() as connection:
            connection.execute("UPDATE telegram_deliveries SET sent_at = ? WHERE id = ?", (old, sent["delivery_id"]))
        self.study.create_review_request(uid, user_id="1")
        due = self.study.unanswered_deliveries_due(wait_hours=24, max_resends=2)
        self.assertEqual(due, [])

    def test_reset_preserves_active_correction_suspension(self) -> None:
        uid = self.make_question("Q-RESET", "aprovado")
        self.study.create_review_request(uid, user_id="1")
        self.study.reset_progress()
        with self.db.connect() as connection:
            state = connection.execute(
                "SELECT sent_count, suspended FROM study_state WHERE question_uid = ?", (uid,)
            ).fetchone()
        self.assertEqual(state["sent_count"], 0)
        self.assertEqual(state["suspended"], 1)
        self.assertEqual(self.study.pending_review_count(), 1)


if __name__ == "__main__":
    unittest.main()
