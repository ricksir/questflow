from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from core.storage import QuestFlowDatabase
from web_api import QuestFlowWebApi


class BankCorrection555Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="questflow-bank-fix-")
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
                "row": 31,
                "trilha": "TRILHA 1",
                "tarefa": "26",
                "materia": "FLUÊNCIA EM DADOS",
                "aula": "Aula 01",
                "descricao": "Teoria da Aula 01 – Parte 1 de 3. De Conceitos Básicos até Tipos de Operadores.",
                "segmentos": ["Conceitos Básicos", "Tipos de Operadores"],
                "estudado": True,
                "ch_efetiva_min": 90,
                "questoes_feitas": 20,
                "acertos": 14,
                "meta_questoes": 20,
            },
            {
                "row": 85,
                "trilha": "TRILHA 2",
                "tarefa": "80",
                "materia": "AUDITORIA",
                "aula": "Aula 02",
                "descricao": "Teoria da Aula 02 – Parte 1 de 1 – Auditoria Interna.",
                "segmentos": ["Auditoria Interna"],
                "estudado": True,
                "ch_efetiva_min": 90,
                "questoes_feitas": 30,
                "acertos": 25,
                "meta_questoes": 30,
            },
        ]
        self.api.taxonomy = SimpleNamespace(
            tasks=self.tasks,
            materias=["AUDITORIA", "FLUÊNCIA EM DADOS"],
            source_name="Planilha de Controle",
        )

    def tearDown(self) -> None:
        self.api.shutdown()
        self.temp.cleanup()

    def _question(self, subject="AUDITORIA", lesson="Aula 02") -> str:
        assert self.api.commands is not None and self.api.queries is not None
        uid = self.api.commands.create_manual(None)
        question = self.api.queries.get(uid)
        assert question is not None
        question.update(
            {
                "materia": subject,
                "aula_planilha": lesson,
                "assunto": "Auditoria Interna",
                "assuntos": ["Auditoria Interna"],
                "enunciado": "Questão para teste da correção do banco.",
                "alternativas": [{"chave": "A", "texto": "A"}, {"chave": "B", "texto": "B"}],
                "gabarito": "A",
                "classificacao_planilha": {
                    "status": "classificado",
                    "confianca": 1.0,
                    "referencia": self.tasks[1]["descricao"],
                    "contexto_task_id": "TRILHA 2:85",
                },
                "contexto_importacao_estudos": {"task_id": "TRILHA 2:85", "materia": subject, "aula": lesson},
            }
        )
        self.api.commands.update(uid, question)
        return uid

    def test_sql_filters_questions_by_subject_and_lesson(self) -> None:
        uid_a = self._question("AUDITORIA", "Aula 02")
        uid_b = self._question("FLUÊNCIA EM DADOS", "Aula 01")
        result = self.api.list_questions("", "todos", 0, 2000, "FLUÊNCIA EM DADOS", "Aula 01")
        self.assertEqual(result["total"], 1)
        self.assertEqual(result["items"][0]["uid"], uid_b)
        self.assertNotEqual(result["items"][0]["uid"], uid_a)

    def test_exact_task_correction_moves_question_and_coverage(self) -> None:
        uid = self._question()
        result = self.api.update_question_classification(
            uid,
            {"materia": "FLUÊNCIA EM DADOS", "aula": "Aula 01", "task_id": "TRILHA 1:31"},
        )
        self.assertTrue(result["ok"])
        assert self.api.queries is not None and self.api.study is not None
        saved = self.api.queries.get(uid)
        assert saved is not None
        self.assertEqual(saved["materia"], "FLUÊNCIA EM DADOS")
        self.assertEqual(saved["aula_planilha"], "Aula 01")
        self.assertEqual(saved["classificacao_planilha"]["referencia"], self.tasks[0]["descricao"])
        self.assertEqual(saved["classificacao_planilha"]["contexto_task_id"], "TRILHA 1:31")
        self.assertEqual(saved["contexto_importacao_estudos"]["task_id"], "TRILHA 1:31")
        coverage = self.api.study.studied_content_coverage(self.tasks)["items"]
        by_task = {row["task_id"]: row for row in coverage}
        self.assertEqual(by_task["TRILHA 1:31"]["bank_question_count"], 1)
        self.assertEqual(by_task["TRILHA 2:85"]["bank_question_count"], 0)
        self.assertEqual(result["coverage_assignment"]["task_id"], "TRILHA 1:31")

    def test_exact_task_correction_is_available_in_studio_v1(self) -> None:
        uid = self._question()
        result = self.api.dispatch_studio_v1(
            "questions.classification.update",
            {
                "uid": uid,
                "classification": {
                    "materia": "FLUÊNCIA EM DADOS",
                    "aula": "Aula 01",
                    "task_id": "TRILHA 1:31",
                },
            },
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["operation"], "questions.classification.update")
        self.assertEqual(result["module"], "editorial_bank")
        self.assertEqual(result["data"]["coverage_assignment"]["task_id"], "TRILHA 1:31")

        assert self.api.queries is not None
        saved = self.api.queries.get(uid)
        assert saved is not None
        self.assertEqual(saved["materia"], "FLUÊNCIA EM DADOS")
        self.assertEqual(saved["aula_planilha"], "Aula 01")
        self.assertEqual(saved["classificacao_planilha"]["contexto_task_id"], "TRILHA 1:31")
        self.assertEqual(saved["contexto_importacao_estudos"]["task_id"], "TRILHA 1:31")

    def test_manual_subject_lesson_change_drops_stale_exact_reference(self) -> None:
        uid = self._question()
        result = self.api.update_question_classification(
            uid,
            {"materia": "FLUÊNCIA EM DADOS", "aula": "Aula 01", "task_id": ""},
        )
        self.assertTrue(result["ok"])
        assert self.api.queries is not None
        saved = self.api.queries.get(uid)
        assert saved is not None
        self.assertNotIn("referencia", saved["classificacao_planilha"])
        self.assertNotIn("contexto_task_id", saved["classificacao_planilha"])
        self.assertNotIn("contexto_importacao_estudos", saved)
        self.assertTrue(saved.get("historico_classificacao"))

    def test_full_editor_change_also_clears_stale_context(self) -> None:
        uid = self._question()
        assert self.api.queries is not None
        current = self.api.queries.get(uid)
        assert current is not None
        payload = {
            "codigo_origem": current["codigo_origem"],
            "materia": "FLUÊNCIA EM DADOS",
            "aula_planilha": "Aula 01",
            "assunto": current.get("assunto", ""),
            "assuntos": current.get("assuntos", []),
            "alternativas": current.get("alternativas", []),
            "gabarito": current.get("gabarito", ""),
            "enunciado": current.get("enunciado", ""),
        }
        merged = self.api._merge_question(current, payload, approve=False)
        self.assertNotIn("referencia", merged["classificacao_planilha"])
        self.assertNotIn("contexto_task_id", merged["classificacao_planilha"])
        self.assertNotIn("contexto_importacao_estudos", merged)

    def test_organize_lesson_group_updates_all_variants_and_preserves_topics(self) -> None:
        uid_a = self._question("DIREITO TRIBUTÁRIO", "Aula 0")
        uid_b = self._question("DIREITO TRIBUTÁRIO", "Aula 00")
        uid_c = self._question("DIREITO TRIBUTÁRIO", "Aula 01")
        assert self.api.queries is not None and self.api.commands is not None
        second = self.api.queries.get(uid_b)
        assert second is not None
        second["assunto"] = "Conceito de tributos"
        second["assuntos"] = ["Conceito de tributos"]
        self.api.commands.update(uid_b, second)

        result = self.api.dispatch_studio_v1(
            "taxonomy.lesson_group.organize",
            {
                "source_matter": "Direito Tributário",
                "source_lesson": "00",
                "materia": "DIREITO TRIBUTÁRIO",
                "aula": "Aula 00",
                "titulo_aula": "CONCEITO DE TRIBUTOS",
            },
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["operation"], "taxonomy.lesson_group.organize")
        self.assertEqual(result["module"], "editorial_bank")
        self.assertEqual(result["data"]["group"]["updated"], 2)
        saved_a = self.api.queries.get(uid_a)
        saved_b = self.api.queries.get(uid_b)
        saved_c = self.api.queries.get(uid_c)
        assert saved_a is not None and saved_b is not None and saved_c is not None
        self.assertEqual(saved_a["aula_planilha"], "Aula 00")
        self.assertEqual(saved_b["titulo_aula"], "CONCEITO DE TRIBUTOS")
        self.assertEqual(saved_b["assunto"], "Conceito de tributos")
        self.assertNotIn("titulo_aula", saved_c)

    def test_lesson_catalog_is_applied_to_future_imports(self) -> None:
        uid = self._question("DIREITO TRIBUTÁRIO", "Aula 00")
        organized = self.api.organize_bank_lesson_group(
            {
                "source_matter": "DIREITO TRIBUTÁRIO",
                "source_lesson": "Aula 00",
                "materia": "DIREITO TRIBUTÁRIO",
                "aula": "Aula 00",
                "titulo_aula": "CONCEITO DE TRIBUTOS",
            }
        )
        self.assertTrue(organized["ok"])
        assert self.api.queries is not None and self.api.commands is not None
        future = copy.deepcopy(self.api.queries.get(uid))
        assert future is not None
        future.pop("database_uid", None)
        future["codigo_origem"] = "QFUTURE001"
        future["id"] = "QFUTURE001"
        future["fingerprint"] = "future-import-lesson-catalog-001"
        future["titulo_aula"] = ""
        future["classificacao_planilha"].pop("titulo_aula", None)
        future["fonte"] = {"arquivo": "future.pdf", "pagina_inicial": 1}
        imported = self.api.commands.import_extraction(
            {"source_file": "future.pdf", "questions": [future], "schema": "test.future.v1"}
        )
        self.assertEqual(imported["inserted"], 1)
        saved = self.api.queries.by_code("QFUTURE001")
        assert saved is not None
        self.assertEqual(saved["titulo_aula"], "CONCEITO DE TRIBUTOS")
        self.assertEqual(saved["classificacao_planilha"]["titulo_aula"], "CONCEITO DE TRIBUTOS")

    def test_ui_has_dedicated_bank_correction_workspace(self) -> None:
        web_root = Path(__file__).resolve().parents[1] / "web"
        html = (web_root / "index.html").read_text(encoding="utf-8")
        js = (web_root / "app.js").read_text(encoding="utf-8")
        css = (web_root / "styles.css").read_text(encoding="utf-8")
        self.assertIn('data-route="bankfix"', html)
        self.assertIn('data-page="bankfix"', html)
        self.assertIn('id="bankFixMatter"', html)
        self.assertIn('id="bankFixLesson"', html)
        self.assertIn("get_bank_classification_options", js)
        self.assertIn("update_question_classification", js)
        options_start = js.index("async function getBankClassificationOptions")
        options_end = js.index("async function loadBankFixOptions", options_start)
        classification_options = js[options_start:options_end]
        self.assertIn("bridge.studioGet(", classification_options)
        self.assertIn("taxonomy/classification-options?", classification_options)
        self.assertIn("'get_bank_classification_options'", classification_options)
        self.assertNotIn("bridge.call('get_bank_classification_options'", js)
        self.assertIn("organize_bank_lesson_group", js)
        group_start = js.index("function openBankFixLessonGroup")
        group_end = js.index("async function loadBankFix", group_start)
        organize_group = js[group_start:group_end]
        self.assertIn("bridge.studioPost(", organize_group)
        self.assertIn("taxonomy/lesson-group/organize", organize_group)
        self.assertIn("'organize_bank_lesson_group'", organize_group)
        self.assertNotIn("bridge.call('organize_bank_lesson_group'", js)
        self.assertIn("groupBankFixQuestions", js)
        render_slice = js[js.index("function renderBankFixTable"):js.index("async function loadBankFix")]
        self.assertNotIn("PDF origem", render_slice)
        self.assertNotIn("Pág.", render_slice)
        self.assertIn("Editor completo", js)
        self.assertIn("Excluir", js)

        open_start = js.index("async function openBankFixQuestion")
        open_end = js.index("async function deleteBankFixQuestion", open_start)
        open_question = js[open_start:open_end]
        self.assertIn("bridge.studioGet(", open_question)
        self.assertIn("questions/${encodeURIComponent(questionUid)}", open_question)
        self.assertIn("'get_question'", open_question)
        self.assertNotIn("bridge.call('get_question'", open_question)
        self.assertIn("bridge.studioPost(", open_question)
        self.assertIn("/delete", open_question)
        self.assertIn("'delete_question'", open_question)
        self.assertNotIn("bridge.call('delete_question'", open_question)
        self.assertIn("/classification", open_question)
        self.assertIn("'update_question_classification'", open_question)
        self.assertNotIn("bridge.call('update_question_classification'", open_question)

        delete_start = js.index("async function deleteBankFixQuestion")
        delete_end = js.index("function bindBankFixRows", delete_start)
        delete_question = js[delete_start:delete_end]
        self.assertIn("bridge.studioPost(", delete_question)
        self.assertIn("questions/${encodeURIComponent(uid)}/delete", delete_question)
        self.assertIn("'delete_question'", delete_question)
        self.assertNotIn("bridge.call('delete_question'", delete_question)
        self.assertIn(".bank-fix-lesson-body .data-table", css)
        self.assertIn("table-layout: fixed", css)
        self.assertIn(".bank-fix-lesson-body .data-table-wrap", css)
        self.assertIn("overflow-x: auto", css)
        self.assertIn(".bank-fix-lesson-meta", css)
        from web_server import ALLOWED_API_METHODS
        self.assertIn("get_bank_classification_options", ALLOWED_API_METHODS)
        self.assertIn("update_question_classification", ALLOWED_API_METHODS)
        self.assertIn("organize_bank_lesson_group", ALLOWED_API_METHODS)


if __name__ == "__main__":
    unittest.main()
