from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from core.retrieval_health_service import RetrievalHealthService, RetrievalHealthSnapshotStore
from web_server import ALLOWED_API_METHODS

ROOT = Path(__file__).resolve().parents[1]


class FakeCalibration:
    def __init__(self):
        self._baseline = None
        self._profile = {
            "id": "balanced-v1",
            "label": "Balanceado",
            "thresholds": {
                "score_drop_warn": 4,
                "recall_drop_warn": 5,
                "grounding_drop_warn": 3,
                "min_cases": 3,
            },
        }
    def current(self): return dict(self._profile)
    def baseline(self): return self._baseline
    def save_baseline(self, snapshot): self._baseline = dict(snapshot); return self._baseline
    def apply(self, profile, reason=""): self._profile = dict(profile); return {"active": profile, "reason": reason}


class FakeKnowledge:
    engine_id = "knowledge_engine"
    name = "Knowledge Engine"
    version = "qf-knowledge-engine-3.4"
    def __init__(self):
        self.retrieval_calibration_store = FakeCalibration()
        self.snapshot_calls = 0
    def observability_snapshot(self):
        self.snapshot_calls += 1
        return {
            "coverage": 100.0,
            "rag_chunks": 12,
            "source_count": 6,
            "index_digest": "idx",
            "chunk_fingerprints": {"a": "1"},
            "source_fingerprints": {"s": "1"},
        }


class FakeGovernance:
    def gold_questions(self, active_only=True):
        return [{"question_uid": f"q{i}", "subject": "AUDITORIA"} for i in range(5)]


class FakeEditorial:
    def question_candidates(self, limit=200): return []


def benchmark_report():
    return {
        "version": "qf-grounding-benchmark-1",
        "cases": 5,
        "sample_status": "suficiente",
        "backends": [{
            "backend": "hybrid", "score": 82.0, "recall": 81.0,
            "grounding_rate": 100.0, "commentary_support": 90,
            "precision": 85, "visual_coverage": 100, "path_safety": 100,
        }],
        "items": [
            {"subject": "AUDITORIA", "backends": [{"backend": "hybrid", "composite_score": 82, "recall": 81, "grounding_rate": 100}]}
            for _ in range(5)
        ],
    }


class RetrievalHealthService6110Tests(unittest.TestCase):
    def build(self, root):
        knowledge = FakeKnowledge()
        service = RetrievalHealthService(
            knowledge=knowledge,
            governance=FakeGovernance(),
            editorial=FakeEditorial(),
            calibration_store=knowledge.retrieval_calibration_store,
            root=root,
        )
        return knowledge, service

    def wait_job(self, service, job_id, timeout=5):
        deadline = time.time() + timeout
        while time.time() < deadline:
            job = service.job(job_id)
            if job.get("status") not in {"queued", "running"}:
                return job
            time.sleep(0.02)
        self.fail("Evaluator Worker não concluiu dentro do timeout do teste")

    def test_query_side_never_touches_benchmark_or_live_index(self):
        with tempfile.TemporaryDirectory() as td:
            knowledge, service = self.build(td)
            with patch("core.grounding_benchmark.MultimodalGroundingBenchmark.run", side_effect=AssertionError("benchmark em query")):
                obs = service.read_observability(release="6.21.0")
                gate = service.read_quality_gate(release="6.21.0")
            self.assertEqual(knowledge.snapshot_calls, 0)
            self.assertTrue(obs["snapshot_store_only"])
            self.assertTrue(gate["snapshot_store_only"])
            service.shutdown()

    @patch("core.grounding_benchmark.MultimodalGroundingBenchmark.run", return_value=benchmark_report())
    def test_single_worker_evaluation_updates_observability_and_gate_once(self, run):
        with tempfile.TemporaryDirectory() as td:
            knowledge, service = self.build(td)
            first = service.start_evaluation(release="6.21.0", limit=30, source="quality_gate")
            second = service.start_evaluation(release="6.21.0", limit=30, source="observability")
            self.assertEqual(first["id"], second["id"])
            self.assertTrue(second.get("deduplicated"))
            job = self.wait_job(service, first["id"])
            self.assertEqual(job["status"], "completed")
            self.assertEqual(run.call_count, 1)
            self.assertEqual(knowledge.snapshot_calls, 1)
            canonical = service.snapshot_store.snapshot()
            self.assertTrue(canonical["consistent"])
            evaluation_id = canonical["evaluation_id"]
            obs = service.read_observability(release="6.21.0")
            gate = service.read_quality_gate(release="6.21.0")
            self.assertEqual(obs["history"][0]["evaluation_id"], evaluation_id)
            self.assertEqual(gate["evaluation_id"], evaluation_id)
            self.assertEqual(gate["current"]["evaluation_id"], evaluation_id)
            service.shutdown()

    @patch("core.grounding_benchmark.MultimodalGroundingBenchmark.run", return_value=benchmark_report())
    def test_promotion_uses_cached_gate_and_does_not_rebenchmark(self, run):
        with tempfile.TemporaryDirectory() as td:
            _, service = self.build(td)
            job = service.start_evaluation(release="6.21.0", source="quality_gate")
            self.wait_job(service, job["id"])
            self.assertEqual(run.call_count, 1)
            with patch("core.grounding_benchmark.MultimodalGroundingBenchmark.run", side_effect=AssertionError("promotion benchmark")):
                result = service.promote(release="6.21.0", reason="Promoção humana após validação do worker.")
            self.assertEqual(result["approved"]["release"], "6.21.0")
            service.shutdown()

    def test_interrupted_worker_state_is_repaired_on_startup(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "retrieval_health_service_state.json").write_text(
                '{"status":"running","active_job":{"id":"old"}}', encoding="utf-8"
            )
            store = RetrievalHealthSnapshotStore(root)
            state = store.state()
            self.assertEqual(state["status"], "interrupted")
            self.assertIsNone(state["active_job"])

    def test_application_path_no_longer_routes_observability_through_ai_engine(self):
        ai = (ROOT / "core" / "engines" / "ai_engine.py").read_text(encoding="utf-8")
        web_api = (ROOT / "web_api.py").read_text(encoding="utf-8")
        self.assertNotIn("def get_retrieval_observability", ai)
        self.assertNotIn("def get_retrieval_quality_gate", ai)
        self.assertNotIn("engines.ai.get_retrieval_observability", web_api)
        self.assertIn("RetrievalHealthService", web_api)

    def test_http_contract_exposes_service_worker_and_snapshot_queries(self):
        for method in (
            "get_retrieval_health_service",
            "get_retrieval_health_snapshot",
            "start_retrieval_evaluation",
            "get_retrieval_evaluation_job",
        ):
            self.assertIn(method, ALLOWED_API_METHODS)

    def test_ui_polls_worker_instead_of_running_gate_inline(self):
        js = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        self.assertIn("start_retrieval_evaluation", js)
        self.assertIn("get_retrieval_evaluation_job", js)
        self.assertIn("Snapshot Store", js)
        self.assertNotIn("force?'reevaluate_retrieval_quality_gate':'get_retrieval_quality_gate'", js)

    def test_release_is_6110_mobile_contract_unchanged(self):
        self.assertEqual((ROOT / "VERSION.txt").read_text(encoding="utf-8").strip(), "6.24.0")
        self.assertIn('version = "6.24.0"', (ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        package = (ROOT / "mobile" / "package.json").read_text(encoding="utf-8")
        self.assertIn('"version": "0.16.0"', package)


if __name__ == "__main__":
    unittest.main()
