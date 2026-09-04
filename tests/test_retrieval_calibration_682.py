from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from core.retrieval_calibration import (
    DEFAULT_PROFILE, RetrievalCalibrationService, RetrievalCalibrationStore,
    benchmark_snapshot, compare_regression, profile_by_id, rerank_items,
)
from web_server import ALLOWED_API_METHODS


class FakeKnowledge:
    def retrieve_multimodal(self, uid, query, *, limit=8, backend='hybrid'):
        text_good={"id":"gold","title":"Fonte ouro","content":f"{query} fundamento correto lei norma auditoria","modality":"text","scores":{"score":.75},"grounding":{"source_id":"gold"}}
        text_noise={"id":"noise","title":"Ruído","content":"conteúdo genérico sem relação","modality":"text","scores":{"score":.95},"grounding":{"source_id":"noise"}}
        visual={"id":"visual","title":"Figura","content":"figura contexto visual","modality":"visual","scores":{"score":1},"grounding":{"source_id":"visual"}}
        if backend=='text': return {"items":[text_noise,text_good]}
        if backend=='visual': return {"items":[visual]}
        return {"items":[visual,text_noise,text_good]}


class FakeGovernance:
    def gold_questions(self, active_only=True):
        rows=[]
        for i in range(4):
            rows.append({"id":f"g{i}","question_uid":f"q{i}","subject":"AUDITORIA","sources":[{"id":"gold","title":"Fonte ouro","content":"fundamento correto lei norma auditoria"}],"question":{"database_uid":f"q{i}","materia":"AUDITORIA","enunciado":"fundamento correto lei norma auditoria","explicacao":"fundamento correto lei norma auditoria"}})
        return rows


class RetrievalCalibration682Tests(unittest.TestCase):
    def test_reranking_is_explicit_and_query_aware(self):
        items=[
            {"id":"noise","content":"texto genérico","modality":"text","scores":{"score":1.0},"grounding":{"source_id":"noise"}},
            {"id":"good","content":"auditoria norma evidência correta","modality":"text","scores":{"score":.65},"grounding":{"source_id":"good"}},
        ]
        profile=profile_by_id('text-relevance-v1')
        ranked=rerank_items(items,query='auditoria norma evidência correta',question={},profile=profile)
        self.assertEqual(ranked[0]['id'],'good')
        self.assertEqual(ranked[0]['reranking']['profile_id'],'text-relevance-v1')
        self.assertIn('features',ranked[0]['reranking'])

    def test_calibration_recommends_but_does_not_auto_apply(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=RetrievalCalibrationStore(tmp)
            before=store.current()['id']
            report=RetrievalCalibrationService(FakeKnowledge(),FakeGovernance(),store).calibrate(limit=10)
            self.assertEqual(report['cases'],4)
            self.assertFalse(report['auto_apply'])
            self.assertEqual(store.current()['id'],before)
            self.assertIn('objective',report)
            self.assertGreaterEqual(len(report['candidates']),4)

    def test_profile_history_supports_rollback(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=RetrievalCalibrationStore(tmp)
            store.apply(profile_by_id('grounding-first-v1'))
            self.assertEqual(store.current()['id'],'grounding-first-v1')
            rolled=store.rollback()
            self.assertEqual(rolled['active']['id'],DEFAULT_PROFILE['id'])

    def test_regression_detects_global_and_subject_drop(self):
        baseline={"hybrid":{"score":80,"recall":82,"grounding_rate":100},"subjects":{"AUDITORIA":{"score":82,"recall":84,"grounding_rate":100}}}
        current={"hybrid":{"score":72,"recall":70,"grounding_rate":94},"subjects":{"AUDITORIA":{"score":72,"recall":70,"grounding_rate":94}}}
        result=compare_regression(current,baseline)
        self.assertEqual(result['status'],'regressao')
        self.assertTrue(any(x['scope']=='subject' for x in result['alerts']))

    def test_snapshot_groups_by_subject(self):
        report={"version":"b1","cases":1,"sample_status":"insuficiente","backends":[{"backend":"hybrid","score":80,"recall":75,"grounding_rate":100}],"items":[{"subject":"AUDITORIA","backends":[{"backend":"hybrid","composite_score":80,"recall":75,"grounding_rate":100}]}]}
        snap=benchmark_snapshot(report,release='6.8.2')
        self.assertEqual(snap['release'],'6.8.2')
        self.assertEqual(snap['subjects']['AUDITORIA']['score'],80.0)

    def test_http_and_ui_expose_calibration_controls(self):
        for method in ('run_retrieval_calibration','apply_retrieval_calibration','rollback_retrieval_calibration','save_retrieval_regression_baseline','get_retrieval_regression_status'):
            self.assertIn(method,ALLOWED_API_METHODS)
        root=Path(__file__).resolve().parents[1]
        html=(root/'web/index.html').read_text(encoding='utf-8')
        js=(root/'web/app.js').read_text(encoding='utf-8')
        self.assertIn('Calibrar retrieval',html)
        self.assertIn('openRetrievalCalibration',js)
        self.assertIn('Aplicar perfil recomendado',js)


if __name__=='__main__':
    unittest.main()
