from __future__ import annotations

import unittest

from core.bank_intelligence import calculate_quality, curation_readiness, statement_integrity


class StatementIntegrity667Tests(unittest.TestCase):
    @staticmethod
    def question(statement: str, answer: str = "C") -> dict:
        return {
            "materia": "DIREITO TRIBUTÁRIO",
            "assunto": "Imunidade tributária",
            "tipo": "multipla_escolha",
            "enunciado": statement,
            "alternativas": [
                {"chave": "A", "texto": "Primeira alternativa."},
                {"chave": "B", "texto": "Segunda alternativa."},
                {"chave": "C", "texto": "Terceira alternativa."},
                {"chave": "D", "texto": "Quarta alternativa."},
            ],
            "gabarito": answer,
            "revisao": {"status": "aprovado_automaticamente"},
            "proveniencia": {"tipo": "oficial", "fonte_primaria": "Prova oficial"},
        }

    def test_short_exam_stem_with_colon_is_contextually_integral(self) -> None:
        q = self.question("A imunidade tributária:")
        result = statement_integrity(q)
        self.assertTrue(result["ok"])
        self.assertEqual(result["reason"], "contextual_short")
        quality = calculate_quality(q)
        check = next(item for item in quality["checks"] if item["label"] == "Enunciado íntegro")
        self.assertTrue(check["ok"])
        self.assertNotIn("Enunciado íntegro", curation_readiness(q)["blocking_missing"])

    def test_no_fixed_40_character_requirement_remains(self) -> None:
        q = self.question("Tributo indireto:")
        self.assertLess(len(q["enunciado"]), 40)
        self.assertTrue(statement_integrity(q)["ok"])

    def test_empty_statement_is_still_blocking(self) -> None:
        q = self.question("")
        self.assertFalse(statement_integrity(q)["ok"])
        self.assertIn("Enunciado íntegro", curation_readiness(q)["blocking_missing"])

    def test_suspected_truncation_is_warning_not_blocker(self) -> None:
        q = self.question("Nos termos da legislação aplicável,")
        result = statement_integrity(q)
        self.assertTrue(result["ok"])
        self.assertTrue(result["warning"])
        quality = calculate_quality(q)
        self.assertTrue(quality["warnings"])
        self.assertNotIn("Enunciado íntegro", curation_readiness(q)["blocking_missing"])

    def test_gabarito_remains_a_separate_check(self) -> None:
        q = self.question("A imunidade tributária:", answer="Z")
        quality = calculate_quality(q)
        statement_check = next(item for item in quality["checks"] if item["label"] == "Enunciado íntegro")
        answer_check = next(item for item in quality["checks"] if item["label"] == "Gabarito consistente")
        self.assertTrue(statement_check["ok"])
        self.assertFalse(answer_check["ok"])

    def test_short_stem_can_complete_human_curation_review(self) -> None:
        import tempfile
        from pathlib import Path
        from core.storage import QuestFlowDatabase

        q = self.question("A imunidade tributária:")
        q.update({
            "codigo_origem": "Q319242",
            "banca": "FGV",
            "ano": 2026,
            "orgao": "SEFAZ",
            "prova": "Auditor",
            "explicacao": "Comentário revisado.",
            "comentario_meta": {"origem": "manual_nao_classificado"},
        })
        with tempfile.TemporaryDirectory() as temp:
            db = QuestFlowDatabase(Path(temp) / "q.sqlite")
            db.import_extraction({"source_file": "prova.pdf", "questions": [q]})
            with db.connect() as c:
                uid = str(c.execute("SELECT uid FROM questions WHERE source_code='Q319242'").fetchone()[0])
            before = db.refresh_question_intelligence(uid, scan_duplicates=False)
            self.assertNotIn("Enunciado íntegro", before["curation_review"]["blocking_missing"])
            result = db.complete_curation_review(uid, reviewer="Usuário")
            self.assertTrue(result["ok"])
            self.assertEqual(result["intelligence"]["curation_status"], "pronta")


if __name__ == "__main__":
    unittest.main()
