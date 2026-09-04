from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.ai_providers import generate, provider_capabilities
from core.ai_safety import privacy_settings
from core.engines.knowledge_engine import KnowledgeEngine
from core.question_services import QuestionCommandService, QuestionQueryService
from core.storage import QuestFlowDatabase


class MultimodalRag680Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="qf-mmrag-680-")
        root = Path(self.tmp.name)
        self.db = QuestFlowDatabase(root / "q.sqlite")
        self.queries = QuestionQueryService(self.db)
        self.commands = QuestionCommandService(self.db)
        self.image = root / "questao.png"
        self.image.write_bytes(b"\x89PNG\r\n\x1a\n" + b"x" * 128)
        self.pdf = root / "aula.pdf"
        self.pdf.write_bytes(b"%PDF-1.4\n%%EOF")
        self.uid = self.db.create_manual_question(None)
        q = self.db.get_question(self.uid); assert q
        q.update({
            "enunciado": "Observe o gráfico e assinale a alternativa correta.",
            "materia": "ESTATÍSTICA",
            "assunto": "Distribuição",
            "imagem_questao": {"path": str(self.image), "page": 3, "origem": "recorte_pdf"},
            "contexto_visual": {"descricao": "Gráfico de barras com quatro categorias.", "paginas": [3]},
            "source_file": str(self.pdf),
            "source_page": 3,
        })
        self.db.update_question(self.uid, q)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_hybrid_retrieval_returns_auditable_visual_grounding_without_local_path(self) -> None:
        engine = KnowledgeEngine(self.queries, self.commands)
        result = engine.retrieve_multimodal(self.uid, "gráfico", backend="hybrid", limit=8)
        self.assertEqual(result["engine"], "qf-multimodal-rag-3")
        self.assertIn("visual", result["modalities"])
        visual = next(item for item in result["items"] if item.get("modality") == "visual")
        self.assertEqual(visual["backend"], "local_visual_evidence")
        self.assertEqual(visual["grounding"]["source_page"], 3)
        self.assertTrue(visual["grounding"]["image_path_sha256"])
        serialized = json.dumps(visual, ensure_ascii=False)
        self.assertNotIn(str(self.image), serialized)
        self.assertNotIn(str(self.pdf), serialized)
        self.assertTrue(any(item.get("kind") == "image" for item in visual.get("media", [])))
        self.assertTrue(any(item.get("kind") == "pdf" for item in visual.get("media", [])))

    def test_binary_media_is_never_enabled_by_balanced_preset(self) -> None:
        policy = privacy_settings({"ai_privacy_mode": "balanced", "share_binary_media": True})
        self.assertFalse(policy["share_binary_media"])

    def test_custom_mode_requires_explicit_binary_media_flag(self) -> None:
        off = privacy_settings({"ai_privacy_mode": "custom"})
        on = privacy_settings({"ai_privacy_mode": "custom", "share_binary_media": True})
        self.assertFalse(off["share_binary_media"])
        self.assertTrue(on["share_binary_media"])

    def test_gemini_adapter_inlines_image_only_when_attachments_are_passed(self) -> None:
        captured = {}

        def fake_post(url, payload, headers, **kwargs):
            captured.update(payload)
            return {"output_text": "OK", "usage": {}}

        config = {"ai_gemini_model": "gemini-test"}
        with patch("core.ai_providers.load_keys", return_value={"gemini": "secret"}), patch("core.ai_providers._post", side_effect=fake_post):
            result = generate(
                "gemini", "Analise a imagem.", config=config, config_path=Path(self.tmp.name) / "config.json",
                attachments=[{"kind": "image", "path": str(self.image), "mime_type": "image/png"}],
            )
        self.assertEqual(result["media_sent_count"], 1)
        self.assertIsInstance(captured["input"], list)
        self.assertEqual(captured["input"][0]["type"], "text")
        self.assertEqual(captured["input"][1]["type"], "image")
        self.assertEqual(captured["input"][1]["mime_type"], "image/png")
        self.assertTrue(captured["input"][1]["data"])
        self.assertTrue(provider_capabilities("gemini", "gemini-test")["multimodal_binary"])
        self.assertFalse(provider_capabilities("openai", "any")["multimodal_binary"])


if __name__ == "__main__":
    unittest.main()
