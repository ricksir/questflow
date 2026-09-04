from __future__ import annotations

import tempfile
import unittest
import uuid
from pathlib import Path

from core.exam_projects import ExamProjectService
from core.mobile_foundation import MobileFoundationService
from core.storage import QuestFlowDatabase
from core.study import StudyRepository


class MobileAlpha691Tests(unittest.TestCase):
    def build_stack(self, root: Path):
        root.mkdir(parents=True, exist_ok=True)
        db = QuestFlowDatabase(root / "questflow.sqlite")
        study = StudyRepository(db)
        ExamProjectService(db)
        service = MobileFoundationService(db, study, control_plane_path=root / "control.sqlite")
        return db, study, service

    def make_question(self, db: QuestFlowDatabase) -> str:
        uid = db.create_manual_question()
        question = db.get_question(uid)
        assert question is not None
        question["materia"] = "Direito Administrativo"
        question["enunciado"] = "Questão para o Alpha 0.1"
        question["alternativas"] = [
            {"chave": "A", "texto": "Correta"},
            {"chave": "B", "texto": "Incorreta"},
        ]
        question["gabarito"] = "A"
        question["telegram"] = {"modo": "quiz", "indice_correto": 0, "opcoes": ["Correta", "Incorreta"]}
        question.setdefault("revisao", {})["status"] = "aprovado"
        db.update_question(uid, question, change_source="test_mobile_691")
        return uid

    def pair(self, service: MobileFoundationService):
        pairing = service.create_pairing(requested_by="691")
        exchange = service.exchange_pairing(pairing["pairing_token"], {"platform": "android", "app_version": "0.1.0"})
        return service.authenticate(exchange["access_token"])

    def test_health_is_public_but_study_projection_still_requires_bearer(self):
        with tempfile.TemporaryDirectory() as folder:
            _db, _study, service = self.build_stack(Path(folder))
            status, health = service.http_request(method="GET", path="/api/v1/mobile/health", headers={}, body={}, query={})
            self.assertEqual(status, 200)
            self.assertTrue(health["ok"])
            self.assertEqual(health["api"], "questflow.mobile.v1")
            status, progress = service.http_request(method="GET", path="/api/v1/mobile/progress", headers={}, body={}, query={})
            self.assertEqual(status, 401)
            self.assertFalse(progress["ok"])

    def test_failed_event_can_retry_only_with_identical_immutable_content(self):
        with tempfile.TemporaryDirectory() as folder:
            db, study, service = self.build_stack(Path(folder))
            uid = self.make_question(db)
            revision = service.question_for_mobile(uid)["question_revision"]
            auth = self.pair(service)
            event_id = str(uuid.uuid4())
            attempt_id = str(uuid.uuid4())
            event = {
                "event_id": event_id,
                "event_type": "answer_submitted",
                "attempt_id": attempt_id,
                "session_id": "session-691",
                "question_id": uid,
                "question_revision": revision,
                "occurred_at": "2026-08-17T13:00:00-03:00",
                "client": {"platform": "android", "version": "0.1.0"},
                "payload": {"selected_index": 0, "active_response_seconds": 25, "wall_response_seconds": 25, "timing_source": "client_active_timer_v1"},
            }

            original = study.record_local_practice_attempt
            calls = {"count": 0}

            def fail_once(*args, **kwargs):
                calls["count"] += 1
                if calls["count"] == 1:
                    raise RuntimeError("falha transitória simulada")
                return original(*args, **kwargs)

            study.record_local_practice_attempt = fail_once  # type: ignore[method-assign]
            first = service.ingest_events(auth, [event])
            self.assertFalse(first["ok"])
            self.assertEqual(first["failed"][0]["event_id"], event_id)

            retry = service.ingest_events(auth, [event])
            self.assertTrue(retry["ok"])
            self.assertEqual(retry["accepted"], [event_id])
            with db.connect() as connection:
                self.assertEqual(int(connection.execute("SELECT COUNT(*) FROM telegram_attempts WHERE id=?", (attempt_id,)).fetchone()[0]), 1)

            duplicate = service.ingest_events(auth, [event])
            self.assertEqual(duplicate["duplicates"], [event_id])

    def test_mobile_alpha_sources_and_pairing_transport_are_packaged(self):
        root = Path(__file__).resolve().parents[1]
        required = [
            root / "mobile" / "package.json",
            root / "mobile" / "app" / "pair.tsx",
            root / "mobile" / "app" / "(tabs)" / "today.tsx",
            root / "mobile" / "app" / "(tabs)" / "questions.tsx",
            root / "mobile" / "app" / "(tabs)" / "progress.tsx",
            root / "mobile" / "src" / "lib" / "timing.ts",
            root / "mobile" / "src" / "lib" / "db.ts",
            root / "mobile" / "src" / "lib" / "sync.ts",
        ]
        for path in required:
            self.assertTrue(path.exists(), path)
        pairing_code = (root / "web_api.py").read_text(encoding="utf-8")
        self.assertIn("api_base_url", pairing_code)
        self.assertIn("&server=", pairing_code)
        app_json = (root / "mobile" / "app.json").read_text(encoding="utf-8")
        self.assertIn("NSAllowsLocalNetworking", app_json)
        self.assertIn('"recordAudioAndroid": false', app_json)

    def test_timer_source_explicitly_stops_after_inactivity(self):
        root = Path(__file__).resolve().parents[1]
        timing = (root / "mobile" / "src" / "lib" / "timing.ts").read_text(encoding="utf-8")
        config = (root / "mobile" / "src" / "lib" / "config.ts").read_text(encoding="utf-8")
        self.assertIn("idleGap <= ACTIVE_IDLE_CUTOFF_MS", timing)
        self.assertIn("export const ACTIVE_IDLE_CUTOFF_MS = 60_000", config)
        self.assertIn("max_idle_gap_seconds", timing)
        self.assertIn("interaction_count", timing)


if __name__ == "__main__":
    unittest.main()
