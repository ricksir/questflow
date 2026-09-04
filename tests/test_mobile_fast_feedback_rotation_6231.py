from __future__ import annotations

import json
import tempfile
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from core.mobile_foundation import MobileFoundationService
from core.storage import QuestFlowDatabase
from core.study import StudyRepository


class MobileFastFeedbackRotation6231Tests(unittest.TestCase):
    def build(self, root: Path, total: int = 36):
        db = QuestFlowDatabase(root / "questflow.sqlite")
        study = StudyRepository(db)
        mobile = MobileFoundationService(db, study, control_plane_path=root / "mobile_control.sqlite")
        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        rows = []
        for index in range(total):
            uid = f"fast-rotation-{index:03d}"
            data = {
                "uid": uid,
                "codigo_origem": f"FR{index}",
                "materia": f"Matéria {index % 4}",
                "assunto": f"Assunto {index % 9}",
                "aula": f"Aula {index % 12}",
                "enunciado": f"Questão {index}",
                "alternativas": [
                    {"chave": "A", "texto": "Correta"},
                    {"chave": "B", "texto": "Incorreta"},
                ],
                "gabarito": "A",
                "explicacao": f"Explicação {index}",
                "revisao": {"status": "aprovado"},
            }
            rows.append((
                uid, f"source-{index}", f"FR{index}", f"fingerprint-{index}",
                data["materia"], data["assunto"], data["assunto"], data["aula"],
                "ok", 1.0, "test", "CEBRASPE", 2026, "Órgão", "Prova",
                "multiple_choice", "A", data["enunciado"], "aprovado", 1.0,
                "", None, now, now, json.dumps(data, ensure_ascii=False),
            ))
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
        study.sync_questions()
        pairing = mobile.create_pairing(requested_by="test-6231")
        exchange = mobile.exchange_pairing(pairing["pairing_token"], {
            "device_id": "mobile-fast-6231",
            "platform": "android",
            "name": "Fast Feedback Test",
            "app_version": "0.15.6",
        })
        return db, study, mobile, mobile.authenticate(exchange["access_token"]), exchange["access_token"]

    @staticmethod
    def event(auth: dict, event_type: str, *, attempt_id: str, session_id: str, uid: str, sequence: int, payload: dict):
        return {
            "event_id": str(uuid.uuid4()),
            "event_type": event_type,
            "device_id": auth["device_id"],
            "session_id": session_id,
            "attempt_id": attempt_id,
            "question_id": uid,
            "question_revision": 1,
            "occurred_at": datetime.now(timezone.utc).isoformat(),
            "sequence_no": sequence,
            "client": {"platform": "android", "version": "0.15.6"},
            "payload": payload,
        }

    def test_fast_sync_returns_feedback_before_rebuild_and_durable_drain_finishes_it(self):
        with tempfile.TemporaryDirectory() as folder:
            db, study, mobile, auth, token = self.build(Path(folder))
            mobile.projection_scheduler = lambda: None
            uid = "fast-rotation-000"
            attempt_id = str(uuid.uuid4())
            session_id = str(uuid.uuid4())
            events = [
                self.event(auth, "confidence_reported", attempt_id=attempt_id, session_id=session_id, uid=uid, sequence=1, payload={"confidence": "high"}),
                self.event(auth, "answer_submitted", attempt_id=attempt_id, session_id=session_id, uid=uid, sequence=2, payload={
                    "selected_index": 0,
                    "confidence": "high",
                    "active_response_seconds": 18,
                    "wall_response_seconds": 19,
                    "idle_seconds": 1,
                    "timing_source": "active_timer",
                }),
            ]
            with patch.object(study, "project_local_practice_attempt", wraps=study.project_local_practice_attempt) as projector:
                status, payload = mobile.http_request(
                    method="POST",
                    path="/api/v1/mobile/sync",
                    headers={"Authorization": f"Bearer {token}"},
                    body={
                        "cursor": 0,
                        "events": events,
                        "limit": 1,
                        "refresh_offline_pack": False,
                        "feedback_attempt_id": attempt_id,
                    },
                    query={},
                )
                self.assertEqual(status, 200)
                self.assertTrue(payload["ok"])
                self.assertTrue(payload["feedback"]["is_correct"])
                self.assertEqual(payload["feedback"]["explanation"], "Explicação 0")
                self.assertTrue(payload["projection_pending"])
                projector.assert_not_called()

                with db.connect() as connection:
                    pending = connection.execute(
                        "SELECT process_status FROM qf_learning_events WHERE attempt_id=? AND event_type='answer_submitted'",
                        (attempt_id,),
                    ).fetchone()
                    attempt = connection.execute("SELECT is_correct FROM telegram_attempts WHERE id=?", (attempt_id,)).fetchone()
                self.assertEqual(pending["process_status"], "projection_pending")
                self.assertEqual(attempt["is_correct"], 1)

                drained = mobile.process_pending_attempt_projections()
                self.assertEqual(drained["processed"], 1)
                self.assertEqual(drained["failed"], 0)
                projector.assert_called_once()

            with db.connect() as connection:
                applied = connection.execute(
                    "SELECT process_status FROM qf_learning_events WHERE attempt_id=? AND event_type='answer_submitted'",
                    (attempt_id,),
                ).fetchone()
                state = connection.execute(
                    "SELECT correct_count,wrong_count,last_answered_at FROM study_state WHERE question_uid=?",
                    (uid,),
                ).fetchone()
            self.assertEqual(applied["process_status"], "applied")
            self.assertEqual(state["correct_count"], 1)
            self.assertEqual(state["wrong_count"], 0)
            self.assertTrue(state["last_answered_at"])

    def test_recommended_new_block_excludes_previous_block_but_review_mode_remains_explicit(self):
        with tempfile.TemporaryDirectory() as folder:
            db, study, mobile, auth, _token = self.build(Path(folder))
            previous = ["fast-rotation-000", "fast-rotation-001", "fast-rotation-002"]
            for index, uid in enumerate(previous):
                study.record_local_practice_attempt(
                    uid,
                    1 if index == 0 else 0,
                    session_id="previous-block",
                    source="mobile_android",
                    attempt_id_override=f"previous-attempt-{index}",
                    learner_id=auth["learner_id"],
                    device_id=auth["device_id"],
                )
            recommended_exclusions = mobile._session_start_exclusions(auth["learner_id"], "", "recommended")
            review_exclusions = mobile._session_start_exclusions(auth["learner_id"], "", "review")
            self.assertTrue(set(previous).issubset(recommended_exclusions))
            self.assertTrue(set(previous).isdisjoint(review_exclusions))

            next_session = mobile.start_adaptive_study_session(
                auth,
                session_id="next-block",
                count=10,
                mode="recommended",
                micro_batch_size=5,
            )
            next_ids = {item["question_id"] for item in next_session["micro_batch"]["questions"]}
            self.assertTrue(next_ids)
            self.assertTrue(next_ids.isdisjoint(previous))

            past = (datetime.now(timezone.utc) - timedelta(minutes=5)).replace(microsecond=0).isoformat()
            with db.connect() as connection:
                connection.execute(
                    "UPDATE study_state SET due_at=?,fsrs_due_at=? WHERE question_uid IN (?,?,?)",
                    (past, past, *previous),
                )
            review = mobile.question_batch(
                count=10,
                mode="review",
                learner_id=auth["learner_id"],
            )["questions"]
            review_ids = {item["question_id"] for item in review}
            self.assertTrue(review_ids.intersection(previous))

    def test_mobile_source_has_no_blocking_full_sync_in_next_question_path(self):
        source = (Path(__file__).resolve().parents[1] / "mobile" / "app" / "(tabs)" / "questions.tsx").read_text(encoding="utf-8")
        prefetch = source[source.index("const prefetchNextMicroBatch"):source.index("const loadNextAdaptiveMicroBatch")]
        load_next = source[source.index("const loadNextAdaptiveMicroBatch"):source.index("const nextQuestion")]
        finish = source[source.index("const finishUnderstanding"):source.index("const skip")]
        self.assertNotIn("await syncNow()", prefetch)
        self.assertNotIn("await syncNow()", load_next)
        self.assertNotIn("await syncNow()", finish)
        self.assertIn("syncNow().catch", finish)
        self.assertIn("rotatePreviousBlock", source)


if __name__ == "__main__":
    unittest.main()
