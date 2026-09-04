from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pymupdf

from core.exporter import build_questflow_question_bank, validate_questflow_question_bank
from core.extractor import ExtractorConfig, extract_pdf
from core.markdown_pipeline import MarkdownBundle


class ExtractorExporterTests(unittest.TestCase):
    def test_textual_list_and_true_false(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            pdf = root / "questions.pdf"
            doc = pymupdf.open()
            page = doc.new_page()
            content = (
                "LISTA DE QUESTÕES\n\n"
                "1. (FGV / TCE - 2025) Assinale a opção correta.\n"
                "a) Alfa.\n"
                "b) Beta.\n\n"
                "2. (CEBRASPE / TCU - 2025) Julgue o item a seguir.\n"
                "A auditoria contribui para a governança.\n\n"
                "GABARITO\n"
                "1. LETRA B\n"
                "2. CORRETO\n"
            )
            page.insert_textbox(pymupdf.Rect(35, 35, 560, 800), content, fontsize=10)
            doc.save(pdf)
            doc.close()
            bundle = MarkdownBundle(
                source_path=str(pdf),
                cache_key="inline-commented-test",
                markdown_path=str(root / "document.md"),
                metadata_path=str(root / "metadata.json"),
                image_dir=str(root / "images"),
                pages=[content],
                engine="test-native-text",
                used_ocr=False,
            )
            with patch("core.extractor.build_markdown_bundle", return_value=bundle):
                result = extract_pdf(pdf, ExtractorConfig(), markdown_cache_dir=root / "md")
            self.assertEqual(len(result["questions"]), 2)
            self.assertEqual(result["questions"][0]["gabarito"], "B")
            self.assertEqual(result["questions"][1]["tipo"], "certo_errado")

    def test_resolved_and_commented_questions_with_inline_answers(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            pdf = root / "auditoria_resolvida.pdf"
            doc = pymupdf.open()
            page = doc.new_page()
            content = (
                "QUESTOES RESOLVIDAS E COMENTADAS - FGV\n\n"
                "1. (FGV / SEFAZ AM /2022) Assinale a opcao correta.\n"
                "a) Inspecao.\n"
                "b) Observacao.\n"
                "c) Confirmacao.\n"
                "Comentarios\n"
                "A confirmacao produz evidencia externa.\n"
                "Gabarito: C.\n\n"
                "2. (FGV / TCE AM /2021) Assinale a opcao incorreta.\n"
                "a) Planejamento.\n"
                "b) Execucao.\n"
                "c) Arquivamento.\n"
                "Comentarios\n"
                "O arquivamento nao substitui a execucao.\n"
                "Gabarito: C.\n"
            )
            page.insert_textbox(pymupdf.Rect(35, 35, 560, 800), content, fontsize=10)
            doc.save(pdf)
            doc.close()
            bundle = MarkdownBundle(
                source_path=str(pdf),
                cache_key="inline-commented-test",
                markdown_path=str(root / "document.md"),
                metadata_path=str(root / "metadata.json"),
                image_dir=str(root / "images"),
                pages=[content],
                engine="test-native-text",
                used_ocr=False,
            )
            with patch("core.extractor.build_markdown_bundle", return_value=bundle):
                result = extract_pdf(pdf, ExtractorConfig(), markdown_cache_dir=root / "md")
            self.assertEqual(result["extractor_mode"], "texto_nativo_comentado")
            self.assertEqual(len(result["questions"]), 2)
            self.assertEqual(result["questions"][0]["gabarito"], "C")
            self.assertEqual(len(result["questions"][0]["alternativas"]), 3)
            self.assertIn("evidencia externa", result["questions"][0]["explicacao"])

    def test_scanned_commented_book_forces_ocr_and_keeps_duplicate_numbers_unique(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            pdf = root / "scanned-book.pdf"
            document = pymupdf.open()
            document.new_page()
            document.save(pdf)
            document.close()
            empty_bundle = MarkdownBundle(
                source_path=str(pdf),
                cache_key="native-empty",
                markdown_path=str(root / "native.md"),
                metadata_path=str(root / "native.json"),
                image_dir=str(root / "native-images"),
                pages=[""],
                engine="native-empty",
                used_ocr=False,
            )
            ocr_text = (
                "QUESTÕES RESOLVIDAS E COMENTADAS - MULTIBANCAS\n"
                "1. (FGV / ÓRGÃO - 2025) Primeira questão.\n"
                "a) Alfa. b) Beta. c) Gama. d) Delta. e) Épsilon.\n"
                "Comentários:\nA alternativa correta é a primeira.\n"
                "Pelo exposto, nosso gabarito é a letra A.\n"
                "As demais alternativas não atendem ao enunciado.\n"
                "1. (CESPE / ÓRGÃO - 2024) Julgue o item subsequente.\n"
                "A afirmação está incorreta.\nComentários\n"
                "Gabarito: ERRADO.\n"
            )
            ocr_bundle = MarkdownBundle(
                source_path=str(pdf),
                cache_key="forced-ocr",
                markdown_path=str(root / "ocr.md"),
                metadata_path=str(root / "ocr.json"),
                image_dir=str(root / "ocr-images"),
                pages=[ocr_text],
                engine="tesseract-test",
                used_ocr=True,
            )
            with (
                patch("core.extractor.build_markdown_bundle", side_effect=[empty_bundle, ocr_bundle]) as build,
                patch("core.extractor.configure_tesseract", return_value="tesseract"),
                patch("core.extractor._is_scanned_strategy_question_book", return_value=True),
            ):
                result = extract_pdf(pdf, ExtractorConfig(), markdown_cache_dir=root / "cache")
            self.assertEqual(result["extractor_mode"], "ocr_comentado")
            self.assertTrue(result["markdown"]["used_ocr"])
            self.assertEqual(result["markdown"]["pages"], [ocr_text])
            self.assertEqual(len(result["questions"]), 2)
            self.assertEqual([item["gabarito"] for item in result["questions"]], ["A", "E"])
            self.assertEqual(len(result["questions"][0]["alternativas"]), 5)
            self.assertIn("demais alternativas", result["questions"][0]["explicacao"])
            self.assertNotIn("nosso gabarito", result["questions"][0]["explicacao"].lower())
            for question in result["questions"]:
                self.assertTrue(question["enunciado"])
                self.assertTrue(question["gabarito"])
                self.assertTrue(question["fonte"])
                self.assertTrue(question["ocr"])
                self.assertIn("materia", question)
                self.assertIn("banca", question)
                self.assertIn("ano", question)
            self.assertEqual(len({item["id"] for item in result["questions"]}), 2)
            self.assertTrue(build.call_args_list[1].kwargs["force_ocr"])

    def test_commented_book_does_not_require_resolved_word_in_title(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            pdf = root / "fluenciaemdados.pdf"
            document = pymupdf.open()
            document.new_page()
            document.save(pdf)
            document.close()
            content = (
                "Q UESTÕES\nC OMENTADAS\n"
                "1. (CEBRASPE / EMBRAPA - 2025) Julgue o item sobre banco de dados.\n"
                "Um atributo de uma entidade representa uma característica do mundo real.\n"
                "Comentários:\nA afirmação descreve corretamente uma entidade.\n"
                "Gabarito: Correto\n"
                "2. (FGV / ÓRGÃO - 2024) Na notação Crow's foot, escolha o símbolo gráfico correto:\n"
                "a) b) c) d) e)\n"
                "Comentários:\nA alternativa D representa a cardinalidade solicitada.\n"
                "Gabarito: Letra D\n"
            )
            bundle = MarkdownBundle(
                source_path=str(pdf),
                cache_key="commented-without-resolved",
                markdown_path=str(root / "document.md"),
                metadata_path=str(root / "metadata.json"),
                image_dir=str(root / "images"),
                pages=[content],
                engine="test-native-text",
                used_ocr=False,
            )
            with patch("core.extractor.build_markdown_bundle", return_value=bundle):
                result = extract_pdf(pdf, ExtractorConfig(), markdown_cache_dir=root / "md")
            self.assertEqual(result["extractor_mode"], "texto_nativo_comentado")
            self.assertEqual(len(result["questions"]), 2)
            self.assertEqual({item["materia"] for item in result["questions"]}, {"FLUÊNCIA EM DADOS"})
            self.assertEqual([item["gabarito"] for item in result["questions"]], ["C", "D"])
            self.assertIn("corretamente uma entidade", result["questions"][0]["explicacao"])
            self.assertIn("cardinalidade solicitada", result["questions"][1]["explicacao"])
            self.assertTrue(result["questions"][1]["contexto_visual"]["necessario"])
            self.assertEqual(len(result["questions"][1]["alternativas"]), 5)
            self.assertEqual(
                [item["chave"] for item in result["questions"][1]["alternativas"]],
                ["A", "B", "C", "D", "E"],
            )

    def test_commented_book_accepts_markdown_decorated_question_headers(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            pdf = root / "contabilidade_aula02.pdf"
            document = pymupdf.open()
            document.new_page()
            document.save(pdf)
            document.close()
            content = (
                "# QUESTÕES COMENTADAS – ESCRITURAÇÃO\n"
                "**1. (CEBRASPE/PC DF/Contador/2025) Um lançamento contábil altera o patrimônio líquido.**\n"
                "#### **Comentários:**\nO comentário integral deve virar a explicação.\n"
                "#### **Gabarito: Certo**\n"
                "Julgue o próximo item.\n"
                "**<mark>2. (FGV/ÓRGÃO/Contador/2024) Considere a tabela apresentada.</mark>**\n"
                "![](tabela.png)\n- (A) Ativo.\n- (B) Passivo.\n- (C) Receita.\n"
                "## **Comentários:**\nA alternativa B é a classificação correta.\n"
                "## **Gabarito: B**\n"
                "**3. (FGV/ÓRGÃO/Contador/2024) Julgue os itens apresentados e assinale a opção correta:**\n"
                "A Apenas o item I.\nB Apenas o item II.\nC Todos os itens.\n"
                "## **Comentários:**\nA alternativa A corresponde à análise.\n"
                "## **Gabarito: A**\n"
            )
            bundle = MarkdownBundle(
                source_path=str(pdf),
                cache_key="commented-markdown-decorators",
                markdown_path=str(root / "document.md"),
                metadata_path=str(root / "metadata.json"),
                image_dir=str(root / "images"),
                pages=[content],
                engine="pymupdf4llm-test",
                used_ocr=False,
            )
            with patch("core.extractor.build_markdown_bundle", return_value=bundle):
                result = extract_pdf(
                    pdf,
                    ExtractorConfig(),
                    markdown_cache_dir=root / "md",
                    asset_dir=root / "assets",
                )
            self.assertEqual(len(result["questions"]), 3)
            self.assertEqual([item["gabarito"] for item in result["questions"]], ["C", "B", "A"])
            self.assertEqual({item["materia"] for item in result["questions"]}, {"CONTABILIDADE GERAL E AVANÇADA"})
            self.assertIn("comentário integral", result["questions"][0]["explicacao"].lower())
            self.assertNotIn("Julgue o próximo item", result["questions"][0]["explicacao"])
            self.assertNotIn("**", result["questions"][0]["enunciado"])
            self.assertTrue(result["questions"][1]["contexto_visual"]["necessario"])
            self.assertTrue(Path(result["questions"][1]["imagem_questao"]["path"]).exists())
            self.assertEqual(result["questions"][2]["tipo"], "multipla_escolha")
            self.assertEqual(
                [item["chave"] for item in result["questions"][2]["alternativas"]],
                ["A", "B", "C"],
            )

    def test_import_button_remains_disabled_after_queue_is_cleared(self) -> None:
        script = (Path(__file__).resolve().parents[1] / "web" / "app.js").read_text(encoding="utf-8")
        self.assertIn("button.disabled = !state.selectedImportFiles.length;", script)
        self.assertIn("numberOrZero(completed?.extracted) === 0", script)
        api = (Path(__file__).resolve().parents[1] / "web_api.py").read_text(encoding="utf-8")
        self.assertIn("Nenhuma questão foi reconhecida. O arquivo é válido", api)

    def test_native_bank_validation(self) -> None:
        question = {
            "id": "Q1",
            "enunciado": "Questão",
            "alternativas": [
                {"chave": "A", "texto": "Sim"},
                {"chave": "B", "texto": "Não"},
            ],
            "gabarito": "A",
        }
        payload = build_questflow_question_bank([question])
        self.assertEqual(payload["question_count"], 1)
        self.assertEqual(validate_questflow_question_bank(payload), [])


if __name__ == "__main__":
    unittest.main()
