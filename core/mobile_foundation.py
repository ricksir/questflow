from __future__ import annotations

"""QuestFlow 6.9.0 — Mobile Integration Foundation.

This module intentionally keeps the mobile contract separated from the desktop
schema.  The future iOS/Android client consumes stable projections and immutable
learning events rather than reading internal tables directly.

The service is dependency-free (stdlib + the existing QuestFlow core) so the
6.9.0 foundation can be exercised before the React Native application exists.
"""

from dataclasses import asdict, dataclass
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import secrets
import sqlite3
import threading
import uuid
from typing import Any, Iterable

from .schema_migrations import apply_migration
from .study_batch_service import StudyBatchService
from .adaptive_session_orchestrator import AdaptiveSessionOrchestrator, DEFAULT_MICRO_BATCH_SIZE

MOBILE_API_VERSION = "v1"
MOBILE_SCHEMA_VERSION = 1
MOBILE_CONTRACT = "questflow.mobile.v1"
PAIRING_TTL_MINUTES = 5
ACCESS_TOKEN_TTL_DAYS = 30

# A question may genuinely demand several minutes.  The limit below is a data
# quality guardrail, not a pedagogical time limit.  Values outside it are kept
# for audit but not used as a speed signal.
MAX_ACTIVE_RESPONSE_SECONDS = 30 * 60
IDLE_CONTAMINATION_SECONDS = 5 * 60

LEARNING_EVENT_TYPES = frozenset(
    {
        "session_started",
        "session_ended",
        "question_presented",
        "question_opened",
        "answer_selected",
        "answer_changed",
        "answer_submitted",
        "confidence_reported",
        "difficulty_reported",
        "result_seen",
        "explanation_opened",
        "explanation_finished",
        "learning_gap_reported",
        "question_skipped",
        "question_correction_requested",
        "topic_not_studied_reported",
        "topic_study_completed",
        "hint_requested",
        "scaffold_used",
    }
)

TIMING_ELIGIBLE_QUALITIES = frozenset({"valid", "active_filtered"})


def utc_now_dt() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def utc_now() -> str:
    return utc_now_dt().isoformat()


def parse_iso(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def _float_or_none(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int_or_none(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, float(value)))


@dataclass(slots=True, frozen=True)
class TimingAssessment:
    """Result of the response-time quality gate.

    ``active_seconds`` is the only value eligible for learning analytics.  Wall
    clock and idle time are retained for audit.  A large wall time can coexist
    with a valid active time when the mobile client used its foreground/idle
    aware monotonic timer.
    """

    active_seconds: float | None
    wall_seconds: float | None
    idle_seconds: float | None
    quality: str
    source: str
    eligible_for_speed_models: bool
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def assess_response_timing(
    *,
    active_seconds: Any = None,
    wall_seconds: Any = None,
    idle_seconds: Any = None,
    source: str = "",
    abandoned: bool = False,
    max_idle_gap_seconds: Any = None,
    interaction_count: Any = None,
) -> TimingAssessment:
    """Validate timing without confusing an open screen with study time.

    Preferred client behavior (``client_active_timer_v1``): count time only
    while the app is foregrounded, the question is visible and the user is not
    idle.  The raw wall time may therefore be hours while active time is only a
    few minutes; that is acceptable and is labelled ``active_filtered``.

    A simple wall-clock measurement is rejected whenever there is evidence of
    long inactivity, because it would punish a user who left the app open.
    """

    active = _float_or_none(active_seconds)
    wall = _float_or_none(wall_seconds)
    idle = _float_or_none(idle_seconds)
    source_norm = str(source or "").strip().lower() or "unknown"
    max_idle_gap = _float_or_none(max_idle_gap_seconds)
    interactions = _int_or_none(interaction_count)

    if abandoned:
        return TimingAssessment(active, wall, idle, "abandoned", source_norm, False, "Questão abandonada/sem resposta contínua confiável.")
    if active is not None and active < 0:
        return TimingAssessment(None, wall, idle, "invalid", source_norm, False, "Tempo ativo negativo.")
    if wall is not None and wall < 0:
        return TimingAssessment(active, None, idle, "invalid", source_norm, False, "Tempo de relógio negativo.")
    if idle is not None and idle < 0:
        idle = None

    trusted_active = source_norm in {
        "client_active_timer_v1",
        "mobile_active_timer",
        "desktop_active_timer_v1",
    }

    if active is None:
        # Legacy/wall-only timing is deliberately not promoted to an active
        # metric.  It remains available for audit only.
        if wall is None:
            return TimingAssessment(None, None, idle, "missing", source_norm, False, "Nenhum tempo ativo confiável foi informado.")
        if wall > IDLE_CONTAMINATION_SECONDS:
            return TimingAssessment(None, wall, idle, "idle_contaminated", source_norm, False, "Apenas tempo de relógio disponível; possível abandono/inatividade.")
        return TimingAssessment(None, wall, idle, "wall_clock_unverified", source_norm, False, "Tempo de relógio sem medição ativa; excluído dos modelos de velocidade.")

    if active > MAX_ACTIVE_RESPONSE_SECONDS:
        return TimingAssessment(active, wall, idle, "outlier", source_norm, False, "Tempo ativo acima do limite de qualidade de 30 minutos.")

    if wall is not None and active > wall + 5.0:
        return TimingAssessment(active, wall, idle, "invalid", source_norm, False, "Tempo ativo maior que o tempo total de relógio.")

    inferred_idle = idle
    if inferred_idle is None and wall is not None:
        inferred_idle = max(0.0, wall - active)

    if trusted_active:
        # O cliente oficial envia apenas agregados de atividade (sem coordenadas
        # ou histórico de toques). Se uma questão ficou aberta por muito tempo
        # quase sem interação e o timer não separou nenhum período ocioso, o
        # servidor prefere descartar a velocidade a rotular o aluno como lento.
        suspicious_long_open = bool(
            wall is not None
            and wall >= 2 * IDLE_CONTAMINATION_SECONDS
            and (inferred_idle or 0.0) < IDLE_CONTAMINATION_SECONDS
            and interactions is not None
            and interactions <= 2
        )
        inconsistent_idle = bool(
            max_idle_gap is not None
            and max_idle_gap >= IDLE_CONTAMINATION_SECONDS
            and (inferred_idle or 0.0) < IDLE_CONTAMINATION_SECONDS
        )
        if suspicious_long_open or inconsistent_idle:
            return TimingAssessment(
                active, wall, inferred_idle, "idle_contaminated", source_norm, False,
                "Questão permaneceu aberta por longo período sem evidência suficiente de atividade contínua; velocidade descartada."
            )
        quality = "active_filtered" if (inferred_idle or 0.0) >= IDLE_CONTAMINATION_SECONDS else "valid"
        reason = (
            "Tempo ativo medido por temporizador que pausa em background/inatividade."
            if quality == "active_filtered"
            else "Tempo ativo consistente."
        )
        return TimingAssessment(round(active, 3), wall, inferred_idle, quality, source_norm, True, reason)

    # An untrusted active value is accepted only when wall-clock evidence also
    # indicates a short, continuous interaction.
    if wall is not None and (inferred_idle or 0.0) < IDLE_CONTAMINATION_SECONDS and wall <= MAX_ACTIVE_RESPONSE_SECONDS:
        return TimingAssessment(round(active, 3), wall, inferred_idle, "valid", source_norm, True, "Tempo curto e consistente, sem indício de longa inatividade.")

    return TimingAssessment(active, wall, inferred_idle, "idle_contaminated", source_norm, False, "Medição não distingue adequadamente tempo ativo de tempo com a tela abandonada.")


class TenantControlPlane:
    """Small local control plane for database-per-tenant provisioning.

    The current desktop database is registered as one tenant without moving it,
    preserving compatibility.  New tenants can be provisioned into independent
    SQLite files.  A cloud/Turso adapter can later replace the locator while the
    contract remains unchanged.
    """

    def __init__(self, path: str | Path, tenants_root: str | Path):
        self.path = Path(path)
        self.tenants_root = Path(tenants_root)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.tenants_root.mkdir(parents=True, exist_ok=True)
        self.initialize()

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
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
                CREATE TABLE IF NOT EXISTS qf_accounts (
                    account_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active'
                );
                CREATE TABLE IF NOT EXISTS qf_tenants (
                    tenant_id TEXT PRIMARY KEY,
                    account_id TEXT NOT NULL,
                    database_locator TEXT NOT NULL UNIQUE,
                    schema_version INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active',
                    FOREIGN KEY(account_id) REFERENCES qf_accounts(account_id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_qf_tenants_account ON qf_tenants(account_id, status);
                """
            )

    def register_existing(self, *, account_id: str, tenant_id: str, database_locator: str) -> dict[str, Any]:
        now = utc_now()
        with self.connect() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO qf_accounts(account_id,created_at,status) VALUES(?,?,'active')",
                (account_id, now),
            )
            connection.execute(
                """
                INSERT INTO qf_tenants(tenant_id,account_id,database_locator,schema_version,created_at,status)
                VALUES(?,?,?,? ,?,'active')
                ON CONFLICT(tenant_id) DO UPDATE SET
                    account_id=excluded.account_id,
                    database_locator=excluded.database_locator,
                    schema_version=MAX(qf_tenants.schema_version, excluded.schema_version),
                    status='active'
                """,
                (tenant_id, account_id, str(database_locator), MOBILE_SCHEMA_VERSION, now),
            )
        return self.get_tenant(tenant_id) or {}

    def provision_tenant(self, *, account_id: str | None = None) -> dict[str, Any]:
        account = str(account_id or uuid.uuid4())
        tenant = str(uuid.uuid4())
        database_path = self.tenants_root / tenant / "questflow.sqlite"
        database_path.parent.mkdir(parents=True, exist_ok=True)
        now = utc_now()
        with self.connect() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO qf_accounts(account_id,created_at,status) VALUES(?,?,'active')",
                (account, now),
            )
            connection.execute(
                "INSERT INTO qf_tenants(tenant_id,account_id,database_locator,schema_version,created_at,status) VALUES(?,?,?,?,?,'active')",
                (tenant, account, str(database_path), MOBILE_SCHEMA_VERSION, now),
            )
        return self.get_tenant(tenant) or {}

    def get_tenant(self, tenant_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM qf_tenants WHERE tenant_id=?", (str(tenant_id),)).fetchone()
        return dict(row) if row else None

    def list_tenants(self, account_id: str = "") -> list[dict[str, Any]]:
        with self.connect() as connection:
            if account_id:
                rows = connection.execute("SELECT * FROM qf_tenants WHERE account_id=? ORDER BY created_at", (str(account_id),)).fetchall()
            else:
                rows = connection.execute("SELECT * FROM qf_tenants ORDER BY created_at").fetchall()
        return [dict(row) for row in rows]


class MobileFoundationService:
    def __init__(
        self,
        database: Any,
        study: Any,
        *,
        control_plane_path: str | Path | None = None,
        cloud_bridge_provider: Any | None = None,
        pairing_completed_callback: Any | None = None,
        projection_scheduler: Any | None = None,
    ):
        self.database = database
        self.study = study
        self.cloud_bridge_provider = cloud_bridge_provider
        self.pairing_completed_callback = pairing_completed_callback
        self.projection_scheduler = projection_scheduler
        self._projection_drain_lock = threading.Lock()
        data_dir = Path(getattr(database, "path", Path("data/questflow_questions.sqlite"))).resolve().parent
        self.control_plane = TenantControlPlane(
            control_plane_path or (data_dir / "mobile_control_plane.sqlite"),
            data_dir / "tenants",
        )
        self.ensure_schema()
        self.study_batch = StudyBatchService(database, study)
        self.adaptive_sessions = AdaptiveSessionOrchestrator(database, self.study_batch)
        identity = self.identity()
        self.control_plane.register_existing(
            account_id=identity["account_id"],
            tenant_id=identity["tenant_id"],
            database_locator=str(Path(getattr(database, "path", "")).resolve()),
        )

    # ------------------------------- schema ----------------------------
    def ensure_schema(self) -> None:
        with self.database.connect() as connection:
            def migration(conn: sqlite3.Connection) -> None:
                conn.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS qf_mobile_identity (
                        singleton_id INTEGER PRIMARY KEY CHECK(singleton_id=1),
                        account_id TEXT NOT NULL UNIQUE,
                        tenant_id TEXT NOT NULL UNIQUE,
                        learner_id TEXT NOT NULL UNIQUE,
                        display_name TEXT,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS qf_mobile_devices (
                        device_id TEXT PRIMARY KEY,
                        platform TEXT NOT NULL,
                        name TEXT,
                        app_version TEXT,
                        push_token TEXT,
                        push_provider TEXT,
                        status TEXT NOT NULL DEFAULT 'active',
                        paired_at TEXT NOT NULL,
                        last_seen_at TEXT NOT NULL,
                        revoked_at TEXT
                    );
                    CREATE INDEX IF NOT EXISTS idx_qf_mobile_devices_status
                        ON qf_mobile_devices(status,last_seen_at DESC);

                    CREATE TABLE IF NOT EXISTS qf_mobile_pairings (
                        token_hash TEXT PRIMARY KEY,
                        created_at TEXT NOT NULL,
                        expires_at TEXT NOT NULL,
                        used_at TEXT,
                        requested_by TEXT NOT NULL DEFAULT 'desktop'
                    );
                    CREATE INDEX IF NOT EXISTS idx_qf_mobile_pairings_expiry
                        ON qf_mobile_pairings(expires_at,used_at);

                    CREATE TABLE IF NOT EXISTS qf_mobile_sessions (
                        token_hash TEXT PRIMARY KEY,
                        device_id TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        expires_at TEXT NOT NULL,
                        last_seen_at TEXT NOT NULL,
                        revoked_at TEXT,
                        FOREIGN KEY(device_id) REFERENCES qf_mobile_devices(device_id) ON DELETE CASCADE
                    );
                    CREATE INDEX IF NOT EXISTS idx_qf_mobile_sessions_device
                        ON qf_mobile_sessions(device_id,expires_at);

                    CREATE TABLE IF NOT EXISTS qf_mobile_question_revisions (
                        question_uid TEXT PRIMARY KEY,
                        revision INTEGER NOT NULL DEFAULT 1,
                        content_hash TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        FOREIGN KEY(question_uid) REFERENCES questions(uid) ON DELETE CASCADE
                    );
                    CREATE TABLE IF NOT EXISTS qf_mobile_question_snapshots (
                        question_uid TEXT NOT NULL,
                        revision INTEGER NOT NULL,
                        snapshot_json TEXT NOT NULL,
                        content_hash TEXT NOT NULL,
                        captured_at TEXT NOT NULL,
                        PRIMARY KEY(question_uid, revision),
                        FOREIGN KEY(question_uid) REFERENCES questions(uid) ON DELETE CASCADE
                    );

                    CREATE TABLE IF NOT EXISTS qf_learning_events (
                        seq INTEGER PRIMARY KEY AUTOINCREMENT,
                        event_id TEXT NOT NULL UNIQUE,
                        schema_version INTEGER NOT NULL,
                        event_type TEXT NOT NULL,
                        account_id TEXT NOT NULL,
                        tenant_id TEXT NOT NULL,
                        learner_id TEXT NOT NULL,
                        device_id TEXT NOT NULL,
                        session_id TEXT,
                        attempt_id TEXT,
                        exam_project_id TEXT,
                        question_uid TEXT,
                        question_revision INTEGER,
                        occurred_at TEXT NOT NULL,
                        sequence_no INTEGER,
                        client_platform TEXT,
                        client_version TEXT,
                        payload_json TEXT NOT NULL,
                        received_at TEXT NOT NULL,
                        processed_at TEXT,
                        process_status TEXT NOT NULL DEFAULT 'received',
                        process_error TEXT,
                        FOREIGN KEY(device_id) REFERENCES qf_mobile_devices(device_id) ON DELETE CASCADE
                    );
                    CREATE INDEX IF NOT EXISTS idx_qf_learning_events_device_seq
                        ON qf_learning_events(device_id,seq);
                    CREATE INDEX IF NOT EXISTS idx_qf_learning_events_question_time
                        ON qf_learning_events(question_uid,occurred_at);
                    CREATE INDEX IF NOT EXISTS idx_qf_learning_events_attempt
                        ON qf_learning_events(attempt_id,event_type);
                    CREATE INDEX IF NOT EXISTS idx_qf_learning_events_project
                        ON qf_learning_events(exam_project_id,seq);

                    CREATE TABLE IF NOT EXISTS qf_mobile_event_effects (
                        event_id TEXT PRIMARY KEY,
                        effect_type TEXT NOT NULL,
                        legacy_attempt_id TEXT,
                        detail_json TEXT NOT NULL DEFAULT '{}',
                        created_at TEXT NOT NULL,
                        FOREIGN KEY(event_id) REFERENCES qf_learning_events(event_id) ON DELETE CASCADE
                    );
                    """
                )

            apply_migration(
                connection,
                component="mobile_foundation",
                version=1,
                name="identity devices event log revision snapshots and auth",
                callback=migration,
            )

            def device_lifecycle_migration(conn: sqlite3.Connection) -> None:
                columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(qf_mobile_devices)").fetchall()}
                if "hidden_at" not in columns:
                    conn.execute("ALTER TABLE qf_mobile_devices ADD COLUMN hidden_at TEXT")

            apply_migration(
                connection,
                component="mobile_foundation",
                version=2,
                name="mobile device disconnect reconnect and list lifecycle",
                callback=device_lifecycle_migration,
            )

            def study_triage_migration(conn: sqlite3.Connection) -> None:
                conn.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS qf_mobile_study_backlog (
                        backlog_id TEXT PRIMARY KEY,
                        topic_key TEXT NOT NULL,
                        exam_project_id TEXT NOT NULL DEFAULT '',
                        subject TEXT NOT NULL DEFAULT '',
                        topic TEXT NOT NULL DEFAULT '',
                        lesson TEXT NOT NULL DEFAULT '',
                        source_question_uid TEXT,
                        status TEXT NOT NULL DEFAULT 'pending',
                        mark_count INTEGER NOT NULL DEFAULT 1,
                        first_marked_at TEXT NOT NULL,
                        last_marked_at TEXT NOT NULL,
                        reviewed_at TEXT,
                        FOREIGN KEY(source_question_uid) REFERENCES questions(uid) ON DELETE SET NULL,
                        UNIQUE(topic_key, exam_project_id)
                    );
                    CREATE INDEX IF NOT EXISTS idx_qf_mobile_study_backlog_status
                        ON qf_mobile_study_backlog(status,exam_project_id,last_marked_at DESC);
                    """
                )

            apply_migration(
                connection,
                component="mobile_foundation",
                version=3,
                name="pre-answer correction requests and not-studied topic backlog",
                callback=study_triage_migration,
            )

            row = connection.execute("SELECT account_id FROM qf_mobile_identity WHERE singleton_id=1").fetchone()
            if not row:
                now = utc_now()
                connection.execute(
                    """
                    INSERT INTO qf_mobile_identity(singleton_id,account_id,tenant_id,learner_id,display_name,created_at,updated_at)
                    VALUES(1,?,?,?,?,?,?)
                    """,
                    (str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4()), "", now, now),
                )

    # ------------------------------ identity/auth ----------------------
    def identity(self) -> dict[str, Any]:
        with self.database.connect() as connection:
            row = connection.execute("SELECT * FROM qf_mobile_identity WHERE singleton_id=1").fetchone()
        if not row:
            raise RuntimeError("Identidade mobile não inicializada.")
        return dict(row)

    def create_pairing(self, *, requested_by: str = "desktop") -> dict[str, Any]:
        token = secrets.token_urlsafe(32)
        now = utc_now_dt()
        expires = now + timedelta(minutes=PAIRING_TTL_MINUTES)
        with self.database.connect() as connection:
            connection.execute("DELETE FROM qf_mobile_pairings WHERE expires_at < ? OR used_at IS NOT NULL", (now.isoformat(),))
            connection.execute(
                "INSERT INTO qf_mobile_pairings(token_hash,created_at,expires_at,requested_by) VALUES(?,?,?,?)",
                (_sha256(token), now.isoformat(), expires.isoformat(), str(requested_by or "desktop")),
            )
        return {
            "pairing_token": token,
            "expires_at": expires.isoformat(),
            "expires_in_seconds": PAIRING_TTL_MINUTES * 60,
            "single_use": True,
            "warning": "O token de pareamento não contém credenciais do banco e expira após um único uso.",
        }

    def discovery_fingerprint(self) -> str:
        identity = self.identity()
        return _sha256(f"questflow-discovery:{identity.get('tenant_id','')}")[:24]

    def exchange_pairing(self, pairing_token: str, device: dict[str, Any] | None = None) -> dict[str, Any]:
        token_hash = _sha256(str(pairing_token or ""))
        now = utc_now_dt()
        device = dict(device or {})
        with self.database.connect() as connection:
            pairing = connection.execute("SELECT * FROM qf_mobile_pairings WHERE token_hash=?", (token_hash,)).fetchone()
            if not pairing:
                raise PermissionError("Token de pareamento inválido.")
            if pairing["used_at"]:
                raise PermissionError("Token de pareamento já utilizado.")
            expiry = parse_iso(pairing["expires_at"])
            if expiry is None or expiry < now:
                raise PermissionError("Token de pareamento expirado.")

            device_id = str(device.get("device_id") or uuid.uuid4()).strip()
            platform = str(device.get("platform") or "unknown").strip().lower()[:40]
            name = str(device.get("name") or "QuestFlow Mobile").strip()[:160]
            app_version = str(device.get("app_version") or "0.0.0").strip()[:40]
            connection.execute(
                """
                INSERT INTO qf_mobile_devices(device_id,platform,name,app_version,status,paired_at,last_seen_at)
                VALUES(?,?,?,?, 'active', ?, ?)
                ON CONFLICT(device_id) DO UPDATE SET
                    platform=excluded.platform,name=excluded.name,app_version=excluded.app_version,
                    status='active',last_seen_at=excluded.last_seen_at,revoked_at=NULL,hidden_at=NULL
                """,
                (device_id, platform, name, app_version, now.isoformat(), now.isoformat()),
            )
            connection.execute("UPDATE qf_mobile_pairings SET used_at=? WHERE token_hash=?", (now.isoformat(), token_hash))

            access_token = secrets.token_urlsafe(48)
            expires = now + timedelta(days=ACCESS_TOKEN_TTL_DAYS)
            connection.execute(
                "INSERT INTO qf_mobile_sessions(token_hash,device_id,created_at,expires_at,last_seen_at) VALUES(?,?,?,?,?)",
                (_sha256(access_token), device_id, now.isoformat(), expires.isoformat(), now.isoformat()),
            )

        identity = self.identity()
        cloud_bridge: dict[str, Any] = {}
        if callable(self.cloud_bridge_provider):
            try:
                candidate = self.cloud_bridge_provider()
                if isinstance(candidate, dict):
                    cloud_bridge = dict(candidate)
            except Exception:
                cloud_bridge = {}
        result = {
            "access_token": access_token,
            "token_type": "Bearer",
            "expires_at": expires.isoformat(),
            "device_id": device_id,
            "identity": {key: identity[key] for key in ("account_id", "tenant_id", "learner_id")},
            "api": MOBILE_CONTRACT,
            "server_fingerprint": self.discovery_fingerprint(),
            "cloud_bridge": cloud_bridge,
        }
        if callable(self.pairing_completed_callback):
            try:
                self.pairing_completed_callback()
            except Exception:
                # Pairing succeeds locally even if the optional cloud bridge is offline.
                pass
        return result

    def authenticate(self, access_token: str) -> dict[str, Any]:
        token = str(access_token or "").strip()
        if not token:
            raise PermissionError("Token mobile ausente.")
        now = utc_now_dt()
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT s.*, d.platform, d.name, d.app_version, d.status AS device_status
                FROM qf_mobile_sessions s JOIN qf_mobile_devices d ON d.device_id=s.device_id
                WHERE s.token_hash=?
                """,
                (_sha256(token),),
            ).fetchone()
            if not row or row["revoked_at"] or str(row["device_status"]) != "active":
                raise PermissionError("Sessão mobile inválida ou desconectada.")
            expiry = parse_iso(row["expires_at"])
            if expiry is None or expiry < now:
                raise PermissionError("Sessão mobile expirada.")
            connection.execute("UPDATE qf_mobile_sessions SET last_seen_at=? WHERE token_hash=?", (now.isoformat(), _sha256(token)))
            connection.execute("UPDATE qf_mobile_devices SET last_seen_at=? WHERE device_id=?", (now.isoformat(), row["device_id"]))
        identity = self.identity()
        return {**dict(row), **{key: identity[key] for key in ("account_id", "tenant_id", "learner_id")}}

    def auth_for_device(self, device_id: str, *, allow_disconnected: bool = False) -> dict[str, Any]:
        """Build trusted auth context for events already authenticated by Cloud Bridge.

        ``allow_disconnected`` is used only for the immutable Cloud queue: an event
        may have been authenticated by the Gateway while the session was active and
        arrive at the Studio after the user disconnected.  That historical event must
        still be preserved; new requests remain blocked by normal bearer auth.
        """
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT device_id,platform,name,app_version,status FROM qf_mobile_devices WHERE device_id=?",
                (str(device_id),),
            ).fetchone()
        if not row:
            raise PermissionError("Aparelho Cloud Bridge não pertence a este QuestFlow.")
        if not allow_disconnected and str(row["status"] or "") != "active":
            raise PermissionError("Aparelho Cloud Bridge não está ativo neste QuestFlow.")
        identity = self.identity()
        return {**dict(row), **{key: identity[key] for key in ("account_id", "tenant_id", "learner_id")}}

    def ingest_cloud_events(self, events: Iterable[dict[str, Any]]) -> dict[str, Any]:
        """Apply gateway events with the same immutable/idempotent pipeline as LAN events."""
        grouped: dict[str, list[dict[str, Any]]] = {}
        failed: list[dict[str, Any]] = []
        for event in events or []:
            if not isinstance(event, dict):
                failed.append({"event_id": "", "error": "Evento Cloud Bridge inválido."})
                continue
            device_id = str(event.get("device_id") or "").strip()
            if not device_id:
                failed.append({"event_id": str(event.get("event_id") or ""), "error": "device_id ausente."})
                continue
            grouped.setdefault(device_id, []).append(event)
        accepted: list[str] = []
        duplicates: list[str] = []
        effects: list[dict[str, Any]] = []
        for device_id, device_events in grouped.items():
            try:
                auth = self.auth_for_device(device_id, allow_disconnected=True)
                result = self.ingest_events(auth, device_events)
                accepted.extend(list(result.get("accepted") or []))
                duplicates.extend(list(result.get("duplicates") or []))
                effects.extend(list(result.get("effects") or []))
                failed.extend(list(result.get("failed") or []))
            except Exception as error:
                for event in device_events:
                    failed.append({"event_id": str(event.get("event_id") or ""), "error": str(error)})
        return {
            "ok": not bool(failed),
            "accepted": accepted,
            "duplicates": duplicates,
            "failed": failed,
            "effects": effects,
            "source": "mobile_cloud_bridge",
        }

    def disconnect_device(self, device_id: str) -> dict[str, Any]:
        """Encerra as sessões de um aparelho sem apagar seu histórico de estudo.

        O campo ``revoked_at`` é mantido no schema por compatibilidade com bancos
        anteriores, mas a linguagem de produto passa a ser apenas "desconectar".
        """
        now = utc_now()
        with self.database.connect() as connection:
            changed = connection.execute(
                "UPDATE qf_mobile_devices SET status='disconnected',revoked_at=? WHERE device_id=?",
                (now, str(device_id)),
            ).rowcount
            connection.execute(
                "UPDATE qf_mobile_sessions SET revoked_at=? WHERE device_id=? AND revoked_at IS NULL",
                (now, str(device_id)),
            )
        return {"ok": bool(changed), "device_id": str(device_id), "disconnected_at": now if changed else None}

    def revoke_device(self, device_id: str) -> dict[str, Any]:
        # Alias interno para preservar compatibilidade com integrações 6.9.4.
        return self.disconnect_device(device_id)

    def forget_device(self, device_id: str) -> dict[str, Any]:
        """Oculta da lista um aparelho já desconectado, preservando eventos/histórico."""
        now = utc_now()
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT status FROM qf_mobile_devices WHERE device_id=?",
                (str(device_id),),
            ).fetchone()
            if not row:
                return {"ok": False, "device_id": str(device_id), "error": "Aparelho não encontrado."}
            if str(row["status"] or "") == "active":
                raise ValueError("Desconecte o aparelho antes de removê-lo da lista.")
            changed = connection.execute(
                "UPDATE qf_mobile_devices SET hidden_at=? WHERE device_id=?",
                (now, str(device_id)),
            ).rowcount
        return {"ok": bool(changed), "device_id": str(device_id), "hidden_at": now if changed else None}

    def register_push_token(self, auth: dict[str, Any], *, push_token: str, provider: str = "fcm") -> dict[str, Any]:
        token = str(push_token or "").strip()
        if not token:
            raise ValueError("Push token vazio.")
        with self.database.connect() as connection:
            connection.execute(
                "UPDATE qf_mobile_devices SET push_token=?,push_provider=?,last_seen_at=? WHERE device_id=?",
                (token[:2048], str(provider or "fcm")[:40], utc_now(), str(auth["device_id"])),
            )
        return {"ok": True, "device_id": str(auth["device_id"]), "provider": str(provider or "fcm")}

    # --------------------------- question revisions --------------------
    @staticmethod
    def _question_hash(question: dict[str, Any]) -> str:
        stable = {
            "uid": question.get("database_uid") or question.get("uid"),
            "codigo": question.get("codigo") or question.get("codigo_origem") or question.get("source_code"),
            "enunciado": question.get("enunciado") or question.get("statement"),
            "alternativas": question.get("alternativas"),
            "gabarito": question.get("gabarito") or question.get("answer"),
            "materia": question.get("materia") or question.get("subject"),
            "assunto": question.get("assunto") or question.get("primary_topic"),
        }
        return hashlib.sha256(_json(stable).encode("utf-8")).hexdigest()

    def current_question_revision(self, question_uid: str, *, capture_snapshot: bool = True) -> tuple[int, dict[str, Any]]:
        question = self.database.get_question(str(question_uid))
        if not question:
            raise ValueError("Questão não encontrada.")
        digest = self._question_hash(question)
        now = utc_now()
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT revision,content_hash FROM qf_mobile_question_revisions WHERE question_uid=?",
                (str(question_uid),),
            ).fetchone()
            if not row:
                revision = 1
                connection.execute(
                    "INSERT INTO qf_mobile_question_revisions(question_uid,revision,content_hash,updated_at) VALUES(?,?,?,?)",
                    (str(question_uid), revision, digest, now),
                )
            elif str(row["content_hash"]) != digest:
                revision = int(row["revision"] or 1) + 1
                connection.execute(
                    "UPDATE qf_mobile_question_revisions SET revision=?,content_hash=?,updated_at=? WHERE question_uid=?",
                    (revision, digest, now, str(question_uid)),
                )
            else:
                revision = int(row["revision"] or 1)
            if capture_snapshot:
                connection.execute(
                    """
                    INSERT OR IGNORE INTO qf_mobile_question_snapshots(question_uid,revision,snapshot_json,content_hash,captured_at)
                    VALUES(?,?,?,?,?)
                    """,
                    (str(question_uid), revision, _json(question), digest, now),
                )
        return revision, question

    def question_snapshot(self, question_uid: str, revision: int) -> dict[str, Any] | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT snapshot_json FROM qf_mobile_question_snapshots WHERE question_uid=? AND revision=?",
                (str(question_uid), int(revision)),
            ).fetchone()
        if not row:
            return None
        try:
            return json.loads(str(row[0]))
        except Exception:
            return None

    @staticmethod
    def _answer_index(question: dict[str, Any]) -> int | None:
        alternatives = question.get("alternativas") if isinstance(question.get("alternativas"), list) else []
        telegram = question.get("telegram") if isinstance(question.get("telegram"), dict) else {}
        index = telegram.get("indice_correto")
        if isinstance(index, int) and 0 <= index < len(alternatives):
            return index
        answer = str(question.get("gabarito") or question.get("answer") or "").strip().upper()
        keys = [str(item.get("chave", "")).strip().upper() for item in alternatives if isinstance(item, dict)]
        return keys.index(answer) if answer in keys else None

    @staticmethod
    def _public_question(question: dict[str, Any], revision: int) -> dict[str, Any]:
        alternatives = []
        for index, item in enumerate(question.get("alternativas") or []):
            if not isinstance(item, dict):
                continue
            alternatives.append(
                {
                    "index": index,
                    "key": str(item.get("chave") or ""),
                    "text": str(item.get("texto") or item.get("text") or ""),
                }
            )
        return {
            "question_id": str(question.get("database_uid") or question.get("uid") or ""),
            "question_revision": int(revision),
            "code": str(question.get("codigo") or question.get("codigo_origem") or question.get("source_code") or ""),
            "subject": str(question.get("materia") or question.get("subject") or ""),
            "topic": str(question.get("assunto") or question.get("primary_topic") or ""),
            "lesson": str(question.get("aula_planilha") or question.get("lesson") or ""),
            "statement": str(question.get("enunciado") or question.get("statement") or ""),
            "question_type": str(question.get("tipo") or question.get("tipo_questao") or question.get("question_type") or ""),
            "alternatives": alternatives,
            # Answer/commentary are deliberately withheld until submission.
            "has_explanation": bool(str(question.get("explicacao") or question.get("comentario") or "").strip()),
        }

    def question_for_mobile(self, question_uid: str) -> dict[str, Any]:
        revision, question = self.current_question_revision(question_uid, capture_snapshot=True)
        return self._public_question(question, revision)

    def _study_backlog_excluded_uids(self, exam_project_id: str = "") -> set[str]:
        project_id = str(exam_project_id or "").strip()
        try:
            with self.database.connect() as connection:
                rows = connection.execute(
                    """
                    SELECT DISTINCT q.uid
                    FROM questions q
                    JOIN qf_mobile_study_backlog b
                      ON b.status='pending'
                     AND (COALESCE(b.exam_project_id,'')='' OR COALESCE(b.exam_project_id,'')=?)
                     AND LOWER(TRIM(COALESCE(b.subject,'')))=LOWER(TRIM(COALESCE(q.subject,'')))
                     AND LOWER(TRIM(COALESCE(b.topic,'')))=LOWER(TRIM(COALESCE(q.primary_topic,'')))
                     AND LOWER(TRIM(COALESCE(b.lesson,'')))=LOWER(TRIM(COALESCE(q.lesson,'')))
                    """,
                    (project_id,),
                ).fetchall()
            return {str(row["uid"]) for row in rows}
        except sqlite3.Error:
            return set()

    def _previous_mobile_block_uids(self, learner_id: str, exam_project_id: str = "") -> set[str]:
        """Retorna as questões respondidas no bloco Mobile anterior do aluno."""
        learner = str(learner_id or "").strip()
        if not learner:
            return set()
        project = str(exam_project_id or "").strip()
        try:
            with self.database.connect() as connection:
                session = connection.execute(
                    """
                    SELECT session_id,MAX(answered_at) AS last_answered
                    FROM telegram_attempts
                    WHERE learner_id=? AND COALESCE(session_id,'')<>''
                      AND source LIKE 'mobile_%'
                      AND (?='' OR COALESCE(exam_project_id,'')=?)
                    GROUP BY session_id
                    ORDER BY last_answered DESC
                    LIMIT 1
                    """,
                    (learner, project, project),
                ).fetchone()
                if not session:
                    return set()
                rows = connection.execute(
                    """
                    SELECT DISTINCT question_uid FROM telegram_attempts
                    WHERE learner_id=? AND session_id=? AND COALESCE(question_uid,'')<>''
                    """,
                    (learner, str(session["session_id"] or "")),
                ).fetchall()
            return {str(row["question_uid"] or "") for row in rows if str(row["question_uid"] or "")}
        except sqlite3.Error:
            return set()

    def _session_start_exclusions(self, learner_id: str, project_id: str, mode: str) -> set[str]:
        exclusions = self._study_backlog_excluded_uids(project_id)
        # Revisão e erros são escolhas explícitas do aluno. Nos demais modos,
        # uma sessão nova gira o conteúdo mesmo que um passo curto do FSRS já
        # tenha vencido desde o bloco imediatamente anterior.
        if str(mode or "recommended").strip().lower() in {"recommended", "subject"}:
            exclusions.update(self._previous_mobile_block_uids(learner_id, project_id))
        return exclusions

    def _mobile_public_from_selected(self, selected: dict[str, Any]) -> dict[str, Any] | None:
        uid = str(selected.get("database_uid") or selected.get("uid") or "")
        if not uid:
            return None
        public = self.question_for_mobile(uid)
        state = selected.get("study_state") if isinstance(selected.get("study_state"), dict) else {}
        due_at = parse_iso(state.get("due_at"))
        bucket = int((selected.get("selection") or {}).get("bucket", selected.get("selection_bucket", 9)))
        public["study_flags"] = {
            "due": bool(due_at is not None and due_at <= utc_now_dt()),
            "review_eligible": bool((selected.get("selection") or {}).get("review_eligible", bucket in {0, 1, 2})),
            "wrong_count": int(state.get("wrong_count") or 0),
            "sent_count": int(state.get("sent_count") or 0),
        }
        public["selection"] = dict(selected.get("selection") or {})
        return public

    def _mobile_public_from_decision(self, question_uid: str, session_id: str, batch_id: str) -> dict[str, Any] | None:
        uid = str(question_uid or "")
        if not uid:
            return None
        public = self.question_for_mobile(uid)
        with self.database.connect() as connection:
            state = connection.execute(
                "SELECT sent_count,wrong_count,due_at,last_selection_bucket FROM study_state WHERE question_uid=?",
                (uid,),
            ).fetchone()
            decision_row = connection.execute(
                """SELECT decision_json,reason,strategy_profile,plan_revision,position
                   FROM qf_adaptive_question_decisions
                   WHERE session_id=? AND batch_id=? AND question_uid=?
                   ORDER BY id DESC LIMIT 1""",
                (str(session_id), str(batch_id), uid),
            ).fetchone()
        state_dict = dict(state) if state else {}
        due_at = parse_iso(state_dict.get("due_at"))
        selection: dict[str, Any] = {}
        if decision_row:
            try:
                decision = json.loads(str(decision_row["decision_json"] or "{}")) if decision_row["decision_json"] else {}
            except Exception:
                decision = {}
            selection = dict(decision.get("selection") or {}) if isinstance(decision, dict) and isinstance(decision.get("selection"), dict) else {}
            selection.update({
                "strategy_profile": str(decision_row["strategy_profile"] or selection.get("strategy_profile") or "balanced"),
                "plan_revision": int(decision_row["plan_revision"] or 0),
                "micro_batch_position": int(decision_row["position"] or 0),
            })
        try:
            bucket = int(selection.get("bucket", state_dict.get("last_selection_bucket") or 9))
        except Exception:
            bucket = 9
        public["study_flags"] = {
            "due": bool(due_at is not None and due_at <= utc_now_dt()),
            "review_eligible": bool(selection.get("review_eligible", bucket in {0, 1, 2})),
            "wrong_count": int(state_dict.get("wrong_count") or 0),
            "sent_count": int(state_dict.get("sent_count") or 0),
        }
        public["selection"] = selection
        return public

    def _publicize_adaptive_batch(self, session_id: str, batch: dict[str, Any]) -> dict[str, Any]:
        batch = dict(batch or {})
        public_questions: list[dict[str, Any]] = []
        selected_questions = list(batch.get("questions") or [])
        if selected_questions:
            for selected in selected_questions:
                if not isinstance(selected, dict):
                    continue
                public = self._mobile_public_from_selected(selected)
                if public is not None:
                    public_questions.append(public)
        else:
            for uid in list(batch.get("question_ids") or []):
                public = self._mobile_public_from_decision(str(uid), session_id, str(batch.get("batch_id") or ""))
                if public is not None:
                    public_questions.append(public)
        batch["questions"] = public_questions
        batch.pop("question_ids", None)
        return batch

    def start_adaptive_study_session(
        self,
        auth: dict[str, Any],
        *,
        session_id: str,
        count: int,
        exam_project_id: str = "",
        mode: str = "recommended",
        subject: str = "",
        micro_batch_size: int = DEFAULT_MICRO_BATCH_SIZE,
    ) -> dict[str, Any]:
        project_id = str(exam_project_id or "").strip()
        result = self.adaptive_sessions.start_session(
            session_id=str(session_id or ""),
            learner_id=str(auth.get("learner_id") or ""),
            device_id=str(auth.get("device_id") or ""),
            project_id=project_id,
            mode=str(mode or "recommended"),
            subject=str(subject or ""),
            target_questions=max(1, min(50, int(count or 10))),
            micro_batch_size=micro_batch_size,
            excluded_uids=self._session_start_exclusions(
                str(auth.get("learner_id") or ""), project_id, str(mode or "recommended")
            ),
        )
        result = dict(result)
        result["micro_batch"] = self._publicize_adaptive_batch(str(result.get("session_id") or session_id), dict(result.get("micro_batch") or {}))
        return result

    def next_adaptive_micro_batch(
        self,
        auth: dict[str, Any],
        session_id: str,
        *,
        purpose: str = "active",
        prefetched_batch_id: str = "",
        force_replan: bool = False,
        excluded_uids: Iterable[str] = (),
    ) -> dict[str, Any]:
        # Session ids are opaque, but learner ownership remains mandatory.
        row = self.adaptive_sessions._session(session_id)
        if str(row.get("learner_id") or "") and str(row.get("learner_id") or "") != str(auth.get("learner_id") or ""):
            raise PermissionError("Sessão adaptativa pertence a outro aluno.")
        batch = self.adaptive_sessions.next_micro_batch(
            session_id,
            purpose=purpose,
            prefetched_batch_id=str(prefetched_batch_id or ""),
            force_replan=bool(force_replan),
            excluded_uids=excluded_uids,
        )
        public = self._publicize_adaptive_batch(session_id, batch)
        status = self.adaptive_sessions.session_status(session_id)
        return {
            "contract": "questflow.mobile.adaptive_session.v1",
            "session_id": session_id,
            "goal": public.get("goal") or status.get("goal") or {},
            "micro_batch": public,
        }

    def question_batch(
        self,
        *,
        count: int = 8,
        exam_project_id: str = "",
        mode: str = "recommended",
        subject: str = "",
        learner_id: str = "",
        device_id: str = "",
    ) -> dict[str, Any]:
        """Monta um lote consumindo a inteligência adaptativa central do QuestFlow.

        O Mobile não mantém ranking pedagógico próprio. ``StudyBatchService`` usa
        ``StudyRepository.select_questions`` e aplica somente a política de composição
        da sessão (mix, interleaving e cooldown de exposição recente).
        """
        count = max(1, min(50, int(count or 8)))
        project_id = str(exam_project_id or "").strip()
        mode_key = str(mode or "recommended").strip().lower()
        if mode_key not in {"recommended", "review", "errors", "subject"}:
            mode_key = "recommended"
        subject_filter = str(subject or "").strip()
        if mode_key == "subject" and not subject_filter:
            raise ValueError("Uma matéria deve ser informada para a sessão por matéria.")

        exclusions = self._session_start_exclusions(str(learner_id or ""), project_id, mode_key)
        result = self.study_batch.select_batch(
            count=count,
            mode=mode_key,
            subject=subject_filter,
            project_id=project_id,
            learner_id=str(learner_id or ""),
            excluded_uids=exclusions,
        )
        items: list[dict[str, Any]] = []
        for selected in list(result.get("questions") or []):
            if not isinstance(selected, dict):
                continue
            public = self._mobile_public_from_selected(selected)
            if public is not None:
                items.append(public)

        return {
            "contract": MOBILE_CONTRACT,
            "exam_project_id": project_id,
            "batch_id": str(uuid.uuid4()),
            "generated_at": utc_now(),
            "mode": mode_key,
            "subject": subject_filter,
            "selection_policy": str(result.get("policy") or ""),
            "core_policy": str(result.get("core_policy") or ""),
            "session_start_excluded": len(exclusions),
            "questions": items,
        }

    def _active_exam_project_id(self, preferred: str = "") -> str:
        project_id = str(preferred or "").strip()
        if project_id:
            return project_id
        try:
            with self.database.connect() as connection:
                row = connection.execute("SELECT id FROM qf_exam_projects WHERE active=1 LIMIT 1").fetchone()
            return str(row["id"] if row else "")
        except sqlite3.OperationalError:
            return ""

    def _offline_pack_eligible_questions(self, questions: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Keep only never-answered items or reviews explicitly due by Studio.

        The Mobile reserve must never become an implicit early-review engine.  A
        question that already has an answer may return to the offline reserve only
        after the Studio scheduler says its spacing interval is due.
        """
        unique_ids: list[str] = []
        seen: set[str] = set()
        for item in questions:
            uid = str(item.get("question_id") or "").strip() if isinstance(item, dict) else ""
            if uid and uid not in seen:
                seen.add(uid)
                unique_ids.append(uid)
        if not unique_ids:
            return []
        placeholders = ",".join("?" for _ in unique_ids)
        with self.database.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT s.question_uid, s.due_at, s.fsrs_due_at, s.fsrs_state,
                       s.correct_count, s.wrong_count,
                       (SELECT COUNT(*) FROM telegram_attempts a WHERE a.question_uid=s.question_uid) AS answered_attempts
                FROM study_state s
                WHERE s.question_uid IN ({placeholders})
                """,
                unique_ids,
            ).fetchall()
        state_by_uid = {str(row["question_uid"]): dict(row) for row in rows}
        now = utc_now_dt()
        output: list[dict[str, Any]] = []
        for item in questions:
            if not isinstance(item, dict):
                continue
            uid = str(item.get("question_id") or "").strip()
            if not uid or uid not in state_by_uid:
                continue
            state = state_by_uid[uid]
            answered_attempts = int(state.get("answered_attempts") or 0)
            # Treat any learner evidence as an answer, even when legacy/imported
            # progress exists without a corresponding telegram_attempts row.
            state_answered_count = int(state.get("correct_count") or 0) + int(state.get("wrong_count") or 0)
            answered_evidence = max(answered_attempts, state_answered_count)
            due_text = str(state.get("fsrs_due_at") or state.get("due_at") or "").strip()
            due_dt = parse_iso(due_text) if due_text else None
            if answered_evidence <= 0:
                eligibility = "never_answered"
            elif due_dt is not None and due_dt <= now:
                eligibility = "studio_spacing_due"
            else:
                # Answered items whose FSRS/fallback spacing has not expired are
                # deliberately excluded even if another composition rule would
                # otherwise allow an early/manual review.
                continue
            public = dict(item)
            public["offline_eligibility"] = {
                "policy": "never_answered_or_studio_due_v1",
                "kind": eligibility,
                "answered_before": answered_evidence > 0,
                "due_at": due_text if eligibility == "studio_spacing_due" else "",
                "fsrs_state": str(state.get("fsrs_state") or "new"),
            }
            output.append(public)
        return output

    def offline_study_pack(
        self,
        auth: dict[str, Any],
        *,
        exam_project_id: str = "",
        count: int = 30,
    ) -> dict[str, Any]:
        """Create the Mobile offline reserve from the same central study policy.

        This is intentionally a snapshot, not a second adaptive engine. The Studio
        decides the ordered reserve using StudyBatchService/StudyRepository after
        applying the latest synced learner events. While disconnected the Mobile
        only consumes this previously decided sequence and queues new evidence.
        """
        size = max(5, min(50, int(count or 30)))
        project_id = self._active_exam_project_id(exam_project_id)
        # Ask for a larger central candidate window so filtering out answered-but-
        # not-due items does not unnecessarily shrink the normal 30-question pack.
        candidate_count = min(50, max(size, size * 2))
        batch = self.question_batch(
            count=candidate_count,
            exam_project_id=project_id,
            mode="recommended",
            subject="",
            learner_id=str(auth.get("learner_id") or ""),
            device_id=str(auth.get("device_id") or ""),
        )
        eligible = self._offline_pack_eligible_questions(list(batch.get("questions") or []))[:size]
        return {
            "contract": "questflow.mobile.offline_study_pack.v1",
            "pack_id": str(uuid.uuid4()),
            "generated_at": utc_now(),
            "exam_project_id": project_id,
            "requested_count": size,
            "eligible_count": len(eligible),
            "eligibility_policy": "never_answered_or_studio_due_v1",
            "selection_policy": str(batch.get("selection_policy") or ""),
            "core_policy": str(batch.get("core_policy") or ""),
            "source": "studio_learning_engine",
            "adaptive_while_offline": False,
            "questions": eligible,
        }

    # ------------------------------ events -----------------------------
    def _normalize_event(self, event: dict[str, Any], auth: dict[str, Any]) -> dict[str, Any]:
        event_id = str(event.get("event_id") or "").strip()
        if not event_id:
            raise ValueError("event_id é obrigatório.")
        event_type = str(event.get("event_type") or "").strip().lower()
        if event_type not in LEARNING_EVENT_TYPES:
            raise ValueError(f"event_type não suportado: {event_type}")
        supplied_device = str(event.get("device_id") or auth["device_id"]).strip()
        if supplied_device != str(auth["device_id"]):
            raise PermissionError("Evento pertence a outro dispositivo.")
        occurred = parse_iso(event.get("occurred_at")) or utc_now_dt()
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        client = event.get("client") if isinstance(event.get("client"), dict) else {}
        revision = _int_or_none(event.get("question_revision"))
        return {
            "event_id": event_id,
            "schema_version": max(1, int(event.get("schema_version") or 1)),
            "event_type": event_type,
            "account_id": str(auth["account_id"]),
            "tenant_id": str(auth["tenant_id"]),
            "learner_id": str(auth["learner_id"]),
            "device_id": supplied_device,
            "session_id": str(event.get("session_id") or "") or None,
            "attempt_id": str(event.get("attempt_id") or "") or None,
            "exam_project_id": str(event.get("exam_project_id") or "") or None,
            "question_uid": str(event.get("question_id") or event.get("question_uid") or "") or None,
            "question_revision": revision,
            "occurred_at": occurred.isoformat(),
            "sequence_no": _int_or_none(event.get("sequence_no")),
            "client_platform": str(client.get("platform") or auth.get("platform") or "")[:40],
            "client_version": str(client.get("version") or auth.get("app_version") or "")[:40],
            "payload": payload,
        }

    @staticmethod
    def _normalize_confidence(value: Any) -> str:
        key = str(value or "").strip().casefold()
        return {
            "low": "duvida", "baixa": "duvida", "duvida": "duvida", "dúvida": "duvida",
            "medium": "duvida", "media": "duvida", "média": "duvida",
            "high": "sabia", "alta": "sabia", "sabia": "sabia", "seguro": "sabia",
            "guess": "chutei", "chute": "chutei", "chutei": "chutei",
        }.get(key, key)

    @staticmethod
    def _normalize_difficulty(value: Any) -> str:
        key = str(value or "").strip().casefold()
        return {
            "easy": "facil", "fácil": "facil", "facil": "facil",
            "medium": "media", "média": "media", "medio": "media", "médio": "media", "media": "media",
            "hard": "dificil", "difícil": "dificil", "dificil": "dificil",
        }.get(key, key)

    def _attempt_meta_from_events(self, attempt_id: str, base: dict[str, Any] | None = None) -> dict[str, Any]:
        merged = dict(base or {})
        if not attempt_id:
            return merged
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT event_type,payload_json FROM qf_learning_events
                WHERE attempt_id=? AND event_type IN ('confidence_reported','difficulty_reported','learning_gap_reported')
                ORDER BY seq ASC
                """,
                (str(attempt_id),),
            ).fetchall()
        for row in rows:
            try:
                payload = json.loads(str(row["payload_json"] or "{}"))
            except Exception:
                payload = {}
            if row["event_type"] == "confidence_reported":
                merged["confidence"] = payload.get("confidence") or payload.get("level") or payload.get("value")
            elif row["event_type"] == "difficulty_reported":
                merged["perceived_difficulty"] = payload.get("perceived_difficulty") or payload.get("difficulty") or payload.get("value")
            elif row["event_type"] == "learning_gap_reported":
                merged["learning_gap"] = bool(payload.get("learning_gap", payload.get("value", True)))
        return merged

    def ingest_events(
        self,
        auth: dict[str, Any],
        events: Iterable[dict[str, Any]],
        *,
        defer_answer_projections: bool = False,
    ) -> dict[str, Any]:
        accepted: list[str] = []
        duplicates: list[str] = []
        failed: list[dict[str, str]] = []
        effects: list[dict[str, Any]] = []
        normalized_events: list[dict[str, Any]] = []
        for raw in list(events):
            if not isinstance(raw, dict):
                failed.append({"event_id": "", "error": "Evento inválido."})
                continue
            try:
                normalized_events.append(self._normalize_event(raw, auth))
            except Exception as error:
                failed.append({"event_id": str(raw.get("event_id") or ""), "error": str(error)})

        for event in normalized_events:
            event_id = event["event_id"]
            try:
                with self.database.connect() as connection:
                    existing = connection.execute(
                        """
                        SELECT process_status,event_type,device_id,session_id,attempt_id,exam_project_id,
                               question_uid,question_revision,occurred_at,sequence_no,client_platform,
                               client_version,payload_json
                        FROM qf_learning_events WHERE event_id=?
                        """,
                        (event_id,),
                    ).fetchone()
                    if existing and str(existing["process_status"] or "") not in {"error", "received"}:
                        duplicates.append(event_id)
                        continue
                    if existing:
                        # A previous delivery was persisted but its effect failed.
                        # The event remains immutable: a retry may reprocess only
                        # exactly the content stored under this event_id.
                        persisted_payload = {}
                        try:
                            persisted_payload = json.loads(str(existing["payload_json"] or "{}"))
                        except Exception:
                            persisted_payload = {}
                        immutable_fields = (
                            ("event_type", event["event_type"]),
                            ("device_id", event["device_id"]),
                            ("session_id", event["session_id"]),
                            ("attempt_id", event["attempt_id"]),
                            ("exam_project_id", event["exam_project_id"]),
                            ("question_uid", event["question_uid"]),
                            ("question_revision", event["question_revision"]),
                            ("occurred_at", event["occurred_at"]),
                            ("sequence_no", event["sequence_no"]),
                            ("client_platform", event["client_platform"]),
                            ("client_version", event["client_version"]),
                        )
                        if any(existing[name] != value for name, value in immutable_fields) or persisted_payload != event["payload"]:
                            raise ValueError("event_id já existe com conteúdo diferente; eventos de aprendizagem são imutáveis.")
                        connection.execute(
                            "UPDATE qf_learning_events SET process_status='received',process_error=NULL,received_at=? WHERE event_id=?",
                            (utc_now(), event_id),
                        )
                    else:
                        connection.execute(
                            """
                            INSERT INTO qf_learning_events(
                                event_id,schema_version,event_type,account_id,tenant_id,learner_id,device_id,
                                session_id,attempt_id,exam_project_id,question_uid,question_revision,occurred_at,
                                sequence_no,client_platform,client_version,payload_json,received_at,process_status
                            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'received')
                            """,
                            (
                                event_id,event["schema_version"],event["event_type"],event["account_id"],event["tenant_id"],event["learner_id"],event["device_id"],
                                event["session_id"],event["attempt_id"],event["exam_project_id"],event["question_uid"],event["question_revision"],event["occurred_at"],
                                event["sequence_no"],event["client_platform"],event["client_version"],_json(event["payload"]),utc_now(),
                            ),
                        )
                if event["event_type"] == "answer_submitted":
                    effect = self._apply_answer_effect(event, defer_projection=defer_answer_projections)
                    if effect:
                        effects.append(effect)
                elif event["event_type"] in {"confidence_reported", "difficulty_reported", "learning_gap_reported"}:
                    effect = self._apply_meta_effect(event)
                    if effect:
                        effects.append(effect)
                elif event["event_type"] in {"question_correction_requested", "topic_not_studied_reported", "topic_study_completed"}:
                    effect = self._apply_preanswer_effect(event)
                    if effect:
                        effects.append(effect)
                else:
                    with self.database.connect() as connection:
                        connection.execute(
                            "UPDATE qf_learning_events SET process_status='stored',processed_at=? WHERE event_id=?",
                            (utc_now(), event_id),
                        )
                accepted.append(event_id)
                if event["event_type"] == "session_ended" and str(event.get("session_id") or ""):
                    try:
                        self.adaptive_sessions.finish_session(str(event["session_id"]))
                    except ValueError:
                        # Sessões legadas/offline podem não ter registro no orquestrador.
                        pass
            except Exception as error:
                with self.database.connect() as connection:
                    connection.execute(
                        "UPDATE qf_learning_events SET process_status='error',process_error=?,processed_at=? WHERE event_id=?",
                        (str(error)[:1000], utc_now(), event_id),
                    )
                failed.append({"event_id": event_id, "error": str(error)})

        return {
            "ok": not failed,
            "accepted": accepted,
            "duplicates": duplicates,
            "failed": failed,
            "effects": effects,
            "idempotent": True,
        }

    @staticmethod
    def _study_topic_key(subject: Any, topic: Any, lesson: Any) -> str:
        normalized = "|".join(str(value or "").strip().casefold() for value in (subject, topic, lesson))
        return hashlib.sha1(normalized.encode("utf-8")).hexdigest()

    def _apply_preanswer_effect(self, event: dict[str, Any]) -> dict[str, Any] | None:
        event_id = str(event["event_id"])
        with self.database.connect() as connection:
            if connection.execute("SELECT 1 FROM qf_mobile_event_effects WHERE event_id=?", (event_id,)).fetchone():
                return None

        kind = str(event["event_type"])
        payload = dict(event.get("payload") or {})
        question_uid = str(event.get("question_uid") or "").strip()
        detail: dict[str, Any] = {}
        effect_type = kind

        if kind == "question_correction_requested":
            if not question_uid:
                raise ValueError("Questão não informada para correção.")
            result = self.study.create_review_request(
                question_uid,
                user_id=f"mobile:{event.get('learner_id') or event.get('device_id') or ''}",
                username="QuestFlow Mobile",
                source="mobile_preanswer",
                note=str(payload.get("note") or "Solicitação feita antes de responder no aplicativo.")[:2000],
            )
            detail = {"review_request_id": str(result.get("id") or ""), "question_uid": question_uid}
            effect_type = "question_correction_queued"

        elif kind == "topic_not_studied_reported":
            if not question_uid:
                raise ValueError("Questão não informada para marcar o assunto.")
            with self.database.connect() as connection:
                question = connection.execute(
                    "SELECT uid,subject,primary_topic,lesson FROM questions WHERE uid=?",
                    (question_uid,),
                ).fetchone()
                if not question:
                    raise ValueError("A questão indicada não existe mais na base.")
                subject = str(question["subject"] or "")
                topic = str(question["primary_topic"] or "")
                lesson = str(question["lesson"] or "")
                topic_key = self._study_topic_key(subject, topic, lesson)
                project_id = str(event.get("exam_project_id") or "")
                now = utc_now()
                existing = connection.execute(
                    "SELECT backlog_id,mark_count FROM qf_mobile_study_backlog WHERE topic_key=? AND exam_project_id=?",
                    (topic_key, project_id),
                ).fetchone()
                if existing:
                    backlog_id = str(existing["backlog_id"])
                    connection.execute(
                        """
                        UPDATE qf_mobile_study_backlog
                        SET subject=?,topic=?,lesson=?,source_question_uid=?,status='pending',
                            mark_count=?,last_marked_at=?,reviewed_at=NULL
                        WHERE backlog_id=?
                        """,
                        (subject, topic, lesson, question_uid, int(existing["mark_count"] or 0) + 1, now, backlog_id),
                    )
                else:
                    backlog_id = str(uuid.uuid4())
                    connection.execute(
                        """
                        INSERT INTO qf_mobile_study_backlog(
                            backlog_id,topic_key,exam_project_id,subject,topic,lesson,source_question_uid,
                            status,mark_count,first_marked_at,last_marked_at
                        ) VALUES(?,?,?,?,?,?,?,'pending',1,?,?)
                        """,
                        (backlog_id, topic_key, project_id, subject, topic, lesson, question_uid, now, now),
                    )
            detail = {
                "backlog_id": backlog_id, "topic_key": topic_key, "subject": subject,
                "topic": topic, "lesson": lesson, "question_uid": question_uid,
            }
            effect_type = "topic_added_to_study_backlog"

        elif kind == "topic_study_completed":
            backlog_id = str(payload.get("backlog_id") or "").strip()
            topic_key = str(payload.get("topic_key") or "").strip()
            if not backlog_id and not topic_key:
                raise ValueError("Item de estudo não informado.")
            project_id = str(event.get("exam_project_id") or "")
            now = utc_now()
            with self.database.connect() as connection:
                if backlog_id:
                    row = connection.execute(
                        "SELECT backlog_id,topic_key FROM qf_mobile_study_backlog WHERE backlog_id=? AND (?='' OR exam_project_id=?)",
                        (backlog_id, project_id, project_id),
                    ).fetchone()
                else:
                    row = connection.execute(
                        "SELECT backlog_id,topic_key FROM qf_mobile_study_backlog WHERE topic_key=? AND (?='' OR exam_project_id=?)",
                        (topic_key, project_id, project_id),
                    ).fetchone()
                if not row:
                    raise ValueError("Assunto não encontrado na lista de estudo.")
                backlog_id = str(row["backlog_id"])
                topic_key = str(row["topic_key"])
                connection.execute(
                    "UPDATE qf_mobile_study_backlog SET status='reviewed',reviewed_at=? WHERE backlog_id=?",
                    (now, backlog_id),
                )
            detail = {"backlog_id": backlog_id, "topic_key": topic_key}
            effect_type = "topic_released_after_study"

        with self.database.connect() as connection:
            connection.execute(
                "INSERT INTO qf_mobile_event_effects(event_id,effect_type,legacy_attempt_id,detail_json,created_at) VALUES(?,?,?,?,?)",
                (event_id, effect_type, None, _json(detail), utc_now()),
            )
            connection.execute(
                "UPDATE qf_learning_events SET process_status='applied',processed_at=? WHERE event_id=?",
                (utc_now(), event_id),
            )
        return {"event_id": event_id, "effect": effect_type, **detail}

    def list_study_backlog_for_studio(self, *, status: str = "pending", limit: int = 2000) -> list[dict[str, Any]]:
        """Projection for Studio Correções. Keeps study triage separate from editorial correction state."""
        requested_status = str(status or "pending").strip().lower()
        clauses: list[str] = []
        values: list[Any] = []
        if requested_status in {"pending", "reviewed"}:
            clauses.append("b.status=?")
            values.append(requested_status)
        elif requested_status not in {"all", "todas", "todos"}:
            clauses.append("b.status='pending'")
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        values.append(max(1, min(int(limit), 5000)))
        with self.database.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT b.backlog_id,b.topic_key,b.exam_project_id,b.subject,b.topic,b.lesson,
                       b.source_question_uid,b.status,b.mark_count,b.first_marked_at,b.last_marked_at,b.reviewed_at,
                       q.source_code,q.statement,q.board,q.exam_year,q.agency,q.review_status
                FROM qf_mobile_study_backlog b
                LEFT JOIN questions q ON q.uid=b.source_question_uid
                {where}
                ORDER BY CASE b.status WHEN 'pending' THEN 0 ELSE 1 END, b.last_marked_at DESC
                LIMIT ?
                """,
                values,
            ).fetchall()
        return [
            {
                "id": f"not_studied:{row['backlog_id']}",
                "backlog_id": str(row["backlog_id"]),
                "item_type": "not_studied",
                "type_label": "Ainda não estudado",
                "source": "mobile_not_studied",
                "status": "aguardando_estudo" if str(row["status"]) == "pending" else "estudado",
                "created_at": str(row["first_marked_at"] or ""),
                "updated_at": str(row["last_marked_at"] or ""),
                "reviewed_at": str(row["reviewed_at"] or ""),
                "question_uid": str(row["source_question_uid"] or ""),
                "question_code": str(row["source_code"] or ""),
                "codigo": str(row["source_code"] or ""),
                "materia": str(row["subject"] or ""),
                "assunto": str(row["topic"] or ""),
                "aula": str(row["lesson"] or ""),
                "statement": str(row["statement"] or ""),
                "board": str(row["board"] or ""),
                "exam_year": row["exam_year"],
                "agency": str(row["agency"] or ""),
                "review_status": str(row["review_status"] or ""),
                "mark_count": int(row["mark_count"] or 1),
                "user_name": "QuestFlow Mobile",
                "note": "Assunto marcado no aplicativo como ainda não estudado. Não contabilizado como acerto ou erro.",
            }
            for row in rows
        ]

    def pending_study_backlog_count(self) -> int:
        with self.database.connect() as connection:
            row = connection.execute("SELECT COUNT(*) FROM qf_mobile_study_backlog WHERE status='pending'").fetchone()
        return int(row[0]) if row else 0

    def studio_study_backlog_action(self, backlog_id: str, action: str) -> dict[str, Any]:
        """Studio-side lifecycle for Mobile 'not studied yet' triage items."""
        item_id = str(backlog_id or "").strip()
        if not item_id:
            raise ValueError("Pendência de estudo não informada.")
        action_name = str(action or "").strip().lower()
        now = utc_now()
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT backlog_id,status FROM qf_mobile_study_backlog WHERE backlog_id=?",
                (item_id,),
            ).fetchone()
            if not row:
                raise ValueError("Pendência de estudo não encontrada.")
            if action_name in {"resolve", "reviewed", "mark_studied"}:
                connection.execute(
                    "UPDATE qf_mobile_study_backlog SET status='reviewed',reviewed_at=? WHERE backlog_id=?",
                    (now, item_id),
                )
                return {"ok": True, "status": "reviewed", "backlog_id": item_id}
            if action_name in {"delete", "remove"}:
                connection.execute("DELETE FROM qf_mobile_study_backlog WHERE backlog_id=?", (item_id,))
                return {"ok": True, "status": "deleted", "backlog_id": item_id}
            if action_name in {"reopen", "pending"}:
                connection.execute(
                    "UPDATE qf_mobile_study_backlog SET status='pending',reviewed_at=NULL,last_marked_at=? WHERE backlog_id=?",
                    (now, item_id),
                )
                return {"ok": True, "status": "pending", "backlog_id": item_id}
        raise ValueError("Ação de pendência de estudo desconhecida.")

    def _study_backlog_projection(self, exam_project_id: str = "") -> dict[str, Any]:
        project_id = str(exam_project_id or "").strip()
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT backlog_id,topic_key,exam_project_id,subject,topic,lesson,source_question_uid,
                       mark_count,first_marked_at,last_marked_at
                FROM qf_mobile_study_backlog
                WHERE status='pending' AND (?='' OR exam_project_id=? OR exam_project_id='')
                ORDER BY last_marked_at DESC
                LIMIT 30
                """,
                (project_id, project_id),
            ).fetchall()
        items = [
            {
                "backlog_id": str(row["backlog_id"]),
                "topic_key": str(row["topic_key"]),
                "exam_project_id": str(row["exam_project_id"] or ""),
                "subject": str(row["subject"] or "Sem matéria"),
                "topic": str(row["topic"] or "Sem assunto"),
                "lesson": str(row["lesson"] or ""),
                "source_question_id": str(row["source_question_uid"] or ""),
                "mark_count": int(row["mark_count"] or 1),
                "first_marked_at": str(row["first_marked_at"] or ""),
                "last_marked_at": str(row["last_marked_at"] or ""),
            }
            for row in rows
        ]
        return {"pending_count": len(items), "items": items}

    def _apply_meta_effect(self, event: dict[str, Any]) -> dict[str, Any] | None:
        event_id = str(event["event_id"])
        attempt_id = str(event.get("attempt_id") or "")
        if not attempt_id:
            with self.database.connect() as connection:
                connection.execute("UPDATE qf_learning_events SET process_status='stored',processed_at=? WHERE event_id=?", (utc_now(), event_id))
            return None
        with self.database.connect() as connection:
            if connection.execute("SELECT 1 FROM qf_mobile_event_effects WHERE event_id=?", (event_id,)).fetchone():
                return None
            attempt = connection.execute("SELECT id FROM telegram_attempts WHERE id=?", (attempt_id,)).fetchone()
        if not attempt:
            with self.database.connect() as connection:
                connection.execute("UPDATE qf_learning_events SET process_status='pending_attempt_meta',processed_at=? WHERE event_id=?", (utc_now(), event_id))
            return None
        payload = dict(event.get("payload") or {})
        kwargs: dict[str, Any] = {}
        if event["event_type"] == "confidence_reported":
            kwargs["confidence"] = self._normalize_confidence(payload.get("confidence") or payload.get("level") or payload.get("value"))
        elif event["event_type"] == "difficulty_reported":
            kwargs["perceived_difficulty"] = self._normalize_difficulty(payload.get("perceived_difficulty") or payload.get("difficulty") or payload.get("value"))
        elif event["event_type"] == "learning_gap_reported":
            kwargs["learning_gap"] = bool(payload.get("learning_gap", payload.get("value", True)))
        result = self.study.record_attempt_meta(attempt_id, **kwargs)
        with self.database.connect() as connection:
            connection.execute(
                "INSERT INTO qf_mobile_event_effects(event_id,effect_type,legacy_attempt_id,detail_json,created_at) VALUES(?,?,?,?,?)",
                (event_id, "attempt_meta_updated", attempt_id, _json(kwargs), utc_now()),
            )
            connection.execute("UPDATE qf_learning_events SET process_status='applied',processed_at=? WHERE event_id=?", (utc_now(), event_id))
        return {"event_id": event_id, "attempt_id": attempt_id, "effect": "attempt_meta_updated", "ok": bool(result.get("ok"))}

    def _apply_answer_effect(
        self,
        event: dict[str, Any],
        *,
        defer_projection: bool = False,
    ) -> dict[str, Any] | None:
        event_id = event["event_id"]
        with self.database.connect() as connection:
            effect = connection.execute("SELECT * FROM qf_mobile_event_effects WHERE event_id=?", (event_id,)).fetchone()
            if effect:
                return None

        uid = str(event.get("question_uid") or "")
        if not uid:
            raise ValueError("answer_submitted sem question_id.")
        revision = int(event.get("question_revision") or 0)
        if revision <= 0:
            revision, _ = self.current_question_revision(uid, capture_snapshot=True)
        snapshot = self.question_snapshot(uid, revision)
        if snapshot is None:
            current_revision, current = self.current_question_revision(uid, capture_snapshot=True)
            if current_revision != revision:
                raise ValueError("Revisão apresentada não está disponível no histórico; tentativa preservada sem reavaliar conteúdo incorreto.")
            snapshot = current
        correct_index = self._answer_index(snapshot)
        if correct_index is None:
            raise ValueError("A revisão da questão não possui gabarito utilizável.")

        attempt_id = str(event.get("attempt_id") or event_id)
        payload = self._attempt_meta_from_events(attempt_id, dict(event.get("payload") or {}))
        selected = payload.get("selected_indices")
        if not isinstance(selected, list):
            one = payload.get("selected_index")
            selected = [] if one is None else [one]
        if not selected:
            raise ValueError("answer_submitted sem alternativa selecionada.")
        selected_index = int(selected[0])
        snapshot_alternatives = snapshot.get("alternativas") if isinstance(snapshot.get("alternativas"), list) else []
        if selected_index < 0 or selected_index >= max(1, len(snapshot_alternatives)):
            raise ValueError("Alternativa selecionada não existe na revisão apresentada.")

        timing = assess_response_timing(
            active_seconds=payload.get("active_response_seconds"),
            wall_seconds=payload.get("wall_response_seconds"),
            idle_seconds=payload.get("idle_seconds"),
            source=str(payload.get("timing_source") or ""),
            abandoned=bool(payload.get("abandoned", False)),
            max_idle_gap_seconds=payload.get("max_idle_gap_seconds"),
            interaction_count=payload.get("interaction_count"),
        )
        outcome = self.study.record_local_practice_attempt(
            uid,
            selected_index,
            session_id=str(event.get("session_id") or "mobile"),
            confidence=self._normalize_confidence(payload.get("confidence")),
            response_seconds=timing.active_seconds if timing.eligible_for_speed_models else None,
            perceived_difficulty=self._normalize_difficulty(payload.get("perceived_difficulty")),
            learning_gap=payload.get("learning_gap") if "learning_gap" in payload else None,
            source=("mobile_" + str(event.get("client_platform") or "unknown").strip().lower()),
            attempt_id_override=attempt_id,
            correct_index_override=int(correct_index),
            timing_meta=timing.to_dict(),
            question_revision=revision,
            exam_project_id=str(event.get("exam_project_id") or ""),
            device_id=str(event.get("device_id") or ""),
            account_id=str(event.get("account_id") or ""),
            tenant_id=str(event.get("tenant_id") or ""),
            learner_id=str(event.get("learner_id") or ""),
            defer_projections=bool(defer_projection),
        )

        detail = {
            "timing": timing.to_dict(),
            "is_correct": bool(outcome.get("is_correct")),
            "correct_index": int(correct_index),
            "question_revision": revision,
            "projection_status": "pending" if defer_projection else "applied",
        }
        with self.database.connect() as connection:
            connection.execute(
                "INSERT INTO qf_mobile_event_effects(event_id,effect_type,legacy_attempt_id,detail_json,created_at) VALUES(?,?,?,?,?)",
                (event_id, "attempt_recorded", str(outcome.get("attempt_id") or attempt_id), _json(detail), utc_now()),
            )
            connection.execute(
                "UPDATE qf_learning_events SET process_status=?,processed_at=? WHERE event_id=?",
                ("projection_pending" if defer_projection else "applied", utc_now(), event_id),
            )
            # Meta events may have arrived before the answer.  Their information
            # was merged above; mark them applied now so sync diagnostics do not
            # leave false pending work.
            connection.execute(
                "UPDATE qf_learning_events SET process_status='applied',processed_at=? WHERE attempt_id=? AND process_status='pending_attempt_meta'",
                (utc_now(), attempt_id),
            )
        return {"event_id": event_id, "attempt_id": attempt_id, "effect": "attempt_recorded", **detail}

    def schedule_projection_drain(self) -> None:
        scheduler = self.projection_scheduler
        if callable(scheduler):
            scheduler()
            return
        timer = threading.Timer(0.01, self.process_pending_attempt_projections)
        timer.daemon = True
        timer.name = "questflow-mobile-projections"
        timer.start()

    def process_pending_attempt_projections(self, *, limit: int = 50) -> dict[str, Any]:
        """Retoma projeções pesadas sem bloquear o feedback do Mobile.

        A atualização dos modelos e o checkpoint ``applied`` compartilham uma
        transação SQLite. Se o processo cair, o evento permanece
        ``projection_pending`` e será retomado no próximo ciclo.
        """
        if not self._projection_drain_lock.acquire(blocking=False):
            return {"ok": True, "processed": 0, "failed": 0, "state": "already_running"}
        processed = 0
        failed = 0
        try:
            with self.database.connect() as connection:
                rows = connection.execute(
                    """
                    SELECT event_id,attempt_id,question_uid
                    FROM qf_learning_events
                    WHERE event_type='answer_submitted' AND process_status='projection_pending'
                    ORDER BY seq ASC LIMIT ?
                    """,
                    (max(1, min(500, int(limit or 50))),),
                ).fetchall()
            for row in rows:
                event_id = str(row["event_id"] or "")
                attempt_id = str(row["attempt_id"] or event_id)
                try:
                    with self.database.connect() as connection:
                        result = self.study.project_local_practice_attempt(
                            connection,
                            attempt_id,
                            question_uid=str(row["question_uid"] or ""),
                        )
                        effect = connection.execute(
                            "SELECT detail_json FROM qf_mobile_event_effects WHERE event_id=?",
                            (event_id,),
                        ).fetchone()
                        try:
                            detail = json.loads(str(effect["detail_json"] or "{}")) if effect else {}
                        except Exception:
                            detail = {}
                        detail["projection_status"] = "applied"
                        detail["projection_completed_at"] = utc_now()
                        connection.execute(
                            "UPDATE qf_mobile_event_effects SET detail_json=? WHERE event_id=?",
                            (_json(detail), event_id),
                        )
                        connection.execute(
                            "UPDATE qf_learning_events SET process_status='applied',process_error=NULL,processed_at=? WHERE event_id=?",
                            (utc_now(), event_id),
                        )
                    processed += 1
                except Exception as error:
                    failed += 1
                    with self.database.connect() as connection:
                        connection.execute(
                            "UPDATE qf_learning_events SET process_error=?,processed_at=? WHERE event_id=?",
                            (str(error)[:1000], utc_now(), event_id),
                        )
            return {"ok": failed == 0, "processed": processed, "failed": failed, "state": "completed"}
        finally:
            self._projection_drain_lock.release()

    def feedback_for_attempt(self, auth: dict[str, Any], attempt_id: str) -> dict[str, Any]:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT id,question_uid,selected_indices_json,is_correct,question_revision,timing_quality,
                       response_seconds,response_wall_seconds,response_idle_seconds,tenant_id,learner_id
                FROM telegram_attempts WHERE id=?
                """,
                (str(attempt_id),),
            ).fetchone()
        if not row:
            raise ValueError("Tentativa não encontrada.")
        if str(row["tenant_id"] or "") and str(row["tenant_id"]) != str(auth["tenant_id"]):
            raise PermissionError("Tentativa pertence a outro tenant.")
        if str(row["learner_id"] or "") and str(row["learner_id"]) != str(auth["learner_id"]):
            raise PermissionError("Tentativa pertence a outro usuário.")
        snapshot = self.question_snapshot(str(row["question_uid"]), int(row["question_revision"] or 1))
        if snapshot is None:
            snapshot = self.database.get_question(str(row["question_uid"])) or {}
        correct_index = self._answer_index(snapshot)
        alternatives = snapshot.get("alternativas") if isinstance(snapshot.get("alternativas"), list) else []
        answer_key = ""
        if correct_index is not None and 0 <= int(correct_index) < len(alternatives) and isinstance(alternatives[int(correct_index)], dict):
            answer_key = str(alternatives[int(correct_index)].get("chave") or "")
        try:
            selected = json.loads(str(row["selected_indices_json"] or "[]"))
        except Exception:
            selected = []
        return {
            "attempt_id": str(row["id"]),
            "question_id": str(row["question_uid"]),
            "question_revision": int(row["question_revision"] or 1),
            "selected_indices": selected,
            "is_correct": bool(row["is_correct"]),
            "correct_index": correct_index,
            "correct_key": answer_key,
            "explanation": str(snapshot.get("explicacao") or snapshot.get("comentario") or ""),
            "timing": {
                "active_response_seconds": row["response_seconds"],
                "wall_response_seconds": row["response_wall_seconds"],
                "idle_seconds": row["response_idle_seconds"],
                "quality": str(row["timing_quality"] or "missing"),
            },
        }

    def _recent_activity_projection(self) -> list[dict[str, Any]]:
        try:
            summary = self.study.activity_summary()
        except Exception:
            return []
        result: list[dict[str, Any]] = []
        for row in list(summary.get("recent_attempts") or [])[:8]:
            timing_quality = str(row.get("timing_quality") or "")
            response_seconds = row.get("response_seconds")
            result.append({
                "attempt_id": str(row.get("id") or ""),
                "question_id": str(row.get("question_uid") or ""),
                "code": str(row.get("codigo") or "Sem código"),
                "subject": str(row.get("materia") or "Matéria não informada"),
                "answered_at": str(row.get("answered_at") or ""),
                "is_correct": bool(row.get("is_correct")),
                "active_response_seconds": (
                    round(float(response_seconds), 1)
                    if response_seconds is not None and timing_quality in TIMING_ELIGIBLE_QUALITIES
                    else None
                ),
                "timing_quality": timing_quality or "missing",
            })
        return result

    def _recent_subject_insights(self, limit: int = 1200) -> dict[str, dict[str, Any]]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT COALESCE(NULLIF(TRIM(q.subject),''),'Sem matéria') AS subject,
                       COALESCE(NULLIF(TRIM(q.primary_topic),''),'Sem assunto') AS topic,
                       COALESCE(NULLIF(TRIM(q.lesson),''),'Sem aula') AS lesson,
                       a.is_correct,a.answered_at,a.perceived_difficulty,a.learning_gap
                FROM telegram_attempts a JOIN questions q ON q.uid=a.question_uid
                ORDER BY a.answered_at DESC LIMIT ?
                """,
                (max(50, int(limit)),),
            ).fetchall()
        grouped: dict[str, list[Any]] = {}
        for row in rows:
            grouped.setdefault(str(row["subject"]), []).append(row)
        insights: dict[str, dict[str, Any]] = {}
        for subject, items in grouped.items():
            recent = items[:10]
            previous = items[10:20]
            recent_accuracy = (sum(1 for row in recent if bool(row["is_correct"])) / len(recent)) if recent else None
            previous_accuracy = (sum(1 for row in previous if bool(row["is_correct"])) / len(previous)) if previous else None
            trend_delta = None if recent_accuracy is None or previous_accuracy is None else recent_accuracy - previous_accuracy
            difficulty = {"easy": 0, "medium": 0, "hard": 0, "known": 0}
            gaps_marked = 0
            gaps_known = 0
            for row in recent:
                value = str(row["perceived_difficulty"] or "").strip().lower()
                mapped = {"facil": "easy", "fácil": "easy", "easy": "easy", "media": "medium", "média": "medium", "medium": "medium", "dificil": "hard", "difícil": "hard", "hard": "hard"}.get(value)
                if mapped:
                    difficulty[mapped] += 1
                    difficulty["known"] += 1
                if row["learning_gap"] is not None:
                    gaps_known += 1
                    if bool(row["learning_gap"]):
                        gaps_marked += 1
            topic_stats: dict[str, list[int]] = {}
            for row in items[:40]:
                name = str(row["topic"] or "Sem assunto")
                bucket = topic_stats.setdefault(name, [0, 0])
                bucket[1] += 1
                bucket[0] += 1 if bool(row["is_correct"]) else 0
            weak_topics = [
                {"name": name, "accuracy": round(correct / total, 4), "attempts": total}
                for name, (correct, total) in topic_stats.items() if total
            ]
            weak_topics.sort(key=lambda item: (item["accuracy"], -item["attempts"], item["name"]))
            insights[subject] = {
                "recent_accuracy": None if recent_accuracy is None else round(recent_accuracy, 4),
                "trend_delta": None if trend_delta is None else round(trend_delta, 4),
                "recent_sample": len(recent),
                "last_answered_at": str(items[0]["answered_at"] or "") if items else "",
                "difficulty": difficulty,
                "learning_gap": {"marked": gaps_marked, "known": gaps_known},
                "weak_topics": weak_topics[:3],
            }
        return insights

    # --------------------------- projections ---------------------------
    @staticmethod
    def _mastery_level(value: float, confidence: float, attempts: int) -> tuple[str, str]:
        if attempts < 5 or confidence < 0.25:
            return "insufficient_evidence", "low"
        if value >= 0.85:
            level = "strong"
        elif value >= 0.68:
            level = "consolidating"
        elif value >= 0.50:
            level = "developing"
        else:
            level = "fragile"
        conf = "high" if confidence >= 0.75 and attempts >= 20 else "medium" if confidence >= 0.45 and attempts >= 8 else "low"
        return level, conf

    def priorities_projection(self, exam_project_id: str = "") -> list[dict[str, Any]]:
        now = utc_now()
        project_id = str(exam_project_id or "").strip()
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT COALESCE(NULLIF(TRIM(q.subject),''),'Sem matéria') AS subject,
                       COUNT(*) AS question_count,
                       SUM(s.correct_count) AS correct_count,
                       SUM(s.wrong_count) AS wrong_count,
                       SUM(CASE WHEN s.sent_count>0 AND s.due_at IS NOT NULL AND s.due_at<=? THEN 1 ELSE 0 END) AS due_count,
                       AVG(COALESCE(s.kt_mastery,0.5)) AS mastery,
                       AVG(COALESCE(s.kt_confidence,0.0)) AS mastery_confidence,
                       AVG(COALESCE(s.memory_retrievability,0.9)) AS retrievability,
                       AVG(COALESCE(s.learner_fusion_priority,s.adaptive_priority,0.0)) AS priority,
                       SUM(CASE WHEN EXISTS (SELECT 1 FROM telegram_attempts a WHERE a.question_uid=q.uid AND a.learning_gap=1) THEN 1 ELSE 0 END) AS gap_questions
                FROM questions q JOIN study_state s ON s.question_uid=q.uid
                WHERE COALESCE(s.suspended,0)=0
                  AND (? = '' OR EXISTS (
                      SELECT 1 FROM qf_exam_question_links eql
                      WHERE eql.project_id=? AND eql.question_uid=q.uid AND COALESCE(eql.active,1)=1
                  ))
                GROUP BY COALESCE(NULLIF(TRIM(q.subject),''),'Sem matéria')
                ORDER BY priority DESC,due_count DESC,wrong_count DESC
                LIMIT 20
                """,
                (now, project_id, project_id),
            ).fetchall()
        recent_insights = self._recent_subject_insights()
        result: list[dict[str, Any]] = []
        for row in rows:
            correct = int(row["correct_count"] or 0)
            wrong = int(row["wrong_count"] or 0)
            attempts = correct + wrong
            mastery = _clamp(float(row["mastery"] or 0.5), 0.0, 1.0)
            confidence = _clamp(float(row["mastery_confidence"] or 0.0), 0.0, 1.0)
            level, conf_label = self._mastery_level(mastery, confidence, attempts)
            due = int(row["due_count"] or 0)
            gaps = int(row["gap_questions"] or 0)
            accuracy = correct / attempts if attempts else None
            priority = _clamp(float(row["priority"] or 0.0), 0.0, 1.0)
            reasons: list[str] = []
            if due:
                reasons.append("memory_risk")
            if accuracy is not None and attempts >= 5 and accuracy < 0.65:
                reasons.append("recent_performance")
            if gaps:
                reasons.append("learning_gap")
            if level in {"fragile", "developing"} and conf_label != "low":
                reasons.append("mastery_gap")
            if not reasons and attempts < 5:
                reasons.append("insufficient_evidence")
            priority_level = "high" if priority >= 0.68 or due >= 5 else "medium" if priority >= 0.38 or due else "low"
            result.append(
                {
                    "subject_id": hashlib.sha1(str(row["subject"]).encode("utf-8")).hexdigest()[:12],
                    "label": str(row["subject"]),
                    "status": "needs_attention" if priority_level == "high" else "monitor" if priority_level == "medium" else "stable",
                    "mastery": {"level": level, "confidence": conf_label, "estimate": round(mastery, 4)},
                    "performance": {"accuracy": None if accuracy is None else round(accuracy, 4), "attempts": attempts},
                    "memory": {"status": "review_due" if due else "up_to_date", "due_count": due, "retrievability": round(float(row["retrievability"] or 0.0), 4)},
                    "priority": {"level": priority_level, "score": round(priority, 4), "reasons": reasons},
                    "recommended_action": {"type": "question_session", "question_count": max(5, min(12, due or 8))},
                    "insight": recent_insights.get(str(row["subject"]), {
                        "recent_accuracy": None, "trend_delta": None, "recent_sample": 0,
                        "last_answered_at": "",
                        "difficulty": {"easy": 0, "medium": 0, "hard": 0, "known": 0},
                        "learning_gap": {"marked": 0, "known": 0}, "weak_topics": [],
                    }),
                    "exam_project_id": project_id,
                }
            )
        return result

    def progress_projection(self, exam_project_id: str = "") -> dict[str, Any]:
        project_id = str(exam_project_id or "").strip()
        priorities = self.priorities_projection(project_id)
        with self.database.connect() as connection:
            totals = connection.execute(
                """
                SELECT COUNT(*) AS attempts,
                       SUM(CASE WHEN is_correct=1 THEN 1 ELSE 0 END) AS correct,
                       AVG(CASE WHEN timing_quality IN ('valid','active_filtered') THEN response_seconds END) AS active_avg,
                       SUM(CASE WHEN timing_quality IN ('valid','active_filtered') AND response_seconds IS NOT NULL THEN 1 ELSE 0 END) AS timing_samples,
                       SUM(CASE WHEN timing_quality IN ('idle_contaminated','outlier','abandoned','wall_clock_unverified','legacy_unverified') THEN 1 ELSE 0 END) AS timing_excluded,
                       SUM(CASE WHEN substr(answered_at,1,10)=substr(?,1,10) THEN 1 ELSE 0 END) AS today_attempts
                FROM telegram_attempts
                WHERE (?='' OR exam_project_id=?)
                """,
                (utc_now(), project_id, project_id),
            ).fetchone()
        attempts = int(totals["attempts"] or 0) if totals else 0
        correct = int(totals["correct"] or 0) if totals else 0
        wrong = max(0, attempts - correct)
        accuracy = (correct / attempts) if attempts else None
        coach_text = "Responda algumas questões para o QuestFlow começar a reconhecer seu padrão de estudo."
        if priorities:
            top = priorities[0]
            recent = top.get("insight") or {}
            recent_accuracy = recent.get("recent_accuracy")
            if top["priority"]["level"] == "high":
                coach_text = f"{top['label']} é sua principal prioridade agora. Faça o lote recomendado e reavalie a tendência depois."
            elif recent_accuracy is not None and float(recent_accuracy) >= 0.80:
                coach_text = f"{top['label']} está mais controlada, mas ainda é a melhor matéria para manter em observação."
            else:
                coach_text = f"Continue consolidando {top['label']} com um lote curto antes de ampliar o foco."
        study_backlog = self._study_backlog_projection(project_id)
        return {
            "contract": MOBILE_CONTRACT,
            "generated_at": utc_now(),
            "exam_project_id": project_id,
            "study_backlog": study_backlog,
            "summary": {
                "attempts": attempts,
                "correct": correct,
                "wrong": wrong,
                "accuracy": None if accuracy is None else round(accuracy, 4),
                "avg_active_response_seconds": None if not totals or totals["active_avg"] is None else round(float(totals["active_avg"]), 1),
                "timing_samples": int(totals["timing_samples"] or 0) if totals else 0,
                "timing_samples_excluded": int(totals["timing_excluded"] or 0) if totals else 0,
                "today_attempts": int(totals["today_attempts"] or 0) if totals else 0,
                "coach_text": coach_text,
                "timing_note": "Tempo médio usa apenas tempo ativo aprovado pelo Quality Gate; deixar o app aberto não conta como lentidão.",
            },
            "subjects": priorities,
            "recent_activity": self._recent_activity_projection(),
        }

    @staticmethod
    def _analytics_window(value: str) -> tuple[int | None, str]:
        """Normalize the public analytics range without accepting unbounded scans."""
        normalized = str(value or "all").strip().lower()
        if normalized in {"all", "history", "full"}:
            return None, "all"
        allowed = {"4w": 4, "8w": 8, "12w": 12, "24w": 24}
        weeks = allowed.get(normalized, 12)
        return weeks, f"{weeks}w"

    @staticmethod
    def _analytics_period_start(value: datetime, grain: str) -> datetime:
        current = value.astimezone(timezone.utc)
        if grain == "day":
            return current.replace(hour=0, minute=0, second=0, microsecond=0)
        return (current - timedelta(days=current.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)

    def analytics_projection(
        self,
        exam_project_id: str = "",
        *,
        range_value: str = "all",
        grain: str = "attempt",
    ) -> dict[str, Any]:
        """Return an evidence-backed analytics snapshot shared by Studio and Mobile.

        Historical retention is deliberately left null because the current database
        stores the latest FSRS retrievability, not a time series of past snapshots.
        This prevents the UI from drawing a convincing but fabricated retention line.
        """
        project_id = str(exam_project_id or "").strip()
        weeks, normalized_range = self._analytics_window(range_value)
        now = utc_now_dt()
        start = None if weeks is None else now - timedelta(weeks=weeks)
        normalized_grain = str(grain or "attempt").strip().lower()
        if normalized_grain not in {"attempt", "day", "week"}:
            normalized_grain = "attempt"
        priorities = self.priorities_projection(project_id)
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT a.answered_at,a.is_correct,a.response_seconds,a.timing_quality,
                       COALESCE(NULLIF(TRIM(q.subject),''),'Sem matéria') AS subject
                FROM telegram_attempts a
                JOIN questions q ON q.uid=a.question_uid
                WHERE (? IS NULL OR a.answered_at>=?)
                  AND (?='' OR COALESCE(a.exam_project_id,'')=? OR EXISTS (
                    SELECT 1 FROM qf_exam_question_links eql
                    WHERE eql.project_id=? AND eql.question_uid=a.question_uid AND COALESCE(eql.active,1)=1
                  ))
                ORDER BY a.answered_at
                """,
                (None if start is None else start.isoformat(), None if start is None else start.isoformat(), project_id, project_id, project_id),
            ).fetchall()

        buckets: dict[str, dict[str, Any]] = {}
        subject_totals: dict[str, dict[str, Any]] = {}
        raw_timeline: list[dict[str, Any]] = []
        running_attempts = 0
        running_correct = 0
        latest_answered_at = ""
        for row in rows:
            answered = parse_iso(row["answered_at"])
            if answered is None:
                continue
            period = self._analytics_period_start(answered, "day" if normalized_grain == "attempt" else normalized_grain).date().isoformat()
            bucket = buckets.setdefault(period, {"attempts": 0, "correct": 0, "active_total": 0.0, "active_samples": 0})
            bucket["attempts"] += 1
            bucket["correct"] += 1 if bool(row["is_correct"]) else 0
            running_attempts += 1
            running_correct += 1 if bool(row["is_correct"]) else 0
            if row["response_seconds"] is not None and str(row["timing_quality"] or "") in TIMING_ELIGIBLE_QUALITIES:
                bucket["active_total"] += float(row["response_seconds"])
                bucket["active_samples"] += 1
            subject = str(row["subject"] or "Sem matéria")
            subject_bucket = subject_totals.setdefault(subject, {"attempts": 0, "correct": 0})
            subject_bucket["attempts"] += 1
            subject_bucket["correct"] += 1 if bool(row["is_correct"]) else 0
            latest_answered_at = max(latest_answered_at, str(row["answered_at"] or ""))
            if normalized_grain == "attempt":
                raw_timeline.append({
                    "period_start": answered.isoformat(),
                    "response_index": running_attempts,
                    "attempts": 1,
                    "accuracy": 1.0 if bool(row["is_correct"]) else 0.0,
                    "is_correct": bool(row["is_correct"]),
                    "cumulative_accuracy": round(running_correct / running_attempts, 4),
                    "retention": None,
                    "due_reviews": None,
                    "active_minutes": round(float(row["response_seconds"] or 0.0) / 60.0, 1) if str(row["timing_quality"] or "") in TIMING_ELIGIBLE_QUALITIES else 0.0,
                    "timing_samples": 1 if row["response_seconds"] is not None and str(row["timing_quality"] or "") in TIMING_ELIGIBLE_QUALITIES else 0,
                })

        timeline: list[dict[str, Any]] = raw_timeline
        if normalized_grain != "attempt":
            effective_start = start or (parse_iso(rows[0]["answered_at"]) if rows else now)
            cursor = self._analytics_period_start(effective_start or now, normalized_grain)
            end_period = self._analytics_period_start(now, normalized_grain)
            step = timedelta(days=1 if normalized_grain == "day" else 7)
            timeline = []
            cumulative_attempts = 0
            cumulative_correct = 0
            while cursor <= end_period:
                key = cursor.date().isoformat()
                item = buckets.get(key, {"attempts": 0, "correct": 0, "active_total": 0.0, "active_samples": 0})
                attempts = int(item["attempts"])
                cumulative_attempts += attempts
                cumulative_correct += int(item["correct"])
                timeline.append({
                    "period_start": key,
                    "attempts": attempts,
                    "accuracy": None if not attempts else round(int(item["correct"]) / attempts, 4),
                    "cumulative_accuracy": None if not cumulative_attempts else round(cumulative_correct / cumulative_attempts, 4),
                    "retention": None,
                    "due_reviews": None,
                    "active_minutes": round(float(item["active_total"]) / 60.0, 1),
                    "timing_samples": int(item["active_samples"]),
                })
                cursor += step

        priority_by_subject = {str(item.get("label") or ""): item for item in priorities}
        subjects: list[dict[str, Any]] = []
        for label, item in subject_totals.items():
            attempts = int(item["attempts"])
            priority = priority_by_subject.get(label, {})
            memory = priority.get("memory") or {}
            mastery = priority.get("mastery") or {}
            subjects.append({
                "subject_id": hashlib.sha1(label.encode("utf-8")).hexdigest()[:12],
                "label": label,
                "attempts": attempts,
                "accuracy": None if not attempts else round(int(item["correct"]) / attempts, 4),
                "retention": memory.get("retrievability"),
                "mastery": mastery.get("estimate"),
                "due_reviews": int(memory.get("due_count") or 0),
                "sample_confidence": "high" if attempts >= 30 else "medium" if attempts >= 12 else "low",
            })
        subjects.sort(key=lambda item: (-int(item["due_reviews"]), item["accuracy"] if item["accuracy"] is not None else 2, -int(item["attempts"])))

        total_attempts = running_attempts
        total_correct = running_correct
        accuracy = (total_correct / total_attempts) if total_attempts else None
        if accuracy is None:
            low = high = None
        else:
            # Wilson interval, which behaves better than a symmetric normal band for small samples.
            z = 1.96
            denominator = 1 + (z * z / total_attempts)
            centre = (accuracy + (z * z / (2 * total_attempts))) / denominator
            margin = z * ((accuracy * (1 - accuracy) / total_attempts + z * z / (4 * total_attempts * total_attempts)) ** 0.5) / denominator
            low, high = round(max(0.0, centre - margin), 4), round(min(1.0, centre + margin), 4)

        retention_values = [float(item["retention"]) for item in subjects if item.get("retention") is not None]
        retention_current = round(sum(retention_values) / len(retention_values), 4) if retention_values else None
        due_total = sum(int(item["due_reviews"]) for item in subjects)
        priority_breakdown: list[dict[str, Any]] = []
        for item in priorities[:8]:
            performance = item.get("performance") or {}
            memory = item.get("memory") or {}
            mastery = item.get("mastery") or {}
            attempts = int(performance.get("attempts") or 0)
            priority_breakdown.append({
                "subject_id": str(item.get("subject_id") or ""),
                "label": str(item.get("label") or "Sem matéria"),
                "total": round(float((item.get("priority") or {}).get("score") or 0.0), 4),
                "memory_risk": round(1.0 - float(memory.get("retrievability") or 0.0), 4),
                "performance_gap": round(1.0 - float(performance.get("accuracy") if performance.get("accuracy") is not None else 0.5), 4),
                "mastery_gap": round(1.0 - float(mastery.get("estimate") or 0.5), 4),
                "evidence_gap": round(max(0.0, 1.0 - attempts / 20.0), 4),
            })

        return {
            "contract": "questflow.analytics.v2",
            "generated_at": utc_now(),
            "exam_project_id": project_id,
            "range": normalized_range,
            "grain": normalized_grain,
            "summary": {
                "attempts": total_attempts,
                "correct": total_correct,
                "accuracy": None if accuracy is None else round(accuracy, 4),
                "retention_current": retention_current,
                "due_reviews": due_total,
                "active_minutes": round(sum(float(item["active_minutes"]) for item in timeline), 1),
            },
            "timeline": timeline,
            "subjects": subjects,
            "priority_breakdown": priority_breakdown,
            "projection_band": {
                "estimate": None if accuracy is None else round(accuracy, 4),
                "low": low,
                "high": high,
                "confidence": 0.95 if total_attempts else None,
                "sample_size": total_attempts,
                "label": "Intervalo de desempenho observado; não é probabilidade de aprovação.",
            },
            "review_queue": [
                {
                    "subject_id": str(item.get("subject_id") or ""),
                    "label": str(item.get("label") or "Sem matéria"),
                    "due_count": int((item.get("memory") or {}).get("due_count") or 0),
                    "priority": str((item.get("priority") or {}).get("level") or "low"),
                    "question_count": int((item.get("recommended_action") or {}).get("question_count") or 0),
                }
                for item in priorities if int((item.get("memory") or {}).get("due_count") or 0) > 0
            ][:8],
            "sample_size": total_attempts,
            "source_freshness": {
                "latest_answered_at": latest_answered_at or None,
                "generated_at": utc_now(),
                "attempt_history": "available" if total_attempts else "empty",
                "retention_history": "not_collected",
                "note": "O percurso usa todas as respostas confirmadas desde o início. A retenção histórica só será desenhada quando houver snapshots FSRS persistidos.",
            },
        }

    def today_projection(self, exam_project_id: str = "") -> dict[str, Any]:
        priorities = self.priorities_projection(exam_project_id)
        top = priorities[0] if priorities else None
        due_total = sum(int(item["memory"]["due_count"]) for item in priorities)
        recommended = sum(int(item["recommended_action"]["question_count"]) for item in priorities[:3]) if priorities else 0
        if top:
            reason_labels = {
                "memory_risk": "há revisões vencidas ou próximas",
                "recent_performance": "o desempenho recente está abaixo do desejável",
                "learning_gap": "você marcou que ainda precisa estudar parte do conteúdo",
                "mastery_gap": "o domínio estimado ainda está em consolidação",
                "insufficient_evidence": "ainda há pouca evidência para uma leitura segura",
            }
            reasons = [reason_labels.get(reason, reason) for reason in list(top["priority"].get("reasons") or [])]
            why = "; ".join(reasons[:3]) or "é a melhor oportunidade de ganho identificada pelo seu histórico atual"
            coach = {
                "headline": f"Comece por {top['label']}",
                "what_happened": f"O QuestFlow colocou {top['label']} como prioridade {str(top['priority']['level']).lower()}.",
                "why_it_matters": why[:1].upper() + why[1:] + ".",
                "next_action": f"Faça {int(top['recommended_action']['question_count'])} questões agora e use o resultado para recalibrar a próxima sessão.",
                "question_count": int(top["recommended_action"]["question_count"]),
            }
        else:
            coach = {
                "headline": "Comece a gerar evidência",
                "what_happened": "Ainda não há respostas suficientes para destacar uma prioridade confiável.",
                "why_it_matters": "Sem amostra, percentuais isolados podem dar uma falsa impressão de domínio.",
                "next_action": "Responda um primeiro lote de questões para o QuestFlow montar sua leitura inicial.",
                "question_count": 8,
            }
        return {
            "contract": MOBILE_CONTRACT,
            "generated_at": utc_now(),
            "exam_project_id": str(exam_project_id or ""),
            "top_priority": top,
            "today": {
                "reviews_due": due_total,
                "recommended_questions": max(0, min(40, recommended)),
                "not_studied_topics": self._study_backlog_projection(exam_project_id).get("pending_count", 0),
            },
            "coach": coach,
            "focus": priorities[:5],
            "recent_activity": self._recent_activity_projection()[:5],
        }

    def _cloud_bridge_projection(self) -> dict[str, Any]:
        if callable(self.cloud_bridge_provider):
            try:
                value = self.cloud_bridge_provider()
                if isinstance(value, dict):
                    return dict(value)
            except Exception:
                pass
        return {"enabled": False, "base_url": "", "state": "disabled", "protocol": "questflow.mobile.cloud.v1"}


    def bootstrap_projection(self, exam_project_id: str = "") -> dict[str, Any]:
        identity = self.identity()
        with self.database.connect() as connection:
            device_count = int(connection.execute("SELECT COUNT(*) FROM qf_mobile_devices WHERE status='active'").fetchone()[0] or 0)
            project = None
            if exam_project_id:
                project = connection.execute("SELECT id,name,agency,role,board,exam_date,status,active FROM qf_exam_projects WHERE id=?", (str(exam_project_id),)).fetchone()
            if project is None:
                project = connection.execute("SELECT id,name,agency,role,board,exam_date,status,active FROM qf_exam_projects WHERE active=1 LIMIT 1").fetchone()
        project_payload = dict(project) if project else None
        project_id = str(project_payload.get("id") if project_payload else exam_project_id or "")
        return {
            "contract": MOBILE_CONTRACT,
            "schema_version": MOBILE_SCHEMA_VERSION,
            "identity": {key: identity[key] for key in ("account_id", "tenant_id", "learner_id")},
            "active_project": project_payload,
            "today": self.today_projection(project_id),
            "progress": self.progress_projection(project_id),
            "analytics": self.analytics_projection(project_id, range_value="all", grain="attempt"),
            "devices": device_count,
            "sync": {
                "event_cursor": self.latest_cursor(),
                "idempotent_events": True,
                "offline_outbox_supported": True,
                "offline_study_pack_supported": True,
                "offline_study_pack_policy": "studio_learning_engine_snapshot_v1",
                "transport": "studio_lan",
                "cloud_bridge": self._cloud_bridge_projection(),
            },
            "privacy": {"location": False, "contacts": False, "microphone": False, "advertising_id": False},
        }

    # ------------------------------- sync -------------------------------
    def latest_cursor(self) -> int:
        with self.database.connect() as connection:
            row = connection.execute("SELECT COALESCE(MAX(seq),0) FROM qf_learning_events").fetchone()
        return int(row[0] or 0)

    def sync_pull(self, auth: dict[str, Any], *, cursor: int = 0, limit: int = 250) -> dict[str, Any]:
        cursor = max(0, int(cursor or 0))
        limit = max(1, min(1000, int(limit or 250)))
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT seq,event_id,event_type,device_id,session_id,attempt_id,exam_project_id,
                       question_uid,question_revision,occurred_at,sequence_no,client_platform,client_version,
                       payload_json,process_status
                FROM qf_learning_events
                WHERE seq>? ORDER BY seq ASC LIMIT ?
                """,
                (cursor, limit),
            ).fetchall()
        events = []
        next_cursor = cursor
        for row in rows:
            item = dict(row)
            next_cursor = max(next_cursor, int(item.pop("seq")))
            try:
                item["payload"] = json.loads(str(item.pop("payload_json")))
            except Exception:
                item["payload"] = {}
                item.pop("payload_json", None)
            events.append(item)
        return {
            "contract": MOBILE_CONTRACT,
            "cursor": next_cursor,
            "has_more": len(rows) >= limit,
            "events": events,
            "server_time": utc_now(),
        }

    # -------------------------- status & HTTP bridge --------------------
    def status(self) -> dict[str, Any]:
        identity = self.identity()
        with self.database.connect() as connection:
            device_rows = connection.execute(
                """
                SELECT device_id,platform,name,app_version,status,paired_at,last_seen_at,revoked_at,hidden_at,
                       CASE WHEN push_token IS NULL OR TRIM(push_token)='' THEN 0 ELSE 1 END AS push_registered
                FROM qf_mobile_devices
                WHERE hidden_at IS NULL
                ORDER BY CASE WHEN status='active' THEN 0 ELSE 1 END, last_seen_at DESC
                """
            ).fetchall()
            devices = sum(1 for row in device_rows if str(row["status"] or "") == "active")
            disconnected = sum(1 for row in device_rows if str(row["status"] or "") != "active")
            events = int(connection.execute("SELECT COUNT(*) FROM qf_learning_events").fetchone()[0] or 0)
            applied = int(connection.execute("SELECT COUNT(*) FROM qf_mobile_event_effects").fetchone()[0] or 0)
            pairings = int(connection.execute("SELECT COUNT(*) FROM qf_mobile_pairings WHERE used_at IS NULL AND expires_at>=?", (utc_now(),)).fetchone()[0] or 0)
        return {
            "ok": True,
            "api": MOBILE_CONTRACT,
            "schema_version": MOBILE_SCHEMA_VERSION,
            "identity_ready": True,
            "account_id": identity["account_id"],
            "tenant_id": identity["tenant_id"],
            "learner_id": identity["learner_id"],
            "database_per_tenant_control_plane": True,
            "active_devices": devices,
            "disconnected_devices": disconnected,
            "devices": [
                {**dict(row), "status": "active" if str(row["status"] or "") == "active" else "disconnected"}
                for row in device_rows
            ],
            "learning_events": events,
            "applied_event_effects": applied,
            "open_pairings": pairings,
            "event_idempotency": True,
            "question_revisions": True,
            "offline_sync_cursor": True,
            "active_timing_quality_gate": True,
            "cloud_bridge": self._cloud_bridge_projection(),
        }

    @staticmethod
    def bearer_from_headers(headers: Any) -> str:
        value = ""
        try:
            value = str(headers.get("Authorization", "") or "")
        except Exception:
            value = ""
        if value.lower().startswith("bearer "):
            return value[7:].strip()
        return ""

    def http_request(
        self,
        *,
        method: str,
        path: str,
        headers: Any,
        body: dict[str, Any] | None = None,
        query: dict[str, list[str]] | None = None,
    ) -> tuple[int, dict[str, Any]]:
        """Dependency-free versioned HTTP contract used by ``web_server``."""
        method = str(method or "GET").upper()
        path = str(path or "")
        body = dict(body or {})
        query = query or {}

        try:
            if path == "/api/v1/mobile/health" and method == "GET":
                return 200, {
                    "ok": True,
                    "api": MOBILE_CONTRACT,
                    "schema_version": MOBILE_SCHEMA_VERSION,
                    "server_time": utc_now(),
                    "pairing_supported": True,
                    "auth": "pairing_then_bearer",
                    "server_fingerprint": self.discovery_fingerprint(),
                }
            if path == "/api/v1/mobile/pairing/exchange" and method == "POST":
                result = self.exchange_pairing(str(body.get("pairing_token") or ""), body.get("device") if isinstance(body.get("device"), dict) else {})
                return 200, {"ok": True, **result}

            auth = self.authenticate(self.bearer_from_headers(headers))

            project_id = str(body.get("exam_project_id") or (query.get("exam_project_id") or [""])[0] or "")
            if path == "/api/v1/mobile/bootstrap" and method == "GET":
                return 200, {"ok": True, "data": self.bootstrap_projection(project_id)}
            if path == "/api/v1/mobile/today" and method == "GET":
                return 200, {"ok": True, "data": self.today_projection(project_id)}
            if path == "/api/v1/mobile/priorities" and method == "GET":
                return 200, {"ok": True, "data": self.priorities_projection(project_id)}
            if path == "/api/v1/mobile/progress" and method == "GET":
                return 200, {"ok": True, "data": self.progress_projection(project_id)}
            if path == "/api/v1/mobile/analytics" and method == "GET":
                range_value = str((query.get("range") or ["12w"])[0] or "12w")
                grain = str((query.get("grain") or ["week"])[0] or "week")
                return 200, {"ok": True, "data": self.analytics_projection(project_id, range_value=range_value, grain=grain)}
            if path.startswith("/api/v1/mobile/attempts/") and path.endswith("/feedback") and method == "GET":
                attempt_id = path.split("/")[-2]
                return 200, {"ok": True, "data": self.feedback_for_attempt(auth, attempt_id)}
            if path.startswith("/api/v1/mobile/questions/") and method == "GET":
                uid = path.rsplit("/", 1)[-1]
                return 200, {"ok": True, "data": self.question_for_mobile(uid)}
            if path == "/api/v1/mobile/study-sessions" and method == "POST":
                return 200, {"ok": True, "data": self.start_adaptive_study_session(
                    auth,
                    session_id=str(body.get("session_id") or ""),
                    count=int(body.get("count") or 10),
                    exam_project_id=project_id,
                    mode=str(body.get("mode") or "recommended"),
                    subject=str(body.get("subject") or ""),
                    micro_batch_size=int(body.get("micro_batch_size") or DEFAULT_MICRO_BATCH_SIZE),
                )}
            if path.startswith("/api/v1/mobile/study-sessions/") and path.endswith("/micro-batches") and method == "POST":
                session_id = path.split("/")[-2]
                return 200, {"ok": True, "data": self.next_adaptive_micro_batch(
                    auth,
                    session_id,
                    purpose=str(body.get("purpose") or "active"),
                    prefetched_batch_id=str(body.get("prefetched_batch_id") or ""),
                    force_replan=bool(body.get("force_replan", False)),
                    excluded_uids=list(body.get("excluded_question_ids") or []),
                )}
            if path.startswith("/api/v1/mobile/study-sessions/") and method == "GET":
                session_id = path.rsplit("/", 1)[-1]
                row = self.adaptive_sessions._session(session_id)
                if str(row.get("learner_id") or "") and str(row.get("learner_id") or "") != str(auth.get("learner_id") or ""):
                    raise PermissionError("Sessão adaptativa pertence a outro aluno.")
                return 200, {"ok": True, "data": self.adaptive_sessions.session_status(session_id)}
            if path == "/api/v1/mobile/question-batches" and method == "POST":
                return 200, {"ok": True, "data": self.question_batch(
                    count=int(body.get("count") or 8),
                    exam_project_id=project_id,
                    mode=str(body.get("mode") or "recommended"),
                    subject=str(body.get("subject") or ""),
                    learner_id=str(auth.get("learner_id") or ""),
                    device_id=str(auth.get("device_id") or ""),
                )}
            if path == "/api/v1/mobile/events:batch" and method == "POST":
                events = body.get("events") if isinstance(body.get("events"), list) else []
                return 200, self.ingest_events(auth, events)
            if path == "/api/v1/mobile/sync" and method == "GET":
                cursor = int((query.get("cursor") or [0])[0] or 0)
                limit = int((query.get("limit") or [250])[0] or 250)
                return 200, {"ok": True, "data": self.sync_pull(auth, cursor=cursor, limit=limit)}
            if path == "/api/v1/mobile/sync" and method == "POST":
                events = body.get("events") if isinstance(body.get("events"), list) else []
                feedback_attempt_id = str(body.get("feedback_attempt_id") or "").strip()
                fast_feedback = bool(feedback_attempt_id) and not bool(body.get("refresh_offline_pack", True))
                pushed = self.ingest_events(
                    auth,
                    events,
                    defer_answer_projections=fast_feedback,
                )
                pulled = self.sync_pull(auth, cursor=int(body.get("cursor") or 0), limit=int(body.get("limit") or 250))
                offline_pack = None
                if bool(body.get("refresh_offline_pack", True)):
                    offline_pack = self.offline_study_pack(
                        auth,
                        exam_project_id=str(body.get("exam_project_id") or ""),
                        count=int(body.get("offline_pack_size") or 30),
                    )
                feedback = None
                if feedback_attempt_id and not bool(pushed.get("failed")):
                    # O resultado da tentativa volta na mesma viagem que registra a
                    # resposta. A atualização completa do pacote offline pode ocorrer
                    # depois, sem bloquear a tela de feedback do estudante.
                    feedback = self.feedback_for_attempt(auth, feedback_attempt_id)
                projection_pending = any(
                    str(effect.get("projection_status") or "") == "pending"
                    for effect in list(pushed.get("effects") or [])
                    if isinstance(effect, dict)
                )
                if fast_feedback and not projection_pending:
                    with self.database.connect() as connection:
                        projection_pending = bool(connection.execute(
                            "SELECT 1 FROM qf_learning_events WHERE attempt_id=? AND process_status='projection_pending' LIMIT 1",
                            (feedback_attempt_id,),
                        ).fetchone())
                if projection_pending:
                    self.schedule_projection_drain()
                return 200, {
                    "ok": not bool(pushed.get("failed")),
                    "push": pushed,
                    "pull": pulled,
                    "offline_study_pack": offline_pack,
                    "feedback": feedback,
                    "projection_pending": projection_pending,
                }
            if path == "/api/v1/mobile/devices/push-token" and method == "POST":
                return 200, self.register_push_token(auth, push_token=str(body.get("push_token") or ""), provider=str(body.get("provider") or "fcm"))
            if path.startswith("/api/v1/mobile/devices/") and method == "DELETE":
                device_id = path.rsplit("/", 1)[-1]
                if device_id != str(auth["device_id"]):
                    raise PermissionError("Um dispositivo só pode desconectar a própria sessão por esta API.")
                return 200, self.disconnect_device(device_id)
            return 404, {"ok": False, "error": "Rota mobile não encontrada."}
        except PermissionError as error:
            return 401, {"ok": False, "error": str(error)}
        except (ValueError, TypeError, KeyError) as error:
            return 400, {"ok": False, "error": str(error)}
        except Exception as error:
            return 500, {"ok": False, "error": str(error)}


__all__ = [
    "ACCESS_TOKEN_TTL_DAYS",
    "IDLE_CONTAMINATION_SECONDS",
    "LEARNING_EVENT_TYPES",
    "MAX_ACTIVE_RESPONSE_SECONDS",
    "MOBILE_API_VERSION",
    "MOBILE_CONTRACT",
    "MOBILE_SCHEMA_VERSION",
    "MobileFoundationService",
    "PAIRING_TTL_MINUTES",
    "TIMING_ELIGIBLE_QUALITIES",
    "TenantControlPlane",
    "TimingAssessment",
    "assess_response_timing",
]
