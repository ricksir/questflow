from __future__ import annotations

import tempfile
import unittest
import uuid
from pathlib import Path

from core.exam_projects import ExamProjectService
from core.mobile_foundation import MobileFoundationService
from core.storage import QuestFlowDatabase
from core.study import StudyRepository


class MobileCoach694Tests(unittest.TestCase):
    def make_question(self, db: QuestFlowDatabase, subject: str = "Auditoria") -> str:
        uid = db.create_manual_question()
        question = db.get_question(uid)
        assert question is not None
        question["materia"] = subject
        question["assunto"] = "Evidência de auditoria"
        question["aula"] = "Aula 01"
        question["enunciado"] = "Questão de teste do Mobile Coach."
        question["alternativas"] = [{"chave": "A", "texto": "Correta"}, {"chave": "B", "texto": "Errada"}]
        question["gabarito"] = "A"
        question["telegram"] = {"modo": "quiz", "indice_correto": 0, "opcoes": ["Correta", "Errada"]}
        question.setdefault("revisao", {})["status"] = "aprovado"
        db.update_question(uid, question, change_source="test_mobile_694")
        return uid

    def pair_token(self, service: MobileFoundationService) -> str:
        pairing = service.create_pairing(requested_by="test")
        exchange = service.exchange_pairing(
            pairing["pairing_token"],
            {"device_id": str(uuid.uuid4()), "platform": "android", "app_version": "0.2.1"},
        )
        return exchange["access_token"]

    def test_progress_aggregates_study_history_without_exposing_source_channel(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            db = QuestFlowDatabase(root / "q.sqlite")
            study = StudyRepository(db)
            ExamProjectService(db)
            service = MobileFoundationService(db, study, control_plane_path=root / "control.sqlite")
            uid = self.make_question(db)
            study.sync_questions()
            study.record_local_practice_attempt(
                uid,
                0,
                response_seconds=38,
                timing_meta={"quality": "active_filtered", "source": "client_active_timer_v1", "wall_seconds": 900, "idle_seconds": 862},
                source="mobile_android",
            )
            study.record_local_practice_attempt(uid, 1, source="telegram")

            progress = service.progress_projection()
            self.assertEqual(progress["summary"]["attempts"], 2)
            self.assertNotIn("channels", progress["summary"])
            self.assertEqual(progress["summary"]["timing_samples"], 1)
            self.assertTrue(progress["summary"]["coach_text"])
            self.assertTrue(progress["recent_activity"])
            self.assertTrue(all("channel" not in item for item in progress["recent_activity"]))
            self.assertIn("insight", progress["subjects"][0])
            self.assertEqual(progress["subjects"][0]["insight"]["recent_sample"], 2)

            today = service.today_projection()
            self.assertIn("coach", today)
            self.assertTrue(today["coach"]["headline"])
            self.assertIn("recent_activity", today)

    def test_mobile_api_does_not_expose_telegram_channel_controls(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            db = QuestFlowDatabase(root / "q.sqlite")
            study = StudyRepository(db)
            ExamProjectService(db)
            service = MobileFoundationService(db, study, control_plane_path=root / "control.sqlite")
            token = self.pair_token(service)
            headers = {"Authorization": f"Bearer {token}"}
            code, response = service.http_request(
                method="PUT",
                path="/api/v1/mobile/channels/telegram",
                headers=headers,
                body={"questions_paused": True},
                query={},
            )
            self.assertEqual(code, 404)
            self.assertFalse(response["ok"])

    def test_mobile_02_sources_expose_action_oriented_ui(self):
        root = Path(__file__).resolve().parents[1]
        today = (root / "mobile" / "app" / "(tabs)" / "today.tsx").read_text(encoding="utf-8")
        progress = (root / "mobile" / "app" / "(tabs)" / "progress.tsx").read_text(encoding="utf-8")
        config = (root / "mobile" / "src" / "lib" / "config.ts").read_text(encoding="utf-8")
        self.assertIn("Seu desempenho", today)
        self.assertIn("Acerto por matéria", today)
        self.assertNotIn("Pausar questões no Telegram", today)
        self.assertIn("Ver progresso completo", today)
        self.assertNotIn("Últimas respostas", today)
        self.assertIn("Prioridade por matéria", progress)
        self.assertIn("Por que esta prioridade?", progress)
        self.assertIn("0.16.0", config)


if __name__ == "__main__":
    unittest.main()
