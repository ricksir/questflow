from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from core.exam_projects import ExamProjectService
from core.mobile_foundation import MobileFoundationService
from core.storage import QuestFlowDatabase
from core.study import StudyRepository


class MobileDeviceLifecycle695Tests(unittest.TestCase):
    def build_service(self, root: Path):
        db = QuestFlowDatabase(root / "q.sqlite")
        study = StudyRepository(db)
        ExamProjectService(db)
        service = MobileFoundationService(db, study, control_plane_path=root / "control.sqlite")
        return db, service

    @staticmethod
    def pair(service: MobileFoundationService, device_id: str = "physical-device-001"):
        pairing = service.create_pairing(requested_by="test")
        return service.exchange_pairing(
            pairing["pairing_token"],
            {
                "device_id": device_id,
                "platform": "android",
                "name": "Galaxy Note9 de Richard",
                "app_version": "0.2.1",
            },
        )

    def test_disconnect_and_reconnect_reuses_same_device_record(self):
        with tempfile.TemporaryDirectory() as folder:
            db, service = self.build_service(Path(folder))
            first = self.pair(service)
            self.assertEqual(service.status()["active_devices"], 1)

            result = service.disconnect_device(first["device_id"])
            self.assertTrue(result["ok"])
            with self.assertRaises(PermissionError):
                service.authenticate(first["access_token"])

            disconnected = service.status()
            self.assertEqual(disconnected["active_devices"], 0)
            self.assertEqual(disconnected["disconnected_devices"], 1)
            self.assertEqual(disconnected["devices"][0]["status"], "disconnected")

            second = self.pair(service, first["device_id"])
            self.assertEqual(second["device_id"], first["device_id"])
            self.assertNotEqual(second["access_token"], first["access_token"])
            service.authenticate(second["access_token"])

            reconnected = service.status()
            self.assertEqual(reconnected["active_devices"], 1)
            self.assertEqual(reconnected["disconnected_devices"], 0)
            self.assertEqual(len(reconnected["devices"]), 1)
            with db.connect() as connection:
                total = int(connection.execute("SELECT COUNT(*) FROM qf_mobile_devices").fetchone()[0])
            self.assertEqual(total, 1)

    def test_remove_from_list_hides_but_does_not_delete_device_history(self):
        with tempfile.TemporaryDirectory() as folder:
            db, service = self.build_service(Path(folder))
            first = self.pair(service)
            service.disconnect_device(first["device_id"])

            forgotten = service.forget_device(first["device_id"])
            self.assertTrue(forgotten["ok"])
            self.assertEqual(service.status()["devices"], [])

            with db.connect() as connection:
                device = connection.execute(
                    "SELECT device_id,status,hidden_at FROM qf_mobile_devices WHERE device_id=?",
                    (first["device_id"],),
                ).fetchone()
                sessions = int(connection.execute(
                    "SELECT COUNT(*) FROM qf_mobile_sessions WHERE device_id=?",
                    (first["device_id"],),
                ).fetchone()[0])
            self.assertIsNotNone(device)
            self.assertTrue(device["hidden_at"])
            self.assertGreaterEqual(sessions, 1)

            # Reconnecting the same installation unhides/reactivates the same row.
            self.pair(service, first["device_id"])
            status = service.status()
            self.assertEqual(status["active_devices"], 1)
            self.assertEqual(len(status["devices"]), 1)
            self.assertEqual(status["devices"][0]["device_id"], first["device_id"])

    def test_active_device_must_be_disconnected_before_removal_from_list(self):
        with tempfile.TemporaryDirectory() as folder:
            _db, service = self.build_service(Path(folder))
            first = self.pair(service)
            with self.assertRaises(ValueError):
                service.forget_device(first["device_id"])

    def test_ui_uses_disconnect_language_and_persistent_installation_id(self):
        root = Path(__file__).resolve().parents[1]
        html = (root / "web" / "index.html").read_text(encoding="utf-8")
        js = (root / "web" / "app.js").read_text(encoding="utf-8")
        profile = (root / "mobile" / "app" / "(tabs)" / "profile.tsx").read_text(encoding="utf-8")
        session = (root / "mobile" / "src" / "lib" / "session.ts").read_text(encoding="utf-8")

        self.assertIn("Aparelhos conectados", js)
        self.assertIn("data-mobile-disconnect", js)
        self.assertIn("Remover da lista", js)
        self.assertNotIn(">Revogar<", js)
        self.assertNotIn("Revogado", js)
        self.assertIn("Desconectar deste QuestFlow", profile)
        self.assertNotIn("Desconectar e revogar", profile)
        self.assertIn("questflow.mobile.device-id.v1", session)
        self.assertIn("saveDeviceId(session.deviceId)", session)
        self.assertIn("Cloud Bridge integrado", html)


if __name__ == "__main__":
    unittest.main()
