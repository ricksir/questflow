from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
import urllib.request
from pathlib import Path

from app_shared import TAXONOMY_PATH
from core.storage import QuestFlowDatabase
from web_api import QuestFlowWebApi
from web_server import QuestFlowLocalServer


class StudioV1CurationReviewTests(unittest.TestCase):
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

    def tearDown(self) -> None:
        self.api.shutdown()
        self.temp.cleanup()

    @staticmethod
    def _question(code: str, *, critical_ok: bool = True) -> dict:
        statement = "Considere a situação apresentada e assinale a alternativa correta segundo a legislação aplicável ao caso concreto."
        return {
            "id": code,
            "codigo_origem": code,
            "fingerprint": hashlib.sha256((code + statement).encode()).hexdigest(),
            "materia": "DIREITO TRIBUTÁRIO" if critical_ok else "",
            "aula_planilha": "Aula 05",
            "assunto": "Sujeitos da obrigação tributária",
            "assuntos": ["Sujeitos da obrigação tributária"],
            "banca": "",
            "ano": None,
            "orgao": "",
            "prova": "",
            "tipo": "multipla_escolha",
            "enunciado": statement,
            "alternativas": [
                {"chave": "A", "texto": "Alternativa correta"},
                {"chave": "B", "texto": "Alternativa incorreta"},
            ],
            "gabarito": "A",
            "explicacao": "Comentário humano revisado para a questão.",
            "revisao": {"status": "aprovado_automaticamente", "confianca": 0.95, "alertas": []},
            "proveniencia": {"tipo": "oficial", "verificada": True, "fonte_primaria": "Prova oficial / edital"},
            "origem_questao": "oficial",
            "comentario_meta": {"origem": "manual_nao_classificado"},
        }

    def _import_question(self, code: str, *, critical_ok: bool = True) -> str:
        db = QuestFlowDatabase(self.db_path)
        db.import_extraction({"source_file": "prova.pdf", "questions": [self._question(code, critical_ok=critical_ok)]})
        db.rebuild_bank_intelligence_derived()
        with db.connect() as connection:
            row = connection.execute("SELECT uid FROM questions WHERE source_code=?", (code,)).fetchone()
        assert row is not None
        return str(row[0])

    def test_contract_marks_curation_completion_as_mutating_and_dispatches_it(self) -> None:
        uid = self._import_question("Q-STUDIO-CURATION-DIRECT")
        contract = self.api.get_studio_contract_v1()
        definition = next(item for item in contract["operations"] if item["name"] == "curation.review.complete")
        self.assertTrue(definition["mutating"])
        self.assertEqual(definition["module"], "editorial_bank")

        result = self.api.dispatch_studio_v1(
            "curation.review.complete",
            {"uid": uid, "reviewer": "Revisão humana via Studio v1"},
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["contract"], "questflow.studio.v1")
        self.assertEqual(result["operation"], "curation.review.complete")
        self.assertEqual(result["module"], "editorial_bank")
        self.assertEqual(result["data"]["intelligence"]["curation_status"], "pronta")
        self.assertTrue(result["data"]["intelligence"]["curation_review"]["human_approved"])

    def test_generic_studio_v1_http_route_completes_curation_review(self) -> None:
        uid = self._import_question("Q-STUDIO-CURATION-HTTP")
        server = QuestFlowLocalServer(
            self.api,
            Path(__file__).resolve().parents[1] / "web",
            preferred_port=0,
        )
        server.start()
        try:
            request = urllib.request.Request(
                f"{server.base_url}/api/v1/studio/use-cases/curation/review/complete",
                data=json.dumps({
                    "uid": uid,
                    "reviewer": "Revisão humana HTTP Studio v1",
                }, ensure_ascii=False).encode("utf-8"),
                headers={
                    "X-QuestFlow-Token": server.token,
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=5) as response:
                payload = json.loads(response.read().decode("utf-8"))
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["contract"], "questflow.studio.v1")
            self.assertEqual(payload["operation"], "curation.review.complete")
            self.assertEqual(payload["module"], "editorial_bank")
            self.assertEqual(payload["data"]["intelligence"]["curation_status"], "pronta")
        finally:
            server.stop()


    def test_blocked_review_keeps_business_details_in_studio_v1(self) -> None:
        uid = self._import_question("Q-STUDIO-CURATION-BLOCK", critical_ok=False)
        result = self.api.dispatch_studio_v1(
            "curation.review.complete",
            {"uid": uid, "reviewer": "Revisão humana bloqueada"},
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["operation"], "curation.review.complete")
        self.assertFalse(result["data"]["ok"])
        self.assertIn("Matéria informada", result["data"].get("blocking_missing", []))

    def test_frontend_uses_studio_v1_with_legacy_fallback_and_keeps_blockers(self) -> None:
        javascript = (Path(__file__).resolve().parents[1] / "web" / "app.js").read_text(encoding="utf-8")
        helper_start = javascript.index("async function completeCurationReview")
        helper_end = javascript.index("async function loadBankFixOptions", helper_start)
        helper = javascript[helper_start:helper_end]

        self.assertIn("bridge.studioPost(", helper)
        self.assertIn("'use-cases/curation/review/complete'", helper)
        self.assertIn("bridge.call('complete_curation_review'", helper)
        self.assertEqual(javascript.count("bridge.call('complete_curation_review'"), 1)
        self.assertIn("await completeCurationReview(uid, 'Revisão humana pela Curadoria')", javascript)
        self.assertIn(
            "await completeCurationReview(state.currentUid, 'Revisão humana pelo editor da Curadoria')",
            javascript,
        )
        self.assertIn("completion?.blocking_missing", javascript)


if __name__ == "__main__":
    unittest.main()
