from __future__ import annotations

import tempfile
import unittest
import uuid
from pathlib import Path

from core.exam_projects import ExamProjectService
from core.mobile_foundation import MobileFoundationService, assess_response_timing
from core.storage import QuestFlowDatabase
from core.study import StudyRepository


class MobileIntegrationFoundation690Tests(unittest.TestCase):
    def build_stack(self, root: Path, name: str = "questflow.sqlite"):
        db = QuestFlowDatabase(root / name)
        study = StudyRepository(db)
        ExamProjectService(db)
        service = MobileFoundationService(
            db,
            study,
            control_plane_path=root / (name + ".control.sqlite"),
        )
        return db, study, service

    def make_question(self, db: QuestFlowDatabase, *, subject: str = "Direito Administrativo") -> str:
        uid = db.create_manual_question()
        question = db.get_question(uid)
        self.assertIsNotNone(question)
        question["materia"] = subject
        question["assunto"] = "Atos administrativos"
        question["enunciado"] = "Assinale a alternativa correta para o teste mobile."
        question["alternativas"] = [
            {"chave": "A", "texto": "Alternativa correta na revisão inicial."},
            {"chave": "B", "texto": "Alternativa incorreta na revisão inicial."},
        ]
        question["gabarito"] = "A"
        question["explicacao"] = "Explicação da revisão inicial."
        question["telegram"] = {
            "modo": "quiz",
            "pergunta": question["enunciado"],
            "opcoes": ["Alternativa correta na revisão inicial.", "Alternativa incorreta na revisão inicial."],
            "indice_correto": 0,
        }
        question.setdefault("revisao", {})["status"] = "aprovado"
        db.update_question(uid, question, change_source="test_mobile_690")
        return uid

    def pair(self, service: MobileFoundationService, device_id: str | None = None):
        pairing = service.create_pairing(requested_by="unittest")
        exchange = service.exchange_pairing(
            pairing["pairing_token"],
            {
                "device_id": device_id or str(uuid.uuid4()),
                "platform": "ios",
                "name": "iPhone Teste",
                "app_version": "0.1.0",
            },
        )
        return exchange, service.authenticate(exchange["access_token"])

    @staticmethod
    def answer_event(uid: str, revision: int, *, attempt_id: str, event_id: str | None = None, selected: int = 0, payload: dict | None = None):
        answer_payload = {"selected_index": selected}
        answer_payload.update(payload or {})
        return {
            "event_id": event_id or str(uuid.uuid4()),
            "schema_version": 1,
            "event_type": "answer_submitted",
            "attempt_id": attempt_id,
            "session_id": "session-test",
            "question_id": uid,
            "question_revision": revision,
            "occurred_at": "2026-08-17T12:00:00-03:00",
            "client": {"platform": "ios", "version": "0.1.0"},
            "payload": answer_payload,
        }

    def test_timing_gate_separates_active_time_from_open_screen_time(self):
        good = assess_response_timing(
            active_seconds=42,
            wall_seconds=3600,
            idle_seconds=3558,
            source="client_active_timer_v1",
        )
        self.assertTrue(good.eligible_for_speed_models)
        self.assertEqual(good.quality, "active_filtered")
        self.assertEqual(good.active_seconds, 42)

        contaminated = assess_response_timing(
            wall_seconds=3600,
            source="wall_clock",
        )
        self.assertFalse(contaminated.eligible_for_speed_models)
        self.assertEqual(contaminated.quality, "idle_contaminated")
        self.assertIsNone(contaminated.active_seconds)

        foreground_abandoned = assess_response_timing(
            active_seconds=900,
            wall_seconds=900,
            idle_seconds=0,
            source="client_active_timer_v1",
            interaction_count=2,
            max_idle_gap_seconds=850,
        )
        self.assertFalse(foreground_abandoned.eligible_for_speed_models)
        self.assertEqual(foreground_abandoned.quality, "idle_contaminated")

    def test_idempotent_event_and_timing_projection_exclude_idle_contamination(self):
        with tempfile.TemporaryDirectory() as folder:
            db, _study, service = self.build_stack(Path(folder))
            uid = self.make_question(db)
            revision = service.question_for_mobile(uid)["question_revision"]
            _exchange, auth = self.pair(service)

            attempt1 = str(uuid.uuid4())
            event1 = self.answer_event(
                uid,
                revision,
                attempt_id=attempt1,
                payload={
                    "active_response_seconds": 42,
                    "wall_response_seconds": 3600,
                    "idle_seconds": 3558,
                    "timing_source": "client_active_timer_v1",
                },
            )
            first = service.ingest_events(auth, [event1])
            second = service.ingest_events(auth, [event1])
            self.assertEqual(first["accepted"], [event1["event_id"]])
            self.assertEqual(second["duplicates"], [event1["event_id"]])

            attempt2 = str(uuid.uuid4())
            event2 = self.answer_event(
                uid,
                revision,
                attempt_id=attempt2,
                selected=1,
                payload={
                    "wall_response_seconds": 4000,
                    "timing_source": "wall_clock",
                },
            )
            service.ingest_events(auth, [event2])

            with db.connect() as connection:
                attempts = int(connection.execute("SELECT COUNT(*) FROM telegram_attempts").fetchone()[0])
                row1 = connection.execute(
                    "SELECT response_seconds,response_wall_seconds,response_idle_seconds,timing_quality FROM telegram_attempts WHERE id=?",
                    (attempt1,),
                ).fetchone()
                row2 = connection.execute(
                    "SELECT response_seconds,response_wall_seconds,timing_quality FROM telegram_attempts WHERE id=?",
                    (attempt2,),
                ).fetchone()
            self.assertEqual(attempts, 2)
            self.assertAlmostEqual(float(row1["response_seconds"]), 42.0)
            self.assertAlmostEqual(float(row1["response_wall_seconds"]), 3600.0)
            self.assertAlmostEqual(float(row1["response_idle_seconds"]), 3558.0)
            self.assertEqual(row1["timing_quality"], "active_filtered")
            self.assertIsNone(row2["response_seconds"])
            self.assertEqual(row2["timing_quality"], "idle_contaminated")

            progress = service.progress_projection()
            self.assertEqual(progress["summary"]["attempts"], 2)
            self.assertAlmostEqual(progress["summary"]["avg_active_response_seconds"], 42.0)
            self.assertEqual(progress["summary"]["timing_samples_excluded"], 1)

    def test_question_revision_snapshot_preserves_historical_answer(self):
        with tempfile.TemporaryDirectory() as folder:
            db, _study, service = self.build_stack(Path(folder))
            uid = self.make_question(db)
            public_v1 = service.question_for_mobile(uid)
            self.assertEqual(public_v1["question_revision"], 1)
            self.assertNotIn("gabarito", public_v1)
            self.assertNotIn("explanation", public_v1)

            changed = db.get_question(uid)
            changed["gabarito"] = "B"
            changed["explicacao"] = "Explicação da revisão 2."
            changed["telegram"]["indice_correto"] = 1
            db.update_question(uid, changed, change_source="test_revision_690")
            public_v2 = service.question_for_mobile(uid)
            self.assertEqual(public_v2["question_revision"], 2)

            _exchange, auth = self.pair(service)
            attempt_id = str(uuid.uuid4())
            result = service.ingest_events(
                auth,
                [self.answer_event(uid, 1, attempt_id=attempt_id, selected=0)],
            )
            self.assertTrue(result["ok"])
            feedback = service.feedback_for_attempt(auth, attempt_id)
            self.assertTrue(feedback["is_correct"])
            self.assertEqual(feedback["question_revision"], 1)
            self.assertEqual(feedback["correct_key"], "A")
            self.assertEqual(feedback["explanation"], "Explicação da revisão inicial.")

    def test_metacognition_events_before_answer_are_merged_into_attempt(self):
        with tempfile.TemporaryDirectory() as folder:
            db, _study, service = self.build_stack(Path(folder))
            uid = self.make_question(db)
            revision = service.question_for_mobile(uid)["question_revision"]
            _exchange, auth = self.pair(service)
            attempt_id = str(uuid.uuid4())
            confidence_event = {
                "event_id": str(uuid.uuid4()),
                "event_type": "confidence_reported",
                "attempt_id": attempt_id,
                "question_id": uid,
                "question_revision": revision,
                "occurred_at": "2026-08-17T12:00:00-03:00",
                "client": {"platform": "ios", "version": "0.1.0"},
                "payload": {"confidence": "high"},
            }
            answer = self.answer_event(uid, revision, attempt_id=attempt_id, selected=0)
            service.ingest_events(auth, [confidence_event, answer])
            with db.connect() as connection:
                row = connection.execute("SELECT confidence FROM telegram_attempts WHERE id=?", (attempt_id,)).fetchone()
            self.assertEqual(row["confidence"], "sabia")

    def test_pairing_is_single_use(self):
        with tempfile.TemporaryDirectory() as folder:
            _db, _study, service = self.build_stack(Path(folder))
            pairing = service.create_pairing(requested_by="unittest")
            service.exchange_pairing(pairing["pairing_token"], {"platform": "android"})
            with self.assertRaises(PermissionError):
                service.exchange_pairing(pairing["pairing_token"], {"platform": "android"})

    def test_physical_tenant_isolation_rejects_foreign_session(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            db_a, _study_a, service_a = self.build_stack(root / "a")
            db_b, _study_b, service_b = self.build_stack(root / "b")
            uid_a = self.make_question(db_a, subject="A")
            self.make_question(db_b, subject="B")
            revision_a = service_a.question_for_mobile(uid_a)["question_revision"]
            exchange_a, auth_a = self.pair(service_a, "device-A")

            with self.assertRaises(PermissionError):
                service_b.authenticate(exchange_a["access_token"])

            event = self.answer_event(uid_a, revision_a, attempt_id=str(uuid.uuid4()))
            service_a.ingest_events(auth_a, [event])
            with db_a.connect() as connection:
                count_a = int(connection.execute("SELECT COUNT(*) FROM qf_learning_events").fetchone()[0])
            with db_b.connect() as connection:
                count_b = int(connection.execute("SELECT COUNT(*) FROM qf_learning_events").fetchone()[0])
            self.assertEqual(count_a, 1)
            self.assertEqual(count_b, 0)
            self.assertNotEqual(service_a.identity()["tenant_id"], service_b.identity()["tenant_id"])


    def test_versioned_http_contract_requires_bearer_and_accepts_pairing_exchange(self):
        with tempfile.TemporaryDirectory() as folder:
            db, _study, service = self.build_stack(Path(folder))
            self.make_question(db)
            status, denied = service.http_request(
                method="GET", path="/api/v1/mobile/progress", headers={}, body={}, query={}
            )
            self.assertEqual(status, 401)
            self.assertFalse(denied["ok"])

            pairing = service.create_pairing()
            status, exchanged = service.http_request(
                method="POST",
                path="/api/v1/mobile/pairing/exchange",
                headers={},
                body={"pairing_token": pairing["pairing_token"], "device": {"platform": "android", "app_version": "0.1.0"}},
                query={},
            )
            self.assertEqual(status, 200)
            token = exchanged["access_token"]
            status, progress = service.http_request(
                method="GET",
                path="/api/v1/mobile/progress",
                headers={"Authorization": f"Bearer {token}"},
                body={},
                query={},
            )
            self.assertEqual(status, 200)
            self.assertTrue(progress["ok"])
            self.assertEqual(progress["data"]["contract"], "questflow.mobile.v1")

    def test_studio_exposes_mobile_foundation_panel_and_actions(self):
        root = Path(__file__).resolve().parents[1]
        html = (root / "web" / "index.html").read_text(encoding="utf-8")
        js = (root / "web" / "app.js").read_text(encoding="utf-8")
        self.assertIn("MOBILE 0.16.0", html)
        self.assertIn('id="createMobilePairing"', html)
        self.assertIn('id="mobilePairingQr"', html)
        self.assertIn("create_mobile_pairing", js)
        self.assertIn("get_mobile_foundation_status", js)


if __name__ == "__main__":
    unittest.main()
