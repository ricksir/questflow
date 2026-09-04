from __future__ import annotations

import json
import tempfile
import threading
import unittest
import urllib.request
import uuid
from pathlib import Path

from core.exam_projects import ExamProjectService
from core.mobile_cloud_bridge import MobileCloudBridgeEngine
from core.mobile_foundation import MobileFoundationService
from core.storage import QuestFlowDatabase
from core.study import StudyRepository
from mobile_cloud_gateway import GatewayServer, GatewayStore, sha256


class MobileCloudBridge696Tests(unittest.TestCase):
    def build_stack(self, root: Path):
        db = QuestFlowDatabase(root / "questflow.sqlite")
        study = StudyRepository(db)
        ExamProjectService(db)
        service = MobileFoundationService(db, study, control_plane_path=root / "mobile-control.sqlite")
        return db, service

    def make_question(self, db: QuestFlowDatabase) -> str:
        uid = db.create_manual_question()
        question = db.get_question(uid)
        self.assertIsNotNone(question)
        question["materia"] = "Direito Administrativo"
        question["assunto"] = "Cloud Bridge"
        question["enunciado"] = "Qual alternativa valida o pacote de estudo seguro?"
        question["alternativas"] = [
            {"chave": "A", "texto": "A alternativa correta."},
            {"chave": "B", "texto": "A alternativa incorreta."},
        ]
        question["gabarito"] = "A"
        question["explicacao"] = "O gabarito privado fica no Gateway e não no payload público da questão."
        question["telegram"] = {
            "modo": "quiz",
            "pergunta": question["enunciado"],
            "opcoes": ["A alternativa correta.", "A alternativa incorreta."],
            "indice_correto": 0,
        }
        question.setdefault("revisao", {})["status"] = "aprovado"
        db.update_question(uid, question, change_source="test_mobile_cloud_696")
        # StudyRepository normally creates this state during its reconcile cycle.
        # The test creates the question after repository initialization, so ensure it here.
        with db.connect() as connection:
            connection.execute("INSERT OR IGNORE INTO study_state(question_uid) VALUES(?)", (uid,))
        return uid

    @staticmethod
    def http_json(url: str, *, token: str = "", method: str = "GET", body: dict | None = None) -> dict:
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        data = None if body is None else json.dumps(body).encode("utf-8")
        request = urllib.request.Request(url, data=data, method=method, headers=headers)
        with urllib.request.urlopen(request, timeout=5) as response:
            return json.loads(response.read().decode("utf-8"))

    def test_gateway_end_to_end_publish_study_offline_and_drain_to_studio(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            db, service = self.build_stack(root)
            uid = self.make_question(db)
            revision = service.question_for_mobile(uid)["question_revision"]

            pairing = service.create_pairing(requested_by="cloud-test")
            exchange = service.exchange_pairing(pairing["pairing_token"], {
                "device_id": "device-cloud-001",
                "platform": "android",
                "name": "Galaxy Teste",
                "app_version": "0.3.0",
            })
            token = exchange["access_token"]

            key = "cloud-bridge-test-key-696-strong"
            store = GatewayStore(root / "gateway.sqlite")
            server = GatewayServer(("127.0.0.1", 0), store, key)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = f"http://127.0.0.1:{server.server_address[1]}"
            try:
                config = {
                    "mobile_cloud_bridge_enabled": True,
                    "mobile_cloud_bridge_url": base,
                    "mobile_cloud_bridge_interval_seconds": 30,
                    "mobile_cloud_bridge_pack_size": 8,
                }
                bridge = MobileCloudBridgeEngine(
                    service,
                    config=config,
                    config_path=root / "config.json",
                    bridge_key_override=key,
                )
                service.cloud_bridge_provider = bridge.client_projection

                published = bridge.publish()
                self.assertTrue(published["ok"], published)
                self.assertGreaterEqual(published["published_questions"], 1)

                bootstrap = self.http_json(f"{base}/api/v1/mobile/bootstrap", token=token)["data"]
                self.assertEqual(bootstrap["sync"]["transport"], "cloud_bridge")
                self.assertTrue(bootstrap["sync"]["cloud_bridge"]["enabled"])
                self.assertIn("last_studio_publish_at", bootstrap["sync"])

                batch = self.http_json(
                    f"{base}/api/v1/mobile/question-batches",
                    token=token,
                    method="POST",
                    body={"count": 8},
                )["data"]["questions"]
                self.assertTrue(batch)
                self.assertEqual(batch[0]["question_id"], uid)
                self.assertNotIn("gabarito", batch[0])
                self.assertNotIn("explanation", batch[0])

                attempt_id = str(uuid.uuid4())
                event_id = str(uuid.uuid4())
                event = {
                    "event_id": event_id,
                    "schema_version": 1,
                    "event_type": "answer_submitted",
                    "device_id": "device-cloud-001",
                    "session_id": str(uuid.uuid4()),
                    "attempt_id": attempt_id,
                    "question_id": uid,
                    "question_revision": revision,
                    "occurred_at": "2026-08-18T21:00:00-03:00",
                    "sequence_no": 1,
                    "client": {"platform": "android", "version": "0.3.0"},
                    "payload": {
                        "selected_index": 0,
                        "confidence": "high",
                        "active_response_seconds": 31,
                        "wall_response_seconds": 300,
                        "idle_seconds": 269,
                        "timing_source": "client_active_timer_v1",
                    },
                }
                sync = self.http_json(
                    f"{base}/api/v1/mobile/sync",
                    token=token,
                    method="POST",
                    body={"cursor": 0, "events": [event]},
                )
                self.assertEqual(sync["push"]["accepted"], [event_id])

                feedback = self.http_json(f"{base}/api/v1/mobile/attempts/{attempt_id}/feedback", token=token)["data"]
                self.assertTrue(feedback["is_correct"])
                self.assertTrue(feedback["provisional"])
                self.assertEqual(feedback["source"], "cloud_bridge_study_pack")
                self.assertEqual(feedback["timing"]["quality"], "pending_studio_validation")

                # The cloud only queues the event; the Studio remains authoritative.
                with db.connect() as connection:
                    before = int(connection.execute("SELECT COUNT(*) FROM telegram_attempts WHERE id=?", (attempt_id,)).fetchone()[0])
                self.assertEqual(before, 0)

                drained = bridge.drain()
                self.assertTrue(drained["ok"], drained)
                self.assertIn(event_id, drained["acked"])
                with db.connect() as connection:
                    row = connection.execute(
                        "SELECT response_seconds,timing_quality FROM telegram_attempts WHERE id=?",
                        (attempt_id,),
                    ).fetchone()
                self.assertIsNotNone(row)
                self.assertAlmostEqual(float(row["response_seconds"]), 31.0)
                self.assertIn(row["timing_quality"], {"valid", "active_filtered"})

                status = store.status(service.identity()["tenant_id"])
                self.assertEqual(status["pending_events"], 0)
                with store.connect() as connection:
                    cloud_session = connection.execute("SELECT token_hash FROM bridge_sessions WHERE device_id=?", ("device-cloud-001",)).fetchone()
                self.assertEqual(cloud_session["token_hash"], sha256(token))
                self.assertNotEqual(cloud_session["token_hash"], token)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=3)

    def test_cloud_disconnect_is_delivered_to_studio_without_deleting_history(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            db, service = self.build_stack(root)
            uid = self.make_question(db)
            revision = service.question_for_mobile(uid)["question_revision"]
            pairing = service.create_pairing(requested_by="cloud-test")
            exchange = service.exchange_pairing(pairing["pairing_token"], {
                "device_id": "device-disconnect-001", "platform": "android", "name": "Teste", "app_version": "0.3.0"
            })
            token = exchange["access_token"]
            key = "cloud-bridge-test-key-696-disconnect"
            store = GatewayStore(root / "gateway.sqlite")
            server = GatewayServer(("127.0.0.1", 0), store, key)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = f"http://127.0.0.1:{server.server_address[1]}"
            try:
                config = {"mobile_cloud_bridge_enabled": True, "mobile_cloud_bridge_url": base, "mobile_cloud_bridge_pack_size": 8}
                bridge = MobileCloudBridgeEngine(service, config=config, config_path=root / "config.json", bridge_key_override=key)
                self.assertTrue(bridge.publish()["ok"])
                pending_attempt = str(uuid.uuid4())
                pending_event = {
                    "event_id": str(uuid.uuid4()),
                    "schema_version": 1,
                    "event_type": "answer_submitted",
                    "device_id": "device-disconnect-001",
                    "attempt_id": pending_attempt,
                    "question_id": uid,
                    "question_revision": revision,
                    "occurred_at": "2026-08-18T21:10:00-03:00",
                    "sequence_no": 1,
                    "client": {"platform": "android", "version": "0.3.0"},
                    "payload": {"selected_index": 0, "active_response_seconds": 20, "wall_response_seconds": 20, "idle_seconds": 0, "timing_source": "client_active_timer_v1"},
                }
                queued = self.http_json(f"{base}/api/v1/mobile/sync", token=token, method="POST", body={"cursor": 0, "events": [pending_event]})
                self.assertEqual(queued["push"]["accepted"], [pending_event["event_id"]])
                disconnected = self.http_json(
                    f"{base}/api/v1/mobile/devices/device-disconnect-001",
                    token=token,
                    method="DELETE",
                )
                self.assertTrue(disconnected["ok"])
                result = bridge.drain()
                self.assertTrue(result["ok"], result)
                self.assertEqual(service.status()["active_devices"], 0)
                self.assertEqual(service.status()["disconnected_devices"], 1)
                with db.connect() as connection:
                    preserved = connection.execute("SELECT id FROM telegram_attempts WHERE id=?", (pending_attempt,)).fetchone()
                self.assertIsNotNone(preserved, "A resposta enviada antes da desconexão precisa sobreviver ao drain.")
                with self.assertRaises(PermissionError):
                    service.authenticate(token)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=3)

    def test_release_surfaces_cloud_bridge_without_exposing_internal_database(self):
        root = Path(__file__).resolve().parents[1]
        html = (root / "web" / "index.html").read_text(encoding="utf-8")
        js = (root / "web" / "app.js").read_text(encoding="utf-8")
        profile = (root / "mobile" / "app" / "(tabs)" / "profile.tsx").read_text(encoding="utf-8")
        context = (root / "mobile" / "src" / "context" / "QuestFlowContext.tsx").read_text(encoding="utf-8")
        gateway = (root / "mobile_cloud_gateway.py").read_text(encoding="utf-8")

        self.assertIn("Mobile Cloud Bridge", html)
        self.assertIn("save_mobile_cloud_bridge_settings", js)
        self.assertNotIn("Cloud Bridge", profile)
        self.assertIn("cloudBaseUrl", context)
        self.assertIn("data?.sync?.cloud_bridge?.base_url", context)
        self.assertIn("result.reachable", context)
        self.assertIn("QuestFlow Mobile Cloud Gateway 0.5", gateway)
        self.assertNotIn("TURSO_AUTH_TOKEN", gateway)


if __name__ == "__main__":
    unittest.main()
