from __future__ import annotations

import tempfile
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from core.learning_analytics import subject_priority, weighted_recent_accuracy
from core.storage import QuestFlowDatabase
from core.study import StudyRepository
from core.telegram import _feedback_markup


BASE = Path(__file__).resolve().parents[1]


class LearningAnalytics570Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="qf-la570-")
        self.db = QuestFlowDatabase(Path(self.tmp.name) / "q.sqlite")
        self.study = StudyRepository(self.db)

    def tearDown(self):
        self.tmp.cleanup()

    def make_question(self, subject: str = "AUDITORIA", lesson: str = "Aula 01") -> str:
        uid = self.db.create_manual_question(None)
        q = self.db.get_question(uid); assert q
        q.update({
            "codigo_origem": f"Q-{uid[:8]}", "id": f"Q-{uid[:8]}",
            "materia": subject, "aula_planilha": lesson, "assunto": "Assunto teste",
            "enunciado": "Questão de teste",
            "alternativas": [{"chave": "A", "texto": "Certa"}, {"chave": "B", "texto": "Errada"}],
            "gabarito": "A", "telegram": {"indice_correto": 0},
            "revisao": {"status": "aprovado", "confianca": 1.0, "alertas": []},
        })
        self.db.update_question(uid, q)
        self.study.sync_questions()
        return uid

    def insert_attempt(self, uid: str, when: datetime, correct: bool, *, difficulty: str | None = None, gap: int | None = None) -> str:
        delivery_id = str(uuid.uuid4())
        attempt_id = str(uuid.uuid4())
        poll_id = f"poll-{attempt_id}"
        when_text = when.replace(microsecond=0).isoformat()
        sent_text = (when - timedelta(seconds=25)).replace(microsecond=0).isoformat()
        with self.db.connect() as c:
            c.execute(
                """INSERT INTO telegram_deliveries(id, cycle_id, question_uid, poll_id, chat_id, sent_at, status)
                   VALUES (?, 'test', ?, ?, '1', ?, 'enviado')""",
                (delivery_id, uid, poll_id, sent_text),
            )
            c.execute(
                """INSERT INTO telegram_attempts(
                       id, delivery_id, question_uid, poll_id, user_id, username,
                       selected_indices_json, is_correct, answered_at, response_seconds,
                       perceived_difficulty, learning_gap
                   ) VALUES (?, ?, ?, ?, '1', 'tester', '[0]', ?, ?, 25, ?, ?)""",
                (attempt_id, delivery_id, uid, poll_id, 1 if correct else 0, when_text, difficulty, gap),
            )
            c.execute(
                """UPDATE study_state SET sent_count = sent_count + 1, last_sent_at = ?, last_answered_at = ?,
                   correct_count = correct_count + ?, wrong_count = wrong_count + ? WHERE question_uid = ?""",
                (sent_text, when_text, 1 if correct else 0, 0 if correct else 1, uid),
            )
        return attempt_id

    def test_migration_creates_learning_analytics_columns_and_daily_table(self):
        with self.db.connect() as c:
            columns = {row[1] for row in c.execute("PRAGMA table_info(telegram_attempts)")}
            table = c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='subject_analytics_daily'").fetchone()
        self.assertTrue({"perceived_difficulty", "learning_gap", "meta_updated_at"}.issubset(columns))
        self.assertIsNotNone(table)

    def test_cold_start_studied_subject_has_actionable_priority_without_fake_accuracy(self):
        self.make_question("AUDITORIA", "Aula 01")
        self.study.refresh_studied_scope([{
            "materia": "AUDITORIA", "aula": "Aula 01", "trilha": "Trilha 01",
            "row": 10, "estudado": True, "ch_efetiva_min": 90,
        }])
        row = self.study.subject_stats(10)[0]
        self.assertTrue(row["studied"])
        self.assertFalse(row["has_answers"])
        self.assertIsNone(row["recent_accuracy"])
        self.assertEqual(row["performance_label"], "Sem respostas")
        self.assertNotEqual(row["priority_label"], "Aguardando estudo")
        self.assertGreater(row["priority_score"], 0)

    def test_unstudied_cold_start_is_not_artificially_prioritized(self):
        self.make_question("CONTABILIDADE", "Aula 03")
        row = self.study.subject_stats(10)[0]
        self.assertEqual(row["priority_label"], "Aguardando estudo")
        self.assertLessEqual(row["priority_score"], 25)

    def test_recent_window_and_trend_detect_improvement(self):
        uid = self.make_question("DIREITO TRIBUTÁRIO", "Aula 02")
        now = datetime.now(timezone.utc)
        # 30 antigas: 10 certas. 30 recentes: 24 certas.
        for index in range(30):
            self.insert_attempt(uid, now - timedelta(days=60 - index), index < 10)
        for index in range(30):
            self.insert_attempt(uid, now - timedelta(days=29 - index), index < 24)
        self.study.rebuild_subject_analytics_daily()
        row = self.study.subject_stats(10)[0]
        self.assertAlmostEqual(row["recent_accuracy"], 80.0, places=1)
        self.assertGreater(row["trend_delta_pp"], 40)
        self.assertGreaterEqual(len(row["trend"]), 2)

    def test_meta_buttons_store_difficulty_and_learning_gap_and_refresh_daily(self):
        uid = self.make_question("FLUÊNCIA EM DADOS", "Aula 01")
        attempt_id = self.insert_attempt(uid, datetime.now(timezone.utc), True)
        result = self.study.record_attempt_meta(attempt_id, perceived_difficulty="dificil", learning_gap=True)
        self.assertTrue(result["ok"])
        with self.db.connect() as c:
            row = c.execute("SELECT perceived_difficulty, learning_gap, meta_updated_at FROM telegram_attempts WHERE id = ?", (attempt_id,)).fetchone()
            daily = c.execute("SELECT hard_count, learning_gap_count FROM subject_analytics_daily WHERE subject = 'FLUÊNCIA EM DADOS'").fetchone()
        self.assertEqual(row["perceived_difficulty"], "dificil")
        self.assertEqual(row["learning_gap"], 1)
        self.assertTrue(row["meta_updated_at"])
        self.assertEqual(int(daily["hard_count"]), 1)
        self.assertEqual(int(daily["learning_gap_count"]), 1)

    def test_feedback_markup_collects_difficulty_and_explicit_study_gap(self):
        markup = _feedback_markup({"database_uid": "uid-1"}, attempt_id="12345678-1234-1234-1234-123456789012", is_correct=False)
        self.assertIsNotNone(markup); assert markup
        data = [button["callback_data"] for row in markup["inline_keyboard"] for button in row]
        self.assertTrue(any(item.endswith(":d:e") for item in data))
        self.assertTrue(any(item.endswith(":d:m") for item in data))
        self.assertTrue(any(item.endswith(":d:h") for item in data))
        self.assertTrue(any(item.endswith(":g:y") for item in data))

    def test_priority_model_combines_retention_performance_coverage_and_recency(self):
        good = subject_priority(retention=.92, recent_accuracy=.88, coverage=.92, days_since_review=1, due_count=0, attempts=80, studied=True)
        weak = subject_priority(retention=.55, recent_accuracy=.58, coverage=.35, days_since_review=18, due_count=12, attempts=80, studied=True)
        self.assertGreater(weak.score, good.score)
        self.assertEqual(weak.label, "Alta")
        self.assertIn("retention", weak.components)
        self.assertIn("coverage", weak.components)

    def test_weighted_recent_accuracy_values_newer_answers_more(self):
        # Mesmo número de acertos/erros; melhora no fim deve elevar a média ponderada.
        improving = weighted_recent_accuracy([0, 0, 0, 1, 1, 1])
        declining = weighted_recent_accuracy([1, 1, 1, 0, 0, 0])
        self.assertIsNotNone(improving); self.assertIsNotNone(declining)
        self.assertGreater(improving, declining)

    def test_web_dashboard_contains_learning_analytics_components(self):
        js = (BASE / "web" / "app.js").read_text(encoding="utf-8")
        css = (BASE / "web" / "styles.css").read_text(encoding="utf-8")
        html = (BASE / "web" / "index.html").read_text(encoding="utf-8")
        for token in ("Retenção estimada hoje", "Desempenho recente", "Cobertura estudada", "subject-summary-toggle", "renderVisualAnalyticsPanel", "openSubjectAnalyticsModal"):
            self.assertIn(token, js)
        for token in ("learning-analytics-overview", "subject-summary-toggle", "analytics-dashboard-grid"):
            self.assertIn(token, css)
        for token in ('data-route="visualanalytics"', 'data-page="visualanalytics"', 'id="visualAnalyticsPanel"'):
            self.assertIn(token, html)


if __name__ == "__main__":
    unittest.main()
