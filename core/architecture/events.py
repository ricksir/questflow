from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Iterable


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


@dataclass(frozen=True, slots=True)
class DomainEvent:
    event_type: str
    module: str
    payload: dict[str, Any]
    aggregate_type: str = ""
    aggregate_id: str = ""
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    occurred_at: str = field(default_factory=_utc_now)
    correlation_id: str = ""
    causation_id: str = ""
    schema_version: int = 1


class InternalEventBus:
    """Barramento síncrono com outbox durável no SQLite compartilhado."""

    def __init__(self, database: Any) -> None:
        self.database = database
        self._handlers: dict[str, list[Callable[[DomainEvent], Any]]] = {}
        self._lock = threading.RLock()
        self.initialize()

    def initialize(self) -> None:
        with self.database.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS qf_internal_events (
                    event_id TEXT PRIMARY KEY,
                    event_type TEXT NOT NULL,
                    source_module TEXT NOT NULL,
                    aggregate_type TEXT NOT NULL DEFAULT '',
                    aggregate_id TEXT NOT NULL DEFAULT '',
                    payload_json TEXT NOT NULL,
                    occurred_at TEXT NOT NULL,
                    correlation_id TEXT NOT NULL DEFAULT '',
                    causation_id TEXT NOT NULL DEFAULT '',
                    schema_version INTEGER NOT NULL DEFAULT 1,
                    dispatch_status TEXT NOT NULL DEFAULT 'pending',
                    dispatched_at TEXT,
                    last_error TEXT NOT NULL DEFAULT ''
                );
                CREATE INDEX IF NOT EXISTS idx_qf_internal_events_pending
                    ON qf_internal_events(dispatch_status, occurred_at);
                """
            )

    def install_capture_triggers(self) -> list[str]:
        """Conecta fontes canônicas existentes ao event store sem duplicá-las.

        Os triggers são somente de INSERT: estados FSRS/KT/IRT continuam sendo
        projeções e nunca viram eventos por sofrerem UPDATE.
        """
        installed: list[str] = []
        with self.database.connect() as connection:
            tables = {str(row[0]) for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()}
            if "telegram_attempts" in tables:
                connection.executescript(
                    """
                    CREATE TRIGGER IF NOT EXISTS qf_es_telegram_attempts_ai
                    AFTER INSERT ON telegram_attempts
                    BEGIN
                      INSERT OR IGNORE INTO qf_event_store(
                        event_id,stream_type,stream_id,stream_version,event_type,payload_json,metadata_json,occurred_at
                      ) VALUES(
                        'attempt:' || NEW.id,'attempt',NEW.id,1,'attempt.recorded',
                        json_object(
                          'attempt_id',NEW.id,'delivery_id',NEW.delivery_id,'question_uid',NEW.question_uid,
                          'user_id',NEW.user_id,'selected_indices_json',NEW.selected_indices_json,
                          'is_correct',NEW.is_correct,'answered_at',NEW.answered_at
                        ),json_object('source_table','telegram_attempts'),NEW.answered_at
                      );
                    END;
                    """
                )
                installed.append("telegram_attempts")
            if "qf_learning_events" in tables:
                connection.executescript(
                    """
                    CREATE TRIGGER IF NOT EXISTS qf_es_learning_events_ai
                    AFTER INSERT ON qf_learning_events
                    BEGIN
                      INSERT OR IGNORE INTO qf_event_store(
                        event_id,stream_type,stream_id,stream_version,event_type,payload_json,metadata_json,occurred_at
                      ) VALUES(
                        'learning:' || NEW.event_id,'learning',
                        COALESCE(NULLIF(NEW.attempt_id,''),NULLIF(NEW.session_id,''),NEW.event_id),
                        NEW.seq,NEW.event_type,NEW.payload_json,
                        json_object(
                          'source_table','qf_learning_events','device_id',NEW.device_id,
                          'question_uid',NEW.question_uid,'schema_version',NEW.schema_version
                        ),NEW.occurred_at
                      );
                    END;
                    """
                )
                installed.append("qf_learning_events")
            if "learner_model_events" in tables:
                connection.executescript(
                    """
                    CREATE TRIGGER IF NOT EXISTS qf_es_learner_model_events_ai
                    AFTER INSERT ON learner_model_events
                    BEGIN
                      INSERT OR IGNORE INTO qf_event_store(
                        event_id,stream_type,stream_id,stream_version,event_type,payload_json,metadata_json,occurred_at
                      ) VALUES(
                        'learner-model:' || NEW.attempt_id,'learning',NEW.attempt_id,1,'learner_model.updated',
                        json_object(
                          'attempt_id',NEW.attempt_id,'question_uid',NEW.question_uid,
                          'subject',NEW.subject,'is_correct',NEW.is_correct,
                          'mastery_after',NEW.mastery_after,'theta_after',NEW.theta_after,
                          'item_difficulty_after',NEW.item_difficulty_after,
                          'item_information',NEW.item_information,'model_version',NEW.model_version
                        ),json_object('source_table','learner_model_events'),NEW.created_at
                      );
                    END;
                    """
                )
                installed.append("learner_model_events")
            if "qf_ai_interactions" in tables:
                connection.executescript(
                    """
                    CREATE TRIGGER IF NOT EXISTS qf_es_ai_interactions_ai
                    AFTER INSERT ON qf_ai_interactions
                    BEGIN
                      INSERT OR IGNORE INTO qf_event_store(
                        event_id,stream_type,stream_id,stream_version,event_type,payload_json,metadata_json,occurred_at
                      ) VALUES(
                        'ai-audit:' || NEW.id,'ai_audit',NEW.id,1,'ai.interaction.recorded',
                        json_object(
                          'interaction_id',NEW.id,'question_uid',NEW.question_uid,
                          'interaction_type',NEW.interaction_type,'provider',NEW.provider,
                          'model',NEW.model,'prompt_sha256',NEW.prompt_sha256,'status',NEW.status
                        ),json_object('source_table','qf_ai_interactions'),NEW.created_at
                      );
                    END;
                    """
                )
                installed.append("qf_ai_interactions")
            if "qf_sync_events" in tables:
                connection.executescript(
                    """
                    CREATE TRIGGER IF NOT EXISTS qf_es_sync_events_ai
                    AFTER INSERT ON qf_sync_events
                    BEGIN
                      INSERT OR IGNORE INTO qf_event_store(
                        event_id,stream_type,stream_id,stream_version,event_type,payload_json,metadata_json,occurred_at
                      ) VALUES(
                        'sync:' || NEW.event_id,'sync',NEW.event_id,1,'sync.change.recorded',
                        NEW.payload_json,
                        json_object(
                          'source_table','qf_sync_events','device_id',NEW.device_id,
                          'generation',NEW.generation,'table_name',NEW.table_name,
                          'row_key',NEW.row_key,'operation',NEW.operation,'checksum',NEW.checksum
                        ),NEW.created_at
                      );
                    END;
                    """
                )
                installed.append("qf_sync_events")
        return installed

    def subscribe(self, event_type: str, handler: Callable[[DomainEvent], Any]) -> None:
        with self._lock:
            self._handlers.setdefault(str(event_type), []).append(handler)

    def publish(self, event: DomainEvent, *, dispatch: bool = True) -> DomainEvent:
        payload_json = json.dumps(event.payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO qf_internal_events(
                    event_id,event_type,source_module,aggregate_type,aggregate_id,payload_json,
                    occurred_at,correlation_id,causation_id,schema_version
                ) VALUES(?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    event.event_id, event.event_type, event.module, event.aggregate_type,
                    event.aggregate_id, payload_json, event.occurred_at, event.correlation_id,
                    event.causation_id, int(event.schema_version),
                ),
            )
        if dispatch:
            self._dispatch(event)
        return event

    def _dispatch(self, event: DomainEvent) -> None:
        handlers = [*self._handlers.get(event.event_type, ()), *self._handlers.get("*", ())]
        try:
            for handler in handlers:
                handler(event)
        except Exception as error:
            with self.database.connect() as connection:
                connection.execute(
                    "UPDATE qf_internal_events SET dispatch_status='error',last_error=? WHERE event_id=?",
                    (str(error)[:1000], event.event_id),
                )
            raise
        with self.database.connect() as connection:
            connection.execute(
                """UPDATE qf_internal_events
                   SET dispatch_status='dispatched',dispatched_at=?,last_error=''
                   WHERE event_id=?""",
                (_utc_now(), event.event_id),
            )

    def pending(self, limit: int = 100) -> list[DomainEvent]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """SELECT * FROM qf_internal_events WHERE dispatch_status IN ('pending','error')
                   ORDER BY occurred_at,event_id LIMIT ?""",
                (max(1, min(1000, int(limit))),),
            ).fetchall()
        return [self._from_row(row) for row in rows]

    def drain(self, limit: int = 100) -> dict[str, int]:
        sent = failed = 0
        for event in self.pending(limit):
            try:
                self._dispatch(event)
                sent += 1
            except Exception:
                failed += 1
        return {"dispatched": sent, "failed": failed}

    @staticmethod
    def _from_row(row: sqlite3.Row) -> DomainEvent:
        return DomainEvent(
            event_id=str(row["event_id"]), event_type=str(row["event_type"]),
            module=str(row["source_module"]), payload=json.loads(str(row["payload_json"] or "{}")),
            aggregate_type=str(row["aggregate_type"] or ""), aggregate_id=str(row["aggregate_id"] or ""),
            occurred_at=str(row["occurred_at"]), correlation_id=str(row["correlation_id"] or ""),
            causation_id=str(row["causation_id"] or ""), schema_version=int(row["schema_version"] or 1),
        )


class SelectiveEventStore:
    """Event store limitado aos fluxos que exigem replay/auditoria completa."""

    ALLOWED_STREAMS = frozenset({"attempt", "learning", "sync", "ai_audit"})

    def __init__(self, database: Any) -> None:
        self.database = database
        self.initialize()

    def initialize(self) -> None:
        with self.database.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS qf_event_store (
                    global_position INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT NOT NULL UNIQUE,
                    stream_type TEXT NOT NULL CHECK(stream_type IN ('attempt','learning','sync','ai_audit')),
                    stream_id TEXT NOT NULL,
                    stream_version INTEGER NOT NULL,
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    occurred_at TEXT NOT NULL,
                    UNIQUE(stream_type,stream_id,stream_version)
                );
                CREATE INDEX IF NOT EXISTS idx_qf_event_store_stream
                    ON qf_event_store(stream_type,stream_id,stream_version);
                """
            )
        self.install_capture_triggers()

    def install_capture_triggers(self) -> list[str]:
        # O instalador é compartilhado com o barramento para manter em um único
        # lugar o SQL de captura; ele depende apenas de ``self.database``.
        return InternalEventBus.install_capture_triggers(self)

    def append(
        self,
        stream_type: str,
        stream_id: str,
        event_type: str,
        payload: dict[str, Any],
        *,
        metadata: dict[str, Any] | None = None,
        expected_version: int | None = None,
        event_id: str | None = None,
        occurred_at: str | None = None,
    ) -> dict[str, Any]:
        stream_type = str(stream_type or "").strip()
        if stream_type not in self.ALLOWED_STREAMS:
            raise ValueError(
                "Event sourcing é permitido apenas para tentativas, aprendizagem, sincronização e auditoria de IA."
            )
        stream_id = str(stream_id or "").strip()
        if not stream_id:
            raise ValueError("stream_id é obrigatório.")
        with self.database.connect() as connection:
            current = int(connection.execute(
                "SELECT COALESCE(MAX(stream_version),0) FROM qf_event_store WHERE stream_type=? AND stream_id=?",
                (stream_type, stream_id),
            ).fetchone()[0])
            if expected_version is not None and current != int(expected_version):
                raise RuntimeError(f"Concorrência no stream {stream_type}/{stream_id}: esperado {expected_version}, atual {current}.")
            version = current + 1
            item_id = str(event_id or uuid.uuid4())
            timestamp = str(occurred_at or _utc_now())
            connection.execute(
                """INSERT INTO qf_event_store(
                    event_id,stream_type,stream_id,stream_version,event_type,payload_json,metadata_json,occurred_at
                ) VALUES(?,?,?,?,?,?,?,?)""",
                (
                    item_id, stream_type, stream_id, version, str(event_type),
                    json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                    json.dumps(metadata or {}, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                    timestamp,
                ),
            )
        return {"event_id": item_id, "stream_type": stream_type, "stream_id": stream_id, "version": version, "occurred_at": timestamp}

    def read(self, stream_type: str, stream_id: str, *, after_version: int = 0) -> list[dict[str, Any]]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """SELECT * FROM qf_event_store
                   WHERE stream_type=? AND stream_id=? AND stream_version>?
                   ORDER BY stream_version""",
                (str(stream_type), str(stream_id), max(0, int(after_version))),
            ).fetchall()
        return [
            {
                "position": int(row["global_position"]), "event_id": str(row["event_id"]),
                "stream_type": str(row["stream_type"]), "stream_id": str(row["stream_id"]),
                "version": int(row["stream_version"]), "event_type": str(row["event_type"]),
                "payload": json.loads(str(row["payload_json"])),
                "metadata": json.loads(str(row["metadata_json"] or "{}")),
                "occurred_at": str(row["occurred_at"]),
            }
            for row in rows
        ]


__all__ = ["DomainEvent", "InternalEventBus", "SelectiveEventStore"]
