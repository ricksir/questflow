from __future__ import annotations

import hashlib
import tempfile
import unittest
import json
import urllib.request
from pathlib import Path

from core.engines import EngineRegistry
from core.question_services import QuestionCommandService, QuestionQueryService
from core.storage import QuestFlowDatabase
from core.study import StudyRepository
from web_server import ALLOWED_API_METHODS, QuestFlowLocalServer

BASE = Path(__file__).resolve().parents[1]


class Stage5ControlledGenerationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = QuestFlowDatabase(Path(self.tmp.name) / "questflow.sqlite")
        self.queries = QuestionQueryService(self.db)
        self.commands = QuestionCommandService(self.db)
        self.study = StudyRepository(self.db)
        self.engines = EngineRegistry.build(
            database=self.db, queries=self.queries, commands=self.commands, study=self.study
        )
        self.uid = self._insert_source_question()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _insert_source_question(self) -> str:
        question = {
            "id": "SRC-630-1",
            "codigo_origem": "SRC-630-1",
            "fingerprint": hashlib.sha256(b"SRC-630-1").hexdigest(),
            "materia": "Direito Tributário",
            "assunto": "Suspensão da exigibilidade",
            "assuntos": ["Suspensão da exigibilidade"],
            "banca": "CEBRASPE",
            "ano": 2024,
            "orgao": "Órgão teste",
            "prova": "Prova teste",
            "tipo": "Múltipla escolha",
            "enunciado": "Considere as regras do Código Tributário Nacional sobre suspensão da exigibilidade do crédito tributário.",
            "alternativas": [
                {"chave": "A", "texto": "A moratória suspende a exigibilidade do crédito tributário."},
                {"chave": "B", "texto": "A moratória extingue definitivamente o crédito tributário."},
                {"chave": "C", "texto": "A suspensão elimina a obrigação tributária principal."},
                {"chave": "D", "texto": "A suspensão converte o crédito em obrigação natural."},
                {"chave": "E", "texto": "A suspensão impede qualquer lançamento tributário futuro."},
            ],
            "gabarito": "A",
            "explicacao": (
                "Nos termos do CTN, a moratória é hipótese de suspensão da exigibilidade do crédito tributário. "
                "A suspensão não extingue o crédito tributário e impede temporariamente sua exigência enquanto perdurar a causa legal."
            ),
            "fonte": {"arquivo": "fonte_stage5.pdf", "pagina_inicial": 1},
            "proveniencia": {"tipo": "oficial", "verificada": True},
            "revisao": {"status": "aprovado", "confianca": 1.0},
        }
        result = self.commands.import_extraction({"source_file": "fonte_stage5.pdf", "questions": [question]})
        self.assertEqual(result["inserted"], 1)
        saved = self.queries.by_code("SRC-630-1")
        assert saved is not None
        return str(saved["database_uid"])

    def _source_ids(self) -> list[str]:
        retrieval = self.engines.knowledge.retrieve(self.uid, "", limit=8)
        return [item["id"] for item in retrieval["items"]]

    def test_stage5_migrations_and_six_engines(self) -> None:
        history = self.queries.schema_history()
        versions = {(row["component"], row["version"]) for row in history}
        self.assertIn(("question_bank", 7), versions)
        self.assertIn(("ai_governance", 2), versions)
        architecture = self.engines.architecture()
        self.assertGreaterEqual(architecture["engine_count"], 6)
        self.assertTrue(architecture["extensible"])
        self.assertTrue(architecture["all_ready"])
        self.assertIn("selected_source_generation", architecture["principles"])
        self.assertIn("temporal_legislation", architecture["principles"])
        self.assertIn("gold_regression", architecture["principles"])

    def test_legislation_versions_resolve_by_date_and_enter_rag(self) -> None:
        first = self.engines.editorial.upsert_legislation({
            "canonical_key": "CTN_ART_151",
            "title": "CTN art. 151 · versão 1",
            "subject": "Direito Tributário",
            "effective_from": "1966-10-25",
            "effective_to": "2025-12-31",
            "text_content": "Suspendem a exigibilidade do crédito tributário a moratória e o depósito do seu montante integral.",
            "source_label": "Fonte oficial",
        })
        second = self.engines.editorial.upsert_legislation({
            "canonical_key": "CTN_ART_151",
            "title": "CTN art. 151 · versão 2",
            "subject": "Direito Tributário",
            "effective_from": "2026-01-01",
            "text_content": "Suspendem a exigibilidade do crédito tributário a moratória, o depósito integral e as demais hipóteses previstas nesta versão.",
            "source_label": "Fonte oficial",
        })
        self.assertNotEqual(first["id"], second["id"])
        self.assertEqual(self.engines.editorial.resolve_legislation("CTN_ART_151", "2024-05-01")["id"], first["id"])
        self.assertEqual(self.engines.editorial.resolve_legislation("CTN_ART_151", "2026-08-13")["id"], second["id"])
        summary = self.engines.editorial.legislation_summary()
        self.assertEqual(summary["versions"], 2)
        self.assertGreaterEqual(summary["rag_chunks"], 2)

    def test_generator_refuses_unselected_sources(self) -> None:
        with self.assertRaisesRegex(ValueError, "Selecione ao menos uma fonte"):
            self.engines.ai.generate_controlled_question(seed_uid=self.uid, source_chunk_ids=[])

    def test_generation_is_grounded_validated_and_not_auto_published(self) -> None:
        result = self.engines.ai.generate_controlled_question(
            seed_uid=self.uid,
            source_chunk_ids=self._source_ids()[:1],
            question_type="multipla_escolha",
            board_style="CEBRASPE",
        )
        draft = result["draft"]
        self.assertEqual(draft["generator_model"], "qf-controlled-generator-1")
        self.assertIn(draft["status"], {"validado", "rascunho"})
        self.assertEqual(draft["validation"]["version"], "qf-generation-critic-2")
        self.assertTrue(draft["validation"]["independent_model"])
        self.assertEqual(draft["draft"]["tipo_origem"], "inedita_propria")
        self.assertEqual(draft["draft"]["geracao_ia"]["politica"], "selected_sources_only")
        self.assertIsNone(draft["published_question_uid"])
        self.assertIsNone(self.queries.by_code(draft["draft"]["codigo_origem"]))

    def test_publish_requires_human_approval_then_enters_editorial_bank(self) -> None:
        result = self.engines.ai.generate_controlled_question(
            seed_uid=self.uid, source_chunk_ids=self._source_ids()[:1]
        )
        draft_id = result["draft"]["id"]
        with self.assertRaisesRegex(ValueError, "Somente rascunhos aprovados"):
            self.engines.ai.publish_generation_draft(draft_id)
        self.engines.governance.review_generation_draft(draft_id, decision="aprovar", note="Revisado por humano")
        published = self.engines.ai.publish_generation_draft(draft_id)
        saved = published["published"]["question"]
        self.assertEqual(saved["revisao"]["status"], "aprovado")
        self.assertEqual(saved["tipo_origem"], "inedita_propria")
        self.assertEqual(published["draft"]["status"], "publicado")

    def test_temporal_validator_blocks_norm_not_in_force_on_exam_date(self) -> None:
        version = self.engines.editorial.upsert_legislation({
            "canonical_key": "NORMA_NOVA",
            "title": "Norma nova",
            "subject": "Direito Tributário",
            "effective_from": "2027-01-01",
            "text_content": "A norma nova estabelece requisito específico para a suspensão da exigibilidade do crédito tributário após sua vigência.",
        })
        chunk_id = f"leg:{version['id']}:1"
        result = self.engines.ai.generate_controlled_question(
            seed_uid=self.uid, source_chunk_ids=[chunk_id], exam_date="2026-08-13"
        )
        validation = result["draft"]["validation"]
        self.assertEqual(validation["status"], "revisar")
        self.assertTrue(any(flag.startswith("norma_ainda_nao_vigente_na_data_da_prova") for flag in validation["critical_flags"]))
        with self.assertRaisesRegex(ValueError, "não passou pela validação independente"):
            self.engines.governance.review_generation_draft(result["draft"]["id"], decision="aprovar")

    def test_distractors_record_student_error_pattern(self) -> None:
        self.engines.governance.record_diagnosis(
            question_uid=self.uid,
            attempt_id=None,
            diagnosis={
                "version":"test","error_type":"confusao_conceitual","confidence":0.95,
                "signals":["teste"],"intervention":"comparar conceitos","explanation":"teste"
            },
        )
        result = self.engines.ai.generate_controlled_question(
            seed_uid=self.uid, source_chunk_ids=self._source_ids()[:1]
        )
        q = result["draft"]["draft"]
        self.assertGreaterEqual(result["draft"]["error_profile"]["total"], 1)
        based = [alt.get("geracao_meta",{}).get("based_on_error") for alt in q["alternativas"]]
        self.assertIn("confusao_conceitual", based)

    def test_gold_set_and_regression_are_persistent(self) -> None:
        gold = self.engines.ai.add_gold_question(self.uid, label="CTN ouro")
        self.assertEqual(gold["expected_answer"], "A")
        result = self.engines.ai.run_gold_regression()
        self.assertEqual(result["cases"], 1)
        self.assertEqual(result["model"], "qf-gold-grounded-baseline-2")
        self.assertTrue(result["run_id"])
        dashboard = self.engines.governance.gold_dashboard()
        self.assertEqual(dashboard["active_gold_questions"], 1)
        self.assertEqual(dashboard["last_run"]["run_id"], result["run_id"])

    def test_stage5_http_methods_are_allowlisted(self) -> None:
        required = {
            "get_stage5_workspace", "create_legislation_version", "resolve_legislation_version",
            "generate_controlled_question", "get_generation_draft", "review_generation_draft",
            "publish_generation_draft", "add_gold_question", "run_gold_regression", "get_gold_dashboard",
        }
        self.assertTrue(required.issubset(ALLOWED_API_METHODS))

    def test_stage5_frontend_is_wired(self) -> None:
        html = (BASE / "web" / "index.html").read_text(encoding="utf-8")
        js = (BASE / "web" / "app.js").read_text(encoding="utf-8")
        self.assertIn('data-route="stage5"', html)
        self.assertIn('data-page="stage5"', html)
        self.assertIn('id="stage5SourcePool"', html)
        self.assertIn('id="legislationTimeline"', html)
        self.assertIn('id="goldRegressionPanel"', html)
        self.assertIn("async function loadStage5Page", js)
        self.assertIn("async function generateStage5Draft", js)
        self.assertIn("async function resolveLegislationVersion", js)
        self.assertIn("async function runGoldRegression", js)


class LocalHttpStage5RegressionTests(unittest.TestCase):
    def test_stage5_methods_are_reachable_over_real_local_http(self) -> None:
        class DummyApi:
            def get_stage5_workspace(self, uid=""):
                return {"ok": True, "workspace": {"selected": {"uid": uid}, "source_pool": []}}
            def resolve_legislation_version(self, canonical_key, reference_date):
                return {"ok": True, "version": {"canonical_key": canonical_key, "effective_from": reference_date}}
            def get_gold_dashboard(self):
                return {"ok": True, "summary": {"active_gold_questions": 0}, "items": []}

        server = QuestFlowLocalServer(DummyApi(), BASE / "web", preferred_port=0)
        server.start()
        try:
            calls = (
                ("get_stage5_workspace", ["u1"]),
                ("resolve_legislation_version", ["CTN_ART_151", "2026-08-13"]),
                ("get_gold_dashboard", []),
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
