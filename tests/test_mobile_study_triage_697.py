from __future__ import annotations

import tempfile
import unittest
import uuid
from pathlib import Path

from core.exam_projects import ExamProjectService
from core.mobile_foundation import MobileFoundationService
from core.storage import QuestFlowDatabase
from core.study import StudyRepository


class MobileStudyTriage697Tests(unittest.TestCase):
    def build_stack(self, root: Path):
        db = QuestFlowDatabase(root / "questflow.sqlite")
        study = StudyRepository(db)
        ExamProjectService(db)
        service = MobileFoundationService(db, study, control_plane_path=root / "mobile_control.sqlite")
        return db, study, service

    def make_question(self, db: QuestFlowDatabase, *, code: str, topic: str = "Atos administrativos") -> str:
        uid = db.create_manual_question()
        question = db.get_question(uid)
        self.assertIsNotNone(question)
        question["codigo_origem"] = code
        question["materia"] = "Direito Administrativo"
        question["assunto"] = topic
        question["aula"] = "Aula 01"
        question["enunciado"] = f"Enunciado {code}"
        question["alternativas"] = [
            {"chave": "A", "texto": "Correta"},
            {"chave": "B", "texto": "Incorreta"},
        ]
        question["gabarito"] = "A"
        question["explicacao"] = "Explicação"
        question["telegram"] = {
            "modo": "quiz",
            "pergunta": question["enunciado"],
            "opcoes": ["Correta", "Incorreta"],
            "indice_correto": 0,
        }
        question.setdefault("revisao", {})["status"] = "aprovado"
        db.update_question(uid, question, change_source="test_mobile_study_triage_697")
        return uid

    def pair(self, service: MobileFoundationService):
        pairing = service.create_pairing(requested_by="unittest")
        exchange = service.exchange_pairing(
            pairing["pairing_token"],
            {"device_id": str(uuid.uuid4()), "platform": "android", "name": "Galaxy Teste", "app_version": "0.4.0"},
        )
        return service.authenticate(exchange["access_token"])

    @staticmethod
    def event(event_type: str, uid: str | None = None, revision: int | None = None, payload: dict | None = None):
        return {
            "event_id": str(uuid.uuid4()),
            "schema_version": 1,
            "event_type": event_type,
            "session_id": "session-triage",
            "attempt_id": str(uuid.uuid4()),
            "question_id": uid,
            "question_revision": revision,
            "occurred_at": "2026-08-18T22:00:00-03:00",
            "client": {"platform": "android", "version": "0.4.0"},
            "payload": payload or {},
        }

    def test_correction_before_answer_enters_existing_correction_queue_without_attempt(self):
        with tempfile.TemporaryDirectory() as folder:
            db, study, service = self.build_stack(Path(folder))
            uid = self.make_question(db, code="Q-CORR")
            study.sync_questions()
            revision = service.question_for_mobile(uid)["question_revision"]
            auth = self.pair(service)

            result = service.ingest_events(auth, [self.event("question_correction_requested", uid, revision)])
            self.assertTrue(result["ok"])
            self.assertEqual(result["effects"][0]["effect"], "question_correction_queued")

            requests = study.list_review_requests("ativas")
            self.assertEqual(len(requests), 1)
            self.assertEqual(requests[0]["question_uid"], uid)
            self.assertEqual(requests[0]["source"], "mobile_preanswer")
            with db.connect() as connection:
                attempts = int(connection.execute("SELECT COUNT(*) FROM telegram_attempts").fetchone()[0])
                suspended = int(connection.execute("SELECT suspended FROM study_state WHERE question_uid=?", (uid,)).fetchone()[0])
            self.assertEqual(attempts, 0)
            self.assertEqual(suspended, 1)

    def test_not_studied_marks_topic_backlog_excludes_topic_and_does_not_create_error(self):
        with tempfile.TemporaryDirectory() as folder:
            db, study, service = self.build_stack(Path(folder))
            uid1 = self.make_question(db, code="Q-NS1")
            uid2 = self.make_question(db, code="Q-NS2")
            uid3 = self.make_question(db, code="Q-OTHER", topic="Poderes administrativos")
            study.sync_questions()
            revision = service.question_for_mobile(uid1)["question_revision"]
            auth = self.pair(service)

            result = service.ingest_events(auth, [self.event("topic_not_studied_reported", uid1, revision)])
            self.assertTrue(result["ok"])
            effect = result["effects"][0]
            self.assertEqual(effect["effect"], "topic_added_to_study_backlog")

            progress = service.progress_projection()
            self.assertEqual(progress["study_backlog"]["pending_count"], 1)
            self.assertEqual(progress["study_backlog"]["items"][0]["topic"], "Atos administrativos")
            self.assertEqual(progress["summary"]["attempts"], 0)

            batch_ids = {item["question_id"] for item in service.question_batch(count=20)["questions"]}
            self.assertNotIn(uid1, batch_ids)
            self.assertNotIn(uid2, batch_ids)
            self.assertIn(uid3, batch_ids)

    def test_marking_topic_studied_releases_it_back_to_question_batches(self):
        with tempfile.TemporaryDirectory() as folder:
            db, study, service = self.build_stack(Path(folder))
            uid = self.make_question(db, code="Q-RELEASE")
            study.sync_questions()
            revision = service.question_for_mobile(uid)["question_revision"]
            auth = self.pair(service)

            marked = service.ingest_events(auth, [self.event("topic_not_studied_reported", uid, revision)])
            backlog = marked["effects"][0]
            self.assertNotIn(uid, {item["question_id"] for item in service.question_batch(count=20)["questions"]})

            completed = self.event(
                "topic_study_completed",
                payload={"backlog_id": backlog["backlog_id"], "topic_key": backlog["topic_key"]},
            )
            result = service.ingest_events(auth, [completed])
            self.assertTrue(result["ok"])
            self.assertEqual(result["effects"][0]["effect"], "topic_released_after_study")
            self.assertEqual(service.progress_projection()["study_backlog"]["pending_count"], 0)
            self.assertIn(uid, {item["question_id"] for item in service.question_batch(count=20)["questions"]})


if __name__ == "__main__":
    unittest.main()
