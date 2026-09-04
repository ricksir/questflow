from __future__ import annotations

import tempfile
import unittest
from unittest.mock import patch
from datetime import datetime, timedelta, timezone
from pathlib import Path

from core.storage import QuestFlowDatabase
from core.study import StudyRepository


class UnansweredAndCoverageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="questflow-3013-")
        self.db = QuestFlowDatabase(Path(self.temp.name) / "test.sqlite")
        self.study = StudyRepository(self.db)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _question(self, subject: str = "AUDITORIA", lesson: str = "Aula 01") -> str:
        uid = self.db.create_manual_question(None)
        question = self.db.get_question(uid)
        assert question is not None
        question["materia"] = subject
        question["aula_planilha"] = lesson
        question["assunto"] = "Assunto teste"
        question["enunciado"] = "Questão de teste"
        question["alternativas"] = [
            {"chave": "A", "texto": "Correta"},
            {"chave": "B", "texto": "Incorreta"},
        ]
        question["gabarito"] = "A"
        question["telegram"] = {"modo": "quiz", "pergunta": "Questão de teste", "opcoes": ["Correta", "Incorreta"], "indice_correto": 0}
        question["revisao"] = {"status": "aprovado", "confianca": 1.0, "alertas": []}
        self.db.update_question(uid, question)
        self.study.sync_questions()
        return uid

    @staticmethod
    def _send_result(poll_id: str, message_id: int) -> dict:
        return {
            "direct_poll": True,
            "poll": {"result": {"message_id": message_id, "poll": {"id": poll_id}}},
        }

    def test_unanswered_delivery_is_resent_once_and_parent_resolved(self) -> None:
        uid = self._question()
        first = self.study.record_delivery(uid, "123", self._send_result("poll-1", 1), "cycle-1")
        old = (datetime.now(timezone.utc) - timedelta(hours=30)).replace(microsecond=0).isoformat()
        with self.db.connect() as connection:
            connection.execute("UPDATE telegram_deliveries SET sent_at = ? WHERE id = ?", (old, first["delivery_id"]))
        due = self.study.unanswered_deliveries_due(wait_hours=24, max_resends=2)
        self.assertEqual([row["id"] for row in due], [first["delivery_id"]])

        child = self.study.record_delivery(
            uid,
            "123",
            self._send_result("poll-2", 2),
            "cycle-1",
            parent_delivery_id=first["delivery_id"],
            resend_reason="sem_resposta",
            unanswered_resend_count=1,
        )
        parent = self.study.get_delivery(first["delivery_id"])
        self.assertIsNotNone(parent)
        self.assertEqual(parent["status"], "reenviado_sem_resposta")
        self.assertEqual(parent["resolved_by_delivery_id"], child["delivery_id"])
        self.assertEqual(child["unanswered_resend_count"], 1)

    def test_answered_delivery_is_not_due(self) -> None:
        uid = self._question()
        sent = self.study.record_delivery(uid, "123", self._send_result("poll-answered", 1), "cycle-1")
        old = (datetime.now(timezone.utc) - timedelta(hours=30)).replace(microsecond=0).isoformat()
        with self.db.connect() as connection:
            connection.execute("UPDATE telegram_deliveries SET sent_at = ? WHERE id = ?", (old, sent["delivery_id"]))
        answer = self.study.record_poll_answer({"poll_id": "poll-answered", "user": {"id": 1}, "option_ids": [0]})
        self.assertTrue(answer and answer["is_correct"])
        self.assertEqual(self.study.unanswered_deliveries_due(wait_hours=24, max_resends=2), [])

    def test_callback_inbox_and_outbox_are_persistent(self) -> None:
        callback = {"id": "cb-1", "data": "qf:review:abc", "message": {"chat": {"id": 123}}}
        item_id = self.study.enqueue_callback_update(99, callback)
        pending = self.study.pending_callback_updates()
        self.assertEqual(pending[0]["id"], item_id)
        self.assertEqual(pending[0]["payload"]["data"], "qf:review:abc")
        self.study.mark_callback_processed(item_id)
        self.assertEqual(self.study.pending_callback_updates(), [])

        outbox_id = self.study.enqueue_outbox_message("123", "Confirmação", kind="teste")
        self.assertEqual(self.study.pending_outbox_messages()[0]["id"], outbox_id)
        self.study.mark_outbox_sent(outbox_id)
        self.assertEqual(self.study.pending_outbox_messages(), [])

    def test_lesson_coverage_distinguishes_missing_never_sent_and_sent(self) -> None:
        uid_a = self._question("AUDITORIA", "Aula 01")
        self._question("DIREITO TRIBUTÁRIO", "Aula 02")
        self.study.record_delivery(uid_a, "123", self._send_result("poll-cover", 3), "cycle-cover")
        tasks = [
            {"materia": "AUDITORIA", "aula": "Aula 01", "descricao": "Evidências", "segmentos": ["Evidências"]},
            {"materia": "DIREITO TRIBUTÁRIO", "aula": "Aula 02", "descricao": "Obrigação", "segmentos": ["Obrigação"]},
            {"materia": "CONTABILIDADE PÚBLICA", "aula": "Aula 03", "descricao": "Balanços", "segmentos": ["Balanços"]},
        ]
        report = {(row["subject"], row["lesson"]): row for row in self.study.lesson_coverage(tasks)}
        self.assertEqual(report[("AUDITORIA", "Aula 01")]["status"], "todas_enviadas")
        self.assertEqual(report[("DIREITO TRIBUTÁRIO", "Aula 02")]["status"], "com_questoes_nao_enviadas")
        self.assertEqual(report[("CONTABILIDADE PÚBLICA", "Aula 03")]["status"], "sem_questoes")

    def test_engine_resends_due_unanswered_question(self) -> None:
        from core.flow import CyclicStudyEngine

        uid = self._question()
        first = self.study.record_delivery(uid, "123", self._send_result("poll-engine-1", 1), "cycle-1")
        old = (datetime.now(timezone.utc) - timedelta(hours=30)).replace(microsecond=0).isoformat()
        with self.db.connect() as connection:
            connection.execute("UPDATE telegram_deliveries SET sent_at = ? WHERE id = ?", (old, first["delivery_id"]))
        config = {
            "telegram_bot_token": "token",
            "telegram_chat_id": "123",
            "flow_unanswered_resend_enabled": True,
            "flow_unanswered_resend_hours": 24,
            "flow_unanswered_max_resends": 2,
            "flow_question_retry_attempts": 1,
        }
        config.update({
            "flow_background_startup_grace_minutes": 0,
            "flow_unanswered_batch_limit": 1,
            "flow_unanswered_daily_cap": 3,
            "flow_unanswered_session_cap": 3,
        })
        self.study.set_runtime("unanswered_policy_version", "3.0.14")
        self.study.set_runtime("unanswered_resend_activated_at", (datetime.now(timezone.utc) - timedelta(days=2)).replace(microsecond=0).isoformat())
        engine = CyclicStudyEngine(self.db, self.study, lambda: dict(config))
        engine._session_started_at = datetime.now() - timedelta(minutes=1)
        with patch("core.flow.send_message", return_value={"ok": True}), patch(
            "core.flow.send_quiz_with_retry", return_value=self._send_result("poll-engine-2", 2)
        ):
            engine._resend_due_unanswered(config, datetime.now())
        parent = self.study.get_delivery(first["delivery_id"])
        self.assertEqual(parent["status"], "reenviado_sem_resposta")

    def test_pending_review_callback_is_recovered(self) -> None:
        from core.flow import CyclicStudyEngine

        uid = self._question()
        callback = {
            "id": "cb-recover",
            "data": f"qf:review:{uid}",
            "from": {"id": 1, "username": "aluna"},
            "message": {"chat": {"id": 123}, "message_id": 10},
        }
        self.study.enqueue_callback_update(501, callback)
        config = {"telegram_bot_token": "token", "telegram_chat_id": "123", "flow_retry_minutes": 1}
        engine = CyclicStudyEngine(self.db, self.study, lambda: dict(config))
        with patch("core.flow.answer_callback_query", return_value={"ok": True}), patch(
            "core.flow.send_message", return_value={"ok": True}
        ):
            engine._retry_pending_callbacks(config, datetime.now())
        self.assertEqual(self.study.pending_review_count(), 1)
        self.assertEqual(self.study.pending_callback_updates(), [])


if __name__ == "__main__":
    unittest.main()
