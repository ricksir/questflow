from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import app_shared
from core.cloud_sync import SYNC_TABLE_MAP
from core.engines import EngineRegistry
from core.question_services import QuestionCommandService, QuestionQueryService
from core.schema_migrations import migration_history
from core.storage import QuestFlowDatabase
from core.study import StudyRepository
from web_server import ALLOWED_API_METHODS

BASE = Path(__file__).resolve().parents[1]


class TutorScaffolding670Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="qf-670-")
        self.db = QuestFlowDatabase(Path(self.tmp.name) / "q.sqlite")
        self.study = StudyRepository(self.db)
        self.queries = QuestionQueryService(self.db)
        self.commands = QuestionCommandService(self.db)
        self.engines = EngineRegistry.build(database=self.db, queries=self.queries, commands=self.commands, study=self.study)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def make_question(self, code: str = "Q670") -> str:
        uid = self.db.create_manual_question(None)
        q = self.db.get_question(uid); assert q
        q.update({
            "codigo_origem": code,
            "materia": "DIREITO TRIBUTÁRIO",
            "aula_planilha": "Aula 02",
            "assunto": "Imunidade tributária",
            "enunciado": "A imunidade tributária:",
            "alternativas": [
                {"chave":"A","texto":"decorre apenas de lei ordinária."},
                {"chave":"B","texto":"constitui limitação constitucional ao poder de tributar."},
                {"chave":"C","texto":"equivale sempre a isenção tributária."},
            ],
            "gabarito": "B",
            "explicacao": "A imunidade tributária decorre da Constituição e limita a competência tributária.",
            "banca": "CEBRASPE",
            "revisao": {"status":"aprovado","confianca":1.0,"alertas":[]},
            "imagem_questao": {"path": str(Path(self.tmp.name)/"figura.png"), "origem":"teste"},
            "contexto_visual": {"necessario": True, "observacao": "Figura ilustrativa vinculada ao item."},
        })
        self.db.update_question(uid, q)
        self.study.sync_questions()
        return uid

    def test_release_and_study_v11(self) -> None:
        self.assertEqual(app_shared.APP_VERSION, "6.23.2")
        with self.db.connect() as connection:
            versions = [int(r["version"]) for r in migration_history(connection) if r["component"] == "study"]
            tables = {r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertIn(11, versions)
        self.assertIn("tutor_scaffold_sessions", tables)
        self.assertIn("tutor_scaffold_events", tables)

    def test_scaffold_progression_records_support_signal(self) -> None:
        uid = self.make_question()
        first = self.engines.ai.start_scaffolding(uid, representation="texto", online=False)
        self.assertTrue(first["ok"])
        self.assertEqual(first["step"]["level"], 0)
        sid = first["session"]["id"]
        second = self.engines.ai.advance_scaffolding(sid, action="next", online=False)
        self.assertEqual(second["step"]["level"], 1)
        solved = self.engines.ai.advance_scaffolding(sid, action="solved", online=False)
        self.assertTrue(solved["completed"])
        self.assertEqual(solved["session"]["solved_level"], 1)
        signal = self.study.scaffolding_signal(uid)
        self.assertEqual(signal["sessions"], 1)
        self.assertGreater(signal["independence_score"], 0.7)
        state = self.engines.learner.question_state(uid)
        self.assertIn("scaffolding", state)
        self.assertIn("support_adjusted_confidence", state)

    def test_reveal_full_explanation_marks_high_support(self) -> None:
        uid = self.make_question("Q670-FULL")
        first = self.engines.ai.start_scaffolding(uid, representation="passo_a_passo", online=False)
        sid = first["session"]["id"]
        final = self.engines.ai.advance_scaffolding(sid, action="reveal", online=False)
        self.assertTrue(final["completed"])
        self.assertEqual(final["step"]["level"], 5)
        self.assertIn("final_tutor", final["step"])
        signal = self.study.scaffolding_signal(uid)
        self.assertTrue(signal["high_support"])
        self.assertLessEqual(signal["independence_score"], 0.05)

    def test_multimodal_packet_is_local_and_privacy_safe(self) -> None:
        uid = self.make_question("Q670-VISUAL")
        packet = self.engines.ai.tutor_packet(uid, mode="socratico")
        self.assertTrue(packet["multimodal"]["has_image"])
        self.assertFalse(packet["multimodal"]["external_image_upload"])
        self.assertIn("imagem", packet["multimodal"]["privacy_note"].casefold())
        result = self.engines.ai.start_scaffolding(uid, representation="visual", online=False)
        self.assertEqual(result["step"]["representation"], "visual")
        self.assertIn("Revisão visual", result["step"]["content"]["hint"])

    def test_scaffold_tables_are_cloud_sync_scoped(self) -> None:
        self.assertIn("tutor_scaffold_sessions", SYNC_TABLE_MAP)
        self.assertIn("tutor_scaffold_events", SYNC_TABLE_MAP)

    def test_api_and_ui_are_wired(self) -> None:
        required = {"start_tutor_scaffolding", "advance_tutor_scaffolding", "get_tutor_scaffolding"}
        self.assertTrue(required.issubset(ALLOWED_API_METHODS))
        html = (BASE / "web" / "index.html").read_text(encoding="utf-8")
        js = (BASE / "web" / "app.js").read_text(encoding="utf-8")
        self.assertIn('id="tutorRepresentation"', html)
        self.assertIn('id="tutorScaffoldStatus"', html)
        self.assertIn("startTutorScaffolding", js)
        self.assertIn("advanceTutorScaffold", js)
        for method in required:
            self.assertIn(method, js)

    def test_six_engine_architecture_preserved(self) -> None:
        architecture = self.engines.architecture()
        self.assertGreaterEqual(architecture["engine_count"], 6)
        self.assertTrue(architecture["extensible"])
        self.assertTrue(architecture["all_ready"])
        versions = {x["id"]: x["version"] for x in architecture["engines"]}
        self.assertEqual(versions["ai_engine"], "qf-ai-engine-4")
        self.assertEqual(versions["learner_model"], "qf-learner-engine-4")
        self.assertEqual(versions["learning_engine"], "qf-learning-engine-6")



if __name__ == "__main__":
    unittest.main()
