from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from core.bank_intelligence import curation_readiness, curation_status
from core.storage import QuestFlowDatabase


class CurationCompletion665Tests(unittest.TestCase):
    @staticmethod
    def question(code: str, *, auto: bool = True, critical_ok: bool = True) -> dict:
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
            "revisao": {
                "status": "aprovado_automaticamente" if auto else "pendente",
                "confianca": 0.95,
                "alertas": [],
            },
            "proveniencia": {"tipo": "oficial", "verificada": True, "fonte_primaria": "Prova oficial / edital"},
            "origem_questao": "oficial",
            "comentario_meta": {"origem": "manual_nao_classificado"},
        }

    def test_automatic_approval_is_not_human_completion_for_grade_b(self):
        q = self.question("Q665-AUTO")
        ready = curation_readiness(q)
        self.assertTrue(ready["auto_approved"])
        self.assertFalse(ready["human_approved"])
        self.assertTrue(ready["can_complete_review"])
        self.assertEqual(curation_status(q), "revisar")

    def test_explicit_completion_removes_autoapproved_b_from_queue(self):
        with tempfile.TemporaryDirectory() as temp:
            db = QuestFlowDatabase(Path(temp) / "q.sqlite")
            db.import_extraction({"source_file": "prova.pdf", "questions": [self.question("Q665-COMPLETE")]})
            db.rebuild_bank_intelligence_derived()
            self.assertEqual(db.bank_intelligence_summary()["needs_review"], 1)
            with db.connect() as c:
                uid = str(c.execute("SELECT uid FROM questions WHERE source_code='Q665-COMPLETE'").fetchone()[0])
            result = db.complete_curation_review(uid, reviewer="Usuário")
            self.assertTrue(result["ok"])
            self.assertEqual(result["intelligence"]["curation_status"], "pronta")
            self.assertTrue(result["intelligence"]["curation_review"]["human_approved"])
            self.assertEqual(db.bank_intelligence_summary()["needs_review"], 0)
            saved = db.get_question(uid)
            self.assertTrue(saved["curadoria"]["revisao_humana_concluida"])
            self.assertEqual(saved["revisao"]["status"], "aprovado")

    def test_completion_refuses_critical_gap_and_explains_it(self):
        with tempfile.TemporaryDirectory() as temp:
            db = QuestFlowDatabase(Path(temp) / "q.sqlite")
            db.import_extraction({"source_file": "prova.pdf", "questions": [self.question("Q665-BLOCK", critical_ok=False)]})
            with db.connect() as c:
                uid = str(c.execute("SELECT uid FROM questions WHERE source_code='Q665-BLOCK'").fetchone()[0])
            result = db.complete_curation_review(uid, reviewer="Usuário")
            self.assertFalse(result["ok"])
            self.assertIn("Matéria informada", result.get("blocking_missing", []))
            self.assertEqual(db.bank_intelligence_summary()["needs_review"], 1)


if __name__ == "__main__":
    unittest.main()
