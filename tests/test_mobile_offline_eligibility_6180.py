from __future__ import annotations

import json
import tempfile
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from core.mobile_foundation import MobileFoundationService
from core.storage import QuestFlowDatabase
from core.study import StudyRepository


class MobileOfflineEligibility6180Tests(unittest.TestCase):
    def build(self, root: Path):
        db = QuestFlowDatabase(root / "questflow.sqlite")
        study = StudyRepository(db)
        mobile = MobileFoundationService(db, study, control_plane_path=root / "mobile_control.sqlite")
        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        rows = []
        for index in range(45):
            uid = f"offline-elig-{index:03d}"
            data = {
                "uid": uid, "codigo_origem": f"OE{index}", "materia": f"Matéria {index % 3}",
                "assunto": f"Assunto {index % 7}", "aula": f"Aula {index % 9}", "enunciado": f"Questão {index}",
                "alternativas": [{"chave": "A", "texto": "Correta"}, {"chave": "B", "texto": "Incorreta"}],
                "gabarito": "A", "revisao": {"status": "aprovado"},
            }
            rows.append((uid, f"s{index}", f"OE{index}", f"f{index}", data["materia"], data["assunto"], data["assunto"], data["aula"],
                         "ok", 1.0, "test", "CEBRASPE", 2026, "Órgão", "Prova", "multiple_choice", "A", data["enunciado"],
                         "aprovado", 1.0, "", None, now, now, json.dumps(data, ensure_ascii=False)))
        with db.connect() as connection:
            connection.execute("CREATE TABLE IF NOT EXISTS qf_exam_projects(id TEXT PRIMARY KEY,name TEXT,agency TEXT,role TEXT,board TEXT,exam_date TEXT,status TEXT,active INTEGER)")
            connection.executemany(
                """INSERT INTO questions(uid,source_key,source_code,fingerprint,subject,primary_topic,topics_text,lesson,
                taxonomy_status,taxonomy_confidence,taxonomy_source,board,exam_year,agency,exam_name,question_type,answer,
                statement,review_status,confidence,source_file,source_page,created_at,updated_at,data_json)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", rows)
        study.sync_questions()
        pairing = mobile.create_pairing(requested_by="6180")
        exchange = mobile.exchange_pairing(pairing["pairing_token"], {"device_id": "offline-6180", "platform": "android", "name": "Test", "app_version": "0.13.0"})
        return db, study, mobile, mobile.authenticate(exchange["access_token"])

    def answer_and_set_due(self, db: QuestFlowDatabase, uid: str, *, due_in_days: int) -> None:
        attempt_id = str(uuid.uuid4())
        delivery_id = str(uuid.uuid4())
        answered = datetime.now(timezone.utc).replace(microsecond=0)
        due = answered + timedelta(days=due_in_days)
        with db.connect() as connection:
            connection.execute(
                "INSERT INTO telegram_deliveries(id,cycle_id,question_uid,poll_id,chat_id,message_id,sent_at,direct_poll,status) VALUES(?,?,?,?,?,?,?,1,'respondido')",
                (delivery_id, "cycle-6180", uid, f"poll-{attempt_id}", "chat", 1, answered.isoformat()),
            )
            connection.execute(
                "INSERT INTO telegram_attempts(id,delivery_id,question_uid,poll_id,user_id,selected_indices_json,is_correct,answered_at) VALUES(?,?,?,?,?,?,?,?)",
                (attempt_id, delivery_id, uid, f"poll-{attempt_id}", "user", "[0]", 1, answered.isoformat()),
            )
            connection.execute(
                """UPDATE study_state SET sent_count=1,correct_count=1,wrong_count=0,last_answered_at=?,due_at=?,fsrs_due_at=?,fsrs_state='review'
                   WHERE question_uid=?""",
                (answered.isoformat(), due.isoformat(), due.isoformat(), uid),
            )

    def test_answered_question_is_excluded_until_studio_spacing_is_due(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            db, _study, mobile, auth = self.build(Path(folder))
            uid = "offline-elig-000"
            self.answer_and_set_due(db, uid, due_in_days=5)
            pack = mobile.offline_study_pack(auth, count=30)
            ids = [q["question_id"] for q in pack["questions"]]
            self.assertNotIn(uid, ids)
            self.assertEqual(pack["eligibility_policy"], "never_answered_or_studio_due_v1")
            self.assertTrue(all(q["offline_eligibility"]["kind"] == "never_answered" for q in pack["questions"]))

            past = (datetime.now(timezone.utc) - timedelta(hours=1)).replace(microsecond=0).isoformat()
            with db.connect() as connection:
                connection.execute("UPDATE study_state SET due_at=?,fsrs_due_at=? WHERE question_uid=?", (past, past, uid))
            due_pack = mobile.offline_study_pack(auth, count=30)
            due_item = next(q for q in due_pack["questions"] if q["question_id"] == uid)
            self.assertEqual(due_item["offline_eligibility"]["kind"], "studio_spacing_due")
            self.assertTrue(due_item["offline_eligibility"]["answered_before"])

    def test_state_only_answer_evidence_is_not_misclassified_as_never_answered(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            db, _study, mobile, auth = self.build(Path(folder))
            uid = "offline-elig-002"
            future = (datetime.now(timezone.utc) + timedelta(days=10)).replace(microsecond=0).isoformat()
            # Simulate legacy/imported learner state with no telegram_attempts row.
            with db.connect() as connection:
                connection.execute(
                    "UPDATE study_state SET correct_count=2,wrong_count=1,last_answered_at=?,due_at=?,fsrs_due_at=?,fsrs_state='review' WHERE question_uid=?",
                    (datetime.now(timezone.utc).replace(microsecond=0).isoformat(), future, future, uid),
                )
            candidate = [{"question_id": uid, "code": "OE2", "subject": "Matéria 2"}]
            self.assertEqual(mobile._offline_pack_eligible_questions(candidate), [])

            past = (datetime.now(timezone.utc) - timedelta(minutes=5)).replace(microsecond=0).isoformat()
            with db.connect() as connection:
                connection.execute("UPDATE study_state SET due_at=?,fsrs_due_at=? WHERE question_uid=?", (past, past, uid))
            due_items = mobile._offline_pack_eligible_questions(candidate)
            self.assertEqual(len(due_items), 1)
            due_item = due_items[0]
            self.assertEqual(due_item["offline_eligibility"]["kind"], "studio_spacing_due")
            self.assertTrue(due_item["offline_eligibility"]["answered_before"])

    def test_pack_contains_no_answer_key_and_no_early_answered_reviews(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            db, _study, mobile, auth = self.build(Path(folder))
            self.answer_and_set_due(db, "offline-elig-001", due_in_days=30)
            pack = mobile.offline_study_pack(auth, count=25)
            for question in pack["questions"]:
                self.assertNotIn("answer", question)
                self.assertNotIn("correct_index", question)
                eligibility = question.get("offline_eligibility") or {}
                self.assertIn(eligibility.get("kind"), {"never_answered", "studio_spacing_due"})


if __name__ == "__main__":
    unittest.main()
