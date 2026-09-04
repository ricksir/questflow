from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from core.exam_projects import ExamProjectService
from core.mobile_foundation import MobileFoundationService
from core.storage import QuestFlowDatabase
from core.study import StudyRepository


class MobileStudySession6100Tests(unittest.TestCase):
    def build_stack(self, root: Path):
        db = QuestFlowDatabase(root / "questflow.sqlite")
        study = StudyRepository(db)
        ExamProjectService(db)
        service = MobileFoundationService(db, study, control_plane_path=root / "mobile_control.sqlite")
        return db, study, service

    def make_question(self, db: QuestFlowDatabase, *, code: str, subject: str) -> str:
        uid = db.create_manual_question()
        question = db.get_question(uid)
        assert question is not None
        question["codigo_origem"] = code
        question["materia"] = subject
        question["assunto"] = "Assunto teste"
        question["aula"] = "Aula 01"
        question["enunciado"] = f"Enunciado {code}"
        question["alternativas"] = [{"chave": "A", "texto": "Correta"}, {"chave": "B", "texto": "Incorreta"}]
        question["gabarito"] = "A"
        question["telegram"] = {"modo": "quiz", "pergunta": question["enunciado"], "opcoes": ["Correta", "Incorreta"], "indice_correto": 0}
        question.setdefault("revisao", {})["status"] = "aprovado"
        db.update_question(uid, question, change_source="test_mobile_study_session_6100")
        return uid

    def test_batches_support_review_error_and_subject_modes(self):
        with tempfile.TemporaryDirectory() as folder:
            db, study, service = self.build_stack(Path(folder))
            due_uid = self.make_question(db, code="Q-DUE", subject="Direito Tributário")
            error_uid = self.make_question(db, code="Q-ERR", subject="Contabilidade")
            other_uid = self.make_question(db, code="Q-OTHER", subject="Direito Tributário")
            study.sync_questions()
            past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
            with db.connect() as connection:
                connection.execute("UPDATE study_state SET due_at=?, wrong_count=0 WHERE question_uid=?", (past, due_uid))
                connection.execute("UPDATE study_state SET wrong_count=4 WHERE question_uid=?", (error_uid,))
                connection.execute("UPDATE study_state SET wrong_count=0, due_at=NULL WHERE question_uid=?", (other_uid,))

            review = service.question_batch(count=20, mode="review")["questions"]
            self.assertEqual({q["question_id"] for q in review}, {due_uid})
            self.assertTrue(review[0]["study_flags"]["due"])

            errors = service.question_batch(count=20, mode="errors")["questions"]
            self.assertEqual({q["question_id"] for q in errors}, {error_uid})
            self.assertEqual(errors[0]["study_flags"]["wrong_count"], 4)

            tributario = service.question_batch(count=20, mode="subject", subject="Direito Tributário")["questions"]
            self.assertEqual({q["question_id"] for q in tributario}, {due_uid, other_uid})

    def test_subject_mode_requires_subject(self):
        with tempfile.TemporaryDirectory() as folder:
            _db, _study, service = self.build_stack(Path(folder))
            with self.assertRaises(ValueError):
                service.question_batch(count=5, mode="subject", subject="")

    def test_mobile_screen_contains_setup_resume_and_summary(self):
        root = Path(__file__).resolve().parents[1]
        screen = (root / "mobile" / "app" / "(tabs)" / "questions.tsx").read_text(encoding="utf-8")
        self.assertIn("Como você quer estudar agora?", screen)
        self.assertIn("Continuar sessão", screen)
        self.assertIn("SESSÃO CONCLUÍDA", screen)
        self.assertIn("Meus erros", screen)
        self.assertIn("Por matéria", screen)
        self.assertIn("Tamanho da sessão", screen)


if __name__ == "__main__":
    unittest.main()
