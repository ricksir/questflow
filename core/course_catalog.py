from __future__ import annotations

"""Safe course-catalog refresh with durable learner-state preservation.

The spreadsheet is a read-only content source.  Once QuestFlow has observed
personal study evidence, that evidence is persisted in SQLite and survives
future catalog snapshots whose personal cells are blank.
"""

import hashlib
import json
import os
import re
import sqlite3
import unicodedata
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .spreadsheet_taxonomy import save_taxonomy


MERGE_STRATEGY = "incremental-preserve-progress-v1"
CATALOG_SCHEMA_VERSION = 1
PROGRESS_FIELDS = (
    "data",
    "ch_efetiva_min",
    "ch_efetiva",
    "questoes_feitas",
    "acertos",
    "desempenho",
    "estudado",
    "evidencias_estudo",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def _norm(value: Any) -> str:
    text = unicodedata.normalize("NFKD", _clean(value))
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).upper()
    text = re.sub(r"[^A-Z0-9]+", "_", text).strip("_")
    # Predictable abbreviation normalization without guessing domain meaning.
    replacements = {
        "DIREITO_TRIB": "DIREITO_TRIBUTARIO",
        "DIR_TRIBUTARIO": "DIREITO_TRIBUTARIO",
        "CONTAB": "CONTABILIDADE",
    }
    return replacements.get(text, text)


def stable_lesson_key(task: dict[str, Any]) -> str:
    """Stable identity; never depends on worksheet row position."""
    parts = [task.get("trilha"), task.get("tarefa"), task.get("aula"), task.get("materia")]
    return "|".join(_norm(value) for value in parts)


def structural_lesson_key(task: dict[str, Any]) -> str:
    """Secondary identity for title/task-number drift; intentionally conservative."""
    parts = [task.get("trilha"), task.get("aula"), task.get("materia")]
    return "|".join(_norm(value) for value in parts)


def _progress_present(task: dict[str, Any]) -> bool:
    return bool(task.get("estudado")) or any(
        (
            _clean(task.get("data")),
            int(task.get("ch_efetiva_min", 0) or 0) > 0,
            int(task.get("questoes_feitas", 0) or 0) > 0,
            int(task.get("acertos", 0) or 0) > 0,
        )
    )


def _progress_from_task(task: dict[str, Any]) -> dict[str, Any]:
    evidence = [str(x) for x in task.get("evidencias_estudo", []) if _clean(x)]
    return {
        "data": _clean(task.get("data")),
        "ch_efetiva_min": max(0, int(task.get("ch_efetiva_min", 0) or 0)),
        "ch_efetiva": _clean(task.get("ch_efetiva")),
        "questoes_feitas": max(0, int(task.get("questoes_feitas", 0) or 0)),
        "acertos": max(0, int(task.get("acertos", 0) or 0)),
        "desempenho": max(0.0, float(task.get("desempenho", 0) or 0)),
        "estudado": bool(task.get("estudado")) or _progress_present(task),
        "evidencias_estudo": sorted(set(evidence)),
    }


def _merge_progress(old: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
    """Monotonic merge: blank/stale spreadsheet values never regress learner state."""
    old = dict(old or {})
    new = dict(new or {})
    merged = dict(old)
    old_date = _clean(old.get("data"))
    new_date = _clean(new.get("data"))
    merged["data"] = new_date or old_date
    for field in ("ch_efetiva_min", "questoes_feitas", "acertos"):
        merged[field] = max(int(old.get(field, 0) or 0), int(new.get(field, 0) or 0))
    # Percentage is derivative; only move it when the incoming sheet carries evidence.
    merged["desempenho"] = (
        float(new.get("desempenho", 0) or 0)
        if _progress_present(new) and float(new.get("desempenho", 0) or 0) > 0
        else float(old.get("desempenho", 0) or 0)
    )
    merged["estudado"] = bool(old.get("estudado")) or bool(new.get("estudado")) or _progress_present(old) or _progress_present(new)
    merged["evidencias_estudo"] = sorted(
        set(str(x) for x in old.get("evidencias_estudo", []) if _clean(x))
        | set(str(x) for x in new.get("evidencias_estudo", []) if _clean(x))
    )
    minutes = int(merged.get("ch_efetiva_min", 0) or 0)
    # ``course_learner_state`` persists the canonical duration in minutes; the
    # source sheet may render the same value as ``1h30``, ``01:30`` or ``90``.
    # Comparing those display strings made every background refresh look like
    # new learner evidence and recreated the complete Cloud Sync outbox.
    merged["ch_efetiva"] = f"{minutes // 60:02d}:{minutes % 60:02d}" if minutes > 0 else ""
    return merged


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temp, path)


@dataclass
class CatalogDiff:
    change_type: str
    lesson_key: str
    trail: str
    lesson: str
    subject: str
    previous_title: str = ""
    current_title: str = ""
    confidence: str = "high"
    action: str = ""
    candidates: list[dict[str, str]] | None = None


class CourseCatalogService:
    def __init__(self, database, taxonomy_path: str | Path, config_path: str | Path | None = None):
        self.database = database
        self.taxonomy_path = Path(taxonomy_path)
        self.config_path = Path(config_path) if config_path else None
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        with self.database.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS course_catalog_lessons (
                    lesson_key TEXT PRIMARY KEY,
                    structural_key TEXT NOT NULL,
                    trail TEXT,
                    task_no TEXT,
                    lesson TEXT,
                    subject TEXT,
                    title TEXT,
                    source_row INTEGER,
                    active INTEGER NOT NULL DEFAULT 1,
                    catalog_version TEXT NOT NULL,
                    source_spreadsheet TEXT,
                    structural_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_course_catalog_structural ON course_catalog_lessons(structural_key, active);
                CREATE INDEX IF NOT EXISTS idx_course_catalog_active ON course_catalog_lessons(active, trail, subject, lesson);

                CREATE TABLE IF NOT EXISTS course_learner_state (
                    lesson_key TEXT PRIMARY KEY,
                    studied INTEGER NOT NULL DEFAULT 0,
                    study_date TEXT,
                    effective_minutes INTEGER NOT NULL DEFAULT 0,
                    questions_done INTEGER NOT NULL DEFAULT 0,
                    correct_answers INTEGER NOT NULL DEFAULT 0,
                    performance REAL NOT NULL DEFAULT 0,
                    evidence_json TEXT NOT NULL DEFAULT '[]',
                    first_observed_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS course_catalog_imports (
                    id TEXT PRIMARY KEY,
                    catalog_version TEXT NOT NULL,
                    previous_source TEXT,
                    source_spreadsheet TEXT,
                    source_title TEXT,
                    imported_at TEXT NOT NULL,
                    merge_strategy TEXT NOT NULL,
                    status TEXT NOT NULL,
                    backup_path TEXT,
                    backup_sha256 TEXT,
                    quick_check TEXT,
                    foreign_key_violations INTEGER NOT NULL DEFAULT 0,
                    summary_json TEXT NOT NULL,
                    manifest_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS course_catalog_changes (
                    id TEXT PRIMARY KEY,
                    import_id TEXT NOT NULL,
                    lesson_key TEXT NOT NULL,
                    change_type TEXT NOT NULL,
                    detail_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(import_id) REFERENCES course_catalog_imports(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_course_catalog_changes_import ON course_catalog_changes(import_id, change_type);
                """
            )

    @staticmethod
    def _task_title(task: dict[str, Any]) -> str:
        return _clean(task.get("descricao"))

    @staticmethod
    def _catalog_version(payload: dict[str, Any]) -> str:
        source = dict(payload.get("source", {}) or {})
        tasks = []
        for raw in payload.get("tarefas_referencia", []):
            task = dict(raw)
            structural = {k: v for k, v in task.items() if k not in PROGRESS_FIELDS and k != "row"}
            tasks.append([stable_lesson_key(task), structural])
        material = json.dumps(
            {
                "source": source.get("spreadsheet_id") or source.get("url") or source.get("title"),
                "tasks": tasks,
            },
            ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        )
        return hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]

    def _seed_current_snapshot(self, current_payload: dict[str, Any] | None, connection: sqlite3.Connection | None = None) -> None:
        if not current_payload:
            return
        now = utc_now()
        version = self._catalog_version(current_payload)
        source = dict(current_payload.get("source", {}) or {})

        def seed(conn: sqlite3.Connection) -> None:
            for raw in current_payload.get("tarefas_referencia", []):
                task = dict(raw)
                key = stable_lesson_key(task)
                structural = structural_lesson_key(task)
                conn.execute(
                    """
                    INSERT OR IGNORE INTO course_catalog_lessons(
                        lesson_key,structural_key,trail,task_no,lesson,subject,title,source_row,active,
                        catalog_version,source_spreadsheet,structural_json,created_at,updated_at
                    ) VALUES(?,?,?,?,?,?,?,?,1,?,?,?,?,?)
                    """,
                    (
                        key, structural, _clean(task.get("trilha")), _clean(task.get("tarefa")),
                        _clean(task.get("aula")), _clean(task.get("materia")), self._task_title(task),
                        int(task.get("row", 0) or 0), version, _clean(source.get("url")),
                        json.dumps({k: v for k, v in task.items() if k not in PROGRESS_FIELDS}, ensure_ascii=False, sort_keys=True),
                        now, now,
                    ),
                )
                if _progress_present(task):
                    self._upsert_learner_state(conn, key, _progress_from_task(task), now)

        if connection is not None:
            seed(connection)
        else:
            with self.database.connect() as owned:
                seed(owned)

    def _upsert_learner_state(self, connection: sqlite3.Connection, key: str, progress: dict[str, Any], now: str) -> bool:
        row = connection.execute("SELECT * FROM course_learner_state WHERE lesson_key=?", (key,)).fetchone()
        old = {}
        if row:
            old = {
                "data": str(row["study_date"] or ""),
                "ch_efetiva_min": int(row["effective_minutes"] or 0),
                "questoes_feitas": int(row["questions_done"] or 0),
                "acertos": int(row["correct_answers"] or 0),
                "desempenho": float(row["performance"] or 0),
                "estudado": bool(row["studied"]),
                "evidencias_estudo": json.loads(str(row["evidence_json"] or "[]")),
            }
        merged = _merge_progress(old, progress)
        if row and merged == _merge_progress(old, {}):
            return False
        connection.execute(
            """
            INSERT INTO course_learner_state(
                lesson_key,studied,study_date,effective_minutes,questions_done,correct_answers,
                performance,evidence_json,first_observed_at,updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(lesson_key) DO UPDATE SET
                studied=excluded.studied,study_date=excluded.study_date,effective_minutes=excluded.effective_minutes,
                questions_done=excluded.questions_done,correct_answers=excluded.correct_answers,
                performance=excluded.performance,evidence_json=excluded.evidence_json,updated_at=excluded.updated_at
            """,
            (
                key, 1 if merged.get("estudado") else 0, _clean(merged.get("data")),
                int(merged.get("ch_efetiva_min", 0) or 0), int(merged.get("questoes_feitas", 0) or 0),
                int(merged.get("acertos", 0) or 0), float(merged.get("desempenho", 0) or 0),
                json.dumps(merged.get("evidencias_estudo", []), ensure_ascii=False), now, now,
            ),
        )
        return True

    def _current_catalog_rows(self) -> list[dict[str, Any]]:
        with self.database.connect() as connection:
            rows = connection.execute("SELECT * FROM course_catalog_lessons WHERE active=1").fetchall()
        return [dict(row) for row in rows]

    def preflight(self, new_payload: dict[str, Any], current_payload: dict[str, Any] | None = None, *, resolutions: dict[str, dict[str, str]] | None = None) -> dict[str, Any]:
        resolutions = dict(resolutions or {})
        # Dry-run is read-only. If this is the first 6.15.x import, compare
        # against the legacy taxonomy snapshot in memory instead of seeding DB.
        old_rows = self._current_catalog_rows()
        if not old_rows and current_payload:
            legacy_version = self._catalog_version(current_payload)
            legacy_source = dict(current_payload.get("source", {}) or {})
            old_rows = []
            for raw in current_payload.get("tarefas_referencia", []):
                task = dict(raw)
                old_rows.append({
                    "lesson_key": stable_lesson_key(task),
                    "structural_key": structural_lesson_key(task),
                    "trail": _clean(task.get("trilha")), "task_no": _clean(task.get("tarefa")),
                    "lesson": _clean(task.get("aula")), "subject": _clean(task.get("materia")),
                    "title": self._task_title(task), "source_row": int(task.get("row", 0) or 0),
                    "catalog_version": legacy_version, "source_spreadsheet": _clean(legacy_source.get("url")),
                })
        old_by_key = {str(r["lesson_key"]): r for r in old_rows}
        by_structural: dict[str, list[dict[str, Any]]] = {}
        for row in old_rows:
            by_structural.setdefault(str(row["structural_key"]), []).append(row)

        diffs: list[CatalogDiff] = []
        matched_old: set[str] = set()
        matches: dict[str, str] = {}
        ambiguous = 0
        for raw in new_payload.get("tarefas_referencia", []):
            task = dict(raw)
            key = stable_lesson_key(task)
            structural = structural_lesson_key(task)
            old = old_by_key.get(key)
            match_key = key
            confidence = "high"
            if old is None:
                candidates = [r for r in by_structural.get(structural, []) if str(r["lesson_key"]) not in matched_old]
                if len(candidates) == 1:
                    old = candidates[0]
                    match_key = str(old["lesson_key"])
                    confidence = "medium"
                elif len(candidates) > 1:
                    resolution = dict(resolutions.get(key, {}) or {})
                    action = str(resolution.get("action") or "").strip().lower()
                    candidate_rows = [
                        {
                            "lesson_key": str(row.get("lesson_key") or ""),
                            "trail": str(row.get("trail") or ""),
                            "task_no": str(row.get("task_no") or ""),
                            "lesson": str(row.get("lesson") or ""),
                            "subject": str(row.get("subject") or ""),
                            "title": str(row.get("title") or ""),
                        }
                        for row in candidates
                    ]
                    if action == "same":
                        selected_key = str(resolution.get("old_key") or "")
                        selected = next((row for row in candidates if str(row.get("lesson_key")) == selected_key), None)
                        if selected is not None:
                            old = selected
                            match_key = selected_key
                            confidence = "manual"
                        else:
                            action = ""
                    elif action == "new":
                        # Explicit human decision: create a new catalog lesson and never move old progress.
                        old = None
                        confidence = "manual"
                    if action not in {"same", "new"}:
                        ambiguous += 1
                        diffs.append(CatalogDiff(
                            "uncertain", key, _clean(task.get("trilha")), _clean(task.get("aula")), _clean(task.get("materia")),
                            current_title="%s" % self._task_title(task), confidence="low",
                            action="Requer decisão humana; nenhum progresso será movido automaticamente.",
                            candidates=candidate_rows,
                        ))
                        continue
            if old is None:
                diffs.append(CatalogDiff(
                    "new", key, _clean(task.get("trilha")), _clean(task.get("aula")), _clean(task.get("materia")),
                    current_title=self._task_title(task), confidence=confidence,
                    action="Adicionar como não estudada, salvo evidência explícita na nova planilha.",
                ))
                continue
            matched_old.add(match_key)
            matches[key] = match_key
            previous = _clean(old.get("title"))
            current = self._task_title(task)
            change = "updated" if previous != current or confidence == "medium" else "equal"
            diffs.append(CatalogDiff(
                change, key, _clean(task.get("trilha")), _clean(task.get("aula")), _clean(task.get("materia")),
                previous_title=previous, current_title=current, confidence=confidence,
                action="Atualizar estrutura e preservar Learner State." if change == "updated" else "Manter estrutura/progresso.",
            ))
        for old in old_rows:
            key = str(old["lesson_key"])
            if key not in matched_old:
                diffs.append(CatalogDiff(
                    "archived", key, str(old.get("trail") or ""), str(old.get("lesson") or ""), str(old.get("subject") or ""),
                    previous_title=str(old.get("title") or ""), action="Arquivar no catálogo; histórico pessoal permanece no SQLite.",
                ))
        counts = {kind: sum(1 for d in diffs if d.change_type == kind) for kind in ("equal", "updated", "new", "archived", "uncertain")}
        source = dict(new_payload.get("source", {}) or {})
        logic = dict(new_payload.get("spreadsheet_logic", {}) or {})
        return {
            "ok": ambiguous == 0,
            "catalog_version": self._catalog_version(new_payload),
            "source": source,
            "sheets": [logic.get("mapa_sheet", ""), logic.get("ciclo_sheet", "")],
            "counts": counts,
            "diffs": [asdict(item) for item in diffs],
            "matches": matches,
            "merge_strategy": MERGE_STRATEGY,
            "personal_fields_blank_overwrite": 0,
            "message": "Pronta para mesclar com preservação de progresso." if ambiguous == 0 else "Há correspondências incertas que exigem decisão humana.",
        }

    def _pedagogical_snapshot(self, connection: sqlite3.Connection) -> dict[str, int]:
        def count(table: str) -> int:
            try:
                return int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            except sqlite3.DatabaseError:
                return 0
        return {
            "questions": count("questions"),
            "fsrs_rows": count("study_state"),
            "kt_lesson_rows": count("lesson_learning_state"),
            "kt_topic_rows": count("topic_learning_state"),
            "adaptive_model_rows": count("adaptive_model_state"),
            "xp_events": count("xp_events"),
            "mobile_attempts": count("mobile_attempts"),
        }

    def _backup(self) -> dict[str, Any]:
        backup_dir = self.database.path.parent / "backups" / "course_catalog"
        backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        target = backup_dir / f"QuestFlow-pre-catalog-{stamp}.sqlite"
        self.database.backup(target)
        with sqlite3.connect(target) as connection:
            quick_row = connection.execute("PRAGMA quick_check(1)").fetchone()
            quick = str(quick_row[0] if quick_row else "sem resultado")
            fk = len(connection.execute("PRAGMA foreign_key_check").fetchall())
        if quick.lower() != "ok" or fk:
            raise RuntimeError(f"Backup não passou na validação SQLite (quick_check={quick}; foreign_keys={fk}).")
        return {"path": str(target), "sha256": _sha256(target), "quick_check": quick, "foreign_key_violations": fk}

    def _restore_backup(self, backup_path: str | Path) -> None:
        source_path = Path(backup_path)
        if not source_path.exists():
            raise RuntimeError("Backup de rollback não foi encontrado.")
        with sqlite3.connect(source_path, timeout=30) as source:
            with sqlite3.connect(self.database.path, timeout=30) as target:
                source.backup(target)
                target.commit()

    def _incoming_progress_would_change(self, payload: dict[str, Any]) -> bool:
        with self.database.connect() as connection:
            for raw in payload.get("tarefas_referencia", []):
                task = dict(raw)
                if not _progress_present(task):
                    continue
                key = stable_lesson_key(task)
                old = self._learner_progress(connection, key)
                incoming = _progress_from_task(task)
                if _merge_progress(old, incoming) != _merge_progress(old, {}):
                    return True
        return False

    def _learner_progress(self, connection: sqlite3.Connection, lesson_key: str) -> dict[str, Any]:
        row = connection.execute("SELECT * FROM course_learner_state WHERE lesson_key=?", (lesson_key,)).fetchone()
        if not row:
            return {}
        return {
            "data": str(row["study_date"] or ""),
            "ch_efetiva_min": int(row["effective_minutes"] or 0),
            "questoes_feitas": int(row["questions_done"] or 0),
            "acertos": int(row["correct_answers"] or 0),
            "desempenho": float(row["performance"] or 0),
            "estudado": bool(row["studied"]),
            "evidencias_estudo": json.loads(str(row["evidence_json"] or "[]")),
        }

    def apply(self, new_payload: dict[str, Any], current_payload: dict[str, Any] | None = None, *, new_url: str = "", resolutions: dict[str, dict[str, str]] | None = None) -> dict[str, Any]:
        preflight = self.preflight(new_payload, current_payload, resolutions=resolutions)
        if not preflight["ok"]:
            raise ValueError("A mesclagem foi bloqueada: há correspondências incertas. Revise o dry-run antes de aplicar.")

        counts = dict(preflight.get("counts", {}) or {})
        current_version = str(dict((current_payload or {}).get("course_catalog", {}) or {}).get("version") or "")
        new_version = str(preflight["catalog_version"])
        structural_change = any(int(counts.get(k, 0) or 0) for k in ("updated", "new", "archived", "uncertain"))
        if current_version == new_version and not structural_change and not self._incoming_progress_would_change(new_payload):
            return {
                "ok": True, "noop": True, "import_id": "", "catalog_version": new_version,
                "backup": {}, "quick_check": "ok", "foreign_key_violations": 0,
                "summary": {**counts, "progress_preserved": sum(1 for t in new_payload.get("tarefas_referencia", []) if _progress_present(dict(t))), "learner_rows_changed": 0, "personal_fields_overwritten_by_blank": 0},
                "payload": current_payload or new_payload, "preflight": preflight,
            }

        backup = self._backup()
        with self.database.connect() as snapshot_connection:
            pedagogical_before = self._pedagogical_snapshot(snapshot_connection)
        old_taxonomy_bytes = self.taxonomy_path.read_bytes() if self.taxonomy_path.exists() else None
        old_config_bytes = self.config_path.read_bytes() if self.config_path and self.config_path.exists() else None
        import_id = str(uuid.uuid4())
        now = utc_now()
        source = dict(new_payload.get("source", {}) or {})
        previous_source = _clean(dict((current_payload or {}).get("source", {}) or {}).get("url"))
        version = new_version
        diffs = list(preflight["diffs"])
        match_map = dict(preflight.get("matches", {}))
        merged_tasks: list[dict[str, Any]] = []
        progress_preserved = 0
        learner_rows_changed = 0
        db_committed = False
        try:
            # Seed legacy learner evidence only inside the real transaction, never during dry-run.
            with self.database.connect() as connection:
                self._seed_current_snapshot(current_payload, connection=connection)
                # Archive only rows that actually disappeared (or whose stable
                # identity changed). Deactivating the whole catalog and then
                # reactivating every row produced hundreds of false upserts.
                archive_keys = {
                    str(item.get("lesson_key") or "")
                    for item in diffs
                    if str(item.get("change_type") or "") == "archived"
                }
                archive_keys.update(
                    str(old_key)
                    for new_key, old_key in match_map.items()
                    if str(old_key) and str(old_key) != str(new_key)
                )
                if archive_keys:
                    connection.executemany(
                        "UPDATE course_catalog_lessons SET active=0, updated_at=? WHERE lesson_key=? AND active<>0",
                        ((now, key) for key in sorted(archive_keys)),
                    )
                for raw in new_payload.get("tarefas_referencia", []):
                    task = dict(raw)
                    new_key = stable_lesson_key(task)
                    old_key = match_map.get(new_key, new_key)
                    incoming_progress = _progress_from_task(task)
                    if _progress_present(task):
                        learner_rows_changed += int(self._upsert_learner_state(connection, old_key, incoming_progress, now))
                    learner = self._learner_progress(connection, old_key)
                    if learner:
                        progress_preserved += 1
                        task.update(_merge_progress(learner, incoming_progress))
                    if old_key != new_key:
                        old_progress = self._learner_progress(connection, old_key)
                        if old_progress:
                            learner_rows_changed += int(self._upsert_learner_state(connection, new_key, old_progress, now))
                            connection.execute("DELETE FROM course_learner_state WHERE lesson_key=?", (old_key,))
                    structural = structural_lesson_key(task)
                    structural_payload = {k: v for k, v in task.items() if k not in PROGRESS_FIELDS}
                    structural_json = json.dumps(structural_payload, ensure_ascii=False, sort_keys=True)
                    existing = connection.execute("SELECT * FROM course_catalog_lessons WHERE lesson_key=?", (new_key,)).fetchone()
                    values = (
                        structural, _clean(task.get("trilha")), _clean(task.get("tarefa")), _clean(task.get("aula")),
                        _clean(task.get("materia")), self._task_title(task), int(task.get("row", 0) or 0),
                        version, _clean(new_url or source.get("url")), structural_json, now, new_key,
                    )
                    if existing:
                        changed = any([
                            str(existing["structural_key"] or "") != values[0], str(existing["trail"] or "") != values[1],
                            str(existing["task_no"] or "") != values[2], str(existing["lesson"] or "") != values[3],
                            str(existing["subject"] or "") != values[4], str(existing["title"] or "") != values[5],
                            int(existing["source_row"] or 0) != values[6], int(existing["active"] or 0) != 1,
                            str(existing["catalog_version"] or "") != values[7], str(existing["source_spreadsheet"] or "") != values[8],
                            str(existing["structural_json"] or "") != values[9],
                        ])
                        if changed:
                            connection.execute(
                                """UPDATE course_catalog_lessons SET structural_key=?,trail=?,task_no=?,lesson=?,subject=?,title=?,source_row=?,
                                   active=1,catalog_version=?,source_spreadsheet=?,structural_json=?,updated_at=? WHERE lesson_key=?""", values
                            )
                        else:
                            connection.execute("UPDATE course_catalog_lessons SET active=1 WHERE lesson_key=? AND active<>1", (new_key,))
                    else:
                        connection.execute(
                            """INSERT INTO course_catalog_lessons(lesson_key,structural_key,trail,task_no,lesson,subject,title,source_row,active,catalog_version,source_spreadsheet,structural_json,created_at,updated_at)
                               VALUES(?,?,?,?,?,?,?,?,1,?,?,?,?,?)""",
                            (new_key, structural, _clean(task.get("trilha")), _clean(task.get("tarefa")), _clean(task.get("aula")), _clean(task.get("materia")), self._task_title(task), int(task.get("row",0) or 0), version, _clean(new_url or source.get("url")), structural_json, now, now),
                        )
                    merged_tasks.append(task)

                pedagogical_after = self._pedagogical_snapshot(connection)
                summary = {
                    **counts,
                    "progress_preserved": progress_preserved,
                    "learner_rows_changed": learner_rows_changed,
                    "personal_fields_overwritten_by_blank": 0,
                    "pedagogical_before": pedagogical_before,
                    "pedagogical_after": pedagogical_after,
                    "fsrs_rows_preserved": pedagogical_after.get("fsrs_rows", 0) if pedagogical_after.get("fsrs_rows", 0) == pedagogical_before.get("fsrs_rows", 0) else -1,
                    "knowledge_tracing_rows_preserved": (pedagogical_after.get("kt_lesson_rows", 0) + pedagogical_after.get("kt_topic_rows", 0)) if (pedagogical_after.get("kt_lesson_rows", 0), pedagogical_after.get("kt_topic_rows", 0)) == (pedagogical_before.get("kt_lesson_rows", 0), pedagogical_before.get("kt_topic_rows", 0)) else -1,
                }
                manifest = {
                    "course_catalog_version": version, "source_spreadsheet": _clean(new_url or source.get("url")),
                    "imported_at": now, "previous_source": previous_source, "merge_strategy": MERGE_STRATEGY,
                    "backup_sha256": backup["sha256"],
                }
                connection.execute(
                    """INSERT INTO course_catalog_imports(id,catalog_version,previous_source,source_spreadsheet,source_title,imported_at,merge_strategy,status,backup_path,backup_sha256,quick_check,foreign_key_violations,summary_json,manifest_json)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (import_id, version, previous_source, _clean(new_url or source.get("url")), _clean(source.get("title")), now, MERGE_STRATEGY, "completed", backup["path"], backup["sha256"], backup["quick_check"], int(backup["foreign_key_violations"]), json.dumps(summary, ensure_ascii=False, sort_keys=True), json.dumps(manifest, ensure_ascii=False, sort_keys=True)),
                )
                for item in diffs:
                    if str(item.get("change_type")) == "equal":
                        continue
                    connection.execute(
                        "INSERT INTO course_catalog_changes(id,import_id,lesson_key,change_type,detail_json,created_at) VALUES(?,?,?,?,?,?)",
                        (str(uuid.uuid4()), import_id, str(item["lesson_key"]), str(item["change_type"]), json.dumps(item, ensure_ascii=False, sort_keys=True), now),
                    )
            db_committed = True

            merged_payload = json.loads(json.dumps(new_payload, ensure_ascii=False))
            merged_payload["tarefas_referencia"] = merged_tasks
            merged_payload["schema"] = "questflow.taxonomy.v1"
            merged_payload["course_catalog"] = {"version": version, "import_id": import_id, "merge_strategy": MERGE_STRATEGY, "learner_state": "sqlite:course_learner_state"}
            save_taxonomy(merged_payload, self.taxonomy_path)
            if self.config_path and new_url:
                config = json.loads(self.config_path.read_text(encoding="utf-8")) if self.config_path.exists() else {}
                config["taxonomy_spreadsheet_url"] = new_url
                config["course_catalog_version"] = version
                config["course_catalog_last_import_id"] = import_id
                _atomic_json(self.config_path, config)
            with self.database.connect() as connection:
                quick_row = connection.execute("PRAGMA quick_check(1)").fetchone()
                quick = str(quick_row[0] if quick_row else "sem resultado")
                fk = len(connection.execute("PRAGMA foreign_key_check").fetchall())
            if quick.lower() != "ok" or fk:
                raise RuntimeError(f"Validação pós-mesclagem falhou (quick_check={quick}; foreign_keys={fk}).")
            return {"ok": True, "noop": False, "import_id": import_id, "catalog_version": version, "backup": backup, "quick_check": quick, "foreign_key_violations": fk, "summary": summary, "payload": merged_payload, "preflight": preflight}
        except Exception:
            if db_committed:
                self._restore_backup(backup["path"])
            if old_taxonomy_bytes is None:
                try: self.taxonomy_path.unlink()
                except FileNotFoundError: pass
            else:
                self.taxonomy_path.write_bytes(old_taxonomy_bytes)
            if self.config_path:
                if old_config_bytes is None:
                    try: self.config_path.unlink()
                    except FileNotFoundError: pass
                else:
                    self.config_path.write_bytes(old_config_bytes)
            raise

    def recent_imports(self, limit: int = 20) -> list[dict[str, Any]]:
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM course_catalog_imports ORDER BY imported_at DESC LIMIT ?", (max(1, min(100, int(limit))),)
            ).fetchall()
        return [dict(row) for row in rows]


__all__ = [
    "CourseCatalogService", "CatalogDiff", "stable_lesson_key", "structural_lesson_key",
    "MERGE_STRATEGY", "PROGRESS_FIELDS",
]
