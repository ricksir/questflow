from __future__ import annotations

import json
import tempfile
import unittest
import urllib.parse
import urllib.request
from pathlib import Path

from app_shared import TAXONOMY_PATH
from core.storage import QuestFlowDatabase
from web_api import QuestFlowWebApi
from web_server import QuestFlowLocalServer


class StudioV1RecommendationReadTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.db_path = self.root / "questflow.sqlite"
        self.api = QuestFlowWebApi(
            self.db_path,
            config={},
            config_path=self.root / "config.json",
            taxonomy_path=TAXONOMY_PATH,
        )
        self.api.bootstrap()
        self._seed_questions()

    def tearDown(self) -> None:
        self.api.shutdown()
        self.temp.cleanup()

    def _seed_questions(self, count: int = 6) -> None:
        database = QuestFlowDatabase(self.db_path)
        for index in range(count):
            uid = database.create_manual_question(None)
            question = database.get_question(uid)
            assert question is not None
            question.update({
                "codigo_origem": f"Q-STUDIO-REC-{index}",
                "id": f"Q-STUDIO-REC-{index}",
                "materia": "DIREITO TRIBUTÁRIO",
                "aula_planilha": f"Aula {index:02d}",
                "assunto": f"Assunto {index}",
                "assuntos": [f"Assunto {index}"],
                "banca": "CEBRASPE",
                "ano": 2026,
                "enunciado": f"Questão adaptativa {index} para validar o contrato Studio v1.",
                "alternativas": [
                    {"chave": "A", "texto": "Alternativa correta"},
                    {"chave": "B", "texto": "Alternativa incorreta"},
                ],
                "gabarito": "A",
                "telegram": {"indice_correto": 0},
                "revisao": {"status": "aprovado", "confianca": 1.0, "alertas": []},
            })
            database.update_question(uid, question)
        assert self.api.study is not None
        self.api.study.set_learning_preferences(studied_only=False, early_review_enabled=True)
        self.api.study.sync_questions()

    def _start_simulation(self) -> str:
        started = self.api.start_adaptive_simulation({"mode": "equilibrado", "target_count": 5})
        self.assertTrue(started["ok"])
        return str(started["simulation"]["session"]["id"])

    def test_contract_exposes_learning_reads_as_non_mutating(self) -> None:
        definitions = {
            item["name"]: item
            for item in self.api.get_studio_contract_v1()["operations"]
        }
        for operation in ("learning.recommendations.dashboard", "learning.simulations.get"):
            with self.subTest(operation=operation):
                self.assertEqual(definitions[operation]["module"], "learning")
                self.assertFalse(definitions[operation]["mutating"])

    def test_contract_exposes_simulation_lifecycle_as_mutating(self) -> None:
        definitions = {
            item["name"]: item
            for item in self.api.get_studio_contract_v1()["operations"]
        }
        for operation in (
            "learning.simulations.start",
            "learning.simulations.answers.submit",
            "learning.simulations.abandon",
        ):
            with self.subTest(operation=operation):
                self.assertEqual(definitions[operation]["module"], "learning")
                self.assertTrue(definitions[operation]["mutating"])

    def test_dispatcher_matches_existing_learning_engine_facades(self) -> None:
        legacy_dashboard = self.api.get_recommendation_dashboard("diagnostico")
        studio_dashboard = self.api.dispatch_studio_v1(
            "learning.recommendations.dashboard",
            {"mode": "diagnostico"},
        )
        self.assertTrue(studio_dashboard["ok"])
        self.assertEqual(studio_dashboard["data"], {"dashboard": legacy_dashboard["dashboard"]})

        session_id = self._start_simulation()
        legacy_simulation = self.api.get_adaptive_simulation(session_id)
        studio_simulation = self.api.dispatch_studio_v1(
            "learning.simulations.get",
            {"session_id": session_id},
        )
        self.assertTrue(studio_simulation["ok"])
        self.assertEqual(studio_simulation["data"], {"simulation": legacy_simulation["simulation"]})

    def test_missing_simulation_returns_validation_error(self) -> None:
        result = self.api.dispatch_studio_v1("learning.simulations.get", {})

        self.assertFalse(result["ok"])
        self.assertEqual(result["code"], "validation_error")
        self.assertEqual(result["status"], 400)

    def test_dispatcher_runs_simulation_lifecycle(self) -> None:
        started = self.api.dispatch_studio_v1(
            "learning.simulations.start",
            {"mode": "equilibrado", "target_count": 5},
        )
        self.assertTrue(started["ok"])
        session_id = str(started["data"]["simulation"]["session"]["id"])

        answered = self.api.dispatch_studio_v1(
            "learning.simulations.answers.submit",
            {
                "session_id": session_id,
                "selected_index": 0,
                "response_seconds": 12.5,
                "confidence": "certeza",
                "perceived_difficulty": "facil",
                "learning_gap": False,
            },
        )
        self.assertTrue(answered["ok"])
        self.assertEqual(answered["data"]["simulation"]["session"]["answered_count"], 1)
        self.assertTrue(answered["data"]["simulation"]["feedback"]["is_correct"])

        abandoned = self.api.dispatch_studio_v1(
            "learning.simulations.abandon",
            {"session_id": session_id},
        )
        self.assertTrue(abandoned["ok"])
        self.assertEqual(abandoned["data"]["simulation"]["session"]["status"], "abandonado")

    def test_simulation_lifecycle_validation_errors_use_studio_contract(self) -> None:
        cases = (
            ("learning.simulations.answers.submit", {}),
            ("learning.simulations.answers.submit", {"session_id": "sessao"}),
            ("learning.simulations.abandon", {}),
        )
        for operation, payload in cases:
            with self.subTest(operation=operation, payload=payload):
                result = self.api.dispatch_studio_v1(operation, payload)
                self.assertFalse(result["ok"])
                self.assertEqual(result["code"], "validation_error")
                self.assertEqual(result["status"], 400)

    def test_authenticated_get_routes_return_learning_payloads(self) -> None:
        session_id = self._start_simulation()
        server = QuestFlowLocalServer(
            self.api,
            Path(__file__).resolve().parents[1] / "web",
            preferred_port=0,
        )
        server.start()
        try:
            cases = (
                (
                    "/api/v1/studio/learning/recommendations?"
                    + urllib.parse.urlencode({"mode": "diagnostico"}),
                    "learning.recommendations.dashboard",
                ),
                (
                    f"/api/v1/studio/learning/simulations/{urllib.parse.quote(session_id)}",
                    "learning.simulations.get",
                ),
            )
            for path, operation in cases:
                with self.subTest(operation=operation):
                    request = urllib.request.Request(
                        f"{server.base_url}{path}",
                        headers={"X-QuestFlow-Token": server.token},
                    )
                    with urllib.request.urlopen(request, timeout=5) as response:
                        payload = json.loads(response.read().decode("utf-8"))
                    self.assertTrue(payload["ok"])
                    self.assertEqual(payload["contract"], "questflow.studio.v1")
                    self.assertEqual(payload["operation"], operation)
        finally:
            server.stop()

    def test_authenticated_post_routes_run_simulation_lifecycle(self) -> None:
        server = QuestFlowLocalServer(
            self.api,
            Path(__file__).resolve().parents[1] / "web",
            preferred_port=0,
        )
        server.start()
        try:
            def post(path: str, payload: dict) -> dict:
                request = urllib.request.Request(
                    f"{server.base_url}{path}",
                    data=json.dumps(payload).encode("utf-8"),
                    headers={
                        "Content-Type": "application/json",
                        "X-QuestFlow-Token": server.token,
                    },
                    method="POST",
                )
                with urllib.request.urlopen(request, timeout=10) as response:
                    return json.loads(response.read().decode("utf-8"))

            started = post(
                "/api/v1/studio/learning/simulations",
                {"mode": "equilibrado", "target_count": 5},
            )
            self.assertTrue(started["ok"])
            self.assertEqual(started["operation"], "learning.simulations.start")
            session_id = str(started["data"]["simulation"]["session"]["id"])
            encoded_id = urllib.parse.quote(session_id)

            answered = post(
                f"/api/v1/studio/learning/simulations/{encoded_id}/answers",
                {"selected_index": 0, "response_seconds": 8, "confidence": "certeza"},
            )
            self.assertTrue(answered["ok"])
            self.assertEqual(answered["operation"], "learning.simulations.answers.submit")

            abandoned = post(
                f"/api/v1/studio/learning/simulations/{encoded_id}/abandon",
                {},
            )
            self.assertTrue(abandoned["ok"])
            self.assertEqual(abandoned["contract"], "questflow.studio.v1")
            self.assertEqual(abandoned["operation"], "learning.simulations.abandon")
        finally:
            server.stop()

    def test_frontend_uses_studio_get_with_legacy_fallbacks(self) -> None:
        javascript = (Path(__file__).resolve().parents[1] / "web" / "app.js").read_text(encoding="utf-8")

        self.assertIn("`learning/recommendations?${query.toString()}`", javascript)
        self.assertIn("'get_recommendation_dashboard'", javascript)
        self.assertIn("`learning/simulations/${encodeURIComponent(id)}`", javascript)
        self.assertIn("'get_adaptive_simulation'", javascript)
        self.assertEqual(javascript.count("getRecommendationDashboard("), 3)
        for method in ("get_recommendation_dashboard", "get_adaptive_simulation"):
            self.assertNotIn(f"bridge.call('{method}'", javascript)
        self.assertIn("'learning/simulations'", javascript)
        self.assertIn("`learning/simulations/${encodeURIComponent(state.adaptiveSimulationId)}/answers`", javascript)
        self.assertIn("`learning/simulations/${encodeURIComponent(state.adaptiveSimulationId)}/abandon`", javascript)
        for method in (
            "start_adaptive_simulation",
            "submit_adaptive_simulation_answer",
            "abandon_adaptive_simulation",
        ):
            self.assertIn(f"'{method}'", javascript)
            self.assertNotIn(f"bridge.call('{method}'", javascript)


if __name__ == "__main__":
    unittest.main()
