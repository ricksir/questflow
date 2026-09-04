from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pymupdf

from core.markdown_pipeline import build_markdown_bundle


class MarkdownPipelineTests(unittest.TestCase):
    def test_pdf_to_markdown_and_cache(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            pdf = root / "sample.pdf"
            doc = pymupdf.open()
            page = doc.new_page()
            page.insert_text((50, 80), "LISTA DE QUESTÕES - ETL e Data Warehouse")
            doc.save(pdf)
            doc.close()
            bundle = build_markdown_bundle(pdf, root / "cache")
            self.assertIn("LISTA DE QUEST", bundle.markdown)
            self.assertTrue(Path(bundle.markdown_path).exists())
            cached = build_markdown_bundle(pdf, root / "cache")
            self.assertEqual(bundle.cache_key, cached.cache_key)
            self.assertEqual(bundle.pages, cached.pages)

    def test_source_pdf_is_released_after_conversion(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            pdf = root / "released.pdf"
            doc = pymupdf.open()
            page = doc.new_page()
            page.insert_text((50, 80), "QuestFlow handle release test")
            doc.save(pdf)
            doc.close()
            build_markdown_bundle(pdf, root / "cache")
            pdf.unlink()
            self.assertFalse(pdf.exists())


if __name__ == "__main__":
    unittest.main()
