from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app import QuestFlowApp


class DeepSourceResolutionTests(unittest.TestCase):
    def test_resolve_missing_original_path_by_filename(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            nested = root / "curso" / "pdfs"
            nested.mkdir(parents=True)
            pdf = nested / "auditoria1.pdf"
            pdf.write_bytes(b"%PDF-1.4\n%%EOF")
            question = {
                "fonte": {
                    "arquivo": "auditoria1.pdf",
                    "caminho_arquivo": r"C:\pasta-antiga\auditoria1.pdf",
                }
            }
            resolved = QuestFlowApp._resolve_question_source(question, [str(root)], {})
            self.assertEqual(Path(resolved), pdf.resolve())

    def test_missing_filename_returns_empty(self) -> None:
        question = {"fonte": {"arquivo": "nao_existe.pdf"}}
        with tempfile.TemporaryDirectory() as temp_name:
            resolved = QuestFlowApp._resolve_question_source(question, [temp_name], {})
        self.assertEqual(resolved, "")


if __name__ == "__main__":
    unittest.main()
