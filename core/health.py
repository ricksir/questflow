from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import os
import sqlite3
import time
from pathlib import Path


@dataclass(slots=True)
class HealthSnapshot:
    status: str
    database_latency_ms: float
    database_size_mb: float
    wal_size_mb: float
    pending_outbox: int
    failed_deliveries: int
    pending_corrections: int
    checked_at: str

    def to_dict(self) -> dict:
        return asdict(self)


def collect_health(database_path: str | Path) -> HealthSnapshot:
    path = Path(database_path)
    started = time.perf_counter()
    pending_outbox = failed = corrections = 0
    status = "operacional"
    try:
        connection = sqlite3.connect(path, timeout=3)
        try:
            connection.execute("SELECT 1").fetchone()
            pending_outbox = int(connection.execute(
                "SELECT COUNT(*) FROM telegram_outbox WHERE status != 'enviado'"
            ).fetchone()[0])
            failed = int(connection.execute(
                "SELECT COUNT(*) FROM telegram_deliveries WHERE status = 'erro' AND resolved_by_delivery_id IS NULL"
            ).fetchone()[0])
            corrections = int(connection.execute(
                "SELECT COUNT(*) FROM telegram_review_requests WHERE status IN ('pendente','aberta')"
            ).fetchone()[0])
        finally:
            connection.close()
    except Exception:
        status = "degradado"
    latency = (time.perf_counter() - started) * 1000.0
    if latency > 250:
        status = "atenção"
    size = path.stat().st_size / 1048576 if path.exists() else 0.0
    wal = Path(str(path) + "-wal")
    wal_size = wal.stat().st_size / 1048576 if wal.exists() else 0.0
    return HealthSnapshot(
        status=status,
        database_latency_ms=round(latency, 2),
        database_size_mb=round(size, 2),
        wal_size_mb=round(wal_size, 2),
        pending_outbox=pending_outbox,
        failed_deliveries=failed,
        pending_corrections=corrections,
        checked_at=datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    )


__all__ = ["HealthSnapshot", "collect_health"]
