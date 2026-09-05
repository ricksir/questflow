from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.retrieval_calibration import benchmark_snapshot
from core.retrieval_observability import RetrievalObservabilityService, RetrievalObservabilityStore
from core.retrieval_quality_gates import RetrievalQualityGateService, RetrievalQualityGateStore
from web_server import ALLOWED_API_METHODS

ROOT = Path(__file__).resolve().parents[1]


class _Cal:
    def current(self):
        return {
            "id": "balanced-v1", "label": "Balanceado 6.8.2",
            "thresholds": {"score_drop_warn": 4, "recall_drop_warn": 5, "grounding_drop_warn": 3, "min_cases": 3},
        }
    def baseline(self): return None


class _Knowledge:
    engine_id = "knowledge_engine"
    name = "Knowledge Engine"
    version = "qf-knowledge-engine-3.4"
    def __init__(self):
        self.retrieval_calibration_store = _Cal()
    def observability_snapshot(self):
        return {
            "coverage": 100.0, "rag_chunks": 10, "source_count": 5, "index_digest": "x",
            "chunk_fingerprints": {}, "source_fingerprints": {},
        }


class _Governance:
    def __init__(self, count=0): self.count = count
    def gold_questions(self, active_only=True):
        return [{"id": f"g{i}"} for i in range(self.count)]


class _Editorial:
    def question_candidates(self, limit=200): return []


class RetrievalIncremental6103Tests(unittest.TestCase):
    def test_zero_cases_are_not_reported_as_quality_zero(self):
        snap = benchmark_snapshot({
            "version": "qf-grounding-benchmark-1", "cases": 0, "sample_status": "insuficiente",
            "backends": [{"backend": "hybrid", "score": 0.0, "grounding_rate": 0.0, "recall": None}], "items": [],
        }, release="6.21.0")
        self.assertIsNone(snap["hybrid"]["score"])
        self.assertIsNone(snap["hybrid"]["grounding_rate"])
        self.assertIsNone(snap["hybrid"]["recall"])

    def test_observability_read_does_not_run_benchmark_or_record(self):
        with tempfile.TemporaryDirectory() as td:
            store = RetrievalObservabilityStore(td)
            service = RetrievalObservabilityService(_Knowledge(), _Governance(), _Editorial(), store)
            with patch("core.grounding_benchmark.MultimodalGroundingBenchmark.run", side_effect=AssertionError("benchmark should not run")):
                result = service.latest_dashboard(release="6.21.0")
            self.assertEqual(result["release"], "6.21.0")
            self.assertFalse(result["recorded"])
            self.assertEqual(result["retrieval"]["cases"], 0)
            self.assertIsNone(result["retrieval"]["hybrid"]["score"])
            self.assertEqual(store.history(), [])

    def test_quality_gate_cached_read_does_not_run_benchmark(self):
        with tempfile.TemporaryDirectory() as td:
            service = RetrievalQualityGateService(_Knowledge(), _Governance(5), _Cal(), RetrievalQualityGateStore(td))
            with patch("core.grounding_benchmark.MultimodalGroundingBenchmark.run", side_effect=AssertionError("benchmark should not run")):
                gate = service.cached(release="6.21.0")
            self.assertEqual(gate["status"], "pending_evaluation")
            # 6.11+: leitura é Snapshot Store only; não consulta Governance para
            # contar Questões Ouro. Sem snapshot anterior, a amostra é desconhecida/0.
            self.assertEqual(gate["current"]["cases"], 0)
            self.assertIsNone(gate["current"]["hybrid"]["score"])
            self.assertFalse(gate["can_promote"])
            self.assertTrue(gate["snapshot_store_only"])

    def test_explicit_reevaluate_api_is_exposed(self):
        self.assertIn("reevaluate_retrieval_quality_gate", ALLOWED_API_METHODS)

    def test_modal_css_uses_compositor_safe_path(self):
        css = (ROOT / "web" / "styles.css").read_text(encoding="utf-8")
        self.assertIn(".modal-backdrop { position: absolute; inset: 0; background: rgba(3, 12, 23, 0.76); backdrop-filter: none", css)
        self.assertIn("animation: qf-modal-safe 140ms ease-out", css)
        self.assertIn("body.qf-modal-open .topbar", css)
        self.assertIn("contain: paint", css)

    def test_retrieval_ui_is_read_only_until_explicit_action(self):
        js = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        self.assertIn("start_retrieval_evaluation", js)
        self.assertIn("get_retrieval_evaluation_job", js)
        self.assertIn("runRetrievalEvaluator", js)
        self.assertIn("Reavaliar e registrar", js)
        self.assertIn("Mostrar detalhes técnicos e histórico", js)
        self.assertIn("Modo avançado", js)
        self.assertIn("retrievalEngineEyebrow", js)

    def test_release_is_6103(self):
        self.assertEqual((ROOT / "VERSION.txt").read_text(encoding="utf-8").strip(), "6.24.0")
        self.assertIn('version = "6.24.0"', (ROOT / "pyproject.toml").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
