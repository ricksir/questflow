from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from core.engines import EngineRegistry
from core.question_services import QuestionCommandService, QuestionQueryService
from core.schema_migrations import migration_history
from core.storage import QuestFlowDatabase
from core.study import StudyRepository
from web_server import ALLOWED_API_METHODS

BASE = Path(__file__).resolve().parents[1]


class TutorAIArchitecture610Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="qf-tutor610-")
        self.db = QuestFlowDatabase(Path(self.tmp.name) / "q.sqlite")
        self.study = StudyRepository(self.db)
        self.queries = QuestionQueryService(self.db)
        self.commands = QuestionCommandService(self.db)
        self.engines = EngineRegistry.build(
            database=self.db,
            queries=self.queries,
            commands=self.commands,
            study=self.study,
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def make_question(self, code: str = "Q610-1", *, explanation: str = "O CTN disciplina a suspensão da exigibilidade do crédito tributário.") -> str:
        uid = self.db.create_manual_question(None)
        q = self.db.get_question(uid); assert q
        q.update({
            "codigo_origem": code,
            "id": code,
            "materia": "DIREITO TRIBUTÁRIO",
            "aula_planilha": "Aula 03",
            "assunto": "Suspensão da exigibilidade",
            "assuntos": ["Suspensão da exigibilidade", "Crédito tributário"],
            "enunciado": "Assinale a alternativa correta sobre a suspensão da exigibilidade do crédito tributário.",
            "alternativas": [
                {"chave": "A", "texto": "A hipótese indicada suspende a exigibilidade."},
                {"chave": "B", "texto": "A hipótese indicada extingue necessariamente o crédito."},
            ],
            "gabarito": "A",
            "explicacao": explanation,
            "banca": "CEBRASPE",
            "ano": 2026,
            "referencias_legais": ["CTN, art. 151"],
            "telegram": {"indice_correto": 0},
            "revisao": {"status": "aprovado", "confianca": 1.0, "alertas": []},
        })
        self.db.update_question(uid, q)
        self.study.sync_questions()
        return uid

    def add_attempt(self, uid: str, *, correct: bool = False, confidence: str = "chutei", error_type: str = "", response_seconds: int = 8) -> str:
        attempt_id = f"attempt-{uid}-{confidence}-{error_type}-{response_seconds}"
        delivery_id = f"delivery-{attempt_id}"
        with self.db.connect() as connection:
            connection.execute(
                "INSERT INTO telegram_deliveries(id, cycle_id, question_uid, poll_id, chat_id, message_id, sent_at, direct_poll, status) VALUES (?, ?, ?, ?, ?, ?, ?, 1, 'respondido')",
                (delivery_id, "cycle-610", uid, f"poll-{attempt_id}", "chat", 1, "2026-08-13T10:00:00+00:00"),
            )
            connection.execute(
                """
                INSERT INTO telegram_attempts(
                    id, delivery_id, question_uid, poll_id, user_id, username,
                    selected_indices_json, is_correct, answered_at, confidence,
                    error_type, learning_gap, response_seconds
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    attempt_id, delivery_id, uid, f"poll-{attempt_id}", "user", "tester",
                    "[0]" if correct else "[1]", 1 if correct else 0,
                    "2026-08-13T10:00:00+00:00", confidence, error_type,
                    0, response_seconds,
                ),
            )
        self.study.ensure_learner_model_current()
        return attempt_id

    def test_registry_exposes_extensible_domain_modules(self) -> None:
        architecture = self.engines.architecture()
        self.assertEqual(architecture["architecture"], "extensible_domain_modules")
        self.assertGreaterEqual(architecture["engine_count"], 6)
        self.assertTrue(architecture["extensible"])
        ids = {item["id"] for item in architecture["engines"]}
        self.assertTrue({
            "editorial_bank", "learner_model", "learning_engine",
            "knowledge_engine", "ai_engine", "evaluation_governance",
        }.issubset(ids))
        self.assertTrue(architecture["all_ready"])

    def test_ai_governance_migration_and_tables_exist(self) -> None:
        with self.db.connect() as connection:
            history = [r for r in migration_history(connection) if r["component"] == "ai_governance"]
            tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        self.assertEqual([int(r["version"]) for r in history][:1], [1])
        self.assertGreaterEqual(max(int(r["version"]) for r in history), 1)
        self.assertTrue({"qf_ai_interactions", "qf_ai_evaluations", "qf_error_diagnoses"}.issubset(tables))

    def test_error_diagnosis_uses_behavioral_signal_and_is_a_hypothesis(self) -> None:
        uid = self.make_question("Q610-CHUTE")
        self.add_attempt(uid, correct=False, confidence="chutei")
        diagnosis = self.engines.ai.diagnose_error(uid, persist=True)
        self.assertEqual(diagnosis["error_type"], "chute")
        self.assertGreaterEqual(float(diagnosis["confidence"]), 0.5)
        self.assertIn("não é uma certeza causal", diagnosis["explanation"])
        with self.db.connect() as connection:
            count = connection.execute("SELECT COUNT(*) FROM qf_error_diagnoses WHERE question_uid=?", (uid,)).fetchone()[0]
        self.assertGreaterEqual(count, 1)

    def test_reported_concept_confusion_has_precedence(self) -> None:
        uid = self.make_question("Q610-CONFUSAO")
        self.add_attempt(uid, correct=False, confidence="media", error_type="confundi", response_seconds=40)
        diagnosis = self.engines.ai.diagnose_error(uid, persist=False)
        self.assertEqual(diagnosis["error_type"], "confusao_conceitual")
        self.assertTrue(any("confusão" in signal.casefold() for signal in diagnosis["signals"]))

    def test_offline_tutor_generates_draft_evaluation_and_audit(self) -> None:
        uid = self.make_question("Q610-TUTOR")
        self.add_attempt(uid, correct=False, confidence="chutei")
        result = self.engines.ai.generate_tutor(uid, mode="professor", user_prompt="Explique meu erro.", online=False)
        self.assertTrue(result["ok"])
        self.assertEqual(result["provider"], "QuestFlow Grounded Composer")
        self.assertEqual(result["publication_policy"], "rascunho_requer_aprovacao_humana")
        self.assertTrue(result["response"])
        self.assertIn("overall_score", result["evaluation"])
        audit = self.engines.governance.interaction(result["interaction_id"])
        self.assertEqual(audit["status"], "rascunho")
        self.assertEqual(audit["prompt_sha256"], audit["prompt_sha256"].lower())
        self.assertIn("evaluation", audit)
        self.assertTrue(audit["sources"])

    def test_editorial_ai_assistance_also_uses_governance_engine(self) -> None:
        uid = self.make_question("Q610-CURADORIA")
        result = self.engines.ai.generate_editorial_commentary(uid, online=False)
        self.assertEqual(result["publication_policy"], "rascunho_requer_aprovacao_humana")
        self.assertIn("evaluation", result)
        audit = self.engines.governance.interaction(result["interaction_id"])
        self.assertEqual(audit["interaction_type"], "editorial_commentary")
        self.assertEqual(audit["status"], "rascunho")
        self.assertIn("evaluation", audit)

    def test_human_review_is_required_to_approve_ai_output(self) -> None:
        uid = self.make_question("Q610-REVIEW")
        result = self.engines.ai.generate_tutor(uid, mode="rapido", online=False)
        before = self.engines.governance.interaction(result["interaction_id"])
        self.assertEqual(before["status"], "rascunho")
        reviewed = self.engines.governance.review_interaction(result["interaction_id"], decision="aprovar", note="Conferido.")
        self.assertEqual(reviewed["status"], "aprovado")
        after = self.engines.governance.interaction(result["interaction_id"])
        self.assertEqual(after["status"], "aprovado")
        self.assertEqual(after["human_note"], "Conferido.")

    def test_independent_evaluator_flags_unsupported_legal_reference(self) -> None:
        uid = self.make_question("Q610-EVAL", explanation="A evidência local trata da suspensão do crédito tributário sem citar dispositivo numérico.")
        interaction_id = self.engines.governance.record_interaction(
            question_uid=uid,
            interaction_type="tutor",
            mode="professor",
            provider="test",
            model="test",
            prompt_text="prompt",
            response_text="Segundo o art. 999, esta é a regra.",
            learner_context={},
            sources=[{"content": "A evidência local explica apenas a regra geral."}],
            diagnosis={"intervention": "Revisar."},
        )
        evaluation = self.engines.governance.evaluate(
            interaction_id,
            response_text="Segundo o art. 999, esta é a regra.",
            mode="professor",
            official_answer="A",
            source_texts=["A evidência local explica apenas a regra geral."],
            diagnosis={"intervention": "Revisar."},
        )
        self.assertTrue(any("referencia_legal_nao_encontrada" in flag for flag in evaluation["flags"]))
        self.assertEqual(evaluation["status"], "revisar")

    def test_stage3_http_allowlist_and_ui_are_wired(self) -> None:
        required = {
            "get_engine_architecture", "get_tutor_workspace", "diagnose_question_error",
            "start_tutor_assist", "get_ai_audit", "get_ai_interaction", "review_ai_interaction",
        }
        self.assertTrue(required.issubset(ALLOWED_API_METHODS))
        html = (BASE / "web" / "index.html").read_text(encoding="utf-8")
        js = (BASE / "web" / "app.js").read_text(encoding="utf-8")
        self.assertIn('data-route="tutor"', html)
        self.assertIn('data-page="tutor"', html)
        self.assertIn('id="engineArchitecture"', html)
        self.assertIn('id="aiAuditTable"', html)
        for method in required:
            self.assertIn(method, js)


class LocalHttpStage3RegressionTests(unittest.TestCase):
    def test_stage3_methods_are_reachable_over_real_local_http(self) -> None:
        import urllib.request
        from web_server import QuestFlowLocalServer

        class DummyApi:
            def get_engine_architecture(self):
                return {"ok": True, "architecture": {"engine_count": 6}}

            def get_tutor_workspace(self, uid=""):
                return {"ok": True, "workspace": {"selected": None, "recent_errors": []}}

            def get_ai_audit(self, limit=20):
                return {"ok": True, "summary": {"interactions": 0}, "items": []}

        server = QuestFlowLocalServer(DummyApi(), BASE / "web", preferred_port=0)
        server.start()
        try:
            for method, args in (
                ("get_engine_architecture", []),
                ("get_tutor_workspace", [""]),
                ("get_ai_audit", [20]),
            ):
                payload = json.dumps({"method": method, "args": args}).encode("utf-8")
                request = urllib.request.Request(
                    f"{server.base_url}/api/call",
                    data=payload,
                    headers={"Content-Type": "application/json", "X-QuestFlow-Token": server.token},
                    method="POST",
                )
                with urllib.request.urlopen(request, timeout=5) as response:
                    result = json.loads(response.read().decode("utf-8"))
                self.assertTrue(result["ok"])
                self.assertTrue(result["result"]["ok"])
        finally:
            server.stop()


if __name__ == "__main__":
    unittest.main()
