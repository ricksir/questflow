from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
import urllib.request
from pathlib import Path

from app_shared import TAXONOMY_PATH
from web_api import QuestFlowWebApi
from web_server import QuestFlowLocalServer


class StudioV1GoldOperationTests(unittest.TestCase):
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
        assert self.api.commands is not None and self.api.queries is not None
        question = {
            "id": "SRC-STUDIO-V1-GOLD",
            "codigo_origem": "SRC-STUDIO-V1-GOLD",
            "fingerprint": hashlib.sha256(b"SRC-STUDIO-V1-GOLD").hexdigest(),
            "materia": "Direito Tributário",
            "assunto": "Suspensão da exigibilidade",
            "assuntos": ["Suspensão da exigibilidade"],
            "banca": "CEBRASPE",
            "ano": 2026,
            "orgao": "Órgão de teste",
            "prova": "Prova de teste",
            "tipo": "Múltipla escolha",
            "enunciado": "Assinale a hipótese que suspende a exigibilidade do crédito tributário.",
            "alternativas": [
                {"chave": "A", "texto": "A moratória suspende a exigibilidade do crédito tributário."},
                {"chave": "B", "texto": "A moratória sempre extingue o crédito tributário."},
                {"chave": "C", "texto": "A suspensão elimina a obrigação principal."},
                {"chave": "D", "texto": "A suspensão converte o crédito em obrigação natural."},
                {"chave": "E", "texto": "A suspensão dispensa previsão legal."},
            ],
            "gabarito": "A",
            "explicacao": (
                "A moratória é hipótese legal de suspensão da exigibilidade do crédito tributário. "
                "A suspensão impede temporariamente sua cobrança, sem extinguir o crédito."
            ),
            "fonte": {"arquivo": "studio_v1_gold.pdf", "pagina_inicial": 1},
            "proveniencia": {"tipo": "oficial", "verificada": True},
            "revisao": {"status": "aprovado", "confianca": 1.0},
        }
        imported = self.api.commands.import_extraction({
            "source_file": "studio_v1_gold.pdf",
            "questions": [question],
        })
        self.assertEqual(imported["inserted"], 1)
        saved = self.api.queries.by_code(question["codigo_origem"])
        assert saved is not None
        self.uid = str(saved["database_uid"])

    def tearDown(self) -> None:
        self.api.shutdown()
        self.temp.cleanup()

    def test_contract_exposes_gold_operations_as_mutating(self) -> None:
        definitions = {
            item["name"]: item
            for item in self.api.get_studio_contract_v1()["operations"]
        }
        for operation in (
            "governance.gold.questions.add",
            "governance.gold.regressions.run",
        ):
            with self.subTest(operation=operation):
                self.assertEqual(definitions[operation]["module"], "ai")
                self.assertTrue(definitions[operation]["mutating"])

    def test_dispatcher_adds_question_and_runs_persistent_regression(self) -> None:
        added = self.api.dispatch_studio_v1(
            "governance.gold.questions.add",
            {"uid": self.uid, "label": "CTN ouro", "notes": "Aprovação humana de teste."},
        )
        self.assertTrue(added["ok"])
        self.assertEqual(added["data"]["gold"]["expected_answer"], "A")
        self.assertEqual(added["data"]["summary"]["active_gold_questions"], 1)

        regression = self.api.dispatch_studio_v1(
            "governance.gold.regressions.run",
            {"limit": 50},
        )
        self.assertTrue(regression["ok"])
        self.assertEqual(regression["data"]["result"]["cases"], 1)
        self.assertTrue(regression["data"]["result"]["run_id"])
        self.assertEqual(
            regression["data"]["summary"]["last_run"]["run_id"],
            regression["data"]["result"]["run_id"],
        )

    def test_gold_operations_return_validation_errors(self) -> None:
        cases = (
            ("governance.gold.questions.add", {}),
            ("governance.gold.regressions.run", {"limit": "inválido"}),
        )
        for operation, payload in cases:
            with self.subTest(operation=operation):
                result = self.api.dispatch_studio_v1(operation, payload)
                self.assertFalse(result["ok"])
                self.assertEqual(result["code"], "validation_error")
                self.assertEqual(result["status"], 400)

    def test_authenticated_routes_add_gold_and_run_regression(self) -> None:
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

            added = post(
                "/api/v1/studio/governance/gold/questions",
                {"uid": self.uid, "label": "CTN HTTP", "notes": "Aprovação humana HTTP."},
            )
            self.assertTrue(added["ok"])
            self.assertEqual(added["operation"], "governance.gold.questions.add")

            regression = post(
                "/api/v1/studio/governance/gold/regressions",
                {"limit": 50},
            )
            self.assertTrue(regression["ok"])
            self.assertEqual(regression["contract"], "questflow.studio.v1")
            self.assertEqual(regression["operation"], "governance.gold.regressions.run")
            self.assertEqual(regression["data"]["result"]["cases"], 1)
        finally:
            server.stop()

    def test_frontend_uses_studio_post_with_legacy_fallbacks(self) -> None:
        javascript = (Path(__file__).resolve().parents[1] / "web" / "app.js").read_text(encoding="utf-8")

        self.assertEqual(javascript.count("'governance/gold/questions'"), 2)
        self.assertIn("'governance/gold/regressions'", javascript)
        for method in ("add_gold_question", "run_gold_regression"):
            self.assertIn(f"'{method}'", javascript)
            self.assertNotIn(f"bridge.call('{method}'", javascript)


if __name__ == "__main__":
    unittest.main()
