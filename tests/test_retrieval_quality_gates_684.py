from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.retrieval_quality_gates import RetrievalQualityGateService, RetrievalQualityGateStore
from web_server import ALLOWED_API_METHODS


def report(score=80, recall=80, grounding=100, cases=5):
    items=[]
    for i in range(cases):
        items.append({"subject":"AUDITORIA","backends":[{"backend":"hybrid","composite_score":score,"recall":recall,"grounding_rate":grounding}]})
    return {
        "version":"qf-grounding-benchmark-1","cases":cases,"sample_status":"suficiente" if cases>=3 else "insuficiente",
        "backends":[{"backend":"hybrid","score":score,"recall":recall,"grounding_rate":grounding}],"items":items,
    }


class FakeKnowledge:
    def __init__(self, coverage=100): self.coverage=coverage
    def observability_snapshot(self):
        return {"coverage":self.coverage,"rag_chunks":100,"source_count":50,"chunk_fingerprints":{},"source_fingerprints":{}}


class FakeGovernance: pass


class FakeCalibration:
    def __init__(self, baseline=None):
        self._baseline=baseline; self.applied=[]
        self._profile={"id":"balanced-v1","label":"Balanceado","weights":{},"thresholds":{"score_drop_warn":4,"recall_drop_warn":5,"grounding_drop_warn":3,"min_cases":3}}
    def current(self): return dict(self._profile)
    def baseline(self): return self._baseline
    def save_baseline(self, snapshot): self._baseline=dict(snapshot); return self._baseline
    def apply(self, profile, reason=""): self._profile=dict(profile); self.applied.append((profile,reason)); return {"active":profile}


def baseline(release="6.8.3",score=80,recall=80,grounding=100,coverage=100):
    return {"release":release,"cases":5,"hybrid":{"score":score,"recall":recall,"grounding_rate":grounding},"subjects":{"AUDITORIA":{"cases":5,"score":score,"recall":recall,"grounding_rate":grounding}},"index_coverage":coverage}


class RetrievalQualityGates684Tests(unittest.TestCase):
    @patch("core.grounding_benchmark.MultimodalGroundingBenchmark.run", return_value=report(score=81,recall=81))
    def test_gate_passes_against_legacy_baseline(self, _run):
        with tempfile.TemporaryDirectory() as td:
            cal=FakeCalibration(baseline())
            service=RetrievalQualityGateService(FakeKnowledge(),FakeGovernance(),cal,RetrievalQualityGateStore(td))
            gate=service.evaluate(release="6.8.4")
            self.assertEqual(gate["status"],"pass")
            self.assertTrue(gate["can_promote"])
            self.assertEqual(gate["baseline_source"],"legacy_regression_baseline")

    @patch("core.grounding_benchmark.MultimodalGroundingBenchmark.run", return_value=report(score=70,recall=70,grounding=94))
    def test_gate_quarantines_regression(self, _run):
        with tempfile.TemporaryDirectory() as td:
            cal=FakeCalibration(baseline())
            service=RetrievalQualityGateService(FakeKnowledge(coverage=94),FakeGovernance(),cal,RetrievalQualityGateStore(td))
            gate=service.evaluate(release="6.8.4")
            self.assertEqual(gate["status"],"quarantine")
            self.assertFalse(gate["can_promote"])
            self.assertTrue(gate["can_override"])
            metrics={x.get("metric") for x in gate["blockers"]}
            self.assertTrue({"score","recall","grounding_rate"}.issubset(metrics))

    @patch("core.grounding_benchmark.MultimodalGroundingBenchmark.run", return_value=report(score=82,recall=82))
    def test_promotion_creates_approved_baseline(self, _run):
        with tempfile.TemporaryDirectory() as td:
            cal=FakeCalibration(baseline())
            store=RetrievalQualityGateStore(td)
            service=RetrievalQualityGateService(FakeKnowledge(),FakeGovernance(),cal,store)
            result=service.promote(release="6.8.4",reason="aprovação humana de teste")
            self.assertEqual(result["approved"]["release"],"6.8.4")
            self.assertFalse(result["approved"]["override"])
            self.assertEqual(store.approved_baseline()["release"],"6.8.4")

    @patch("core.grounding_benchmark.MultimodalGroundingBenchmark.run", return_value=report(score=70,recall=70,grounding=94))
    def test_override_requires_reason_and_is_audited(self, _run):
        with tempfile.TemporaryDirectory() as td:
            cal=FakeCalibration(baseline())
            service=RetrievalQualityGateService(FakeKnowledge(94),FakeGovernance(),cal,RetrievalQualityGateStore(td))
            with self.assertRaises(ValueError): service.override(release="6.8.4",reason="curto")
            result=service.override(release="6.8.4",reason="Exceção operacional autorizada para teste controlado.")
            self.assertTrue(result["approved"]["override"])
            self.assertIn("Exceção operacional",result["approved"]["approval_reason"])

    @patch("core.grounding_benchmark.MultimodalGroundingBenchmark.run", return_value=report(score=82,recall=82))
    def test_rollback_restores_previous_approved_release_and_profile(self, _run):
        with tempfile.TemporaryDirectory() as td:
            cal=FakeCalibration(baseline())
            store=RetrievalQualityGateStore(td)
            # estabelece uma primeira promoção e depois uma segunda
            store.approve(baseline("6.8.3"),profile=cal.current(),action="promote",reason="seed",gate={"status":"pass","blockers":[]})
            service=RetrievalQualityGateService(FakeKnowledge(),FakeGovernance(),cal,store)
            service.promote(release="6.8.4",reason="promoção 6.8.4")
            result=service.rollback()
            self.assertEqual(result["restored"]["release"],"6.8.3")
            self.assertTrue(cal.applied)

    @patch("core.grounding_benchmark.MultimodalGroundingBenchmark.run", return_value=report(score=81,recall=81))
    def test_export_report_json_and_csv(self, _run):
        with tempfile.TemporaryDirectory() as td:
            service=RetrievalQualityGateService(FakeKnowledge(),FakeGovernance(),FakeCalibration(baseline()),RetrievalQualityGateStore(td))
            js=service.export_report(release="6.8.4",format="json")
            csv=service.export_report(release="6.8.4",format="csv")
            self.assertEqual(json.loads(js["content"])["gate"]["release"],"6.8.4")
            self.assertIn("release,status,metric",csv["content"])

    def test_release_api_and_ui_expose_quality_gates(self):
        root=Path(__file__).resolve().parents[1]
        self.assertEqual((root/"VERSION.txt").read_text(encoding="utf-8").strip(),"6.24.0")
        self.assertIn('version = "6.24.0"',(root/"pyproject.toml").read_text(encoding="utf-8"))
        self.assertIn('version = "qf-knowledge-engine-3.4"',(root/"core/engines/knowledge_engine.py").read_text(encoding="utf-8"))
        for method in ("get_retrieval_quality_gate","promote_retrieval_release","override_retrieval_quality_gate","rollback_retrieval_release_gate","export_retrieval_quality_gate_report"):
            self.assertIn(method,ALLOWED_API_METHODS)
        html=(root/"web/index.html").read_text(encoding="utf-8")
        js=(root/"web/app.js").read_text(encoding="utf-8")
        self.assertIn('id="openRetrievalQualityGate"',html)
        self.assertIn('Promover release',js)
        self.assertIn('Override auditado',js)
        self.assertIn('Rollback',js)


if __name__ == "__main__":
    unittest.main()
