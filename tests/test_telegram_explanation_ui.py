from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from core.telegram import send_explanation_card, telegram_payload


class TelegramExplanationUITests(unittest.TestCase):
    def setUp(self) -> None:
        self.question = {
            "database_uid": "11111111-1111-1111-1111-111111111111",
            "codigo_origem": "QVISUAL",
            "materia": "CONTABILIDADE GERAL",
            "aula_planilha": "Aula 01",
            "assunto": "Princípios Contábeis",
            "banca": "FGV",
            "ano": 2026,
            "orgao": "SEFAZ",
            "enunciado": "Assinale a alternativa correta.",
            "alternativas": [
                {"chave": "A", "texto": "Primeira alternativa"},
                {"chave": "B", "texto": "Segunda alternativa"},
            ],
            "gabarito": "B",
            "tipo": "multipla_escolha",
            "explicacao": "A segunda alternativa está correta porque aplica o conceito adequado.",
        }

    def test_native_poll_omits_cramped_explanation_by_default(self) -> None:
        payload = telegram_payload(self.question, "123")
        self.assertNotIn("explanation", payload)
        options = [item["text"] for item in json.loads(payload["options"])]
        self.assertEqual(options, ["A) Primeira alternativa", "B) Segunda alternativa"])

    def test_action_buttons_include_explanation_review_and_next(self) -> None:
        payload = telegram_payload(self.question, "123")
        markup = json.loads(payload["reply_markup"])
        labels = [button["text"] for row in markup["inline_keyboard"] for button in row]
        self.assertIn("📖 Ver explicação", labels)
        self.assertIn("⚠️ Corrigir", labels)
        self.assertIn("➡️ Próxima questão", labels)

    def test_native_explanation_can_be_enabled_for_compatibility(self) -> None:
        payload = telegram_payload(self.question, "123", native_explanation=True)
        self.assertEqual(payload["explanation"], self.question["explicacao"])

    def test_full_explanation_is_sent_as_html_message(self) -> None:
        fake = {"ok": True, "result": {"message_id": 900}}
        with patch("core.telegram._post", return_value=fake) as post:
            result = send_explanation_card(
                "token",
                "123",
                self.question,
                selected_indices=[0],
                correct_index=1,
                is_correct=False,
                reply_to_message_id=77,
            )
        self.assertTrue(result["ok"])
        payload = post.call_args.args[2]
        self.assertEqual(payload["parse_mode"], "HTML")
        self.assertIn("REVISÃO NECESSÁRIA", payload["text"])
        self.assertIn("EXPLICAÇÃO", payload["text"])
        self.assertIn(self.question["explicacao"], payload["text"])
        self.assertEqual(json.loads(payload["reply_parameters"])["message_id"], 77)

    def test_feedback_card_contains_progress_metrics(self) -> None:
        fake = {"ok": True, "result": {"message_id": 901}}
        with patch("core.telegram._post", return_value=fake) as post:
            send_explanation_card(
                "token",
                "123",
                self.question,
                selected_indices=[1],
                correct_index=1,
                is_correct=True,
                study_state={
                    "streak": 4,
                    "response_seconds": 23,
                    "predicted_recall": 0.84,
                },
            )
        payload = post.call_args.args[2]
        self.assertIn("+12 XP", payload["text"])
        self.assertIn("sequência 4", payload["text"])
        self.assertIn("retenção prevista 84%", payload["text"])

    def test_long_explanation_is_split_into_readable_messages(self) -> None:
        question = dict(self.question)
        question["explicacao"] = "Explicação detalhada. " * 500
        fake = {"ok": True, "result": {"message_id": 902}}
        with patch("core.telegram._post", return_value=fake) as post:
            result = send_explanation_card("token", "123", question, is_correct=False)
        self.assertTrue(result["ok"])
        self.assertGreater(post.call_count, 1)
        last_payload = post.call_args.args[2]
        self.assertIn("reply_markup", last_payload)


if __name__ == "__main__":
    unittest.main()
