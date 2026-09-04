from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from core.mobile_cloud_bridge import MobileCloudBridgeEngine
from core.exam_projects import ExamProjectService
from core.mobile_foundation import MobileFoundationService
from core.storage import QuestFlowDatabase
from core.study import StudyRepository
from mobile_cloud_gateway import GatewayStore

ROOT = Path(__file__).resolve().parents[1]


class MobileStudyBoundary6122Tests(unittest.TestCase):
    def build_mobile(self, root: Path) -> MobileFoundationService:
        db = QuestFlowDatabase(root / "questflow.sqlite")
        study = StudyRepository(db)
        ExamProjectService(db)
        return MobileFoundationService(db, study, control_plane_path=root / "mobile_control.sqlite")

    def test_mobile_ai_health_route_is_not_exposed(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            service = self.build_mobile(root)
            pairing = service.create_pairing(requested_by="test")
            exchange = service.exchange_pairing(
                pairing["pairing_token"],
                {"device_id": "dev-study-only", "platform": "android", "app_version": "0.11.0"},
            )
            headers = {"Authorization": f"Bearer {exchange['access_token']}"}
            status, payload = service.http_request(method="GET", path="/api/v1/mobile/ai-health", headers=headers)
            self.assertEqual(status, 404)
            self.assertFalse(payload["ok"])

    def test_mobile_client_contains_no_ai_health_screen_or_api(self):
        mobile = ROOT / "mobile"
        self.assertFalse((mobile / "app" / "ai-health.tsx").exists())
        targets = [
            mobile / "app" / "_layout.tsx",
            mobile / "app" / "(tabs)" / "profile.tsx",
            mobile / "src" / "lib" / "api.ts",
            mobile / "src" / "lib" / "types.ts",
        ]
        text = "\n".join(path.read_text(encoding="utf-8") for path in targets).lower()
        for forbidden in ("/ai-health", "saúde da ia", "aihealthprojection", "questflow.mobile.ai_health"):
            self.assertNotIn(forbidden, text)

    def test_profile_is_study_focused_and_excludes_telegram_and_technical_diagnostics(self):
        profile = (ROOT / "mobile" / "app" / "(tabs)" / "profile.tsx").read_text(encoding="utf-8")
        for expected in (
            "MEU ESTUDO",
            "Revisões hoje",
            "Questões sugeridas",
            "Respostas para salvar",
            "Lembretes de estudo",
        ):
            self.assertIn(expected, profile)
        for forbidden in (
            "Diagnóstico técnico",
            "Endpoint",
            "Cursor",
            "Rota ativa",
            "Versão do app",
            "Saúde da IA",
            "Verificar infraestrutura de IA",
            "Telegram",
            "Entrega de questões",
        ):
            self.assertNotIn(forbidden, profile)

    def test_mobile_contract_exposes_no_telegram_controls_or_channel_labels(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            service = self.build_mobile(root)
            pairing = service.create_pairing(requested_by="test")
            exchange = service.exchange_pairing(
                pairing["pairing_token"],
                {"device_id": "dev-no-telegram", "platform": "android", "app_version": "0.11.0"},
            )
            headers = {"Authorization": f"Bearer {exchange['access_token']}"}
            status, payload = service.http_request(method="GET", path="/api/v1/mobile/channels/telegram", headers=headers)
            self.assertEqual(status, 404)
            self.assertFalse(payload["ok"])
            bootstrap = service.bootstrap_projection()
            serialized = json.dumps(bootstrap, ensure_ascii=False).lower()
            self.assertNotIn("telegram", serialized)
            self.assertNotIn("channels", bootstrap)
            self.assertNotIn("channels", bootstrap["today"])
            self.assertNotIn("channels", bootstrap["progress"]["summary"])

    def test_mobile_source_tree_has_no_telegram_product_surface(self):
        mobile = ROOT / "mobile"
        targets = [*mobile.glob("app/**/*.tsx"), *mobile.glob("src/**/*.ts"), *mobile.glob("src/**/*.tsx")]
        text = "\n".join(path.read_text(encoding="utf-8") for path in targets if path.is_file()).lower()
        self.assertNotIn("telegram", text)
        studio = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        self.assertIn("Pausar questões no Telegram", studio)
        self.assertIn("Retomar questões no Telegram", studio)

    def test_cloud_bridge_publish_payload_has_only_study_projections(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            foundation = self.build_mobile(root)
            foundation.identity = lambda: {"account_id": "a", "tenant_id": "t", "learner_id": "l"}
            foundation.bootstrap_projection = lambda: {"contract": "questflow.mobile.v1", "today": {"contract": "questflow.mobile.v1"}, "progress": {"contract": "questflow.mobile.v1"}}
            foundation.today_projection = lambda: {"contract": "questflow.mobile.v1"}
            foundation.progress_projection = lambda: {"contract": "questflow.mobile.v1"}
            bridge = MobileCloudBridgeEngine(foundation, config={"mobile_cloud_bridge_enabled": False}, config_path=root / "config.json")
            bridge._active_sessions = lambda: []
            bridge._study_pack = lambda _count: []
            payload = bridge.build_publish_payload()
            projections = payload.get("projections") or {}
            self.assertEqual(set(projections), {"bootstrap", "today", "progress"})
            self.assertNotIn("ai_health", projections)

    def test_gateway_purges_legacy_ai_health_projection_on_next_publish(self):
        with tempfile.TemporaryDirectory() as td:
            store = GatewayStore(Path(td) / "gateway.sqlite")
            tenant_id = "tenant-study"
            with store.connect() as connection:
                connection.execute(
                    "INSERT INTO bridge_tenants(tenant_id,account_id,learner_id,last_publish_at,protocol) VALUES(?,?,?,?,?)",
                    (tenant_id, "account-study", "learner-study", "2026-08-19T16:00:00+00:00", "questflow.mobile.cloud.v1"),
                )
                connection.execute(
                    "INSERT INTO bridge_projections(tenant_id,kind,payload_json,published_at) VALUES(?,?,?,?)",
                    (tenant_id, "ai_health", json.dumps({"legacy": True}), "2026-08-19T16:00:00+00:00"),
                )
            result = store.publish({
                "protocol": "questflow.mobile.cloud.v1",
                "published_at": "2026-08-19T17:00:00+00:00",
                "identity": {"tenant_id": tenant_id, "account_id": "account-study", "learner_id": "learner-study"},
                "sessions": [],
                "projections": {"today": {"contract": "questflow.mobile.v1"}},
                "study_pack": [],
            })
            self.assertTrue(result["ok"])
            with self.assertRaises(ValueError):
                store.projection(tenant_id, "ai_health")

    def test_release_and_mobile_versions(self):
        self.assertEqual((ROOT / "VERSION.txt").read_text(encoding="utf-8").strip(), "6.23.2")
        self.assertIn('version = "6.23.2"', (ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        self.assertEqual(json.loads((ROOT / "mobile" / "app.json").read_text(encoding="utf-8"))["expo"]["version"], "0.15.6")
        self.assertEqual(json.loads((ROOT / "mobile" / "package.json").read_text(encoding="utf-8"))["version"], "0.15.6")
        config = (ROOT / "mobile" / "src" / "lib" / "config.ts").read_text(encoding="utf-8")
        self.assertIn("MOBILE_APP_VERSION = '0.15.6'", config)


if __name__ == "__main__":
    unittest.main()
