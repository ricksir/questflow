from __future__ import annotations

"""Local-first synchronization layer backed by Turso Cloud.

The QuestFlow domain database remains ordinary SQLite and all UI/business reads
and writes stay local. A durable SQLite outbox captures committed changes. The
outbox is replicated to an append-only event log stored in Turso over the
official SQL-over-HTTP endpoint. This design intentionally avoids replacing the
existing SQLite driver and therefore keeps backup/export/repair code compatible,
works offline, and uses the existing corporate proxy manager.

Important semantics:
* committed local work is durable before any network request;
* remote event IDs are idempotent, so a crash after upload is safe to retry;
* pull replays remote changes atomically while keeping local pending changes;
* a global study generation prevents stale pre-reset progress from returning;
* operational queues (Telegram inbox/outbox/runtime) stay device-local.
"""

import base64
import hashlib
import json
import os
import socket
import sqlite3
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator, Sequence

from app_shared import APP_VERSION
from .network import NetworkManager
from .rate_limiter import acquire_external_slot
from .secure_store import clear_secret, load_secret_map, save_secret_map


SYNC_SCHEMA_VERSION = 1
CLOUD_CREDENTIAL_FILENAME = "turso_credentials.dat"

# Parent / identity tables first so FK-dependent tables are uploaded in a safe order.
SYNC_TABLES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("questions", ("uid",)),
    ("qf_question_currency", ("question_uid",)),
    ("qf_legislation_versions", ("id",)),
    ("qf_exam_projects", ("id",)),
    ("qf_exam_versions", ("id",)),
    ("qf_exam_syllabus_items", ("id",)),
    ("qf_exam_question_links", ("project_id", "syllabus_item_id", "question_uid")),
    ("excluded_questions", ("id",)),
    ("imports", ("id",)),
    ("question_code_history", ("id",)),
    ("course_catalog_lessons", ("lesson_key",)),
    ("course_catalog_imports", ("id",)),
    ("course_catalog_changes", ("id",)),
    ("course_learner_state", ("lesson_key",)),
    ("study_state", ("question_uid",)),
    ("telegram_deliveries", ("id",)),
    ("telegram_attempts", ("id",)),
    ("adaptive_simulation_sessions", ("id",)),
    ("adaptive_simulation_items", ("id",)),
    ("tutor_scaffold_sessions", ("id",)),
    ("tutor_scaffold_events", ("id",)),
    ("study_cycles", ("id",)),
    ("telegram_review_requests", ("id",)),
    ("adaptive_model_state", ("id",)),
    ("topic_learning_state", ("subject", "topic")),
    ("lesson_learning_state", ("subject", "lesson")),
    ("xp_events", ("id",)),
    ("learner_profile", ("id",)),
    # Eventos internos e event store seletivo usam a mesma outbox durável.
    # As projeções reconstruíveis permanecem locais e não são sincronizadas.
    ("qf_internal_events", ("event_id",)),
    ("qf_event_store", ("event_id",)),
)
SYNC_TABLE_MAP = dict(SYNC_TABLES)
TABLE_RANK = {name: index for index, (name, _pk) in enumerate(SYNC_TABLES)}

SYNC_TABLE_LABELS: dict[str, str] = {
    "questions": "Questões",
    "qf_question_currency": "Atualidade das questões",
    "qf_legislation_versions": "Legislação temporal",
    "qf_exam_projects": "Projetos de concurso",
    "qf_exam_versions": "Editais e retificações",
    "qf_exam_syllabus_items": "Itens do edital",
    "qf_exam_question_links": "Vínculos questão ↔ edital",
    "excluded_questions": "Questões excluídas",
    "imports": "Importações",
    "question_code_history": "Histórico de códigos",
    "course_catalog_lessons": "Catálogo de trilhas e aulas",
    "course_catalog_imports": "Histórico de versões do catálogo",
    "course_catalog_changes": "Alterações do catálogo",
    "course_learner_state": "Progresso por aula do catálogo",
    "study_state": "FSRS / estado de estudo",
    "telegram_deliveries": "Entregas Telegram",
    "telegram_attempts": "Tentativas / respostas",
    "adaptive_simulation_sessions": "Sessões de simulado",
    "adaptive_simulation_items": "Itens de simulado",
    "tutor_scaffold_sessions": "Sessões de scaffolding do Tutor",
    "tutor_scaffold_events": "Níveis/pistas do Tutor",
    "study_cycles": "Ciclos de estudo",
    "telegram_review_requests": "Pedidos de revisão",
    "adaptive_model_state": "Modelo adaptativo",
    "topic_learning_state": "Knowledge Tracing por tópico",
    "lesson_learning_state": "Knowledge Tracing por aula",
    "xp_events": "Eventos de XP",
    "learner_profile": "Perfil do aluno",
    "qf_internal_events": "Eventos internos entre módulos",
    "qf_event_store": "Event store seletivo",
}

# Campos derivados/transitórios que podem mudar ao apenas abrir/atualizar painéis.
# Eles são recalculáveis a partir do estado durável (FSRS/histórico) e NÃO devem
# criar eventos de Cloud Sync. Sem essa separação, uma simples pré-visualização
# do Recomendador atualizava study_state e recriava centenas de itens na outbox.
SYNC_TRANSIENT_UPDATE_COLUMNS: dict[str, frozenset[str]] = {
    # Colunas editoriais derivadas podem ser reconstruídas a partir de data_json
    # e das tentativas. Recalcular a Curadoria não deve criar alterações remotas.
    "questions": frozenset({
        "origin_type",
        "curation_status",
        "quality_score",
        "commentary_source",
        "rights_status",
        "difficulty_score",
        "difficulty_label",
        "tags_text",
        "law_refs_text",
        "semantic_version",
        "semantic_indexed_at",
    }),
    "study_state": frozenset({
        "memory_retrievability",
        "adaptive_prediction",
        "adaptive_priority",
        "last_selection_reason",
        "last_selection_bucket",
    }),
}

# A global study reset invalidates only learning/progress state. Editorial content
# (questions, code history, imports and review requests) must survive and may have
# legitimate offline edits waiting on another device.
RESET_SCOPED_TABLES = frozenset(
    {
        "study_state",
        "telegram_deliveries",
        "telegram_attempts",
        "adaptive_simulation_sessions",
        "adaptive_simulation_items",
        "tutor_scaffold_sessions",
        "tutor_scaffold_events",
        "study_cycles",
        "adaptive_model_state",
        "topic_learning_state",
        "lesson_learning_state",
        "course_learner_state",
        "xp_events",
        "learner_profile",
    }
)

# Cloud Sync 6.14.1 — safe activation metadata. These labels do not change
# replication semantics; they make dry-runs and recovery decisions explicit.
SYNC_TABLE_NAMESPACES: dict[str, str] = {
    "questions": "content",
    "qf_question_currency": "content",
    "qf_legislation_versions": "content",
    "qf_exam_projects": "content",
    "qf_exam_versions": "content",
    "qf_exam_syllabus_items": "content",
    "qf_exam_question_links": "content",
    "excluded_questions": "content",
    "imports": "content",
    "question_code_history": "content",
    "course_catalog_lessons": "content",
    "course_catalog_imports": "content",
    "course_catalog_changes": "content",
    "course_learner_state": "learner",
    "telegram_deliveries": "integration",
    "telegram_review_requests": "integration",
    "telegram_attempts": "learner",
    "study_state": "learner",
    "adaptive_simulation_sessions": "learner",
    "adaptive_simulation_items": "learner",
    "tutor_scaffold_sessions": "learner",
    "tutor_scaffold_events": "learner",
    "study_cycles": "learner",
    "adaptive_model_state": "learner",
    "topic_learning_state": "learner",
    "lesson_learning_state": "learner",
    "xp_events": "learner",
    "learner_profile": "learner",
    "qf_internal_events": "system",
    "qf_event_store": "system",
}

SYNC_DERIVED_TABLES = frozenset({
    "study_state", "adaptive_model_state", "topic_learning_state", "lesson_learning_state",
})

SAFE_ACTIVATION_RUNTIME_KEYS: tuple[tuple[str, str], ...] = (
    ("activation_state", "not_started"),
    ("activation_validated_at", ""),
    ("activation_backup_path", ""),
    ("activation_backup_sha256", ""),
    ("activation_first_sync_at", ""),
    ("activation_completed_at", ""),
    ("activation_last_error", ""),
    ("activation_checkpoint", ""),
    ("activation_recovery_guard_released_at", ""),
    ("activation_recovery_guard_archive", ""),
    ("activation_recovery_guard_sha256", ""),
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _json_default(value: Any) -> Any:
    if isinstance(value, (bytes, bytearray, memoryview)):
        return {"__qf_blob__": base64.b64encode(bytes(value)).decode("ascii")}
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"Tipo não serializável: {type(value)!r}")


def _json_object_hook(value: dict[str, Any]) -> Any:
    if set(value) == {"__qf_blob__"}:
        try:
            return base64.b64decode(str(value["__qf_blob__"]))
        except Exception:
            return b""
    return value


def _stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=_json_default)


def _checksum(table: str, row_key: str, operation: str, payload_json: str, generation: int) -> str:
    material = "\x1f".join([str(generation), table, row_key, operation, payload_json]).encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def _row_key(values: Sequence[Any]) -> str:
    return _stable_json(list(values))


def _parse_row_key(value: str) -> list[Any]:
    parsed = json.loads(str(value or "[]"))
    if not isinstance(parsed, list):
        raise ValueError("Chave de sincronização inválida.")
    return parsed


def _cloud_secret_path(config_path: str | Path) -> Path:
    return Path(config_path).resolve().parent / CLOUD_CREDENTIAL_FILENAME


def save_turso_token(config_path: str | Path, token: str) -> None:
    token = str(token or "").strip()
    path = _cloud_secret_path(config_path)
    if not token:
        clear_secret(path)
        return
    save_secret_map(path, {"auth_token": token}, description="QuestFlow Turso Cloud Token")


def load_turso_token(config_path: str | Path) -> str:
    return str(load_secret_map(_cloud_secret_path(config_path)).get("auth_token", "") or "")


def clear_turso_token(config_path: str | Path) -> None:
    clear_secret(_cloud_secret_path(config_path))


def normalize_turso_url(value: str) -> str:
    text = str(value or "").strip().rstrip("/")
    if not text:
        return ""
    parsed = urllib.parse.urlparse(text)
    if parsed.scheme in {"turso", "libsql"}:
        text = urllib.parse.urlunparse(("https", parsed.netloc, parsed.path, "", "", "")).rstrip("/")
    elif parsed.scheme not in {"http", "https"}:
        raise ValueError("A URL do Turso deve começar por turso://, libsql://, https:// ou http://.")
    return text


def turso_pipeline_url(value: str) -> str:
    base = normalize_turso_url(value)
    if not base:
        raise ValueError("Informe a URL do banco Turso.")
    if base.endswith("/v2/pipeline"):
        return base
    return base + "/v2/pipeline"


def _encode_http_arg(value: Any) -> dict[str, Any]:
    if value is None:
        return {"type": "null"}
    if isinstance(value, bool):
        return {"type": "integer", "value": "1" if value else "0"}
    if isinstance(value, int):
        return {"type": "integer", "value": str(value)}
    if isinstance(value, float):
        return {"type": "float", "value": repr(value)}
    if isinstance(value, (bytes, bytearray, memoryview)):
        return {"type": "blob", "base64": base64.b64encode(bytes(value)).decode("ascii")}
    return {"type": "text", "value": str(value)}


def _decode_http_value(value: Any) -> Any:
    if not isinstance(value, dict):
        return value
    kind = value.get("type")
    if kind == "null":
        return None
    raw = value.get("value")
    if kind == "integer":
        try:
            return int(raw)
        except (TypeError, ValueError):
            return raw
    if kind == "float":
        try:
            return float(raw)
        except (TypeError, ValueError):
            return raw
    if kind == "blob":
        encoded = value.get("base64", raw or "")
        try:
            return base64.b64decode(str(encoded))
        except Exception:
            return b""
    return raw


class TursoHttpError(RuntimeError):
    def __init__(self, message: str, *, status: int | None = None, category: str = "cloud") -> None:
        super().__init__(message)
        self.status = status
        self.category = category


class TursoHttpClient:
    """Minimal official SQL-over-HTTP client with QuestFlow proxy support."""

    def __init__(
        self,
        remote_url: str,
        auth_token: str,
        *,
        network_manager: NetworkManager | None = None,
        timeout: float = 15.0,
        rate_config: dict | None = None,
    ) -> None:
        self.remote_url = normalize_turso_url(remote_url)
        self.pipeline_url = turso_pipeline_url(remote_url)
        self.auth_token = str(auth_token or "").strip()
        self.network = network_manager or NetworkManager()
        self.timeout = max(2.0, float(timeout))
        self.rate_config = rate_config if isinstance(rate_config, dict) else {}

    def _request(self, statements: Sequence[tuple[str, Sequence[Any]]]) -> list[dict[str, Any]]:
        if not self.auth_token:
            raise TursoHttpError("O token do Turso não foi configurado.", category="auth")
        requests: list[dict[str, Any]] = []
        for sql, args in statements:
            requests.append(
                {
                    "type": "execute",
                    "stmt": {"sql": str(sql), "args": [_encode_http_arg(value) for value in args]},
                }
            )
        requests.append({"type": "close"})
        body = json.dumps({"requests": requests}, separators=(",", ":")).encode("utf-8")
        acquire_external_slot(self.rate_config, "turso", timeout=min(5.0, self.timeout), burst=12.0)
        request = urllib.request.Request(
            self.pipeline_url,
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.auth_token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": f"QuestFlowStudio/{APP_VERSION}",
            },
        )
        try:
            with self.network.open(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            if error.code in {401, 403}:
                raise TursoHttpError("O Turso recusou o token ou a permissão do banco.", status=error.code, category="auth") from error
            if error.code == 407:
                raise TursoHttpError("O proxy corporativo exige autenticação (HTTP 407).", status=407, category="proxy_auth") from error
            detail = ""
            try:
                raw = error.read().decode("utf-8", errors="replace")[:1600]
                parsed = json.loads(raw) if raw else {}
                if isinstance(parsed, dict):
                    candidate = parsed.get("message") or parsed.get("error") or parsed.get("detail")
                    if isinstance(candidate, dict):
                        candidate = candidate.get("message") or candidate.get("detail")
                    detail = str(candidate or "").strip()
                if not detail:
                    detail = raw.strip()
            except Exception:
                detail = ""
            suffix = f" — {detail[:700]}" if detail else ""
            raise TursoHttpError(f"O Turso respondeu HTTP {error.code}{suffix}.", status=error.code, category="http") from error
        except urllib.error.URLError as error:
            raise TursoHttpError(f"Sem conexão com o Turso: {getattr(error, 'reason', error)}", category="offline") from error
        except (TimeoutError, socket.timeout) as error:
            raise TursoHttpError("A conexão com o Turso expirou.", category="timeout") from error
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            raise TursoHttpError("O Turso retornou uma resposta inválida.", category="protocol") from error

        results = payload.get("results") if isinstance(payload, dict) else None
        if not isinstance(results, list):
            raise TursoHttpError("Resposta SQL-over-HTTP sem a lista de resultados.", category="protocol")
        decoded: list[dict[str, Any]] = []
        for result in results[: len(statements)]:
            if not isinstance(result, dict):
                raise TursoHttpError("Resultado SQL-over-HTTP inválido.", category="protocol")
            if result.get("type") == "error":
                error = result.get("error") or {}
                raise TursoHttpError(str(error.get("message") or error or "Falha SQL no Turso."), category="sql")
            response = result.get("response") or {}
            execute_result = response.get("result") or {}
            cols = [str(item.get("name", "")) for item in execute_result.get("cols", []) if isinstance(item, dict)]
            rows: list[dict[str, Any]] = []
            for row in execute_result.get("rows", []) or []:
                values = [_decode_http_value(item) for item in row]
                rows.append(dict(zip(cols, values)))
            decoded.append(
                {
                    "rows": rows,
                    "affected_row_count": int(execute_result.get("affected_row_count", 0) or 0),
                    "last_insert_rowid": _decode_http_value(execute_result.get("last_insert_rowid")),
                }
            )
        return decoded

    def execute(self, sql: str, args: Sequence[Any] = ()) -> dict[str, Any]:
        return self._request([(sql, args)])[0]

    def execute_batch(self, statements: Sequence[tuple[str, Sequence[Any]]]) -> list[dict[str, Any]]:
        if not statements:
            return []
        return self._request(statements)

    def ensure_schema(self) -> None:
        statements = [
            (
                """
                CREATE TABLE IF NOT EXISTS qf_sync_events (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT NOT NULL UNIQUE,
                    device_id TEXT NOT NULL,
                    generation INTEGER NOT NULL,
                    table_name TEXT NOT NULL,
                    row_key TEXT NOT NULL,
                    operation TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    checksum TEXT NOT NULL,
                    schema_version INTEGER NOT NULL DEFAULT 1
                )
                """,
                (),
            ),
            ("CREATE INDEX IF NOT EXISTS idx_qf_sync_events_generation_seq ON qf_sync_events(generation, seq)", ()),
            (
                "CREATE INDEX IF NOT EXISTS idx_qf_sync_events_table_key_seq "
                "ON qf_sync_events(table_name, row_key, seq)",
                (),
            ),
            (
                """
                CREATE TABLE IF NOT EXISTS qf_sync_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """,
                (),
            ),
            (
                """
                CREATE TABLE IF NOT EXISTS qf_sync_devices (
                    device_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    app_version TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL
                )
                """,
                (),
            ),
            (
                "INSERT OR IGNORE INTO qf_sync_meta(key,value,updated_at) VALUES('generation','1',?)",
                (_utc_now(),),
            ),
        ]
        self.execute_batch(statements)

    def test(self) -> dict[str, Any]:
        started = time.perf_counter()
        self.ensure_schema()
        result = self.execute("SELECT value FROM qf_sync_meta WHERE key='generation'")
        generation = int((result["rows"][0] if result["rows"] else {}).get("value", 1) or 1)
        return {"ok": True, "generation": generation, "elapsed_ms": round((time.perf_counter() - started) * 1000)}

    def get_generation(self) -> int:
        result = self.execute("SELECT value FROM qf_sync_meta WHERE key='generation'")
        try:
            return max(1, int(result["rows"][0]["value"])) if result["rows"] else 1
        except Exception:
            return 1

    def set_generation(self, generation: int) -> None:
        self.execute(
            """
            INSERT INTO qf_sync_meta(key,value,updated_at) VALUES('generation',?,?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
            """,
            (str(max(1, int(generation))), _utc_now()),
        )

    def touch_device(self, device_id: str, name: str) -> None:
        self.execute(
            """
            INSERT INTO qf_sync_devices(device_id,name,app_version,last_seen_at) VALUES(?,?,?,?)
            ON CONFLICT(device_id) DO UPDATE SET name=excluded.name, app_version=excluded.app_version,
                last_seen_at=excluded.last_seen_at
            """,
            (device_id, name, APP_VERSION, _utc_now()),
        )

    def append_events(self, events: Sequence[dict[str, Any]]) -> int:
        if not events:
            return 0
        written = 0
        for offset in range(0, len(events), 50):
            statements: list[tuple[str, Sequence[Any]]] = []
            for event in events[offset : offset + 50]:
                statements.append(
                    (
                        """
                        INSERT OR IGNORE INTO qf_sync_events(
                            event_id,device_id,generation,table_name,row_key,operation,payload_json,
                            created_at,checksum,schema_version
                        ) VALUES(?,?,?,?,?,?,?,?,?,?)
                        """,
                        (
                            event["event_id"], event["device_id"], int(event["generation"]), event["table_name"],
                            event["row_key"], event["operation"], event["payload_json"], event["created_at"],
                            event["checksum"], SYNC_SCHEMA_VERSION,
                        ),
                    )
                )
            results = self.execute_batch(statements)
            written += sum(int(item.get("affected_row_count", 0) or 0) for item in results)
        return written

    def fetch_events(self, after_seq: int, generation: int, *, limit: int = 500) -> list[dict[str, Any]]:
        result = self.execute(
            """
            SELECT seq,event_id,device_id,generation,table_name,row_key,operation,payload_json,created_at,checksum
            FROM qf_sync_events
            WHERE seq > ?
            ORDER BY seq ASC
            LIMIT ?
            """,
            (max(0, int(after_seq)), max(1, min(5000, int(limit)))),
        )
        return list(result.get("rows") or [])

    def event_count(self) -> int:
        result = self.execute("SELECT COUNT(*) AS total FROM qf_sync_events")
        return int((result["rows"][0] if result["rows"] else {}).get("total", 0) or 0)

    def current_row_count(self, table_name: str) -> int:
        """Return the current logical row count represented by the append-only event log.

        The latest event for each row key wins. This is intentionally not filtered
        by study generation because editorial rows (especially ``questions``) survive
        a global study reset and may legitimately have been last written in an older
        generation.
        """
        result = self.execute(
            """
            SELECT COUNT(*) AS total
            FROM qf_sync_events AS current
            INNER JOIN (
                SELECT row_key, MAX(seq) AS max_seq
                FROM qf_sync_events
                WHERE table_name=?
                GROUP BY row_key
            ) AS latest
              ON latest.max_seq=current.seq
            WHERE current.table_name=? AND current.operation <> 'delete'
            """,
            (str(table_name), str(table_name)),
        )
        return int((result["rows"][0] if result["rows"] else {}).get("total", 0) or 0)

    def current_rows(self, table_name: str, *, limit: int = 5000) -> list[dict[str, Any]]:
        """Return latest non-deleted logical rows for read-only activation comparison."""
        table = str(table_name)
        result = self.execute(
            """
            SELECT current.seq,current.event_id,current.device_id,current.generation,current.row_key,
                   current.payload_json,current.created_at,current.checksum
            FROM qf_sync_events AS current
            INNER JOIN (
                SELECT row_key, MAX(seq) AS max_seq
                FROM qf_sync_events
                WHERE table_name=?
                GROUP BY row_key
            ) AS latest ON latest.max_seq=current.seq
            WHERE current.table_name=? AND current.operation <> 'delete'
            ORDER BY current.seq ASC
            LIMIT ?
            """,
            (table, table, max(1, min(20000, int(limit)))),
        )
        return list(result.get("rows") or [])

    def max_event_seq(self) -> int:
        result = self.execute("SELECT COALESCE(MAX(seq),0) AS seq FROM qf_sync_events")
        return int((result["rows"][0] if result["rows"] else {}).get("seq", 0) or 0)

    def health_counters(self, table_name: str = "questions") -> dict[str, int]:
        """Fetch the remote health counters in one SQL-over-HTTP round trip."""
        table = str(table_name)
        results = self.execute_batch(
            [
                (
                    """
                    SELECT COUNT(*) AS total
                    FROM qf_sync_events AS current
                    INNER JOIN (
                        SELECT row_key, MAX(seq) AS max_seq
                        FROM qf_sync_events
                        WHERE table_name=?
                        GROUP BY row_key
                    ) AS latest
                      ON latest.max_seq=current.seq
                    WHERE current.table_name=? AND current.operation <> 'delete'
                    """,
                    (table, table),
                ),
                ("SELECT value FROM qf_sync_meta WHERE key='generation'", ()),
                ("SELECT COALESCE(MAX(seq),0) AS seq FROM qf_sync_events", ()),
            ]
        )
        count_rows = results[0].get("rows") or []
        generation_rows = results[1].get("rows") or []
        seq_rows = results[2].get("rows") or []
        return {
            "row_count": int((count_rows[0] if count_rows else {}).get("total", 0) or 0),
            "generation": max(1, int((generation_rows[0] if generation_rows else {}).get("value", 1) or 1)),
            "max_event_seq": int((seq_rows[0] if seq_rows else {}).get("seq", 0) or 0),
        }


@dataclass(slots=True)
class SyncStatus:
    enabled: bool = False
    state: str = "disabled"
    pending: int = 0
    conflicts: int = 0
    generation: int = 1
    last_sync_at: str = ""
    last_attempt_at: str = ""
    last_error: str = ""
    last_error_at: str = ""
    last_push_count: int = 0
    last_pull_count: int = 0
    device_id: str = ""
    device_name: str = ""

    def public(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "state": self.state,
            "pending": self.pending,
            "conflicts": self.conflicts,
            "generation": self.generation,
            "last_sync_at": self.last_sync_at,
            "last_attempt_at": self.last_attempt_at,
            "last_error": self.last_error,
            "last_error_at": self.last_error_at,
            "last_push_count": self.last_push_count,
            "last_pull_count": self.last_pull_count,
            "device_id": self.device_id,
            "device_name": self.device_name,
        }


class CloudSyncEngine:
    def __init__(
        self,
        database_path: str | Path,
        *,
        config: dict,
        config_path: str | Path,
        remote_client: Any | None = None,
        reset_callback: Callable[[], Any] | None = None,
        auth_token: str | None = None,
    ) -> None:
        self.database_path = Path(database_path)
        self.config = config
        self.config_path = Path(config_path)
        self.reset_callback = reset_callback
        self._lock = threading.RLock()
        self._health_lock = threading.RLock()
        self._integrity_cache: dict[str, Any] = {}
        self._integrity_cache_at = 0.0
        self._integrity_cache_seconds = 300.0
        self._remote_client = remote_client
        self._auth_token_override = auth_token
        self.initialize_local()

    @contextmanager
    def _connect(self, *, timeout: float = 8.0) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path, timeout=timeout)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA busy_timeout=8000")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize_local(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS qf_sync_runtime (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS qf_sync_outbox (
                    event_id TEXT PRIMARY KEY,
                    generation INTEGER NOT NULL,
                    table_name TEXT NOT NULL,
                    row_key TEXT NOT NULL,
                    operation TEXT NOT NULL,
                    changed_at TEXT NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT NOT NULL DEFAULT '',
                    UNIQUE(table_name,row_key)
                );
                CREATE INDEX IF NOT EXISTS idx_qf_sync_outbox_generation ON qf_sync_outbox(generation,changed_at);
                CREATE TABLE IF NOT EXISTS qf_sync_outbox_deadletter (
                    id TEXT PRIMARY KEY,
                    event_id TEXT NOT NULL,
                    generation INTEGER NOT NULL,
                    table_name TEXT NOT NULL,
                    row_key TEXT NOT NULL,
                    operation TEXT NOT NULL,
                    changed_at TEXT NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT NOT NULL DEFAULT '',
                    quarantined_at TEXT NOT NULL,
                    reason TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_qf_sync_deadletter_time ON qf_sync_outbox_deadletter(quarantined_at);
                CREATE TABLE IF NOT EXISTS qf_sync_inbox (
                    event_id TEXT PRIMARY KEY,
                    remote_seq INTEGER NOT NULL,
                    received_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_qf_sync_inbox_remote_seq ON qf_sync_inbox(remote_seq);
                CREATE TABLE IF NOT EXISTS qf_sync_conflicts (
                    id TEXT PRIMARY KEY,
                    event_id TEXT NOT NULL,
                    table_name TEXT NOT NULL,
                    row_key TEXT NOT NULL,
                    local_event_id TEXT NOT NULL,
                    detected_at TEXT NOT NULL,
                    detail TEXT NOT NULL
                );
                """
            )
            for key, value in (
                ("generation", "1"), ("last_remote_seq", "0"), ("last_sync_at", ""),
                ("last_attempt_at", ""), ("last_error", ""), ("last_error_at", ""),
                ("last_push_count", "0"), ("last_pull_count", "0"),
                *SAFE_ACTIVATION_RUNTIME_KEYS,
            ):
                connection.execute(
                    "INSERT OR IGNORE INTO qf_sync_runtime(key,value,updated_at) VALUES(?,?,?)",
                    (key, value, _utc_now()),
                )
            device_id = self._runtime(connection, "device_id")
            if not device_id:
                device_id = str(uuid.uuid4())
                self._set_runtime(connection, "device_id", device_id)
            self._install_triggers(connection)

    def _install_triggers(self, connection: sqlite3.Connection) -> None:
        existing = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        for table, pk_columns in SYNC_TABLES:
            if table not in existing:
                continue
            key_new = "json_array(" + ",".join(f"NEW.\"{column}\"" for column in pk_columns) + ")"
            key_old = "json_array(" + ",".join(f"OLD.\"{column}\"" for column in pk_columns) + ")"
            for suffix in ("ai", "au", "ad"):
                connection.execute(f'DROP TRIGGER IF EXISTS "qf_sync_{table}_{suffix}"')
            common = "COALESCE((SELECT CAST(value AS INTEGER) FROM qf_sync_runtime WHERE key='generation'),1)"
            suppressed = "COALESCE((SELECT value FROM qf_sync_runtime WHERE key='suppress'),'0') <> '1'"
            # UPDATEs que alteram somente campos transitórios/recalculáveis não
            # representam uma mudança de domínio e não devem entrar na outbox.
            ignored = SYNC_TRANSIENT_UPDATE_COLUMNS.get(table, frozenset())
            table_columns = [str(row[1]) for row in connection.execute(f'PRAGMA table_info("{table}")').fetchall()]
            durable_columns = [column for column in table_columns if column not in ignored]
            changed_durable = " OR ".join(
                f'OLD."{column}" IS NOT NEW."{column}"' for column in durable_columns
            ) or "0"
            update_when = f"({suppressed}) AND ({changed_durable})"
            upsert_sql = lambda key_expr: f"""
                INSERT INTO qf_sync_outbox(event_id,generation,table_name,row_key,operation,changed_at,attempts,last_error)
                VALUES(lower(hex(randomblob(16))),{common},'{table}',{key_expr},'upsert',strftime('%Y-%m-%dT%H:%M:%fZ','now'),0,'')
                ON CONFLICT(table_name,row_key) DO UPDATE SET
                    event_id=excluded.event_id,generation=excluded.generation,operation='upsert',
                    changed_at=excluded.changed_at,attempts=0,last_error='';
            """
            delete_sql = f"""
                INSERT INTO qf_sync_outbox(event_id,generation,table_name,row_key,operation,changed_at,attempts,last_error)
                VALUES(lower(hex(randomblob(16))),{common},'{table}',{key_old},'delete',strftime('%Y-%m-%dT%H:%M:%fZ','now'),0,'')
                ON CONFLICT(table_name,row_key) DO UPDATE SET
                    event_id=excluded.event_id,generation=excluded.generation,operation='delete',
                    changed_at=excluded.changed_at,attempts=0,last_error='';
            """
            connection.executescript(
                f"""
                CREATE TRIGGER "qf_sync_{table}_ai" AFTER INSERT ON "{table}"
                WHEN {suppressed}
                BEGIN {upsert_sql(key_new)} END;
                CREATE TRIGGER "qf_sync_{table}_au" AFTER UPDATE ON "{table}"
                WHEN {update_when}
                BEGIN {upsert_sql(key_new)} END;
                CREATE TRIGGER "qf_sync_{table}_ad" AFTER DELETE ON "{table}"
                WHEN {suppressed}
                BEGIN {delete_sql} END;
                """
            )

    def _runtime(self, connection: sqlite3.Connection, key: str, default: str = "") -> str:
        row = connection.execute("SELECT value FROM qf_sync_runtime WHERE key=?", (key,)).fetchone()
        return str(row[0]) if row else default

    def _set_runtime(self, connection: sqlite3.Connection, key: str, value: Any) -> None:
        connection.execute(
            """
            INSERT INTO qf_sync_runtime(key,value,updated_at) VALUES(?,?,?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at
            """,
            (key, str(value), _utc_now()),
        )

    def generation(self) -> int:
        with self._connect() as connection:
            try:
                return max(1, int(self._runtime(connection, "generation", "1")))
            except ValueError:
                return 1

    def device_id(self) -> str:
        with self._connect() as connection:
            return self._runtime(connection, "device_id")

    def device_name(self) -> str:
        configured = str(self.config.get("cloud_device_name", "") or "").strip()
        if configured:
            return configured
        return os.environ.get("COMPUTERNAME") or socket.gethostname() or "QuestFlow"

    def _token(self) -> str:
        if self._auth_token_override is not None:
            return str(self._auth_token_override)
        return load_turso_token(self.config_path)

    def remote(self) -> Any:
        if self._remote_client is not None:
            return self._remote_client
        url = str(self.config.get("cloud_turso_url", "") or "").strip()
        return TursoHttpClient(
            url,
            self._token(),
            network_manager=NetworkManager(self.config, config_path=self.config_path),
            timeout=float(self.config.get("cloud_sync_timeout_seconds", 15) or 15),
            rate_config=self.config,
        )

    def recovery_guard_status(self) -> dict[str, Any]:
        """Describe the post-recovery Cloud Sync guard without changing it."""
        path = self.database_path.parent / "RECOVERY_GUARD.json"
        result: dict[str, Any] = {"active": path.exists(), "path": str(path), "reason": "", "created_at": ""}
        if not path.exists():
            return result
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                result["reason"] = str(payload.get("reason") or "Proteção pós-recuperação ativa.")
                result["created_at"] = str(payload.get("created_at") or "")
                result["schema"] = str(payload.get("schema") or "")
        except Exception as error:
            result["reason"] = f"Proteção pós-recuperação ativa; metadados não puderam ser lidos: {error}"
        return result

    def _release_recovery_guard_for_safe_activation(self) -> dict[str, Any]:
        """Archive RECOVERY_GUARD only after the user entered protected activation.

        Safe Activation is the explicit reconciliation action that the recovery
        guard was designed to wait for.  The guard is archived, never silently
        discarded, and automatic sync remains blocked by activation state until
        the first protected synchronization reaches queue=0/conflicts=0.
        """
        status = self.recovery_guard_status()
        if not status.get("active"):
            return {"released": False, "active": False}
        path = Path(str(status.get("path") or self.database_path.parent / "RECOVERY_GUARD.json"))
        if not path.exists():
            return {"released": False, "active": False}
        backup_path = str(self.activation_status().get("backup_path") or "")
        if not backup_path or not Path(backup_path).exists():
            raise RuntimeError("A proteção pós-recuperação só pode ser liberada após criar e validar o backup da ativação segura.")
        archive_dir = self.database_path.parent / "cloud_sync_backups"
        archive_dir.mkdir(parents=True, exist_ok=True)
        raw = path.read_bytes()
        sha = hashlib.sha256(raw).hexdigest()
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        archive = archive_dir / f"RECOVERY_GUARD.released-{stamp}.json"
        # write-then-delete keeps an auditable copy even if rename across a
        # protected/redirected Windows folder would fail.
        archive.write_bytes(raw)
        if hashlib.sha256(archive.read_bytes()).hexdigest() != sha:
            try:
                archive.unlink()
            except OSError:
                pass
            raise RuntimeError("Não foi possível validar o arquivamento do RECOVERY_GUARD.json.")
        path.unlink()
        with self._connect(timeout=3.0) as connection:
            self._set_runtime(connection, "activation_recovery_guard_released_at", _utc_now())
            self._set_runtime(connection, "activation_recovery_guard_archive", str(archive))
            self._set_runtime(connection, "activation_recovery_guard_sha256", sha)
        return {"released": True, "active": False, "archive": str(archive), "sha256": sha}

    def settings(self) -> dict[str, Any]:
        return {
            "cloud_sync_enabled": bool(self.config.get("cloud_sync_enabled", False)),
            "cloud_turso_url": str(self.config.get("cloud_turso_url", "") or ""),
            "cloud_device_name": self.device_name(),
            "cloud_sync_interval_seconds": int(self.config.get("cloud_sync_interval_seconds", 30) or 30),
            "cloud_sync_on_start": bool(self.config.get("cloud_sync_on_start", True)),
            "cloud_sync_on_shutdown": bool(self.config.get("cloud_sync_on_shutdown", True)),
            "cloud_turso_token_configured": bool(self._token()),
            "cloud_sync_safe_activation_required": bool(self.config.get("cloud_sync_safe_activation_required", False)),
            "cloud_sync_activation_completed": self.activation_completed(),
            "cloud_sync_activation_state": self.activation_status().get("state", "not_started"),
            "mobile_lan_enabled": bool(self.config.get("mobile_lan_enabled", False)),
        }

    def status(self) -> dict[str, Any]:
        with self._connect(timeout=2.0) as connection:
            pending = int(connection.execute("SELECT COUNT(*) FROM qf_sync_outbox").fetchone()[0])
            conflicts = int(connection.execute("SELECT COUNT(*) FROM qf_sync_conflicts").fetchone()[0])
            status = SyncStatus(
                enabled=bool(self.config.get("cloud_sync_enabled", False)),
                state="pending" if pending else ("synced" if self._runtime(connection, "last_sync_at") else "ready"),
                pending=pending,
                conflicts=conflicts,
                generation=max(1, int(self._runtime(connection, "generation", "1") or 1)),
                last_sync_at=self._runtime(connection, "last_sync_at"),
                last_attempt_at=self._runtime(connection, "last_attempt_at"),
                last_error=self._runtime(connection, "last_error"),
                last_error_at=self._runtime(connection, "last_error_at"),
                last_push_count=int(self._runtime(connection, "last_push_count", "0") or 0),
                last_pull_count=int(self._runtime(connection, "last_pull_count", "0") or 0),
                device_id=self._runtime(connection, "device_id"),
                device_name=self.device_name(),
            )
            if status.last_error:
                status.state = "error" if pending else "warning"
            public = status.public()
            activation = self.activation_status(connection=connection)
            public["activation"] = activation
            if bool(self.config.get("cloud_sync_safe_activation_required", False)) and not activation.get("completed"):
                public["state"] = "activation_required" if not status.last_error else public["state"]
            return public

    def activation_status(self, *, connection: sqlite3.Connection | None = None) -> dict[str, Any]:
        owns = connection is None
        if owns:
            context = self._connect(timeout=2.0)
            connection = context.__enter__()
        try:
            assert connection is not None
            state = self._runtime(connection, "activation_state", "not_started") or "not_started"
            completed_at = self._runtime(connection, "activation_completed_at", "")
            return {
                "required": bool(self.config.get("cloud_sync_safe_activation_required", False)),
                "completed": bool(completed_at) or state == "active",
                "state": state,
                "validated_at": self._runtime(connection, "activation_validated_at", ""),
                "backup_path": self._runtime(connection, "activation_backup_path", ""),
                "backup_sha256": self._runtime(connection, "activation_backup_sha256", ""),
                "first_sync_at": self._runtime(connection, "activation_first_sync_at", ""),
                "completed_at": completed_at,
                "last_error": self._runtime(connection, "activation_last_error", ""),
                "checkpoint": self._runtime(connection, "activation_checkpoint", ""),
                "source": self._runtime(connection, "activation_source", ""),
                "seeded_at": self._runtime(connection, "activation_seeded_at", ""),
                "recovery_guard_released_at": self._runtime(connection, "activation_recovery_guard_released_at", ""),
                "recovery_guard_archive": self._runtime(connection, "activation_recovery_guard_archive", ""),
                "recovery_guard_sha256": self._runtime(connection, "activation_recovery_guard_sha256", ""),
            }
        finally:
            if owns:
                context.__exit__(None, None, None)

    def activation_completed(self) -> bool:
        if not bool(self.config.get("cloud_sync_safe_activation_required", False)):
            return True
        try:
            return bool(self.activation_status().get("completed"))
        except Exception:
            return False

    def auto_sync_allowed(self) -> bool:
        return bool(self.config.get("cloud_sync_enabled", False)) and self.activation_completed()

    def invalidate_activation(self, reason: str = "Configuração do Turso alterada.") -> dict[str, Any]:
        with self._connect() as connection:
            self._set_runtime(connection, "activation_state", "needs_validation")
            self._set_runtime(connection, "activation_completed_at", "")
            self._set_runtime(connection, "activation_last_error", str(reason)[:1200])
            self._set_runtime(connection, "activation_checkpoint", "configuration_changed")
        return self.activation_status()

    def health_snapshot(self) -> dict[str, Any]:
        """Compare local SQLite health and synchronization state with Turso.

        This check is read-only. It deliberately verifies more than just ``pending=0``:
        local/remote question counts, generation and the last remote event sequence must
        also agree before the UI claims that both databases are synchronized.
        """
        local_count = 0
        local_quick_check = "indisponível"
        foreign_key_violations = 0
        last_remote_seq = 0
        status = self.safe_status()
        try:
            queue = self.pending_details(limit=12)
        except Exception:
            queue = {"total": int(status.get("pending", 0) or 0), "with_error": 0, "deadletter": 0, "groups": [], "items": []}
        now = time.monotonic()
        with self._health_lock:
            integrity_fresh = bool(self._integrity_cache) and (
                now - self._integrity_cache_at < self._integrity_cache_seconds
            )
            try:
                with self._connect(timeout=4.0) as connection:
                    if self._table_exists(connection, "questions"):
                        local_count = int(connection.execute('SELECT COUNT(*) FROM "questions"').fetchone()[0])
                    try:
                        last_remote_seq = max(0, int(self._runtime(connection, "last_remote_seq", "0") or 0))
                    except ValueError:
                        last_remote_seq = 0
                    if integrity_fresh:
                        local_quick_check = str(self._integrity_cache.get("quick_check", "indisponível"))
                        foreign_key_violations = int(self._integrity_cache.get("foreign_key_violations", -1))
                    else:
                        row = connection.execute("PRAGMA quick_check(1)").fetchone()
                        local_quick_check = str(row[0] if row else "indisponível")
                        try:
                            foreign_key_violations = sum(1 for _ in connection.execute("PRAGMA foreign_key_check"))
                        except sqlite3.Error:
                            foreign_key_violations = -1
                        self._integrity_cache = {
                            "quick_check": local_quick_check,
                            "foreign_key_violations": foreign_key_violations,
                        }
                        self._integrity_cache_at = now
            except sqlite3.Error as error:
                return {
                    "ok": False, "local_healthy": False, "local_question_count": local_count,
                    "remote_question_count": None, "counts_equal": False, "synchronized": False,
                    "cloud_reachable": False, "quick_check": str(error), "foreign_key_violations": -1,
                    "status": status, "queue": queue, "message": f"Banco local indisponível: {error}",
                }

        local_healthy = local_quick_check.lower() == "ok" and foreign_key_violations == 0
        enabled = bool(self.config.get("cloud_sync_enabled", False))
        token_configured = bool(self._token())
        url_configured = bool(str(self.config.get("cloud_turso_url", "") or "").strip())
        activation = self.activation_status()
        if not token_configured or not url_configured:
            return {
                "ok": local_healthy, "local_healthy": local_healthy, "local_question_count": local_count,
                "remote_question_count": None, "counts_equal": False, "synchronized": False,
                "cloud_reachable": False, "quick_check": local_quick_check,
                "foreign_key_violations": foreign_key_violations, "status": status, "queue": queue,
                "activation": activation,
                "message": "Banco local saudável; informe URL e token do Turso para validar o Cloud Sync.",
            }

        try:
            remote = self.remote()
            if hasattr(remote, "health_counters"):
                try:
                    # Fast path: a configured Turso database already has the
                    # synchronization schema, so health is one network round trip.
                    counters = remote.health_counters("questions")
                except Exception:
                    # First use or a newly changed Turso URL may not have the
                    # schema yet. Initialize once and retry instead of paying the
                    # CREATE/INDEX round trip on every dashboard refresh.
                    remote.ensure_schema()
                    counters = remote.health_counters("questions")
                remote_count = int(counters.get("row_count", 0) or 0)
                remote_generation = int(counters.get("generation", 1) or 1)
                remote_max_seq = int(counters.get("max_event_seq", 0) or 0)
            else:
                remote.ensure_schema()
                remote_count = int(remote.current_row_count("questions"))
                remote_generation = int(remote.get_generation())
                remote_max_seq = int(remote.max_event_seq())
            counts_equal = local_count == remote_count
            generation_equal = int(status.get("generation", 1) or 1) == remote_generation
            sequence_equal = last_remote_seq >= remote_max_seq
            synchronized = bool(
                local_healthy
                and counts_equal
                and generation_equal
                and sequence_equal
                and int(status.get("pending", 0) or 0) == 0
                and int(status.get("conflicts", 0) or 0) == 0
                and not str(status.get("last_error", "") or "").strip()
            )
            if synchronized:
                message = "Banco saudável, atualizado e sincronizado com o Turso."
            elif str(status.get("last_error", "") or "").strip():
                message = "A última tentativa de sincronização falhou; veja o erro e as alterações pendentes abaixo."
            elif not counts_equal:
                message = "Banco saudável, mas a quantidade de questões local e no Turso ainda difere."
            elif not sequence_equal:
                message = "Há atualizações no Turso que este computador ainda não confirmou."
            elif int(status.get("pending", 0) or 0):
                message = "Há alterações locais aguardando sincronização."
            elif int(status.get("conflicts", 0) or 0):
                message = "Existem conflitos de sincronização que precisam de revisão."
            else:
                message = "Banco conectado; conclua uma nova sincronização para confirmar o estado."
            return {
                "ok": local_healthy, "local_healthy": local_healthy, "local_question_count": local_count,
                "remote_question_count": remote_count, "counts_equal": counts_equal,
                "synchronized": synchronized, "cloud_reachable": True, "quick_check": local_quick_check,
                "foreign_key_violations": foreign_key_violations, "local_generation": int(status.get("generation", 1) or 1),
                "remote_generation": remote_generation, "last_remote_seq": last_remote_seq,
                "remote_max_seq": remote_max_seq, "status": status, "queue": queue, "activation": activation, "message": message,
            }
        except Exception as error:
            return {
                "ok": local_healthy, "local_healthy": local_healthy, "local_question_count": local_count,
                "remote_question_count": None, "counts_equal": False, "synchronized": False,
                "cloud_reachable": False, "quick_check": local_quick_check,
                "foreign_key_violations": foreign_key_violations, "status": status, "queue": queue, "activation": activation,
                "message": f"Banco local saudável, mas o Turso não pôde ser verificado: {error}",
                "error": str(error),
            }

    def safe_status(self) -> dict[str, Any]:
        """Return a UI-safe status even when SQLite is temporarily unavailable.

        This is deliberately separate from :meth:`status`: normal code should
        still fail loudly when the database is invalid, while network/background
        workers must never turn a transient lock, detached drive, or abrupt
        shutdown recovery into an application crash.
        """
        if not self.database_path.exists():
            return {
                "enabled": bool(self.config.get("cloud_sync_enabled", False)),
                "state": "database_unavailable",
                "pending": 0,
                "conflicts": 0,
                "generation": 1,
                "last_sync_at": "",
                "last_attempt_at": "",
                "last_error": "Banco local indisponível.",
                "last_error_at": "",
                "last_push_count": 0,
                "last_pull_count": 0,
                "device_id": "",
                "device_name": self.device_name(),
            }
        try:
            return self.status()
        except sqlite3.Error as error:
            return {
                "enabled": bool(self.config.get("cloud_sync_enabled", False)),
                "state": "database_busy",
                "pending": -1,
                "conflicts": -1,
                "generation": 1,
                "last_sync_at": "",
                "last_attempt_at": "",
                "last_error": f"Banco local temporariamente indisponível: {error}",
                "last_error_at": "",
                "last_push_count": 0,
                "last_pull_count": 0,
                "device_id": "",
                "device_name": self.device_name(),
            }

    def _quarantine_outbox_row(self, connection: sqlite3.Connection, row: sqlite3.Row, reason: str) -> None:
        connection.execute(
            """
            INSERT OR REPLACE INTO qf_sync_outbox_deadletter(
                id,event_id,generation,table_name,row_key,operation,changed_at,attempts,last_error,quarantined_at,reason
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                uuid.uuid4().hex, str(row["event_id"]), int(row["generation"]), str(row["table_name"]),
                str(row["row_key"]), str(row["operation"]), str(row["changed_at"]), int(row["attempts"] or 0),
                str(row["last_error"] or ""), _utc_now(), str(reason)[:1200],
            ),
        )
        connection.execute("DELETE FROM qf_sync_outbox WHERE event_id=?", (str(row["event_id"]),))

    def repair_pending_outbox(self) -> dict[str, Any]:
        """Quarantine structurally unsendable legacy events instead of leaving pending stuck forever."""
        repaired = 0
        reasons: dict[str, int] = {}
        with self._connect() as connection:
            generation = max(1, int(self._runtime(connection, "generation", "1") or 1))
            self._advance_pending_events_for_generation(connection, generation)
            rows = connection.execute("SELECT * FROM qf_sync_outbox ORDER BY changed_at ASC").fetchall()
            for row in rows:
                table = str(row["table_name"] or "")
                operation = str(row["operation"] or "")
                reason = ""
                if table not in SYNC_TABLE_MAP:
                    reason = "Tabela não pertence mais ao contrato de sincronização desta versão."
                elif not self._table_exists(connection, table):
                    reason = "Tabela de origem não existe nesta instalação."
                elif operation not in {"upsert", "delete"}:
                    reason = f"Operação de sincronização inválida: {operation or '(vazia)'}."
                else:
                    try:
                        key_values = _parse_row_key(str(row["row_key"]))
                        if len(key_values) != len(SYNC_TABLE_MAP[table]):
                            reason = "Chave de sincronização incompatível com a tabela."
                    except Exception:
                        reason = "Chave de sincronização corrompida ou ilegível."
                if reason:
                    self._quarantine_outbox_row(connection, row, reason)
                    repaired += 1
                    reasons[reason] = reasons.get(reason, 0) + 1
        return {"repaired": repaired, "reasons": reasons}

    def pending_details(self, *, limit: int = 40) -> dict[str, Any]:
        """Describe pending local changes without exposing row payloads or secrets."""
        max_items = max(1, min(200, int(limit)))
        with self._connect(timeout=3.0) as connection:
            total = int(connection.execute("SELECT COUNT(*) FROM qf_sync_outbox").fetchone()[0])
            with_error = int(connection.execute(
                "SELECT COUNT(*) FROM qf_sync_outbox WHERE attempts>0 OR trim(last_error)<>''"
            ).fetchone()[0])
            deadletter = int(connection.execute("SELECT COUNT(*) FROM qf_sync_outbox_deadletter").fetchone()[0])
            oldest_row = connection.execute("SELECT MIN(changed_at),MAX(changed_at),MAX(attempts) FROM qf_sync_outbox").fetchone()
            rows = connection.execute(
                "SELECT * FROM qf_sync_outbox ORDER BY CASE WHEN trim(last_error)<>'' THEN 0 ELSE 1 END, changed_at ASC LIMIT ?",
                (max_items,),
            ).fetchall()
            grouped_rows = connection.execute(
                """SELECT table_name,operation,COUNT(*) AS total,MAX(attempts) AS max_attempts,
                          SUM(CASE WHEN attempts>0 OR trim(last_error)<>'' THEN 1 ELSE 0 END) AS errors
                   FROM qf_sync_outbox GROUP BY table_name,operation ORDER BY total DESC,table_name"""
            ).fetchall()
            groups = [
                {
                    "table_name": str(row["table_name"]),
                    "label": SYNC_TABLE_LABELS.get(str(row["table_name"]), str(row["table_name"])),
                    "operation": str(row["operation"]),
                    "count": int(row["total"] or 0),
                    "errors": int(row["errors"] or 0),
                    "max_attempts": int(row["max_attempts"] or 0),
                }
                for row in grouped_rows
            ]
            items: list[dict[str, Any]] = []
            questions_exists = self._table_exists(connection, "questions")
            question_columns = set(self._table_columns(connection, "questions")) if questions_exists else set()
            for row in rows:
                table = str(row["table_name"] or "")
                row_key = str(row["row_key"] or "")
                display = row_key
                try:
                    keys = _parse_row_key(row_key)
                    display = " / ".join(str(value) for value in keys)
                    if table in {"questions", "study_state", "qf_question_currency"} and keys and questions_exists:
                        qid = str(keys[0])
                        wanted = [c for c in ("codigo_origem", "materia", "aula_planilha") if c in question_columns]
                        if wanted:
                            sql_cols = ",".join(f'"{c}"' for c in wanted)
                            question = connection.execute(f'SELECT {sql_cols} FROM "questions" WHERE uid=?', (qid,)).fetchone()
                            if question:
                                parts = [str(question[c] or "").strip() for c in wanted]
                                display = " · ".join(part for part in parts if part) or qid
                except Exception:
                    pass
                items.append({
                    "event_id": str(row["event_id"]),
                    "table_name": table,
                    "label": SYNC_TABLE_LABELS.get(table, table),
                    "row": display[:240],
                    "operation": str(row["operation"]),
                    "changed_at": str(row["changed_at"]),
                    "attempts": int(row["attempts"] or 0),
                    "last_error": str(row["last_error"] or "")[:600],
                })
            return {
                "total": total, "with_error": with_error, "deadletter": deadletter,
                "oldest_at": str(oldest_row[0] or "") if oldest_row else "",
                "newest_at": str(oldest_row[1] or "") if oldest_row else "",
                "max_attempts": int(oldest_row[2] or 0) if oldest_row else 0,
                "groups": groups, "items": items,
            }

    def _canonical_payload(self, table: str, payload: dict[str, Any]) -> str:
        ignored = SYNC_TRANSIENT_UPDATE_COLUMNS.get(table, frozenset())
        return _stable_json({str(k): v for k, v in payload.items() if str(k) not in ignored})

    def _payload_digest(self, table: str, payload_json: str) -> str:
        try:
            payload = json.loads(str(payload_json or "{}"), object_hook=_json_object_hook)
        except Exception:
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
        return hashlib.sha256(self._canonical_payload(table, payload).encode("utf-8")).hexdigest()

    def _local_manifest(self, table: str) -> dict[str, str]:
        if table not in SYNC_TABLE_MAP:
            return {}
        with self._connect(timeout=6.0) as connection:
            if not self._table_exists(connection, table):
                return {}
            pk_columns = SYNC_TABLE_MAP[table]
            rows = connection.execute(f'SELECT * FROM "{table}"').fetchall()
            manifest: dict[str, str] = {}
            for row in rows:
                payload = dict(row)
                key = _row_key([payload.get(column) for column in pk_columns])
                canonical = self._canonical_payload(table, payload)
                manifest[key] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
            return manifest

    def _remote_manifest(self, table: str, *, max_events: int = 25000) -> dict[str, str]:
        remote = self.remote()
        if hasattr(remote, "current_rows"):
            rows = list(remote.current_rows(table, limit=max_events))
            return {str(row.get("row_key", "")): self._payload_digest(table, str(row.get("payload_json", "{}"))) for row in rows if row.get("row_key")}
        latest: dict[str, dict[str, Any]] = {}
        after = 0
        while after < max_events:
            events = list(remote.fetch_events(after, 1, limit=min(1000, max_events-after)))
            if not events:
                break
            for event in events:
                after = max(after, int(event.get("seq", 0) or 0))
                if str(event.get("table_name", "")) == table:
                    latest[str(event.get("row_key", ""))] = dict(event)
            if len(events) < min(1000, max_events-after if max_events-after > 0 else 1000):
                break
        manifest: dict[str, str] = {}
        for key, event in latest.items():
            if key and str(event.get("operation", "")) != "delete":
                manifest[key] = self._payload_digest(table, str(event.get("payload_json", "{}")))
        return manifest

    def _unseen_remote_events(self, *, max_events: int = 10000) -> list[dict[str, Any]]:
        remote = self.remote()
        with self._connect(timeout=3.0) as connection:
            after = max(0, int(self._runtime(connection, "last_remote_seq", "0") or 0))
        items: list[dict[str, Any]] = []
        while len(items) < max_events:
            batch = list(remote.fetch_events(after, self.generation(), limit=min(1000, max_events-len(items))))
            if not batch:
                break
            items.extend(dict(item) for item in batch)
            after = max(after, max(int(item.get("seq", 0) or 0) for item in batch))
            if len(batch) < 1000:
                break
        return items

    def _activation_dry_run(self) -> dict[str, Any]:
        events = self._build_events(limit=5000)
        unseen = self._unseen_remote_events(max_events=10000)
        unseen_keys = {(str(item.get("table_name", "")), str(item.get("row_key", ""))): item for item in unseen}
        groups: dict[tuple[str, str, str], dict[str, Any]] = {}
        predicted_conflicts: list[dict[str, Any]] = []
        for item in events:
            table = str(item.get("table_name", ""))
            namespace = SYNC_TABLE_NAMESPACES.get(table, "system")
            kind = "derived" if table in SYNC_DERIVED_TABLES else "canonical"
            key = (namespace, kind, table)
            group = groups.setdefault(key, {
                "namespace": namespace, "kind": kind, "table_name": table,
                "label": SYNC_TABLE_LABELS.get(table, table), "count": 0,
            })
            group["count"] += 1
            remote_event = unseen_keys.get((table, str(item.get("row_key", ""))))
            if remote_event and str(remote_event.get("device_id", "")) != str(item.get("device_id", "")):
                predicted_conflicts.append({
                    "table_name": table, "label": SYNC_TABLE_LABELS.get(table, table),
                    "row_key": str(item.get("row_key", "")),
                    "remote_device_id": str(remote_event.get("device_id", "")),
                    "remote_seq": int(remote_event.get("seq", 0) or 0),
                })
        return {
            "pending": len(events),
            "groups": sorted(groups.values(), key=lambda g: (-int(g["count"]), g["namespace"], g["table_name"])),
            "predicted_conflicts": predicted_conflicts[:100],
            "predicted_conflict_count": len(predicted_conflicts),
            "unseen_remote_events": len(unseen),
            "event_ids_unique": len({str(item.get("event_id", "")) for item in events}) == len(events),
            "idempotency": "event_id_unique_remote",
        }

    def activation_preview(self) -> dict[str, Any]:
        """Read-only preflight for the first Cloud Sync write.

        If a previous protected activation already seeded the local outbox and
        stopped only because the bounded drain window ended, keep that
        checkpoint intact so the next click resumes instead of reseeding the
        same logical rows with new event IDs.
        """
        existing_activation = self.activation_status()
        checkpoint_value = str(existing_activation.get("checkpoint", "") or "")
        last_error_value = str(existing_activation.get("last_error", "") or "")
        resume_available = bool(existing_activation.get("seeded_at")) or (
            checkpoint_value in {"first_sync_started", "first_sync_progress", "first_sync_failed"}
            and last_error_value in {
                "A primeira sincronização não foi concluída.",
                "A primeira sincronização terminou com fila ou conflitos pendentes.",
                "",
            }
            and bool(existing_activation.get("backup_path"))
        )
        checkpoint = "local_validation"
        with self._connect(timeout=5.0) as connection:
            row = connection.execute("PRAGMA quick_check(1)").fetchone()
            quick = str(row[0] if row else "indisponível")
            fk = sum(1 for _ in connection.execute("PRAGMA foreign_key_check"))
            if not resume_available:
                self._set_runtime(connection, "activation_checkpoint", checkpoint)
        local_healthy = quick.lower() == "ok" and fk == 0
        url_ok = bool(str(self.config.get("cloud_turso_url", "") or "").strip())
        token_ok = bool(self._token())
        config_ok = url_ok and token_ok
        result: dict[str, Any] = {
            "ok": False, "read_only": True, "local_healthy": local_healthy,
            "quick_check": quick, "foreign_key_violations": fk,
            "configuration": {"url_configured": url_ok, "token_configured": token_ok, "complete": config_ok},
            "remote": {"reachable": False}, "questions": {}, "dry_run": {},
            "activation": self.activation_status(),
            "recovery_guard": self.recovery_guard_status(),
        }
        if not local_healthy or not config_ok:
            result["message"] = "Corrija a validação local ou a configuração do Turso antes de ativar."
            return result
        try:
            checkpoint = "remote_validation"
            remote = self.remote()
            test = remote.test()
            remote_events = int(remote.event_count()) if hasattr(remote, "event_count") else 0
            remote_manifest = self._remote_manifest("questions")
            local_manifest = self._local_manifest("questions")
            local_keys, remote_keys = set(local_manifest), set(remote_manifest)
            common = local_keys & remote_keys
            differing = [key for key in common if local_manifest[key] != remote_manifest[key]]
            local_only = sorted(local_keys - remote_keys)
            remote_only = sorted(remote_keys - local_keys)
            dry_run = self._activation_dry_run()
            with self._connect(timeout=3.0) as connection:
                if not resume_available:
                    self._set_runtime(connection, "activation_state", "validated")
                    self._set_runtime(connection, "activation_validated_at", _utc_now())
                    self._set_runtime(connection, "activation_last_error", "")
                    self._set_runtime(connection, "activation_checkpoint", "dry_run_complete")
            comparison = {
                "local_count": len(local_manifest), "remote_count": len(remote_manifest),
                "same_count": len(common) - len(differing),
                "different_count": len(differing),
                "local_only_count": len(local_only), "remote_only_count": len(remote_only),
                "counts_equal": len(local_manifest) == len(remote_manifest),
                "hashes_equal": not differing and not local_only and not remote_only,
                "samples": {
                    "different": differing[:8], "local_only": local_only[:8], "remote_only": remote_only[:8],
                },
            }
            result.update({
                "ok": True,
                "remote": {"reachable": True, "generation": int(test.get("generation", 1) or 1), "elapsed_ms": test.get("elapsed_ms"), "event_count": remote_events},
                "questions": comparison, "dry_run": dry_run, "activation": self.activation_status(),
                "recommended_source": (str(existing_activation.get("source") or "") if resume_available else "") or ("this_device" if remote_events == 0 else "merge"),
                "resume_available": resume_available,
                "resume_pending": int(dry_run.get("pending", 0) or 0) if resume_available else 0,
                "requires_difference_confirmation": (False if resume_available else (bool(differing or local_only or remote_only) and remote_events > 0)),
                "blocking_conflicts": bool(dry_run.get("predicted_conflict_count")),
                "message": ("Ativação anterior pode ser retomada com segurança; nenhuma nova semeadura será feita." if resume_available else "Pré-validação concluída. Nenhuma escrita foi feita no Turso."),
            })
            return result
        except Exception as error:
            with self._connect(timeout=3.0) as connection:
                self._set_runtime(connection, "activation_state", "validation_failed")
                self._set_runtime(connection, "activation_last_error", str(error)[:1200])
                self._set_runtime(connection, "activation_checkpoint", checkpoint)
            result["message"] = f"Não foi possível concluir a validação segura: {error}"
            result["error"] = str(error)
            result["activation"] = self.activation_status()
            return result

    def create_activation_backup(self) -> dict[str, Any]:
        backup_dir = self.database_path.parent / "cloud_sync_backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        target = backup_dir / f"QuestFlow-pre-cloud-sync-{stamp}.sqlite"
        source = sqlite3.connect(self.database_path, timeout=8.0)
        destination = sqlite3.connect(target)
        try:
            source.backup(destination)
            destination.commit()
            quick_row = destination.execute("PRAGMA quick_check(1)").fetchone()
            quick = str(quick_row[0] if quick_row else "indisponível")
            fk = sum(1 for _ in destination.execute("PRAGMA foreign_key_check"))
        finally:
            destination.close()
            source.close()
        sha = hashlib.sha256(target.read_bytes()).hexdigest()
        if quick.lower() != "ok" or fk:
            try:
                target.unlink()
            except OSError:
                pass
            raise RuntimeError("O backup de segurança falhou na validação SQLite.")
        with self._connect() as connection:
            self._set_runtime(connection, "activation_backup_path", str(target))
            self._set_runtime(connection, "activation_backup_sha256", sha)
            self._set_runtime(connection, "activation_checkpoint", "backup_validated")
        return {"path": str(target), "sha256": sha, "quick_check": quick, "foreign_key_violations": fk}

    def _activation_resume_available(self) -> bool:
        status = self.activation_status()
        checkpoint = str(status.get("checkpoint", "") or "")
        last_error = str(status.get("last_error", "") or "")
        if bool(status.get("seeded_at")) and checkpoint in {"first_sync_started", "first_sync_progress", "first_sync_failed"}:
            return True
        # Compatibility with 6.14.1–6.14.3: older activation paths may not persist
        # activation_seeded_at, but this exact generic error is only raised after
        # enqueue_full_snapshot() and a bounded sync_until_idle() attempt.
        return bool(status.get("backup_path")) and checkpoint == "first_sync_failed" and last_error in {
            "A primeira sincronização não foi concluída.",
            "A primeira sincronização terminou com fila ou conflitos pendentes.",
        }

    def _activation_sync_chunk(self, *, source: str, backup: dict[str, Any] | None = None, preview: dict[str, Any] | None = None, seeded: int = 0, pulled_before: int = 0) -> dict[str, Any]:
        """Advance a protected first sync without treating a bounded drain as failure.

        Normal Cloud Sync deliberately pushes at most 250 events per round. A
        first activation may contain thousands of rows, so one bounded call is
        a progress slice, not an all-or-nothing transaction. The UI can call
        activate_safely() again; the persisted checkpoint resumes the same
        outbox and keeps remote retries idempotent.
        """
        pending_before = self.pending_count()
        result = self.sync_until_idle(max_rounds=8, max_seconds=55.0, force=True)
        status = self.safe_status()
        pending = max(0, int(status.get("pending", 0) or 0))
        conflicts = max(0, int(status.get("conflicts", 0) or 0))
        pushed = max(0, int(result.get("pushed", 0) or 0))
        blocker = ""
        if result.get("recovery_guard") or (result.get("disabled") and result.get("message")):
            blocker = str(result.get("message") or "Cloud Sync bloqueado por proteção local.")
        error = str(result.get("error", "") or blocker or status.get("last_error", "") or "").strip()
        if not error and pending and pending >= pending_before and pushed == 0:
            error = "A sincronização não enviou nenhum evento neste ciclo. Verifique a proteção pós-recuperação, a conectividade e o diagnóstico do Cloud Sync antes de tentar novamente."
        if error:
            with self._connect(timeout=3.0) as connection:
                self._set_runtime(connection, "activation_state", "failed")
                self._set_runtime(connection, "activation_last_error", error[:1200])
                self._set_runtime(connection, "activation_checkpoint", "first_sync_failed")
            return {
                "ok": False, "completed": False, "stage": "first_sync", "error": error,
                "backup": backup or {}, "preview": preview or {}, "activation": self.activation_status(),
                "status": status, "sync": result, "pending": pending, "conflicts": conflicts,
                "retry_safe": True, "remote_writes_are_idempotent": True,
            }
        if conflicts:
            message = f"A primeira sincronização encontrou {conflicts} conflito(s) que precisam de revisão antes da ativação automática."
            with self._connect(timeout=3.0) as connection:
                self._set_runtime(connection, "activation_state", "failed")
                self._set_runtime(connection, "activation_last_error", message[:1200])
                self._set_runtime(connection, "activation_checkpoint", "first_sync_failed")
            return {
                "ok": False, "completed": False, "stage": "conflicts", "error": message,
                "backup": backup or {}, "preview": preview or {}, "activation": self.activation_status(),
                "status": status, "sync": result, "pending": pending, "conflicts": conflicts,
                "retry_safe": True, "remote_writes_are_idempotent": True,
            }
        if pending:
            with self._connect(timeout=3.0) as connection:
                self._set_runtime(connection, "activation_state", "syncing")
                self._set_runtime(connection, "activation_last_error", "")
                self._set_runtime(connection, "activation_checkpoint", "first_sync_progress")
            return {
                "ok": True, "completed": False, "in_progress": True, "source": source,
                "backup": backup or {}, "preview": preview or {}, "seeded": seeded,
                "pulled_before_seed": pulled_before, "sync": result, "pending": pending,
                "pending_before": pending_before, "pushed": pushed,
                "conflicts": 0, "activation": self.activation_status(), "status": self.safe_status(),
                "message": f"Primeira sincronização em andamento: {pending} alteração(ões) ainda aguardam envio.",
            }
        now = _utc_now()
        with self._connect() as connection:
            self._set_runtime(connection, "activation_state", "active")
            self._set_runtime(connection, "activation_first_sync_at", self._runtime(connection, "activation_first_sync_at", "") or now)
            self._set_runtime(connection, "activation_completed_at", now)
            self._set_runtime(connection, "activation_last_error", "")
            self._set_runtime(connection, "activation_checkpoint", "active")
        return {
            "ok": True, "completed": True, "in_progress": False, "source": source,
            "backup": backup or {}, "preview": preview or {}, "seeded": seeded,
            "pulled_before_seed": pulled_before, "sync": result, "pending": 0, "conflicts": 0,
            "activation": self.activation_status(), "status": self.safe_status(),
        }

    def activate_safely(self, *, source: str = "merge", confirm_remote_differences: bool = False) -> dict[str, Any]:
        source = str(source or "merge").strip().lower()
        if source not in {"this_device", "cloud", "merge"}:
            return {"ok": False, "error": "Modo inicial inválido."}
        prior_enabled = bool(self.config.get("cloud_sync_enabled", False))

        # Resume a previously seeded activation instead of enqueueing a second
        # full snapshot with fresh event IDs. This specifically repairs the
        # 6.14.2/6.14.3 resumable case; safe activation must also release any post-recovery guard explicitly.
        if self._activation_resume_available():
            activation = self.activation_status()
            source = str(activation.get("source") or source or "merge")
            backup = {
                "path": str(activation.get("backup_path") or ""),
                "sha256": str(activation.get("backup_sha256") or ""),
                "quick_check": "ok",
                "resumed": True,
            }
            if not backup["path"] or not Path(backup["path"]).exists():
                fresh_backup = self.create_activation_backup()
                backup.update(fresh_backup)
                backup["resumed"] = True
            guard_release = self._release_recovery_guard_for_safe_activation()
            if guard_release.get("released"):
                backup["recovery_guard"] = guard_release
            self.config["cloud_sync_enabled"] = True
            with self._connect(timeout=3.0) as connection:
                self._set_runtime(connection, "activation_state", "syncing")
                self._set_runtime(connection, "activation_last_error", "")
                self._set_runtime(connection, "activation_checkpoint", "first_sync_progress")
            try:
                return self._activation_sync_chunk(source=source, backup=backup)
            finally:
                if not self.activation_completed():
                    self.config["cloud_sync_enabled"] = False if not prior_enabled else prior_enabled

        preview = self.activation_preview()
        if not preview.get("ok"):
            return {"ok": False, "stage": "preflight", "preview": preview, "error": preview.get("error") or preview.get("message")}
        if preview.get("blocking_conflicts"):
            return {"ok": False, "stage": "conflict_check", "preview": preview, "error": "Há alterações remotas não confirmadas que conflitam com a fila local. Sincronize/reconcilie antes da primeira ativação."}
        if preview.get("requires_difference_confirmation") and not confirm_remote_differences:
            return {"ok": False, "stage": "confirmation", "confirmation_required": True, "preview": preview, "error": "A nuvem e o banco local possuem diferenças. Confirme a mesclagem depois de revisar o resumo."}
        if source == "this_device" and int((preview.get("remote") or {}).get("event_count", 0) or 0) > 0:
            return {"ok": False, "stage": "source", "preview": preview, "error": "A nuvem já contém dados; use Mesclar com a nuvem para evitar sobrescrita acidental."}
        backup = self.create_activation_backup()
        guard_release = self._release_recovery_guard_for_safe_activation()
        if guard_release.get("released"):
            backup["recovery_guard"] = guard_release
        self.config["cloud_sync_enabled"] = True
        with self._connect() as connection:
            self._set_runtime(connection, "activation_state", "syncing")
            self._set_runtime(connection, "activation_checkpoint", "first_sync_started")
            self._set_runtime(connection, "activation_last_error", "")
            self._set_runtime(connection, "activation_source", source)
        try:
            remote = self.remote()
            remote.ensure_schema()
            remote_count = int(remote.event_count()) if hasattr(remote, "event_count") else int((preview.get("remote") or {}).get("event_count", 0) or 0)
            seeded = 0
            pulled_before = 0
            if source == "cloud":
                pulled_before = self.pull()
            elif source == "merge":
                if remote_count:
                    pulled_before = self.pull()
                seeded = self.enqueue_full_snapshot()
            else:
                seeded = self.enqueue_full_snapshot()
            with self._connect(timeout=3.0) as connection:
                self._set_runtime(connection, "activation_seeded_at", _utc_now())
                self._set_runtime(connection, "activation_checkpoint", "first_sync_progress")
            return self._activation_sync_chunk(
                source=source, backup=backup, preview=preview, seeded=seeded, pulled_before=pulled_before,
            )
        except Exception as error:
            self.config["cloud_sync_enabled"] = False
            with self._connect(timeout=3.0) as connection:
                self._set_runtime(connection, "activation_state", "failed")
                self._set_runtime(connection, "activation_last_error", str(error)[:1200])
                self._set_runtime(connection, "activation_checkpoint", "first_sync_failed")
            return {
                "ok": False, "completed": False, "stage": "first_sync", "error": str(error), "backup": backup,
                "preview": preview, "activation": self.activation_status(), "status": self.safe_status(),
                "retry_safe": True, "remote_writes_are_idempotent": True,
            }
        finally:
            if not self.activation_completed():
                self.config["cloud_sync_enabled"] = False if not prior_enabled else prior_enabled

    def pending_count(self) -> int:
        with self._connect(timeout=2.0) as connection:
            return int(connection.execute("SELECT COUNT(*) FROM qf_sync_outbox").fetchone()[0])

    def enqueue_full_snapshot(self) -> int:
        count = 0
        with self._connect() as connection:
            generation = max(1, int(self._runtime(connection, "generation", "1") or 1))
            for table, pk_columns in SYNC_TABLES:
                if not self._table_exists(connection, table):
                    continue
                select_columns = ",".join(f'"{column}"' for column in pk_columns)
                rows = connection.execute(f'SELECT {select_columns} FROM "{table}"').fetchall()
                for row in rows:
                    key = _row_key([row[index] for index in range(len(pk_columns))])
                    connection.execute(
                        """
                        INSERT INTO qf_sync_outbox(event_id,generation,table_name,row_key,operation,changed_at,attempts,last_error)
                        VALUES(?,?,?,?, 'upsert', ?,0,'')
                        ON CONFLICT(table_name,row_key) DO UPDATE SET event_id=excluded.event_id,
                          generation=excluded.generation,operation='upsert',changed_at=excluded.changed_at,
                          attempts=0,last_error=''
                        """,
                        (uuid.uuid4().hex, generation, table, key, _utc_now()),
                    )
                    count += 1
        return count

    def _advance_pending_events_for_generation(self, connection: sqlite3.Connection, generation: int) -> None:
        """Discard stale learning events but preserve pending editorial work.

        A study reset must never erase an offline edit to a question just because
        that edit was made before the reset on another device. Editorial events
        are therefore re-tagged to the new generation; only progress events are
        invalidated.
        """
        progress = tuple(sorted(RESET_SCOPED_TABLES))
        placeholders = ",".join("?" for _ in progress)
        connection.execute(
            f"DELETE FROM qf_sync_outbox WHERE generation < ? AND table_name IN ({placeholders})",
            (generation, *progress),
        )
        connection.execute(
            f"UPDATE qf_sync_outbox SET generation=? WHERE generation < ? AND table_name NOT IN ({placeholders})",
            (generation, generation, *progress),
        )

    def begin_global_reset(self) -> int:
        """Advance the study generation before local reset mutations are committed."""
        with self._connect() as connection:
            current = max(1, int(self._runtime(connection, "generation", "1") or 1))
            generation = current + 1
            self._set_runtime(connection, "generation", generation)
            self._advance_pending_events_for_generation(connection, generation)
            self._set_runtime(connection, "last_error", "")
            return generation

    def _table_exists(self, connection: sqlite3.Connection, table: str) -> bool:
        return bool(connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone())

    def _table_columns(self, connection: sqlite3.Connection, table: str) -> list[str]:
        return [str(row[1]) for row in connection.execute(f'PRAGMA table_info("{table}")').fetchall()]

    def _fetch_row_payload(self, connection: sqlite3.Connection, table: str, row_key: str) -> str:
        pk_columns = SYNC_TABLE_MAP[table]
        key_values = _parse_row_key(row_key)
        if len(key_values) != len(pk_columns):
            raise ValueError(f"Chave inválida para {table}.")
        where = " AND ".join(f'"{column}"=?' for column in pk_columns)
        row = connection.execute(f'SELECT * FROM "{table}" WHERE {where}', tuple(key_values)).fetchone()
        if not row:
            return "{}"
        return _stable_json(dict(row))

    def _build_events(self, limit: int = 250) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM qf_sync_outbox ORDER BY changed_at ASC LIMIT ?", (max(1, min(5000, int(limit))),)
            ).fetchall()
            items: list[dict[str, Any]] = []
            for row in rows:
                table = str(row["table_name"])
                if table not in SYNC_TABLE_MAP:
                    raise ValueError(f"Evento pendente para tabela não suportada: {table}")
                operation = str(row["operation"])
                payload_json = "{}" if operation == "delete" else self._fetch_row_payload(connection, table, str(row["row_key"]))
                # Row may have been deleted after a coalesced upsert.
                if operation == "upsert" and payload_json == "{}":
                    operation = "delete"
                item = {
                    "event_id": str(row["event_id"]),
                    "device_id": self._runtime(connection, "device_id"),
                    "generation": int(row["generation"]),
                    "table_name": table,
                    "row_key": str(row["row_key"]),
                    "operation": operation,
                    "payload_json": payload_json,
                    "created_at": str(row["changed_at"]),
                }
                item["checksum"] = _checksum(table, item["row_key"], operation, payload_json, item["generation"])
                items.append(item)
        items.sort(key=lambda item: (int(item["generation"]), TABLE_RANK.get(item["table_name"], 999), item["created_at"]))
        return items

    def _mark_events_uploaded(self, event_ids: Iterable[str]) -> None:
        values = [str(item) for item in event_ids]
        if not values:
            return
        with self._connect() as connection:
            connection.executemany("DELETE FROM qf_sync_outbox WHERE event_id=?", ((item,) for item in values))

    def _mark_push_error(self, event_ids: Iterable[str], message: str) -> None:
        values = [str(item) for item in event_ids]
        if not values:
            return
        with self._connect() as connection:
            connection.executemany(
                "UPDATE qf_sync_outbox SET attempts=attempts+1,last_error=? WHERE event_id=?",
                ((str(message)[:1000], item) for item in values),
            )

    def push(self, *, limit: int = 250) -> int:
        events = self._build_events(limit=limit)
        if not events:
            return 0
        remote = self.remote()
        try:
            remote.append_events(events)
        except Exception as error:
            self._mark_push_error((item["event_id"] for item in events), str(error))
            raise
        # Event IDs are UNIQUE remotely, so deleting only after a successful response
        # makes retry safe even if a process died after the server commit.
        self._mark_events_uploaded(item["event_id"] for item in events)
        return len(events)

    def _record_conflict(
        self,
        connection: sqlite3.Connection,
        event: dict[str, Any],
        local_event_id: str,
    ) -> None:
        connection.execute(
            """
            INSERT OR IGNORE INTO qf_sync_conflicts(id,event_id,table_name,row_key,local_event_id,detected_at,detail)
            VALUES(?,?,?,?,?,?,?)
            """,
            (
                uuid.uuid4().hex, str(event["event_id"]), str(event["table_name"]), str(event["row_key"]),
                str(local_event_id), _utc_now(),
                "Alteração remota aplicada; a alteração local pendente foi preservada e será reenviada.",
            ),
        )

    def _apply_event(self, connection: sqlite3.Connection, event: dict[str, Any]) -> None:
        table = str(event["table_name"])
        if table not in SYNC_TABLE_MAP or not self._table_exists(connection, table):
            return
        operation = str(event["operation"])
        pk_columns = SYNC_TABLE_MAP[table]
        key_values = _parse_row_key(str(event["row_key"]))
        if len(key_values) != len(pk_columns):
            return
        if operation == "delete":
            where = " AND ".join(f'"{column}"=?' for column in pk_columns)
            connection.execute(f'DELETE FROM "{table}" WHERE {where}', tuple(key_values))
            return
        payload = json.loads(str(event.get("payload_json") or "{}"), object_hook=_json_object_hook)
        if not isinstance(payload, dict) or not payload:
            return

        # Catalog learner progress is monotonic and must not use generic
        # last-write-wins. A remote snapshot can add evidence but cannot erase
        # locally known study simply because a source sheet had blank cells.
        if table == "course_learner_state" and operation == "upsert":
            lesson_key = str(payload.get("lesson_key") or (key_values[0] if key_values else ""))
            existing = connection.execute(
                "SELECT * FROM course_learner_state WHERE lesson_key=?", (lesson_key,)
            ).fetchone()
            if existing:
                try:
                    local_evidence = set(json.loads(str(existing["evidence_json"] or "[]")))
                except Exception:
                    local_evidence = set()
                try:
                    remote_evidence = set(json.loads(str(payload.get("evidence_json") or "[]")))
                except Exception:
                    remote_evidence = set()
                questions = max(int(existing["questions_done"] or 0), int(payload.get("questions_done", 0) or 0))
                hits = max(int(existing["correct_answers"] or 0), int(payload.get("correct_answers", 0) or 0))
                performance = (100.0 * hits / questions) if questions > 0 else max(float(existing["performance"] or 0), float(payload.get("performance", 0) or 0))
                payload.update({
                    "lesson_key": lesson_key,
                    "studied": 1 if bool(existing["studied"]) or bool(payload.get("studied")) else 0,
                    "study_date": str(existing["study_date"] or payload.get("study_date") or ""),
                    "effective_minutes": max(int(existing["effective_minutes"] or 0), int(payload.get("effective_minutes", 0) or 0)),
                    "questions_done": questions,
                    "correct_answers": hits,
                    "performance": performance,
                    "evidence_json": json.dumps(sorted(local_evidence | remote_evidence), ensure_ascii=False),
                    "first_observed_at": min([x for x in (str(existing["first_observed_at"] or ""), str(payload.get("first_observed_at") or "")) if x] or [str(existing["first_observed_at"] or "")]),
                    "updated_at": max(str(existing["updated_at"] or ""), str(payload.get("updated_at") or "")),
                })

        allowed = set(self._table_columns(connection, table))
        row = {str(key): value for key, value in payload.items() if str(key) in allowed}
        for column, value in zip(pk_columns, key_values):
            row.setdefault(column, value)
        if not row or any(column not in row for column in pk_columns):
            return
        columns = list(row)
        placeholders = ",".join("?" for _ in columns)
        quoted = ",".join(f'"{column}"' for column in columns)
        update_columns = [column for column in columns if column not in pk_columns]
        conflict = ",".join(f'"{column}"' for column in pk_columns)
        if update_columns:
            updates = ",".join(f'"{column}"=excluded."{column}"' for column in update_columns)
            sql = f'INSERT INTO "{table}"({quoted}) VALUES({placeholders}) ON CONFLICT({conflict}) DO UPDATE SET {updates}'
        else:
            sql = f'INSERT OR IGNORE INTO "{table}"({quoted}) VALUES({placeholders})'
        connection.execute(sql, tuple(row[column] for column in columns))

    def _apply_remote_generation(self, remote_generation: int) -> None:
        local_generation = self.generation()
        if remote_generation <= local_generation:
            return
        # Suppression is durable across connections, so the domain reset callback
        # cannot accidentally enqueue a complete stale-reset echo.
        with self._connect() as connection:
            self._set_runtime(connection, "suppress", "1")
            self._set_runtime(connection, "generation", remote_generation)
            self._advance_pending_events_for_generation(connection, remote_generation)
        try:
            if self.reset_callback is not None:
                self.reset_callback()
        finally:
            with self._connect() as connection:
                self._set_runtime(connection, "suppress", "0")
                self._set_runtime(connection, "generation", remote_generation)

    def pull(self, *, limit: int = 500) -> int:
        remote = self.remote()
        remote_generation = int(remote.get_generation())
        self._apply_remote_generation(remote_generation)
        applied_total = 0
        while True:
            with self._connect() as connection:
                after_seq = int(self._runtime(connection, "last_remote_seq", "0") or 0)
                generation = max(1, int(self._runtime(connection, "generation", "1") or 1))
                device_id = self._runtime(connection, "device_id")
            events = list(remote.fetch_events(after_seq, generation, limit=limit))
            if not events:
                break
            with self._connect() as connection:
                self._set_runtime(connection, "suppress", "1")
                try:
                    connection.execute("PRAGMA defer_foreign_keys=ON")
                    for event in events:
                        seq = int(event.get("seq", 0) or 0)
                        event_id = str(event.get("event_id", ""))
                        if not event_id:
                            continue
                        already = connection.execute("SELECT 1 FROM qf_sync_inbox WHERE event_id=?", (event_id,)).fetchone()
                        if already:
                            self._set_runtime(connection, "last_remote_seq", max(seq, int(self._runtime(connection, "last_remote_seq", "0") or 0)))
                            continue
                        expected = _checksum(
                            str(event.get("table_name", "")), str(event.get("row_key", "")),
                            str(event.get("operation", "")), str(event.get("payload_json", "")),
                            int(event.get("generation", generation) or generation),
                        )
                        if expected != str(event.get("checksum", "")):
                            raise ValueError(f"Evento remoto {event_id} falhou na verificação de integridade.")
                        event_table = str(event.get("table_name", ""))
                        event_generation = int(event.get("generation", 1) or 1)
                        # Editorial history remains valid across study resets. Old
                        # learning/progress frames do not: a new device may need
                        # old question events to reconstruct its bank, but must not
                        # resurrect pre-reset progress.
                        if event_table in RESET_SCOPED_TABLES and event_generation < generation:
                            connection.execute(
                                "INSERT OR IGNORE INTO qf_sync_inbox(event_id,remote_seq,received_at) VALUES(?,?,?)",
                                (event_id, seq, _utc_now()),
                            )
                            self._set_runtime(connection, "last_remote_seq", seq)
                            continue
                        local_pending = connection.execute(
                            "SELECT event_id FROM qf_sync_outbox WHERE table_name=? AND row_key=?",
                            (str(event.get("table_name", "")), str(event.get("row_key", ""))),
                        ).fetchone()
                        if str(event.get("device_id", "")) != device_id:
                            if local_pending:
                                # Keep the local row untouched so its pending change can be
                                # pushed after this pull (rollback/replay semantics). The
                                # remote event is still acknowledged locally and audited.
                                self._record_conflict(connection, event, str(local_pending[0]))
                            else:
                                self._apply_event(connection, event)
                                applied_total += 1
                        connection.execute(
                            "INSERT OR IGNORE INTO qf_sync_inbox(event_id,remote_seq,received_at) VALUES(?,?,?)",
                            (event_id, seq, _utc_now()),
                        )
                        self._set_runtime(connection, "last_remote_seq", seq)
                    # qf_sync_inbox is a replay/deduplication safety cache, not
                    # permanent audit history. Keep a bounded tail so years of
                    # Cloud Sync cannot inflate the local SQLite file forever.
                    inbox_count = int(connection.execute("SELECT COUNT(*) FROM qf_sync_inbox").fetchone()[0])
                    if inbox_count > 12000:
                        cutoff = connection.execute(
                            "SELECT remote_seq FROM qf_sync_inbox ORDER BY remote_seq DESC LIMIT 1 OFFSET 9999"
                        ).fetchone()
                        if cutoff is not None:
                            connection.execute("DELETE FROM qf_sync_inbox WHERE remote_seq < ?", (int(cutoff[0]),))
                finally:
                    self._set_runtime(connection, "suppress", "0")
            if len(events) < limit:
                break
        return applied_total

    def sync_once(self, *, force: bool = False) -> dict[str, Any]:
        with self._lock:
            recovery_guard = self.database_path.parent / "RECOVERY_GUARD.json"
            if recovery_guard.exists():
                return {
                    "ok": False,
                    "disabled": True,
                    "recovery_guard": True,
                    "message": "Cloud Sync temporariamente pausado para proteger a base local recuperada.",
                    "status": self.safe_status(),
                }
            if not bool(self.config.get("cloud_sync_enabled", False)) and not force:
                return {"ok": False, "disabled": True, "status": self.safe_status()}
            if bool(self.config.get("cloud_sync_safe_activation_required", False)) and not self.activation_completed() and not force:
                return {
                    "ok": False, "disabled": True, "activation_required": True,
                    "message": "Conclua a ativação segura do Cloud Sync antes de enviar dados.",
                    "status": self.safe_status(),
                }
            repair = self.repair_pending_outbox()
            try:
                with self._connect(timeout=2.0) as connection:
                    self._set_runtime(connection, "last_attempt_at", _utc_now())
            except Exception:
                pass
            remote = self.remote()
            try:
                remote.ensure_schema()
                local_generation = self.generation()
                remote_generation = int(remote.get_generation())
                if remote_generation > local_generation:
                    self._apply_remote_generation(remote_generation)
                elif local_generation > remote_generation:
                    remote.set_generation(local_generation)
                remote.touch_device(self.device_id(), self.device_name())
                # Pull first to preserve pending local changes on top, then push.
                pulled = self.pull()
                pushed = self.push()
                # Pull again to receive server-order/conflict frames and writes from
                # another client that raced with our push.
                pulled += self.pull()
                with self._connect() as connection:
                    self._set_runtime(connection, "last_sync_at", _utc_now())
                    self._set_runtime(connection, "last_error", "")
                    self._set_runtime(connection, "last_error_at", "")
                    self._set_runtime(connection, "last_push_count", pushed)
                    self._set_runtime(connection, "last_pull_count", pulled)
                return {"ok": True, "pushed": pushed, "pulled": pulled, "repaired": repair, "status": self.safe_status()}
            except Exception as error:
                try:
                    with self._connect(timeout=2.0) as connection:
                        self._set_runtime(connection, "last_error", str(error)[:1200])
                        self._set_runtime(connection, "last_error_at", _utc_now())
                except Exception:
                    pass
                return {"ok": False, "error": str(error), "status": self.safe_status()}

    def sync_until_idle(self, *, max_rounds: int = 8, max_seconds: float = 45.0, force: bool = False) -> dict[str, Any]:
        """Drain the outbox in bounded rounds and stop visibly if no progress is possible."""
        started = time.monotonic()
        total_push = total_pull = repaired_total = rounds = 0
        previous_pending: int | None = None
        last_result: dict[str, Any] = {}
        while rounds < max(1, int(max_rounds)) and time.monotonic() - started < max(2.0, float(max_seconds)):
            rounds += 1
            before = self.pending_count()
            result = self.sync_once(force=force)
            last_result = result
            total_push += int(result.get("pushed", 0) or 0)
            total_pull += int(result.get("pulled", 0) or 0)
            repaired_total += int((result.get("repaired") or {}).get("repaired", 0) or 0)
            after = self.pending_count()
            if not result.get("ok") or after == 0:
                break
            if after >= before and previous_pending == after:
                break
            previous_pending = after
        status = self.safe_status()
        pending = int(status.get("pending", 0) or 0)
        error = str(last_result.get("error", "") or status.get("last_error", ""))
        blocked_message = ""
        if last_result and not last_result.get("ok") and not error:
            blocked_message = str(last_result.get("message") or "").strip()
            if last_result.get("recovery_guard") and not blocked_message:
                blocked_message = "Cloud Sync pausado pelo RECOVERY_GUARD.json até reconciliação explícita."
        return {
            "ok": not error and not blocked_message and pending == 0, "pushed": total_push, "pulled": total_pull,
            "rounds": rounds, "repaired": repaired_total, "pending": pending, "status": status,
            "error": error or blocked_message,
            "recovery_guard": bool(last_result.get("recovery_guard")) if last_result else False,
            "disabled": bool(last_result.get("disabled")) if last_result else False,
            "message": blocked_message,
            "stalled": bool(pending and not error and not blocked_message and total_push == 0 and repaired_total == 0),
        }

    def prepare_remote(self, *, source: str = "merge") -> dict[str, Any]:
        """Prepare Turso and choose how the first device populates the cloud.

        source='this_device': seed every current synchronized row, then push.
        source='cloud': do not seed local rows; only pull from remote.
        source='merge': seed local rows and also pull remote events.
        """
        source = str(source or "merge").strip().lower()
        if source not in {"this_device", "cloud", "merge"}:
            raise ValueError("Modo inicial inválido.")
        remote = self.remote()
        remote.ensure_schema()
        remote_count = int(remote.event_count())
        seeded = 0
        if source == "this_device" and remote_count:
            raise ValueError(
                "A nuvem já contém dados. Para evitar sobrescrever outro computador, use 'Mesclar com a nuvem'."
            )
        if source == "cloud":
            pulled = self.pull()
            result = {"ok": True, "pushed": 0, "pulled": pulled, "status": self.safe_status()}
        elif source == "merge":
            # Cloud wins existing keys during first reconciliation because the
            # pre-existing local database has no outbox history yet. Local-only
            # rows are retained, then a snapshot publishes the union.
            if remote_count:
                self.pull()
            seeded = self.enqueue_full_snapshot()
            result = self.sync_once() if bool(self.config.get("cloud_sync_enabled", False)) else {"ok": True}
        else:  # this_device on an empty cloud
            seeded = self.enqueue_full_snapshot()
            result = self.sync_once() if bool(self.config.get("cloud_sync_enabled", False)) else {"ok": True}
        return {"ok": bool(result.get("ok", True)), "remote_events_before": remote_count, "seeded": seeded, "mode": source, "sync": result}

    def test_remote(self) -> dict[str, Any]:
        remote = self.remote()
        return remote.test()

    def clear_conflicts(self) -> int:
        with self._connect() as connection:
            count = int(connection.execute("SELECT COUNT(*) FROM qf_sync_conflicts").fetchone()[0])
            connection.execute("DELETE FROM qf_sync_conflicts")
            return count


class CloudSyncService:
    """Background scheduler supervisionado. Toda operação de rede é best-effort e limitada."""

    def __init__(self, engine: CloudSyncEngine) -> None:
        self.engine = engine
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._thread: threading.Thread | None = None
        self._state_lock = threading.RLock()
        self._last_heartbeat = 0.0
        self._last_attempt = 0.0
        self._last_success = 0.0
        self._last_error = ""
        self._sync_in_progress = False
        self._restart_count = 0
        self._consecutive_failures = 0
        self._retry_delay_seconds = 0.0

    def _heartbeat(self) -> None:
        with self._state_lock:
            self._last_heartbeat = time.monotonic()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._wake.clear()
        self._heartbeat()
        self._thread = threading.Thread(target=self._run, daemon=True, name="questflow-cloud-sync")
        self._thread.start()

    def wake(self) -> None:
        self._wake.set()

    def _run(self) -> None:
        first = True
        next_sync = time.monotonic()
        while not self._stop.is_set():
            self._heartbeat()
            interval = max(10, min(900, int(self.engine.config.get("cloud_sync_interval_seconds", 30) or 30)))
            now = time.monotonic()
            database_path = getattr(self.engine, "database_path", None)
            recovery_guard_active = bool(database_path) and (Path(database_path).parent / "RECOVERY_GUARD.json").exists()
            auto_allowed = self.engine.auto_sync_allowed() if hasattr(self.engine, "auto_sync_allowed") else bool(self.engine.config.get("cloud_sync_enabled", False))
            enabled = bool(auto_allowed) and not recovery_guard_active
            should_sync = enabled and now >= next_sync and (not first or bool(self.engine.config.get("cloud_sync_on_start", True)))
            if should_sync:
                with self._state_lock:
                    self._sync_in_progress = True
                    self._last_attempt = time.monotonic()
                try:
                    result = self.engine.sync_until_idle(max_rounds=4, max_seconds=25.0)
                    with self._state_lock:
                        if result.get("ok") or (not result.get("error") and int(result.get("pending", 0) or 0) == 0):
                            self._last_success = time.monotonic()
                            self._last_error = ""
                            self._consecutive_failures = 0
                            self._retry_delay_seconds = 0.0
                        else:
                            self._last_error = str(result.get("error") or result.get("status", {}).get("last_error") or "Sincronização incompleta.")[:1000]
                            self._consecutive_failures += 1
                            base = max(2, int(self.engine.config.get("cloud_sync_retry_base_seconds", 5) or 5))
                            ceiling = max(base, int(self.engine.config.get("cloud_sync_retry_max_seconds", 300) or 300))
                            self._retry_delay_seconds = float(min(ceiling, base * (2 ** max(0, self._consecutive_failures - 1))))
                except Exception as error:
                    with self._state_lock:
                        self._last_error = str(error)[:1000]
                        self._consecutive_failures += 1
                        base = max(2, int(self.engine.config.get("cloud_sync_retry_base_seconds", 5) or 5))
                        ceiling = max(base, int(self.engine.config.get("cloud_sync_retry_max_seconds", 300) or 300))
                        self._retry_delay_seconds = float(min(ceiling, base * (2 ** max(0, self._consecutive_failures - 1))))
                finally:
                    with self._state_lock:
                        self._sync_in_progress = False
                    self._heartbeat()
                with self._state_lock:
                    retry_delay = self._retry_delay_seconds
                next_sync = time.monotonic() + (retry_delay if retry_delay > 0 else interval)
            elif not enabled:
                next_sync = time.monotonic() + interval
            elif first and not bool(self.engine.config.get("cloud_sync_on_start", True)):
                next_sync = time.monotonic() + interval
            first = False
            # Heartbeat remains fresh even with a 15-minute sync interval.
            self._wake.wait(timeout=min(2.0, max(0.2, next_sync - time.monotonic())))
            if self._wake.is_set():
                self._wake.clear()
                next_sync = time.monotonic()

    def health(self) -> dict[str, Any]:
        with self._state_lock:
            alive = bool(self._thread and self._thread.is_alive())
            age = max(0.0, time.monotonic() - self._last_heartbeat) if self._last_heartbeat else 9999.0
            in_progress = self._sync_in_progress
            last_error = self._last_error
            attempt_age = max(0.0, time.monotonic() - self._last_attempt) if self._last_attempt else None
            success_age = max(0.0, time.monotonic() - self._last_success) if self._last_success else None
        enabled = self.engine.auto_sync_allowed() if hasattr(self.engine, "auto_sync_allowed") else bool(self.engine.config.get("cloud_sync_enabled", False))
        if not enabled:
            state = "disabled"
            ok = True
        elif not alive or age > 8.0:
            state = "degraded"
            ok = False
        elif last_error:
            # Falta de internet é estado degradado do canal, não falha do processo.
            lowered = last_error.casefold()
            if any(token in lowered for token in ("sem conexão", "offline", "expirou", "timeout", "proxy")):
                state = "offline"
                ok = True
            else:
                state = "degraded"
                ok = False
        else:
            state = "healthy"
            ok = True
        try:
            status = self.engine.safe_status()
        except Exception:
            status = {}
        return {
            "ok": ok, "state": state, "thread_alive": alive,
            "heartbeat_age_seconds": round(age, 3), "sync_in_progress": in_progress,
            "last_attempt_age_seconds": round(attempt_age, 2) if attempt_age is not None else None,
            "last_success_age_seconds": round(success_age, 2) if success_age is not None else None,
            "last_error": last_error, "pending": int(status.get("pending", 0) or 0),
            "conflicts": int(status.get("conflicts", 0) or 0), "restarts": self._restart_count,
            "consecutive_failures": self._consecutive_failures,
            "retry_delay_seconds": round(self._retry_delay_seconds, 2),
            "activation": status.get("activation", {}),
        }

    def restart(self) -> dict[str, Any]:
        self._restart_count += 1
        self.stop(flush=False, timeout=3.0)
        self._stop.clear()
        self.start()
        return {"ok": True, "health": self.health()}

    def stop(self, *, flush: bool = True, timeout: float = 8.0) -> dict[str, Any] | None:
        self._stop.set()
        self._wake.set()
        thread = self._thread
        if thread and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=max(0.2, timeout / 2))
        if thread and thread.is_alive():
            return {
                "ok": False,
                "in_progress": True,
                "deferred": True,
                "message": "Sincronização ainda em andamento; alterações pendentes permanecem seguras no banco local.",
                "status": self.engine.safe_status(),
            }
        auto_allowed = self.engine.auto_sync_allowed() if hasattr(self.engine, "auto_sync_allowed") else bool(self.engine.config.get("cloud_sync_enabled", False))
        if flush and auto_allowed and bool(self.engine.config.get("cloud_sync_on_shutdown", True)):
            return self.engine.sync_once()
        return None


__all__ = [
    "CLOUD_CREDENTIAL_FILENAME",
    "CloudSyncEngine",
    "CloudSyncService",
    "SYNC_SCHEMA_VERSION",
    "SYNC_TABLES",
    "TursoHttpClient",
    "TursoHttpError",
    "clear_turso_token",
    "load_turso_token",
    "normalize_turso_url",
    "save_turso_token",
    "turso_pipeline_url",
]
