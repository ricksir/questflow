from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from core.telegram import telegram_payload
from web_api import QuestFlowWebApi


class GroupedCoverageAndQuestionType556Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="questflow-556-")
        self.root = Path(self.temp.name)
        self.api = QuestFlowWebApi(
            self.root / "questions.sqlite",
            config={},
            config_path=self.root / "config.json",
            taxonomy_path=self.root / "taxonomy.json",
        )
        self.api._ensure_core()
        self.tasks = [
            {
                "row": 10,
                "trilha": "TRILHA 2",
                "tarefa": "60",
                "materia": "AUDITORIA",
                "aula": "Aula 02",
                "descricao": "Teoria da Aula 02 – Parte 1.",
                "segmentos": ["Auditoria interna"],
                "estudado": True,
                "ch_efetiva_min": 90,
                "ch_efetiva": "1:30",
                "questoes_feitas": 10,
                "acertos": 8,
                "meta_questoes": 10,
            },
            {
                "row": 11,
                "trilha": "TRILHA 2",
                "tarefa": "61",
                "materia": "AUDITORIA",
                "aula": "Aula 02",
                "descricao": "Teoria da Aula 02 – Parte 2.",
                "segmentos": ["Controles internos"],
                "estudado": True,
                "ch_efetiva_min": 60,
                "ch_efetiva": "1:00",
                "questoes_feitas": 20,
                "acertos": 15,
                "meta_questoes": 20,
            },
            {
                "row": 12,
                "trilha": "TRILHA 2",
                "tarefa": "62",
                "materia": "AUDITORIA",
                "aula": "Aula 02",
                "descricao": "Resolução de questões do PDF da Aula 02.",
                "segmentos": ["Questões da Aula 02"],
                "estudado": True,
                "ch_efetiva_min": 30,
                "ch_efetiva": "0:30",
                "questoes_feitas": 5,
                "acertos": 4,
                "meta_questoes": 5,
            },
        ]
        self.api.taxonomy = SimpleNamespace(
            tasks=self.tasks,
            materias=["AUDITORIA"],
            source_name="Planilha de Controle",
            payload={"source": {"title": "Planilha de Controle"}, "generated_at": ""},
        )

    def tearDown(self) -> None:
        self.api.shutdown()
        self.temp.cleanup()

    def test_same_trail_subject_and_lesson_are_one_group(self) -> None:
        assert self.api.study is not None
        grouped = self.api.study.studied_lesson_group_coverage(self.tasks)
        self.assertEqual(len(grouped["items"]), 1)
        row = grouped["items"][0]
        self.assertEqual(row["task_count"], 3)
        self.assertEqual(row["questions_done"], 35)
        self.assertEqual(row["correct_answers"], 27)
        self.assertEqual(row["effective_minutes"], 180)
        self.assertEqual(row["effective_time"], "3h")
        self.assertEqual(row["missing_question_count"], 35)
        self.assertEqual(len(row["task_ids"]), 3)
        self.assertIn("3 conteúdos estudados nesta aula", row["content"])

    def test_group_context_is_authoritative_and_counts_once(self) -> None:
        assert self.api.study is not None and self.api.commands is not None and self.api.queries is not None
        grouped = self.api.study.studied_lesson_group_coverage(self.tasks)["items"][0]
        resolved = self.api._resolve_study_import_context({"group_id": grouped["group_id"]})
        self.assertEqual(resolved["materia"], "AUDITORIA")
        self.assertEqual(resolved["aula"], "Aula 02")
        self.assertEqual(len(resolved["task_ids"]), 3)

        extraction = {
            "questions": [
                {
                    "codigo_origem": "Q-556-GROUP",
                    "materia": "MATÉRIA ERRADA",
                    "aula_planilha": "Aula 99",
                    "assunto": "Assunto detectado no PDF",
                    "assuntos": ["Assunto detectado no PDF"],
                    "enunciado": "Questão agrupada.",
                    "alternativas": [{"chave": "A", "texto": "A"}, {"chave": "B", "texto": "B"}],
                    "gabarito": "A",
                    "tipo": "multipla_escolha",
                }
            ]
        }
        applied = self.api._apply_study_import_context(extraction, resolved)
        q = applied["questions"][0]
        self.assertEqual(q["materia"], "AUDITORIA")
        self.assertEqual(q["aula_planilha"], "Aula 02")
        self.assertEqual(q["classificacao_planilha"]["contexto_group_id"], grouped["group_id"])
        self.assertNotIn("referencia", q["classificacao_planilha"])
        self.assertEqual(q["contexto_importacao_estudos"]["task_ids"], grouped["task_ids"])

        imported = self.api.commands.import_extraction(applied)
        self.assertEqual(imported["inserted"], 1)
        refreshed = self.api.study.studied_lesson_group_coverage(self.tasks)["items"][0]
        self.assertEqual(refreshed["bank_question_count"], 1)
        self.assertEqual(refreshed["missing_question_count"], 34)

    def test_switching_to_true_false_persists_only_certo_errado_options(self) -> None:
        assert self.api.commands is not None and self.api.queries is not None
        uid = self.api.commands.create_manual(None)
        current = self.api.queries.get(uid)
        assert current is not None
        current.update(
            {
                "codigo_origem": "Q-556-TF",
                "enunciado": "Julgue o item.",
                "tipo": "multipla_escolha",
                "alternativas": [
                    {"chave": "A", "texto": "Primeira"},
                    {"chave": "B", "texto": "Segunda"},
                    {"chave": "C", "texto": "Terceira"},
                ],
                "gabarito": "A",
            }
        )
        self.api.commands.update(uid, current)
        result = self.api.save_question(uid, {"tipo": "certo_errado", "gabarito": ""}, False)
        self.assertTrue(result["ok"], result.get("error"))
        saved = result["question"]
        self.assertEqual(saved["tipo"], "certo_errado")
        self.assertEqual(saved["alternativas"], [{"chave": "C", "texto": "Certo"}, {"chave": "E", "texto": "Errado"}])
        self.assertEqual(saved["gabarito"], "")
        self.assertTrue(saved.get("historico_formato"))

    def test_legacy_true_false_with_a_to_e_is_normalized_on_open_and_telegram(self) -> None:
        assert self.api.commands is not None and self.api.queries is not None
        uid = self.api.commands.create_manual(None)
        current = self.api.queries.get(uid)
        assert current is not None
        current.update(
            {
                "codigo_origem": "Q-556-LEGACY",
                "enunciado": "O item está correto.",
                "tipo": "certo_errado",
                "alternativas": [
                    {"chave": "A", "texto": "A"}, {"chave": "B", "texto": "B"},
                    {"chave": "C", "texto": "C"}, {"chave": "D", "texto": "D"},
                    {"chave": "E", "texto": "E"},
                ],
                "gabarito": "C",
            }
        )
        self.api.commands.update(uid, current)
        opened = self.api.get_question(uid)["question"]
        self.assertEqual(opened["alternativas"], [{"chave": "C", "texto": "Certo"}, {"chave": "E", "texto": "Errado"}])
        payload = telegram_payload(current, "123")
        self.assertIn('"text": "C) Certo"', payload["options"])
        self.assertIn('"text": "E) Errado"', payload["options"])
        self.assertNotIn('"text": "A)', payload["options"])

    def test_web_ui_changes_layout_immediately_and_uses_group_rows(self) -> None:
        web_root = Path(__file__).resolve().parents[1] / "web"
        html = (web_root / "index.html").read_text(encoding="utf-8")
        js = (web_root / "app.js").read_text(encoding="utf-8")
        self.assertIn('id="alternativesSubtitle"', html)
        self.assertIn("handleQuestionTypeChange", js)
        self.assertIn("trueFalseOptionsClient", js)
        self.assertIn("alternative-row--locked", js)
        self.assertIn("study-group-id", js)
        self.assertIn("group_id: item.group_id", js)
        self.assertIn("partes da mesma aula", js)


if __name__ == "__main__":
    unittest.main()
