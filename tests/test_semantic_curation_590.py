from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from core.semantic_retrieval import hashed_embedding, cosine_similarity, semantic_duplicate_score
from core.storage import QuestFlowDatabase

BASE = Path(__file__).resolve().parents[1]


class SemanticCuration590Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="qf-sem590-")
        self.db = QuestFlowDatabase(Path(self.tmp.name) / "q.sqlite")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    @staticmethod
    def question(code: str, statement: str, *, subject: str = "DIREITO TRIBUTÁRIO", topic: str = "Crédito tributário") -> dict:
        return {
            "id": code,
            "codigo_origem": code,
            "fingerprint": hashlib.sha256((code + statement).encode("utf-8")).hexdigest(),
            "materia": subject,
            "aula_planilha": "Aula 01",
            "assunto": topic,
            "assuntos": [topic, "Suspensão da exigibilidade"],
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
            "explicacao": "O art. 151 do CTN disciplina hipóteses de suspensão da exigibilidade do crédito tributário.",
            "referencias_legais": ["CTN, art. 151"],
            "tags": ["CTN", "suspensão"],
            "fonte": {"arquivo": "prova_fgv_2026.pdf", "pagina_inicial": 10},
            "revisao": {"status": "aprovado", "confianca": 1.0, "alertas": []},
            "proveniencia": {"tipo": "oficial", "fonte_primaria": "prova_fgv_2026.pdf", "verificada": True},
            "comentario_meta": {"origem": "professor"},
        }

    def import_question(self, question: dict) -> str:
        result = self.db.import_extraction({"source_file": "prova.pdf", "questions": [question]})
        self.assertEqual(result["inserted"], 1)
        with self.db.connect() as connection:
            return str(connection.execute("SELECT uid FROM questions WHERE source_code = ?", (question["codigo_origem"],)).fetchone()[0])

    def test_local_semantic_vector_prefers_related_text(self) -> None:
        query = "suspensão da exigibilidade do crédito tributário conforme o CTN"
        related = "O Código Tributário Nacional prevê hipóteses que suspendem a exigibilidade do crédito tributário."
        unrelated = "A depreciação de máquinas integra a contabilidade de custos industriais."
        qv = hashed_embedding(query)
        self.assertGreater(cosine_similarity(qv, hashed_embedding(related)), cosine_similarity(qv, hashed_embedding(unrelated)))

    def test_hybrid_duplicate_detects_small_rewrite(self) -> None:
        left = self.question("Q1", "À luz do CTN, assinale a alternativa correta sobre as hipóteses de suspensão da exigibilidade do crédito tributário.")
        right = self.question("Q2", "Segundo o Código Tributário Nacional, indique a opção correta acerca das hipóteses que suspendem a exigibilidade do crédito tributário.")
        result = semantic_duplicate_score(left, right, lexical_similarity=0.72)
        self.assertGreaterEqual(result["score"], 0.70)
        self.assertEqual(result["method"], "hybrid_local_hashing")
        uid1 = self.import_question(left)
        uid2 = self.import_question(right)
        candidates = self.db.refresh_question_intelligence(uid2, scan_duplicates=True)["duplicate_candidates"]
        self.assertTrue(any(item["uid"] == uid1 and item["method"] == "hybrid_local_hashing" for item in candidates))

    def test_question_is_indexed_into_graph_and_hybrid_rag(self) -> None:
        uid = self.import_question(self.question(
            "Q5901",
            "A respeito da suspensão da exigibilidade do crédito tributário, assinale a alternativa correta conforme o CTN.",
        ))
        summary = self.db.semantic_index_summary()
        self.assertEqual(summary["indexed_questions"], 1)
        self.assertEqual(summary["coverage"], 100.0)
        self.assertGreaterEqual(summary["rag_chunks"], 2)
        self.assertGreater(summary["knowledge_nodes"], 2)

        graph = self.db.knowledge_graph_for_question(uid)
        labels = {item["label"] for item in graph["nodes"]}
        self.assertIn("DIREITO TRIBUTÁRIO", labels)
        self.assertIn("CTN, art. 151", labels)

        retrieval = self.db.retrieve_rag_context(uid, "artigo 151 CTN suspensão exigibilidade", limit=5)
        self.assertTrue(retrieval["items"])
        self.assertTrue(any("151" in item["content"] for item in retrieval["items"]))
        self.assertIn("semantic", retrieval["items"][0]["scores"])

    def test_update_reindexes_taxonomy_and_delete_removes_semantic_assets(self) -> None:
        uid = self.import_question(self.question(
            "Q5902",
            "Analise as hipóteses de suspensão da exigibilidade do crédito tributário previstas no CTN.",
        ))
        question = self.db.get_question(uid)
        assert question is not None
        question["assunto"] = "Lançamento tributário"
        question["assuntos"] = ["Lançamento tributário"]
        question["referencias_legais"] = ["CTN, art. 142"]
        question["explicacao"] = "O art. 142 do CTN trata da constituição do crédito pelo lançamento."
        self.db.update_question(uid, question)
        labels = {item["label"] for item in self.db.knowledge_graph_for_question(uid)["nodes"]}
        self.assertIn("Lançamento tributário", labels)
        self.assertIn("CTN, art. 142", labels)
        self.assertNotIn("CTN, art. 151", labels)

        self.db.delete_question(uid)
        with self.db.connect() as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM qf_semantic_signatures WHERE question_uid = ?", (uid,)).fetchone()[0], 0)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM qf_rag_chunks WHERE source_ref = ?", (uid,)).fetchone()[0], 0)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM qf_question_concepts WHERE question_uid = ?", (uid,)).fetchone()[0], 0)

    def test_web_interface_exposes_semantic_stage_controls(self) -> None:
        html = (BASE / "web" / "index.html").read_text(encoding="utf-8")
        js = (BASE / "web" / "app.js").read_text(encoding="utf-8")
        css = (BASE / "web" / "styles.css").read_text(encoding="utf-8")
        for token in ('id="semanticIndexOverview"', 'id="rebuildSemanticIndex"', 'id="showKnowledgeGraph"', 'id="showHybridEvidence"'):
            self.assertIn(token, html)
        for token in ("loadSemanticIndex", "showKnowledgeGraph", "showHybridEvidence", "start_semantic_rebuild"):
            self.assertIn(token, js)
        for token in ("semantic-index-summary", "hybrid-evidence-list", "knowledge-graph-view"):
            self.assertIn(token, css)


if __name__ == "__main__":
    unittest.main()
