from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app_shared import TAXONOMY_PATH
from core.storage import QuestFlowDatabase
from core.study import StudyRepository
from web_api import QuestFlowWebApi


BASE = Path(__file__).resolve().parents[1]


class BrandingAndReset531Tests(unittest.TestCase):
    def _database_with_question(self, root: Path) -> tuple[QuestFlowDatabase, str]:
        database = QuestFlowDatabase(root / "questions.sqlite")
        uid = database.create_manual_question(None)
        question = database.get_question(uid)
        assert question is not None
        question.update(
            {
                "codigo_origem": "Q-RESET-531",
                "materia": "AUDITORIA",
                "aula_planilha": "Aula 01",
                "assunto": "Papéis de trabalho",
                "enunciado": "Questão de teste do reinício.",
                "alternativas": [
                    {"chave": "A", "texto": "Correta"},
                    {"chave": "B", "texto": "Incorreta"},
                ],
                "gabarito": "A",
                "revisao": {"status": "aprovado", "alertas": []},
            }
        )
        database.update_question(uid, question)
        return database, uid

    def test_brand_assets_are_integrated_without_using_full_hd_everywhere(self) -> None:
        html = (BASE / "web" / "index.html").read_text(encoding="utf-8")
        css = (BASE / "web" / "styles.css").read_text(encoding="utf-8")
        js = (BASE / "web" / "app.js").read_text(encoding="utf-8")
        assets = BASE / "web" / "assets"

        self.assertIn("questflow_logo_light_128.png", html)
        self.assertIn("questflow_logo_dark_128.png", html)
        self.assertIn("questflow_exam_light.svg", html)
        self.assertIn("questflow_exam_dark.svg", html)
        self.assertIn("brand-image", css)
        self.assertIn("theme-art--dark", css)
        self.assertIn("identityPicture", js)
        for name in (
            "questflow_exam_light.svg",
            "questflow_exam_dark.svg",
            "questflow_exam_light_256.png",
            "questflow_exam_dark_256.png",
            "questflow_logo_light_256.png",
            "questflow_logo_dark_256.png",
            "questflow_logo_light_128.png",
            "questflow_logo_dark_128.png",
            "questflow_logo_light_64.png",
            "questflow_logo_dark_64.png",
            "questflow_logo_light_32.png",
            "questflow_logo_dark_32.png",
        ):
            self.assertTrue((assets / name).is_file(), name)

    def test_web_ui_has_protected_reset_button_and_typed_confirmation(self) -> None:
        html = (BASE / "web" / "index.html").read_text(encoding="utf-8")
        js = (BASE / "web" / "app.js").read_text(encoding="utf-8")
        self.assertIn('id="resetStudyCycle"', html)
        self.assertIn("Reiniciar estudos do zero", html)
        backend = (BASE / "web_api.py").read_text(encoding="utf-8")
        self.assertIn("QuestFlow-pre-reset", backend)
        self.assertIn("Digite <strong>REINICIAR</strong>", js)
        self.assertIn("bridge.call('flow_action', 'reset')", js)

    def test_reset_clears_adaptive_learning_and_gamification_but_keeps_questions_and_corrections(self) -> None:
        with tempfile.TemporaryDirectory(prefix="questflow-531-reset-") as temp:
            root = Path(temp)
            database, uid = self._database_with_question(root)
            study = StudyRepository(database)
            study.sync_questions()
            request_id = study.create_review_request(uid, user_id="1")
            self.assertTrue(request_id)

            with database.connect() as connection:
                connection.execute(
                    """
                    UPDATE study_state
                    SET sent_count=9, correct_count=7, wrong_count=2, streak=4,
                        due_at='2099-01-01T00:00:00+00:00', memory_stability=12.0,
                        adaptive_prediction=0.93, adaptive_priority=8.0,
                        fsrs_card_json='{}', fsrs_due_at='2099-01-01T00:00:00+00:00',
                        fsrs_rating=4, fsrs_version='test'
                    WHERE question_uid=?
                    """,
                    (uid,),
                )
                connection.execute(
                    "INSERT OR REPLACE INTO adaptive_model_state(id, model_json, updated_at) VALUES(1, ?, 'now')",
                    (json.dumps({"samples": 25}),),
                )
                connection.execute(
                    """
                    INSERT OR REPLACE INTO topic_learning_state(
                        subject, topic, correct_count, wrong_count, exposure_count,
                        last_seen_at, last_score, updated_at
                    ) VALUES('AUDITORIA','Papéis',7,2,9,'now',0.8,'now')
                    """
                )
                connection.execute(
                    "INSERT INTO xp_events(id, question_uid, xp, reason, created_at) VALUES('xp-reset', ?, 90, 'teste', 'now')",
                    (uid,),
                )
                connection.execute(
                    "UPDATE learner_profile SET total_xp=90, level=2, best_streak=4, updated_at='now' WHERE id=1"
                )
                connection.execute(
                    "INSERT OR REPLACE INTO flow_runtime(key, value, updated_at) VALUES('telegram_update_offset','123','now')"
                )
                connection.execute(
                    "INSERT OR REPLACE INTO flow_runtime(key, value, updated_at) VALUES('temporary_cycle_marker','x','now')"
                )

            result = study.reset_progress()
            self.assertEqual(result["active_corrections_preserved"], 1)

            with database.connect() as connection:
                state = connection.execute("SELECT * FROM study_state WHERE question_uid=?", (uid,)).fetchone()
                self.assertEqual(state["sent_count"], 0)
                self.assertEqual(state["correct_count"], 0)
                self.assertEqual(state["wrong_count"], 0)
                self.assertEqual(state["streak"], 0)
                self.assertIsNone(state["due_at"])
                self.assertAlmostEqual(state["memory_stability"], 1.0)
                self.assertAlmostEqual(state["adaptive_prediction"], 0.5)
                self.assertEqual(state["adaptive_priority"], 0.0)
                self.assertIsNone(state["fsrs_card_json"])
                self.assertEqual(state["suspended"], 1)
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM xp_events").fetchone()[0], 0)
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM topic_learning_state").fetchone()[0], 0)
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM adaptive_model_state").fetchone()[0], 0)
                profile = connection.execute("SELECT total_xp, level, best_streak FROM learner_profile WHERE id=1").fetchone()
                self.assertEqual(tuple(profile), (0, 1, 0))
                self.assertEqual(connection.execute("SELECT value FROM flow_runtime WHERE key='telegram_update_offset'").fetchone()[0], "123")
                self.assertIsNone(connection.execute("SELECT value FROM flow_runtime WHERE key='temporary_cycle_marker'").fetchone())
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM questions").fetchone()[0], 1)
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM telegram_review_requests").fetchone()[0], 1)

    def test_web_reset_creates_automatic_sqlite_backup(self) -> None:
        with tempfile.TemporaryDirectory(prefix="questflow-531-web-reset-") as temp:
            root = Path(temp)
            database, _uid = self._database_with_question(root)
            api = QuestFlowWebApi(
                database.path,
                config={"flow_target_retention": 0.88},
                config_path=root / "config.json",
                taxonomy_path=TAXONOMY_PATH,
            )
            try:
                api.bootstrap()
                result = api.flow_action("reset")
                self.assertTrue(result["ok"])
                backup = Path(result["backup_path"])
                self.assertTrue(backup.is_file())
                self.assertEqual(backup.parent.name, "backups")
                self.assertEqual(api.list_questions()["total"], 1)
            finally:
                api.shutdown()


if __name__ == "__main__":
    unittest.main()
