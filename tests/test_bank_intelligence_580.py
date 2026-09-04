from __future__ import annotations

import hashlib
import tempfile
import unittest
import uuid
from datetime import datetime, timezone
from pathlib import Path

from core.bank_intelligence import calculate_quality, duplicate_similarity, empirical_difficulty, infer_origin_type
from core.storage import QuestFlowDatabase
from core.study import StudyRepository

BASE = Path(__file__).resolve().parents[1]


class BankIntelligence580Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="qf-bi580-")
        self.db = QuestFlowDatabase(Path(self.tmp.name) / "q.sqlite")
        self.study = StudyRepository(self.db)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    @staticmethod
    def question(code: str, statement: str, *, subject: str = "DIREITO TRIBUTÁRIO") -> dict:
        return {
            "id": code,
            "codigo_origem": code,
            "fingerprint": hashlib.sha256((code + statement).encode("utf-8")).hexdigest(),
            "materia": subject,
            "aula_planilha": "Aula 01",
            "assunto": "Crédito tributário",
            "assuntos": ["Crédito tributário", "Suspensão"],
            "banca": "FGV",
            "ano": 2026,
            "orgao": "SEFAZ",
            "prova": "Auditor Fiscal",
            "tipo": "multipla_escolha",
            "enunciado": statement,
            "alternativas": [
                {"chave": "A", "texto": "Alternativa correta"},
                {"chave": "B", "texto": "Alternativa incorreta"},
            ],
            "gabarito": "A",
            "explicacao": "Explicação fundamentada para revisão do conteúdo.",
            "fonte": {"arquivo": "prova_fgv_2026.pdf", "pagina_inicial": 10},
            "revisao": {"status": "aprovado", "confianca": 1.0, "alertas": []},
            "proveniencia": {"tipo": "oficial", "fonte_primaria": "prova_fgv_2026.pdf", "verificada": True},
            "comentario_meta": {"origem": "professor"},
        }

    def import_question(self, code: str, statement: str) -> str:
        result = self.db.import_extraction({"source_file": "prova.pdf", "questions": [self.question(code, statement)]})
        self.assertEqual(result["inserted"], 1)
        with self.db.connect() as c:
            return str(c.execute("SELECT uid FROM questions WHERE source_code = ?", (code,)).fetchone()[0])

    def test_origin_and_quality_are_explicit_and_explainable(self) -> None:
        q = self.question("Q1", "Considere a situação hipotética apresentada e assinale a alternativa correta sobre crédito tributário e suspensão de exigibilidade.")
        self.assertEqual(infer_origin_type(q), "oficial")
        quality = calculate_quality(q)
        self.assertGreaterEqual(quality["score"], 88)
        self.assertEqual(quality["grade"], "A")
        self.assertEqual(quality["status"], "pronta")

    def test_similarity_control_flags_near_duplicate_without_auto_deleting(self) -> None:
        first = "À luz do CTN, assinale a alternativa correta a respeito das hipóteses de suspensão da exigibilidade do crédito tributário e seus efeitos."
        second = "À luz do CTN, assinale a alternativa correta sobre as hipóteses de suspensão da exigibilidade do crédito tributário e os seus efeitos."
        self.assertGreaterEqual(duplicate_similarity(first, second), 0.80)
        uid1 = self.import_question("Q1001", first)
        uid2 = self.import_question("Q1002", second)
        intelligence = self.db.refresh_question_intelligence(uid2, scan_duplicates=True)
        candidates = intelligence["duplicate_candidates"]
        self.assertTrue(any(item["uid"] == uid1 for item in candidates))
        with self.db.connect() as c:
            self.assertEqual(int(c.execute("SELECT COUNT(*) FROM questions").fetchone()[0]), 2)

    def test_empirical_difficulty_uses_attempt_accuracy_and_perception(self) -> None:
        result = empirical_difficulty(attempts=20, correct=8, hard_count=10)
        self.assertEqual(result["label"], "dificil")
        self.assertEqual(result["confidence"], "moderada")
        self.assertLess(result["accuracy"], 50)

    def test_database_refresh_reads_real_attempts_and_updates_summary(self) -> None:
        uid = self.import_question(
            "Q2001",
            "Em relação ao lançamento tributário, analise a situação apresentada e assinale a opção correta segundo o Código Tributário Nacional.",
        )
        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        with self.db.connect() as c:
            for index in range(10):
                attempt_id = str(uuid.uuid4())
                delivery_id = str(uuid.uuid4())
                poll_id = f"p-{index}"
                c.execute(
                    """INSERT INTO telegram_deliveries(id, cycle_id, question_uid, poll_id, chat_id, sent_at, status)
                       VALUES (?, 'teste', ?, ?, '1', ?, 'enviado')""",
                    (delivery_id, uid, poll_id, now),
                )
                c.execute(
                    """INSERT INTO telegram_attempts(id, delivery_id, question_uid, poll_id, user_id, selected_indices_json, is_correct, answered_at, perceived_difficulty)
                       VALUES (?, ?, ?, ?, '1', '[0]', ?, ?, ?)""",
                    (attempt_id, delivery_id, uid, poll_id, 1 if index < 4 else 0, now, "dificil" if index >= 4 else "media"),
                )
        intelligence = self.db.refresh_question_intelligence(uid, scan_duplicates=False)
        self.assertEqual(intelligence["attempts"]["attempts"], 10)
        self.assertEqual(intelligence["difficulty"]["label"], "dificil")
        summary = self.db.bank_intelligence_summary()
        self.assertEqual(summary["total"], 1)
        self.assertGreater(summary["average_quality"], 70)

    def test_web_interface_exposes_curation_ai_and_duplicate_controls(self) -> None:
        html = (BASE / "web" / "index.html").read_text(encoding="utf-8")
        js = (BASE / "web" / "app.js").read_text(encoding="utf-8")
        css = (BASE / "web" / "styles.css").read_text(encoding="utf-8")
        for token in ('data-route="curation"', 'data-page="curation"', 'id="questionIntelligencePanel"', 'id="assistCommentaryAi"'):
            self.assertIn(token, html)
        for token in ("loadBankIntelligence", "loadQuestionIntelligence", "assistCommentaryWithAi", "resolve_duplicate_candidate"):
            self.assertIn(token, js)
        for token in ("curation-layout", "intelligence-cards", "duplicate-candidate", "ai-draft-review"):
            self.assertIn(token, css)


if __name__ == "__main__":
    unittest.main()
