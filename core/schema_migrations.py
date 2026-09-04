from __future__ import annotations

"""Migrações incrementais e auditáveis do banco QuestFlow.

As migrações são idempotentes e registradas por componente/versão. O objetivo
é substituir alterações dispersas de esquema por um histórico explícito que
possa ser inspecionado, testado e recuperado em bancos antigos.
"""

from collections.abc import Callable, Mapping
from datetime import datetime, timezone
import hashlib
import sqlite3

MigrationCallback = Callable[[sqlite3.Connection], None]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def ensure_migration_table(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            component TEXT NOT NULL,
            version INTEGER NOT NULL,
            name TEXT NOT NULL,
            checksum TEXT NOT NULL,
            applied_at TEXT NOT NULL,
            PRIMARY KEY(component, version)
        )
        """
    )


def _checksum(component: str, version: int, name: str) -> str:
    raw = f"{component}:{version}:{name}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def applied_versions(connection: sqlite3.Connection) -> dict[str, int]:
    ensure_migration_table(connection)
    rows = connection.execute(
        "SELECT component, MAX(version) AS version FROM schema_migrations GROUP BY component"
    ).fetchall()
    return {str(row[0]): int(row[1] or 0) for row in rows}


def apply_migration(
    connection: sqlite3.Connection,
    *,
    component: str,
    version: int,
    name: str,
    callback: MigrationCallback,
) -> bool:
    """Aplica uma migração uma única vez e registra o resultado.

    O callback deve ser idempotente para permitir recuperação segura de bancos
    que já possuíam parte da estrutura antes da adoção do versionamento.
    """

    ensure_migration_table(connection)
    expected = _checksum(component, version, name)
    row = connection.execute(
        "SELECT checksum FROM schema_migrations WHERE component = ? AND version = ?",
        (component, int(version)),
    ).fetchone()
    if row:
        if str(row[0]) != expected:
            raise RuntimeError(
                f"Migração {component}/{version} já registrada com checksum diferente."
            )
        return False

    callback(connection)
    connection.execute(
        """
        INSERT INTO schema_migrations(component, version, name, checksum, applied_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (component, int(version), name, expected, utc_now()),
    )
    return True


def table_columns(connection: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})").fetchall()}


def ensure_columns(
    connection: sqlite3.Connection,
    table: str,
    columns: Mapping[str, str],
) -> None:
    existing = table_columns(connection, table)
    for column, definition in columns.items():
        if column not in existing:
            connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
            existing.add(column)


def migration_history(connection: sqlite3.Connection) -> list[dict]:
    ensure_migration_table(connection)
    rows = connection.execute(
        """
        SELECT component, version, name, checksum, applied_at
        FROM schema_migrations
        ORDER BY component, version
        """
    ).fetchall()
    return [
        {
            "component": str(row[0]),
            "version": int(row[1]),
            "name": str(row[2]),
            "checksum": str(row[3]),
            "applied_at": str(row[4]),
        }
        for row in rows
    ]
