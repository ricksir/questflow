from __future__ import annotations

import re
import tempfile
import unittest
from pathlib import Path

from core.learner_model import update_bkt, update_irt_online
from core.schema_migrations import migration_history
from core.storage import QuestFlowDatabase
from core.study import SelectionFilters, StudyRepository
from web_server import ALLOWED_API_METHODS

BASE = Path(__file__).resolve().parents[1]


class LearnerModel600Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="qf-learner600-")
        self.db = QuestFlowDatabase(Path(self.tmp.name) / "q.sqlite")
        self.study = StudyRepository(self.db)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def make_question(self, code: str, topic: str = "Crédito tributário") -> str:
        uid = self.db.create_manual_question(None)
        q = self.db.get_question(uid); assert q
        q.update({
            "codigo_origem": code, "id": code,
            "materia": "DIREITO TRIBUTÁRIO", "aula_planilha": "Aula 03",
            "assunto": topic, "assuntos": [topic], "enunciado": f"Questão {code} sobre {topic}.",
            "alternativas": [{"chave": "A", "texto": "Certa"}, {"chave": "B", "texto": "Errada"}],
            "gabarito": "A", "telegram": {"indice_correto": 0},
            "revisao": {"status": "aprovado", "confianca": 1.0, "alertas": []},
        })
        self.db.update_question(uid, q)
        self.study.sync_questions()
        return uid

    def test_bkt_and_irt_move_in_expected_direction(self) -> None:
        correct = update_bkt(0.25, True)
        wrong = update_bkt(0.75, False)
        self.assertGreater(correct.mastery, 0.25)
        self.assertLess(wrong.posterior_observation, 0.75)
        irt_correct = update_irt_online(0.0, 0.0, 1.0, True)
        irt_wrong = update_irt_online(0.0, 0.0, 1.0, False)
        self.assertGreater(irt_correct.theta, 0.0)
        self.assertLess(irt_correct.difficulty, 0.0)
        self.assertLess(irt_wrong.theta, 0.0)
        self.assertGreater(irt_wrong.difficulty, 0.0)

    def test_study_migration_8_and_learning_event(self) -> None:
        uid = self.make_question("Q600-1")
        with self.db.connect() as connection:
            result1 = self.study._update_learner_model_event(
                connection, attempt_id="evt-1", question_uid=uid, correct=True,
                answered_at="2026-08-13T01:00:00+00:00",
            )
            result2 = self.study._update_learner_model_event(
                connection, attempt_id="evt-2", question_uid=uid, correct=True,
                answered_at="2026-08-13T01:05:00+00:00",
            )
            state = connection.execute(
                "SELECT kt_mastery, kt_confidence, irt_information, learner_fusion_priority, learner_model_version FROM study_state WHERE question_uid = ?",
                (uid,),
            ).fetchone()
            versions = [row for row in migration_history(connection) if row["component"] == "study"]
        self.assertTrue(result1["ok"] and result2["ok"])
        self.assertGreater(float(result2["mastery"]), float(result1["mastery"]))
        self.assertIsNotNone(state["kt_mastery"])
        self.assertGreater(float(state["kt_confidence"]), 0.0)
        self.assertGreater(float(state["irt_information"]), 0.0)
        self.assertGreaterEqual(float(state["learner_fusion_priority"]), 0.0)
        self.assertEqual(state["learner_model_version"], "qf-learner-2")
        self.assertEqual(max(int(row["version"]) for row in versions), 12)
        dashboard = self.study.learner_model_dashboard()
        self.assertEqual(dashboard["events"], 2)
        self.assertGreaterEqual(dashboard["concepts"], 3)
        self.assertTrue(dashboard["abilities"])

    def test_existing_attempt_history_is_backfilled_automatically(self) -> None:
        uid = self.make_question("Q600-HISTORY", "Obrigação tributária")
        with self.db.connect() as connection:
            for index, correct in enumerate((True, False, True), 1):
                delivery_id = f"hist-delivery-{index}"
                attempt_id = f"hist-attempt-{index}"
                when = f"2026-08-1{index}T12:00:00+00:00"
                connection.execute(
                    "INSERT INTO telegram_deliveries(id, cycle_id, question_uid, poll_id, chat_id, message_id, sent_at, direct_poll, status) VALUES (?, ?, ?, ?, ?, ?, ?, 1, 'respondido')",
                    (delivery_id, "hist-cycle", uid, f"hist-poll-{index}", "chat", index, when),
                )
                connection.execute(
                    "INSERT INTO telegram_attempts(id, delivery_id, question_uid, poll_id, user_id, username, selected_indices_json, is_correct, answered_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (attempt_id, delivery_id, uid, f"hist-poll-{index}", "user", "tester", "[0]" if correct else "[1]", 1 if correct else 0, when),
                )
        status = self.study.ensure_learner_model_current()
        self.assertEqual(status["action"], "rebuilt_predictions")
        self.assertEqual(status["events"], 3)
        model = self.study.question_learning_state(uid)
        self.assertGreater(model["mastery_confidence"], 0.0)
        self.assertGreater(model["irt_attempts"], 0)
        second = self.study.ensure_learner_model_current()
        self.assertEqual(second["action"], "none")

    def test_learner_fusion_influences_only_within_same_fsrs_bucket(self) -> None:
        high = self.make_question("Q600-HIGH", "Suspensão")
        low = self.make_question("Q600-LOW", "Extinção")
        self.study.set_learning_preferences(studied_only=False, early_review_enabled=True)
        with self.db.connect() as connection:
            connection.execute("UPDATE study_state SET learner_fusion_priority=100 WHERE question_uid=?", (high,))
            connection.execute("UPDATE study_state SET learner_fusion_priority=0 WHERE question_uid=?", (low,))
        chosen = self.study.select_questions(SelectionFilters(subjects=[], approved_only=True), 1)
        self.assertEqual(chosen[0]["database_uid"], high)

    def test_http_allowlist_covers_every_frontend_bridge_call(self) -> None:
        js = (BASE / "web" / "app.js").read_text(encoding="utf-8")
        called = set(re.findall(r"bridge\.call\(\s*['\"]([^'\"]+)['\"]", js))
        missing = sorted(called - set(ALLOWED_API_METHODS))
        self.assertEqual(missing, [], f"Métodos usados pela UI fora da allowlist HTTP: {missing}")
        for required in {
            "get_bank_intelligence", "get_semantic_index_summary", "start_semantic_rebuild",
            "get_learning_model", "start_learner_model_rebuild",
        }:
            self.assertIn(required, ALLOWED_API_METHODS)

    def test_visual_analytics_binds_learner_model_before_rendering(self) -> None:
        js = (BASE / "web" / "app.js").read_text(encoding="utf-8")
        marker = "function renderVisualAnalyticsPanel(data)"
        start = js.index(marker)
        block = js[start:start + 650]
        self.assertIn("const learnerModel = data?.learner_model || {};", block)
        self.assertIn("learnerModelPanelHtml(learnerModel)", block)

    def test_curation_label_is_not_forced_to_ellipsis(self) -> None:
        html = (BASE / "web" / "index.html").read_text(encoding="utf-8")
        css = (BASE / "web" / "styles.css").read_text(encoding="utf-8")
        self.assertIn('<span class="nav-label">Curadoria inteligente</span>', html)
        self.assertIn('.nav-item[data-route="curation"] > .nav-label', css)
        self.assertIn('white-space: normal', css)


class LocalHttpCurationRegressionTests(unittest.TestCase):
    def test_curation_and_rag_methods_are_reachable_over_http(self):
        import json
        import urllib.request
        from pathlib import Path
        from web_server import QuestFlowLocalServer

        class DummyApi:
            def get_bank_intelligence(self):
                return {"status": "ok", "questions": 12}

            def get_semantic_index_summary(self):
                return {"status": "ok", "coverage": 1.0}

        web_root = Path(__file__).resolve().parents[1] / "web"
        server = QuestFlowLocalServer(DummyApi(), web_root, preferred_port=0)
        server.start()
        try:
            for method in ("get_bank_intelligence", "get_semantic_index_summary"):
                payload = json.dumps({"method": method, "args": []}).encode("utf-8")
                request = urllib.request.Request(
                    f"{server.base_url}/api/call",
                    data=payload,
                    headers={
                        "Content-Type": "application/json",
                        "X-QuestFlow-Token": server.token,
                    },
                    method="POST",
                )
                with urllib.request.urlopen(request, timeout=5) as response:
                    result = json.loads(response.read().decode("utf-8"))
                self.assertTrue(result["ok"])
                self.assertEqual("ok", result["result"]["status"])
        finally:
            server.stop()


if __name__ == "__main__":
    unittest.main()
