from __future__ import annotations

import json
from pathlib import Path
import tempfile
import time
import unittest

import app_shared
from core.background_runtime import BackgroundRuntime
from core.cloud_sync import CloudSyncService
from core.compatibility import compatibility_report
from core.rate_limiter import RateLimiterRegistry
from core.runtime_supervisor import RuntimeSupervisor, ServiceSpec
from web_api import QuestFlowWebApi
from web_server import ALLOWED_API_METHODS, QuestFlowLocalServer


class RuntimeWatchdog668Tests(unittest.TestCase):
    def test_release_and_watchdog_defaults(self):
        self.assertEqual(app_shared.APP_VERSION, "6.23.2")
        self.assertTrue(app_shared.DEFAULT_CONFIG["watchdog_enabled"])
        self.assertTrue(app_shared.DEFAULT_CONFIG["watchdog_auto_recover"])
        self.assertGreaterEqual(app_shared.DEFAULT_CONFIG["runtime_io_max_concurrency"], 2)
        self.assertGreater(app_shared.DEFAULT_CONFIG["ai_rate_limit_per_minute"], 0)

    def test_background_runtime_has_heartbeat_and_can_reconfigure(self):
        runtime = BackgroundRuntime(max_concurrency=2)
        try:
            future = runtime.run_blocking(lambda: 42)
            self.assertEqual(future.result(timeout=3), 42)
            health = runtime.health()
            self.assertTrue(health["ok"])
            self.assertTrue(health["loop_running"])
            self.assertEqual(health["completed"], 1)
            result = runtime.reconfigure(max_concurrency=3)
            self.assertTrue(result["ok"])
            self.assertEqual(runtime.health()["max_concurrency"], 3)
            self.assertGreaterEqual(runtime.health()["generation"], 2)
        finally:
            runtime.shutdown()

    def test_rate_limiter_registry_is_bounded_and_observable(self):
        registry = RateLimiterRegistry()
        registry.acquire("demo", rate_per_minute=6000, burst=2, timeout=1)
        registry.acquire("demo", rate_per_minute=6000, burst=2, timeout=1)
        status = registry.snapshot()
        self.assertEqual(len(status), 1)
        self.assertEqual(status[0]["key"], "demo")
        self.assertLessEqual(status[0]["available_tokens"], 1.1)

    def test_supervisor_treats_offline_as_normal_and_never_recovers_it(self):
        with tempfile.TemporaryDirectory() as d:
            recoveries = []
            supervisor = RuntimeSupervisor(config={"watchdog_enabled": True, "watchdog_auto_recover": True}, journal_path=Path(d) / "watchdog.jsonl", interval_seconds=60)
            supervisor.register(ServiceSpec(
                name="network", label="Rede", health_check=lambda: {"ok": True, "state": "offline", "last_error": "sem internet"},
                recover=lambda: recoveries.append(1),
            ))
            result = supervisor.check_once(auto_recover=True)
            self.assertEqual(result["overall"], "offline_normal")
            self.assertEqual(result["services"][0]["status"], "offline")
            self.assertEqual(recoveries, [])

    def test_supervisor_recovers_only_after_failure_threshold(self):
        with tempfile.TemporaryDirectory() as d:
            state = {"healthy": False, "recoveries": 0}
            def health():
                return {"ok": state["healthy"], "state": "healthy" if state["healthy"] else "degraded", "error": "travado" if not state["healthy"] else ""}
            def recover():
                state["recoveries"] += 1
                state["healthy"] = True
                return {"ok": True}
            supervisor = RuntimeSupervisor(
                config={"watchdog_enabled": True, "watchdog_auto_recover": True, "watchdog_max_restarts_per_window": 2, "watchdog_restart_window_seconds": 600},
                journal_path=Path(d) / "watchdog.jsonl", interval_seconds=60,
            )
            supervisor.register(ServiceSpec(name="worker", label="Worker", health_check=health, recover=recover, failure_threshold=2, recovery_cooldown=0))
            first = supervisor.check_once(auto_recover=True)
            self.assertEqual(first["services"][0]["status"], "degraded")
            self.assertEqual(state["recoveries"], 0)
            supervisor.check_once(auto_recover=True)
            self.assertEqual(state["recoveries"], 1)
            third = supervisor.check_once(auto_recover=True)
            self.assertEqual(third["services"][0]["status"], "healthy")
            self.assertTrue((Path(d) / "watchdog.jsonl").exists())

    def test_cloud_sync_service_exposes_heartbeat_without_long_interval_staleness(self):
        class FakeEngine:
            def __init__(self):
                self.config = {"cloud_sync_enabled": True, "cloud_sync_interval_seconds": 900, "cloud_sync_on_start": False, "cloud_sync_on_shutdown": False}
            def sync_until_idle(self, **_kwargs):
                return {"ok": True, "pending": 0}
            def safe_status(self):
                return {"pending": 0, "conflicts": 0}
            def sync_once(self):
                return {"ok": True}
        service = CloudSyncService(FakeEngine())
        service.start()
        try:
            time.sleep(0.08)
            health = service.health()
            self.assertTrue(health["thread_alive"])
            self.assertTrue(health["ok"])
            self.assertLess(health["heartbeat_age_seconds"], 3)
        finally:
            service.stop(flush=False)

    def test_runtime_api_is_allowlisted_and_reports_compatibility(self):
        expected = {"get_runtime_watchdog_status", "run_runtime_watchdog_check", "restart_runtime_service", "save_runtime_watchdog_settings"}
        self.assertTrue(expected <= set(ALLOWED_API_METHODS))
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            api = QuestFlowWebApi(database_path=root / "q.sqlite", config_path=root / "config.json", config={**app_shared.DEFAULT_CONFIG, "watchdog_enabled": False})
            try:
                result = api.get_runtime_watchdog_status()
                self.assertTrue(result["ok"])
                self.assertEqual(result["compatibility"]["app_version"], "6.23.2")
                self.assertIn("python", result["compatibility"])
            finally:
                api.shutdown()

    def test_runtime_status_is_reachable_through_real_http(self):
        class DummyApi:
            def get_runtime_watchdog_status(self):
                return {"ok": True, "watchdog": {"overall": "healthy", "score": 100}}
        root = Path(__file__).resolve().parents[1]
        server = QuestFlowLocalServer(DummyApi(), root / "web", preferred_port=0)
        server.start()
        try:
            import urllib.request
            payload = json.dumps({"method": "get_runtime_watchdog_status", "args": []}).encode("utf-8")
            request = urllib.request.Request(
                f"{server.base_url}/api/call", data=payload,
                headers={"Content-Type": "application/json", "X-QuestFlow-Token": server.token}, method="POST",
            )
            with urllib.request.urlopen(request, timeout=5) as response:
                result = json.loads(response.read().decode("utf-8"))
            self.assertTrue(result["ok"])
            self.assertEqual(result["result"]["watchdog"]["score"], 100)
        finally:
            server.stop()

    def test_compatibility_report_accepts_test_runtime(self):
        report = compatibility_report()
        self.assertTrue(report["ok"])
        self.assertTrue(report["python"]["supported"])
        self.assertTrue(report["sqlite"]["supported"])


if __name__ == "__main__":
    unittest.main()
