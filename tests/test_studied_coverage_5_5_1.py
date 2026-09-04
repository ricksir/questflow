from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from core.spreadsheet_taxonomy import _duration_minutes, _performance_percent, _question_goal_from_description
from core.storage import QuestFlowDatabase
from core.study import StudyRepository


class StudiedCoverage551Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="questflow-studied-")
        self.db = QuestFlowDatabase(Path(self.temp.name) / "questions.sqlite")
        self.study = StudyRepository(self.db)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _add_question(self, subject: str, lesson: str, topic: str, reference: str = "") -> str:
        uid = self.db.create_manual_question(None)
        question = self.db.get_question(uid)
        assert question is not None
        question["materia"] = subject
        question["aula_planilha"] = lesson
        question["assunto"] = topic
        question["assuntos"] = [topic]
        question["enunciado"] = f"Questão sobre {topic}."
        question["alternativas"] = [
            {"chave": "A", "texto": "Certa"},
            {"chave": "B", "texto": "Errada"},
        ]
        question["gabarito"] = "A"
        question["classificacao_planilha"] = {
            "status": "classificado",
            "confianca": 1.0,
            "referencia": reference,
            "fonte": "teste",
        }
        question["revisao"] = {"status": "aprovado", "confianca": 1.0, "alertas": []}
        self.db.update_question(uid, question)
        return uid

    def test_duration_and_sheet_number_helpers_cover_google_xlsx_values(self) -> None:
        self.assertEqual(_duration_minutes(0.0625), 90)
        self.assertEqual(_duration_minutes("1:30"), 90)
        self.assertEqual(_performance_percent(0.8462, 13, 11), 84.62)
        self.assertEqual(_question_goal_from_description("e resolução de 21 questões do PDF da aula 00."), 21)

    def test_only_studied_tasks_are_reported_and_missing_count_is_exact(self) -> None:
        studied = {
            "row": 6,
            "trilha": "TRILHA 0",
            "tarefa": "3",
            "materia": "DIREITO TRIBUTÁRIO",
            "aula": "Aula 00",
            "descricao": "Estudo da Aula 00 – Parte 1 de 3. De noções introdutórias até espécies tributárias.",
            "segmentos": ["noções introdutórias", "espécies tributárias"],
            "ch_efetiva_min": 90,
            "ch_efetiva": "1h30",
            "questoes_feitas": 20,
            "acertos": 18,
            "desempenho": 90.0,
            "meta_questoes": 20,
            "meta_origem": "questoes_feitas",
            "estudado": True,
        }
        not_studied = {
            "row": 8,
            "trilha": "TRILHA 0",
            "tarefa": "5",
            "materia": "DIREITO ADMINISTRATIVO",
            "aula": "Aula 00",
            "descricao": "Regime Jurídico Administrativo até Princípios Expressos.",
            "segmentos": ["Regime Jurídico Administrativo", "Princípios Expressos"],
            "ch_efetiva_min": 0,
            "questoes_feitas": 0,
            "acertos": 0,
            "estudado": False,
        }
        for number in range(12):
            self._add_question(
                "DIREITO TRIBUTÁRIO",
                "Aula 00",
                f"ESPÉCIES TRIBUTÁRIAS {number}",
                studied["descricao"],
            )
        analysis = self.study.studied_content_coverage([studied, not_studied])
        self.assertEqual(len(analysis["items"]), 1)
        row = analysis["items"][0]
        self.assertEqual(row["bank_question_count"], 12)
        self.assertEqual(row["missing_question_count"], 8)
        self.assertEqual(row["status"], "cobertura_parcial")
        self.assertEqual(analysis["summary"]["known_missing_questions"], 8)
        self.assertEqual(analysis["summary"]["studied_subjects"], 1)

    def test_same_lesson_parts_do_not_double_count_questions(self) -> None:
        part1_description = "Estudo da Aula 00 – Parte 1 de 3. De noções introdutórias até espécies tributárias, exclusive."
        part2_description = "Estudo da Aula 00 – Parte 2 de 3. De espécies tributárias até empréstimos compulsórios, exclusive."
        tasks = [
            {
                "row": 6, "materia": "DIREITO TRIBUTÁRIO", "aula": "Aula 00", "descricao": part1_description,
                "segmentos": ["noções introdutórias", "espécies tributárias"], "estudado": True,
                "ch_efetiva_min": 90, "questoes_feitas": 2, "acertos": 2, "desempenho": 100,
                "meta_questoes": 2, "meta_origem": "questoes_feitas",
            },
            {
                "row": 9, "materia": "DIREITO TRIBUTÁRIO", "aula": "Aula 00", "descricao": part2_description,
                "segmentos": ["espécies tributárias", "empréstimos compulsórios"], "estudado": True,
                "ch_efetiva_min": 90, "questoes_feitas": 2, "acertos": 1, "desempenho": 50,
                "meta_questoes": 2, "meta_origem": "questoes_feitas",
            },
        ]
        self._add_question("DIREITO TRIBUTÁRIO", "Aula 00", "NOÇÕES INTRODUTÓRIAS", part1_description)
        self._add_question("DIREITO TRIBUTÁRIO", "Aula 00", "EMPRÉSTIMOS COMPULSÓRIOS", part2_description)
        rows = sorted(self.study.studied_content_coverage(tasks)["items"], key=lambda item: item["row"])
        self.assertEqual([row["bank_question_count"] for row in rows], [1, 1])
        self.assertEqual([row["missing_question_count"] for row in rows], [1, 1])

    def test_studied_content_without_numeric_goal_is_flagged_without_inventing_count(self) -> None:
        task = {
            "row": 12,
            "materia": "AUDITORIA",
            "aula": "Aula 00",
            "descricao": "Teoria da Aula 00 sobre princípios éticos.",
            "segmentos": ["princípios éticos"],
            "estudado": True,
            "ch_efetiva_min": 90,
            "questoes_feitas": 0,
            "acertos": 0,
            "desempenho": 0,
            "meta_questoes": 0,
            "meta_origem": "",
        }
        row = self.study.studied_content_coverage([task])["items"][0]
        self.assertEqual(row["status"], "sem_questoes")
        self.assertIsNone(row["missing_question_count"])
        self.assertFalse(row["missing_exact"])
        self.assertTrue(row["needs_attention"])


if __name__ == "__main__":
    unittest.main()
