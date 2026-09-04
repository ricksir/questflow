from __future__ import annotations

"""QuestFlow 6.10.0 — Mobile Cloud Bridge.

The bridge is intentionally separate from Cloud Sync/Turso.  It publishes only
mobile-safe projections and a bounded study pack to an always-on gateway.  The
Mobile client can therefore continue studying when the Studio is offline,
while immutable learning events wait in the gateway until the Studio returns.

The gateway never receives the QuestFlow database credential or raw internal
SQLite tables.  It receives:
- public mobile projections;
- public question payloads plus server-side-only feedback material;
- hashes of active mobile bearer tokens;
- immutable mobile learning events on the return path.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import threading
import time
from typing import Any
import urllib.error
import urllib.parse
import urllib.request

from .secure_store import clear_secret, load_secret_map, save_secret_map

BRIDGE_SECRET_FILENAME = "mobile_cloud_bridge_credentials.dat"
BRIDGE_PROTOCOL = "questflow.mobile.cloud.v1"
DEFAULT_INTERVAL_SECONDS = 30
DEFAULT_PACK_SIZE = 40


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def normalize_bridge_url(value: str) -> str:
    text = str(value or "").strip().rstrip("/")
    if not text:
        return ""
    parsed = urllib.parse.urlparse(text)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("A URL do Mobile Cloud Bridge deve começar por https:// ou http://.")
    return text


def _secret_path(config_path: str | Path) -> Path:
    return Path(config_path).resolve().parent / BRIDGE_SECRET_FILENAME


def save_bridge_key(config_path: str | Path, key: str) -> None:
    value = str(key or "").strip()
    path = _secret_path(config_path)
    if not value:
        clear_secret(path)
        return
    save_secret_map(path, {"bridge_key": value}, description="QuestFlow Mobile Cloud Bridge Key")


def load_bridge_key(config_path: str | Path) -> str:
    return str(load_secret_map(_secret_path(config_path)).get("bridge_key", "") or "")


def clear_bridge_key(config_path: str | Path) -> None:
    clear_secret(_secret_path(config_path))


class BridgeHttpError(RuntimeError):
    def __init__(self, message: str, *, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class BridgeHttpClient:
    def __init__(self, base_url: str, bridge_key: str, *, timeout: float = 12.0) -> None:
        self.base_url = normalize_bridge_url(base_url)
        self.bridge_key = str(bridge_key or "").strip()
        self.timeout = max(2.0, float(timeout))

    def request(self, path: str, payload: dict[str, Any] | None = None, *, method: str = "POST") -> dict[str, Any]:
        if not self.base_url:
            raise BridgeHttpError("Mobile Cloud Bridge não configurado.")
        url = self.base_url + "/" + str(path or "").lstrip("/")
        body = None if payload is None else json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=body,
            method=method,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "QuestFlowStudio-MobileBridge/6.16.1",
                "X-QuestFlow-Bridge-Key": self.bridge_key,
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read()
                data = json.loads(raw.decode("utf-8")) if raw else {}
        except urllib.error.HTTPError as error:
            try:
                detail = json.loads(error.read().decode("utf-8"))
                message = str(detail.get("error") or detail.get("message") or error.reason)
            except Exception:
                message = str(error.reason or error)
            raise BridgeHttpError(message, status=int(error.code)) from error
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            raise BridgeHttpError(f"Não foi possível acessar o Mobile Cloud Bridge: {error}") from error
        if isinstance(data, dict) and data.get("ok") is False:
            raise BridgeHttpError(str(data.get("error") or "Falha no Mobile Cloud Bridge."))
        return data if isinstance(data, dict) else {"ok": True, "data": data}


@dataclass
class BridgeStatus:
    state: str = "disabled"
    last_sync_at: str = ""
    last_publish_at: str = ""
    last_drain_at: str = ""
    last_error: str = ""
    published_questions: int = 0
    drained_events: int = 0
    pending_remote_events: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "last_sync_at": self.last_sync_at,
            "last_publish_at": self.last_publish_at,
            "last_drain_at": self.last_drain_at,
            "last_error": self.last_error,
            "published_questions": self.published_questions,
            "drained_events": self.drained_events,
            "pending_remote_events": self.pending_remote_events,
        }


class MobileCloudBridgeEngine:
    def __init__(
        self,
        foundation: Any,
        *,
        config: dict[str, Any],
        config_path: str | Path,
        bridge_key_override: str = "",
    ) -> None:
        self.foundation = foundation
        self.config = config
        self.config_path = Path(config_path)
        self.bridge_key_override = str(bridge_key_override or "")
        self._status = BridgeStatus()
        self._lock = threading.RLock()

    def settings(self) -> dict[str, Any]:
        url = str(self.config.get("mobile_cloud_bridge_url", "") or "").strip()
        return {
            "mobile_cloud_bridge_enabled": bool(self.config.get("mobile_cloud_bridge_enabled", False)),
            "mobile_cloud_bridge_url": url,
            "mobile_cloud_bridge_key_configured": bool(self.bridge_key()),
            "mobile_cloud_bridge_interval_seconds": max(15, min(900, int(self.config.get("mobile_cloud_bridge_interval_seconds", DEFAULT_INTERVAL_SECONDS) or DEFAULT_INTERVAL_SECONDS))),
            "mobile_cloud_bridge_pack_size": max(8, min(100, int(self.config.get("mobile_cloud_bridge_pack_size", DEFAULT_PACK_SIZE) or DEFAULT_PACK_SIZE))),
            "protocol": BRIDGE_PROTOCOL,
        }

    def enabled(self) -> bool:
        settings = self.settings()
        return bool(settings["mobile_cloud_bridge_enabled"] and settings["mobile_cloud_bridge_url"])

    def bridge_key(self) -> str:
        return self.bridge_key_override or load_bridge_key(self.config_path)

    def client(self) -> BridgeHttpClient:
        return BridgeHttpClient(
            str(self.config.get("mobile_cloud_bridge_url", "") or ""),
            self.bridge_key(),
            timeout=float(self.config.get("cloud_sync_timeout_seconds", 15) or 15),
        )

    def client_projection(self) -> dict[str, Any]:
        settings = self.settings()
        status = self.safe_status()
        enabled = bool(settings["mobile_cloud_bridge_enabled"] and settings["mobile_cloud_bridge_url"] and settings["mobile_cloud_bridge_key_configured"])
        return {
            "enabled": enabled,
            "base_url": str(settings["mobile_cloud_bridge_url"] or ""),
            "protocol": BRIDGE_PROTOCOL,
            "state": status.get("state", "disabled"),
            "last_sync_at": status.get("last_sync_at", ""),
            "studio_required_for_pairing": True,
            "offline_study_pack": enabled,
        }

    def safe_status(self) -> dict[str, Any]:
        with self._lock:
            payload = self._status.to_dict()
        payload.update(self.settings())
        if not self.enabled():
            payload["state"] = "disabled"
        elif not self.bridge_key():
            payload["state"] = "needs_key"
        return payload

    def test_remote(self) -> dict[str, Any]:
        data = self.client().request("/bridge/v1/health", None, method="GET")
        with self._lock:
            self._status.state = "ready"
            self._status.last_error = ""
        return data

    def _active_sessions(self) -> list[dict[str, Any]]:
        with self.foundation.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT s.token_hash,s.device_id,s.expires_at,d.platform,d.name,d.app_version,d.status
                FROM qf_mobile_sessions s
                JOIN qf_mobile_devices d ON d.device_id=s.device_id
                WHERE s.revoked_at IS NULL AND d.status='active' AND s.expires_at>?
                ORDER BY s.created_at DESC
                """,
                (_utc_now(),),
            ).fetchall()
        return [dict(row) for row in rows]

    def _study_pack(self, count: int) -> list[dict[str, Any]]:
        batch = self.foundation.question_batch(count=count)
        result: list[dict[str, Any]] = []
        for position, public in enumerate(list(batch.get("questions") or []), start=1):
            uid = str(public.get("question_id") or "")
            revision = int(public.get("question_revision") or 1)
            snapshot = self.foundation.question_snapshot(uid, revision)
            if snapshot is None:
                try:
                    _revision, snapshot = self.foundation.current_question_revision(uid, capture_snapshot=True)
                except Exception:
                    snapshot = None
            if not isinstance(snapshot, dict):
                continue
            correct_index = self.foundation._answer_index(snapshot)
            alternatives = snapshot.get("alternativas") if isinstance(snapshot.get("alternativas"), list) else []
            correct_key = ""
            if correct_index is not None and 0 <= int(correct_index) < len(alternatives) and isinstance(alternatives[int(correct_index)], dict):
                correct_key = str(alternatives[int(correct_index)].get("chave") or "")
            result.append({
                "position": position,
                "public": public,
                "feedback": {
                    "correct_index": correct_index,
                    "correct_key": correct_key,
                    "explanation": str(snapshot.get("explicacao") or snapshot.get("comentario") or ""),
                },
            })
        return result

    def build_publish_payload(self) -> dict[str, Any]:
        identity = self.foundation.identity()
        pack_size = int(self.settings()["mobile_cloud_bridge_pack_size"])
        bootstrap = self.foundation.bootstrap_projection()
        return {
            "protocol": BRIDGE_PROTOCOL,
            "published_at": _utc_now(),
            "identity": {key: identity.get(key) for key in ("account_id", "tenant_id", "learner_id")},
            "sessions": self._active_sessions(),
            "projections": {
                "bootstrap": bootstrap,
                "today": bootstrap.get("today") or self.foundation.today_projection(),
                "progress": bootstrap.get("progress") or self.foundation.progress_projection(),
            },
            "study_pack": self._study_pack(pack_size),
        }

    def publish(self) -> dict[str, Any]:
        if not self.enabled():
            return {"ok": False, "state": "disabled", "error": "Mobile Cloud Bridge desativado."}
        if not self.bridge_key():
            return {"ok": False, "state": "needs_key", "error": "Chave do Mobile Cloud Bridge não configurada."}
        payload = self.build_publish_payload()
        try:
            result = self.client().request("/bridge/v1/publish", payload)
            with self._lock:
                self._status.state = "ready"
                self._status.last_error = ""
                self._status.last_publish_at = _utc_now()
                self._status.last_sync_at = self._status.last_publish_at
                self._status.published_questions = len(payload.get("study_pack") or [])
                self._status.pending_remote_events = int(result.get("pending_events") or 0)
            return {"ok": True, **result, "published_questions": len(payload.get("study_pack") or [])}
        except Exception as error:
            with self._lock:
                self._status.state = "error"
                self._status.last_error = str(error)
            return {"ok": False, "error": str(error)}

    def drain(self, *, limit: int = 250) -> dict[str, Any]:
        if not self.enabled() or not self.bridge_key():
            return {"ok": False, "state": "disabled", "error": "Mobile Cloud Bridge não disponível."}
        identity = self.foundation.identity()
        request = {"protocol": BRIDGE_PROTOCOL, "tenant_id": identity["tenant_id"], "limit": max(1, min(1000, int(limit or 250)))}
        try:
            remote = self.client().request("/bridge/v1/drain", request)
            events = remote.get("events") if isinstance(remote.get("events"), list) else []
            actions = remote.get("device_actions") if isinstance(remote.get("device_actions"), list) else []
            # Events were authenticated by the Gateway when received. Consume them
            # before device actions so an offline answer is never lost merely because
            # the user disconnected before the Studio came back online.
            ingested = self.foundation.ingest_cloud_events(events)
            acknowledged = sorted(set(list(ingested.get("accepted") or []) + list(ingested.get("duplicates") or [])))
            completed_action_ids: list[str] = []
            for action in actions:
                if str(action.get("action") or "") == "disconnect" and action.get("device_id"):
                    self.foundation.disconnect_device(str(action["device_id"]))
                    if action.get("action_id"):
                        completed_action_ids.append(str(action["action_id"]))
            action_ids = completed_action_ids
            if acknowledged or action_ids:
                self.client().request("/bridge/v1/ack", {
                    "protocol": BRIDGE_PROTOCOL,
                    "tenant_id": identity["tenant_id"],
                    "event_ids": acknowledged,
                    "action_ids": action_ids,
                })
            with self._lock:
                self._status.state = "ready"
                self._status.last_error = ""
                self._status.last_drain_at = _utc_now()
                self._status.last_sync_at = self._status.last_drain_at
                self._status.drained_events += len(acknowledged)
                self._status.pending_remote_events = int(remote.get("pending_events") or max(0, len(events) - len(acknowledged)))
            return {"ok": not bool(ingested.get("failed")), "remote": remote, "ingest": ingested, "acked": acknowledged, "device_actions": actions}
        except Exception as error:
            with self._lock:
                self._status.state = "error"
                self._status.last_error = str(error)
            return {"ok": False, "error": str(error)}

    def sync_once(self) -> dict[str, Any]:
        publish = self.publish()
        if not publish.get("ok"):
            return {"ok": False, "publish": publish, "drain": None, "status": self.safe_status()}
        drain = self.drain()
        return {"ok": bool(drain.get("ok", True)), "publish": publish, "drain": drain, "status": self.safe_status()}


class MobileCloudBridgeService:
    def __init__(self, engine: MobileCloudBridgeEngine) -> None:
        self.engine = engine
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            self._wake.set()
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="questflow-mobile-cloud-bridge")
        self._thread.start()

    def wake(self) -> None:
        self._wake.set()

    def _run(self) -> None:
        while not self._stop.is_set():
            if self.engine.enabled():
                self.engine.sync_once()
            interval = int(self.engine.settings()["mobile_cloud_bridge_interval_seconds"])
            self._wake.wait(timeout=interval)
            self._wake.clear()

    def stop(self, *, flush: bool = True, timeout: float = 8.0) -> dict[str, Any]:
        result: dict[str, Any] = {"ok": True}
        if flush and self.engine.enabled():
            result = self.engine.sync_once()
        self._stop.set()
        self._wake.set()
        thread = self._thread
        if thread and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=max(0.1, float(timeout)))
        return result


__all__ = [
    "BRIDGE_PROTOCOL",
    "MobileCloudBridgeEngine",
    "MobileCloudBridgeService",
    "BridgeHttpClient",
    "BridgeHttpError",
    "normalize_bridge_url",
    "save_bridge_key",
    "load_bridge_key",
    "clear_bridge_key",
]
