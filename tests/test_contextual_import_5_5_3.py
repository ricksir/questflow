from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from core.storage import QuestFlowDatabase
from core.study import StudyRepository
from web_api import QuestFlowWebApi


class _FakeCoverageStudy:
    def __init__(self, item: dict) -> None:
        self.item = item

    def studied_content_coverage(self, _tasks):
        return {"items": [dict(self.item)], "summary": {}}


class ContextualImport553Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="questflow-context-import-")
        self.root = Path(self.temp.name)
        self.api = QuestFlowWebApi(
            self.root / "questions.sqlite",
            config={},
            config_path=self.root / "config.json",
            taxonomy_path=self.root / "taxonomy.json",
        )

    def tearDown(self) -> None:
        self.api.shutdown()
        self.temp.cleanup()

    def test_context_is_resolved_from_authoritative_studied_row(self) -> None:
        report_item = {
            "task_id": "TRILHA 3:88",
            "trilha": "TRILHA 3",
            "tarefa": "88",
            "subject": "AUDITORIA",
            "lesson": "Aula 03",
            "content": "Risco de auditoria até risco de detecção",
            "description": "Teoria da Aula 03 sobre risco de auditoria e risco de detecção.",
            "questions_done": 12,
            "bank_question_count": 4,
            "missing_question_count": 8,
            "needs_attention": True,
        }
        self.api.taxonomy = SimpleNamespace(tasks=[{"row": 88}], source_name="Planilha")
        self.api.study = _FakeCoverageStudy(report_item)
        self.api._ensure_core = lambda *args, **kwargs: None  # type: ignore[method-assign]

        resolved = self.api._resolve_study_import_context(
            {"task_id": "TRILHA 3:88", "materia": "MATÉRIA INCORRETA", "aula": "Aula 99"}
        )
        self.assertIsNotNone(resolved)
        assert resolved is not None
        self.assertEqual(resolved["materia"], "AUDITORIA")
        self.assertEqual(resolved["aula"], "Aula 03")
        self.assertEqual(resolved["faltam_antes"], 8)
        self.assertEqual(resolved["descricao"], report_item["description"])

    def test_contextual_binding_forces_subject_lesson_and_exact_task_reference(self) -> None:
        self.api.taxonomy = SimpleNamespace(source_name="Trilhas00a18_AFRFB", tasks=[])
        context = {
            "task_id": "TRILHA 0:6",
            "trilha": "TRILHA 0",
            "tarefa": "3",
            "materia": "DIREITO TRIBUTÁRIO",
            "aula": "Aula 00",
            "conteudo": "noções introdutórias até espécies tributárias",
            "descricao": "Estudo da Aula 00 – Parte 1 de 3. De noções introdutórias até espécies tributárias.",
        }
        result = {
            "source_file": "aula00.pdf",
            "questions": [
                {
                    "codigo_origem": "QCTX001",
                    "materia": "DIREITO ADMINISTRATIVO",
                    "aula_planilha": "Aula 99",
                    "assunto": "ESPÉCIES TRIBUTÁRIAS",
                    "assuntos": ["ESPÉCIES TRIBUTÁRIAS"],
                    "enunciado": "Questão de teste.",
                    "alternativas": [{"chave": "A", "texto": "A"}, {"chave": "B", "texto": "B"}],
                    "gabarito": "A",
                    "revisao": {"status": "pendente", "confianca": 0.8, "alertas": []},
                    "classificacao_planilha": {"status": "revisar", "confianca": 0.2, "referencia": "outra"},
                    "fonte": {"arquivo": "aula00.pdf"},
                }
            ],
        }
        bound = self.api._apply_study_import_context(result, context)
        question = bound["questions"][0]
        self.assertEqual(question["materia"], "DIREITO TRIBUTÁRIO")
        self.assertEqual(question["aula_planilha"], "Aula 00")
        self.assertEqual(question["materia_origem"], "DIREITO ADMINISTRATIVO")
        self.assertEqual(question["aula_origem"], "Aula 99")
        self.assertEqual(question["classificacao_planilha"]["metodo"], "importacao_contextual_estudo")
        self.assertEqual(question["classificacao_planilha"]["confianca"], 1.0)
        self.assertEqual(question["classificacao_planilha"]["referencia"], context["descricao"])
        self.assertEqual(question["contexto_importacao_estudos"]["task_id"], "TRILHA 0:6")

        db = QuestFlowDatabase(self.root / "context.sqlite")
        imported = db.import_extraction(bound)
        self.assertEqual(imported["inserted"], 1)
        coverage = StudyRepository(db).studied_content_coverage(
            [
                {
                    "row": 6,
                    "trilha": "TRILHA 0",
                    "tarefa": "3",
                    "materia": "DIREITO TRIBUTÁRIO",
                    "aula": "Aula 00",
                    "descricao": context["descricao"],
                    "segmentos": ["noções introdutórias", "espécies tributárias"],
                    "estudado": True,
                    "ch_efetiva_min": 90,
                    "questoes_feitas": 2,
                    "acertos": 2,
                    "meta_questoes": 2,
                }
            ]
        )["items"][0]
        self.assertEqual(coverage["bank_question_count"], 1)
        self.assertEqual(coverage["missing_question_count"], 1)

    def test_contextual_file_picker_accepts_only_pdf(self) -> None:
        self.api._dialog_open = lambda **kwargs: [str(self.root / "questoes.pdf"), str(self.root / "foto.png")]  # type: ignore[method-assign]
        result = self.api.choose_import_files(True)
        self.assertEqual(result["paths"], [str(self.root / "questoes.pdf")])

    def test_web_ui_exposes_contextual_import_action(self) -> None:
        web_root = Path(__file__).resolve().parents[1] / "web"
        js = (web_root / "app.js").read_text(encoding="utf-8")
        html = (web_root / "index.html").read_text(encoding="utf-8")
        self.assertIn("beginCoverageImport", js)
        self.assertIn("row.addEventListener('click'", js)
        self.assertIn("rowInteractiveWhen: (item) => Boolean(item.needs_attention)", js)
        self.assertIn("window.getSelection", js)
        self.assertIn("bridge.call('start_import', state.selectedImportFiles, state.importContext)", js)
        self.assertIn("bridge.call('choose_import_files', true)", js)
        self.assertIn('id="importContextPanel"', html)
        self.assertIn("Clique em qualquer ponto de uma linha pendente", html)


if __name__ == "__main__":
    unittest.main()
