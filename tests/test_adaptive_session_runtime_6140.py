from __future__ import annotations

import json
import tempfile
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from core.mobile_foundation import MobileFoundationService
from core.storage import QuestFlowDatabase
from core.study import StudyRepository
from mobile_cloud_gateway import GatewayStore, PROTOCOL, sha256


class AdaptiveSessionRuntime6140Tests(unittest.TestCase):
    def build_mobile(self, root: Path):
        db = QuestFlowDatabase(root / "questflow.sqlite")
        study = StudyRepository(db)
        mobile = MobileFoundationService(db, study, control_plane_path=root / "mobile_control.sqlite")
        return db, study, mobile

    @staticmethod
    def seed(db: QuestFlowDatabase, n: int = 20) -> None:
        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        rows = []
        for i in range(n):
            uid = f"r{i:03d}"
            data = {
                "uid": uid, "codigo_origem": f"R{i}", "materia": "Direito Tributário" if i < 6 else f"M{i%3}",
                "assunto": "Crédito tributário" if i < 6 else f"T{i%5}", "aula": f"A{i%4}",
                "enunciado": f"Questão runtime {i}",
                "alternativas": [{"chave":"A","texto":"Correta"},{"chave":"B","texto":"Errada"}],
                "gabarito":"A", "revisao":{"status":"aprovado"},
            }
            rows.append((uid,f"src{i}",f"R{i}",f"fp{i}",data["materia"],data["assunto"],data["assunto"],data["aula"],
                         "ok",1.0,"test","CEBRASPE",2026,"O","P","multiple_choice","A",data["enunciado"],"aprovado",1.0,"",None,now,now,json.dumps(data,ensure_ascii=False)))
        with db.connect() as connection:
            connection.executemany(
                """INSERT INTO questions(uid,source_key,source_code,fingerprint,subject,primary_topic,topics_text,lesson,
                taxonomy_status,taxonomy_confidence,taxonomy_source,board,exam_year,agency,exam_name,question_type,answer,
                statement,review_status,confidence,source_file,source_page,created_at,updated_at,data_json)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", rows)

    @staticmethod
    def auth(mobile: MobileFoundationService):
        pairing = mobile.create_pairing(requested_by="runtime")
        exchange = mobile.exchange_pairing(pairing["pairing_token"], {"device_id":"dev614","platform":"android","app_version":"0.10.1"})
        return mobile.authenticate(exchange["access_token"]), exchange["access_token"]

    @staticmethod
    def event(auth, kind, session, uid, seq, payload=None):
        return {
            "event_id": str(uuid.uuid4()), "event_type": kind, "device_id": auth["device_id"], "session_id": session,
            "attempt_id": f"a-{uid}-{seq}", "question_id": uid, "occurred_at": datetime.now(timezone.utc).isoformat(),
            "sequence_no": seq, "client":{"platform":"android","version":"0.10.0"}, "payload": payload or {},
        }

    def test_triaged_item_is_replaced_without_counting_as_attempt(self):
        with tempfile.TemporaryDirectory() as folder:
            db, study, mobile = self.build_mobile(Path(folder)); self.seed(db); study.sync_questions(); auth, _ = self.auth(mobile)
            started = mobile.start_adaptive_study_session(auth, session_id="triage614", count=5, micro_batch_size=3)
            first = started["micro_batch"]["questions"]
            uid = first[0]["question_id"]
            result = mobile.ingest_events(auth, [self.event(auth, "question_correction_requested", "triage614", uid, 1)])
            self.assertTrue(result["ok"])
            nxt = mobile.next_adaptive_micro_batch(auth, "triage614", purpose="active", force_replan=True,
                                                   excluded_uids=[q["question_id"] for q in first])["micro_batch"]
            self.assertTrue(nxt["questions"])
            status = mobile.adaptive_sessions.session_status("triage614", include_questions=True)
            last_decision = status["batches"][-1]["decision"]
            self.assertEqual(last_decision["triaged_without_attempt"], 1)
            self.assertEqual(last_decision["counted_toward_target"], 2)
            self.assertEqual(len(nxt["questions"]), 3)

    def test_session_ended_event_closes_orchestrator_session(self):
        with tempfile.TemporaryDirectory() as folder:
            db, study, mobile = self.build_mobile(Path(folder)); self.seed(db); study.sync_questions(); auth, _ = self.auth(mobile)
            mobile.start_adaptive_study_session(auth, session_id="finish614", count=5, micro_batch_size=3)
            ended = self.event(auth, "session_ended", "finish614", "", 1, {"reason":"completed"})
            ended["attempt_id"] = ""
            result = mobile.ingest_events(auth, [ended])
            self.assertTrue(result["ok"])
            self.assertEqual(mobile.adaptive_sessions.session_status("finish614")["status"], "completed")

    def test_cloud_gateway_reuses_prefetch_as_cached_fallback(self):
        with tempfile.TemporaryDirectory() as folder:
            store = GatewayStore(Path(folder)/"gateway.sqlite")
            tenant, account, learner, token, device = "tenant614", "acc614", "learner614", "secret-token", "cloud-device"
            expires = (datetime.now(timezone.utc)+timedelta(days=1)).isoformat()
            pack=[]
            for i in range(12):
                public={"question_id":f"c{i}","question_revision":1,"subject":f"M{i%3}","topic":f"T{i%4}","lesson":"A1",
                        "statement":f"Cloud {i}","alternatives":[{"index":0,"key":"A","text":"a"},{"index":1,"key":"B","text":"b"}],
                        "study_flags":{"due":False,"wrong_count":0}}
                pack.append({"position":i+1,"public":public,"feedback":{"correct_index":0,"correct_key":"A","explanation":""}})
            store.publish({
                "protocol":PROTOCOL,"published_at":datetime.now(timezone.utc).isoformat(),
                "identity":{"tenant_id":tenant,"account_id":account,"learner_id":learner},
                "sessions":[{"token_hash":sha256(token),"device_id":device,"expires_at":expires,"platform":"android","name":"Cloud","app_version":"0.10.1","status":"active"}],
                "projections":{"bootstrap":{},"today":{},"progress":{}},"study_pack":pack,
            })
            auth=store.authenticate(token)
            start=store.start_cached_adaptive_session(auth,{"session_id":"cloud614","count":8,"micro_batch_size":3})
            first_ids=[q["question_id"] for q in start["micro_batch"]["questions"]]
            pre=store.next_cached_adaptive_batch(auth,"cloud614",{"purpose":"prefetch","excluded_question_ids":first_ids})
            pre_ids=[q["question_id"] for q in pre["micro_batch"]["questions"]]
            promoted=store.next_cached_adaptive_batch(auth,"cloud614",{"purpose":"active","prefetched_batch_id":pre["micro_batch"]["batch_id"],"excluded_question_ids":first_ids})
            self.assertEqual([q["question_id"] for q in promoted["micro_batch"]["questions"]], pre_ids)
            self.assertEqual(promoted["micro_batch"]["strategy_profile"], "offline_fallback")
            self.assertFalse(promoted["micro_batch"]["replan_available"])

    def test_studio_observability_has_no_causal_claim_with_small_sample(self):
        with tempfile.TemporaryDirectory() as folder:
            db, study, mobile = self.build_mobile(Path(folder)); self.seed(db); study.sync_questions(); auth, _ = self.auth(mobile)
            mobile.start_adaptive_study_session(auth, session_id="obs614", count=3)
            readiness=mobile.adaptive_sessions.evaluation_readiness()
            self.assertEqual(readiness["status"], "insufficient_sample")
            self.assertEqual(readiness["primary_outcome"], "delayed_retention_and_future_mastery")
            self.assertIn("Acurácia imediata", readiness["warning"])


if __name__ == "__main__":
    unittest.main()
