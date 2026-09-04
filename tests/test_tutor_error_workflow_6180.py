from __future__ import annotations

import tempfile
import unittest
import uuid
from pathlib import Path

from core.engines import EngineRegistry
from core.question_services import QuestionCommandService, QuestionQueryService
from core.storage import QuestFlowDatabase
from core.study import StudyRepository

ROOT = Path(__file__).resolve().parents[1]


class TutorErrorWorkflow6180Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="qf-tutor-workflow-6180-")
        self.db = QuestFlowDatabase(Path(self.tmp.name) / "questflow.sqlite")
        self.study = StudyRepository(self.db)
        self.queries = QuestionQueryService(self.db)
        self.commands = QuestionCommandService(self.db)
        self.engines = EngineRegistry.build(database=self.db, queries=self.queries, commands=self.commands, study=self.study)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def make_question(self, code: str = "Q6180") -> str:
        uid = self.db.create_manual_question(None)
        q = self.db.get_question(uid); assert q
        q.update({
            "codigo_origem": code,
            "materia": "AUDITORIA",
            "assunto": "CONTROLE INTERNO",
            "aula_planilha": "Aula 05",
            "enunciado": "Assinale a alternativa correta.",
            "alternativas": [
                {"chave": "A", "texto": "Alternativa correta."},
                {"chave": "B", "texto": "Alternativa incorreta."},
            ],
            "gabarito": "A",
            "explicacao": "Comentário da questão.",
            "revisao": {"status": "aprovado", "confianca": 1.0, "alertas": []},
        })
        self.db.update_question(uid, q)
        self.study.sync_questions()
        return uid

    def add_error(self, uid: str, answered_at: str) -> str:
        attempt_id = str(uuid.uuid4())
        delivery_id = str(uuid.uuid4())
        with self.db.connect() as connection:
            connection.execute(
                "INSERT INTO telegram_deliveries(id,cycle_id,question_uid,poll_id,chat_id,message_id,sent_at,direct_poll,status) VALUES(?,?,?,?,?,?,?,1,'respondido')",
                (delivery_id, "cycle-6180", uid, f"poll-{attempt_id}", "chat", 1, answered_at),
            )
            connection.execute(
                """INSERT INTO telegram_attempts(
                       id,delivery_id,question_uid,poll_id,user_id,username,selected_indices_json,is_correct,answered_at,confidence,response_seconds
                   ) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (attempt_id, delivery_id, uid, f"poll-{attempt_id}", "user", "tester", "[1]", 0, answered_at, "medium", 20),
            )
        return attempt_id

    def approve_tutor(self, uid: str, reviewed_at: str) -> str:
        iid = self.engines.governance.record_interaction(
            question_uid=uid, interaction_type="tutor", mode="professor",
            provider="QuestFlow Grounded Composer", model="qf-tutor-grounded-2",
            prompt_text="Explique o erro.", response_text="Gabarito: A. Fundamentação.",
            learner_context={}, sources=[], diagnosis={},
        )
        self.engines.governance.review_interaction(iid, decision="aprovar", note="Tratamento concluído.")
        with self.db.connect() as connection:
            connection.execute("UPDATE qf_ai_interactions SET reviewed_at=? WHERE id=?", (reviewed_at, iid))
        return iid

    def test_approved_tutor_moves_latest_error_to_treated_and_new_error_reopens_queue(self) -> None:
        uid = self.make_question()
        self.add_error(uid, "2026-08-21T10:00:00+00:00")
        first = self.engines.ai.workspace(uid)
        self.assertEqual([x["question_uid"] for x in first["error_review_queue"]], [uid])
        self.assertEqual(first["treated_errors"], [])

        self.approve_tutor(uid, "2026-08-21T10:30:00+00:00")
        treated = self.engines.ai.workspace(uid)
        self.assertNotIn(uid, [x["question_uid"] for x in treated["error_review_queue"]])
        treated_item = next(x for x in treated["treated_errors"] if x["question_uid"] == uid)
        self.assertTrue(treated_item["treated"])
        self.assertEqual(treated_item["workflow_status"], "tratado")

        self.add_error(uid, "2026-08-21T11:00:00+00:00")
        reopened = self.engines.ai.workspace(uid)
        pending_item = next(x for x in reopened["error_review_queue"] if x["question_uid"] == uid)
        self.assertFalse(pending_item["treated"])
        self.assertEqual(pending_item["workflow_status"], "revisar")
        self.assertNotIn(uid, [x["question_uid"] for x in reopened["treated_errors"]])

    def test_workspace_keeps_recent_errors_as_backward_compatible_pending_alias(self) -> None:
        uid = self.make_question("Q6180-COMPAT")
        self.add_error(uid, "2026-08-21T10:00:00+00:00")
        workspace = self.engines.ai.workspace(uid)
        self.assertEqual(workspace["recent_errors"], workspace["error_review_queue"])

    def test_web_ui_names_workflow_and_refreshes_after_human_review(self) -> None:
        html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
        js = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        css = (ROOT / "web" / "styles.css").read_text(encoding="utf-8")
        self.assertIn("Revisão de Erros com o Tutor IA", html)
        self.assertIn("Erros Tratados", html)
        self.assertIn('id="tutorTreatedErrors"', html)
        self.assertIn("workspace.treated_errors", js)
        self.assertIn("await loadTutorPage(state.tutorSelectedUid || '')", js)
        self.assertIn(".tutor-queue-column", css)


if __name__ == "__main__":
    unittest.main()
