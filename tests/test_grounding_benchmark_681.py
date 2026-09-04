from __future__ import annotations

import unittest

from core.grounding_benchmark import MultimodalGroundingBenchmark, evaluate_retrieval
from web_server import ALLOWED_API_METHODS


class FakeKnowledge:
    def retrieve_multimodal(self, uid, query, *, limit=8, backend='hybrid'):
        text = {"id":"chunk-1","title":"Comentário ouro","content":"A regra correta decorre da lei e confirma o gabarito.","modality":"text","grounding":{"source_id":"chunk-1"}}
        visual = {"id":"visual-1","title":"Evidência visual local","content":"Figura da questão confirma o contexto da regra.","modality":"visual","grounding":{"source_id":"visual-1","source_page":2}}
        if backend == 'text': items=[text]
        elif backend == 'visual': items=[visual]
        else: items=[visual,text]
        return {"items":items,"backend":backend,"external_binary_shared":False}


class FakeGovernance:
    def gold_questions(self, active_only=True):
        return [{
            "id":"gold-1","question_uid":"q-1","source_code":"Q1","subject":"DIREITO",
            "sources":[{"id":"chunk-1","title":"Comentário ouro","content":"A regra correta decorre da lei e confirma o gabarito."}],
            "question":{"database_uid":"q-1","codigo_origem":"Q1","enunciado":"Assinale a correta.","explicacao":"A regra correta decorre da lei e confirma o gabarito.","contexto_visual":{"descricao":"Figura da questão"}},
        }]


class GroundingBenchmark681Tests(unittest.TestCase):
    def test_evaluate_retrieval_matches_gold_and_grounding(self):
        question={"explicacao":"A regra correta decorre da lei e confirma o gabarito."}
        expected=[{"id":"chunk-1","title":"Comentário ouro","content":"A regra correta decorre da lei e confirma o gabarito."}]
        result={"items":[{"id":"chunk-1","title":"Comentário ouro","content":"A regra correta decorre da lei e confirma o gabarito.","modality":"text","grounding":{"source_id":"chunk-1"}}]}
        metric=evaluate_retrieval(question=question,expected_sources=expected,result=result,backend='text')
        self.assertEqual(metric['precision'],100.0)
        self.assertEqual(metric['recall'],100.0)
        self.assertEqual(metric['grounding_rate'],100.0)
        self.assertGreaterEqual(metric['commentary_support'],90)

    def test_benchmark_compares_three_backends_and_hybrid_gain(self):
        report=MultimodalGroundingBenchmark(FakeKnowledge(),FakeGovernance()).run(limit=10)
        self.assertEqual(report['version'],'qf-grounding-benchmark-1')
        self.assertEqual(report['cases'],1)
        self.assertEqual({x['backend'] for x in report['backends']},{'text','visual','hybrid'})
        self.assertIn('hybrid_gain',report)
        self.assertEqual(report['sample_status'],'insuficiente')

    def test_path_leak_is_flagged(self):
        question={"explicacao":"texto de referência","imagem_questao":{"path":"C:/segredo/questao.png"}}
        result={"items":[{"content":"C:/segredo/questao.png texto de referência","grounding":{},"modality":"visual"}]}
        metric=evaluate_retrieval(question=question,expected_sources=[],result=result,backend='visual')
        self.assertFalse(metric['local_path_safe'])
        self.assertIn('caminho_local_exposto',metric['flags'])

    def test_http_method_is_allowlisted(self):
        self.assertIn('run_multimodal_grounding_benchmark', ALLOWED_API_METHODS)

    def test_ui_contains_benchmark_action(self):
        from pathlib import Path
        root=Path(__file__).resolve().parents[1]
        self.assertIn('Benchmark RAG 3.0',(root/'web/index.html').read_text(encoding='utf-8'))
        js=(root/'web/app.js').read_text(encoding='utf-8')
        self.assertIn('openGroundingBenchmark',js)
        self.assertIn('run_multimodal_grounding_benchmark',js)


if __name__ == '__main__':
    unittest.main()
