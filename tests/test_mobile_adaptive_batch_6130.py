from __future__ import annotations

import json
import tempfile
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from core.fsrs_adapter import rating_from_answer
from core.mobile_foundation import MobileFoundationService
from core.storage import QuestFlowDatabase
from core.study import SelectionFilters, StudyRepository


class MobileAdaptiveBatch6130Tests(unittest.TestCase):
    def build_stack(self, root: Path):
        db = QuestFlowDatabase(root / "questflow.sqlite")
        study = StudyRepository(db)
        mobile = MobileFoundationService(db, study, control_plane_path=root / "mobile_control.sqlite")
        return db, study, mobile

    @staticmethod
    def bulk_questions(db: QuestFlowDatabase, total: int = 1292) -> list[str]:
        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        rows = []
        uids = []
        for index in range(total):
            uid = f"q{index:04d}"
            uids.append(uid)
            subject = f"Matéria {index % 8}"
            topic = f"Assunto {index % 23}"
            lesson = f"Aula {index % 40}"
            data = {
                "uid": uid,
                "codigo_origem": f"Q{index}",
                "materia": subject,
                "assunto": topic,
                "aula": lesson,
                "enunciado": f"Questão {index}",
                "alternativas": [{"chave": "A", "texto": "Correta"}, {"chave": "B", "texto": "Incorreta"}],
                "gabarito": "A",
                "revisao": {"status": "aprovado"},
            }
            rows.append(
                (
                    uid, f"source-{index}", f"Q{index}", f"fingerprint-{index}", subject, topic, topic, lesson,
                    "ok", 1.0, "test", "CEBRASPE", 2026, "Órgão", "Prova", "multiple_choice", "A",
                    f"Questão {index}", "aprovado", 1.0, "", None, now, now, json.dumps(data, ensure_ascii=False),
                )
            )
        with db.connect() as connection:
            connection.executemany(
                """
                INSERT INTO questions(
                    uid,source_key,source_code,fingerprint,subject,primary_topic,topics_text,lesson,
                    taxonomy_status,taxonomy_confidence,taxonomy_source,board,exam_year,agency,exam_name,
                    question_type,answer,statement,review_status,confidence,source_file,source_page,
                    created_at,updated_at,data_json
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                rows,
            )
        return uids

    @staticmethod
    def pair(mobile: MobileFoundationService):
        pairing = mobile.create_pairing(requested_by="test_6130")
        exchange = mobile.exchange_pairing(
            pairing["pairing_token"],
            {"device_id": "adaptive-mobile-device", "platform": "android", "name": "Adaptive Test", "app_version": "0.10.1"},
        )
        return mobile.authenticate(exchange["access_token"])

    @staticmethod
    def event(auth: dict, event_type: str, *, session_id: str, question_uid: str = "", sequence: int = 1, payload: dict | None = None):
        return {
            "event_id": str(uuid.uuid4()),
            "event_type": event_type,
            "device_id": auth["device_id"],
            "session_id": session_id,
            "attempt_id": f"attempt-{session_id}-{sequence}",
            "question_id": question_uid or None,
            "occurred_at": datetime.now(timezone.utc).isoformat(),
            "sequence_no": sequence,
            "client": {"platform": "android", "version": "0.10.1"},
            "payload": payload or {},
        }

    def test_recommended_mix_uses_core_intelligence_and_does_not_become_review_only(self):
        """Regressão principal: 1292 questões, 1279 novas, 11 vencidas, lote recomendado=10."""
        with tempfile.TemporaryDirectory() as folder:
            db, study, mobile = self.build_stack(Path(folder))
            self.bulk_questions(db, 1292)
            study.sync_questions()
            now = datetime.now(timezone.utc).replace(microsecond=0)
            past = (now - timedelta(days=2)).isoformat()
            future = (now + timedelta(days=30)).isoformat()
            with db.connect() as connection:
                for index in range(13):
                    connection.execute(
                        "UPDATE study_state SET sent_count=1,last_sent_at=?,due_at=? WHERE question_uid=?",
                        (past, past if index < 11 else future, f"q{index:04d}"),
                    )

            batch = mobile.question_batch(count=10, mode="recommended")["questions"]
            self.assertEqual(len(batch), 10)
            self.assertTrue(any(q["study_flags"]["due"] for q in batch))
            self.assertTrue(any(int(q["study_flags"]["sent_count"]) == 0 for q in batch), "Recomendado não pode virar 100% Revisões quando há conteúdo novo elegível.")
            self.assertTrue(all(q["selection"]["source"] == "StudyRepository.select_questions" for q in batch))
            self.assertTrue(all(q["selection"]["policy"] == "recommended-adaptive-v2" for q in batch))

            review = mobile.question_batch(count=20, mode="review")["questions"]
            self.assertTrue(review)
            self.assertTrue(all(q["study_flags"]["review_eligible"] for q in review))
            self.assertTrue(all(int(q["study_flags"]["sent_count"]) > 0 for q in review))

    def test_recent_opening_and_skipped_question_receive_cooldown_but_due_content_is_preserved(self):
        with tempfile.TemporaryDirectory() as folder:
            db, study, mobile = self.build_stack(Path(folder))
            self.bulk_questions(db, 40)
            study.sync_questions()
            past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
            with db.connect() as connection:
                connection.execute("UPDATE study_state SET sent_count=1,due_at=?", (past,))

            first_batch = mobile.question_batch(count=10, mode="recommended")["questions"]
            opening = first_batch[0]["question_id"]
            auth = self.pair(mobile)
            session_id = "previous-session"
            result = mobile.ingest_events(
                auth,
                [
                    self.event(auth, "session_started", session_id=session_id, sequence=1),
                    self.event(auth, "question_presented", session_id=session_id, question_uid=opening, sequence=2, payload={"position": 1}),
                    self.event(auth, "question_skipped", session_id=session_id, question_uid=opening, sequence=3, payload={"reason": "user_skip"}),
                ],
            )
            self.assertTrue(result["ok"])

            second = mobile.question_batch(count=10, mode="recommended", learner_id=auth["learner_id"])["questions"]
            self.assertNotEqual(second[0]["question_id"], opening)
            repeated = next((q for q in second if q["question_id"] == opening), None)
            if repeated is not None:
                self.assertGreater(float(repeated["selection"]["recent_exposure_penalty"]), 0.0)
            self.assertTrue(any(q["study_flags"]["due"] for q in second), "Cooldown não pode eliminar revisões vencidas.")

    def test_low_or_medium_confidence_prioritizes_different_question_from_same_concept(self):
        with tempfile.TemporaryDirectory() as folder:
            db, study, mobile = self.build_stack(Path(folder))
            uids = self.bulk_questions(db, 12)
            study.sync_questions()
            # Garante dois itens do mesmo conceito.
            with db.connect() as connection:
                for uid in (uids[0], uids[1]):
                    question = json.loads(connection.execute("SELECT data_json FROM questions WHERE uid=?", (uid,)).fetchone()[0])
                    question["materia"] = "Direito Tributário"
                    question["assunto"] = "Crédito tributário"
                    question["aula"] = "Aula 05"
                    connection.execute(
                        "UPDATE questions SET subject=?,primary_topic=?,lesson=?,data_json=? WHERE uid=?",
                        ("Direito Tributário", "Crédito tributário", "Aula 05", json.dumps(question, ensure_ascii=False), uid),
                    )
            auth = self.pair(mobile)
            result = mobile.ingest_events(
                auth,
                [self.event(auth, "confidence_reported", session_id="uncertain", question_uid=uids[0], sequence=1, payload={"confidence": "medium"})],
            )
            self.assertTrue(result["ok"])
            batch = mobile.question_batch(count=5, mode="recommended", learner_id=auth["learner_id"])["questions"]
            transfer = [q for q in batch if q["selection"].get("topic_transfer")]
            self.assertTrue(transfer)
            self.assertNotEqual(transfer[0]["question_id"], uids[0])
            self.assertEqual(transfer[0]["subject"], "Direito Tributário")
            self.assertEqual(transfer[0]["topic"], "Crédito tributário")

    def test_first_correct_answer_is_not_hard_only_because_history_is_empty(self):
        self.assertEqual(
            rating_from_answer(correct=True, response_seconds=20, prior_accuracy=0.50, prior_attempts=0, confidence="sabia"),
            3,
        )
        self.assertEqual(
            rating_from_answer(correct=True, response_seconds=20, prior_accuracy=0.50, prior_attempts=4, confidence="sabia"),
            2,
        )

    def test_mobile_batch_is_a_session_policy_over_the_same_core_selector(self):
        with tempfile.TemporaryDirectory() as folder:
            db, study, mobile = self.build_stack(Path(folder))
            self.bulk_questions(db, 80)
            study.sync_questions()
            core = study.select_questions(
                SelectionFilters(subjects=[], approved_only=True, strategy="auditor_inteligente", recycle_when_empty=True),
                80,
                persist_state=False,
            )
            core_ids = {str(q.get("database_uid") or "") for q in core}
            batch = mobile.question_batch(count=10, mode="recommended")["questions"]
            self.assertTrue(batch)
            self.assertTrue({q["question_id"] for q in batch}.issubset(core_ids))
            self.assertTrue(all(q["selection"]["core_policy"] == "auditor_inteligente" for q in batch))


if __name__ == "__main__":
    unittest.main()
