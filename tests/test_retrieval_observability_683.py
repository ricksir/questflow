import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.retrieval_observability import (
    RetrievalObservabilityService, RetrievalObservabilityStore, compare_index_drift,
)


class FakeKnowledge:
    def __init__(self):
        self.retrieval_calibration_store = type("Cal", (), {"current": lambda self: {"id":"balanced-v1","label":"Balanceado","weights":{}}})()
        self._snapshot = {
            "coverage": 98.0, "rag_chunks": 3, "source_count": 2, "index_digest":"abc",
            "chunk_fingerprints":{"a":"1","b":"2","c":"3"}, "source_fingerprints":{"s1":"x","s2":"y"},
            "by_subject":{"AUDITORIA":2,"TRIBUTARIO":1}, "by_source_kind":{"question":3},
        }
    def observability_snapshot(self): return dict(self._snapshot)


class FakeGovernance:
    def gold_questions(self, active_only=True):
        return [{"id":"g1","question_uid":"q1","subject":"AUDITORIA"}]


class FakeEditorial:
    def question_candidates(self, limit=200):
        return [
            {"uid":"q1","source_code":"Q1","subject":"AUDITORIA","answer":"C","quality_score":95,"review_status":"aprovado","commentary_source":"manual"},
            {"uid":"q2","source_code":"Q2","subject":"TRIBUTARIO","primary_topic":"CTN","answer":"E","quality_score":91,"review_status":"aprovado","commentary_source":"ia_assistida"},
            {"uid":"q3","source_code":"Q3","subject":"AFO","primary_topic":"LOA","answer":"C","quality_score":82,"review_status":"pendente","commentary_source":"manual"},
        ]


def fake_report(*_args, **_kwargs):
    return {
        "version":"qf-grounding-benchmark-1","cases":4,"sample_status":"suficiente",
        "backends":[{"backend":"hybrid","score":80,"grounding_rate":100,"recall":75,"commentary_support":80,"precision":80,"visual_coverage":100,"path_safety":100}],
        "items":[{"subject":"AUDITORIA","backends":[{"backend":"hybrid","composite_score":82,"grounding_rate":100,"recall":80}]},
                 {"subject":"TRIBUTARIO","backends":[{"backend":"hybrid","composite_score":78,"grounding_rate":100,"recall":70}]}],
    }


class RetrievalObservability683Tests(unittest.TestCase):
    def test_drift_detects_changed_added_removed(self):
        old={"coverage":90,"chunk_fingerprints":{"a":"1","b":"2"},"source_fingerprints":{"s1":"x"}}
        cur={"coverage":92,"chunk_fingerprints":{"a":"9","c":"3"},"source_fingerprints":{"s1":"z","s2":"y"}}
        drift=compare_index_drift(cur,old)
        self.assertEqual(drift["status"],"drift")
        self.assertEqual(drift["changed_chunks"],1)
        self.assertEqual(drift["added_chunks"],1)
        self.assertEqual(drift["removed_chunks"],1)
        self.assertEqual(drift["coverage_delta"],2.0)

    @patch("core.grounding_benchmark.MultimodalGroundingBenchmark.run", side_effect=lambda *a, **k: fake_report())
    def test_dashboard_records_history_and_deduplicates(self, _run):
        with tempfile.TemporaryDirectory() as td:
            store=RetrievalObservabilityStore(td)
            service=RetrievalObservabilityService(FakeKnowledge(),FakeGovernance(),FakeEditorial(),store)
            first=service.dashboard(release="6.8.3",record=True)
            second=service.dashboard(release="6.8.3",record=True)
            self.assertTrue(first["recorded"])
            self.assertFalse(second["recorded"])
            self.assertEqual(len(store.history()),1)
            self.assertIn("index",first)

    def test_gold_expansion_never_auto_approves(self):
        with tempfile.TemporaryDirectory() as td:
            service=RetrievalObservabilityService(FakeKnowledge(),FakeGovernance(),FakeEditorial(),RetrievalObservabilityStore(td))
            result=service.suggest_gold_expansion(limit=10)
            self.assertFalse(result["auto_apply"])
            self.assertTrue(result["suggestions"])
            self.assertNotIn("q1",{x["uid"] for x in result["suggestions"]})
            self.assertTrue(all(x["requires_human_approval"] and not x["auto_approved"] for x in result["suggestions"]))

    @patch("core.grounding_benchmark.MultimodalGroundingBenchmark.run", side_effect=lambda *a, **k: fake_report())
    def test_exports_json_and_csv(self, _run):
        with tempfile.TemporaryDirectory() as td:
            service=RetrievalObservabilityService(FakeKnowledge(),FakeGovernance(),FakeEditorial(),RetrievalObservabilityStore(td))
            service.dashboard(release="6.8.3",record=True)
            js=service.export_report(release="6.8.3",format="json")
            csv=service.export_report(release="6.8.3",format="csv")
            self.assertEqual(json.loads(js["content"])["dashboard"]["release"],"6.8.3")
            self.assertIn("timestamp,release,profile",csv["content"])

    def test_release_files_expose_683_features(self):
        root=Path(__file__).resolve().parents[1]
        self.assertEqual((root/"VERSION.txt").read_text(encoding="utf-8").strip(),"6.23.2")
        self.assertIn('version = "6.23.2"',(root/"pyproject.toml").read_text(encoding="utf-8"))
        self.assertIn('version = "qf-knowledge-engine-3.4"',(root/"core/engines/knowledge_engine.py").read_text(encoding="utf-8"))
        server=(root/"web_server.py").read_text(encoding="utf-8")
        for name in ("get_retrieval_observability","record_retrieval_observability","suggest_gold_question_expansion","export_retrieval_observability_report"):
            self.assertIn(f'"{name}"',server)
        html=(root/"web/index.html").read_text(encoding="utf-8")
        self.assertIn('id="openRetrievalObservability"',html)


if __name__ == "__main__":
    unittest.main()
