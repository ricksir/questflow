from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from core.engines import EngineRegistry
from core.question_services import QuestionCommandService, QuestionQueryService
from core.schema_migrations import migration_history
from core.storage import QuestFlowDatabase
from core.study import StudyRepository


class EvaluationGovernance661Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='qf661-')
        self.db=QuestFlowDatabase(Path(self.tmp.name)/'q.sqlite')
        self.study=StudyRepository(self.db)
        self.engines=EngineRegistry.build(
            database=self.db,queries=QuestionQueryService(self.db),commands=QuestionCommandService(self.db),study=self.study
        )
        self.uid=self.db.create_manual_question(None)
        q=self.db.get_question(self.uid); assert q
        q.update({
            'codigo_origem':'Q661-1','id':'Q661-1','materia':'DIREITO TRIBUTÁRIO','assunto':'Suspensão da exigibilidade',
            'enunciado':'Assinale a alternativa correta sobre moratória.','alternativas':[{'chave':'A','texto':'Suspende a exigibilidade.'},{'chave':'B','texto':'Extingue o crédito.'}],
            'gabarito':'A','explicacao':'A moratória suspende a exigibilidade do crédito tributário, conforme art. 151 do CTN.',
            'referencias_legais':['CTN, art. 151'],'ano':2026,'revisao':{'status':'aprovado','confianca':1.0,'alertas':[]},
        })
        self.db.update_question(self.uid,q); self.study.sync_questions()

    def tearDown(self): self.tmp.cleanup()

    def _interaction(self,response,sources):
        iid=self.engines.governance.record_interaction(
            question_uid=self.uid,interaction_type='tutor',mode='professor',provider='test',model='test',prompt_text='prompt',
            response_text=response,learner_context={},sources=sources,diagnosis={'intervention':'Comparar regra e exceção.'}
        )
        ev=self.engines.governance.evaluate(
            iid,response_text=response,mode='professor',official_answer='A',source_texts=[s['content'] for s in sources],
            sources=sources,diagnosis={'intervention':'Comparar regra e exceção.'},question_context={'reference_date':'2026-08-15','currency_status':'vigente'}
        )
        return iid,ev

    def test_migration_v4_and_claim_tables(self):
        with self.db.connect() as c:
            versions=[int(x['version']) for x in migration_history(c) if x['component']=='ai_governance']
            tables={x[0] for x in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertIn(4,versions)
        self.assertTrue({'qf_ai_claims','qf_ai_claim_evidence','qf_gold_run_evaluations'} <= tables)
        self.assertEqual(self.engines.governance.version,'qf-ai-governance-6')

    def test_claims_are_evaluated_and_persisted(self):
        src=[{'title':'CTN comentado','content':'A moratória suspende a exigibilidade do crédito tributário. O art. 151 do CTN prevê hipóteses de suspensão.'}]
        iid,ev=self._interaction('Gabarito: A. A moratória suspende a exigibilidade do crédito tributário conforme art. 151.',src)
        self.assertGreaterEqual(ev['claim_summary']['supported'],1)
        self.assertEqual(ev['claim_summary']['contradicted'],0)
        audit=self.engines.governance.interaction(iid)
        self.assertTrue(audit['claims'])
        self.assertTrue(any(c['verdict']=='suporta' for c in audit['claims']))
        self.assertTrue(any(c['evidence'] for c in audit['claims']))

    def test_contradiction_is_not_rewarded_as_grounding(self):
        src=[{'title':'CTN','content':'A moratória suspende a exigibilidade e não extingue o crédito tributário.'}]
        _,ev=self._interaction('Gabarito: A. A moratória extingue o crédito tributário.',src)
        self.assertGreaterEqual(ev['claim_summary']['contradicted'],1)
        self.assertEqual(ev['status'],'revisar')
        self.assertTrue(any('afirmacoes_contraditas' in f for f in ev['flags']))

    def test_unsupported_legal_reference_is_explicit(self):
        src=[{'title':'Fonte','content':'A moratória suspende a exigibilidade do crédito tributário.'}]
        _,ev=self._interaction('Gabarito: A. Isso decorre do art. 999.',src)
        self.assertTrue(any('referencia_legal_nao_encontrada' in f for f in ev['flags']))
        self.assertGreaterEqual(ev['claim_summary']['insufficient'],1)

    def test_temporal_mismatch_downgrades_claim(self):
        src=[{'title':'Lei futura','source_kind':'legislation','content':'O art. 151-A estabelece uma nova hipótese de suspensão.',
              'metadata':{'canonical_key':'CTN:151-A','effective_from':'2027-01-01','effective_to':''}}]
        _,ev=self._interaction('Gabarito: A. O art. 151-A estabelece essa hipótese.',src)
        self.assertTrue(any('fonte_fora_da_vigencia' in f for f in ev['flags']))
        self.assertTrue(any(c['temporal_status']=='fonte_fora_da_vigencia' for c in ev['claims']))

    def test_gold_regression_records_claim_quality(self):
        self.engines.ai.add_gold_question(self.uid,label='Ouro 661')
        result=self.engines.ai.run_gold_regression()
        self.assertEqual(result['model'],'qf-gold-grounded-baseline-2')
        self.assertEqual(result['evaluator'],'qf-claim-evidence-evaluator-2')
        self.assertIn('claim_summary',result['items'][0])
        dashboard=self.engines.governance.gold_dashboard()
        self.assertIn('claim_support_score',dashboard['last_run'])
        with self.db.connect() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM qf_gold_run_evaluations').fetchone()[0],1)

    def test_generation_critic_exposes_claim_evaluation(self):
        chunks=self.engines.knowledge.retrieve(self.uid,'moratória suspensão',limit=4).get('items',[])
        if not chunks:
            self.skipTest('Índice RAG sem chunks neste fixture')
        result=self.engines.ai.generate_controlled_question(seed_uid=self.uid,source_chunk_ids=[x['id'] for x in chunks],question_type='multipla_escolha')
        validation=result['draft']['validation']
        self.assertIn('claim_evaluation',validation)
        self.assertIn('claim_summary',validation['claim_evaluation'])


if __name__=='__main__': unittest.main()
