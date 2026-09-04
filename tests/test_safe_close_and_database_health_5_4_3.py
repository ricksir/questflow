from __future__ import annotations

import copy
import json
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))

from core.cloud_sync import CloudSyncEngine  # noqa: E402
from core.storage import QuestFlowDatabase  # noqa: E402
from core.study import StudyRepository  # noqa: E402
from web_api import QuestFlowWebApi  # noqa: E402


class HealthRemote:
    def __init__(self) -> None:
        self.generation = 1
        self.events: list[dict] = []
        self.seen: set[str] = set()
        self.seq = 0
        self.devices: dict[str, str] = {}
        self._lock = threading.RLock()

    def ensure_schema(self):
        return None

    def get_generation(self):
        return self.generation

    def set_generation(self, generation):
        self.generation = int(generation)

    def touch_device(self, device_id, name):
        self.devices[str(device_id)] = str(name)

    def append_events(self, events):
        written = 0
        with self._lock:
            for item in events:
                if item["event_id"] in self.seen:
                    continue
                self.seq += 1
                event = copy.deepcopy(dict(item))
                event["seq"] = self.seq
                self.events.append(event)
                self.seen.add(event["event_id"])
                written += 1
        return written

    def fetch_events(self, after_seq, generation, *, limit=500):
        return [copy.deepcopy(e) for e in self.events if int(e["seq"]) > int(after_seq)][:limit]

    def event_count(self):
        return len(self.events)

    def current_row_count(self, table_name):
        latest = {}
        for event in self.events:
            if event["table_name"] == table_name:
                latest[event["row_key"]] = event
        return sum(1 for event in latest.values() if event["operation"] != "delete")

    def max_event_seq(self):
        return max((int(event["seq"]) for event in self.events), default=0)

    def test(self):
        return {"ok": True, "generation": self.generation, "elapsed_ms": 1}


def make_engine(folder: Path, remote: HealthRemote):
    db_path = folder / "questflow.sqlite"
    db = QuestFlowDatabase(db_path)
    study = StudyRepository(db)
    config = {
        "cloud_sync_enabled": True,
        "cloud_turso_url": "https://unit.invalid",
        "cloud_device_name": "TESTE",
        "cloud_sync_interval_seconds": 30,
        "cloud_sync_timeout_seconds": 2,
        "cloud_sync_on_start": True,
        "cloud_sync_on_shutdown": True,
    }
    cfg = folder / "config.json"
    cfg.write_text(json.dumps(config), encoding="utf-8")
    engine = CloudSyncEngine(db_path, config=config, config_path=cfg, remote_client=remote, auth_token="unit")
    return db, study, engine


class SafeCloseAndHealth543Tests(unittest.TestCase):
    def test_health_snapshot_confirms_equal_local_and_cloud_question_counts(self):
        remote = HealthRemote()
        with tempfile.TemporaryDirectory() as tmp:
            db, study, engine = make_engine(Path(tmp), remote)
            for _ in range(3):
                db.create_manual_question()
            study.sync_questions()
            result = engine.sync_once()
            self.assertTrue(result["ok"], result)
            health = engine.health_snapshot()
            self.assertTrue(health["local_healthy"], health)
            self.assertEqual(health["local_question_count"], 3)
            self.assertEqual(health["remote_question_count"], 3)
            self.assertTrue(health["counts_equal"])
            self.assertTrue(health["synchronized"], health)

    def test_health_snapshot_detects_remote_count_mismatch(self):
        remote = HealthRemote()
        with tempfile.TemporaryDirectory() as tmp:
            db, study, engine = make_engine(Path(tmp), remote)
            db.create_manual_question(); study.sync_questions()
            self.assertTrue(engine.sync_once()["ok"])
            remote.seq += 1
            remote.events.append({
                "seq": remote.seq, "event_id": "external-row", "device_id": "OTHER", "generation": 1,
                "table_name": "questions", "row_key": '["external"]', "operation": "upsert",
                "payload_json": "{}", "created_at": "2026-08-10T00:00:00Z", "checksum": "x",
            })
            health = engine.health_snapshot()
            self.assertTrue(health["local_healthy"])
            self.assertFalse(health["counts_equal"])
            self.assertFalse(health["synchronized"])
            self.assertEqual(health["remote_question_count"], 2)

    def test_safe_database_finalize_writes_clean_shutdown_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db_path = root / "questflow.sqlite"
            QuestFlowDatabase(db_path).create_manual_question()
            cfg = root / "config.json"
            cfg.write_text("{}", encoding="utf-8")
            api = QuestFlowWebApi(database_path=db_path, config={}, config_path=cfg, taxonomy_path=root / "taxonomy.json")
            report = api._finalize_database_safely(reason="unit-test", cloud_result={"ok": True})
            self.assertTrue(report["clean"], report)
            self.assertEqual(report["quick_check"], "ok")
            saved = json.loads((root / "last_clean_shutdown.json").read_text(encoding="utf-8"))
            self.assertEqual(saved["reason"], "unit-test")
            self.assertTrue(saved["clean"])
            api.executor.shutdown(wait=False, cancel_futures=True)

    def test_close_request_is_explicit_and_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg = root / "config.json"; cfg.write_text("{}", encoding="utf-8")
            api = QuestFlowWebApi(database_path=root / "questflow.sqlite", config={}, config_path=cfg, taxonomy_path=root / "taxonomy.json")
            self.assertFalse(api.close_requested)
            self.assertTrue(api.request_close()["ok"])
            self.assertTrue(api.close_requested)
            api.executor.shutdown(wait=False, cancel_futures=True)


    def test_runtime_direct_window_close_executes_shutdown_before_terminating_chrome(self):
        import desktop_runtime

        order = []

        class FakeProcess:
            def poll(self): return None
            def terminate(self): order.append('terminate')

        class FakeServer:
            heartbeat_count = 1
            last_heartbeat_age = 999.0
            url = 'http://127.0.0.1:1/'

        class FakeApi:
            close_requested = False
            def start_services(self): order.append('services')
            def shutdown(self, reason='runtime'): order.append(f'shutdown:{reason}')

        fake_browser = BASE / 'chrome.exe'
        with patch.object(desktop_runtime, 'browser_candidates', return_value=[fake_browser]), \
             patch.object(desktop_runtime.subprocess, 'Popen', return_value=FakeProcess()), \
             patch.object(desktop_runtime.time, 'monotonic', side_effect=[0.0, 0.0, 10.0, 20.0, 30.0, 40.0]), \
             patch.object(desktop_runtime.time, 'sleep', return_value=None):
            self.assertTrue(desktop_runtime.run_chrome(FakeServer(), FakeApi()))
        self.assertIn('shutdown:janela_fechada', order)
        self.assertLess(order.index('shutdown:janela_fechada'), order.index('terminate'))

    def test_runtime_close_button_executes_shutdown_before_terminating_chrome(self):
        import desktop_runtime

        order = []

        class FakeProcess:
            def poll(self): return None
            def terminate(self): order.append('terminate')

        class FakeServer:
            heartbeat_count = 1
            last_heartbeat_age = 0.0
            url = 'http://127.0.0.1:1/'

        class FakeApi:
            close_requested = True
            def start_services(self): order.append('services')
            def shutdown(self, reason='runtime'): order.append(f'shutdown:{reason}')

        fake_browser = BASE / 'chrome.exe'
        with patch.object(desktop_runtime, 'browser_candidates', return_value=[fake_browser]), \
             patch.object(desktop_runtime.subprocess, 'Popen', return_value=FakeProcess()), \
             patch.object(desktop_runtime.time, 'monotonic', return_value=0.0), \
             patch.object(desktop_runtime.time, 'sleep', return_value=None):
            self.assertTrue(desktop_runtime.run_chrome(FakeServer(), FakeApi()))
        self.assertIn('shutdown:botao_fechar', order)
        self.assertLess(order.index('shutdown:botao_fechar'), order.index('terminate'))

    def test_ui_and_runtime_expose_safe_close_and_health_panel(self):
        html = (BASE / "web" / "index.html").read_text(encoding="utf-8")
        js = (BASE / "web" / "app.js").read_text(encoding="utf-8")
        runtime = (BASE / "desktop_runtime.py").read_text(encoding="utf-8")
        server = (BASE / "web_server.py").read_text(encoding="utf-8")
        self.assertIn('id="closeQuestFlow"', html)
        self.assertIn('id="databaseHealthPanel"', html)
        self.assertIn("requestSafeClose", js)
        self.assertIn("get_database_health", server)
        self.assertIn('api.shutdown(reason="janela_fechada")', runtime)
        self.assertIn('api.shutdown(reason="botao_fechar")', runtime)


if __name__ == "__main__":
    unittest.main()
