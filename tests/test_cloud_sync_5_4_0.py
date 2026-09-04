from __future__ import annotations

import copy
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from contextlib import closing
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))

from core.cloud_sync import (  # noqa: E402
    CloudSyncEngine,
    TursoHttpClient,
    TursoHttpError,
    normalize_turso_url,
)
from core.storage import QuestFlowDatabase  # noqa: E402
from core.study import StudyRepository  # noqa: E402
from core.network import NetworkManager  # noqa: E402


class FakeRemote:
    """Deterministic in-memory Turso stand-in for failure/convergence tests."""

    def __init__(self) -> None:
        self.generation = 1
        self.events: list[dict] = []
        self.seen: set[str] = set()
        self.seq = 0
        self.offline = False
        self.fail_after_commit_once = False
        self.devices: dict[str, str] = {}
        self._lock = threading.RLock()

    def _check(self) -> None:
        if self.offline:
            raise OSError("rede indisponível")

    def ensure_schema(self) -> None:
        self._check()

    def get_generation(self) -> int:
        self._check()
        return self.generation

    def set_generation(self, generation: int) -> None:
        self._check()
        self.generation = max(self.generation, int(generation))

    def touch_device(self, device_id: str, name: str) -> None:
        self._check()
        self.devices[device_id] = name

    def append_events(self, events) -> int:
        self._check()
        written = 0
        with self._lock:
            for item in events:
                event_id = str(item["event_id"])
                if event_id in self.seen:
                    continue
                self.seq += 1
                event = copy.deepcopy(dict(item))
                event["seq"] = self.seq
                self.events.append(event)
                self.seen.add(event_id)
                written += 1
            if self.fail_after_commit_once:
                self.fail_after_commit_once = False
                raise OSError("conexão caiu após commit remoto")
        return written

    def fetch_events(self, after_seq: int, generation: int, *, limit: int = 500):
        self._check()
        with self._lock:
            return [copy.deepcopy(item) for item in self.events if int(item["seq"]) > int(after_seq)][:limit]

    def event_count(self) -> int:
        self._check()
        return len(self.events)

    def test(self):
        self._check()
        return {"ok": True, "generation": self.generation, "elapsed_ms": 1}


def make_device(folder: Path, remote: FakeRemote, *, name: str = "TEST"):
    folder.mkdir(parents=True, exist_ok=True)
    db_path = folder / "questflow.sqlite"
    db = QuestFlowDatabase(db_path)
    study = StudyRepository(db)
    config = {
        "cloud_sync_enabled": True,
        "cloud_turso_url": "https://unit.invalid",
        "cloud_device_name": name,
        "cloud_sync_interval_seconds": 30,
        "cloud_sync_timeout_seconds": 2,
        "cloud_sync_on_start": True,
        "cloud_sync_on_shutdown": True,
        "mobile_lan_enabled": False,
    }
    cfg = folder / "config.json"
    cfg.write_text(json.dumps(config), encoding="utf-8")
    engine = CloudSyncEngine(db_path, config=config, config_path=cfg, remote_client=remote, reset_callback=study.reset_progress, auth_token="unit")
    return db, study, config, engine


class CloudSyncCompatibilityTests(unittest.TestCase):
    def test_url_normalization_accepts_turso_and_https(self):
        self.assertEqual(normalize_turso_url("turso://abc-example.turso.io"), "https://abc-example.turso.io")
        self.assertEqual(normalize_turso_url("https://abc-example.turso.io/"), "https://abc-example.turso.io")
        with self.assertRaises(ValueError):
            normalize_turso_url("ftp://example.test")

    def test_committed_question_is_durable_in_outbox(self):
        remote = FakeRemote()
        with tempfile.TemporaryDirectory() as tmp:
            db, study, _, engine = make_device(Path(tmp), remote)
            uid = db.create_manual_question()
            study.sync_questions()
            self.assertTrue(uid)
            self.assertGreaterEqual(engine.pending_count(), 2)  # question + study_state
            with closing(sqlite3.connect(db.path)) as conn:
                self.assertEqual(conn.execute("PRAGMA integrity_check").fetchone()[0], "ok")

    def test_two_devices_converge_even_if_never_online_together(self):
        remote = FakeRemote()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db_a, study_a, _, a = make_device(root / "a", remote, name="CASA")
            db_b, study_b, _, b = make_device(root / "b", remote, name="TRABALHO")
            uid = db_a.create_manual_question()
            question = db_a.get_question(uid)
            question["materia"] = "DIREITO TRIBUTÁRIO"
            question["enunciado"] = "Questão criada em casa"
            db_a.update_question(uid, question)
            study_a.sync_questions()
            result_a = a.sync_once()
            self.assertTrue(result_a["ok"], result_a)

            # A can now be completely off. B syncs later against cloud only.
            result_b = b.sync_once()
            self.assertTrue(result_b["ok"], result_b)
            received = db_b.get_question(uid)
            self.assertIsNotNone(received)
            self.assertEqual(received["materia"], "DIREITO TRIBUTÁRIO")

            received["enunciado"] = "Alterada no trabalho sem o PC de casa"
            db_b.update_question(uid, received)
            self.assertTrue(b.sync_once()["ok"])
            # Later A comes back.
            self.assertTrue(a.sync_once()["ok"])
            self.assertEqual(db_a.get_question(uid)["enunciado"], "Alterada no trabalho sem o PC de casa")

    def test_offline_keeps_local_work_and_pending_queue(self):
        remote = FakeRemote()
        with tempfile.TemporaryDirectory() as tmp:
            db, _, _, engine = make_device(Path(tmp), remote)
            uid = db.create_manual_question()
            before = engine.pending_count()
            remote.offline = True
            result = engine.sync_once()
            self.assertFalse(result["ok"])
            self.assertGreaterEqual(engine.pending_count(), before)
            self.assertIsNotNone(db.get_question(uid))
            remote.offline = False
            self.assertTrue(engine.sync_once()["ok"])
            self.assertEqual(engine.pending_count(), 0)

    def test_retry_after_remote_commit_before_ack_is_idempotent(self):
        remote = FakeRemote()
        with tempfile.TemporaryDirectory() as tmp:
            db, _, _, engine = make_device(Path(tmp), remote)
            db.create_manual_question()
            pending = engine.pending_count()
            remote.fail_after_commit_once = True
            first = engine.sync_once()
            self.assertFalse(first["ok"])
            self.assertEqual(engine.pending_count(), pending)
            event_ids_after_first = {e["event_id"] for e in remote.events}
            second = engine.sync_once()
            self.assertTrue(second["ok"], second)
            self.assertEqual(engine.pending_count(), 0)
            self.assertEqual(len(remote.events), len({e["event_id"] for e in remote.events}))
            self.assertTrue(event_ids_after_first.issubset({e["event_id"] for e in remote.events}))

    def test_abrupt_process_exit_after_commit_recovers_outbox(self):
        remote = FakeRemote()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db, study, _, engine = make_device(root, remote)
            # A child simulates a hard power/process loss using os._exit after a committed write.
            code = f'''\nimport os, sys\nsys.path.insert(0, {str(BASE)!r})\nfrom core.storage import QuestFlowDatabase\nfrom core.study import StudyRepository\nfrom core.cloud_sync import CloudSyncEngine\np={str(db.path)!r}\ndb=QuestFlowDatabase(p)\nstudy=StudyRepository(db)\nengine=CloudSyncEngine(p, config={{"cloud_sync_enabled": True,"cloud_device_name":"CRASH"}}, config_path={str(root / "config.json")!r}, remote_client=None, auth_token="x")\ndb.create_manual_question()\nos._exit(37)\n'''
            proc = subprocess.run([sys.executable, "-c", code], cwd=BASE, check=False)
            self.assertEqual(proc.returncode, 37)
            with closing(sqlite3.connect(db.path)) as conn:
                self.assertEqual(conn.execute("PRAGMA integrity_check").fetchone()[0], "ok")
                self.assertGreater(conn.execute("SELECT COUNT(*) FROM qf_sync_outbox").fetchone()[0], 0)
                self.assertGreater(conn.execute("SELECT COUNT(*) FROM questions").fetchone()[0], 0)

    def test_abrupt_exit_mid_transaction_rolls_back_cleanly(self):
        remote = FakeRemote()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db, _, _, _ = make_device(root, remote)
            code = f'''\nimport os, sqlite3\np={str(db.path)!r}\nc=sqlite3.connect(p)\nc.execute("PRAGMA journal_mode=WAL")\nc.execute("BEGIN IMMEDIATE")\nc.execute("INSERT INTO imports(id,source_file,imported_at,metadata_json) VALUES('CRASH-MID','x','x','{{}}')")\nos._exit(41)\n'''
            proc = subprocess.run([sys.executable, "-c", code], cwd=BASE, check=False)
            self.assertEqual(proc.returncode, 41)
            with closing(sqlite3.connect(db.path)) as conn:
                self.assertEqual(conn.execute("PRAGMA integrity_check").fetchone()[0], "ok")
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM imports WHERE id='CRASH-MID'").fetchone()[0], 0)

    def test_conflicting_offline_edits_are_audited_and_last_push_converges(self):
        remote = FakeRemote()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db_a, _, _, a = make_device(root / "a", remote, name="A")
            db_b, _, _, b = make_device(root / "b", remote, name="B")
            uid = db_a.create_manual_question()
            self.assertTrue(a.sync_once()["ok"])
            self.assertTrue(b.sync_once()["ok"])

            qa = db_a.get_question(uid); qb = db_b.get_question(uid)
            qa["enunciado"] = "edição A offline"
            qb["enunciado"] = "edição B offline"
            db_a.update_question(uid, qa)
            db_b.update_question(uid, qb)
            self.assertTrue(a.sync_once()["ok"])
            # B pulls A while it has a pending local edit; local edit is preserved and audited.
            self.assertTrue(b.sync_once()["ok"])
            self.assertEqual(db_b.get_question(uid)["enunciado"], "edição B offline")
            self.assertGreaterEqual(b.safe_status()["conflicts"], 1)
            # A later pulls B, which was the last push.
            self.assertTrue(a.sync_once()["ok"])
            self.assertEqual(db_a.get_question(uid)["enunciado"], "edição B offline")

    def test_global_reset_generation_discards_stale_offline_progress(self):
        remote = FakeRemote()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db_a, study_a, _, a = make_device(root / "a", remote, name="A")
            db_b, study_b, _, b = make_device(root / "b", remote, name="B")
            uid = db_a.create_manual_question(); study_a.sync_questions()
            with db_a.connect() as c:
                c.execute("UPDATE study_state SET sent_count=3, correct_count=2 WHERE question_uid=?", (uid,))
            self.assertTrue(a.sync_once()["ok"])
            self.assertTrue(b.sync_once()["ok"])

            # B makes stale progress while offline.
            with db_b.connect() as c:
                c.execute("UPDATE study_state SET sent_count=9, correct_count=8 WHERE question_uid=?", (uid,))
            self.assertGreater(b.pending_count(), 0)

            # A performs the global reset and publishes a newer generation.
            generation = a.begin_global_reset()
            study_a.reset_progress()
            self.assertEqual(generation, 2)
            self.assertTrue(a.sync_once()["ok"])
            self.assertEqual(remote.generation, 2)

            # When B returns, old-generation pending progress is discarded before any push.
            self.assertTrue(b.sync_once()["ok"])
            self.assertEqual(b.generation(), 2)
            with db_b.connect() as c:
                row = c.execute("SELECT sent_count,correct_count,wrong_count FROM study_state WHERE question_uid=?", (uid,)).fetchone()
            self.assertEqual(tuple(row), (0, 0, 0))
            self.assertFalse(any(int(e["generation"]) == 1 and e["device_id"] == b.device_id() and e["table_name"] == "study_state" for e in remote.events))

    def test_reset_preserves_unsynced_editorial_question_change(self):
        remote = FakeRemote()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db_a, study_a, _, a = make_device(root / "a", remote, name="A")
            db_b, study_b, _, b = make_device(root / "b", remote, name="B")
            uid = db_a.create_manual_question(); study_a.sync_questions()
            self.assertTrue(a.sync_once()["ok"])
            self.assertTrue(b.sync_once()["ok"])

            # B edits editorial content while offline before A performs a study reset.
            qb = db_b.get_question(uid)
            qb["explicacao"] = "edição editorial offline que não pode ser perdida"
            db_b.update_question(uid, qb)
            self.assertGreater(b.pending_count(), 0)

            a.begin_global_reset(); study_a.reset_progress()
            self.assertTrue(a.sync_once()["ok"])
            self.assertTrue(b.sync_once()["ok"])
            self.assertEqual(db_b.get_question(uid)["explicacao"], "edição editorial offline que não pode ser perdida")
            self.assertTrue(a.sync_once()["ok"])
            self.assertEqual(db_a.get_question(uid)["explicacao"], "edição editorial offline que não pode ser perdida")

    def test_new_device_after_reset_reconstructs_questions_but_not_old_progress(self):
        remote = FakeRemote()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db_a, study_a, _, a = make_device(root / "a", remote, name="A")
            uid = db_a.create_manual_question(); study_a.sync_questions()
            with db_a.connect() as c:
                c.execute("UPDATE study_state SET sent_count=5, correct_count=4 WHERE question_uid=?", (uid,))
            self.assertTrue(a.sync_once()["ok"])
            a.begin_global_reset(); study_a.reset_progress()
            self.assertTrue(a.sync_once()["ok"])

            # Device C did not exist before the reset. It must replay old editorial
            # events (the question) while ignoring stale pre-reset study frames.
            db_c, study_c, _, cengine = make_device(root / "c", remote, name="C")
            self.assertTrue(cengine.sync_once()["ok"])
            self.assertIsNotNone(db_c.get_question(uid))
            with db_c.connect() as c:
                row = c.execute("SELECT sent_count,correct_count FROM study_state WHERE question_uid=?", (uid,)).fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(tuple(row), (0, 0))

    def test_merge_prefers_cloud_on_existing_key_and_preserves_local_only_rows(self):
        remote = FakeRemote()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db_a, _, _, a = make_device(root / "a", remote, name="A")
            shared = db_a.create_manual_question()
            qa = db_a.get_question(shared); qa["enunciado"] = "versão nuvem"; db_a.update_question(shared, qa)
            self.assertTrue(a.sync_once()["ok"])

            # Clone A's DB content to B conceptually, but B is stale and has a local-only row.
            db_b, _, _, b = make_device(root / "b", remote, name="B")
            # Pull once to create the shared row, then clear sync history to simulate a
            # pre-Cloud-Sync legacy database with stale content and no outbox history.
            self.assertTrue(b.sync_once()["ok"])
            stale = db_b.get_question(shared); stale["enunciado"] = "stale local"; db_b.update_question(shared, stale)
            local_only = db_b.create_manual_question()
            with db_b.connect() as c:
                c.execute("DELETE FROM qf_sync_outbox")
                c.execute("DELETE FROM qf_sync_inbox")
                c.execute("UPDATE qf_sync_runtime SET value='0' WHERE key='last_remote_seq'")
            result = b.prepare_remote(source="merge")
            self.assertTrue(result["ok"], result)
            self.assertEqual(db_b.get_question(shared)["enunciado"], "versão nuvem")
            self.assertIsNotNone(db_b.get_question(local_only))
            self.assertTrue(a.sync_once()["ok"])
            self.assertIsNotNone(db_a.get_question(local_only))

    def test_device_operational_telegram_queues_are_not_cloud_synced(self):
        remote = FakeRemote()
        with tempfile.TemporaryDirectory() as tmp:
            db, _, _, engine = make_device(Path(tmp), remote)
            before = engine.pending_count()
            with db.connect() as c:
                c.execute("INSERT OR REPLACE INTO flow_runtime(key,value,updated_at) VALUES('device-test','abc','now')")
            self.assertEqual(engine.pending_count(), before)

    def test_database_temporarily_missing_is_reported_without_network_data_loss(self):
        remote = FakeRemote()
        with tempfile.TemporaryDirectory() as tmp:
            db, _, _, engine = make_device(Path(tmp), remote)
            original = db.path
            detached = original.with_suffix(".detached")
            original.replace(detached)
            try:
                state = engine.safe_status()
                self.assertEqual(state["state"], "database_unavailable")
            finally:
                detached.replace(original)
            with closing(sqlite3.connect(original)) as conn:
                self.assertEqual(conn.execute("PRAGMA integrity_check").fetchone()[0], "ok")

    def test_database_exclusive_lock_returns_safe_status_instead_of_crashing(self):
        remote = FakeRemote()
        with tempfile.TemporaryDirectory() as tmp:
            db, _, _, engine = make_device(Path(tmp), remote)
            lock = sqlite3.connect(db.path, timeout=1)
            try:
                lock.execute("BEGIN EXCLUSIVE")
                # safe_status is bounded and must classify instead of propagating OperationalError.
                state = engine.safe_status()
                self.assertIn(state["state"], {"database_busy", "ready", "pending", "synced", "warning", "error"})
            finally:
                lock.rollback(); lock.close()
            with closing(sqlite3.connect(db.path)) as conn:
                self.assertEqual(conn.execute("PRAGMA integrity_check").fetchone()[0], "ok")


class _PipelineHandler(BaseHTTPRequestHandler):
    token = "good-token"
    requests_seen = []

    def log_message(self, fmt, *args):
        return

    def do_POST(self):  # noqa: N802
        if self.headers.get("Authorization") != f"Bearer {self.token}":
            self.send_response(401); self.end_headers(); return
        length = int(self.headers.get("Content-Length", "0") or 0)
        body = self.rfile.read(length)
        payload = json.loads(body)
        type(self).requests_seen.append(payload)
        results = []
        for request in payload.get("requests", []):
            if request.get("type") == "close":
                results.append({"type": "ok", "response": {"type": "close"}})
                continue
            sql = str((request.get("stmt") or {}).get("sql", ""))
            if "SELECT value FROM qf_sync_meta" in sql:
                result = {"cols": [{"name": "value"}], "rows": [[{"type": "text", "value": "1"}]], "affected_row_count": 0}
            else:
                result = {"cols": [], "rows": [], "affected_row_count": 1}
            results.append({"type": "ok", "response": {"type": "execute", "result": result}})
        raw = json.dumps({"results": results}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers(); self.wfile.write(raw)


class TursoHttpProtocolTests(unittest.TestCase):
    def setUp(self):
        _PipelineHandler.requests_seen = []
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _PipelineHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(timeout=2)

    def test_official_sql_over_http_shape_and_bearer_auth(self):
        manager = NetworkManager({"network_mode": "direct"})
        client = TursoHttpClient(self.url, "good-token", network_manager=manager, timeout=2)
        result = client.test()
        self.assertTrue(result["ok"])
        self.assertEqual(result["generation"], 1)
        self.assertTrue(_PipelineHandler.requests_seen)
        first = _PipelineHandler.requests_seen[0]
        self.assertTrue(any(req.get("type") == "execute" for req in first["requests"]))
        self.assertEqual(first["requests"][-1]["type"], "close")

    def test_bad_token_is_classified_as_auth_failure(self):
        manager = NetworkManager({"network_mode": "direct"})
        client = TursoHttpClient(self.url, "bad-token", network_manager=manager, timeout=2)
        with self.assertRaises(TursoHttpError) as caught:
            client.test()
        self.assertEqual(caught.exception.category, "auth")


if __name__ == "__main__":
    unittest.main()
