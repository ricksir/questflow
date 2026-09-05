from __future__ import annotations

import copy
import json
import sqlite3
import tempfile
import threading
import time
import unittest
from contextlib import closing
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
import sys
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))

from core.cloud_sync import CloudSyncEngine, CloudSyncService  # noqa: E402
from core.storage import QuestFlowDatabase  # noqa: E402
from core.study import StudyRepository  # noqa: E402


class FakeRemote:
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

    def test(self):
        self._check()
        return {"ok": True, "generation": self.generation, "elapsed_ms": 1}

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


def make_engine(root: Path, remote: FakeRemote, *, name: str = "SAFE", enabled: bool = False):
    root.mkdir(parents=True, exist_ok=True)
    db_path = root / "questflow.sqlite"
    db = QuestFlowDatabase(db_path)
    study = StudyRepository(db)
    config = {
        "cloud_sync_enabled": enabled,
        "cloud_sync_safe_activation_required": True,
        "cloud_turso_url": "https://unit.invalid",
        "cloud_device_name": name,
        "cloud_sync_interval_seconds": 30,
        "cloud_sync_timeout_seconds": 2,
        "cloud_sync_on_start": True,
        "cloud_sync_on_shutdown": True,
        "cloud_sync_retry_base_seconds": 2,
        "cloud_sync_retry_max_seconds": 8,
    }
    cfg = root / "config.json"
    cfg.write_text(json.dumps(config), encoding="utf-8")
    engine = CloudSyncEngine(
        db_path,
        config=config,
        config_path=cfg,
        remote_client=remote,
        reset_callback=study.reset_progress,
        auth_token="unit",
    )
    return db, study, config, engine


class CloudSyncSafeActivation6141Tests(unittest.TestCase):
    def test_preview_is_remote_read_only_and_compares_ids_hashes(self):
        remote = FakeRemote()
        with tempfile.TemporaryDirectory() as tmp:
            db, study, _, engine = make_engine(Path(tmp), remote)
            uid = db.create_manual_question()
            q = db.get_question(uid)
            q["materia"] = "AUDITORIA"
            q["enunciado"] = "Questão local segura"
            db.update_question(uid, q)
            study.sync_questions()
            before = len(remote.events)
            preview = engine.activation_preview()
            self.assertTrue(preview["ok"], preview)
            self.assertEqual(len(remote.events), before)
            self.assertTrue(preview["read_only"])
            self.assertTrue(preview["local_healthy"])
            self.assertEqual(preview["recommended_source"], "this_device")
            self.assertGreaterEqual(preview["questions"]["local_count"], 1)
            self.assertEqual(preview["questions"]["remote_count"], 0)
            self.assertTrue(preview["dry_run"]["event_ids_unique"])
            self.assertGreaterEqual(preview["dry_run"]["pending"], 1)

    def test_direct_sync_is_blocked_until_safe_activation(self):
        remote = FakeRemote()
        with tempfile.TemporaryDirectory() as tmp:
            db, _, config, engine = make_engine(Path(tmp), remote, enabled=True)
            db.create_manual_question()
            result = engine.sync_once()
            self.assertFalse(result["ok"])
            self.assertTrue(result.get("activation_required"))
            self.assertEqual(remote.event_count(), 0)
            self.assertTrue(config["cloud_sync_enabled"])

    def test_safe_activation_creates_valid_backup_then_enables_sync(self):
        remote = FakeRemote()
        with tempfile.TemporaryDirectory() as tmp:
            db, study, config, engine = make_engine(Path(tmp), remote)
            uid = db.create_manual_question()
            q = db.get_question(uid)
            q["materia"] = "DIREITO TRIBUTÁRIO"
            q["enunciado"] = "Conteúdo para primeira sincronização"
            db.update_question(uid, q)
            study.sync_questions()

            result = engine.activate_safely(source="this_device")
            self.assertTrue(result["ok"], result)
            self.assertTrue(engine.activation_completed())
            self.assertEqual(engine.activation_status()["state"], "active")
            self.assertTrue(config["cloud_sync_enabled"])
            self.assertEqual(engine.pending_count(), 0)
            self.assertGreater(remote.event_count(), 0)
            backup = Path(result["backup"]["path"])
            self.assertTrue(backup.exists())
            with closing(sqlite3.connect(backup)) as conn:
                self.assertEqual(conn.execute("PRAGMA quick_check(1)").fetchone()[0], "ok")
                self.assertEqual(list(conn.execute("PRAGMA foreign_key_check")), [])

    def test_failure_after_remote_commit_is_retry_safe_and_leaves_automatic_off(self):
        remote = FakeRemote()
        remote.fail_after_commit_once = True
        with tempfile.TemporaryDirectory() as tmp:
            db, study, config, engine = make_engine(Path(tmp), remote)
            uid = db.create_manual_question()
            study.sync_questions()
            first = engine.activate_safely(source="this_device")
            self.assertFalse(first["ok"], first)
            self.assertTrue(first.get("retry_safe"))
            self.assertFalse(config["cloud_sync_enabled"])
            self.assertGreater(remote.event_count(), 0)  # remote commit happened
            # Retry uses the append-only/idempotent log and converges without duplicate logical rows.
            second = engine.activate_safely(source="merge", confirm_remote_differences=True)
            self.assertTrue(second["ok"], second)
            self.assertTrue(engine.activation_completed())
            manifest = engine._remote_manifest("questions")
            self.assertIn(json.dumps([uid], ensure_ascii=False, separators=(",", ":")), manifest)

    def test_preflight_detects_unseen_remote_conflict_for_same_pending_row(self):
        remote = FakeRemote()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db_a, study_a, _, a = make_engine(root / "a", remote, name="A")
            db_b, study_b, config_b, b = make_engine(root / "b", remote, name="B")

            uid = db_a.create_manual_question()
            qa = db_a.get_question(uid)
            qa["enunciado"] = "Versão remota"
            db_a.update_question(uid, qa)
            study_a.sync_questions()
            # A is activated and publishes the question.
            self.assertTrue(a.activate_safely(source="this_device")["ok"])

            # B first pulls cloud using forced sync after temporarily marking activation complete.
            with b._connect() as conn:
                b._set_runtime(conn, "activation_state", "active")
                b._set_runtime(conn, "activation_completed_at", "2026-08-20T00:00:00Z")
            config_b["cloud_sync_enabled"] = True
            self.assertTrue(b.sync_once()["ok"])

            # Both edit same row; A publishes another change while B keeps local pending change.
            qb = db_b.get_question(uid)
            qb["enunciado"] = "Versão local B"
            db_b.update_question(uid, qb)
            qa2 = db_a.get_question(uid)
            qa2["enunciado"] = "Versão remota A nova"
            db_a.update_question(uid, qa2)
            self.assertTrue(a.sync_once()["ok"])

            # Force B back into activation-required state; preview must see the unseen same-key frame.
            b.invalidate_activation("teste")
            config_b["cloud_sync_enabled"] = False
            preview = b.activation_preview()
            self.assertTrue(preview["ok"], preview)
            self.assertGreaterEqual(preview["dry_run"]["predicted_conflict_count"], 1)
            self.assertTrue(preview["blocking_conflicts"])


    def test_large_first_sync_is_resumable_beyond_old_2500_event_limit(self):
        remote = FakeRemote()
        with tempfile.TemporaryDirectory() as tmp:
            _, _, config, engine = make_engine(Path(tmp), remote)
            # Reproduces the real failure: 6.14.2 could drain only 10 x 250
            # events in one activation even when the preflight had > 2,500.
            with engine._connect() as conn:
                generation = engine.generation()
                rows = [
                    (f"event-{i:04d}", generation, "questions", json.dumps([f"ghost-{i:04d}"], separators=(",", ":")), "delete", f"2026-08-20T00:{i//60:02d}:{i%60:02d}Z")
                    for i in range(2601)
                ]
                conn.executemany(
                    "INSERT INTO qf_sync_outbox(event_id,generation,table_name,row_key,operation,changed_at) VALUES(?,?,?,?,?,?)",
                    rows,
                )
            initial_pending = engine.pending_count()
            self.assertGreater(initial_pending, 2500)
            first = engine.activate_safely(source="this_device")
            self.assertTrue(first["ok"], first)
            self.assertFalse(first.get("completed"), first)
            self.assertTrue(first.get("in_progress"), first)
            self.assertGreater(first.get("pending", 0), 0)
            self.assertFalse(config["cloud_sync_enabled"])
            remote_after_first = remote.event_count()
            self.assertEqual(remote_after_first, 2000)

            second = engine.activate_safely(source="this_device")
            self.assertTrue(second["ok"], second)
            self.assertTrue(second.get("completed"), second)
            self.assertTrue(engine.activation_completed())
            self.assertEqual(engine.pending_count(), 0)
            expected_total = remote_after_first + int(first.get("pending", 0) or 0)
            self.assertEqual(remote.event_count(), expected_total)
            # Resume must not reseed/replay rows that were already acknowledged.
            self.assertEqual(len(remote.seen), expected_total)

    def test_legacy_6142_generic_failure_resumes_existing_outbox_without_reseed(self):
        remote = FakeRemote()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _, _, _, engine = make_engine(root, remote)
            backup = engine.create_activation_backup()
            with engine._connect() as conn:
                generation = engine.generation()
                conn.executemany(
                    "INSERT INTO qf_sync_outbox(event_id,generation,table_name,row_key,operation,changed_at) VALUES(?,?,?,?,?,?)",
                    [
                        (f"legacy-{i}", generation, "questions", json.dumps([f"legacy-ghost-{i}"], separators=(",", ":")), "delete", "2026-08-20T01:00:00Z")
                        for i in range(600)
                    ],
                )
                engine._set_runtime(conn, "activation_state", "failed")
                engine._set_runtime(conn, "activation_checkpoint", "first_sync_failed")
                engine._set_runtime(conn, "activation_last_error", "A primeira sincronização não foi concluída.")
                engine._set_runtime(conn, "activation_backup_path", backup["path"])
                engine._set_runtime(conn, "activation_backup_sha256", backup["sha256"])
            legacy_pending = engine.pending_count()
            result = engine.activate_safely(source="merge", confirm_remote_differences=True)
            self.assertTrue(result["ok"], result)
            self.assertTrue(result.get("completed"), result)
            self.assertEqual(engine.pending_count(), 0)
            self.assertEqual(remote.event_count(), legacy_pending)

    def test_recovery_guard_is_archived_by_explicit_safe_activation(self):
        remote = FakeRemote()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db, study, config, engine = make_engine(root, remote)
            uid = db.create_manual_question(); study.sync_questions()
            guard = root / "RECOVERY_GUARD.json"
            guard.write_text(json.dumps({
                "schema": "questflow.recovery-guard.v1",
                "created_at": "2026-08-20T00:00:00Z",
                "reason": "Proteção pós-recuperação para teste.",
            }), encoding="utf-8")
            preview = engine.activation_preview()
            self.assertTrue(preview["recovery_guard"]["active"], preview)
            result = engine.activate_safely(source="this_device")
            self.assertTrue(result["ok"], result)
            self.assertTrue(result.get("completed"), result)
            self.assertFalse(guard.exists())
            activation = engine.activation_status()
            self.assertTrue(activation.get("recovery_guard_released_at"))
            archive = Path(activation.get("recovery_guard_archive") or "")
            self.assertTrue(archive.exists(), activation)
            self.assertTrue(config["cloud_sync_enabled"])
            self.assertEqual(engine.pending_count(), 0)
            self.assertGreater(remote.event_count(), 0)

    def test_legacy_resume_with_recovery_guard_releases_guard_and_drains_existing_outbox(self):
        remote = FakeRemote()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _, _, config, engine = make_engine(root, remote)
            backup = engine.create_activation_backup()
            with engine._connect() as conn:
                generation = engine.generation()
                conn.executemany(
                    "INSERT INTO qf_sync_outbox(event_id,generation,table_name,row_key,operation,changed_at) VALUES(?,?,?,?,?,?)",
                    [
                        (f"resume-guard-{i}", generation, "questions", json.dumps([f"resume-ghost-{i}"], separators=(",", ":")), "delete", "2026-08-20T01:00:00Z")
                        for i in range(600)
                    ],
                )
                engine._set_runtime(conn, "activation_state", "syncing")
                engine._set_runtime(conn, "activation_checkpoint", "first_sync_progress")
                engine._set_runtime(conn, "activation_seeded_at", "2026-08-20T01:00:00Z")
                engine._set_runtime(conn, "activation_source", "merge")
                engine._set_runtime(conn, "activation_backup_path", backup["path"])
                engine._set_runtime(conn, "activation_backup_sha256", backup["sha256"])
            guard = root / "RECOVERY_GUARD.json"
            guard.write_text(json.dumps({"schema": "questflow.recovery-guard.v1", "reason": "guard legado"}), encoding="utf-8")
            result = engine.activate_safely(source="merge", confirm_remote_differences=True)
            self.assertTrue(result["ok"], result)
            self.assertTrue(result.get("completed"), result)
            self.assertFalse(guard.exists())
            self.assertEqual(engine.pending_count(), 0)
            self.assertEqual(remote.event_count(), 600)
            self.assertTrue(config["cloud_sync_enabled"])

    def test_guard_block_is_not_reported_as_fake_progress(self):
        remote = FakeRemote()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _, _, config, engine = make_engine(root, remote)
            with engine._connect() as conn:
                generation = engine.generation()
                conn.execute(
                    "INSERT INTO qf_sync_outbox(event_id,generation,table_name,row_key,operation,changed_at) VALUES(?,?,?,?,?,?)",
                    ("guard-block", generation, "questions", json.dumps(["ghost"], separators=(",", ":")), "delete", "2026-08-20T01:00:00Z"),
                )
            (root / "RECOVERY_GUARD.json").write_text("{}", encoding="utf-8")
            config["cloud_sync_enabled"] = True
            result = engine.sync_until_idle(max_rounds=2, max_seconds=5, force=True)
            self.assertFalse(result["ok"], result)
            self.assertTrue(result.get("recovery_guard"), result)
            self.assertIn("pausado", str(result.get("error", "")).lower())
            self.assertEqual(engine.pending_count(), 1)

    def test_background_service_exponential_backoff_after_offline_failure(self):
        remote = FakeRemote()
        with tempfile.TemporaryDirectory() as tmp:
            db, study, config, engine = make_engine(Path(tmp), remote)
            db.create_manual_question(); study.sync_questions()
            self.assertTrue(engine.activate_safely(source="this_device")["ok"])
            db.create_manual_question(); study.sync_questions()
            remote.offline = True
            service = CloudSyncService(engine)
            service.start()
            try:
                service.wake()
                deadline = time.time() + 5
                health = service.health()
                while time.time() < deadline and health.get("consecutive_failures", 0) < 1:
                    time.sleep(.1)
                    health = service.health()
                self.assertGreaterEqual(health.get("consecutive_failures", 0), 1, health)
                self.assertGreaterEqual(health.get("retry_delay_seconds", 0), 2)
            finally:
                remote.offline = False
                service.stop(flush=False, timeout=2)

    def test_version_is_6143_and_mobile_remains_0101(self):
        self.assertEqual((BASE / "VERSION.txt").read_text(encoding="utf-8").strip(), "6.24.0")
        package = json.loads((BASE / "mobile" / "package.json").read_text(encoding="utf-8"))
        self.assertEqual(package["version"], "0.16.0")


if __name__ == "__main__":
    unittest.main()
