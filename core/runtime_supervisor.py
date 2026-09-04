from __future__ import annotations

"""Supervisor central do runtime QuestFlow.

Infraestrutura transversal: não é um sétimo motor. Monitora serviços, limita
reinicializações e registra incidentes fora do SQLite principal para que uma
falha de infraestrutura não bloqueie o banco.
"""

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
import threading
import time
from typing import Any, Callable


def _iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


HealthCheck = Callable[[], dict[str, Any]]
Recovery = Callable[[], Any]
EnabledCheck = Callable[[], bool]


@dataclass(slots=True)
class ServiceSpec:
    name: str
    label: str
    health_check: HealthCheck
    recover: Recovery | None = None
    enabled: EnabledCheck | None = None
    critical: bool = False
    stale_after: float = 45.0
    failure_threshold: int = 2
    recovery_cooldown: float = 30.0


@dataclass(slots=True)
class ServiceState:
    status: str = "initializing"
    last_check_at: str = ""
    last_success_at: str = ""
    last_error: str = ""
    consecutive_failures: int = 0
    recoveries: int = 0
    last_recovery_monotonic: float = 0.0
    detail: dict[str, Any] = field(default_factory=dict)
    restart_times: deque[float] = field(default_factory=lambda: deque(maxlen=32))


class RuntimeSupervisor:
    STATES = {"healthy", "offline", "degraded", "suspect", "recovering", "failed", "disabled", "initializing"}

    def __init__(
        self,
        *,
        config: dict,
        journal_path: str | Path,
        interval_seconds: float = 5.0,
    ) -> None:
        self.config = config
        self.journal_path = Path(journal_path)
        self.interval_seconds = max(2.0, min(60.0, float(interval_seconds)))
        self._lock = threading.RLock()
        self._services: dict[str, ServiceSpec] = {}
        self._states: dict[str, ServiceState] = {}
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._started_at = time.monotonic()
        self._last_cycle = 0.0
        self._history: deque[dict[str, Any]] = deque(maxlen=max(50, int(config.get("watchdog_history_limit", 300) or 300)))
        self._shutdown = False

    def register(self, spec: ServiceSpec) -> None:
        with self._lock:
            self._services[spec.name] = spec
            self._states.setdefault(spec.name, ServiceState())

    def unregister(self, name: str) -> None:
        with self._lock:
            self._services.pop(str(name), None)
            self._states.pop(str(name), None)

    def start(self) -> None:
        if not bool(self.config.get("watchdog_enabled", True)):
            return
        if self._thread and self._thread.is_alive():
            return
        self._shutdown = False
        self._stop.clear()
        self._wake.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="questflow-runtime-watchdog")
        self._thread.start()
        self._journal("supervisor_started", detail={"interval_seconds": self.interval_seconds})

    def stop(self, timeout: float = 4.0) -> None:
        self._shutdown = True
        self._stop.set()
        self._wake.set()
        thread = self._thread
        if thread and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=max(0.2, float(timeout)))
        self._journal("supervisor_stopped")

    def wake(self) -> None:
        self._wake.set()

    def _run(self) -> None:
        while not self._stop.is_set():
            self.check_once(auto_recover=True)
            self._wake.wait(timeout=self.interval_seconds)
            self._wake.clear()

    def _journal(self, event: str, *, service: str = "supervisor", status: str = "", detail: dict[str, Any] | None = None) -> None:
        item = {"at": _iso(), "event": str(event), "service": str(service), "status": str(status), "detail": detail or {}}
        with self._lock:
            self._history.append(item)
        try:
            self.journal_path.parent.mkdir(parents=True, exist_ok=True)
            self._rotate_journal_if_needed()
            with self.journal_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(item, ensure_ascii=False, separators=(",", ":")) + "\n")
        except OSError:
            pass

    def _rotate_journal_if_needed(self) -> None:
        try:
            max_bytes = max(256 * 1024, int(self.config.get("watchdog_journal_max_mb", 2) or 2) * 1024 * 1024)
            if not self.journal_path.exists() or self.journal_path.stat().st_size < max_bytes:
                return
            rotated = self.journal_path.with_suffix(self.journal_path.suffix + ".1")
            rotated.unlink(missing_ok=True)
            self.journal_path.replace(rotated)
        except OSError:
            pass

    def _enabled(self, spec: ServiceSpec) -> bool:
        try:
            return True if spec.enabled is None else bool(spec.enabled())
        except Exception:
            return False

    @staticmethod
    def _normalize_health(result: dict[str, Any]) -> tuple[bool, str, str]:
        ok = bool(result.get("ok", False))
        state = str(result.get("state") or result.get("status") or ("healthy" if ok else "degraded")).strip().lower()
        aliases = {
            "operacional": "healthy", "ready": "healthy", "running": "healthy", "ok": "healthy",
            "atenção": "degraded", "atencao": "degraded", "warning": "degraded",
            "offline_normal": "offline", "offline": "offline", "disabled": "disabled",
        }
        state = aliases.get(state, state)
        if state not in RuntimeSupervisor.STATES:
            state = "healthy" if ok else "degraded"
        error = str(result.get("error") or result.get("last_error") or "")
        return ok, state, error

    def _can_recover(self, spec: ServiceSpec, state: ServiceState, now: float) -> bool:
        if self._shutdown or spec.recover is None or not bool(self.config.get("watchdog_auto_recover", True)):
            return False
        if now - state.last_recovery_monotonic < spec.recovery_cooldown:
            return False
        window = max(60.0, float(self.config.get("watchdog_restart_window_seconds", 600) or 600))
        maximum = max(1, int(self.config.get("watchdog_max_restarts_per_window", 3) or 3))
        while state.restart_times and now - state.restart_times[0] > window:
            state.restart_times.popleft()
        return len(state.restart_times) < maximum

    def _recover(self, spec: ServiceSpec, state: ServiceState) -> None:
        now = time.monotonic()
        if not self._can_recover(spec, state, now):
            return
        previous = state.status
        state.status = "recovering"
        state.last_recovery_monotonic = now
        state.restart_times.append(now)
        state.recoveries += 1
        self._journal("recovery_started", service=spec.name, status="recovering", detail={"previous": previous, "attempt": state.recoveries})
        try:
            result = spec.recover() if spec.recover else None
            self._journal("recovery_requested", service=spec.name, status="recovering", detail={"result": str(result)[:600]})
        except Exception as error:
            state.status = "failed"
            state.last_error = str(error)
            self._journal("recovery_failed", service=spec.name, status="failed", detail={"error": str(error)[:1000]})

    def check_once(self, *, auto_recover: bool = True) -> dict[str, Any]:
        with self._lock:
            specs = list(self._services.values())
        changed: list[tuple[str, str, str]] = []
        for spec in specs:
            state = self._states.setdefault(spec.name, ServiceState())
            previous_status = state.status
            state.last_check_at = _iso()
            if not self._enabled(spec):
                state.status = "disabled"
                state.consecutive_failures = 0
                state.detail = {"ok": True, "state": "disabled", "message": "Serviço desativado pela configuração."}
                continue
            try:
                result = dict(spec.health_check() or {})
                ok, observed_state, error = self._normalize_health(result)
                state.detail = result
                if ok or observed_state in {"healthy", "offline"}:
                    state.status = observed_state
                    state.consecutive_failures = 0
                    state.last_success_at = _iso()
                    state.last_error = error if observed_state == "offline" else ""
                else:
                    state.consecutive_failures += 1
                    state.last_error = error
                    if observed_state == "failed" or state.consecutive_failures >= max(1, spec.failure_threshold + 1):
                        state.status = "failed"
                    elif state.consecutive_failures >= max(1, spec.failure_threshold):
                        state.status = "suspect"
                    else:
                        state.status = observed_state if observed_state != "healthy" else "degraded"
            except Exception as error:
                state.consecutive_failures += 1
                state.last_error = str(error)
                state.detail = {"ok": False, "state": "degraded", "error": str(error)}
                state.status = "failed" if state.consecutive_failures > spec.failure_threshold else "suspect"

            if state.status != previous_status:
                changed.append((spec.name, previous_status, state.status))
                self._journal(
                    "state_changed", service=spec.name, status=state.status,
                    detail={"from": previous_status, "error": state.last_error, "consecutive_failures": state.consecutive_failures},
                )
            if auto_recover and state.status in {"suspect", "failed"}:
                self._recover(spec, state)

        self._last_cycle = time.monotonic()
        return self.snapshot(changed=changed)

    def restart_service(self, name: str, *, manual: bool = True) -> dict[str, Any]:
        with self._lock:
            spec = self._services.get(str(name))
            state = self._states.get(str(name))
        if spec is None or state is None:
            return {"ok": False, "error": "Serviço não encontrado."}
        if spec.recover is None:
            return {"ok": False, "error": "Este serviço não possui reinicialização segura."}
        if manual:
            state.last_recovery_monotonic = 0.0
            state.restart_times.clear()
        self._recover(spec, state)
        return {"ok": True, "service": str(name), "snapshot": self.snapshot()}

    def snapshot(self, *, changed: list[tuple[str, str, str]] | None = None) -> dict[str, Any]:
        with self._lock:
            services = []
            for name, spec in sorted(self._services.items(), key=lambda item: item[0]):
                state = self._states.setdefault(name, ServiceState())
                services.append({
                    "name": name,
                    "label": spec.label,
                    "status": state.status,
                    "critical": spec.critical,
                    "recoverable": spec.recover is not None,
                    "last_check_at": state.last_check_at,
                    "last_success_at": state.last_success_at,
                    "last_error": state.last_error,
                    "consecutive_failures": state.consecutive_failures,
                    "recoveries": state.recoveries,
                    "detail": dict(state.detail),
                })
            history = list(self._history)[-50:]
        active = [x for x in services if x["status"] != "disabled"]
        weights = {"healthy": 1.0, "offline": 0.92, "degraded": 0.65, "suspect": 0.4, "recovering": 0.55, "failed": 0.0, "initializing": 0.75}
        score = round(100.0 * (sum(weights.get(x["status"], 0.5) for x in active) / max(1, len(active))), 1)
        critical_failed = any(x["critical"] and x["status"] == "failed" for x in active)
        if critical_failed:
            overall = "failed"
        elif any(x["status"] in {"failed", "suspect"} for x in active):
            overall = "degraded"
        elif any(x["status"] in {"degraded", "recovering"} for x in active):
            overall = "attention"
        elif any(x["status"] == "offline" for x in active):
            overall = "offline_normal"
        else:
            overall = "healthy"
        return {
            "ok": not critical_failed,
            "overall": overall,
            "score": score,
            "enabled": bool(self.config.get("watchdog_enabled", True)),
            "auto_recover": bool(self.config.get("watchdog_auto_recover", True)),
            "interval_seconds": self.interval_seconds,
            "uptime_seconds": round(max(0.0, time.monotonic() - self._started_at), 1),
            "supervisor_thread_alive": bool(self._thread and self._thread.is_alive()),
            "last_cycle_age_seconds": round(max(0.0, time.monotonic() - self._last_cycle), 2) if self._last_cycle else None,
            "services": services,
            "history": history,
            "changed": changed or [],
        }


__all__ = ["RuntimeSupervisor", "ServiceSpec"]
