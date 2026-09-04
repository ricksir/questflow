from __future__ import annotations

import json
import tempfile
import unittest
import uuid
from datetime import datetime, timezone
from pathlib import Path

from core.mobile_foundation import MobileFoundationService
from core.storage import QuestFlowDatabase
from core.study import StudyRepository


class MobileOfflinePack6160Tests(unittest.TestCase):
    def build(self, root: Path):
        db = QuestFlowDatabase(root / "questflow.sqlite")
        study = StudyRepository(db)
        mobile = MobileFoundationService(db, study, control_plane_path=root / "mobile_control.sqlite")
        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        rows = []
        for index in range(40):
            uid = f"offline-{index:03d}"
            subject = f"Matéria {index % 4}"
            topic = f"Assunto {index % 8}"
            data = {
                "uid": uid, "codigo_origem": f"OFF{index}", "materia": subject,
                "assunto": topic, "aula": f"Aula {index % 10}", "enunciado": f"Questão offline {index}",
                "alternativas": [{"chave": "A", "texto": "Correta"}, {"chave": "B", "texto": "Incorreta"}],
                "gabarito": "A", "revisao": {"status": "aprovado"},
            }
            rows.append((uid, f"s{index}", f"OFF{index}", f"f{index}", subject, topic, topic, f"Aula {index % 10}",
                         "ok", 1.0, "test", "CEBRASPE", 2026, "Órgão", "Prova", "multiple_choice", "A",
                         f"Questão offline {index}", "aprovado", 1.0, "", None, now, now, json.dumps(data, ensure_ascii=False)))
        with db.connect() as connection:
            connection.execute("""CREATE TABLE IF NOT EXISTS qf_exam_projects(
                id TEXT PRIMARY KEY,name TEXT,agency TEXT,role TEXT,board TEXT,exam_date TEXT,status TEXT,active INTEGER
            )""")
            connection.executemany(
                """INSERT INTO questions(uid,source_key,source_code,fingerprint,subject,primary_topic,topics_text,lesson,
                taxonomy_status,taxonomy_confidence,taxonomy_source,board,exam_year,agency,exam_name,question_type,answer,
                statement,review_status,confidence,source_file,source_page,created_at,updated_at,data_json)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", rows)
        study.sync_questions()
        pairing = mobile.create_pairing(requested_by="6160")
        exchange = mobile.exchange_pairing(pairing["pairing_token"], {
            "device_id": "offline-6160", "platform": "android", "name": "Test", "app_version": "0.11.0"
        })
        auth = mobile.authenticate(exchange["access_token"])
        return db, study, mobile, auth, exchange["access_token"]

    def test_offline_pack_is_selected_by_central_study_stack_and_contains_no_answer(self):
        with tempfile.TemporaryDirectory() as folder:
            _db, _study, mobile, auth, _token = self.build(Path(folder))
            pack = mobile.offline_study_pack(auth, count=20)
            self.assertEqual(pack["contract"], "questflow.mobile.offline_study_pack.v1")
            self.assertEqual(pack["source"], "studio_learning_engine")
            self.assertFalse(pack["adaptive_while_offline"])
            self.assertEqual(len(pack["questions"]), 20)
            self.assertTrue(pack["selection_policy"])
            self.assertTrue(pack["core_policy"])
            for question in pack["questions"]:
                self.assertNotIn("answer", question)
                self.assertNotIn("correct_index", question)
                self.assertTrue(question.get("selection", {}).get("core_policy"))

    def test_sync_applies_events_before_refreshing_offline_reserve(self):
        with tempfile.TemporaryDirectory() as folder:
            db, _study, mobile, auth, token = self.build(Path(folder))
            first = mobile.offline_study_pack(auth, count=10)["questions"][0]
            event = {
                "event_id": str(uuid.uuid4()), "event_type": "answer_submitted", "device_id": auth["device_id"],
                "session_id": "offline-session", "attempt_id": "offline-attempt", "question_id": first["question_id"],
                "question_revision": first["question_revision"], "occurred_at": datetime.now(timezone.utc).isoformat(),
                "sequence_no": 1, "client": {"platform": "android", "version": "0.11.0"},
                "payload": {"selected_index": 1, "confidence": "medium", "active_response_seconds": 15,
                            "timing_source": "client_active_timer_v1"},
            }
            status, payload = mobile.http_request(
                method="POST", path="/api/v1/mobile/sync", headers={"Authorization": f"Bearer {token}"},
                body={"cursor": 0, "events": [event], "offline_pack_size": 12, "refresh_offline_pack": True}, query={},
            )
            self.assertEqual(status, 200)
            self.assertTrue(payload["push"]["accepted"])
            self.assertEqual(payload["offline_study_pack"]["source"], "studio_learning_engine")
            self.assertEqual(len(payload["offline_study_pack"]["questions"]), 12)
            with db.connect() as connection:
                row = connection.execute("SELECT process_status FROM qf_learning_events WHERE event_id=?", (event["event_id"],)).fetchone()
            self.assertEqual(str(row["process_status"]), "applied")

    def test_pack_refresh_is_a_new_snapshot_not_a_mobile_pedagogical_state(self):
        with tempfile.TemporaryDirectory() as folder:
            _db, _study, mobile, auth, _token = self.build(Path(folder))
            first = mobile.offline_study_pack(auth, count=8)
            second = mobile.offline_study_pack(auth, count=8)
            self.assertNotEqual(first["pack_id"], second["pack_id"])
            self.assertEqual(first["source"], "studio_learning_engine")
            self.assertEqual(second["source"], "studio_learning_engine")
            self.assertFalse(first["adaptive_while_offline"])
            self.assertFalse(second["adaptive_while_offline"])



if __name__ == "__main__":
    unittest.main()
