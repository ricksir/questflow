from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from core.engines import EngineRegistry
from core.question_services import QuestionCommandService, QuestionQueryService
from core.schema_migrations import migration_history
from core.storage import QuestFlowDatabase
from core.study import StudyRepository
from web_server import ALLOWED_API_METHODS

ROOT = Path(__file__).resolve().parents[1]


class TutorEditableDrafts6171Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="qf-tutor6171-")
        self.db = QuestFlowDatabase(Path(self.tmp.name) / "questflow.sqlite")
        self.study = StudyRepository(self.db)
        self.queries = QuestionQueryService(self.db)
        self.commands = QuestionCommandService(self.db)
        self.engines = EngineRegistry.build(
            database=self.db, queries=self.queries, commands=self.commands, study=self.study
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def make_question(self, code: str = "Q6171") -> str:
        uid = self.db.create_manual_question(None)
        q = self.db.get_question(uid); assert q
        q.update({
            "codigo_origem": code, "id": code,
            "materia": "CONTABILIDADE GERAL E AVANÇADA",
            "assunto": "Estrutura Conceitual",
            "aula_planilha": "Aula 04",
            "enunciado": "A representação fidedigna deve refletir a essência econômica do fenômeno.",
            "alternativas": [
                {"chave": "A", "texto": "A essência econômica prevalece quando difere da forma legal."},
                {"chave": "B", "texto": "A forma legal isolada sempre define a representação fidedigna."},
            ],
            "gabarito": "A",
            "explicacao": "A informação contábil deve representar a essência do fenômeno econômico.",
            "revisao": {"status": "aprovado", "confianca": 1.0, "alertas": []},
        })
        self.db.update_question(uid, q)
        self.study.sync_questions()
        return uid

    def record_tutor(self, uid: str, text: str = "Gabarito: A. Fundamentação original da IA.") -> str:
        iid = self.engines.governance.record_interaction(
            question_uid=uid, interaction_type="tutor", mode="professor",
            provider="QuestFlow Grounded Composer", model="qf-tutor-grounded-2",
            prompt_text="prompt atual", response_text=text, learner_context={},
            sources=[{"title": "Comentário", "provider": "Banco Editorial", "content": "A essência econômica é a referência da representação fidedigna."}],
            diagnosis={"label": "Desatenção", "intervention": "Revisar."},
        )
        self.engines.governance.evaluate(
            iid, response_text=text, mode="professor", official_answer="A",
            source_texts=["A essência econômica é a referência da representação fidedigna."],
            diagnosis={"intervention": "Revisar."},
            sources=[{"title": "Comentário", "provider": "Banco Editorial", "content": "A essência econômica é a referência da representação fidedigna."}],
        )
        return iid

    def test_migration_adds_edit_and_question_snapshot_columns(self) -> None:
        with self.db.connect() as conn:
            cols = {row[1] for row in conn.execute("PRAGMA table_info(qf_ai_interactions)").fetchall()}
            tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
            versions = [int(row["version"]) for row in migration_history(conn) if row["component"] == "ai_governance"]
        self.assertTrue({
            "edited_response_text", "edited_at", "question_snapshot_sha256", "question_snapshot_json", "question_updated_at",
            "question_snapshot_origin", "question_snapshot_captured_at",
        }.issubset(cols))
        self.assertIn("qf_ai_response_revisions", tables)
        self.assertIn(5, versions)
        self.assertIn(6, versions)

    def test_legacy_interactions_receive_content_baseline_without_timestamp_false_positive(self) -> None:
        uid = self.make_question("Q6171-LEGACY")
        iid = self.record_tutor(uid, "Gabarito: A. Orientação criada antes do snapshot histórico.")

        # Simula uma interação anterior à 6.17.1: sem hash/snapshot. Depois dela,
        # uma manutenção técnica toca updated_at sem mudar qualquer conteúdo que
        # o Tutor utiliza pedagogicamente.
        q = self.db.get_question(uid); assert q
        q["observacao_tecnica_6171"] = "reindexação sem mudança pedagógica"
        self.db.update_question(uid, q)
        with self.db.connect() as conn:
            conn.execute(
                """UPDATE qf_ai_interactions
                   SET question_snapshot_sha256='',question_snapshot_json='{}',question_snapshot_origin='generation',
                       question_snapshot_captured_at=NULL,question_updated_at=created_at
                   WHERE id=?""",
                (iid,),
            )
            conn.execute("DELETE FROM schema_migrations WHERE component='ai_governance' AND version=6")

        self.engines.governance.initialize()
        migrated = self.engines.governance.interaction(iid)
        self.assertFalse(migrated["question_changed"])
        self.assertEqual(migrated["question_snapshot_origin"], "legacy_upgrade_baseline_6171")
        self.assertTrue(migrated["question_snapshot_sha256"])
        self.assertIn("representação fidedigna", migrated["question_snapshot"]["enunciado"])

        audit_item = next(item for item in self.engines.governance.recent_audit(limit=20) if item["id"] == iid)
        self.assertFalse(audit_item["question_changed"])

        # A partir do baseline, uma alteração pedagógica real deve ser detectada.
        q2 = self.db.get_question(uid); assert q2
        q2["enunciado"] = "CONTEÚDO REALMENTE ALTERADO após a migração 6.17.1."
        self.db.update_question(uid, q2)
        self.assertTrue(self.engines.governance.interaction(iid)["question_changed"])
        audit_item2 = next(item for item in self.engines.governance.recent_audit(limit=20) if item["id"] == iid)
        self.assertTrue(audit_item2["question_changed"])

    def test_question_edit_marks_old_tutor_draft_stale_without_overwriting_history(self) -> None:
        uid = self.make_question("Q6171-STALE")
        iid = self.record_tutor(uid)
        before = self.engines.governance.interaction(iid)
        self.assertFalse(before["question_changed"])
        self.assertIn("representação fidedigna", before["question_snapshot"]["enunciado"])

        q = self.db.get_question(uid); assert q
        q["enunciado"] = "TEXTO CORRIGIDO: a representação fidedigna retrata a essência econômica, não apenas a forma legal."
        q["explicacao"] = "COMENTÁRIO CORRIGIDO pelo usuário em Revisar banco."
        self.db.update_question(uid, q)

        after = self.engines.governance.interaction(iid)
        self.assertTrue(after["question_changed"])
        self.assertIn("TEXTO CORRIGIDO", after["current_question"]["enunciado"])
        self.assertNotIn("TEXTO CORRIGIDO", after["question_snapshot"]["enunciado"])
        self.assertEqual(after["response_text"], "Gabarito: A. Fundamentação original da IA.")
        with self.assertRaisesRegex(ValueError, "questão foi alterada"):
            self.engines.governance.review_interaction(iid, decision="aprovar", note="Não deveria aprovar.")

    def test_human_can_edit_tutor_text_original_ai_is_immutable_and_revision_is_audited(self) -> None:
        uid = self.make_question("Q6171-EDIT")
        iid = self.record_tutor(uid)
        original = self.engines.governance.interaction(iid)["response_text"]
        self.engines.governance.review_interaction(iid, decision="aprovar", note="Primeira revisão.")
        edited = self.engines.governance.edit_interaction_response(
            iid, response_text="Gabarito: A. Texto corrigido manualmente pelo usuário.", note="Ajuste didático."
        )
        self.assertEqual(edited["response_text"], original)
        self.assertEqual(edited["display_response_text"], "Gabarito: A. Texto corrigido manualmente pelo usuário.")
        self.assertTrue(edited["has_human_edit"])
        self.assertEqual(edited["status"], "rascunho")
        self.assertEqual(len(edited["revisions"]), 1)
        self.assertEqual(edited["revisions"][0]["response_text"], edited["display_response_text"])

    def test_workspace_returns_latest_tutor_interaction_for_selected_question(self) -> None:
        uid = self.make_question("Q6171-WORKSPACE")
        iid = self.record_tutor(uid, "Gabarito: A. Rascunho recuperável.")
        workspace = self.engines.ai.workspace(uid)
        self.assertEqual(workspace["selected"]["uid"], uid)
        self.assertEqual(workspace["latest_interaction"]["id"], iid)
        self.assertEqual(workspace["latest_interaction"]["display_response_text"], "Gabarito: A. Rascunho recuperável.")

    def test_web_ui_exposes_edit_save_and_stale_regeneration_flow(self) -> None:
        self.assertIn("save_ai_interaction_text", ALLOWED_API_METHODS)
        js = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        css = (ROOT / "web" / "styles.css").read_text(encoding="utf-8")
        for marker in (
            'id="tutorDraftEditor"', "saveTutorDraftText", "data-tutor-save-draft",
            "data-tutor-regenerate", "A questão foi alterada em Revisar banco",
            "texto original da IA", "save_ai_interaction_text",
            "Orientação criada antes do versionamento de questões do Tutor",
        ):
            self.assertIn(marker, js)
        self.assertIn(".tutor-draft-editor", css)
        self.assertIn(".tutor-stale-warning", css)


if __name__ == "__main__":
    unittest.main()
