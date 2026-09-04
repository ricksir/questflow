from __future__ import annotations

import json
import tempfile
import unittest
import uuid
from datetime import datetime, timezone
from pathlib import Path

from core.mobile_foundation import MobileFoundationService
from core.storage import QuestFlowDatabase
from core.study import StudyRepository


class AdaptiveSessionOrchestrator6140Tests(unittest.TestCase):
    def build_stack(self, root: Path):
        db = QuestFlowDatabase(root / "questflow.sqlite")
        study = StudyRepository(db)
        mobile = MobileFoundationService(db, study, control_plane_path=root / "mobile_control.sqlite")
        return db, study, mobile

    @staticmethod
    def seed_questions(db: QuestFlowDatabase, total: int = 60) -> list[str]:
        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        rows = []
        uids = []
        for index in range(total):
            uid = f"q{index:04d}"
            uids.append(uid)
            subject = f"Matéria {index % 4}"
            topic = f"Assunto {index % 8}"
            lesson = f"Aula {index % 12}"
            if index in (0, 1, 2):
                subject, topic, lesson = "Direito Tributário", "Crédito tributário", "Aula 05"
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
            rows.append((uid, f"s{index}", f"Q{index}", f"f{index}", subject, topic, topic, lesson,
                         "ok", 1.0, "test", "CEBRASPE", 2026, "Órgão", "Prova", "multiple_choice", "A",
                         f"Questão {index}", "aprovado", 1.0, "", None, now, now, json.dumps(data, ensure_ascii=False)))
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
    def auth(mobile: MobileFoundationService):
        pairing = mobile.create_pairing(requested_by="6140")
        exchange = mobile.exchange_pairing(pairing["pairing_token"], {
            "device_id": "adaptive-6140", "platform": "android", "name": "Test", "app_version": "0.10.1"
        })
        return mobile.authenticate(exchange["access_token"]), exchange["access_token"]

    @staticmethod
    def event(auth: dict, event_type: str, *, session_id: str, attempt_id: str, uid: str, seq: int, payload: dict):
        return {
            "event_id": str(uuid.uuid4()), "event_type": event_type, "device_id": auth["device_id"],
            "session_id": session_id, "attempt_id": attempt_id, "question_id": uid,
            "occurred_at": datetime.now(timezone.utc).isoformat(), "sequence_no": seq,
            "client": {"platform": "android", "version": "0.10.1"}, "payload": payload,
        }

    def test_starts_with_three_question_microbatch_and_explicit_goal(self):
        with tempfile.TemporaryDirectory() as folder:
            db, study, mobile = self.build_stack(Path(folder))
            self.seed_questions(db)
            study.sync_questions()
            auth, _token = self.auth(mobile)
            result = mobile.start_adaptive_study_session(
                auth, session_id="s-6140-a", count=10, mode="recommended", micro_batch_size=3
            )
            self.assertEqual(result["target_questions"], 10)
            self.assertEqual(result["micro_batch_size"], 3)
            self.assertEqual(len(result["micro_batch"]["questions"]), 3)
            self.assertTrue(result["goal"]["headline"])
            self.assertGreaterEqual(result["goal"]["estimated_minutes"], 1)
            self.assertTrue(all(q["selection"]["strategy_profile"] == "balanced" for q in result["micro_batch"]["questions"]))

    def test_prefetch_is_reused_and_high_confidence_error_can_invalidate_it(self):
        with tempfile.TemporaryDirectory() as folder:
            db, study, mobile = self.build_stack(Path(folder))
            self.seed_questions(db)
            study.sync_questions()
            auth, _token = self.auth(mobile)
            started = mobile.start_adaptive_study_session(auth, session_id="s-6140-b", count=9, mode="recommended")
            first_ids = [q["question_id"] for q in started["micro_batch"]["questions"]]
            prefetched = mobile.next_adaptive_micro_batch(auth, "s-6140-b", purpose="prefetch", excluded_uids=first_ids)
            pre = prefetched["micro_batch"]
            self.assertEqual(len(pre["questions"]), 3)
            repeated_prefetch = mobile.next_adaptive_micro_batch(auth, "s-6140-b", purpose="prefetch", excluded_uids=first_ids)
            self.assertEqual(repeated_prefetch["micro_batch"]["batch_id"], pre["batch_id"])

            # Resposta errada com confiança alta: o efeito é aplicado antes do próximo replanejamento.
            uid = first_ids[-1]
            attempt = "attempt-misconception"
            events = [
                self.event(auth, "confidence_reported", session_id="s-6140-b", attempt_id=attempt, uid=uid, seq=1, payload={"confidence": "high"}),
                self.event(auth, "answer_submitted", session_id="s-6140-b", attempt_id=attempt, uid=uid, seq=2, payload={"selected_index": 1, "confidence": "high", "active_response_seconds": 20, "timing_source": "client_active_timer_v1"}),
            ]
            ingested = mobile.ingest_events(auth, events)
            self.assertTrue(ingested["ok"])
            replanned = mobile.next_adaptive_micro_batch(
                auth, "s-6140-b", purpose="active", prefetched_batch_id=pre["batch_id"], force_replan=True,
                excluded_uids=first_ids,
            )["micro_batch"]
            self.assertNotEqual(replanned["batch_id"], pre["batch_id"])
            self.assertEqual(replanned["strategy_profile"], "consolidate")
            with db.connect() as connection:
                old = connection.execute("SELECT status FROM qf_adaptive_microbatches WHERE batch_id=?", (pre["batch_id"],)).fetchone()
            self.assertEqual(old["status"], "invalidated")

    def test_prefetch_is_automatically_invalidated_when_strategy_changes(self):
        with tempfile.TemporaryDirectory() as folder:
            db, study, mobile = self.build_stack(Path(folder))
            self.seed_questions(db)
            study.sync_questions()
            auth, _token = self.auth(mobile)
            started = mobile.start_adaptive_study_session(auth, session_id="s-6140-auto", count=9, mode="recommended")
            first_ids = [q["question_id"] for q in started["micro_batch"]["questions"]]
            pre = mobile.next_adaptive_micro_batch(auth, "s-6140-auto", purpose="prefetch", excluded_uids=first_ids)["micro_batch"]
            uid = first_ids[-1]
            attempt = "attempt-auto-misconception"
            mobile.ingest_events(auth, [
                self.event(auth, "confidence_reported", session_id="s-6140-auto", attempt_id=attempt, uid=uid, seq=1, payload={"confidence": "high"}),
                self.event(auth, "answer_submitted", session_id="s-6140-auto", attempt_id=attempt, uid=uid, seq=2, payload={"selected_index": 1, "confidence": "high", "active_response_seconds": 20, "timing_source": "client_active_timer_v1"}),
            ])
            promoted = mobile.next_adaptive_micro_batch(
                auth, "s-6140-auto", purpose="active", prefetched_batch_id=pre["batch_id"], force_replan=False, excluded_uids=first_ids
            )["micro_batch"]
            self.assertNotEqual(promoted["batch_id"], pre["batch_id"])
            self.assertTrue(promoted.get("prefetch_invalidated"))
            self.assertTrue(str(promoted.get("prefetch_invalidation_reason") or "").startswith(("strategy_changed", "new_misconception")))
            self.assertEqual(promoted["strategy_profile"], "consolidate")

    def test_misconception_prioritizes_transfer_question_not_same_item(self):
        with tempfile.TemporaryDirectory() as folder:
            db, study, mobile = self.build_stack(Path(folder))
            self.seed_questions(db)
            study.sync_questions()
            auth, _token = self.auth(mobile)
            started = mobile.start_adaptive_study_session(auth, session_id="s-6140-c", count=8, mode="recommended")
            # Force a misconception on q0000, whose concept also has q0001/q0002.
            uid = "q0000"
            attempt = "attempt-transfer"
            mobile.ingest_events(auth, [
                self.event(auth, "confidence_reported", session_id="s-6140-c", attempt_id=attempt, uid=uid, seq=1, payload={"confidence": "high"}),
                self.event(auth, "answer_submitted", session_id="s-6140-c", attempt_id=attempt, uid=uid, seq=2, payload={"selected_index": 1, "confidence": "high", "active_response_seconds": 30, "timing_source": "client_active_timer_v1"}),
            ])
            already = [q["question_id"] for q in started["micro_batch"]["questions"]]
            next_batch = mobile.next_adaptive_micro_batch(auth, "s-6140-c", purpose="active", force_replan=True, excluded_uids=already)["micro_batch"]
            transfers = [q for q in next_batch["questions"] if q.get("selection", {}).get("topic_transfer")]
            if "q0001" not in already or "q0002" not in already:
                self.assertTrue(transfers, "Misconception deve gerar tentativa de transferência conceitual quando houver item elegível.")
                self.assertTrue(all(q["question_id"] != uid for q in transfers))

    def test_decision_is_auditable_in_studio(self):
        with tempfile.TemporaryDirectory() as folder:
            db, study, mobile = self.build_stack(Path(folder))
            self.seed_questions(db, 20)
            study.sync_questions()
            auth, _token = self.auth(mobile)
            started = mobile.start_adaptive_study_session(auth, session_id="s-6140-d", count=5, mode="recommended")
            uid = started["micro_batch"]["questions"][0]["question_id"]
            explanation = mobile.adaptive_sessions.explain_question(uid, session_id="s-6140-d")
            self.assertEqual(explanation["question"]["uid"], uid)
            self.assertTrue(explanation["reason"])
            self.assertIn("retenção", explanation["principle"].lower())
            self.assertIn("selection", explanation["decision"])


if __name__ == "__main__":
    unittest.main()
