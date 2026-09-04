from __future__ import annotations

import json
import tempfile
import types
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from core.fsrs_adapter import optimize_review_logs, rating_from_answer
from core.storage import QuestFlowDatabase
from core.study import SelectionFilters, StudyRepository
from core.telegram import _feedback_markup


class _ReviewLog:
    @classmethod
    def from_json(cls, raw):
        obj = cls(); obj.raw = raw; return obj

class _Optimizer:
    def __init__(self, logs): self.logs = logs
    def compute_optimal_parameters(self): return tuple(float(i) / 10 for i in range(21))
    def compute_optimal_retention(self, parameters): return 0.91


class FSRS6QuestFlowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="qf-fsrs6-")
        self.db = QuestFlowDatabase(Path(self.tmp.name) / "q.sqlite")
        self.study = StudyRepository(self.db)

    def tearDown(self):
        self.tmp.cleanup()

    def make_question(self, code: str, subject: str, lesson: str = "Aula 01") -> str:
        uid = self.db.create_manual_question(None)
        q = self.db.get_question(uid); assert q
        q.update({
            "codigo_origem": code, "id": code, "materia": subject,
            "aula_planilha": lesson, "assunto": "Assunto", "enunciado": code,
            "alternativas": [{"chave":"A","texto":"Certa"},{"chave":"B","texto":"Errada"}],
            "gabarito":"A", "telegram":{"indice_correto":0},
            "revisao":{"status":"aprovado","confianca":1.0,"alertas":[]},
        })
        self.db.update_question(uid, q); self.study.sync_questions(); return uid

    def test_due_review_has_hard_precedence_over_future_high_risk(self):
        due = self.make_question("Q-DUE", "AUDITORIA")
        future = self.make_question("Q-FUTURE", "TRIBUTÁRIO")
        now = datetime.now(timezone.utc)
        with self.db.connect() as c:
            c.execute("UPDATE study_state SET sent_count=3, due_at=?, wrong_count=1 WHERE question_uid=?", ((now-timedelta(days=1)).isoformat(), due))
            c.execute("UPDATE study_state SET sent_count=10, due_at=?, wrong_count=10, correct_count=0 WHERE question_uid=?", ((now+timedelta(days=3)).isoformat(), future))
        chosen = self.study.select_questions(SelectionFilters(subjects=[], approved_only=True), 1)
        self.assertEqual(chosen[0]["database_uid"], due)
        self.assertIn("vencida", chosen[0]["selection_reason"].lower())

    def test_selection_is_restricted_to_studied_subject_lesson(self):
        allowed = self.make_question("Q-STUDIED", "AUDITORIA", "Aula 01")
        self.make_question("Q-NOT-STUDIED", "CONTABILIDADE", "Aula 02")
        self.study.set_learning_preferences(studied_only=True)
        self.study.refresh_studied_scope([{
            "materia":"AUDITORIA", "aula":"Aula 01", "trilha":"Trilha 01",
            "row": 10, "estudado": True, "ch_efetiva_min":90,
        }])
        chosen = self.study.select_questions(SelectionFilters(subjects=[], approved_only=True), 10)
        self.assertEqual([q["database_uid"] for q in chosen], [allowed])

    def test_confidence_changes_fsrs_rating(self):
        self.assertEqual(rating_from_answer(correct=False), 1)
        self.assertEqual(rating_from_answer(correct=True, confidence="chutei", prior_accuracy=.9, response_seconds=5), 2)
        self.assertEqual(rating_from_answer(correct=True, confidence="sabia", prior_accuracy=.9, response_seconds=5), 4)

    def test_optimizer_uses_21_parameters_and_retention(self):
        module = types.SimpleNamespace(ReviewLog=_ReviewLog, Optimizer=_Optimizer, __version__="6.3.2")
        with patch("importlib.import_module", return_value=module):
            result = optimize_review_logs([json.dumps({"x": 1}), json.dumps({"x": 2})])
        self.assertIsNotNone(result); assert result
        self.assertEqual(len(result.parameters), 21)
        self.assertAlmostEqual(result.desired_retention or 0, 0.91)

    def test_feedback_collects_confidence_and_error_type(self):
        markup = _feedback_markup({"database_uid":"uid-1"}, attempt_id="12345678-1234-1234-1234-123456789012", is_correct=False)
        self.assertIsNotNone(markup); assert markup
        data = [button["callback_data"] for row in markup["inline_keyboard"] for button in row]
        self.assertTrue(any(item.endswith(":c:s") for item in data))
        self.assertTrue(any(item.endswith(":c:g") for item in data))
        self.assertTrue(any(item.endswith(":e:c") for item in data))


if __name__ == "__main__":
    unittest.main()
