from __future__ import annotations

import socket
import tempfile
import threading
import time
import unittest
import urllib.request
from pathlib import Path

from app_shared import TAXONOMY_PATH
from core.cloud_sync import CloudSyncService, TursoHttpClient
from core.storage import QuestFlowDatabase
from web_api import QuestFlowWebApi
from web_server import QuestFlowLocalServer


class _DummyApi:
    def bootstrap_shell(self):
        return {"app": {"name": "QuestFlow Studio", "version": "5.5.0"}, "deferred": True}


class _SlowEngine:
    def __init__(self) -> None:
        self.config = {
            "cloud_sync_enabled": True,
            "cloud_sync_on_shutdown": True,
        }
        self.sync_calls = 0

    def safe_status(self):
        return {"state": "syncing", "pending": 2, "conflicts": 0}

    def sync_once(self):
        self.sync_calls += 1
        return {"ok": True}


class PerformanceStability550Tests(unittest.TestCase):
    def make_api(self, root: Path) -> QuestFlowWebApi:
        db_path = root / "questions.sqlite"
        QuestFlowDatabase(db_path)
        return QuestFlowWebApi(
            db_path,
            config={"flow_target_retention": 0.88},
            config_path=root / "config.json",
            taxonomy_path=TAXONOMY_PATH,
        )

    def test_flow_event_cursor_survives_ring_buffer_rotation(self):
        with tempfile.TemporaryDirectory() as tmp:
            api = self.make_api(Path(tmp))
            try:
                for index in range(250):
                    api._on_flow_event("tick", index=index)

                snapshot = api.poll_events(0)
                self.assertEqual(snapshot["cursor"], 250)
                self.assertEqual(len(snapshot["items"]), 200)
                self.assertEqual(snapshot["items"][0]["index"], 50)
                self.assertEqual(snapshot["items"][-1]["index"], 249)

                api._on_flow_event("tick", index=250)
                delta = api.poll_events(250)
                self.assertEqual(delta["cursor"], 251)
                self.assertEqual([item["index"] for item in delta["items"]], [250])
            finally:
                api.shutdown()

    def test_coalesced_background_task_is_not_started_twice(self):
        with tempfile.TemporaryDirectory() as tmp:
            api = self.make_api(Path(tmp))
            gate = threading.Event()
            started = threading.Event()
            calls = []

            def worker(_task_id: str):
                calls.append(1)
                started.set()
                gate.wait(timeout=2)
                return {"ok": True}

            try:
                first = api._start_task("dashboard-regression", worker, coalesce=True)
                self.assertTrue(started.wait(timeout=1))
                second = api._start_task("dashboard-regression", worker, coalesce=True)
                self.assertEqual(first["task_id"], second["task_id"])
                self.assertTrue(second.get("reused"))
                self.assertEqual(len(calls), 1)
            finally:
                gate.set()
                api.shutdown()

    def test_task_history_is_bounded(self):
        with tempfile.TemporaryDirectory() as tmp:
            api = self.make_api(Path(tmp))
            api._task_history_limit = 8
            try:
                ids = []
                for index in range(32):
                    result = api._start_task(f"tiny-{index}", lambda _task_id, n=index: {"n": n})
                    ids.append(result["task_id"])
                deadline = time.monotonic() + 3
                while time.monotonic() < deadline:
                    with api.task_lock:
                        if all(api.tasks.get(task_id, {}).get("status") in {"done", "error"} or task_id not in api.tasks for task_id in ids):
                            api._prune_tasks_locked()
                            break
                    time.sleep(0.01)
                with api.task_lock:
                    api._prune_tasks_locked()
                    self.assertLessEqual(len(api.tasks), api._task_history_limit)
            finally:
                api.shutdown()

    def test_turso_health_counters_use_one_batch(self):
        client = TursoHttpClient("https://example.turso.io", "unit-token")
        calls = []

        def fake_batch(statements):
            calls.append(statements)
            return [
                {"rows": [{"total": 123}]},
                {"rows": [{"value": "7"}]},
                {"rows": [{"seq": 456}]},
            ]

        client.execute_batch = fake_batch  # type: ignore[method-assign]
        result = client.health_counters("questions")
        self.assertEqual(result, {"row_count": 123, "generation": 7, "max_event_seq": 456})
        self.assertEqual(len(calls), 1)
        self.assertEqual(len(calls[0]), 3)

    def test_cloud_stop_defers_instead_of_blocking_behind_running_sync(self):
        engine = _SlowEngine()
        service = CloudSyncService(engine)  # type: ignore[arg-type]
        blocker = threading.Event()
        thread = threading.Thread(target=lambda: blocker.wait(timeout=2), daemon=True)
        thread.start()
        service._thread = thread
        try:
            started = time.perf_counter()
            result = service.stop(flush=True, timeout=0.05)
            elapsed = time.perf_counter() - started
            self.assertLess(elapsed, 0.5)
            self.assertTrue(result and result.get("deferred"))
            self.assertTrue(result and result.get("in_progress"))
            self.assertEqual(engine.sync_calls, 0)
        finally:
            blocker.set()
            thread.join(timeout=1)

    def test_static_files_are_no_store_and_preferred_port_has_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "index.html").write_text("<!doctype html><title>QuestFlow</title>", encoding="utf-8")

            blocker = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            blocker.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            blocker.bind(("127.0.0.1", 0))
            blocker.listen(1)
            occupied = int(blocker.getsockname()[1])

            server = QuestFlowLocalServer(_DummyApi(), root, preferred_port=occupied)
            try:
                server.start()
                self.assertNotEqual(server.port, occupied)
                with urllib.request.urlopen(server.base_url + "/index.html", timeout=3) as response:
                    self.assertEqual(response.headers.get("Cache-Control"), "no-store")
            finally:
                server.stop()
                blocker.close()


if __name__ == "__main__":
    unittest.main()
