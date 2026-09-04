from __future__ import annotations
import tempfile
import unittest
from pathlib import Path
from core.flow import CyclicStudyEngine
from core.storage import QuestFlowDatabase
from core.study import StudyRepository

class StudyInsights693Tests(unittest.TestCase):
    def test_activity_summary_unifies_mobile_and_protects_active_time(self):
        with tempfile.TemporaryDirectory() as temp:
            db=QuestFlowDatabase(Path(temp)/'q.sqlite'); study=StudyRepository(db)
            uid=db.create_manual_question(); q=db.get_question(uid); assert q
            q['materia']='Auditoria'; q['enunciado']='Teste'; q['alternativas']=[{'chave':'A','texto':'A'},{'chave':'B','texto':'B'}]; q['gabarito']='A'; q['telegram']={'modo':'quiz','indice_correto':0,'opcoes':['A','B']}; q.setdefault('revisao',{})['status']='aprovado'; db.update_question(uid,q,change_source='test')
            study.record_local_practice_attempt(uid,0,response_seconds=42,timing_meta={'quality':'active_filtered','source':'active_timer','wall_seconds':3600,'idle_seconds':3558},source='mobile_android')
            summary=study.activity_summary()
            self.assertEqual(summary['attempts'],1); self.assertEqual(summary['mobile_attempts'],1); self.assertEqual(summary['avg_active_seconds'],42.0)
    def test_telegram_question_pause_blocks_new_cycle(self):
        with tempfile.TemporaryDirectory() as temp:
            db=QuestFlowDatabase(Path(temp)/'q.sqlite'); study=StudyRepository(db)
            engine=CyclicStudyEngine(db,study,lambda:{'telegram_questions_paused':True},lambda *_:None)
            result=engine.send_cycle(manual=True)
            self.assertTrue(result['paused']); self.assertEqual(result['sent'],0)

if __name__=='__main__': unittest.main()
