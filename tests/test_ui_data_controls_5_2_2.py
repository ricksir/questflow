from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app_shared import TAXONOMY_PATH
from core.storage import QuestFlowDatabase
from core.study import StudyRepository
from web_api import QuestFlowWebApi


class UiDataControls522Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="questflow-522-")
        self.root = Path(self.temp.name)
        self.db_path = self.root / "questions.sqlite"
        self.db = QuestFlowDatabase(self.db_path)
        self.uid = self.db.create_manual_question(None)
        question = self.db.get_question(self.uid)
        assert question is not None
        question.update(
            {
                "codigo_origem": "Q522001",
                "materia": "MATÉRIA PERSONALIZADA",
                "aula_planilha": "Aula 07",
                "assunto": "Assunto de teste",
                "enunciado": "Questão usada para validar o histórico.",
                "alternativas": [
                    {"chave": "A", "texto": "Correta"},
                    {"chave": "B", "texto": "Incorreta"},
                ],
                "gabarito": "A",
                "telegram": {
                    "modo": "quiz",
                    "pergunta": "Questão usada para validar o histórico.",
                    "opcoes": ["Correta", "Incorreta"],
                    "indice_correto": 0,
                },
                "revisao": {"status": "aprovado", "confianca": 1.0, "alertas": []},
            }
        )
        self.db.update_question(self.uid, question)
        self.api = QuestFlowWebApi(
            self.db_path,
            config={
                "telegram_bot_token": "123456:SECRET_TOKEN_VALUE",
                "telegram_chat_id": "987654",
                "flow_target_retention": 0.88,
            },
            config_path=self.root / "config.json",
            taxonomy_path=TAXONOMY_PATH,
        )

    def tearDown(self) -> None:
        self.api.shutdown()
        self.temp.cleanup()

    def test_matter_selector_combines_taxonomy_and_database(self) -> None:
        result = self.api.list_materias()
        self.assertTrue(result["ok"])
        self.assertIn("MATÉRIA PERSONALIZADA", result["items"])
        self.assertIn("DIREITO TRIBUTÁRIO", result["items"])
        self.assertEqual(result["items"], sorted(result["items"], key=str.casefold))

    def test_recent_delivery_returns_ui_aliases_and_zeroes(self) -> None:
        study = StudyRepository(self.db)
        study.sync_questions()
        study.record_delivery(
            self.uid,
            "987654",
            {"direct_poll": True, "poll": {"result": {"message_id": 1, "poll": {"id": "poll-522"}}}},
            "cycle-522",
        )
        item = study.recent_deliveries(limit=1)[0]
        self.assertNotEqual(item["codigo"], "NÃO ENCONTRADO")
        self.assertTrue(item["codigo"].strip())
        self.assertEqual(item["materia"], "MATÉRIA PERSONALIZADA")
        self.assertEqual(item["attempts"], 1)
        self.assertEqual(item["answers"], 0)
        self.assertEqual(item["correct"], 0)
        self.assertEqual(item["question_uid"], self.uid)

    def test_public_config_masks_token_and_blank_save_keeps_secret(self) -> None:
        public = self.api._public_config()
        self.assertNotIn("telegram_bot_token", public)
        self.assertTrue(public["telegram_bot_token_masked"])
        self.api.save_flow_settings({"telegram_bot_token": "", "telegram_chat_id": "111"})
        self.assertEqual(self.api.config["telegram_bot_token"], "123456:SECRET_TOKEN_VALUE")
        self.assertEqual(self.api.config["telegram_chat_id"], "111")

    def test_telegram_connection_uses_saved_token_when_field_is_blank(self) -> None:
        with patch("core.telegram.get_me", return_value={"ok": True, "result": {"first_name": "QuestBot", "username": "quest_bot"}}) as mocked:
            result = self.api.test_telegram_connection("", "987654")
        self.assertTrue(result["ok"])
        self.assertEqual(result["username"], "quest_bot")
        mocked.assert_called_once_with("123456:SECRET_TOKEN_VALUE", timeout=15)

    def test_web_ui_contains_requested_controls(self) -> None:
        root = Path(__file__).resolve().parents[1]
        html = (root / "web" / "index.html").read_text(encoding="utf-8")
        js = (root / "web" / "app.js").read_text(encoding="utf-8")
        css = (root / "web" / "styles.css").read_text(encoding="utf-8")
        self.assertIn('id="fullscreenToggle"', html)
        self.assertIn('id="telegramBotForm"', html)
        self.assertIn('id="testTelegramConnection"', html)
        self.assertIn("list_materias", js)
        self.assertIn("enhanceManagedTable", js)
        self.assertIn("data-question-column", js)
        self.assertIn("column-resizer", css)
        self.assertIn("table-sort-button", css)


if __name__ == "__main__":
    unittest.main()
