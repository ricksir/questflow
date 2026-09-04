from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from core.engines import EngineRegistry
from core.question_services import QuestionCommandService, QuestionQueryService
from core.storage import QuestFlowDatabase
from core.study import StudyRepository

ROOT = Path(__file__).resolve().parents[1]


class TutorQuestionSelector6161Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="qf-tutor-selector-")
        self.db = QuestFlowDatabase(Path(self.tmp.name) / "q.sqlite")
        self.study = StudyRepository(self.db)
        self.queries = QuestionQueryService(self.db)
        self.commands = QuestionCommandService(self.db)
        self.engines = EngineRegistry.build(
            database=self.db,
            queries=self.queries,
            commands=self.commands,
            study=self.study,
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _make_question(self) -> str:
        uid = self.db.create_manual_question(None)
        question = self.db.get_question(uid)
        assert question is not None
        question.update(
            {
                "codigo_origem": "Q2015460",
                "materia": "AUDITORIA",
                "aula_planilha": "Aula 07",
                "assunto": "AUDITORIA INTERNA - TÓPICOS COMPLEMENTARES",
                "enunciado": "Considerando as normas brasileiras para o exercício da auditoria interna, assinale a opção incorreta.",
                "alternativas": [
                    {"chave": "A", "texto": "Alternativa de teste."},
                    {"chave": "B", "texto": "Outra alternativa de teste."},
                ],
                "gabarito": "B",
                "revisao": {"status": "aprovado", "confianca": 1.0, "alertas": []},
            }
        )
        self.db.update_question(uid, question)
        self.study.sync_questions()
        return uid

    def test_workspace_candidates_have_human_fields_and_keep_uid_internal(self) -> None:
        uid = self._make_question()
        workspace = self.engines.ai.workspace(uid)
        candidate = next(item for item in workspace["candidates"] if item["uid"] == uid)
        self.assertEqual(candidate["code"], "Q2015460")
        self.assertEqual(candidate["subject"], "AUDITORIA")
        self.assertEqual(candidate["topic"], "AUDITORIA INTERNA - TÓPICOS COMPLEMENTARES")
        self.assertEqual(candidate["lesson"], "Aula 07")
        self.assertTrue(candidate["statement"].startswith("Considerando as normas brasileiras"))
        self.assertNotEqual(candidate["code"], uid)

    def test_web_selector_explains_purpose_and_never_falls_back_to_uid_as_label(self) -> None:
        html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
        js = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        self.assertIn("Qual questão você quer entender?", html)
        self.assertIn('id="tutorQuestionSearch"', html)
        self.assertIn("código, matéria, assunto, aula ou trecho do enunciado", html)
        self.assertIn("function tutorCandidateLabel", js)
        self.assertIn("Questão sem código visível", js)
        self.assertNotIn("item.code||item.codigo||item.uid||'Questão'", js)
        self.assertIn("tutorLooksLikeUuid", js)


if __name__ == "__main__":
    unittest.main()
