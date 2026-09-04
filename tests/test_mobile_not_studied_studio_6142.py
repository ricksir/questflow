from __future__ import annotations

import json
import tempfile
import unittest
import uuid
from pathlib import Path

from core.mobile_foundation import MobileFoundationService
from core.storage import QuestFlowDatabase
from core.study import StudyRepository
from web_api import QuestFlowWebApi

ROOT = Path(__file__).resolve().parents[1]


class MobileNotStudiedStudio6142Tests(unittest.TestCase):
    def build_stack(self, root: Path):
        db = QuestFlowDatabase(root / "questflow.sqlite")
        study = StudyRepository(db)
        mobile = MobileFoundationService(db, study, control_plane_path=root / "mobile_control.sqlite")
        return db, study, mobile

    def make_question(self, db: QuestFlowDatabase) -> str:
        uid = db.create_manual_question()
        q = db.get_question(uid)
        self.assertIsNotNone(q)
        q["codigo_origem"] = "Q-NS-STUDIO"
        q["materia"] = "Direito Tributário"
        q["assunto"] = "Competência tributária"
        q["aula"] = "Aula 03"
        q["enunciado"] = "Questão usada para testar a triagem de assunto ainda não estudado."
        q["alternativas"] = [{"chave": "A", "texto": "Certo"}, {"chave": "B", "texto": "Errado"}]
        q["gabarito"] = "A"
        q.setdefault("revisao", {})["status"] = "aprovado"
        db.update_question(uid, q, change_source="test_6142")
        return uid

    def pair(self, mobile: MobileFoundationService):
        pairing = mobile.create_pairing(requested_by="unittest")
        exchange = mobile.exchange_pairing(
            pairing["pairing_token"],
            {"device_id": str(uuid.uuid4()), "platform": "android", "name": "Teste", "app_version": "0.11.0"},
        )
        return mobile.authenticate(exchange["access_token"])

    def not_studied_event(self, uid: str, revision: int):
        return {
            "event_id": str(uuid.uuid4()),
            "schema_version": 1,
            "event_type": "topic_not_studied_reported",
            "session_id": "session-6142",
            "attempt_id": str(uuid.uuid4()),
            "question_id": uid,
            "question_revision": revision,
            "occurred_at": "2026-08-20T01:30:00-03:00",
            "client": {"platform": "android", "version": "0.11.0"},
            "payload": {"reason": "not_studied_yet", "exclude_from_performance": True},
        }

    def test_not_studied_is_projected_to_studio_corrections_without_attempt(self):
        with tempfile.TemporaryDirectory() as folder:
            db, study, mobile = self.build_stack(Path(folder))
            uid = self.make_question(db)
            study.sync_questions()
            revision = mobile.question_for_mobile(uid)["question_revision"]
            auth = self.pair(mobile)

            result = mobile.ingest_events(auth, [self.not_studied_event(uid, revision)])
            self.assertTrue(result["ok"])
            self.assertEqual(mobile.pending_study_backlog_count(), 1)
            items = mobile.list_study_backlog_for_studio()
            self.assertEqual(len(items), 1)
            item = items[0]
            self.assertEqual(item["item_type"], "not_studied")
            self.assertEqual(item["question_uid"], uid)
            self.assertEqual(item["question_code"], "Q-NS-STUDIO")
            self.assertEqual(item["materia"], "Direito Tributário")
            self.assertEqual(item["assunto"], "Competência tributária")
            self.assertIn("Questão usada", item["statement"])
            with db.connect() as connection:
                self.assertEqual(int(connection.execute("SELECT COUNT(*) FROM telegram_attempts").fetchone()[0]), 0)

    def test_web_api_unifies_editorial_and_not_studied_and_action_releases_topic(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            db, study, mobile = self.build_stack(root)
            uid = self.make_question(db)
            study.sync_questions()
            auth = self.pair(mobile)
            revision = mobile.question_for_mobile(uid)["question_revision"]
            mobile.ingest_events(auth, [self.not_studied_event(uid, revision)])
            study.create_review_request(uid, user_id="editorial-test", username="Teste", source="mobile_preanswer")

            api = QuestFlowWebApi(database_path=root / "questflow.sqlite", config_path=root / "config.json", taxonomy_path=root / "missing.json")
            api._ensure_core = lambda *args, **kwargs: None  # type: ignore[method-assign]
            api.study = study
            api.mobile_foundation = mobile
            listed = api.list_corrections("ativas")
            self.assertEqual(listed["summary"]["editorial"], 1)
            self.assertEqual(listed["summary"]["not_studied"], 1)
            self.assertEqual(listed["summary"]["total"], 2)
            study_item = next(item for item in listed["items"] if item["item_type"] == "not_studied")
            action = api.correction_action(study_item["id"], "mark_studied")
            self.assertTrue(action["ok"])
            self.assertEqual(mobile.pending_study_backlog_count(), 0)

    def test_mobile_statusbar_and_studio_window_are_present(self):
        config = json.loads((ROOT / "mobile" / "app.json").read_text(encoding="utf-8"))
        self.assertEqual(config["expo"]["version"], "0.15.6")
        self.assertEqual(config["expo"]["androidStatusBar"]["backgroundColor"], "#080D16")
        self.assertFalse(config["expo"]["androidStatusBar"]["translucent"])
        layout = (ROOT / "mobile" / "app" / "_layout.tsx").read_text(encoding="utf-8")
        self.assertIn('backgroundColor={palette.bg}', layout)
        self.assertIn('translucent={false}', layout)
        web = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        self.assertIn("function openNotStudiedCorrection", web)
        self.assertIn("Assunto ainda não estudado", web)
        self.assertIn("Marcar como estudado", web)


if __name__ == "__main__":
    unittest.main()
