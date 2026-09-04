from __future__ import annotations

"""QuestFlow Mobile Cloud Gateway 0.5 (Studio 6.14.1).

Deployable, dependency-free HTTP gateway for the QuestFlow Mobile Cloud Bridge.
It is deliberately NOT the QuestFlow database.  It stores only bounded mobile
projections, a study pack and immutable events awaiting delivery to the Studio.

Quick start (development/VPS):
  set QUESTFLOW_BRIDGE_KEY=<strong-random-secret>
  python mobile_cloud_gateway.py --host 0.0.0.0 --port 8787 --db data/mobile-cloud-gateway.sqlite

For internet use, put this process behind HTTPS/reverse proxy.  The Mobile app
must use an https:// URL in production.
"""

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import sqlite3
import threading
from typing import Any
from urllib.parse import parse_qs, urlparse
import uuid

PROTOCOL = "questflow.mobile.cloud.v1"
MAX_BODY = 4 * 1024 * 1024


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def sha256(value: str) -> str:
    return hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()


def parse_iso(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except Exception:
        return None


class GatewayStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self.initialize()

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.path, timeout=20)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA journal_mode=WAL")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS bridge_tenants (
                    tenant_id TEXT PRIMARY KEY,
                    account_id TEXT NOT NULL,
                    learner_id TEXT NOT NULL,
                    last_publish_at TEXT NOT NULL,
                    protocol TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS bridge_sessions (
                    token_hash TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    device_id TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    platform TEXT,
                    name TEXT,
                    app_version TEXT,
                    status TEXT NOT NULL DEFAULT 'active',
                    published_at TEXT NOT NULL,
                    remote_disconnected_at TEXT,
                    FOREIGN KEY(tenant_id) REFERENCES bridge_tenants(tenant_id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_bridge_session_device ON bridge_sessions(tenant_id,device_id,status);
                CREATE TABLE IF NOT EXISTS bridge_projections (
                    tenant_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    published_at TEXT NOT NULL,
                    PRIMARY KEY(tenant_id,kind),
                    FOREIGN KEY(tenant_id) REFERENCES bridge_tenants(tenant_id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS bridge_questions (
                    tenant_id TEXT NOT NULL,
                    question_id TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    position INTEGER NOT NULL,
                    public_json TEXT NOT NULL,
                    feedback_json TEXT NOT NULL,
                    published_at TEXT NOT NULL,
                    active INTEGER NOT NULL DEFAULT 1,
                    PRIMARY KEY(tenant_id,question_id,revision),
                    FOREIGN KEY(tenant_id) REFERENCES bridge_tenants(tenant_id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_bridge_questions_active ON bridge_questions(tenant_id,active,position);
                CREATE TABLE IF NOT EXISTS bridge_adaptive_sessions (
                    session_id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    device_id TEXT NOT NULL,
                    target_questions INTEGER NOT NULL,
                    micro_batch_size INTEGER NOT NULL DEFAULT 3,
                    mode TEXT NOT NULL DEFAULT 'recommended',
                    subject TEXT NOT NULL DEFAULT '',
                    ordinal INTEGER NOT NULL DEFAULT 0,
                    served_json TEXT NOT NULL DEFAULT '[]',
                    goal_json TEXT NOT NULL DEFAULT '{}',
                    prefetched_json TEXT NOT NULL DEFAULT '[]',
                    prefetched_batch_id TEXT,
                    status TEXT NOT NULL DEFAULT 'active',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(tenant_id) REFERENCES bridge_tenants(tenant_id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_bridge_adaptive_session_device ON bridge_adaptive_sessions(tenant_id,device_id,status,updated_at DESC);
                CREATE TABLE IF NOT EXISTS bridge_events (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT NOT NULL UNIQUE,
                    tenant_id TEXT NOT NULL,
                    device_id TEXT NOT NULL,
                    event_json TEXT NOT NULL,
                    received_at TEXT NOT NULL,
                    acknowledged_at TEXT,
                    FOREIGN KEY(tenant_id) REFERENCES bridge_tenants(tenant_id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_bridge_events_pending ON bridge_events(tenant_id,acknowledged_at,seq);
                CREATE TABLE IF NOT EXISTS bridge_feedback (
                    tenant_id TEXT NOT NULL,
                    attempt_id TEXT NOT NULL,
                    device_id TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY(tenant_id,attempt_id)
                );
                CREATE TABLE IF NOT EXISTS bridge_device_actions (
                    action_id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    device_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    acknowledged_at TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_bridge_actions_pending ON bridge_device_actions(tenant_id,acknowledged_at,created_at);
                """
            )
            columns = {str(row[1]) for row in connection.execute("PRAGMA table_info(bridge_adaptive_sessions)").fetchall()}
            if "prefetched_json" not in columns:
                connection.execute("ALTER TABLE bridge_adaptive_sessions ADD COLUMN prefetched_json TEXT NOT NULL DEFAULT '[]'")
            if "prefetched_batch_id" not in columns:
                connection.execute("ALTER TABLE bridge_adaptive_sessions ADD COLUMN prefetched_batch_id TEXT")

    def publish(self, payload: dict[str, Any]) -> dict[str, Any]:
        identity = payload.get("identity") if isinstance(payload.get("identity"), dict) else {}
        tenant_id = str(identity.get("tenant_id") or "").strip()
        account_id = str(identity.get("account_id") or "").strip()
        learner_id = str(identity.get("learner_id") or "").strip()
        if not tenant_id or not account_id or not learner_id:
            raise ValueError("Identidade de tenant incompleta.")
        if str(payload.get("protocol") or "") != PROTOCOL:
            raise ValueError("Protocolo do Cloud Bridge incompatível.")
        published_at = str(payload.get("published_at") or utc_now())
        sessions = payload.get("sessions") if isinstance(payload.get("sessions"), list) else []
        projections = payload.get("projections") if isinstance(payload.get("projections"), dict) else {}
        study_pack = payload.get("study_pack") if isinstance(payload.get("study_pack"), list) else []
        with self._lock, self.connect() as connection:
            connection.execute(
                """INSERT INTO bridge_tenants(tenant_id,account_id,learner_id,last_publish_at,protocol)
                   VALUES(?,?,?,?,?) ON CONFLICT(tenant_id) DO UPDATE SET
                   account_id=excluded.account_id,learner_id=excluded.learner_id,
                   last_publish_at=excluded.last_publish_at,protocol=excluded.protocol""",
                (tenant_id, account_id, learner_id, published_at, PROTOCOL),
            )
            seen_hashes: set[str] = set()
            for item in sessions:
                if not isinstance(item, dict):
                    continue
                token_hash = str(item.get("token_hash") or "").strip()
                device_id = str(item.get("device_id") or "").strip()
                expires_at = str(item.get("expires_at") or "").strip()
                if not token_hash or not device_id or not expires_at:
                    continue
                seen_hashes.add(token_hash)
                existing = connection.execute("SELECT remote_disconnected_at FROM bridge_sessions WHERE token_hash=?", (token_hash,)).fetchone()
                remote_disconnected = str(existing["remote_disconnected_at"] or "") if existing else ""
                status = "disconnected" if remote_disconnected else "active"
                connection.execute(
                    """INSERT INTO bridge_sessions(token_hash,tenant_id,device_id,expires_at,platform,name,app_version,status,published_at,remote_disconnected_at)
                       VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(token_hash) DO UPDATE SET
                       tenant_id=excluded.tenant_id,device_id=excluded.device_id,expires_at=excluded.expires_at,
                       platform=excluded.platform,name=excluded.name,app_version=excluded.app_version,
                       status=CASE WHEN bridge_sessions.remote_disconnected_at IS NULL THEN excluded.status ELSE 'disconnected' END,
                       published_at=excluded.published_at""",
                    (token_hash, tenant_id, device_id, expires_at, item.get("platform"), item.get("name"), item.get("app_version"), status, published_at, remote_disconnected or None),
                )
            # Local Studio sessions no longer published are no longer cloud-active.
            if seen_hashes:
                placeholders = ",".join("?" for _ in seen_hashes)
                connection.execute(
                    f"UPDATE bridge_sessions SET status='disconnected' WHERE tenant_id=? AND token_hash NOT IN ({placeholders})",
                    (tenant_id, *sorted(seen_hashes)),
                )
            else:
                connection.execute("UPDATE bridge_sessions SET status='disconnected' WHERE tenant_id=?", (tenant_id,))

            # Mobile 0.8.1+: only study projections are accepted. Purge legacy
            # technical AI-health payloads from tenants that publish again.
            connection.execute("DELETE FROM bridge_projections WHERE tenant_id=? AND kind=\'ai_health\'", (tenant_id,))
            for kind in ("bootstrap", "today", "progress"):
                value = projections.get(kind)
                if not isinstance(value, dict):
                    continue
                connection.execute(
                    """INSERT INTO bridge_projections(tenant_id,kind,payload_json,published_at) VALUES(?,?,?,?)
                       ON CONFLICT(tenant_id,kind) DO UPDATE SET payload_json=excluded.payload_json,published_at=excluded.published_at""",
                    (tenant_id, kind, json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str), published_at),
                )

            connection.execute("UPDATE bridge_questions SET active=0 WHERE tenant_id=?", (tenant_id,))
            count = 0
            for entry in study_pack:
                if not isinstance(entry, dict):
                    continue
                public = entry.get("public") if isinstance(entry.get("public"), dict) else {}
                feedback = entry.get("feedback") if isinstance(entry.get("feedback"), dict) else {}
                question_id = str(public.get("question_id") or "").strip()
                revision = int(public.get("question_revision") or 1)
                if not question_id:
                    continue
                connection.execute(
                    """INSERT INTO bridge_questions(tenant_id,question_id,revision,position,public_json,feedback_json,published_at,active)
                       VALUES(?,?,?,?,?,?,?,1) ON CONFLICT(tenant_id,question_id,revision) DO UPDATE SET
                       position=excluded.position,public_json=excluded.public_json,feedback_json=excluded.feedback_json,
                       published_at=excluded.published_at,active=1""",
                    (tenant_id, question_id, revision, int(entry.get("position") or (count + 1)), json.dumps(public, ensure_ascii=False, separators=(",", ":")), json.dumps(feedback, ensure_ascii=False, separators=(",", ":")), published_at),
                )
                count += 1
            pending = int(connection.execute("SELECT COUNT(*) FROM bridge_events WHERE tenant_id=? AND acknowledged_at IS NULL", (tenant_id,)).fetchone()[0] or 0)
        return {"ok": True, "tenant_id": tenant_id, "published_questions": count, "pending_events": pending, "published_at": published_at}

    def authenticate(self, bearer: str) -> dict[str, Any]:
        token_hash = sha256(str(bearer or "").strip())
        if not bearer:
            raise PermissionError("Token ausente.")
        with self.connect() as connection:
            row = connection.execute(
                """SELECT s.*,t.account_id,t.learner_id,t.last_publish_at
                   FROM bridge_sessions s JOIN bridge_tenants t ON t.tenant_id=s.tenant_id
                   WHERE s.token_hash=?""",
                (token_hash,),
            ).fetchone()
        if not row or str(row["status"] or "") != "active" or row["remote_disconnected_at"]:
            raise PermissionError("Sessão Cloud Bridge inválida ou desconectada.")
        expiry = parse_iso(row["expires_at"])
        if expiry is None or expiry <= datetime.now(timezone.utc):
            raise PermissionError("Sessão Cloud Bridge expirada. Reconecte pelo QR no Studio.")
        return dict(row)

    def projection(self, tenant_id: str, kind: str) -> dict[str, Any]:
        with self.connect() as connection:
            row = connection.execute("SELECT payload_json,published_at FROM bridge_projections WHERE tenant_id=? AND kind=?", (tenant_id, kind)).fetchone()
            tenant = connection.execute("SELECT last_publish_at FROM bridge_tenants WHERE tenant_id=?", (tenant_id,)).fetchone()
            pending = int(connection.execute("SELECT COUNT(*) FROM bridge_events WHERE tenant_id=? AND acknowledged_at IS NULL", (tenant_id,)).fetchone()[0] or 0)
        if not row:
            raise ValueError("Projeção ainda não publicada pelo Studio.")
        data = json.loads(str(row["payload_json"]))
        last_publish = str(tenant["last_publish_at"] or row["published_at"] or "") if tenant else str(row["published_at"] or "")
        if isinstance(data, dict):
            if kind == "bootstrap":
                sync = data.get("sync") if isinstance(data.get("sync"), dict) else {}
                cloud = sync.get("cloud_bridge") if isinstance(sync.get("cloud_bridge"), dict) else {}
                cloud = dict(cloud)
                cloud.update({
                    "enabled": True,
                    "state": "ready",
                    "protocol": PROTOCOL,
                    "last_sync_at": last_publish,
                    "offline_study_pack": True,
                    "studio_required_for_pairing": True,
                })
                sync.update({
                    "transport": "cloud_bridge",
                    "cloud_bridge": cloud,
                    "last_studio_publish_at": last_publish,
                    "pending_remote_events": pending,
                })
                data["sync"] = sync
            # Mobile is a study-only surface. Operational channels (including
            # Telegram) belong exclusively to the Studio, even if an older cloud
            # projection is still cached on this gateway. Strip legacy channel
            # metadata instead of adapting or relabeling it for Mobile.
            data.pop("channels", None)
            if isinstance(data.get("today"), dict):
                today = dict(data["today"])
                today.pop("channels", None)
                data["today"] = today
            if isinstance(data.get("summary"), dict):
                summary = dict(data["summary"])
                summary.pop("channels", None)
                data["summary"] = summary
            if isinstance(data.get("recent_activity"), list):
                cleaned_activity = []
                for item in data["recent_activity"]:
                    if isinstance(item, dict):
                        item = dict(item)
                        item.pop("channel", None)
                    cleaned_activity.append(item)
                data["recent_activity"] = cleaned_activity
        return data

    def questions(self, tenant_id: str, count: int, *, mode: str = "recommended", subject: str = "", excluded_ids: list[str] | None = None) -> list[dict[str, Any]]:
        count = max(1, min(50, int(count or 8)))
        mode_key = str(mode or "recommended").strip().lower()
        subject_key = str(subject or "").strip().casefold()
        excluded = {str(value) for value in (excluded_ids or []) if str(value)}
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT public_json FROM bridge_questions WHERE tenant_id=? AND active=1 ORDER BY position ASC LIMIT 100",
                (tenant_id,),
            ).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            try:
                value = json.loads(str(row["public_json"]))
                if not isinstance(value, dict):
                    continue
                if str(value.get("question_id") or "") in excluded:
                    continue
                flags = value.get("study_flags") if isinstance(value.get("study_flags"), dict) else {}
                if mode_key == "review" and not bool(flags.get("due")):
                    continue
                if mode_key == "errors" and int(flags.get("wrong_count") or 0) <= 0:
                    continue
                if mode_key == "subject" and subject_key and str(value.get("subject") or "").strip().casefold() != subject_key:
                    continue
                result.append(value)
                if len(result) >= count:
                    break
            except Exception:
                continue
        return result

    def questions_by_ids(self, tenant_id: str, question_ids: list[str]) -> list[dict[str, Any]]:
        wanted = [str(x) for x in question_ids if str(x)]
        if not wanted:
            return []
        placeholders = ",".join("?" for _ in wanted)
        with self.connect() as connection:
            rows = connection.execute(
                f"SELECT question_id,public_json FROM bridge_questions WHERE tenant_id=? AND active=1 AND question_id IN ({placeholders})",
                (tenant_id, *wanted),
            ).fetchall()
        mapped: dict[str, dict[str, Any]] = {}
        for row in rows:
            try:
                value = json.loads(str(row["public_json"] or "{}"))
                if isinstance(value, dict): mapped[str(row["question_id"])] = value
            except Exception:
                pass
        return [mapped[qid] for qid in wanted if qid in mapped]

    def start_cached_adaptive_session(self, auth: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
        session_id = str(payload.get("session_id") or uuid.uuid4())
        target = max(1, min(50, int(payload.get("count") or 10)))
        micro = max(1, min(5, int(payload.get("micro_batch_size") or 3), target))
        mode = str(payload.get("mode") or "recommended").strip().lower()
        subject = str(payload.get("subject") or "").strip()
        questions = self.questions(str(auth["tenant_id"]), micro, mode=mode, subject=subject)
        now = utc_now()
        goal = {
            "type": "adaptive",
            "headline": "Continuar a sessão com o plano já preparado pelo QuestFlow",
            "questions_target": target,
            "estimated_minutes": max(1, int(round(target * 75 / 60))),
            "focus": [subject] if subject else ["prioridades já sincronizadas"],
            "strategy_profile": "offline_fallback",
        }
        served = [str(q.get("question_id") or "") for q in questions if str(q.get("question_id") or "")]
        with self._lock, self.connect() as connection:
            connection.execute(
                """INSERT OR REPLACE INTO bridge_adaptive_sessions(
                    session_id,tenant_id,device_id,target_questions,micro_batch_size,mode,subject,ordinal,served_json,goal_json,status,created_at,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?, 'active',?,?)""",
                (session_id, str(auth["tenant_id"]), str(auth["device_id"]), target, micro, mode, subject, 1,
                 json.dumps(served, separators=(",", ":")), json.dumps(goal, ensure_ascii=False, separators=(",", ":")), now, now),
            )
        return {
            "contract": "questflow.mobile.adaptive_session.v1",
            "orchestrator": "cloud-bridge-cached-plan-v1",
            "session_id": session_id,
            "target_questions": target,
            "micro_batch_size": micro,
            "goal": goal,
            "micro_batch": {
                "batch_id": f"cloud-{session_id}-1", "ordinal": 1, "plan_revision": 0, "purpose": "active",
                "strategy_profile": "offline_fallback", "questions": questions, "completed": not bool(questions),
                "cached_plan": True,
            },
        }

    def next_cached_adaptive_batch(self, auth: dict[str, Any], session_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM bridge_adaptive_sessions WHERE session_id=? AND tenant_id=? AND device_id=? AND status='active'",
                (str(session_id), str(auth["tenant_id"]), str(auth["device_id"])),
            ).fetchone()
        if not row:
            raise ValueError("Sessão adaptativa em cache não encontrada no Cloud Bridge.")
        try:
            served = {str(x) for x in json.loads(str(row["served_json"] or "[]"))}
        except Exception:
            served = set()
        served.update(str(x) for x in list(payload.get("excluded_question_ids") or []) if str(x))
        target = int(row["target_questions"] or 0)
        micro_size = int(row["micro_batch_size"] or 3)
        purpose = "prefetch" if str(payload.get("purpose") or "").lower() == "prefetch" else "active"
        force_replan = bool(payload.get("force_replan"))
        requested_prefetch = str(payload.get("prefetched_batch_id") or "")
        stored_prefetch_id = str(row["prefetched_batch_id"] or "")
        try:
            stored_prefetch_ids = [str(x) for x in json.loads(str(row["prefetched_json"] or "[]")) if str(x)]
        except Exception:
            stored_prefetch_ids = []

        if force_replan:
            stored_prefetch_id = ""
            stored_prefetch_ids = []
            with self._lock, self.connect() as connection:
                connection.execute(
                    "UPDATE bridge_adaptive_sessions SET prefetched_json='[]',prefetched_batch_id=NULL,updated_at=? WHERE session_id=?",
                    (utc_now(), str(session_id)),
                )

        if purpose == "prefetch" and stored_prefetch_id and stored_prefetch_ids:
            questions = self.questions_by_ids(str(auth["tenant_id"]), stored_prefetch_ids)
            batch_id = stored_prefetch_id
            ordinal = int(row["ordinal"] or 0) + 1
        elif purpose == "active" and requested_prefetch and requested_prefetch == stored_prefetch_id and stored_prefetch_ids and not force_replan:
            questions = self.questions_by_ids(str(auth["tenant_id"]), stored_prefetch_ids)
            batch_id = stored_prefetch_id
            ordinal = int(row["ordinal"] or 0) + 1
            served.update(str(q.get("question_id") or "") for q in questions if str(q.get("question_id") or ""))
            with self._lock, self.connect() as connection:
                connection.execute(
                    "UPDATE bridge_adaptive_sessions SET ordinal=?,served_json=?,prefetched_json='[]',prefetched_batch_id=NULL,updated_at=?,status=? WHERE session_id=?",
                    (ordinal, json.dumps(sorted(served), separators=(",", ":")), utc_now(),
                     "completed" if len(served) >= target else "active", str(session_id)),
                )
        else:
            remaining = max(0, target - len(served))
            micro = min(micro_size, remaining)
            questions = self.questions(
                str(auth["tenant_id"]), max(1, micro) if micro else 1,
                mode=str(row["mode"]), subject=str(row["subject"]), excluded_ids=list(served),
            ) if micro else []
            ids = [str(q.get("question_id") or "") for q in questions if str(q.get("question_id") or "")]
            ordinal = int(row["ordinal"] or 0) + (1 if questions else 0)
            batch_id = f"cloud-{session_id}-{ordinal}-{uuid.uuid4().hex[:8]}" if questions else ""
            now = utc_now()
            with self._lock, self.connect() as connection:
                if purpose == "prefetch" and questions:
                    connection.execute(
                        "UPDATE bridge_adaptive_sessions SET prefetched_json=?,prefetched_batch_id=?,updated_at=? WHERE session_id=?",
                        (json.dumps(ids, separators=(",", ":")), batch_id, now, str(session_id)),
                    )
                else:
                    served.update(ids)
                    connection.execute(
                        "UPDATE bridge_adaptive_sessions SET ordinal=?,served_json=?,updated_at=?,status=? WHERE session_id=?",
                        (ordinal, json.dumps(sorted(served), separators=(",", ":")), now,
                         "completed" if not questions or len(served) >= target else "active", str(session_id)),
                    )

        return {
            "contract": "questflow.mobile.adaptive_session.v1",
            "orchestrator": "cloud-bridge-cached-plan-v1",
            "session_id": str(session_id),
            "target_questions": target,
            "micro_batch_size": micro_size,
            "goal": json.loads(str(row["goal_json"] or "{}")),
            "micro_batch": {
                "batch_id": batch_id, "ordinal": ordinal, "plan_revision": 0, "purpose": purpose,
                "strategy_profile": "offline_fallback", "questions": questions, "completed": not bool(questions),
                "cached_plan": True, "replan_available": False,
            },
        }

    def _question_feedback(self, tenant_id: str, question_id: str, revision: int) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT feedback_json FROM bridge_questions WHERE tenant_id=? AND question_id=? AND revision=? AND active=1",
                (tenant_id, question_id, int(revision)),
            ).fetchone()
        if not row:
            return None
        try:
            value = json.loads(str(row["feedback_json"]))
            return value if isinstance(value, dict) else None
        except Exception:
            return None

    def ingest_events(self, auth: dict[str, Any], events: list[Any]) -> dict[str, Any]:
        accepted: list[str] = []
        duplicates: list[str] = []
        failed: list[dict[str, str]] = []
        tenant_id = str(auth["tenant_id"])
        device_id = str(auth["device_id"])
        with self._lock, self.connect() as connection:
            for raw in events:
                if not isinstance(raw, dict):
                    failed.append({"event_id": "", "error": "Evento inválido."})
                    continue
                event_id = str(raw.get("event_id") or "").strip()
                supplied_device = str(raw.get("device_id") or device_id).strip()
                if not event_id:
                    failed.append({"event_id": "", "error": "event_id obrigatório."})
                    continue
                if supplied_device != device_id:
                    failed.append({"event_id": event_id, "error": "Evento pertence a outro aparelho."})
                    continue
                existing = connection.execute("SELECT event_json FROM bridge_events WHERE event_id=?", (event_id,)).fetchone()
                serialized = json.dumps(raw, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
                if existing:
                    if str(existing["event_json"]) != serialized:
                        failed.append({"event_id": event_id, "error": "event_id já existe com conteúdo diferente."})
                    else:
                        duplicates.append(event_id)
                    continue
                connection.execute(
                    "INSERT INTO bridge_events(event_id,tenant_id,device_id,event_json,received_at) VALUES(?,?,?,?,?)",
                    (event_id, tenant_id, device_id, serialized, utc_now()),
                )
                accepted.append(event_id)
                if str(raw.get("event_type") or "") == "answer_submitted":
                    self._create_feedback(connection, tenant_id, device_id, raw)
            cursor = int(connection.execute("SELECT COALESCE(MAX(seq),0) FROM bridge_events WHERE tenant_id=?", (tenant_id,)).fetchone()[0] or 0)
        return {"accepted": accepted, "duplicates": duplicates, "failed": failed, "cursor": cursor}

    def _create_feedback(self, connection: sqlite3.Connection, tenant_id: str, device_id: str, event: dict[str, Any]) -> None:
        attempt_id = str(event.get("attempt_id") or event.get("event_id") or "").strip()
        question_id = str(event.get("question_id") or event.get("question_uid") or "").strip()
        revision = int(event.get("question_revision") or 1)
        if not attempt_id or not question_id:
            return
        row = connection.execute(
            "SELECT feedback_json FROM bridge_questions WHERE tenant_id=? AND question_id=? AND revision=? AND active=1",
            (tenant_id, question_id, revision),
        ).fetchone()
        if not row:
            return
        try:
            private = json.loads(str(row["feedback_json"]))
        except Exception:
            private = {}
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        selected = payload.get("selected_indices")
        if not isinstance(selected, list):
            selected = [] if payload.get("selected_index") is None else [payload.get("selected_index")]
        try:
            selected_index = int(selected[0]) if selected else -1
        except Exception:
            selected_index = -1
        correct_index = private.get("correct_index")
        is_correct = correct_index is not None and selected_index == int(correct_index)
        timing = {
            "active_response_seconds": payload.get("active_response_seconds"),
            "wall_response_seconds": payload.get("wall_response_seconds"),
            "idle_seconds": payload.get("idle_seconds"),
            "quality": "pending_studio_validation",
        }
        feedback = {
            "attempt_id": attempt_id,
            "question_id": question_id,
            "question_revision": revision,
            "selected_indices": selected,
            "is_correct": bool(is_correct),
            "correct_index": correct_index,
            "correct_key": str(private.get("correct_key") or ""),
            "explanation": str(private.get("explanation") or ""),
            "timing": timing,
            "provisional": True,
            "source": "cloud_bridge_study_pack",
        }
        connection.execute(
            """INSERT INTO bridge_feedback(tenant_id,attempt_id,device_id,payload_json,created_at) VALUES(?,?,?,?,?)
               ON CONFLICT(tenant_id,attempt_id) DO UPDATE SET payload_json=excluded.payload_json""",
            (tenant_id, attempt_id, device_id, json.dumps(feedback, ensure_ascii=False, separators=(",", ":")), utc_now()),
        )

    def feedback(self, auth: dict[str, Any], attempt_id: str) -> dict[str, Any]:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT payload_json,device_id FROM bridge_feedback WHERE tenant_id=? AND attempt_id=?",
                (str(auth["tenant_id"]), str(attempt_id)),
            ).fetchone()
        if not row:
            raise ValueError("Feedback ainda não disponível no Cloud Bridge.")
        if str(row["device_id"] or "") != str(auth["device_id"]):
            raise PermissionError("Tentativa pertence a outro aparelho.")
        return json.loads(str(row["payload_json"]))

    def drain(self, tenant_id: str, limit: int) -> dict[str, Any]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT event_id,event_json FROM bridge_events WHERE tenant_id=? AND acknowledged_at IS NULL ORDER BY seq ASC LIMIT ?",
                (tenant_id, max(1, min(1000, int(limit or 250)))),
            ).fetchall()
            action_rows = connection.execute(
                "SELECT action_id,device_id,action,created_at FROM bridge_device_actions WHERE tenant_id=? AND acknowledged_at IS NULL ORDER BY created_at ASC LIMIT 100",
                (tenant_id,),
            ).fetchall()
            pending = int(connection.execute("SELECT COUNT(*) FROM bridge_events WHERE tenant_id=? AND acknowledged_at IS NULL", (tenant_id,)).fetchone()[0] or 0)
        events: list[dict[str, Any]] = []
        for row in rows:
            try:
                event = json.loads(str(row["event_json"]))
                if isinstance(event, dict):
                    events.append(event)
            except Exception:
                continue
        return {"ok": True, "events": events, "device_actions": [dict(row) for row in action_rows], "pending_events": pending}

    def ack(self, tenant_id: str, event_ids: list[Any], action_ids: list[Any]) -> dict[str, Any]:
        now = utc_now()
        with self._lock, self.connect() as connection:
            for event_id in event_ids:
                connection.execute("UPDATE bridge_events SET acknowledged_at=? WHERE tenant_id=? AND event_id=?", (now, tenant_id, str(event_id)))
            for action_id in action_ids:
                connection.execute("UPDATE bridge_device_actions SET acknowledged_at=? WHERE tenant_id=? AND action_id=?", (now, tenant_id, str(action_id)))
            pending = int(connection.execute("SELECT COUNT(*) FROM bridge_events WHERE tenant_id=? AND acknowledged_at IS NULL", (tenant_id,)).fetchone()[0] or 0)
        return {"ok": True, "pending_events": pending}

    def disconnect(self, auth: dict[str, Any], device_id: str) -> dict[str, Any]:
        if str(device_id) != str(auth["device_id"]):
            raise PermissionError("Um aparelho só pode desconectar a própria sessão.")
        now = utc_now()
        action_id = str(uuid.uuid4())
        with self._lock, self.connect() as connection:
            connection.execute(
                "UPDATE bridge_sessions SET status='disconnected',remote_disconnected_at=? WHERE token_hash=?",
                (now, str(auth["token_hash"])),
            )
            connection.execute(
                "INSERT INTO bridge_device_actions(action_id,tenant_id,device_id,action,created_at) VALUES(?,?,?,?,?)",
                (action_id, str(auth["tenant_id"]), str(device_id), "disconnect", now),
            )
        return {"ok": True, "device_id": str(device_id), "disconnected_at": now, "action_id": action_id}

    def status(self, tenant_id: str) -> dict[str, Any]:
        with self.connect() as connection:
            tenant = connection.execute("SELECT * FROM bridge_tenants WHERE tenant_id=?", (tenant_id,)).fetchone()
            pending = int(connection.execute("SELECT COUNT(*) FROM bridge_events WHERE tenant_id=? AND acknowledged_at IS NULL", (tenant_id,)).fetchone()[0] or 0)
            questions = int(connection.execute("SELECT COUNT(*) FROM bridge_questions WHERE tenant_id=? AND active=1", (tenant_id,)).fetchone()[0] or 0)
            sessions = int(connection.execute("SELECT COUNT(*) FROM bridge_sessions WHERE tenant_id=? AND status='active'", (tenant_id,)).fetchone()[0] or 0)
        return {
            "ok": True,
            "protocol": PROTOCOL,
            "tenant_id": tenant_id,
            "last_publish_at": str(tenant["last_publish_at"] or "") if tenant else "",
            "pending_events": pending,
            "study_pack_questions": questions,
            "active_sessions": sessions,
        }


class GatewayHandler(BaseHTTPRequestHandler):
    server: "GatewayServer"
    server_version = "QuestFlowMobileCloudGateway/0.5"

    def log_message(self, fmt: str, *args: Any) -> None:
        if self.server.verbose:
            super().log_message(fmt, *args)

    def _json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0") or 0)
        if length < 0 or length > MAX_BODY:
            raise ValueError("Corpo da requisição excede o limite do gateway.")
        raw = self.rfile.read(length) if length else b"{}"
        value = json.loads(raw.decode("utf-8")) if raw else {}
        return value if isinstance(value, dict) else {}

    def _admin(self) -> None:
        expected = self.server.bridge_key
        supplied = str(self.headers.get("X-QuestFlow-Bridge-Key", "") or "")
        if not expected or not supplied or not hashlib.sha256(supplied.encode()).digest() == hashlib.sha256(expected.encode()).digest():
            raise PermissionError("Chave administrativa do Cloud Bridge inválida.")

    def _bearer(self) -> str:
        value = str(self.headers.get("Authorization", "") or "")
        return value[7:].strip() if value.lower().startswith("bearer ") else ""

    def _route(self, method: str) -> None:
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        query = parse_qs(parsed.query)
        try:
            if path == "/bridge/v1/health" and method == "GET":
                self._admin()
                self._json(200, {"ok": True, "protocol": PROTOCOL, "server_time": utc_now(), "gateway": "QuestFlow Mobile Cloud Gateway 0.5"})
                return
            if path == "/bridge/v1/publish" and method == "POST":
                self._admin()
                self._json(200, self.server.store.publish(self._body()))
                return
            if path == "/bridge/v1/drain" and method == "POST":
                self._admin()
                body = self._body()
                tenant_id = str(body.get("tenant_id") or "")
                if not tenant_id:
                    raise ValueError("tenant_id obrigatório.")
                self._json(200, self.server.store.drain(tenant_id, int(body.get("limit") or 250)))
                return
            if path == "/bridge/v1/ack" and method == "POST":
                self._admin()
                body = self._body()
                tenant_id = str(body.get("tenant_id") or "")
                self._json(200, self.server.store.ack(tenant_id, list(body.get("event_ids") or []), list(body.get("action_ids") or [])))
                return
            if path == "/bridge/v1/status" and method == "GET":
                self._admin()
                tenant_id = str((query.get("tenant_id") or [""])[0])
                self._json(200, self.server.store.status(tenant_id))
                return

            if path == "/api/v1/mobile/health" and method == "GET":
                self._json(200, {
                    "ok": True,
                    "api": "questflow.mobile.v1",
                    "schema_version": 1,
                    "server_time": utc_now(),
                    "transport": "cloud_bridge",
                    "cloud_bridge": True,
                    "pairing_supported": False,
                })
                return

            auth = self.server.store.authenticate(self._bearer())
            tenant_id = str(auth["tenant_id"])
            if path == "/api/v1/mobile/bootstrap" and method == "GET":
                self._json(200, {"ok": True, "data": self.server.store.projection(tenant_id, "bootstrap")})
                return
            if path == "/api/v1/mobile/today" and method == "GET":
                self._json(200, {"ok": True, "data": self.server.store.projection(tenant_id, "today")})
                return
            if path == "/api/v1/mobile/progress" and method == "GET":
                self._json(200, {"ok": True, "data": self.server.store.projection(tenant_id, "progress")})
                return
            if path == "/api/v1/mobile/study-sessions" and method == "POST":
                self._json(200, {"ok": True, "data": self.server.store.start_cached_adaptive_session(auth, self._body())})
                return
            if path.startswith("/api/v1/mobile/study-sessions/") and path.endswith("/micro-batches") and method == "POST":
                session_id = path.split("/")[-2]
                self._json(200, {"ok": True, "data": self.server.store.next_cached_adaptive_batch(auth, session_id, self._body())})
                return
            if path == "/api/v1/mobile/question-batches" and method == "POST":
                body = self._body()
                mode = str(body.get("mode") or "recommended")
                subject = str(body.get("subject") or "")
                questions = self.server.store.questions(tenant_id, int(body.get("count") or 8), mode=mode, subject=subject)
                self._json(200, {"ok": True, "data": {"contract": "questflow.mobile.v1", "source": "cloud_bridge", "mode": mode, "subject": subject, "questions": questions}})
                return
            if path == "/api/v1/mobile/sync" and method == "POST":
                body = self._body()
                result = self.server.store.ingest_events(auth, list(body.get("events") or []))
                self._json(200, {
                    "ok": not bool(result["failed"]),
                    "push": {key: result[key] for key in ("accepted", "duplicates", "failed")},
                    "pull": {"contract": "questflow.mobile.v1", "cursor": result["cursor"], "has_more": False, "events": [], "server_time": utc_now(), "transport": "cloud_bridge"},
                })
                return
            if path.startswith("/api/v1/mobile/attempts/") and path.endswith("/feedback") and method == "GET":
                attempt_id = path.split("/")[-2]
                self._json(200, {"ok": True, "data": self.server.store.feedback(auth, attempt_id)})
                return
            if path.startswith("/api/v1/mobile/devices/") and method == "DELETE":
                device_id = path.rsplit("/", 1)[-1]
                self._json(200, self.server.store.disconnect(auth, device_id))
                return
            if path == "/api/v1/mobile/cloud/status" and method == "GET":
                self._json(200, self.server.store.status(tenant_id))
                return
            self._json(404, {"ok": False, "error": "Rota não encontrada no Mobile Cloud Gateway."})
        except PermissionError as error:
            self._json(401, {"ok": False, "error": str(error)})
        except (ValueError, TypeError, KeyError, json.JSONDecodeError) as error:
            self._json(400, {"ok": False, "error": str(error)})
        except Exception as error:
            self._json(500, {"ok": False, "error": str(error)})

    def do_GET(self) -> None:
        self._route("GET")

    def do_POST(self) -> None:
        self._route("POST")

    def do_DELETE(self) -> None:
        self._route("DELETE")


class GatewayServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address: tuple[str, int], store: GatewayStore, bridge_key: str, *, verbose: bool = False) -> None:
        super().__init__(address, GatewayHandler)
        self.store = store
        self.bridge_key = str(bridge_key or "")
        self.verbose = bool(verbose)


def main() -> int:
    parser = argparse.ArgumentParser(description="QuestFlow Mobile Cloud Gateway 0.5")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--db", default="data/mobile-cloud-gateway.sqlite")
    parser.add_argument("--key", default="", help="Chave administrativa. Prefira QUESTFLOW_BRIDGE_KEY.")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    key = str(args.key or os.environ.get("QUESTFLOW_BRIDGE_KEY", "") or "").strip()
    if len(key) < 20:
        raise SystemExit("Defina QUESTFLOW_BRIDGE_KEY com uma chave aleatória de pelo menos 20 caracteres.")
    server = GatewayServer((args.host, int(args.port)), GatewayStore(args.db), key, verbose=args.verbose)
    print(f"QuestFlow Mobile Cloud Gateway 0.5 em http://{args.host}:{args.port} | db={args.db}")
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
