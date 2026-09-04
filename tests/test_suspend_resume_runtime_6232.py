from __future__ import annotations

import itertools
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import desktop_runtime


class SuspendResumeRuntime6232Tests(unittest.TestCase):
    def test_sampling_gap_uses_wall_clock_when_monotonic_pauses(self) -> None:
        gap = desktop_runtime._sampling_gap_seconds(100.0, 1_000.0, 100.5, 4_600.0)
        self.assertEqual(gap, 3_600.0)

    def test_resume_requires_a_new_heartbeat_not_only_a_young_clock_age(self) -> None:
        source = Path(desktop_runtime.__file__).read_text(encoding="utf-8")
        self.assertIn("current_heartbeat > resume_heartbeat_baseline", source)
        self.assertIn("Require\n                                # a new UI emission", source)
        self.assertNotIn("or server.last_heartbeat_age <= heartbeat_timeout", source)

    def test_long_suspend_relaunches_interface_without_window_close_shutdown(self) -> None:
        order: list[str] = []

        class FakeServer:
            heartbeat_count = 1
            url = "http://127.0.0.1:1/"

            def __init__(self) -> None:
                self.relaunched = False
                self.recovery_reads = 0

            @property
            def last_heartbeat_age(self) -> float:
                if self.relaunched:
                    self.recovery_reads += 1
                    return 0.0
                return 999.0

        server = FakeServer()

        class FakeProcess:
            def poll(self):
                return None

            def terminate(self):
                order.append("terminate")

        class FakeApi:
            @property
            def close_requested(self) -> bool:
                return server.recovery_reads >= 1

            def start_services(self):
                order.append("services")

            def shutdown(self, reason="runtime"):
                order.append(f"shutdown:{reason}")

        launches = 0

        def fake_popen(*_args, **_kwargs):
            nonlocal launches
            launches += 1
            order.append(f"launch:{launches}")
            if launches >= 2:
                server.relaunched = True
                server.heartbeat_count += 1
            return FakeProcess()

        clock = itertools.count(start=0, step=1)
        gaps = iter((100.0, 0.0, 0.0))
        fake_browser = Path(__file__).resolve().parents[1] / "chrome.exe"
        with (
            patch.object(desktop_runtime, "browser_candidates", return_value=[fake_browser]),
            patch.object(desktop_runtime.subprocess, "Popen", side_effect=fake_popen),
            patch.object(desktop_runtime, "terminate_stale_questflow_chrome", return_value=1),
            patch.object(desktop_runtime, "_sampling_gap_seconds", side_effect=lambda *_args: next(gaps)),
            patch.object(desktop_runtime, "_journal_runtime_event", side_effect=lambda event, **_detail: order.append(event)),
            patch.object(desktop_runtime, "RESUME_HEARTBEAT_GRACE_SECONDS", 0.0),
            patch.object(desktop_runtime.time, "monotonic", side_effect=lambda: float(next(clock))),
            patch.object(desktop_runtime.time, "time", side_effect=lambda: float(next(clock))),
            patch.object(desktop_runtime.time, "sleep", return_value=None),
        ):
            self.assertTrue(desktop_runtime.run_chrome(server, FakeApi()))

        self.assertEqual(launches, 2)
        self.assertIn("suspend_resume_detected", order)
        self.assertIn("interface_relaunch_started", order)
        self.assertIn("interface_resumed", order)
        self.assertNotIn("shutdown:janela_fechada", order)
        self.assertIn("shutdown:botao_fechar", order)

    def test_lifecycle_journal_is_json_lines(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(desktop_runtime, "DATA_DIR", Path(tmp)):
                desktop_runtime._journal_runtime_event("suspend_resume_detected", sampling_gap_seconds=42.0)
            payload = json.loads((Path(tmp) / "runtime_lifecycle.jsonl").read_text(encoding="utf-8"))
        self.assertEqual(payload["event"], "suspend_resume_detected")
        self.assertEqual(payload["detail"]["sampling_gap_seconds"], 42.0)

    def test_windows_startup_registration_remains_explicit(self) -> None:
        root = Path(__file__).resolve().parents[1]
        activate = (root / "ATIVAR_INICIO_COM_WINDOWS.bat").read_text(encoding="utf-8", errors="replace")
        remove = (root / "REMOVER_INICIO_COM_WINDOWS.bat").read_text(encoding="utf-8", errors="replace")
        self.assertIn("QuestFlow_Studio.vbs", activate)
        self.assertIn("INICIAR_QUESTFLOW_STUDIO.bat", activate)
        self.assertIn("WScript.Sleep 10000", activate)
        self.assertIn("QuestFlow_Studio.vbs", remove)
        manager = (root / "questflow_manager.ps1").read_text(encoding="utf-8", errors="replace")
        self.assertIn("Ativar inicio automatico do Studio com o Windows", manager)
        self.assertIn("REMOVER_INICIO_COM_WINDOWS.bat", manager)


if __name__ == "__main__":
    unittest.main()
