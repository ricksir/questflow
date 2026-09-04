from __future__ import annotations

import json
import tempfile
import unittest
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import app_shared
from core.engines import EngineRegistry
from core.question_services import QuestionCommandService, QuestionQueryService
from core.storage import QuestFlowDatabase
from core.study import StudyRepository
from web_server import ALLOWED_API_METHODS, QuestFlowLocalServer

BASE = Path(__file__).resolve().parents[1]


class EvidenceBenchmark671Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="qf-671-")
        self.db = QuestFlowDatabase(Path(self.tmp.name) / "q.sqlite")
        self.study = StudyRepository(self.db)
        self.queries = QuestionQueryService(self.db)
        self.commands = QuestionCommandService(self.db)
        self.engines = EngineRegistry.build(database=self.db, queries=self.queries, commands=self.commands, study=self.study)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def make_question(self, code: str = "Q671") -> str:
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
            "telegram": {"indice_correto": 1},
            "explicacao": "A imunidade decorre da Constituição.",
            "banca": "CEBRASPE",
            "revisao": {"status":"aprovado","confianca":1.0,"alertas":[]},
        })
        self.db.update_question(uid, q)
        self.study.sync_questions()
        return uid

    def test_release_and_six_engines(self) -> None:
        self.assertEqual(app_shared.APP_VERSION, "6.23.2")
        architecture = self.engines.architecture()
        self.assertGreaterEqual(architecture["engine_count"], 6)
        self.assertTrue(architecture["extensible"])
        versions = {item["id"]: item["version"] for item in architecture["engines"]}
        self.assertEqual(versions["learner_model"], "qf-learner-engine-4")
        self.assertEqual(versions["learning_engine"], "qf-learning-engine-6")

    def test_evidence_plan_explains_abstention_and_returns_questions(self) -> None:
        uid = self.make_question()
        self.study.record_local_practice_attempt(uid, 1, source="test671")
        self.study.record_local_practice_attempt(uid, 0, source="test671")
        model = self.study.learner_model_dashboard()
        uncertain = model["uncertain_concepts"]
        self.assertTrue(uncertain)
        item = next(x for x in uncertain if x["concept_type"] == "assunto")
        plan = self.study.evidence_collection_plan(item["concept_key"])
        self.assertTrue(plan["evidence"]["abstain"])
        self.assertFalse(plan["is_problem"])
        self.assertGreater(plan["recommended_questions"], 0)
        self.assertIn(uid, plan["candidate_uids"])
        self.assertIn("Não é um problema", plan["explanation"])

    def test_evidence_collection_starts_scoped_diagnostic_simulation(self) -> None:
        uid = self.make_question("Q671-E")
        self.study.record_local_practice_attempt(uid, 1, source="test671")
        self.study.record_local_practice_attempt(uid, 0, source="test671")
        model = self.study.learner_model_dashboard()
        item = next(x for x in model["uncertain_concepts"] if x["concept_type"] == "assunto")
        simulation = self.engines.learning.start_evidence_collection(item["concept_key"])
        self.assertEqual(simulation["session"]["mode"], "diagnostico")
        self.assertLessEqual(simulation["session"]["target_count"], 5)
        self.assertEqual(simulation["current"]["uid"], uid)
        self.assertIn("evidence_plan", simulation)
        answered = self.engines.learning.submit_simulation_answer(simulation["session"]["id"], 1)
        self.assertIn("evidence_plan", answered)
        self.assertTrue(answered["evidence_complete"])
        self.assertEqual(answered["session"]["status"], "concluido")

    def test_scaffolding_benchmark_uses_later_real_attempts(self) -> None:
        uid = self.make_question("Q671-B")
        started = self.engines.ai.start_scaffolding(uid, representation="texto", online=False)
        sid = started["session"]["id"]
        self.engines.ai.advance_scaffolding(sid, action="next", online=False)
        self.engines.ai.advance_scaffolding(sid, action="solved", online=False)
        past = (datetime.now(timezone.utc) - timedelta(days=2)).replace(microsecond=0).isoformat()
        with self.db.connect() as connection:
            connection.execute("UPDATE tutor_scaffold_sessions SET completed_at=?, updated_at=? WHERE id=?", (past, past, sid))
        self.study.record_local_practice_attempt(uid, 1, source="test671-retention")
        benchmark = self.study.scaffolding_benchmark()
        self.assertEqual(benchmark["sessions"], 1)
        self.assertGreaterEqual(benchmark["delayed_observations"], 1)
        self.assertEqual(benchmark["delayed_accuracy"], 1.0)
        self.assertTrue(benchmark["by_support"])
        dashboard = self.study.learner_model_dashboard()
        self.assertIn("scaffolding_benchmark", dashboard)

    def test_api_and_ui_wiring(self) -> None:
        required = {"get_evidence_collection_plan", "start_evidence_collection", "get_scaffolding_benchmark"}
        self.assertTrue(required.issubset(ALLOWED_API_METHODS))
        js = (BASE / "web" / "app.js").read_text(encoding="utf-8")
        self.assertIn("openEvidenceCollection", js)
        self.assertIn("Benchmark pedagógico do Tutor", js)
        for method in required:
            self.assertIn(method, js)


class LocalHttp671Tests(unittest.TestCase):
    def test_evidence_methods_are_reachable_over_real_http(self) -> None:
        class DummyApi:
            def get_evidence_collection_plan(self, concept_key):
                return {"ok": True, "plan": {"concept_key": concept_key, "recommended_questions": 2}}
            def start_evidence_collection(self, concept_key):
                return {"ok": True, "simulation": {"session": {"id": "e1"}, "concept_key": concept_key}}
            def get_scaffolding_benchmark(self):
                return {"ok": True, "benchmark": {"observations": 3}}

        server = QuestFlowLocalServer(DummyApi(), BASE / "web", preferred_port=0)
        server.start()
        try:
            for method, args in (("get_evidence_collection_plan", ["assunto|X|Y"]), ("start_evidence_collection", ["assunto|X|Y"]), ("get_scaffolding_benchmark", [])):
                payload = json.dumps({"method": method, "args": args}).encode("utf-8")
                request = urllib.request.Request(
                    f"{server.base_url}/api/call", data=payload,
                    headers={"Content-Type":"application/json", "X-QuestFlow-Token":server.token}, method="POST",
                )
                with urllib.request.urlopen(request, timeout=5) as response:
                    result = json.loads(response.read().decode("utf-8"))
                self.assertTrue(result["ok"])
                self.assertTrue(result["result"]["ok"])
        finally:
            server.stop()


if __name__ == "__main__":
    unittest.main()
