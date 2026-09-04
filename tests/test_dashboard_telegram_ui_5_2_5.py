from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.storage import QuestFlowDatabase
from core.study import StudyRepository
from core.telegram import send_explanation_card, send_quiz


BASE = Path(__file__).resolve().parents[1]


class DashboardTelegramUi525Tests(unittest.TestCase):
    def test_dashboard_explains_every_subject_bar_and_avoids_empty_badge(self) -> None:
        js = (BASE / "web" / "app.js").read_text(encoding="utf-8")
        css = (BASE / "web" / "styles.css").read_text(encoding="utf-8")
        self.assertIn("Como ler este painel", js)
        self.assertIn("retenção FSRS", js)
        self.assertIn("Desempenho recente", js)
        self.assertIn("summary-chip", js)
        self.assertIn("subject-summary-toggle", js)
        self.assertIn("subject-analytics-grid", css)
        self.assertNotIn("<span class=\"tag\">${escapeHtml(item.topic || item.assunto || '')}</span>", js)

    def test_missing_subject_receives_explicit_label(self) -> None:
        with tempfile.TemporaryDirectory(prefix="questflow-525-subject-") as temp:
            database = QuestFlowDatabase(Path(temp) / "questions.sqlite")
            uid = database.create_manual_question(None)
            question = database.get_question(uid)
            assert question is not None
            question.update({
                "materia": "",
                "enunciado": "Questão sem matéria cadastrada.",
                "alternativas": [{"chave": "A", "texto": "Certa"}, {"chave": "B", "texto": "Errada"}],
                "gabarito": "A",
            })
            database.update_question(uid, question)
            study = StudyRepository(database)
            study.sync_questions()
            rows = study.subject_stats(limit=10)
            self.assertTrue(rows)
            self.assertEqual(rows[0]["subject"], "Matéria não informada")
            self.assertEqual(rows[0]["performance_label"], "Sem respostas")
            self.assertEqual(rows[0]["performance_tone"], "neutral")

    def test_question_card_and_poll_use_modern_separated_format(self) -> None:
        question = {
            "database_uid": "11111111-1111-1111-1111-111111111111",
            "codigo_origem": "Q525",
            "materia": "AUDITORIA",
            "aula_planilha": "Aula 03",
            "assunto": "Evidências",
            "banca": "FGV",
            "ano": 2026,
            "enunciado": "Assinale a alternativa correta.",
            "alternativas": [{"chave": "A", "texto": "Correta"}, {"chave": "B", "texto": "Incorreta"}],
            "gabarito": "A",
            "explicacao": "A alternativa A aplica o conceito adequado.",
        }
        fake = {"ok": True, "result": {"message_id": 10, "poll": {"id": "poll-525"}}}
        with patch("core.telegram._post", return_value=fake) as post:
            result = send_quiz("token", "123", question, position=2, total=10)
        self.assertTrue(result["ok"])
        card_payload = post.call_args_list[0].args[2]
        poll_payload = post.call_args_list[-1].args[2]
        self.assertIn("QUESTFLOW • QUESTÃO 2/10", card_payload["text"])
        self.assertIn("AUDITORIA", card_payload["text"])
        self.assertIn("Marque a alternativa correta", card_payload["text"])
        self.assertTrue(poll_payload["question"].startswith("📝"))

    def test_feedback_separates_marking_answer_and_explanation(self) -> None:
        question = {
            "database_uid": "22222222-2222-2222-2222-222222222222",
            "codigo_origem": "Q525-FEEDBACK",
            "materia": "DIREITO TRIBUTÁRIO",
            "aula_planilha": "Aula 01",
            "assunto": "Limitações ao poder de tributar",
            "alternativas": [{"chave": "A", "texto": "Escolhida"}, {"chave": "B", "texto": "Correta"}],
            "gabarito": "B",
            "explicacao": "A alternativa B é a correta conforme o fundamento cadastrado.",
        }
        fake = {"ok": True, "result": {"message_id": 11}}
        with patch("core.telegram._post", return_value=fake) as post:
            send_explanation_card(
                "token", "123", question,
                selected_indices=[0], correct_index=1, is_correct=False,
                study_state={"response_seconds": 18, "predicted_recall": 0.72},
            )
        payload = post.call_args_list[0].args[2]
        text = payload["text"]
        self.assertIn("SUA MARCAÇÃO", text)
        self.assertIn("GABARITO", text)
        self.assertIn("EXPLICAÇÃO", text)
        self.assertIn("Q525-FEEDBACK", text)
        self.assertIn("retenção prevista 72%", text)

    def test_flow_exposes_question_card_and_explanation_format_settings(self) -> None:
        js = (BASE / "web" / "app.js").read_text(encoding="utf-8")
        self.assertIn("flow_question_card_enabled", js)
        self.assertIn("flow_explanation_mode", js)
        self.assertIn("Mostrar resultado e explicação completa", js)
        self.assertIn("Mostrar resultado curto e botão de explicação", js)


if __name__ == "__main__":
    unittest.main()
