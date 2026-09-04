from __future__ import annotations

import hashlib
import tempfile
import unittest
import uuid
from datetime import datetime, timezone
from pathlib import Path

from core.bank_intelligence import calculate_quality
from core.cloud_sync import CloudSyncEngine
from core.storage import QuestFlowDatabase
from core.study import StudyRepository
from tests.test_cloud_sync_5_4_0 import FakeRemote
from web_api import QuestFlowWebApi


class CurationReactive663Tests(unittest.TestCase):
    @staticmethod
    def question(code: str, *, explanation: str = "") -> dict:
        statement = "Considere a situação apresentada e assinale a alternativa correta segundo a legislação aplicável ao caso concreto."
        return {
            "id": code,
            "codigo_origem": code,
            "fingerprint": hashlib.sha256((code + statement).encode()).hexdigest(),
            "materia": "DIREITO TRIBUTÁRIO",
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
            "explicacao": explanation,
            "revisao": {"status": "aprovado", "confianca": 1.0, "alertas": []},
            "proveniencia": {"tipo": "oficial", "fonte_primaria": "Prova oficial CEBRASPE 2026", "verificada": True},
            "origem_questao": "oficial",
            "comentario_meta": {"origem": "manual_nao_classificado" if explanation else "sem_comentario"},
        }

    def test_primary_source_edited_in_ui_counts_as_traceable(self):
        q = self.question("Q663-SOURCE", explanation="Comentário completo e revisado.")
        # Não há fonte.arquivo; só a referência que o editor realmente expõe.
        self.assertNotIn("fonte", q)
        quality = calculate_quality(q)
        check = next(item for item in quality["checks"] if item["label"] == "Fonte rastreável")
        self.assertTrue(check["ok"])
        self.assertEqual(quality["status"], "pronta")

    def test_explanation_cannot_remain_sem_comentario_after_save_merge(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            api = QuestFlowWebApi(root / "q.sqlite", config={}, config_path=root / "config.json", taxonomy_path=root / "missing-taxonomy.json")
            current = self.question("Q663-COMMENT", explanation="")
            current["database_uid"] = "demo"
            payload = {
                "codigo_origem": current["codigo_origem"],
                "materia": current["materia"], "aula_planilha": current["aula_planilha"],
                "assunto": current["assunto"], "assuntos": current["assuntos"],
                "banca": current["banca"], "ano": current["ano"], "orgao": current["orgao"], "prova": current["prova"],
                "tipo": current["tipo"], "gabarito": current["gabarito"], "enunciado": current["enunciado"],
                "alternativas": current["alternativas"], "origem_questao": "oficial",
                "fonte_primaria": "Prova oficial CEBRASPE 2026", "origem_verificada": True,
                "explicacao": "Nova explicação escrita pelo usuário.",
                "origem_comentario": "sem_comentario",
            }
            merged = api._merge_question(current, payload, approve=True)
            self.assertEqual(merged["comentario_meta"]["origem"], "manual_nao_classificado")
            self.assertEqual(calculate_quality(merged)["status"], "pronta")

    def test_full_refresh_repairs_stale_editorial_and_difficulty_without_cloud_noise(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            db = QuestFlowDatabase(root / "q.sqlite")
            study = StudyRepository(db)
            result = db.import_extraction({"source_file": "prova.pdf", "questions": [self.question("Q663-REFRESH", explanation="Comentário completo.")]})
            self.assertEqual(result["inserted"], 1)
            with db.connect() as c:
                uid = str(c.execute("SELECT uid FROM questions WHERE source_code='Q663-REFRESH'").fetchone()[0])
            cloud = CloudSyncEngine(db.path, config={"cloud_sync_enabled": True}, config_path=root / "config.json", remote_client=FakeRemote(), auth_token="unit")
            self.assertTrue(cloud.sync_until_idle()["ok"])
            self.assertEqual(cloud.pending_count(), 0)

            now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
            with db.connect() as c:
                # Simula colunas derivadas de versão antiga que ficaram congeladas.
                c.execute("UPDATE qf_sync_runtime SET value='1' WHERE key='suppress'")
                c.execute("UPDATE questions SET curation_status='revisar', quality_score=74, commentary_source='sem_comentario', difficulty_score=NULL, difficulty_label=NULL WHERE uid=?", (uid,))
                for i in range(4):
                    delivery = str(uuid.uuid4())
                    poll_id = f"p-{i}"
                    c.execute("INSERT INTO telegram_deliveries(id,cycle_id,question_uid,poll_id,chat_id,sent_at,status) VALUES(?,?,?,?,?,?,?)", (delivery,"t",uid,poll_id,"1",now,"enviado"))
                    c.execute("INSERT INTO telegram_attempts(id,delivery_id,question_uid,poll_id,user_id,selected_indices_json,is_correct,answered_at,perceived_difficulty) VALUES(?,?,?,?,?,?,?,?,?)", (str(uuid.uuid4()), delivery, uid, poll_id, "1", "[0]", 1 if i < 3 else 0, now, "facil"))
                c.execute("UPDATE qf_sync_runtime SET value='0' WHERE key='suppress'")
            self.assertTrue(cloud.sync_until_idle(max_rounds=10)["ok"])
            self.assertEqual(cloud.pending_count(), 0)

            refreshed = db.rebuild_bank_intelligence_derived()
            self.assertTrue(refreshed["ok"])
            self.assertGreaterEqual(refreshed["updated"], 1)
            self.assertEqual(refreshed["summary"]["needs_review"], 0)
            self.assertEqual(refreshed["summary"]["with_commentary"], 1)
            self.assertEqual(refreshed["summary"]["difficulty"].get("facil"), 1)
            self.assertEqual(cloud.pending_count(), 0, cloud.pending_details())
            # Abrir a inteligência de uma questão também é uma leitura derivada.
            db.refresh_question_intelligence(uid, scan_duplicates=False)
            self.assertEqual(cloud.pending_count(), 0, cloud.pending_details())

    def test_attention_queue_returns_exact_missing_checks(self):
        with tempfile.TemporaryDirectory() as temp:
            db = QuestFlowDatabase(Path(temp) / "q.sqlite")
            q = self.question("Q663-ATTN", explanation="")
            q["proveniencia"].pop("fonte_primaria", None)
            q["revisao"]["status"] = "pendente"
            db.import_extraction({"source_file": "", "questions": [q]})
            db.rebuild_bank_intelligence_derived()
            queue = db.bank_intelligence_attention("curation", limit=10)
            self.assertEqual(queue["total"], 1)
            self.assertTrue(queue["items"])
            missing = queue["items"][0]["missing"]
            self.assertIn("Comentário disponível", missing)
            self.assertIn("Curadoria aprovada", missing)
            comments = db.bank_intelligence_attention("comments", limit=10)
            self.assertEqual(comments["total"], 1)


if __name__ == "__main__":
    unittest.main()
