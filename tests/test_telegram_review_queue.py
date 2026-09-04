from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.flow import CyclicStudyEngine
from core.storage import QuestFlowDatabase
from core.study import StudyRepository
from core.telegram import telegram_payload


class TelegramReviewQueueTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="qf-review-")
        self.database = QuestFlowDatabase(Path(self.temp.name) / "review.sqlite")
        self.uid = self.database.create_manual_question(None)
        question = self.database.get_question(self.uid)
        assert question is not None
        question["codigo_origem"] = "QREVIEW1"
        question["id"] = "QREVIEW1"
        question["database_uid"] = self.uid
        question["enunciado"] = "Assinale a alternativa correta."
        question["alternativas"] = [
            {"chave": "A", "texto": "Correta"},
            {"chave": "B", "texto": "Incorreta"},
        ]
        question["gabarito"] = "A"
        question["telegram"] = {"indice_correto": 0}
        self.database.update_question(self.uid, question)
        self.persisted_source_code = self.database.list_questions(limit=1)[0]["source_code"]
        self.study = StudyRepository(self.database)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_poll_contains_review_button(self) -> None:
        question = self.database.get_question(self.uid)
        assert question is not None
        payload = telegram_payload(question, "123")
        markup = json.loads(payload["reply_markup"])
        button = markup["inline_keyboard"][0][0]
        self.assertEqual(button["text"], "⚠️ Corrigir esta questão")
        self.assertEqual(button["callback_data"], f"qf:review:{self.uid}")
        self.assertLessEqual(len(button["callback_data"].encode("utf-8")), 64)

    def test_review_request_is_persistent_and_deduplicated(self) -> None:
        first = self.study.create_review_request(
            self.uid, chat_id="123", user_id="99", username="camilla", message_id=7
        )
        second = self.study.create_review_request(
            self.uid, chat_id="123", user_id="99", username="camilla", message_id=8
        )
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(self.study.pending_review_count(), 1)
        rows = self.study.list_review_requests("ativas")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["source_code"], self.persisted_source_code)
        self.assertEqual(rows[0]["message_id"], 8)

    def test_callback_creates_queue_item_and_emits_event(self) -> None:
        events: list[tuple[str, dict]] = []
        engine = CyclicStudyEngine(
            self.database,
            self.study,
            lambda: {"telegram_bot_token": "token", "telegram_chat_id": "123"},
            lambda event, payload: events.append((event, payload)),
        )
        callback = {
            "id": "cb1",
            "data": f"qf:review:{self.uid}",
            "from": {"id": 99, "username": "camilla"},
            "message": {"message_id": 44, "chat": {"id": 123}},
        }
        with patch("core.flow.answer_callback_query", return_value={"ok": True}), patch(
            "core.flow.send_message", return_value={"ok": True}
        ):
            engine._handle_callback_query(callback, engine.config_provider())
        self.assertEqual(self.study.pending_review_count(), 1)
        self.assertTrue(any(name == "review_requested" for name, _ in events))

    def test_resolve_requests_for_question(self) -> None:
        request = self.study.create_review_request(self.uid, user_id="99")
        changed = self.study.resolve_review_requests_for_question(self.uid)
        self.assertEqual(changed, 1)
        row = self.study.get_review_request(request["id"])
        assert row is not None
        self.assertEqual(row["status"], "resolvida")


if __name__ == "__main__":
    unittest.main()
