from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from core.telegram import TelegramError, classify_exception, telegram_payload, with_retry


class TelegramTests(unittest.TestCase):
    def setUp(self) -> None:
        self.question = {
            "codigo_origem": "QTESTE",
            "enunciado": "Assinale a alternativa correta.",
            "alternativas": [
                {"chave": "A", "texto": "Resposta correta"},
                {"chave": "B", "texto": "Resposta incorreta"},
            ],
            "gabarito": "A",
            "tipo": "multipla_escolha",
        }

    def test_quiz_payload(self) -> None:
        payload = telegram_payload(self.question, "123")
        self.assertEqual(payload["type"], "quiz")
        self.assertEqual(json.loads(payload["correct_option_ids"]), [0])
        self.assertEqual(payload["is_anonymous"], "false")

    def test_long_question_uses_context(self) -> None:
        question = dict(self.question)
        question["enunciado"] = "Texto longo " * 80
        payload = telegram_payload(question, "123")
        self.assertFalse(payload["_direct_poll"])
        self.assertIn("QTESTE", payload["_context"])

    def test_retry_transient_error(self) -> None:
        calls = {"count": 0}

        def operation():
            calls["count"] += 1
            if calls["count"] < 3:
                raise TelegramError("temporário", category="servidor_telegram", retryable=True)
            return {"ok": True}

        with patch("core.telegram.time.sleep", return_value=None), patch("core.telegram.random.uniform", return_value=0):
            result = with_retry(operation, attempts=3, base_delay=0)
        self.assertTrue(result["ok"])
        self.assertEqual(calls["count"], 3)

    def test_non_retryable_error_stops(self) -> None:
        calls = {"count": 0}

        def operation():
            calls["count"] += 1
            raise TelegramError("token inválido", category="token_invalido", retryable=False)

        with self.assertRaises(TelegramError):
            with_retry(operation, attempts=5, base_delay=0)
        self.assertEqual(calls["count"], 1)

    def test_local_validation_classification(self) -> None:
        parsed = classify_exception(ValueError("enunciado vazio"))
        self.assertEqual(parsed.category, "validacao_local")
        self.assertFalse(parsed.retryable)


if __name__ == "__main__":
    unittest.main()
