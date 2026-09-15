from __future__ import annotations

import json
import tempfile
import unittest
import urllib.parse
import urllib.request
from pathlib import Path

from app_shared import TAXONOMY_PATH
from web_api import QuestFlowWebApi
from web_server import QuestFlowLocalServer


class StudioV1QuestionIntelligenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.api = QuestFlowWebApi(
            self.root / "questflow.sqlite",
            config={},
            config_path=self.root / "config.json",
            taxonomy_path=TAXONOMY_PATH,
        )
        self.api.bootstrap()
        assert self.api.database is not None
        self.api.database.import_extraction({
            "source_file": "intelligence.pdf",
            "questions": [{
                "id": "Q-STUDIO-INTELLIGENCE",
                "codigo_origem": "Q-STUDIO-INTELLIGENCE",
                "materia": "DIREITO TRIBUTÁRIO",
                "aula_planilha": "Aula 01",
                "assunto": "Suspensão da exigibilidade",
                "assuntos": ["Suspensão da exigibilidade"],
                "banca": "FGV",
                "ano": 2026,
                "tipo": "multipla_escolha",
                "enunciado": "Segundo o CTN, qual hipótese suspende a exigibilidade do crédito tributário?",
                "alternativas": [
                    {"chave": "A", "texto": "Moratória."},
                    {"chave": "B", "texto": "Decadência."},
                ],
                "gabarito": "A",
                "explicacao": "A moratória suspende a exigibilidade conforme o CTN, art. 151.",
                "referencias_legais": ["CTN, art. 151"],
                "revisao": {"status": "aprovado", "alertas": []},
            }],
        })
        assert self.api.study is not None
        self.api.study.sync_questions()
        with self.api.database.connect() as connection:
            self.uid = str(connection.execute(
                "SELECT uid FROM questions WHERE source_code = ?",
                ("Q-STUDIO-INTELLIGENCE",),
            ).fetchone()[0])

    def tearDown(self) -> None:
        self.api.shutdown()
        self.temp.cleanup()

    def test_contract_classifies_question_intelligence_operations(self) -> None:
        definitions = {
            item["name"]: item
            for item in self.api.get_studio_contract_v1()["operations"]
        }

        self.assertEqual(definitions["questions.intelligence.refresh"]["module"], "editorial_bank")
        self.assertTrue(definitions["questions.intelligence.refresh"]["mutating"])
        for operation in ("knowledge.questions.graph", "knowledge.rag.context"):
            with self.subTest(operation=operation):
                self.assertEqual(definitions[operation]["module"], "knowledge")
                self.assertFalse(definitions[operation]["mutating"])

    def test_dispatcher_matches_existing_question_intelligence_facades(self) -> None:
        legacy_intelligence = self.api.get_question_intelligence(self.uid, False)
        studio_intelligence = self.api.dispatch_studio_v1(
            "questions.intelligence.refresh",
            {"uid": self.uid, "scan_duplicates": False},
        )
        self.assertTrue(studio_intelligence["ok"], studio_intelligence)
        self.assertEqual(
            studio_intelligence["data"],
            {"intelligence": legacy_intelligence["intelligence"]},
        )

        legacy_graph = self.api.get_question_knowledge_graph(self.uid)
        studio_graph = self.api.dispatch_studio_v1("knowledge.questions.graph", {"uid": self.uid})
        self.assertTrue(studio_graph["ok"])
        self.assertEqual(studio_graph["data"], {"graph": legacy_graph["graph"]})

        query = "artigo 151 CTN suspensão"
        legacy_rag = self.api.get_rag_context(self.uid, query, 5)
        studio_rag = self.api.dispatch_studio_v1(
            "knowledge.rag.context",
            {"uid": self.uid, "query": query, "limit": 5},
        )
        self.assertTrue(studio_rag["ok"])
        self.assertEqual(studio_rag["data"], {"retrieval": legacy_rag["retrieval"]})

    def test_missing_question_identifiers_return_validation_errors(self) -> None:
        for operation in (
            "questions.intelligence.refresh",
            "knowledge.questions.graph",
            "knowledge.rag.context",
        ):
            with self.subTest(operation=operation):
                result = self.api.dispatch_studio_v1(operation, {})
                self.assertFalse(result["ok"])
                self.assertEqual(result["code"], "validation_error")
                self.assertEqual(result["status"], 400)

    def test_authenticated_routes_return_question_intelligence_payloads(self) -> None:
        server = QuestFlowLocalServer(
            self.api,
            Path(__file__).resolve().parents[1] / "web",
            preferred_port=0,
        )
        server.start()
        encoded_uid = urllib.parse.quote(self.uid)
        try:
            post_request = urllib.request.Request(
                f"{server.base_url}/api/v1/studio/questions/{encoded_uid}/intelligence",
                data=json.dumps({"scan_duplicates": False}).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "X-QuestFlow-Token": server.token,
                },
                method="POST",
            )
            with urllib.request.urlopen(post_request, timeout=5) as response:
                intelligence = json.loads(response.read().decode("utf-8"))
            self.assertTrue(intelligence["ok"])
            self.assertEqual(intelligence["operation"], "questions.intelligence.refresh")

            cases = (
                (
                    f"/api/v1/studio/questions/{encoded_uid}/knowledge-graph",
                    "knowledge.questions.graph",
                ),
                (
                    f"/api/v1/studio/questions/{encoded_uid}/rag-context?"
                    + urllib.parse.urlencode({"query": "CTN 151", "limit": 5}),
                    "knowledge.rag.context",
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

    def test_frontend_uses_studio_v1_with_legacy_fallbacks(self) -> None:
        javascript = (Path(__file__).resolve().parents[1] / "web" / "app.js").read_text(encoding="utf-8")

        self.assertIn("`questions/${encodeURIComponent(uid)}/intelligence`", javascript)
        self.assertIn("`questions/${encodeURIComponent(state.currentUid)}/knowledge-graph`", javascript)
        self.assertIn("`questions/${encodeURIComponent(state.currentUid)}/rag-context?${params.toString()}`", javascript)
        for method in ("get_question_intelligence", "get_question_knowledge_graph", "get_rag_context"):
            with self.subTest(method=method):
                self.assertIn(f"'{method}'", javascript)
                self.assertNotIn(f"bridge.call('{method}'", javascript)


if __name__ == "__main__":
    unittest.main()
