from __future__ import annotations

import json
import tempfile
import unittest
import urllib.request
from pathlib import Path

from core.engines import EngineRegistry
from core.question_services import QuestionCommandService, QuestionQueryService
from core.recommender import blended_projection, multiobjective_priority, wilson_interval
from core.schema_migrations import migration_history
from core.storage import QuestFlowDatabase
from core.study import StudyRepository
from web_server import ALLOWED_API_METHODS, QuestFlowLocalServer

BASE = Path(__file__).resolve().parents[1]


class Stage4RecommendationSimulation620Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="qf-stage4-620-")
        self.db = QuestFlowDatabase(Path(self.tmp.name) / "q.sqlite")
        self.study = StudyRepository(self.db)
        self.study.set_learning_preferences(studied_only=False, early_review_enabled=True)
        self.engines = EngineRegistry.build(
            database=self.db,
            queries=QuestionQueryService(self.db),
            commands=QuestionCommandService(self.db),
            study=self.study,
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def make_question(self, index: int, *, subject: str = "DIREITO TRIBUTÁRIO", topic: str | None = None, board: str = "CEBRASPE") -> str:
        topic = topic or f"Assunto {index % 4}"
        uid = self.db.create_manual_question(None)
        q = self.db.get_question(uid); assert q
        q.update({
            "codigo_origem": f"Q620-{index}", "id": f"Q620-{index}",
            "materia": subject, "aula_planilha": f"Aula {index % 3:02d}",
            "assunto": topic, "assuntos": [topic], "banca": board, "ano": 2026,
            "enunciado": f"Questão adaptativa {index} sobre {topic} e sua aplicação.",
            "alternativas": [
                {"chave": "A", "texto": "Alternativa correta"},
                {"chave": "B", "texto": "Alternativa incorreta"},
                {"chave": "C", "texto": "Outro distrator"},
            ],
            "gabarito": "A", "telegram": {"indice_correto": 0},
            "revisao": {"status": "aprovado", "confianca": 1.0, "alertas": []},
        })
        self.db.update_question(uid, q)
        self.study.sync_questions()
        return uid

    def seed_questions(self, count: int = 8) -> list[str]:
        boards = ["CEBRASPE", "FGV", "FCC"]
        subjects = ["DIREITO TRIBUTÁRIO", "AUDITORIA", "CONTABILIDADE"]
        return [self.make_question(i, subject=subjects[i % len(subjects)], board=boards[i % len(boards)]) for i in range(count)]

    def test_multiobjective_modes_are_explainable(self) -> None:
        common = dict(
            mastery=.35, mastery_confidence=.8, retrievability=.30,
            coverage_gap=.7, board_incidence=.6, irt_information=.65,
            exam_urgency=.7, days_since_seen=25,
        )
        revision = multiobjective_priority(mode="revisao", **common)
        diagnostic = multiobjective_priority(mode="diagnostico", **common)
        self.assertGreater(revision.components["forgetting_risk"], diagnostic.components["forgetting_risk"])
        self.assertGreater(diagnostic.components["irt_information"], revision.components["irt_information"])
        self.assertGreater(revision.score, 0)
        self.assertTrue(revision.reasons)
        self.assertEqual(revision.version, "qf-multiobjective-2")

    def test_projection_always_exposes_interval_and_more_data_narrows_it(self) -> None:
        low_n = blended_projection(correct=3, attempts=5, mastery=.6, mastery_confidence=.4, theta_scale=55)
        high_n = blended_projection(correct=60, attempts=100, mastery=.6, mastery_confidence=.9, theta_scale=55)
        self.assertLess(low_n["low"], low_n["estimate"])
        self.assertGreater(low_n["high"], low_n["estimate"])
        self.assertLess(high_n["high"] - high_n["low"], low_n["high"] - low_n["low"])
        wlow, whigh = wilson_interval(60, 100)
        self.assertLess(wlow, .60)
        self.assertGreater(whigh, .60)

    def test_study_migration_9_creates_adaptive_tables_and_attempt_source(self) -> None:
        with self.db.connect() as connection:
            versions = [int(row["version"]) for row in migration_history(connection) if row["component"] == "study"]
            tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            attempt_columns = {row[1] for row in connection.execute("PRAGMA table_info(telegram_attempts)")}
        self.assertEqual(max(versions), 12)
        self.assertTrue({"adaptive_simulation_sessions", "adaptive_simulation_items"}.issubset(tables))
        self.assertIn("source", attempt_columns)

    def test_dashboard_exposes_recommendations_projection_and_board_incidence(self) -> None:
        self.seed_questions(9)
        dashboard = self.engines.learning.recommendation_dashboard(mode="equilibrado", limit=6)
        self.assertEqual(dashboard["schema"], "questflow.recommender.v1")
        self.assertTrue(dashboard["recommendations"])
        first = dashboard["recommendations"][0]
        self.assertIn("score", first)
        self.assertIn("components", first)
        self.assertIn("bucket", first)
        self.assertTrue(dashboard["projections"])
        self.assertIn("low", dashboard["projections"][0]["projection"])
        self.assertTrue(dashboard["board_incidence"])
        self.assertTrue(any("não chance de aprovação" in text for text in dashboard["caveats"]))

    def test_adaptive_simulation_reselects_only_after_answer_and_updates_models(self) -> None:
        self.seed_questions(8)
        simulation = self.engines.learning.start_simulation({"mode": "diagnostico", "target_count": 5})
        first_uid = simulation["current"]["uid"]
        first_session = simulation["session"]["id"]
        result = self.engines.learning.submit_simulation_answer(
            first_session, 0, response_seconds=12, confidence="alta", perceived_difficulty="media"
        )
        self.assertEqual(result["session"]["answered_count"], 1)
        self.assertTrue(result["feedback"]["is_correct"])
        self.assertIsNotNone(result["current"])
        self.assertNotEqual(result["current"]["uid"], first_uid)
        learning = self.study.question_learning_state(first_uid)
        self.assertGreater(float(learning.get("mastery_confidence") or 0), 0)
        with self.db.connect() as connection:
            source = connection.execute(
                "SELECT source FROM telegram_attempts WHERE question_uid=? ORDER BY answered_at DESC LIMIT 1", (first_uid,)
            ).fetchone()[0]
            used = connection.execute(
                "SELECT COUNT(*), COUNT(DISTINCT question_uid) FROM adaptive_simulation_items WHERE session_id=?", (first_session,)
            ).fetchone()
        self.assertEqual(source, "simulado_adaptativo")
        self.assertEqual(int(used[0]), int(used[1]))

    def test_simulation_progress_is_not_mixed_into_telegram_operational_history(self) -> None:
        self.seed_questions(6)
        simulation = self.engines.learning.start_simulation({"target_count": 5})
        self.engines.learning.submit_simulation_answer(simulation["session"]["id"], 1, response_seconds=7)
        recent = self.study.recent_deliveries(limit=10)
        self.assertFalse(any(str(item.get("source") or "") == "simulado_adaptativo" for item in recent))
        with self.db.connect() as connection:
            local_count = connection.execute("SELECT COUNT(*) FROM telegram_attempts WHERE source='simulado_adaptativo'").fetchone()[0]
        self.assertEqual(local_count, 1)

    def test_six_engine_architecture_is_preserved_and_learning_engine_owns_stage4(self) -> None:
        self.seed_questions(5)
        architecture = self.engines.architecture()
        self.assertGreaterEqual(architecture["engine_count"], 6)
        self.assertTrue(architecture["extensible"])
        ids = {item["id"] for item in architecture["engines"]}
        self.assertNotIn("recommender_engine", ids)
        learning = next(item for item in architecture["engines"] if item["id"] == "learning_engine")
        self.assertEqual(learning["version"], "qf-learning-engine-6")
        self.assertEqual(learning["metrics"]["recommender"], "qf-multiobjective-2")

    def test_stage4_allowlist_and_frontend_are_wired(self) -> None:
        required = {
            "get_recommendation_dashboard", "start_adaptive_simulation", "get_adaptive_simulation",
            "submit_adaptive_simulation_answer", "abandon_adaptive_simulation",
        }
        self.assertTrue(required.issubset(ALLOWED_API_METHODS))
        html = (BASE / "web" / "index.html").read_text(encoding="utf-8")
        js = (BASE / "web" / "app.js").read_text(encoding="utf-8")
        self.assertIn('data-route="recommend"', html)
        self.assertIn('data-page="recommend"', html)
        self.assertIn('id="simulationWorkspace"', html)
        self.assertIn("async function loadRecommendationPage", js)
        self.assertIn("async function submitAdaptiveSimulationAnswer", js)
        for method in required:
            self.assertIn(method, js)


class LocalHttpStage4RegressionTests(unittest.TestCase):
    def test_stage4_methods_are_reachable_over_real_local_http(self) -> None:
        class DummyApi:
            def get_recommendation_dashboard(self, mode="equilibrado"):
                return {"ok": True, "dashboard": {"mode": mode, "recommendations": []}}
            def start_adaptive_simulation(self, payload=None):
                return {"ok": True, "simulation": {"session": {"id": "s1"}, "current": None}}
            def get_adaptive_simulation(self, session_id):
                return {"ok": True, "simulation": {"session": {"id": session_id}, "current": None}}

        server = QuestFlowLocalServer(DummyApi(), BASE / "web", preferred_port=0)
        server.start()
        try:
            calls = (
                ("get_recommendation_dashboard", ["diagnostico"]),
                ("start_adaptive_simulation", [{"target_count": 5}]),
                ("get_adaptive_simulation", ["s1"]),
            )
            for method, args in calls:
                payload = json.dumps({"method": method, "args": args}).encode("utf-8")
                request = urllib.request.Request(
                    f"{server.base_url}/api/call", data=payload,
                    headers={"Content-Type": "application/json", "X-QuestFlow-Token": server.token}, method="POST",
                )
                with urllib.request.urlopen(request, timeout=5) as response:
                    result = json.loads(response.read().decode("utf-8"))
                self.assertTrue(result["ok"])
                self.assertTrue(result["result"]["ok"])
        finally:
            server.stop()


if __name__ == "__main__":
    unittest.main()
