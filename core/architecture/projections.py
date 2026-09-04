from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Iterable


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


@dataclass(frozen=True, slots=True)
class ProjectionDefinition:
    name: str
    owner: str
    source_streams: tuple[str, ...]
    rebuild: Callable[[], Any]
    target_tables: tuple[str, ...] = ()


class ProjectionCatalog:
    """Catálogo e executor de projeções reconstruíveis."""

    def __init__(self, database: Any, definitions: Iterable[ProjectionDefinition] = ()) -> None:
        self.database = database
        self._definitions: dict[str, ProjectionDefinition] = {}
        self.initialize()
        for definition in definitions:
            self.register(definition)

    def initialize(self) -> None:
        with self.database.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS qf_projection_checkpoints (
                    projection_name TEXT PRIMARY KEY,
                    owner_module TEXT NOT NULL,
                    source_streams TEXT NOT NULL,
                    rebuilt_at TEXT,
                    last_position INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'pending',
                    last_error TEXT NOT NULL DEFAULT ''
                );
                """
            )

    def register(self, definition: ProjectionDefinition) -> None:
        if definition.name in self._definitions:
            raise ValueError(f"Projeção já registrada: {definition.name}")
        self._definitions[definition.name] = definition
        with self.database.connect() as connection:
            connection.execute(
                """INSERT INTO qf_projection_checkpoints(
                    projection_name,owner_module,source_streams,status
                ) VALUES(?,?,?,'pending')
                ON CONFLICT(projection_name) DO UPDATE SET
                    owner_module=excluded.owner_module,source_streams=excluded.source_streams""",
                (definition.name, definition.owner, ",".join(definition.source_streams)),
            )

    def names(self) -> tuple[str, ...]:
        return tuple(self._definitions)

    def rebuild(self, name: str) -> dict[str, Any]:
        definition = self._definitions.get(str(name))
        if definition is None:
            raise KeyError(f"Projeção não registrada: {name}")
        try:
            result = definition.rebuild()
        except Exception as error:
            with self.database.connect() as connection:
                connection.execute(
                    "UPDATE qf_projection_checkpoints SET status='error',last_error=? WHERE projection_name=?",
                    (str(error)[:1000], definition.name),
                )
            raise
        timestamp = _utc_now()
        with self.database.connect() as connection:
            position = int(connection.execute("SELECT COALESCE(MAX(global_position),0) FROM qf_event_store").fetchone()[0])
            connection.execute(
                """UPDATE qf_projection_checkpoints
                   SET rebuilt_at=?,last_position=?,status='ready',last_error=''
                   WHERE projection_name=?""",
                (timestamp, position, definition.name),
            )
        return {"name": definition.name, "rebuilt_at": timestamp, "last_position": position, "result": result}

    def rebuild_all(self) -> dict[str, Any]:
        results: list[dict[str, Any]] = []
        for name in self.names():
            results.append(self.rebuild(name))
        return {"ok": True, "count": len(results), "projections": results}

    def status(self) -> list[dict[str, Any]]:
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM qf_projection_checkpoints ORDER BY projection_name"
            ).fetchall()
        return [dict(row) for row in rows]


__all__ = ["ProjectionCatalog", "ProjectionDefinition"]
