from __future__ import annotations

import json
import tempfile
import unittest
import urllib.request
from pathlib import Path

from core.engines import EngineRegistry
from core.question_services import QuestionCommandService, QuestionQueryService
from core.schema_migrations import migration_history
from core.storage import QuestFlowDatabase
from core.study import StudyRepository, SelectionFilters
from web_server import ALLOWED_API_METHODS, QuestFlowLocalServer

BASE = Path(__file__).resolve().parents[1]


class ExamProjectEdtial650Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp=tempfile.TemporaryDirectory(prefix='qf-650-')
        self.db=QuestFlowDatabase(Path(self.tmp.name)/'q.sqlite')
        self.study=StudyRepository(self.db)
        self.study.set_learning_preferences(studied_only=False, early_review_enabled=True)
        self.engines=EngineRegistry.build(database=self.db,queries=QuestionQueryService(self.db),commands=QuestionCommandService(self.db),study=self.study)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def question(self,index:int,subject='DIREITO TRIBUTÁRIO',topic='Crédito Tributário',law='') -> str:
        uid=self.db.create_manual_question(None)
        q=self.db.get_question(uid); assert q
        q.update({'codigo_origem':f'Q650-{index}','id':f'Q650-{index}','materia':subject,'assunto':topic,'assuntos':[topic],
                  'banca':'CEBRASPE','ano':2021,'enunciado':f'Questão {index} sobre {topic}','gabarito':'A',
                  'referencias_legais':[law] if law else [],'revisao':{'status':'aprovado','confianca':1,'alertas':[]}})
        self.db.update_question(uid,q); self.study.sync_questions(); return uid

    def test_question_bank_v8_and_six_engines_preserved(self):
        with self.db.connect() as c:
            versions=[int(r['version']) for r in migration_history(c) if r['component']=='question_bank']
            tables={r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertEqual(max(versions),9)
        self.assertTrue({'qf_exam_projects','qf_exam_versions','qf_exam_syllabus_items','qf_exam_question_links','qf_question_currency'}.issubset(tables))
        arch=self.engines.architecture(); self.assertGreaterEqual(arch['engine_count'],6); self.assertTrue(arch['extensible'])
        self.assertIn('exam_project_centric',arch['principles'])
        editorial=next(i for i in arch['engines'] if i['id']=='editorial_bank')
        learning=next(i for i in arch['engines'] if i['id']=='learning_engine')
        self.assertEqual(editorial['version'],'qf-editorial-engine-3')
        self.assertEqual(learning['version'],'qf-learning-engine-6')

    def test_project_version_diff_autolink_coverage_and_today(self):
        for i in range(5): self.question(i,topic='Crédito Tributário' if i<3 else 'Suspensão da exigibilidade')
        p=self.engines.editorial.upsert_exam_project({'name':'RFB · Auditor-Fiscal','agency':'RFB','role':'Auditor-Fiscal','board':'CEBRASPE','exam_date':'2026-12-06','active':True})
        dash=self.engines.editorial.add_exam_version(p['id'],{'label':'Edital inicial','published_at':'2026-08-01','content_text':'DIREITO TRIBUTÁRIO: Crédito Tributário; Suspensão da exigibilidade'})
        self.assertEqual(dash['coverage']['items'],2)
        self.assertGreaterEqual(dash['coverage']['covered'],1)
        dash2=self.engines.editorial.add_exam_version(p['id'],{'label':'Retificação 1','published_at':'2026-08-10','content_text':'DIREITO TRIBUTÁRIO: Crédito Tributário; Suspensão da exigibilidade; ITCMD'})
        self.assertEqual(dash2['version']['version_no'],2)
        self.assertEqual(dash2['diff']['counts']['added'],1)
        today=self.engines.learning.today_dashboard(p['id'])
        self.assertEqual(today['project']['id'],p['id'])
        self.assertIn('coverage',today)
        self.assertTrue(today['principles'])

    def test_currency_status_excludes_question_from_normal_selection(self):
        uid1=self.question(1); uid2=self.question(2)
        before={q['database_uid'] for q in self.study.select_questions(SelectionFilters(subjects=[], approved_only=True),10)}
        self.assertIn(uid1,before)
        self.engines.editorial.set_question_currency(uid1,'desatualizada',reason='Norma alterada')
        after={q['database_uid'] for q in self.study.select_questions(SelectionFilters(subjects=[], approved_only=True),10)}
        self.assertNotIn(uid1,after); self.assertIn(uid2,after)
        with self.db.connect() as c:
            self.assertIsNotNone(c.execute('SELECT 1 FROM questions WHERE uid=?',(uid1,)).fetchone())

    def test_temporal_scan_flags_old_question_when_norm_changed(self):
        uid=self.question(1,law='CTN_ART_151')
        self.engines.editorial.upsert_legislation({'canonical_key':'CTN_ART_151','title':'CTN art. 151','effective_from':'2024-01-01','text_content':'Texto legal atualizado para fins de teste com conteúdo suficiente e fundamentação oficial.'})
        p=self.engines.editorial.upsert_exam_project({'name':'Projeto temporal','exam_date':'2026-12-01','active':True})
        result=self.engines.editorial.scan_question_currency(p['id'])
        self.assertGreaterEqual(result['flagged'],1)
        item=next(x for x in result['items'] if x['question_uid']==uid)
        self.assertEqual(item['status'],'potencialmente_desatualizada')

    def test_frontend_and_allowlist(self):
        required={'get_today_dashboard','get_exam_project_dashboard','save_exam_project','set_active_exam_project','parse_edital_text','add_edital_version','relink_exam_project','scan_question_currency','set_question_currency'}
        self.assertTrue(required.issubset(ALLOWED_API_METHODS))
        html=(BASE/'web/index.html').read_text(encoding='utf-8'); js=(BASE/'web/app.js').read_text(encoding='utf-8')
        self.assertIn('data-route="examproject"',html); self.assertIn('data-page="examproject"',html); self.assertIn('id="todayPanel"',html)
        self.assertIn('async function loadExamProjectPage',js); self.assertIn('async function loadTodayDashboard',js)
        for method in required: self.assertIn(method,js)


class LocalHttp650Tests(unittest.TestCase):
    def test_http_routes(self):
        class Dummy:
            def get_today_dashboard(self,project_id=''): return {'ok':True,'today':{'project':None}}
            def get_exam_project_dashboard(self,project_id=''): return {'ok':True,'dashboard':{'project':None}}
            def parse_edital_text(self,text=''): return {'ok':True,'items':[],'count':0}
        server=QuestFlowLocalServer(Dummy(),BASE/'web',preferred_port=0); server.start()
        try:
            for method,args in [('get_today_dashboard',[]),('get_exam_project_dashboard',[]),('parse_edital_text',['DIREITO: CTN'])]:
                req=urllib.request.Request(f'{server.base_url}/api/call',data=json.dumps({'method':method,'args':args}).encode(),headers={'Content-Type':'application/json','X-QuestFlow-Token':server.token},method='POST')
                with urllib.request.urlopen(req,timeout=5) as resp: out=json.loads(resp.read().decode())
                self.assertTrue(out['ok']); self.assertTrue(out['result']['ok'])
        finally: server.stop()

if __name__=='__main__': unittest.main()
