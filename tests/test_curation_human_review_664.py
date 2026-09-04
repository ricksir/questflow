from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from core.bank_intelligence import calculate_quality, curation_readiness, curation_status
from core.storage import QuestFlowDatabase
from web_server import ALLOWED_API_METHODS


class CurationHumanReview664Tests(unittest.TestCase):
    @staticmethod
    def question(code: str, *, approved: bool, critical_ok: bool = True) -> dict:
        statement = "Considere a situação apresentada e assinale a alternativa correta segundo a legislação aplicável ao caso concreto."
        return {
            "id": code,
            "codigo_origem": code,
            "fingerprint": hashlib.sha256((code + statement).encode()).hexdigest(),
            "materia": "DIREITO TRIBUTÁRIO" if critical_ok else "",
            "aula_planilha": "Aula 01",
            "assunto": "Crédito tributário",
            "assuntos": ["Crédito tributário"],
            "banca": "CEBRASPE",
            "ano": 2026,
            "orgao": "RFB",
            "prova": "Auditor Fiscal",
            "tipo": "multipla_escolha",
            "enunciado": statement,
            "alternativas": [
                {"chave": "A", "texto": "Alternativa correta"},
                {"chave": "B", "texto": "Alternativa incorreta"},
            ],
            "gabarito": "A",
            # Deliberadamente sem explicação e sem fonte primária: qualidade B.
            "explicacao": "",
            "revisao": {"status": "aprovado" if approved else "pendente", "confianca": 1.0, "alertas": []},
            "proveniencia": {"tipo": "oficial", "verificada": True},
            "origem_questao": "oficial",
            "comentario_meta": {"origem": "sem_comentario"},
        }

    def test_human_approved_grade_b_is_ready_when_critical_fields_are_intact(self):
        q = self.question("Q664-B", approved=True)
        quality = calculate_quality(q)
        self.assertEqual(quality["grade"], "B")
        self.assertLess(quality["score"], 88)
        readiness = curation_readiness(q)
        self.assertTrue(readiness["human_approved"])
        self.assertTrue(readiness["can_complete_review"])
        self.assertTrue(readiness["human_override"])
        self.assertEqual(curation_status(q), "pronta")

    def test_pending_grade_b_can_be_explicitly_completed(self):
        with tempfile.TemporaryDirectory() as temp:
            db = QuestFlowDatabase(Path(temp) / "q.sqlite")
            q = self.question("Q664-PENDING", approved=False)
            result = db.import_extraction({"source_file": "prova.pdf", "questions": [q]})
            self.assertEqual(result["inserted"], 1)
            db.rebuild_bank_intelligence_derived()
            with db.connect() as c:
                uid = str(c.execute("SELECT uid FROM questions WHERE source_code='Q664-PENDING'").fetchone()[0])
            before = db.bank_intelligence_attention("curation", limit=10)
            self.assertEqual(before["total"], 1)
            self.assertTrue(before["items"][0]["can_complete_review"])
            self.assertFalse(before["items"][0]["human_approved"])
            completed = db.complete_curation_review(uid, reviewer="Teste humano")
            self.assertTrue(completed["ok"])
            self.assertEqual(completed["intelligence"]["curation_status"], "pronta")
            self.assertEqual(completed["intelligence"]["quality"]["grade"], "B")
            after = db.bank_intelligence_attention("curation", limit=10)
            self.assertEqual(after["total"], 0)
            summary = db.bank_intelligence_summary()
            self.assertEqual(summary["needs_review"], 0)
            self.assertEqual(summary["human_review_ready_b"], 1)

    def test_human_approval_does_not_override_missing_critical_fields(self):
        q = self.question("Q664-CRITICAL", approved=True, critical_ok=False)
        readiness = curation_readiness(q)
        self.assertIn("Matéria informada", readiness["blocking_missing"])
        self.assertFalse(readiness["can_complete_review"])
        self.assertNotEqual(curation_status(q), "pronta")


    def test_eighteen_approved_grade_b_questions_leave_pending_queue_after_rebuild(self):
        with tempfile.TemporaryDirectory() as temp:
            db = QuestFlowDatabase(Path(temp) / "q.sqlite")
            questions = [self.question(f"Q664-{i:02d}", approved=True) for i in range(18)]
            result = db.import_extraction({"source_file": "prova.pdf", "questions": questions})
            self.assertEqual(result["inserted"], 18)
            rebuilt = db.rebuild_bank_intelligence_derived()
            self.assertEqual(rebuilt["summary"]["needs_review"], 0)
            self.assertEqual(rebuilt["summary"]["ready"], 18)
            self.assertEqual(rebuilt["summary"]["quality_bands"]["B"], 18)
            self.assertEqual(rebuilt["summary"]["human_review_ready_b"], 18)

    def test_summary_distinguishes_awaiting_approval_from_objective_gaps(self):
        with tempfile.TemporaryDirectory() as temp:
            db = QuestFlowDatabase(Path(temp) / "q.sqlite")
            db.import_extraction({
                "source_file": "prova.pdf",
                "questions": [
                    self.question("Q664-READY-TO-APPROVE", approved=False),
                    self.question("Q664-GAP", approved=False, critical_ok=False),
                ],
            })
            db.rebuild_bank_intelligence_derived()
            summary = db.bank_intelligence_summary()
            self.assertEqual(summary["needs_review"], 2)
            self.assertEqual(summary["awaiting_review_completion"], 1)
            self.assertEqual(summary["objective_curation_gaps"], 1)

    def test_complete_review_method_is_http_allowlisted(self):
        self.assertIn("complete_curation_review", ALLOWED_API_METHODS)



if __name__ == "__main__":
    unittest.main()
