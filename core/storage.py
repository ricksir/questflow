from __future__ import annotations

import json
import os
import re
import sqlite3
import threading
import unicodedata
import uuid
from contextlib import closing, contextmanager
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path

from .spreadsheet_taxonomy import SpreadsheetTaxonomy
from .schema_migrations import apply_migration, ensure_columns, migration_history
from .bank_intelligence import (
    calculate_quality,
    commentary_source,
    curation_readiness,
    curation_status,
    duplicate_similarity,
    empirical_difficulty,
    infer_origin_type,
    intelligence_snapshot,
    rights_status,
    split_pipe,
)
from .semantic_retrieval import (
    SEMANTIC_VERSION,
    chunk_text,
    graph_for_question,
    hashed_embedding,
    hybrid_retrieval_score,
    normalize_text as semantic_normalize_text,
    question_document,
    semantic_duplicate_score,
)



def _total_memory_bytes() -> int:
    """Best-effort RAM detection without adding a dependency such as psutil."""
    if os.name == "nt":
        try:
            import ctypes

            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            status = MEMORYSTATUSEX()
            status.dwLength = ctypes.sizeof(status)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                return int(status.ullTotalPhys)
        except Exception:
            pass
    try:
        pages = int(os.sysconf("SC_PHYS_PAGES"))
        page_size = int(os.sysconf("SC_PAGE_SIZE"))
        return pages * page_size
    except (AttributeError, OSError, ValueError):
        return 4 * 1024**3


def _database_tuning() -> tuple[int, int, int]:
    total = max(1024**3, _total_memory_bytes())
    # SQLite receives at most 1/64 of RAM as page cache (32–128 MiB). mmap is
    # a virtual address ceiling, not an eager allocation, and is capped at
    # 512 MiB. This benefits stronger machines without harming small ones.
    cache_bytes = max(32 * 1024**2, min(128 * 1024**2, total // 64))
    mmap_bytes = max(64 * 1024**2, min(512 * 1024**2, total // 16))
    threads = max(1, min(8, int(os.cpu_count() or 4)))
    return cache_bytes // 1024, mmap_bytes, threads

def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _catalog_key(value: object) -> str:
    """Stable, accent-insensitive key used only for lesson catalog matching."""
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"[^A-Z0-9]+", " ", text.upper()).strip()


def _lesson_catalog_key(value: object) -> str:
    """Unify Aula 0, aula 00 and 00 without changing the visible label."""
    text = _catalog_key(value)
    match = re.fullmatch(r"(?:AULA\s*)?(\d{1,3})", text)
    return f"AULA {int(match.group(1)):02d}" if match else text


def _canonical_lesson_label(value: object) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    key = _lesson_catalog_key(text)
    return key.title() if re.fullmatch(r"AULA \d{2,3}", key) else text


_CODE_REFERENCE_KEYS = {
    "codigo", "código", "code", "source_code", "question_code",
    "codigo_origem", "código_origem", "id_questao", "id_questão",
}


def _normalize_question_code(value: object) -> str:
    code = str(value or "").strip()
    if not code:
        raise ValueError("O código da questão não pode ficar vazio.")
    if len(code) > 240:
        raise ValueError("O código da questão deve ter no máximo 240 caracteres.")
    if any(ord(char) < 32 for char in code):
        raise ValueError("O código da questão contém caracteres de controle inválidos.")
    return code


def _sync_nested_code_references(value: object, old_code: str, new_code: str) -> object:
    """Atualiza apenas campos semanticamente identificados como código.

    O texto do enunciado e da explicação não é alterado, mesmo que mencione o
    código antigo. A identidade técnica da questão continua sendo o UID.
    """
    if isinstance(value, dict):
        for key, item in list(value.items()):
            normalized_key = str(key).strip().lower()
            if normalized_key in {
                "historico_codigos", "histórico_codigos", "code_history",
                "old_code", "new_code", "codigo_anterior", "codigo_novo",
            }:
                continue
            is_code_key = (
                normalized_key in _CODE_REFERENCE_KEYS
                or normalized_key.endswith("_code")
                or normalized_key.endswith("_codigo")
                or normalized_key.endswith("_código")
            )
            if is_code_key and isinstance(item, str) and item.strip().casefold() == old_code.casefold():
                value[key] = new_code
            elif isinstance(item, (dict, list)):
                _sync_nested_code_references(item, old_code, new_code)
    elif isinstance(value, list):
        for item in value:
            if isinstance(item, (dict, list)):
                _sync_nested_code_references(item, old_code, new_code)
    return value


class QuestFlowDatabase:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._pragma_lock = threading.Lock()
        self._journal_configured = False
        self._cache_kib, self._mmap_bytes, self._sqlite_threads = _database_tuning()
        self.initialize()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        """Abra uma conexão transacional e sempre libere o arquivo no Windows.

        O gerenciador nativo de ``sqlite3.Connection`` confirma ou desfaz a
        transação, mas não fecha a conexão ao sair do bloco ``with``. Em
        Windows isso mantinha o banco e os arquivos WAL/SHM bloqueados, o que
        fazia o diagnóstico falhar ao remover sua pasta temporária.
        """
        # A 30-second busy timeout made a temporary database lock look like a
        # frozen application. WAL is configured once per process instead of on
        # every read connection, because changing/querying journal mode can
        # itself contend with a writer on Windows.
        connection = sqlite3.connect(self.path, timeout=8)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA busy_timeout = 8000")
            if not self._journal_configured:
                with self._pragma_lock:
                    if not self._journal_configured:
                        connection.execute("PRAGMA journal_mode = WAL")
                        self._journal_configured = True
            connection.execute("PRAGMA synchronous = NORMAL")
            connection.execute("PRAGMA temp_store = MEMORY")
            connection.execute(f"PRAGMA cache_size = -{self._cache_kib}")
            connection.execute(f"PRAGMA mmap_size = {self._mmap_bytes}")
            connection.execute(f"PRAGMA threads = {self._sqlite_threads}")
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
                CREATE TABLE IF NOT EXISTS imports (
                    id TEXT PRIMARY KEY,
                    source_file TEXT NOT NULL,
                    imported_at TEXT NOT NULL,
                    extracted_count INTEGER NOT NULL DEFAULT 0,
                    inserted_count INTEGER NOT NULL DEFAULT 0,
                    duplicate_count INTEGER NOT NULL DEFAULT 0,
                    pending_count INTEGER NOT NULL DEFAULT 0,
                    metadata_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS questions (
                    uid TEXT PRIMARY KEY,
                    source_key TEXT NOT NULL UNIQUE,
                    source_code TEXT NOT NULL,
                    fingerprint TEXT NOT NULL UNIQUE,
                    subject TEXT,
                    primary_topic TEXT,
                    topics_text TEXT,
                    lesson TEXT,
                    taxonomy_status TEXT,
                    taxonomy_confidence REAL NOT NULL DEFAULT 0,
                    taxonomy_source TEXT,
                    board TEXT,
                    exam_year INTEGER,
                    agency TEXT,
                    exam_name TEXT,
                    question_type TEXT,
                    answer TEXT,
                    statement TEXT NOT NULL,
                    review_status TEXT NOT NULL,
                    confidence REAL NOT NULL DEFAULT 0,
                    source_file TEXT,
                    source_page INTEGER,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    data_json TEXT NOT NULL
                );


                CREATE TABLE IF NOT EXISTS excluded_questions (
                    id TEXT PRIMARY KEY,
                    original_uid TEXT,
                    source_key TEXT,
                    source_code TEXT,
                    fingerprint TEXT,
                    exclusion_kind TEXT NOT NULL,
                    exclusion_reason TEXT,
                    excluded_at TEXT NOT NULL,
                    data_json TEXT NOT NULL
                );
                """
            )
            apply_migration(
                connection,
                component="question_bank",
                version=1,
                name="taxonomy columns",
                callback=lambda conn: ensure_columns(
                    conn,
                    "questions",
                    {
                        "primary_topic": "TEXT",
                        "lesson": "TEXT",
                        "taxonomy_status": "TEXT",
                        "taxonomy_confidence": "REAL NOT NULL DEFAULT 0",
                        "taxonomy_source": "TEXT",
                    },
                ),
            )

            def _create_question_indexes(conn: sqlite3.Connection) -> None:
                conn.executescript(
                    """
                    CREATE INDEX IF NOT EXISTS idx_questions_subject ON questions(subject);
                    CREATE INDEX IF NOT EXISTS idx_questions_topic ON questions(primary_topic);
                    CREATE INDEX IF NOT EXISTS idx_questions_lesson ON questions(lesson);
                    CREATE INDEX IF NOT EXISTS idx_questions_board ON questions(board);
                    CREATE INDEX IF NOT EXISTS idx_questions_year ON questions(exam_year);
                    CREATE INDEX IF NOT EXISTS idx_questions_agency ON questions(agency);
                    CREATE INDEX IF NOT EXISTS idx_questions_status ON questions(review_status);
                    CREATE INDEX IF NOT EXISTS idx_questions_status_year_code ON questions(review_status, exam_year DESC, source_code ASC);
                    CREATE INDEX IF NOT EXISTS idx_questions_taxonomy_status ON questions(taxonomy_status);
                    CREATE INDEX IF NOT EXISTS idx_questions_statement ON questions(statement);
                    CREATE INDEX IF NOT EXISTS idx_excluded_source_key ON excluded_questions(source_key);
                    CREATE INDEX IF NOT EXISTS idx_excluded_fingerprint ON excluded_questions(fingerprint);
                    CREATE INDEX IF NOT EXISTS idx_excluded_kind ON excluded_questions(exclusion_kind);
                    """
                )

            apply_migration(
                connection,
                component="question_bank",
                version=2,
                name="question and exclusion indexes",
                callback=_create_question_indexes,
            )

            def _create_read_path_indexes(conn: sqlite3.Connection) -> None:
                conn.executescript(
                    """
                    CREATE INDEX IF NOT EXISTS idx_questions_year_code
                        ON questions(exam_year DESC, source_code ASC);
                    CREATE INDEX IF NOT EXISTS idx_questions_subject_lesson
                        ON questions(subject, lesson);
                    CREATE INDEX IF NOT EXISTS idx_questions_updated
                        ON questions(updated_at DESC);
                    """
                )

            apply_migration(
                connection,
                component="question_bank",
                version=3,
                name="responsive UI read indexes",
                callback=_create_read_path_indexes,
            )

            def _create_question_code_audit(conn: sqlite3.Connection) -> None:
                conn.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS question_code_history (
                        id TEXT PRIMARY KEY,
                        question_uid TEXT NOT NULL,
                        old_code TEXT NOT NULL,
                        new_code TEXT NOT NULL,
                        changed_at TEXT NOT NULL,
                        changed_via TEXT NOT NULL DEFAULT 'sistema',
                        source_key_before TEXT,
                        source_key_after TEXT
                    );
                    CREATE INDEX IF NOT EXISTS idx_question_code_history_uid
                        ON question_code_history(question_uid, changed_at DESC);
                    CREATE INDEX IF NOT EXISTS idx_question_code_history_old
                        ON question_code_history(old_code);
                    CREATE INDEX IF NOT EXISTS idx_question_code_history_new
                        ON question_code_history(new_code);
                    """
                )

            apply_migration(
                connection,
                component="question_bank",
                version=4,
                name="question code change audit",
                callback=_create_question_code_audit,
            )

            def _create_bank_intelligence_schema(conn: sqlite3.Connection) -> None:
                ensure_columns(
                    conn,
                    "questions",
                    {
                        "origin_type": "TEXT NOT NULL DEFAULT 'nao_informada'",
                        "curation_status": "TEXT NOT NULL DEFAULT 'revisar'",
                        "quality_score": "REAL NOT NULL DEFAULT 0",
                        "difficulty_score": "REAL",
                        "difficulty_label": "TEXT",
                        "commentary_source": "TEXT",
                        "rights_status": "TEXT",
                        "tags_text": "TEXT",
                        "law_refs_text": "TEXT",
                    },
                )
                conn.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS question_duplicate_candidates (
                        id TEXT PRIMARY KEY,
                        question_uid TEXT NOT NULL,
                        candidate_uid TEXT NOT NULL,
                        similarity REAL NOT NULL,
                        reason TEXT,
                        status TEXT NOT NULL DEFAULT 'aberto',
                        created_at TEXT NOT NULL,
                        resolved_at TEXT,
                        UNIQUE(question_uid, candidate_uid)
                    );
                    CREATE INDEX IF NOT EXISTS idx_questions_origin_type ON questions(origin_type);
                    CREATE INDEX IF NOT EXISTS idx_questions_curation_status ON questions(curation_status);
                    CREATE INDEX IF NOT EXISTS idx_questions_quality_score ON questions(quality_score DESC);
                    CREATE INDEX IF NOT EXISTS idx_questions_difficulty_label ON questions(difficulty_label);
                    CREATE INDEX IF NOT EXISTS idx_questions_commentary_source ON questions(commentary_source);
                    CREATE INDEX IF NOT EXISTS idx_duplicate_question_status
                        ON question_duplicate_candidates(question_uid, status, similarity DESC);
                    CREATE INDEX IF NOT EXISTS idx_duplicate_candidate_status
                        ON question_duplicate_candidates(candidate_uid, status, similarity DESC);
                    """
                )
                rows = conn.execute("SELECT uid, data_json FROM questions").fetchall()
                for row in rows:
                    try:
                        question = json.loads(row["data_json"] or "{}")
                    except Exception:
                        question = {}
                    snapshot = intelligence_snapshot(question)
                    conn.execute(
                        """
                        UPDATE questions
                        SET origin_type = ?, curation_status = ?, quality_score = ?,
                            commentary_source = ?, rights_status = ?, tags_text = ?, law_refs_text = ?
                        WHERE uid = ?
                        """,
                        (
                            snapshot["origin_type"], snapshot["curation_status"],
                            float(snapshot["quality"]["score"]), snapshot["commentary_source"],
                            snapshot["rights_status"], " | ".join(snapshot["tags"]),
                            " | ".join(snapshot["law_refs"]), str(row["uid"]),
                        ),
                    )

            apply_migration(
                connection,
                component="question_bank",
                version=5,
                name="bank intelligence provenance curation quality and duplicate candidates",
                callback=_create_bank_intelligence_schema,
            )

            def _create_semantic_curation_schema(conn: sqlite3.Connection) -> None:
                ensure_columns(
                    conn,
                    "question_duplicate_candidates",
                    {
                        "method": "TEXT NOT NULL DEFAULT 'lexical_v1'",
                        "details_json": "TEXT",
                    },
                )
                ensure_columns(
                    conn,
                    "questions",
                    {
                        "semantic_version": "TEXT",
                        "semantic_indexed_at": "TEXT",
                    },
                )
                conn.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS qf_semantic_signatures (
                        question_uid TEXT PRIMARY KEY,
                        version TEXT NOT NULL,
                        vector_json TEXT NOT NULL,
                        document_hash TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS qf_knowledge_nodes (
                        id TEXT PRIMARY KEY,
                        node_type TEXT NOT NULL,
                        label TEXT NOT NULL,
                        normalized_label TEXT NOT NULL,
                        metadata_json TEXT NOT NULL DEFAULT '{}',
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        UNIQUE(node_type, normalized_label)
                    );
                    CREATE TABLE IF NOT EXISTS qf_question_concepts (
                        question_uid TEXT NOT NULL,
                        node_id TEXT NOT NULL,
                        relation TEXT NOT NULL DEFAULT 'classificado_como',
                        confidence REAL NOT NULL DEFAULT 1.0,
                        source TEXT NOT NULL DEFAULT 'questao',
                        created_at TEXT NOT NULL,
                        PRIMARY KEY(question_uid, node_id, relation)
                    );
                    CREATE TABLE IF NOT EXISTS qf_knowledge_edges (
                        id TEXT PRIMARY KEY,
                        source_node_id TEXT NOT NULL,
                        target_node_id TEXT NOT NULL,
                        relation TEXT NOT NULL,
                        weight REAL NOT NULL DEFAULT 1.0,
                        evidence_json TEXT NOT NULL DEFAULT '{}',
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        UNIQUE(source_node_id, target_node_id, relation)
                    );
                    CREATE TABLE IF NOT EXISTS qf_rag_chunks (
                        id TEXT PRIMARY KEY,
                        source_kind TEXT NOT NULL,
                        source_ref TEXT NOT NULL,
                        title TEXT,
                        subject TEXT,
                        topic TEXT,
                        content TEXT NOT NULL,
                        normalized_content TEXT NOT NULL,
                        vector_json TEXT NOT NULL DEFAULT '[]',
                        metadata_json TEXT NOT NULL DEFAULT '{}',
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );
                    CREATE INDEX IF NOT EXISTS idx_qf_rag_source ON qf_rag_chunks(source_kind, source_ref);
                    CREATE INDEX IF NOT EXISTS idx_qf_rag_subject ON qf_rag_chunks(subject);
                    CREATE INDEX IF NOT EXISTS idx_qf_concepts_question ON qf_question_concepts(question_uid);
                    CREATE INDEX IF NOT EXISTS idx_qf_nodes_type_label ON qf_knowledge_nodes(node_type, normalized_label);
                    CREATE INDEX IF NOT EXISTS idx_qf_edges_source ON qf_knowledge_edges(source_node_id);
                    CREATE INDEX IF NOT EXISTS idx_qf_edges_target ON qf_knowledge_edges(target_node_id);
                    CREATE INDEX IF NOT EXISTS idx_questions_semantic_version ON questions(semantic_version);
                    """
                )
                rows = conn.execute("SELECT uid, data_json FROM questions").fetchall()
                for row in rows:
                    try:
                        question = json.loads(row["data_json"] or "{}")
                    except Exception:
                        question = {}
                    self._index_semantic_assets(conn, str(row["uid"]), question)

            apply_migration(
                connection,
                component="question_bank",
                version=6,
                name="semantic curation hybrid retrieval knowledge graph and rag chunks",
                callback=_create_semantic_curation_schema,
            )

            def _create_temporal_legislation_schema(conn: sqlite3.Connection) -> None:
                conn.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS qf_legislation_versions (
                        id TEXT PRIMARY KEY,
                        canonical_key TEXT NOT NULL,
                        title TEXT NOT NULL,
                        jurisdiction TEXT,
                        subject TEXT,
                        source_label TEXT,
                        source_url TEXT,
                        effective_from TEXT NOT NULL,
                        effective_to TEXT,
                        text_content TEXT NOT NULL,
                        text_sha256 TEXT NOT NULL,
                        status TEXT NOT NULL DEFAULT 'vigente',
                        notes TEXT,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        UNIQUE(canonical_key, effective_from)
                    );
                    CREATE INDEX IF NOT EXISTS idx_qf_legislation_key_date
                        ON qf_legislation_versions(canonical_key, effective_from, effective_to);
                    CREATE INDEX IF NOT EXISTS idx_qf_legislation_subject
                        ON qf_legislation_versions(subject, effective_from DESC);
                    """
                )

            apply_migration(
                connection,
                component="question_bank",
                version=7,
                name="temporal legislation versions indexed into knowledge engine",
                callback=_create_temporal_legislation_schema,
            )

            def _create_lesson_catalog_schema(conn: sqlite3.Connection) -> None:
                ensure_columns(conn, "questions", {"lesson_title": "TEXT"})
                conn.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS qf_bank_lesson_aliases (
                        alias_key TEXT PRIMARY KEY,
                        source_subject_key TEXT NOT NULL,
                        source_lesson_key TEXT NOT NULL,
                        subject TEXT NOT NULL,
                        lesson TEXT NOT NULL,
                        title TEXT NOT NULL DEFAULT '',
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        UNIQUE(source_subject_key, source_lesson_key)
                    );
                    CREATE INDEX IF NOT EXISTS idx_qf_bank_lesson_target
                        ON qf_bank_lesson_aliases(subject, lesson);
                    """
                )

            apply_migration(
                connection,
                component="question_bank",
                version=9,
                name="canonical subject and lesson catalog with aliases",
                callback=_create_lesson_catalog_schema,
            )

            def _create_course_catalog_schema(conn: sqlite3.Connection) -> None:
                conn.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS course_catalog_lessons (
                        lesson_key TEXT PRIMARY KEY, structural_key TEXT NOT NULL, trail TEXT, task_no TEXT,
                        lesson TEXT, subject TEXT, title TEXT, source_row INTEGER, active INTEGER NOT NULL DEFAULT 1,
                        catalog_version TEXT NOT NULL, source_spreadsheet TEXT, structural_json TEXT NOT NULL,
                        created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                    );
                    CREATE INDEX IF NOT EXISTS idx_course_catalog_structural ON course_catalog_lessons(structural_key, active);
                    CREATE INDEX IF NOT EXISTS idx_course_catalog_active ON course_catalog_lessons(active, trail, subject, lesson);
                    CREATE TABLE IF NOT EXISTS course_learner_state (
                        lesson_key TEXT PRIMARY KEY, studied INTEGER NOT NULL DEFAULT 0, study_date TEXT,
                        effective_minutes INTEGER NOT NULL DEFAULT 0, questions_done INTEGER NOT NULL DEFAULT 0,
                        correct_answers INTEGER NOT NULL DEFAULT 0, performance REAL NOT NULL DEFAULT 0,
                        evidence_json TEXT NOT NULL DEFAULT '[]', first_observed_at TEXT NOT NULL, updated_at TEXT NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS course_catalog_imports (
                        id TEXT PRIMARY KEY, catalog_version TEXT NOT NULL, previous_source TEXT, source_spreadsheet TEXT,
                        source_title TEXT, imported_at TEXT NOT NULL, merge_strategy TEXT NOT NULL, status TEXT NOT NULL,
                        backup_path TEXT, backup_sha256 TEXT, quick_check TEXT, foreign_key_violations INTEGER NOT NULL DEFAULT 0,
                        summary_json TEXT NOT NULL, manifest_json TEXT NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS course_catalog_changes (
                        id TEXT PRIMARY KEY, import_id TEXT NOT NULL, lesson_key TEXT NOT NULL, change_type TEXT NOT NULL,
                        detail_json TEXT NOT NULL, created_at TEXT NOT NULL,
                        FOREIGN KEY(import_id) REFERENCES course_catalog_imports(id) ON DELETE CASCADE
                    );
                    CREATE INDEX IF NOT EXISTS idx_course_catalog_changes_import ON course_catalog_changes(import_id, change_type);
                    """
                )

            apply_migration(
                connection,
                component="course_catalog",
                version=1,
                name="course catalog separated from durable learner state",
                callback=_create_course_catalog_schema,
            )
            # Refresh planner statistics after an upgrade. SQLite executes this
            # incrementally and skips unnecessary work on later starts.
            connection.execute("PRAGMA optimize")


    def _index_legislation_version(self, connection: sqlite3.Connection, version_id: str, payload: dict) -> None:
        version_id = str(version_id)
        connection.execute("DELETE FROM qf_rag_chunks WHERE source_kind='legislation' AND source_ref=?", (version_id,))
        text = str(payload.get("text_content") or "").strip()
        title = str(payload.get("title") or payload.get("canonical_key") or "Legislação")
        subject = str(payload.get("subject") or "")
        metadata = {
            "canonical_key": str(payload.get("canonical_key") or ""),
            "jurisdiction": str(payload.get("jurisdiction") or ""),
            "source_label": str(payload.get("source_label") or ""),
            "source_url": str(payload.get("source_url") or ""),
            "effective_from": str(payload.get("effective_from") or ""),
            "effective_to": str(payload.get("effective_to") or ""),
            "status": str(payload.get("status") or "vigente"),
            "temporal_source": True,
        }
        now = utc_now()
        for idx, content in enumerate(chunk_text(text), start=1):
            chunk_id = f"leg:{version_id}:{idx}"
            connection.execute(
                """
                INSERT OR REPLACE INTO qf_rag_chunks(
                    id,source_kind,source_ref,title,subject,topic,content,normalized_content,vector_json,metadata_json,created_at,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (chunk_id, "legislation", version_id, title, subject, str(payload.get("canonical_key") or ""),
                 content, semantic_normalize_text(content), json.dumps(hashed_embedding(content)),
                 json.dumps(metadata, ensure_ascii=False), now, now),
            )

    def upsert_legislation_version(self, payload: dict) -> dict:
        import hashlib
        canonical_key = str(payload.get("canonical_key") or "").strip()
        title = str(payload.get("title") or "").strip()
        effective_from = str(payload.get("effective_from") or "").strip()
        text_content = str(payload.get("text_content") or "").strip()
        if not canonical_key or not title or not effective_from or len(text_content) < 20:
            raise ValueError("Informe chave canônica, título, início de vigência e texto da norma.")
        effective_to = str(payload.get("effective_to") or "").strip() or None
        if effective_to and effective_to < effective_from:
            raise ValueError("O fim de vigência não pode ser anterior ao início.")
        digest = hashlib.sha256(text_content.encode("utf-8")).hexdigest()
        now = utc_now()
        with self.connect() as connection:
            row = connection.execute(
                "SELECT id,created_at FROM qf_legislation_versions WHERE canonical_key=? AND effective_from=?",
                (canonical_key, effective_from),
            ).fetchone()
            version_id = str(row["id"]) if row else str(uuid.uuid4())
            created_at = str(row["created_at"]) if row else now
            connection.execute(
                """
                INSERT INTO qf_legislation_versions(
                    id,canonical_key,title,jurisdiction,subject,source_label,source_url,effective_from,effective_to,
                    text_content,text_sha256,status,notes,created_at,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(canonical_key,effective_from) DO UPDATE SET
                    title=excluded.title,jurisdiction=excluded.jurisdiction,subject=excluded.subject,
                    source_label=excluded.source_label,source_url=excluded.source_url,effective_to=excluded.effective_to,
                    text_content=excluded.text_content,text_sha256=excluded.text_sha256,status=excluded.status,
                    notes=excluded.notes,updated_at=excluded.updated_at
                """,
                (version_id, canonical_key, title, str(payload.get("jurisdiction") or ""), str(payload.get("subject") or ""),
                 str(payload.get("source_label") or ""), str(payload.get("source_url") or ""), effective_from, effective_to,
                 text_content, digest, str(payload.get("status") or "vigente"), str(payload.get("notes") or ""), created_at, now),
            )
            saved = connection.execute("SELECT * FROM qf_legislation_versions WHERE id=?", (version_id,)).fetchone()
            self._index_legislation_version(connection, version_id, dict(saved))
        return self.get_legislation_version(version_id)

    def get_legislation_version(self, version_id: str) -> dict:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM qf_legislation_versions WHERE id=?", (str(version_id),)).fetchone()
        if not row:
            raise ValueError("Versão legislativa não encontrada.")
        return dict(row)

    def list_legislation_versions(self, canonical_key: str = "", limit: int = 200) -> list[dict]:
        safe_limit = max(1, min(1000, int(limit or 200)))
        with self.connect() as connection:
            if str(canonical_key or "").strip():
                rows = connection.execute(
                    "SELECT * FROM qf_legislation_versions WHERE canonical_key=? ORDER BY effective_from DESC LIMIT ?",
                    (str(canonical_key).strip(), safe_limit),
                ).fetchall()
            else:
                rows = connection.execute(
                    "SELECT * FROM qf_legislation_versions ORDER BY canonical_key COLLATE NOCASE,effective_from DESC LIMIT ?",
                    (safe_limit,),
                ).fetchall()
        return [dict(row) for row in rows]

    def resolve_legislation_version(self, canonical_key: str, reference_date: str) -> dict | None:
        key = str(canonical_key or "").strip()
        date = str(reference_date or "").strip()
        if not key or not date:
            return None
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM qf_legislation_versions
                WHERE canonical_key=? AND effective_from<=? AND (effective_to IS NULL OR effective_to='' OR effective_to>=?)
                ORDER BY effective_from DESC LIMIT 1
                """,
                (key, date, date),
            ).fetchone()
        return dict(row) if row else None

    def temporal_legislation_summary(self) -> dict:
        with self.connect() as connection:
            total = int(connection.execute("SELECT COUNT(*) FROM qf_legislation_versions").fetchone()[0])
            keys = int(connection.execute("SELECT COUNT(DISTINCT canonical_key) FROM qf_legislation_versions").fetchone()[0])
            chunks = int(connection.execute("SELECT COUNT(*) FROM qf_rag_chunks WHERE source_kind='legislation'").fetchone()[0])
        return {"versions": total, "canonical_norms": keys, "rag_chunks": chunks, "temporal_resolution": True}

    def rag_chunks_by_ids(self, chunk_ids: list[str]) -> list[dict]:
        ids = [str(item).strip() for item in (chunk_ids or []) if str(item).strip()]
        if not ids:
            return []
        ids = ids[:50]
        placeholders = ",".join("?" for _ in ids)
        with self.connect() as connection:
            rows = connection.execute(
                f"SELECT id,source_kind,source_ref,title,subject,topic,content,metadata_json FROM qf_rag_chunks WHERE id IN ({placeholders})",
                ids,
            ).fetchall()
        by_id = {str(row["id"]): row for row in rows}
        result = []
        for chunk_id in ids:
            row = by_id.get(chunk_id)
            if not row:
                continue
            try:
                metadata = json.loads(row["metadata_json"] or "{}")
            except Exception:
                metadata = {}
            result.append({
                "id": str(row["id"]), "source_kind": str(row["source_kind"]), "source_ref": str(row["source_ref"]),
                "title": str(row["title"] or ""), "subject": str(row["subject"] or ""), "topic": str(row["topic"] or ""),
                "content": str(row["content"] or ""), "metadata": metadata,
            })
        return result

    def get_question_by_code(self, code: str) -> dict | None:
        with self.connect() as connection:
            row = connection.execute("SELECT data_json FROM questions WHERE source_code=? COLLATE NOCASE LIMIT 1", (str(code),)).fetchone()
        return json.loads(row[0]) if row else None

    def schema_history(self) -> list[dict]:
        with self.connect() as connection:
            return migration_history(connection)

    @staticmethod
    def _source_key(question: dict) -> str:
        source = question.get("fonte", {})
        code = str(question.get("codigo_origem") or question.get("id") or "").strip()
        filename = str(source.get("arquivo", "")).strip()
        if code.startswith("QFLOW-"):
            return f"{filename}:{code}"
        return code or f"{filename}:{question.get('fingerprint', '')}"

    @staticmethod
    def _topics_text(question: dict) -> str:
        return " | ".join(str(item) for item in question.get("assuntos", []))

    @staticmethod
    def _taxonomy_values(question: dict) -> tuple[str, str, str, float, str]:
        classification = question.get("classificacao_planilha", {})
        return (
            str(question.get("assunto", "")),
            str(question.get("aula_planilha", "")),
            str(classification.get("status", "")),
            float(classification.get("confianca", 0) or 0),
            str(classification.get("fonte", "")),
        )

    @staticmethod
    def _lesson_alias_key(subject: object, lesson: object) -> str:
        return f"{_catalog_key(subject)}::{_lesson_catalog_key(lesson)}"

    def _apply_lesson_catalog(self, connection: sqlite3.Connection, question: dict) -> dict:
        """Apply a manual lesson alias without replacing the question topic."""
        source_subject = str(question.get("materia", "")).strip()
        source_lesson = str(question.get("aula_planilha", "")).strip()
        if not source_subject or not source_lesson:
            return question
        row = connection.execute(
            "SELECT subject, lesson, title FROM qf_bank_lesson_aliases WHERE alias_key = ? LIMIT 1",
            (self._lesson_alias_key(source_subject, source_lesson),),
        ).fetchone()
        if not row:
            return question
        target_subject = str(row["subject"] or source_subject).strip()
        target_lesson = str(row["lesson"] or source_lesson).strip()
        title = str(row["title"] or "").strip()
        question["materia"] = target_subject
        question["aula_planilha"] = target_lesson
        if title:
            question["titulo_aula"] = title
        primary = str(question.get("assunto", "")).strip()
        question["trilha_assuntos"] = [item for item in (target_subject, target_lesson, primary) if item]
        classification = question.get("classificacao_planilha")
        if not isinstance(classification, dict):
            classification = {}
        if title:
            classification["titulo_aula"] = title
        question["classificacao_planilha"] = classification
        return question

    @staticmethod
    def _intelligence_values(question: dict) -> tuple[str, str, float, str, str, str, str]:
        snapshot = intelligence_snapshot(question)
        return (
            str(snapshot["origin_type"]),
            str(snapshot["curation_status"]),
            float(snapshot["quality"]["score"]),
            str(snapshot["commentary_source"]),
            str(snapshot["rights_status"]),
            " | ".join(snapshot["tags"]),
            " | ".join(snapshot["law_refs"]),
        )

    def _write_intelligence_columns(self, connection: sqlite3.Connection, uid: str, question: dict) -> None:
        origin_type, curation, quality, comment_source, rights, tags, law_refs = self._intelligence_values(question)
        connection.execute(
            """
            UPDATE questions
            SET origin_type = ?, curation_status = ?, quality_score = ?,
                commentary_source = ?, rights_status = ?, tags_text = ?, law_refs_text = ?
            WHERE uid = ?
            """,
            (origin_type, curation, quality, comment_source, rights, tags, law_refs, str(uid)),
        )

    @staticmethod
    def _semantic_hash(document: str) -> str:
        import hashlib
        return hashlib.sha256(str(document or "").encode("utf-8")).hexdigest()

    def _index_semantic_assets(self, connection: sqlite3.Connection, uid: str, question: dict) -> None:
        """Atualiza assinatura local, grafo e chunks RAG da questão na mesma transação."""
        uid = str(uid)
        now = utc_now()
        document = question_document(question)
        vector = hashed_embedding(document)
        connection.execute(
            """
            INSERT INTO qf_semantic_signatures(question_uid, version, vector_json, document_hash, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(question_uid) DO UPDATE SET
                version = excluded.version,
                vector_json = excluded.vector_json,
                document_hash = excluded.document_hash,
                updated_at = excluded.updated_at
            """,
            (uid, SEMANTIC_VERSION, json.dumps(vector), self._semantic_hash(document), now),
        )
        connection.execute(
            "UPDATE questions SET semantic_version = ?, semantic_indexed_at = ? WHERE uid = ?",
            (SEMANTIC_VERSION, now, uid),
        )

        graph = graph_for_question(question)
        connection.execute("DELETE FROM qf_question_concepts WHERE question_uid = ?", (uid,))
        node_map: dict[str, str] = {}
        for node in graph.get("nodes", []):
            node_id = str(node.get("id") or "")
            node_type = str(node.get("type") or "conceito")
            label = str(node.get("label") or "").strip()
            normalized = str(node.get("normalized") or semantic_normalize_text(label))
            if not node_id or not label or not normalized:
                continue
            connection.execute(
                """
                INSERT INTO qf_knowledge_nodes(id, node_type, label, normalized_label, metadata_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, '{}', ?, ?)
                ON CONFLICT(node_type, normalized_label) DO UPDATE SET
                    label = excluded.label, updated_at = excluded.updated_at
                """,
                (node_id, node_type, label, normalized, now, now),
            )
            resolved = connection.execute(
                "SELECT id FROM qf_knowledge_nodes WHERE node_type = ? AND normalized_label = ?",
                (node_type, normalized),
            ).fetchone()
            resolved_id = str(resolved["id"] if resolved else node_id)
            node_map[node_id] = resolved_id
            connection.execute(
                """
                INSERT OR REPLACE INTO qf_question_concepts(question_uid, node_id, relation, confidence, source, created_at)
                VALUES (?, ?, 'classificado_como', 1.0, 'questao', ?)
                """,
                (uid, resolved_id, now),
            )
        for edge in graph.get("edges", []):
            source = node_map.get(str(edge.get("source") or ""), str(edge.get("source") or ""))
            target = node_map.get(str(edge.get("target") or ""), str(edge.get("target") or ""))
            relation = str(edge.get("relation") or "relaciona")
            if not source or not target or source == target:
                continue
            edge_id = self._semantic_hash(f"{source}:{target}:{relation}")[:32]
            evidence = json.dumps({"question_uid": uid, "version": SEMANTIC_VERSION}, ensure_ascii=False)
            connection.execute(
                """
                INSERT INTO qf_knowledge_edges(id, source_node_id, target_node_id, relation, weight, evidence_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, 1.0, ?, ?, ?)
                ON CONFLICT(source_node_id, target_node_id, relation) DO UPDATE SET
                    weight = MIN(10.0, qf_knowledge_edges.weight + 0.05),
                    evidence_json = excluded.evidence_json,
                    updated_at = excluded.updated_at
                """,
                (edge_id, source, target, relation, evidence, now, now),
            )

        connection.execute(
            "DELETE FROM qf_rag_chunks WHERE source_kind = 'question' AND source_ref = ?", (uid,)
        )
        code = str(question.get("codigo_origem") or question.get("id") or uid)
        subject = str(question.get("materia") or "")
        topic = str(question.get("assunto") or "")
        rag_sections = [
            ("Questão", str(question.get("enunciado") or ""), "enunciado"),
            ("Comentário", str(question.get("explicacao") or ""), "comentario"),
        ]
        for section_title, text, section_kind in rag_sections:
            for index, content in enumerate(chunk_text(text), start=1):
                chunk_id = self._semantic_hash(f"question:{uid}:{section_kind}:{index}:{content}")[:36]
                metadata = {
                    "question_uid": uid,
                    "code": code,
                    "section": section_kind,
                    "board": str(question.get("banca") or ""),
                    "year": question.get("ano"),
                    "source_file": str((question.get("fonte") or {}).get("arquivo", "")) if isinstance(question.get("fonte"), dict) else "",
                    "semantic_version": SEMANTIC_VERSION,
                }
                connection.execute(
                    """
                    INSERT INTO qf_rag_chunks(
                        id, source_kind, source_ref, title, subject, topic, content,
                        normalized_content, vector_json, metadata_json, created_at, updated_at
                    ) VALUES (?, 'question', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        chunk_id, uid, f"{code} · {section_title}", subject, topic, content,
                        semantic_normalize_text(content), json.dumps(hashed_embedding(content)),
                        json.dumps(metadata, ensure_ascii=False), now, now,
                    ),
                )

    def _remove_semantic_assets(self, connection: sqlite3.Connection, uid: str) -> None:
        uid = str(uid)
        connection.execute("DELETE FROM qf_question_concepts WHERE question_uid = ?", (uid,))
        connection.execute("DELETE FROM qf_semantic_signatures WHERE question_uid = ?", (uid,))
        connection.execute("DELETE FROM qf_rag_chunks WHERE source_kind = 'question' AND source_ref = ?", (uid,))
        connection.execute("DELETE FROM question_duplicate_candidates WHERE question_uid = ? OR candidate_uid = ?", (uid, uid))

    def rag_observability_snapshot(self) -> dict:
        """Fingerprint agregado do índice RAG sem expor conteúdo ou caminhos locais."""
        import hashlib
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT id,source_kind,source_ref,subject,normalized_content FROM qf_rag_chunks ORDER BY id"
            ).fetchall()
        summary = self.semantic_index_summary()
        chunk_fingerprints = {}
        source_parts = {}
        source_meta = {}
        by_subject = {}
        by_kind = {}
        for row in rows:
            chunk_key = hashlib.sha256(str(row["id"]).encode("utf-8", errors="ignore")).hexdigest()[:20]
            digest = hashlib.sha256(str(row["normalized_content"] or "").encode("utf-8", errors="ignore")).hexdigest()
            chunk_fingerprints[chunk_key] = digest
            source_kind = str(row["source_kind"] or "unknown")
            source_ref = str(row["source_ref"] or "")
            source_key = hashlib.sha256(f"{source_kind}|{source_ref}".encode("utf-8", errors="ignore")).hexdigest()[:20]
            source_parts.setdefault(source_key, []).append(digest)
            source_meta[source_key] = source_kind
            subject = str(row["subject"] or "SEM_MATERIA")
            by_subject[subject] = by_subject.get(subject, 0) + 1
            by_kind[source_kind] = by_kind.get(source_kind, 0) + 1
        source_fingerprints = {
            key: hashlib.sha256("|".join(sorted(parts)).encode("ascii")).hexdigest()
            for key, parts in source_parts.items()
        }
        index_digest = hashlib.sha256("|".join(f"{k}:{v}" for k,v in sorted(chunk_fingerprints.items())).encode("ascii")).hexdigest()
        return {
            "schema": "questflow.rag_observability_snapshot.v1", "semantic_version": summary.get("version"),
            "coverage": summary.get("coverage"), "indexed_questions": summary.get("indexed_questions"),
            "total_questions": summary.get("total_questions"), "rag_chunks": len(rows),
            "source_count": len(source_fingerprints), "by_subject": by_subject, "by_source_kind": by_kind,
            "index_digest": index_digest, "chunk_fingerprints": chunk_fingerprints,
            "source_fingerprints": source_fingerprints,
        }

    def semantic_index_summary(self) -> dict:
        with self.connect() as connection:
            indexed = int(connection.execute(
                "SELECT COUNT(*) FROM questions WHERE semantic_version = ?", (SEMANTIC_VERSION,)
            ).fetchone()[0])
            total = int(connection.execute("SELECT COUNT(*) FROM questions").fetchone()[0])
            chunks = int(connection.execute("SELECT COUNT(*) FROM qf_rag_chunks").fetchone()[0])
            nodes = int(connection.execute("SELECT COUNT(*) FROM qf_knowledge_nodes").fetchone()[0])
            edges = int(connection.execute("SELECT COUNT(*) FROM qf_knowledge_edges").fetchone()[0])
            links = int(connection.execute("SELECT COUNT(*) FROM qf_question_concepts").fetchone()[0])
        return {
            "version": SEMANTIC_VERSION,
            "indexed_questions": indexed,
            "total_questions": total,
            "coverage": round(indexed / total * 100.0, 1) if total else 100.0,
            "rag_chunks": chunks,
            "knowledge_nodes": nodes,
            "knowledge_edges": edges,
            "concept_links": links,
            "engine": "hybrid_local_hashing",
            "offline_ready": True,
        }

    def rebuild_semantic_index(self) -> dict:
        with self.connect() as connection:
            rows = connection.execute("SELECT uid, data_json FROM questions ORDER BY uid").fetchall()
            active = {str(row["uid"]) for row in rows}
            if active:
                placeholders = ",".join("?" for _ in active)
                connection.execute(f"DELETE FROM qf_question_concepts WHERE question_uid NOT IN ({placeholders})", tuple(active))
                connection.execute(f"DELETE FROM qf_semantic_signatures WHERE question_uid NOT IN ({placeholders})", tuple(active))
                connection.execute(f"DELETE FROM qf_rag_chunks WHERE source_kind = 'question' AND source_ref NOT IN ({placeholders})", tuple(active))
            else:
                connection.execute("DELETE FROM qf_question_concepts")
                connection.execute("DELETE FROM qf_semantic_signatures")
                connection.execute("DELETE FROM qf_rag_chunks WHERE source_kind = 'question'")
            for row in rows:
                try:
                    question = json.loads(row["data_json"] or "{}")
                except Exception:
                    question = {}
                self._index_semantic_assets(connection, str(row["uid"]), question)
            # Remove arestas/nós que deixaram de ser referenciados após exclusões ou reclassificações.
            connection.execute(
                "DELETE FROM qf_knowledge_edges WHERE source_node_id NOT IN (SELECT node_id FROM qf_question_concepts) OR target_node_id NOT IN (SELECT node_id FROM qf_question_concepts)"
            )
            connection.execute(
                "DELETE FROM qf_knowledge_nodes WHERE id NOT IN (SELECT node_id FROM qf_question_concepts)"
            )
        return self.semantic_index_summary()

    def knowledge_graph_for_question(self, uid: str) -> dict:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT n.id, n.node_type, n.label, n.normalized_label, qc.relation, qc.confidence
                FROM qf_question_concepts qc
                JOIN qf_knowledge_nodes n ON n.id = qc.node_id
                WHERE qc.question_uid = ?
                ORDER BY n.node_type, n.label COLLATE NOCASE
                """,
                (str(uid),),
            ).fetchall()
            node_ids = [str(row["id"]) for row in rows]
            edges: list[dict] = []
            if node_ids:
                placeholders = ",".join("?" for _ in node_ids)
                edge_rows = connection.execute(
                    f"""
                    SELECT source_node_id, target_node_id, relation, weight
                    FROM qf_knowledge_edges
                    WHERE source_node_id IN ({placeholders}) AND target_node_id IN ({placeholders})
                    ORDER BY weight DESC, relation
                    """,
                    (*node_ids, *node_ids),
                ).fetchall()
                edges = [dict(row) for row in edge_rows]
        return {
            "version": SEMANTIC_VERSION,
            "question_uid": str(uid),
            "nodes": [dict(row) for row in rows],
            "edges": edges,
        }

    def retrieve_rag_context(self, uid: str, query: str = "", *, limit: int = 8) -> dict:
        safe_limit = max(1, min(20, int(limit or 8)))
        with self.connect() as connection:
            row = connection.execute(
                "SELECT subject, primary_topic, statement, data_json FROM questions WHERE uid = ?", (str(uid),)
            ).fetchone()
            if not row:
                raise ValueError("Questão não encontrada.")
            try:
                question = json.loads(row["data_json"] or "{}")
            except Exception:
                question = {}
            subject = str(row["subject"] or "")
            topic = str(row["primary_topic"] or "")
            effective_query = str(query or "").strip() or " ".join(
                part for part in (subject, topic, str(row["statement"] or "")) if part
            )[:3000]
            # Pré-seleção por matéria reduz custo sem tornar a busca dependente da taxonomia.
            candidate_rows = connection.execute(
                """
                SELECT id, source_kind, source_ref, title, subject, topic, content, vector_json, metadata_json
                FROM qf_rag_chunks
                WHERE subject = ? COLLATE NOCASE OR ? = ''
                ORDER BY updated_at DESC
                LIMIT 700
                """,
                (subject, subject),
            ).fetchall()
            if len(candidate_rows) < max(40, safe_limit * 4):
                candidate_rows = connection.execute(
                    """
                    SELECT id, source_kind, source_ref, title, subject, topic, content, vector_json, metadata_json
                    FROM qf_rag_chunks ORDER BY updated_at DESC LIMIT 900
                    """
                ).fetchall()
        query_vector = hashed_embedding(effective_query)
        ranked: list[dict] = []
        for item in candidate_rows:
            content = str(item["content"] or "")
            metadata_text = " ".join(
                str(value or "") for value in (item["title"], item["subject"], item["topic"])
            )
            try:
                content_vector = json.loads(item["vector_json"] or "[]")
            except Exception:
                content_vector = []
            scores = hybrid_retrieval_score(
                effective_query, content, metadata_text=metadata_text,
                subject_match=bool(subject and str(item["subject"] or "").casefold() == subject.casefold()),
                query_vector=query_vector,
                content_vector=content_vector or None,
            )
            if scores["score"] < 0.12:
                continue
            try:
                metadata = json.loads(item["metadata_json"] or "{}")
            except Exception:
                metadata = {}
            ranked.append({
                "id": str(item["id"]), "source_kind": str(item["source_kind"]),
                "source_ref": str(item["source_ref"]), "title": str(item["title"] or ""),
                "subject": str(item["subject"] or ""), "topic": str(item["topic"] or ""),
                "content": content, "metadata": metadata, "scores": scores,
                "same_question": str(item["source_ref"]) == str(uid),
            })
        ranked.sort(key=lambda item: item["scores"]["score"], reverse=True)
        return {
            "version": SEMANTIC_VERSION,
            "query": effective_query,
            "engine": "hybrid lexical + semantic hashing + metadata rerank",
            "items": ranked[:safe_limit],
            "total_candidates": len(candidate_rows),
        }

    def import_extraction(self, result: dict) -> dict:
        import_id = str(uuid.uuid4())
        source_file = str(result.get("source_file", "PDF"))
        inserted = duplicates = repaired = pending = 0
        now = utc_now()

        with self.connect() as connection:
            for question in result.get("questions", []):
                self._apply_lesson_catalog(connection, question)
                source = question.setdefault("fonte", {})
                source_path = str(result.get("source_path", "")).strip()
                if source_path and not str(source.get("caminho_arquivo", "")).strip():
                    source["caminho_arquivo"] = source_path
                source_key = self._source_key(question)
                fingerprint = str(question.get("fingerprint", "")).strip()
                if fingerprint:
                    existing = connection.execute(
                        "SELECT uid, source_key, data_json, confidence, review_status FROM questions WHERE source_key = ? OR fingerprint = ?",
                        (source_key, fingerprint),
                    ).fetchone()
                    excluded = connection.execute(
                        "SELECT id FROM excluded_questions WHERE source_key = ? OR fingerprint = ?",
                        (source_key, fingerprint),
                    ).fetchone()
                else:
                    existing = connection.execute(
                        "SELECT uid, source_key, data_json, confidence, review_status FROM questions WHERE source_key = ?",
                        (source_key,),
                    ).fetchone()
                    excluded = connection.execute(
                        "SELECT id FROM excluded_questions WHERE source_key = ?",
                        (source_key,),
                    ).fetchone()
                if existing and not excluded:
                    # 5.5.7: old OCR-based QConcursos imports may already exist with
                    # the correct Q-code but empty statement/options.  Re-importing
                    # the same PDF with the native-layout parser should repair those
                    # records instead of silently treating them as immutable duplicates.
                    incoming_method = str(question.get("ocr", {}).get("metodo", "")) if isinstance(question.get("ocr"), dict) else ""
                    try:
                        existing_data = json.loads(existing["data_json"] or "{}")
                    except Exception:
                        existing_data = {}
                    existing_alternatives = list(existing_data.get("alternativas", []) or [])
                    existing_keys = [str(item.get("chave", "")).upper() for item in existing_alternatives if isinstance(item, dict)]
                    existing_answer = str(existing_data.get("gabarito", "")).upper()
                    existing_broken = bool(
                        len(str(existing_data.get("enunciado", "")).strip()) < 18
                        or len(existing_alternatives) < 2
                        or not existing_answer
                        or existing_answer not in existing_keys
                    )
                    incoming_alternatives = list(question.get("alternativas", []) or [])
                    incoming_keys = [str(item.get("chave", "")).upper() for item in incoming_alternatives if isinstance(item, dict)]
                    incoming_answer = str(question.get("gabarito", "")).upper()
                    incoming_complete = bool(
                        len(str(question.get("enunciado", "")).strip()) >= 18
                        and len(incoming_alternatives) >= 2
                        and incoming_answer
                        and incoming_answer in incoming_keys
                    )
                    same_source_key = str(existing["source_key"] or "").casefold() == str(source_key).casefold()
                    if (
                        same_source_key
                        and incoming_method == "texto_nativo_qconcursos_layout"
                        and existing_broken
                        and incoming_complete
                    ):
                        merged = dict(existing_data)
                        merged.update(question)
                        # Never discard a user-written explanation while repairing
                        # extraction fields from the original PDF.
                        if str(existing_data.get("explicacao", "")).strip() and not str(question.get("explicacao", "")).strip():
                            merged["explicacao"] = existing_data.get("explicacao")
                        old_classification = existing_data.get("classificacao_planilha", {}) if isinstance(existing_data.get("classificacao_planilha"), dict) else {}
                        new_classification = question.get("classificacao_planilha", {}) if isinstance(question.get("classificacao_planilha"), dict) else {}
                        if str(old_classification.get("metodo", "")) == "correcao_manual_banco" and not str(new_classification.get("metodo", "")).startswith("importacao_contextual"):
                            for key in ("materia", "aula_planilha", "assunto", "assuntos", "trilha_assuntos", "classificacao_planilha"):
                                if key in existing_data:
                                    merged[key] = existing_data[key]
                        uid = str(existing["uid"])
                        merged["database_uid"] = uid
                        review = merged.setdefault("revisao", {})
                        status = str(review.get("status", "pendente"))
                        confidence = float(review.get("confianca", 0) or 0)
                        primary_topic, lesson, taxonomy_status, taxonomy_confidence, taxonomy_source = self._taxonomy_values(merged)
                        merged_source = merged.get("fonte", {}) if isinstance(merged.get("fonte"), dict) else {}
                        connection.execute(
                            """
                            UPDATE questions
                            SET fingerprint = ?, subject = ?, primary_topic = ?, topics_text = ?, lesson = ?, lesson_title = ?,
                                taxonomy_status = ?, taxonomy_confidence = ?, taxonomy_source = ?,
                                board = ?, exam_year = ?, agency = ?, exam_name = ?, question_type = ?,
                                answer = ?, statement = ?, review_status = ?, confidence = ?,
                                source_file = ?, source_page = ?, updated_at = ?, data_json = ?
                            WHERE uid = ?
                            """,
                            (
                                str(merged.get("fingerprint", "")),
                                str(merged.get("materia", "")),
                                primary_topic,
                                self._topics_text(merged),
                                lesson,
                                str(merged.get("titulo_aula", "")),
                                taxonomy_status,
                                taxonomy_confidence,
                                taxonomy_source,
                                str(merged.get("banca", "")),
                                merged.get("ano"),
                                str(merged.get("orgao", "")),
                                str(merged.get("prova", "")),
                                str(merged.get("tipo", "")),
                                str(merged.get("gabarito", "")),
                                str(merged.get("enunciado", "")),
                                status,
                                confidence,
                                str(merged_source.get("arquivo", source_file)),
                                merged_source.get("pagina_inicial"),
                                now,
                                json.dumps(merged, ensure_ascii=False),
                                uid,
                            ),
                        )
                        self._write_intelligence_columns(connection, uid, merged)
                        self._index_semantic_assets(connection, uid, merged)
                        repaired += 1
                        if status == "pendente":
                            pending += 1
                        continue
                    duplicates += 1
                    continue
                if excluded:
                    duplicates += 1
                    continue

                uid = str(uuid.uuid4())
                review = question.setdefault("revisao", {})
                status = str(review.get("status", "pendente"))
                confidence = float(review.get("confianca", 0) or 0)
                if status == "pendente":
                    pending += 1
                source = question.get("fonte", {})
                primary_topic, lesson, taxonomy_status, taxonomy_confidence, taxonomy_source = (
                    self._taxonomy_values(question)
                )
                question["database_uid"] = uid
                connection.execute(
                    """
                    INSERT INTO questions (
                        uid, source_key, source_code, fingerprint, subject, primary_topic,
                        topics_text, lesson, lesson_title, taxonomy_status, taxonomy_confidence,
                        taxonomy_source, board, exam_year, agency, exam_name, question_type,
                        answer, statement, review_status, confidence, source_file, source_page,
                        created_at, updated_at, data_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        uid,
                        source_key,
                        str(question.get("codigo_origem", question.get("id", ""))),
                        fingerprint,
                        str(question.get("materia", "")),
                        primary_topic,
                        self._topics_text(question),
                        lesson,
                        str(question.get("titulo_aula", "")),
                        taxonomy_status,
                        taxonomy_confidence,
                        taxonomy_source,
                        str(question.get("banca", "")),
                        question.get("ano"),
                        str(question.get("orgao", "")),
                        str(question.get("prova", "")),
                        str(question.get("tipo", "")),
                        str(question.get("gabarito", "")),
                        str(question.get("enunciado", "")),
                        status,
                        confidence,
                        str(source.get("arquivo", source_file)),
                        source.get("pagina_inicial"),
                        now,
                        now,
                        json.dumps(question, ensure_ascii=False),
                    ),
                )
                self._write_intelligence_columns(connection, uid, question)
                self._index_semantic_assets(connection, uid, question)
                inserted += 1

            connection.execute(
                """
                INSERT INTO imports (
                    id, source_file, imported_at, extracted_count, inserted_count,
                    duplicate_count, pending_count, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    import_id,
                    source_file,
                    now,
                    len(result.get("questions", [])),
                    inserted,
                    duplicates,
                    pending,
                    json.dumps(
                        {
                            "schema": result.get("schema"),
                            "answers_found": result.get("answers_found"),
                            "starts_found": result.get("starts_found"),
                            "taxonomy": result.get("taxonomy"),
                            "repaired_existing": repaired,
                        },
                        ensure_ascii=False,
                    ),
                ),
            )
        return {
            "import_id": import_id,
            "extracted": len(result.get("questions", [])),
            "inserted": inserted,
            "duplicates": duplicates,
            "repaired": repaired,
            "pending": pending,
        }

    def distinct_subjects(self) -> list[str]:
        """Return normalized subject names currently present in the question bank."""
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT DISTINCT TRIM(subject) AS subject
                FROM questions
                WHERE TRIM(COALESCE(subject, '')) != ''
                ORDER BY subject COLLATE NOCASE
                """
            ).fetchall()
        return [str(row["subject"]).strip() for row in rows if str(row["subject"] or "").strip()]

    def distinct_lessons(self, subject: str = "") -> list[str]:
        """Return lesson labels present in the bank, optionally scoped to a subject."""
        clauses = ["TRIM(COALESCE(lesson, '')) != ''"]
        values: list[str] = []
        if str(subject or "").strip():
            clauses.append("subject = ? COLLATE NOCASE")
            values.append(str(subject).strip())
        query = f"""
            SELECT DISTINCT TRIM(lesson) AS lesson
            FROM questions
            WHERE {' AND '.join(clauses)}
            ORDER BY lesson COLLATE NOCASE
        """
        with self.connect() as connection:
            rows = connection.execute(query, values).fetchall()
        return [str(row["lesson"]).strip() for row in rows if str(row["lesson"] or "").strip()]

    def organize_lesson_group(
        self,
        source_subject: str,
        source_lesson: str,
        target_subject: str,
        target_lesson: str,
        lesson_title: str,
    ) -> dict:
        """Normalize one subject/lesson group and remember aliases for future imports."""
        source_subject = re.sub(r"\s+", " ", str(source_subject or "")).strip()
        source_lesson = re.sub(r"\s+", " ", str(source_lesson or "")).strip()
        target_subject = re.sub(r"\s+", " ", str(target_subject or "")).strip()
        target_lesson = _canonical_lesson_label(target_lesson)
        lesson_title = re.sub(r"\s+", " ", str(lesson_title or "")).strip()
        if not source_subject:
            raise ValueError("Informe a matéria de origem do grupo.")
        if not source_lesson:
            raise ValueError("Informe a aula de origem do grupo.")
        if not target_subject:
            raise ValueError("Informe a matéria correta.")
        if not target_lesson:
            raise ValueError("Informe a aula correta.")
        if not lesson_title:
            raise ValueError("Informe o título canônico da aula.")

        source_subject_key = _catalog_key(source_subject)
        source_lesson_key = _lesson_catalog_key(source_lesson)
        now = utc_now()
        updated = 0
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT uid, subject, lesson, data_json FROM questions"
            ).fetchall()
            matched = [
                row for row in rows
                if _catalog_key(row["subject"]) == source_subject_key
                and _lesson_catalog_key(row["lesson"]) == source_lesson_key
            ]
            for row in matched:
                try:
                    question = json.loads(row["data_json"] or "{}")
                except Exception:
                    question = {}
                old_subject = str(question.get("materia") or row["subject"] or "").strip()
                old_lesson = str(question.get("aula_planilha") or row["lesson"] or "").strip()
                question["materia"] = target_subject
                question["aula_planilha"] = target_lesson
                question["titulo_aula"] = lesson_title
                primary = str(question.get("assunto", "")).strip()
                question["trilha_assuntos"] = [item for item in (target_subject, target_lesson, primary) if item]
                classification = question.get("classificacao_planilha")
                if not isinstance(classification, dict):
                    classification = {}
                classification.update(
                    {
                        "status": "classificado",
                        "confianca": 1.0,
                        "metodo": "catalogo_canonico_aulas",
                        "titulo_aula": lesson_title,
                    }
                )
                changed_parent = (
                    _catalog_key(old_subject) != _catalog_key(target_subject)
                    or _lesson_catalog_key(old_lesson) != _lesson_catalog_key(target_lesson)
                )
                if changed_parent:
                    classification.pop("referencia", None)
                    classification.pop("contexto_task_id", None)
                    question.pop("contexto_importacao_estudos", None)
                question["classificacao_planilha"] = classification
                history = question.get("historico_classificacao")
                if not isinstance(history, list):
                    history = []
                history.append(
                    {
                        "alterado_em": now,
                        "origem": "organizacao_canonica_aula",
                        "materia_anterior": old_subject,
                        "aula_anterior": old_lesson,
                        "materia_nova": target_subject,
                        "aula_nova": target_lesson,
                        "titulo_aula": lesson_title,
                    }
                )
                question["historico_classificacao"] = history[-100:]
                connection.execute(
                    """
                    UPDATE questions
                    SET subject = ?, lesson = ?, lesson_title = ?, taxonomy_status = ?,
                        taxonomy_confidence = ?, taxonomy_source = ?, updated_at = ?, data_json = ?
                    WHERE uid = ?
                    """,
                    (
                        target_subject,
                        target_lesson,
                        lesson_title,
                        "classificado",
                        1.0,
                        "Catálogo canônico de aulas",
                        now,
                        json.dumps(question, ensure_ascii=False),
                        str(row["uid"]),
                    ),
                )
                self._write_intelligence_columns(connection, str(row["uid"]), question)
                self._index_semantic_assets(connection, str(row["uid"]), question)
                updated += 1

            aliases = {
                (source_subject_key, source_lesson_key),
                (_catalog_key(target_subject), _lesson_catalog_key(target_lesson)),
            }
            for subject_key, lesson_key in aliases:
                alias_key = f"{subject_key}::{lesson_key}"
                connection.execute(
                    """
                    INSERT INTO qf_bank_lesson_aliases(
                        alias_key, source_subject_key, source_lesson_key,
                        subject, lesson, title, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(alias_key) DO UPDATE SET
                        subject = excluded.subject,
                        lesson = excluded.lesson,
                        title = excluded.title,
                        updated_at = excluded.updated_at
                    """,
                    (
                        alias_key,
                        subject_key,
                        lesson_key,
                        target_subject,
                        target_lesson,
                        lesson_title,
                        now,
                        now,
                    ),
                )
        return {
            "updated": updated,
            "source_subject": source_subject,
            "source_lesson": source_lesson,
            "subject": target_subject,
            "lesson": target_lesson,
            "lesson_title": lesson_title,
        }

    def stats(self) -> dict:
        with self.connect() as connection:
            question_row = connection.execute(
                """
                SELECT COUNT(*) AS total,
                       COALESCE(SUM(review_status = 'pendente'), 0) AS pending,
                       COALESCE(SUM(review_status != 'pendente'), 0) AS approved,
                       COALESCE(SUM(taxonomy_status = 'revisar'), 0) AS taxonomy_review
                FROM questions
                """
            ).fetchone()
            import_row = connection.execute(
                """
                SELECT COUNT(*) AS imports,
                       COALESCE(SUM(duplicate_count), 0) AS duplicates
                FROM imports
                """
            ).fetchone()
        return {
            "total": int(question_row["total"] or 0),
            "pending": int(question_row["pending"] or 0),
            "approved": int(question_row["approved"] or 0),
            "imports": int(import_row["imports"] or 0),
            "duplicates": int(import_row["duplicates"] or 0),
            "taxonomy_review": int(question_row["taxonomy_review"] or 0),
        }

    def bank_intelligence_summary(self) -> dict:
        with self.connect() as connection:
            total = int(connection.execute("SELECT COUNT(*) FROM questions").fetchone()[0])
            avg_quality = float(connection.execute("SELECT COALESCE(AVG(quality_score), 0) FROM questions").fetchone()[0] or 0)
            ready = int(connection.execute("SELECT COUNT(*) FROM questions WHERE curation_status = 'pronta'").fetchone()[0])
            needs_review = int(connection.execute("SELECT COUNT(*) FROM questions WHERE curation_status <> 'pronta'").fetchone()[0])
            with_comment = int(connection.execute("SELECT COUNT(*) FROM questions WHERE commentary_source IS NOT NULL AND commentary_source <> 'sem_comentario'").fetchone()[0])
            official = int(connection.execute("SELECT COUNT(*) FROM questions WHERE origin_type = 'oficial'").fetchone()[0])
            unverified = int(connection.execute("SELECT COUNT(*) FROM questions WHERE origin_type = 'nao_informada'").fetchone()[0])
            duplicates = int(connection.execute("SELECT COUNT(*) FROM question_duplicate_candidates WHERE status = 'aberto'").fetchone()[0])
            origins = {str(row[0]): int(row[1]) for row in connection.execute("SELECT origin_type, COUNT(*) FROM questions GROUP BY origin_type").fetchall()}
            curation = {str(row[0]): int(row[1]) for row in connection.execute("SELECT curation_status, COUNT(*) FROM questions GROUP BY curation_status").fetchall()}
            difficulty = {str(row[0] or 'sem_dados'): int(row[1]) for row in connection.execute("SELECT difficulty_label, COUNT(*) FROM questions GROUP BY difficulty_label").fetchall()}
            comments = {str(row[0] or 'sem_comentario'): int(row[1]) for row in connection.execute("SELECT commentary_source, COUNT(*) FROM questions GROUP BY commentary_source").fetchall()}
            quality_bands = {
                "A": int(connection.execute("SELECT COUNT(*) FROM questions WHERE quality_score >= 88").fetchone()[0]),
                "B": int(connection.execute("SELECT COUNT(*) FROM questions WHERE quality_score >= 72 AND quality_score < 88").fetchone()[0]),
                "C": int(connection.execute("SELECT COUNT(*) FROM questions WHERE quality_score >= 52 AND quality_score < 72").fetchone()[0]),
                "D": int(connection.execute("SELECT COUNT(*) FROM questions WHERE quality_score < 52").fetchone()[0]),
            }
            pending_rows = connection.execute(
                "SELECT uid, data_json FROM questions WHERE curation_status <> 'pronta'"
            ).fetchall()
            reviewed_ready_b = int(connection.execute(
                """
                SELECT COUNT(*) FROM questions
                WHERE curation_status='pronta' AND quality_score < 88
                  AND LOWER(COALESCE(review_status,'')) LIKE 'aprovad%'
                """
            ).fetchone()[0] or 0)
            semantic_indexed = int(connection.execute("SELECT COUNT(*) FROM questions WHERE semantic_version = ?", (SEMANTIC_VERSION,)).fetchone()[0])
            semantic_chunks = int(connection.execute("SELECT COUNT(*) FROM qf_rag_chunks").fetchone()[0])
            knowledge_nodes = int(connection.execute("SELECT COUNT(*) FROM qf_knowledge_nodes").fetchone()[0])
            knowledge_edges = int(connection.execute("SELECT COUNT(*) FROM qf_knowledge_edges").fetchone()[0])

        awaiting_approval = 0
        objective_gaps = 0
        for row in pending_rows:
            try:
                question = json.loads(row["data_json"] or "{}")
            except Exception:
                question = {}
            readiness = curation_readiness(question)
            if readiness.get("can_complete_review") and not readiness.get("human_approved"):
                awaiting_approval += 1
            else:
                objective_gaps += 1

        return {
            "total": total, "average_quality": round(avg_quality, 1), "ready": ready,
            "needs_review": needs_review, "with_commentary": with_comment,
            "official": official, "unverified_origin": unverified,
            "open_duplicate_candidates": duplicates, "origins": origins,
            "curation": curation, "difficulty": difficulty, "comments": comments,
            "quality_bands": quality_bands,
            "awaiting_review_completion": awaiting_approval,
            "objective_curation_gaps": objective_gaps,
            "human_review_ready_b": reviewed_ready_b,
            "semantic": {
                "version": SEMANTIC_VERSION,
                "indexed_questions": semantic_indexed,
                "coverage": round(semantic_indexed / total * 100.0, 1) if total else 100.0,
                "rag_chunks": semantic_chunks,
                "knowledge_nodes": knowledge_nodes,
                "knowledge_edges": knowledge_edges,
                "offline_ready": True,
            },
        }

    def rebuild_bank_intelligence_derived(self) -> dict:
        """Recalcula todos os sinais derivados usados pela Curadoria.

        A operação é deliberadamente idempotente e não altera o conteúdo editorial
        bruto (``data_json``). Isso permite corrigir colunas derivadas antigas —
        qualidade, status, comentário e dificuldade empírica — sem transformar um
        simples refresh de painel em uma edição real do banco ou em eventos de Cloud
        Sync.
        """
        changed = 0
        status_changes = 0
        comment_changes = 0
        difficulty_changes = 0
        quality_changes = 0
        with self.connect() as connection:
            # As colunas recalculadas abaixo são declaradas transitórias no Cloud
            # Sync. Assim o refresh não precisa ativar uma supressão global — que
            # poderia esconder uma edição real feita simultaneamente em outra thread.
            attempts_by_uid: dict[str, dict] = {}
            attempts_exists = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='telegram_attempts'"
            ).fetchone()
            if attempts_exists:
                for arow in connection.execute(
                    """
                    SELECT question_uid, COUNT(*) AS attempts,
                           COALESCE(SUM(CASE WHEN is_correct = 1 THEN 1 ELSE 0 END), 0) AS correct,
                           COALESCE(SUM(CASE WHEN perceived_difficulty = 'dificil' THEN 1 ELSE 0 END), 0) AS hard_count
                    FROM telegram_attempts
                    GROUP BY question_uid
                    """
                ).fetchall():
                    attempts_by_uid[str(arow["question_uid"])] = {
                        "attempts": int(arow["attempts"] or 0),
                        "correct": int(arow["correct"] or 0),
                        "hard_count": int(arow["hard_count"] or 0),
                    }

            rows = connection.execute(
                """
                SELECT uid, data_json, origin_type, curation_status, quality_score,
                       commentary_source, rights_status, difficulty_score, difficulty_label
                FROM questions
                """
            ).fetchall()
            for row in rows:
                uid = str(row["uid"])
                try:
                    question = json.loads(row["data_json"] or "{}")
                except Exception:
                    question = {}
                snapshot = intelligence_snapshot(question)
                attempts = attempts_by_uid.get(uid, {"attempts": 0, "correct": 0, "hard_count": 0})
                difficulty = empirical_difficulty(**attempts)
                new_values = (
                    str(snapshot["origin_type"]),
                    str(snapshot["curation_status"]),
                    float(snapshot["quality"]["score"]),
                    str(snapshot["commentary_source"]),
                    str(snapshot["rights_status"]),
                    difficulty["score"],
                    str(difficulty["label"]),
                )
                old_values = (
                    str(row["origin_type"] or ""),
                    str(row["curation_status"] or ""),
                    float(row["quality_score"] or 0),
                    str(row["commentary_source"] or ""),
                    str(row["rights_status"] or ""),
                    row["difficulty_score"],
                    str(row["difficulty_label"] or "sem_dados"),
                )
                if new_values == old_values:
                    continue
                if new_values[1] != old_values[1]:
                    status_changes += 1
                if new_values[2] != old_values[2]:
                    quality_changes += 1
                if new_values[3] != old_values[3]:
                    comment_changes += 1
                if new_values[5:] != old_values[5:]:
                    difficulty_changes += 1
                connection.execute(
                    """
                    UPDATE questions
                    SET origin_type=?, curation_status=?, quality_score=?, commentary_source=?,
                        rights_status=?, difficulty_score=?, difficulty_label=?
                    WHERE uid=?
                    """,
                    (*new_values, uid),
                )
                changed += 1
        return {
            "ok": True,
            "updated": changed,
            "status_changes": status_changes,
            "quality_changes": quality_changes,
            "comment_changes": comment_changes,
            "difficulty_changes": difficulty_changes,
            "summary": self.bank_intelligence_summary(),
        }

    def bank_intelligence_attention(self, kind: str = "curation", *, limit: int = 100) -> dict:
        """Lista a fila real que sustenta cada cartão de atenção da Curadoria."""
        kind = str(kind or "curation").strip().lower()
        safe_limit = max(1, min(500, int(limit or 100)))
        if kind == "duplicates":
            with self.connect() as connection:
                rows = connection.execute(
                    """
                    SELECT d.id, d.question_uid AS uid, q.source_code, q.subject, q.primary_topic,
                           d.similarity, d.reason
                    FROM question_duplicate_candidates d
                    JOIN questions q ON q.uid=d.question_uid
                    WHERE d.status='aberto'
                    ORDER BY d.similarity DESC, d.detected_at DESC
                    LIMIT ?
                    """,
                    (safe_limit,),
                ).fetchall()
                total = int(connection.execute(
                    "SELECT COUNT(*) FROM question_duplicate_candidates WHERE status='aberto'"
                ).fetchone()[0] or 0)
            return {
                "kind": kind, "total": total,
                "items": [{
                    "uid": str(row["uid"]), "code": str(row["source_code"] or ""),
                    "subject": str(row["subject"] or ""), "topic": str(row["primary_topic"] or ""),
                    "score": round(float(row["similarity"] or 0) * 100.0, 1),
                    "missing": [str(row["reason"] or "Comparar possível duplicidade")],
                } for row in rows],
            }

        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT uid, source_code, subject, primary_topic, quality_score, curation_status,
                       commentary_source, difficulty_label, data_json
                FROM questions ORDER BY quality_score ASC, source_code ASC
                """
            ).fetchall()
        items: list[dict] = []
        total = 0
        for row in rows:
            try:
                question = json.loads(row["data_json"] or "{}")
            except Exception:
                question = {}
            quality = calculate_quality(question)
            readiness = curation_readiness(question)
            matches = False
            missing: list[str] = []
            if kind == "curation":
                matches = str(readiness["status"]) != "pronta"
                missing = list(quality.get("missing") or [])
            elif kind == "comments":
                matches = commentary_source(question) == "sem_comentario"
                missing = ["Adicionar uma explicação/comentário estruturado"] if matches else []
            elif kind == "difficulty":
                label = str(row["difficulty_label"] or "sem_dados")
                matches = label == "sem_dados"
                missing = ["Responder a questão para gerar dificuldade empírica"] if matches else []
            else:
                raise ValueError("Tipo de atenção inválido.")
            if not matches:
                continue
            total += 1
            if len(items) < safe_limit:
                items.append({
                    "uid": str(row["uid"]),
                    "code": str(row["source_code"] or question.get("codigo_origem") or ""),
                    "subject": str(row["subject"] or question.get("materia") or ""),
                    "topic": str(row["primary_topic"] or question.get("assunto") or ""),
                    "score": float(quality["score"]),
                    "grade": str(quality["grade"]),
                    "status": str(readiness.get("status") or "revisar"),
                    "review_status": str(readiness.get("review_status") or "pendente"),
                    "human_approved": bool(readiness.get("human_approved")),
                    "auto_approved": bool(readiness.get("auto_approved")),
                    "can_complete_review": bool(readiness.get("can_complete_review")),
                    "blocking_missing": list(readiness.get("blocking_missing") or []),
                    "enrichment_missing": list(readiness.get("enrichment_missing") or []),
                    "prospective_score": float(readiness.get("prospective_score") or quality["score"]),
                    "missing": missing,
                })
        return {"kind": kind, "total": total, "items": items}

    def complete_curation_review(self, uid: str, *, reviewer: str = "") -> dict:
        """Conclui explicitamente a revisão humana sem esconder lacunas críticas.

        A ação é permitida quando a questão tem os controles críticos íntegros e
        alcançaria ao menos a faixa B com a própria aprovação. Lacunas de
        enriquecimento continuam registradas na nota, mas não prendem uma questão
        revisada indefinidamente na fila de Curadoria.
        """
        question = self.get_question(str(uid))
        if not question:
            return {"ok": False, "error": "Questão não encontrada."}
        readiness = curation_readiness(question)
        if readiness.get("human_approved") and readiness.get("status") == "pronta":
            return {"ok": True, "already_complete": True, "summary": self.bank_intelligence_summary(), "intelligence": intelligence_snapshot(question)}
        if not readiness.get("can_complete_review"):
            blocking = list(readiness.get("blocking_missing") or [])
            if blocking:
                detail = ", ".join(blocking)
                return {"ok": False, "error": f"A revisão ainda não pode ser concluída. Corrija primeiro: {detail}.", "blocking_missing": blocking}
            return {"ok": False, "error": "A questão ainda não atingiu a qualidade mínima para conclusão da revisão."}

        now = utc_now()
        review = question.setdefault("revisao", {})
        review.update({"status": "aprovado", "confianca": 1.0, "alertas": [], "aprovado_em": now, "metodo": "curadoria_manual"})
        curation = question.setdefault("curadoria", {})
        curation["revisado_em"] = now
        curation["revisao_humana_concluida"] = True
        curation["revisao_humana_em"] = now
        if str(reviewer or "").strip():
            curation["responsavel"] = str(reviewer).strip()
            curation["revisor_humano"] = str(reviewer).strip()
        self.update_question(str(uid), question, change_source="curadoria_manual")
        refreshed = self.get_question(str(uid)) or question
        return {
            "ok": True,
            "question": refreshed,
            "intelligence": intelligence_snapshot(refreshed),
            "summary": self.bank_intelligence_summary(),
        }

    @staticmethod
    def _attempt_metrics(connection: sqlite3.Connection, uid: str) -> dict:
        exists = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='telegram_attempts'"
        ).fetchone()
        if not exists:
            return {"attempts": 0, "correct": 0, "hard_count": 0}
        row = connection.execute(
            """
            SELECT COUNT(*) AS attempts,
                   COALESCE(SUM(CASE WHEN is_correct = 1 THEN 1 ELSE 0 END), 0) AS correct,
                   COALESCE(SUM(CASE WHEN perceived_difficulty = 'dificil' THEN 1 ELSE 0 END), 0) AS hard_count
            FROM telegram_attempts WHERE question_uid = ?
            """,
            (str(uid),),
        ).fetchone()
        return {
            "attempts": int(row["attempts"] or 0),
            "correct": int(row["correct"] or 0),
            "hard_count": int(row["hard_count"] or 0),
        }

    def _scan_duplicate_candidates(self, connection: sqlite3.Connection, uid: str, question: dict) -> list[dict]:
        statement = str(question.get("enunciado", "") or "").strip()
        if len(statement) < 35:
            return []
        board = str(question.get("banca", "") or "").strip()
        subject = str(question.get("materia", "") or "").strip()
        year = question.get("ano")
        clauses = ["uid <> ?", "length(statement) >= 35"]
        values: list[object] = [str(uid)]
        facets: list[str] = []
        if board:
            facets.append("board = ? COLLATE NOCASE")
            values.append(board)
        if subject:
            facets.append("subject = ? COLLATE NOCASE")
            values.append(subject)
        if year:
            facets.append("exam_year = ?")
            values.append(year)
        if facets:
            clauses.append("(" + " OR ".join(facets) + ")")
        rows = connection.execute(
            f"SELECT uid, source_code, subject, board, exam_year, statement, data_json FROM questions WHERE {' AND '.join(clauses)} ORDER BY updated_at DESC LIMIT 420",
            values,
        ).fetchall()
        found: list[dict] = []
        now = utc_now()
        for row in rows:
            lexical = duplicate_similarity(statement, str(row["statement"] or ""))
            # Um piso lexical barato evita calcular o vetor para candidatos totalmente alheios.
            if lexical < 0.33:
                continue
            try:
                candidate_question = json.loads(row["data_json"] or "{}")
            except Exception:
                candidate_question = {"enunciado": str(row["statement"] or "")}
            hybrid = semantic_duplicate_score(question, candidate_question, lexical_similarity=lexical)
            # Enunciados quase idênticos continuam sendo capturados, mas adaptações
            # semanticamente equivalentes agora podem aparecer mesmo com pequenas reescritas.
            if hybrid["score"] < 0.71 and lexical < 0.82:
                continue
            left, right = sorted((str(uid), str(row["uid"])))
            reason = (
                f"similaridade híbrida {hybrid['score'] * 100:.1f}% "
                f"(texto {hybrid['lexical'] * 100:.1f}% · vetor {hybrid['vector'] * 100:.1f}% · taxonomia {hybrid['taxonomy'] * 100:.1f}%)"
            )
            details = json.dumps(hybrid, ensure_ascii=False)
            connection.execute(
                """
                INSERT INTO question_duplicate_candidates(
                    id, question_uid, candidate_uid, similarity, reason, status, created_at, method, details_json
                ) VALUES (?, ?, ?, ?, ?, 'aberto', ?, ?, ?)
                ON CONFLICT(question_uid, candidate_uid) DO UPDATE SET
                    similarity = excluded.similarity,
                    reason = excluded.reason,
                    method = excluded.method,
                    details_json = excluded.details_json
                """,
                (
                    str(uuid.uuid4()), left, right, float(hybrid["score"]), reason, now,
                    str(hybrid["method"]), details,
                ),
            )
            found.append({
                "uid": str(row["uid"]), "code": str(row["source_code"] or ""),
                "subject": str(row["subject"] or ""), "board": str(row["board"] or ""),
                "year": row["exam_year"], "similarity": round(hybrid["score"] * 100.0, 1),
                "reason": reason, "method": hybrid["method"], "signals": hybrid,
            })
        found.sort(key=lambda item: item["similarity"], reverse=True)
        return found[:12]

    def refresh_question_intelligence(self, uid: str, *, scan_duplicates: bool = True) -> dict:
        with self.connect() as connection:
            row = connection.execute("SELECT data_json FROM questions WHERE uid = ?", (str(uid),)).fetchone()
            if not row:
                raise ValueError("Questão não encontrada.")
            question = json.loads(row["data_json"] or "{}")
            snapshot = intelligence_snapshot(question)
            attempts = self._attempt_metrics(connection, str(uid))
            difficulty = empirical_difficulty(**attempts)
            # Inteligência é derivada. Consultar/abrir uma questão não pode reescrever
            # o conteúdo editorial nem gerar um evento de Cloud Sync. Mantemos o
            # snapshot apenas na resposta e materializamos somente colunas derivadas.
            duplicates = self._scan_duplicate_candidates(connection, str(uid), question) if scan_duplicates else []
            self._write_intelligence_columns(connection, str(uid), question)
            self._index_semantic_assets(connection, str(uid), question)
            connection.execute(
                """UPDATE questions SET difficulty_score = ?, difficulty_label = ? WHERE uid = ?""",
                (difficulty["score"], difficulty["label"], str(uid)),
            )
            duplicate_rows = connection.execute(
                """
                SELECT d.id, d.question_uid, d.candidate_uid, d.similarity, d.reason, d.status, d.method, d.details_json,
                       CASE WHEN d.question_uid = ? THEN q2.uid ELSE q1.uid END AS other_uid,
                       CASE WHEN d.question_uid = ? THEN q2.source_code ELSE q1.source_code END AS other_code,
                       CASE WHEN d.question_uid = ? THEN q2.subject ELSE q1.subject END AS other_subject
                FROM question_duplicate_candidates d
                JOIN questions q1 ON q1.uid = d.question_uid
                JOIN questions q2 ON q2.uid = d.candidate_uid
                WHERE (d.question_uid = ? OR d.candidate_uid = ?) AND d.status = 'aberto'
                ORDER BY d.similarity DESC LIMIT 20
                """,
                (str(uid), str(uid), str(uid), str(uid), str(uid)),
            ).fetchall()
        return {
            **snapshot,
            "difficulty": difficulty,
            "attempts": attempts,
            "duplicate_candidates": [
                {
                    "id": str(item["id"]), "uid": str(item["other_uid"]),
                    "code": str(item["other_code"] or ""), "subject": str(item["other_subject"] or ""),
                    "similarity": round(float(item["similarity"] or 0) * 100.0, 1),
                    "reason": str(item["reason"] or ""),
                    "method": str(item["method"] or ""),
                    "signals": json.loads(item["details_json"] or "{}") if str(item["details_json"] or "").strip() else {},
                } for item in duplicate_rows
            ],
        }

    def resolve_duplicate_candidate(self, candidate_id: str, *, duplicate: bool = False) -> bool:
        status = "confirmado" if duplicate else "descartado"
        with self.connect() as connection:
            cursor = connection.execute(
                "UPDATE question_duplicate_candidates SET status = ?, resolved_at = ? WHERE id = ?",
                (status, utc_now(), str(candidate_id)),
            )
            return bool(cursor.rowcount)

    def list_questions_page(
        self,
        search: str = "",
        status: str = "todos",
        *,
        subject: str = "",
        lesson: str = "",
        offset: int = 0,
        limit: int = 500,
    ) -> tuple[int, list[dict]]:
        """Return a real SQL page instead of materializing the entire bank.

        Optional subject/lesson filters are applied in SQL so the correction
        workspace remains responsive even with a large local database.
        """
        clauses: list[str] = []
        values: list = []
        if search.strip():
            term = f"%{search.strip()}%"
            clauses.append(
                "(source_code LIKE ? OR subject LIKE ? OR primary_topic LIKE ? OR "
                "topics_text LIKE ? OR lesson LIKE ? OR board LIKE ? OR agency LIKE ? "
                "OR statement LIKE ?)"
            )
            values.extend([term] * 8)
        if status != "todos":
            clauses.append("review_status = ?")
            values.append(status)
        if str(subject or "").strip():
            clauses.append("subject = ? COLLATE NOCASE")
            values.append(str(subject).strip())
        if str(lesson or "").strip():
            clauses.append("lesson = ? COLLATE NOCASE")
            values.append(str(lesson).strip())
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        safe_offset = max(0, int(offset or 0))
        safe_limit = max(1, min(5000, int(limit or 500)))
        select_query = f"""
            SELECT uid, source_code, subject, primary_topic, topics_text, lesson, lesson_title,
                   taxonomy_status, taxonomy_confidence, board, exam_year, agency,
                   question_type, answer, review_status, confidence, source_file,
                   source_page, origin_type, curation_status, quality_score,
                   difficulty_label, commentary_source, substr(statement, 1, 280) AS statement
            FROM questions
            {where}
            ORDER BY exam_year DESC, source_code ASC
            LIMIT ? OFFSET ?
        """
        with self.connect() as connection:
            total = int(connection.execute(f"SELECT COUNT(*) FROM questions {where}", values).fetchone()[0])
            rows = [
                dict(row)
                for row in connection.execute(select_query, [*values, safe_limit, safe_offset]).fetchall()
            ]
        return total, rows

    def list_questions(
        self,
        search: str = "",
        status: str = "todos",
        limit: int = 2000,
    ) -> list[dict]:
        clauses: list[str] = []
        values: list = []
        if search.strip():
            term = f"%{search.strip()}%"
            clauses.append(
                "(source_code LIKE ? OR subject LIKE ? OR primary_topic LIKE ? OR "
                "topics_text LIKE ? OR lesson LIKE ? OR board LIKE ? OR agency LIKE ? "
                "OR statement LIKE ?)"
            )
            values.extend([term] * 8)
        if status != "todos":
            clauses.append("review_status = ?")
            values.append(status)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        query = f"""
            SELECT uid, source_code, subject, primary_topic, topics_text, lesson, lesson_title,
                   taxonomy_status, taxonomy_confidence, board, exam_year, agency,
                   question_type, answer, review_status, confidence, source_file,
                   source_page, origin_type, curation_status, quality_score,
                   difficulty_label, commentary_source, statement
            FROM questions
            {where}
            ORDER BY exam_year DESC, source_code ASC
            LIMIT ?
        """
        values.append(limit)
        with self.connect() as connection:
            return [dict(row) for row in connection.execute(query, values).fetchall()]

    def get_question(self, uid: str) -> dict | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT data_json FROM questions WHERE uid = ?", (uid,)
            ).fetchone()
        return json.loads(row[0]) if row else None

    def question_code_history(self, uid: str, limit: int = 50) -> list[dict]:
        safe_limit = max(1, min(500, int(limit or 50)))
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT old_code, new_code, changed_at, changed_via,
                       source_key_before, source_key_after
                FROM question_code_history
                WHERE question_uid = ?
                ORDER BY changed_at DESC, rowid DESC
                LIMIT ?
                """,
                (uid, safe_limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def update_question(
        self,
        uid: str,
        question: dict,
        *,
        change_source: str = "sistema",
    ) -> dict:
        """Atualiza a questão e sincroniza uma eventual troca de código.

        O UID permanece estável; portanto, ciclos de estudo, respostas e envios
        continuam vinculados à mesma questão. O código visível, a chave de
        origem e todas as referências de código no JSON são atualizadas na
        mesma transação, com registro independente de auditoria.
        """
        now = utc_now()
        review = question.setdefault("revisao", {})
        status = str(review.get("status", "pendente"))
        confidence = float(review.get("confianca", 0) or 0)
        primary_topic, lesson, taxonomy_status, taxonomy_confidence, taxonomy_source = (
            self._taxonomy_values(question)
        )
        question["database_uid"] = uid

        with self.connect() as connection:
            current_row = connection.execute(
                "SELECT source_code, source_key, data_json FROM questions WHERE uid = ?",
                (uid,),
            ).fetchone()
            if not current_row:
                raise ValueError("Questão não encontrada para atualização.")

            current_json = json.loads(current_row["data_json"])
            old_code = str(
                current_row["source_code"]
                or current_json.get("codigo_origem")
                or current_json.get("id")
                or ""
            ).strip()
            requested = question.get("codigo_origem", old_code)
            new_code = _normalize_question_code(requested)
            code_changed = new_code != old_code

            if code_changed:
                duplicate = connection.execute(
                    """
                    SELECT uid, source_code FROM questions
                    WHERE uid <> ? AND LOWER(TRIM(source_code)) = LOWER(TRIM(?))
                    LIMIT 1
                    """,
                    (uid, new_code),
                ).fetchone()
                if duplicate:
                    raise ValueError(
                        f"Já existe outra questão cadastrada com o código {new_code}."
                    )
                _sync_nested_code_references(question, old_code, new_code)
                question["codigo_origem"] = new_code
                if not str(question.get("id", "")).strip() or str(question.get("id", "")).strip().casefold() == old_code.casefold():
                    question["id"] = new_code
                source = question.setdefault("fonte", {})
                if isinstance(source, dict):
                    source["codigo"] = new_code
                history = question.setdefault("historico_codigos", [])
                if not isinstance(history, list):
                    history = []
                    question["historico_codigos"] = history
                history.append(
                    {
                        "codigo_anterior": old_code,
                        "codigo_novo": new_code,
                        "alterado_em": now,
                        "origem": str(change_source or "sistema"),
                    }
                )
                # Evita crescimento ilimitado no JSON sem apagar a auditoria SQL.
                question["historico_codigos"] = history[-100:]
            else:
                question["codigo_origem"] = new_code

            source = question.get("fonte", {}) if isinstance(question.get("fonte"), dict) else {}
            new_source_key = self._source_key(question)
            source_key_conflict = connection.execute(
                "SELECT uid FROM questions WHERE uid <> ? AND LOWER(source_key) = LOWER(?) LIMIT 1",
                (uid, new_source_key),
            ).fetchone()
            if source_key_conflict:
                raise ValueError(
                    "O novo código produziria uma chave de origem já usada por outra questão."
                )

            connection.execute(
                """
                UPDATE questions
                SET source_key = ?, source_code = ?,
                    subject = ?, primary_topic = ?, topics_text = ?, lesson = ?, lesson_title = ?,
                    taxonomy_status = ?, taxonomy_confidence = ?, taxonomy_source = ?,
                    board = ?, exam_year = ?, agency = ?, exam_name = ?, question_type = ?,
                    answer = ?, statement = ?, review_status = ?, confidence = ?,
                    source_file = ?, source_page = ?, updated_at = ?, data_json = ?
                WHERE uid = ?
                """,
                (
                    new_source_key,
                    new_code,
                    str(question.get("materia", "")),
                    primary_topic,
                    self._topics_text(question),
                    lesson,
                    str(question.get("titulo_aula", "")),
                    taxonomy_status,
                    taxonomy_confidence,
                    taxonomy_source,
                    str(question.get("banca", "")),
                    question.get("ano"),
                    str(question.get("orgao", "")),
                    str(question.get("prova", "")),
                    str(question.get("tipo", "")),
                    str(question.get("gabarito", "")),
                    str(question.get("enunciado", "")),
                    status,
                    confidence,
                    str(source.get("arquivo", "")),
                    source.get("pagina_inicial"),
                    now,
                    json.dumps(question, ensure_ascii=False),
                    uid,
                ),
            )

            self._write_intelligence_columns(connection, uid, question)
            self._index_semantic_assets(connection, uid, question)

            if code_changed:
                connection.execute(
                    """
                    INSERT INTO question_code_history (
                        id, question_uid, old_code, new_code, changed_at, changed_via,
                        source_key_before, source_key_after
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(uuid.uuid4()),
                        uid,
                        old_code,
                        new_code,
                        now,
                        str(change_source or "sistema"),
                        str(current_row["source_key"] or ""),
                        new_source_key,
                    ),
                )

        return {
            "code_changed": code_changed,
            "old_code": old_code,
            "new_code": new_code,
            "changed_at": now if code_changed else None,
        }

    def set_review_status(self, uid: str, status: str) -> None:
        question = self.get_question(uid)
        if not question:
            return
        question.setdefault("revisao", {})["status"] = status
        if status != "pendente":
            question["revisao"]["confianca"] = max(
                0.95, float(question["revisao"].get("confianca", 0) or 0)
            )
            question["revisao"]["alertas"] = []
        self.update_question(uid, question)

    def reclassify_all(self, taxonomy: SpreadsheetTaxonomy) -> dict:
        updated = review = 0
        with self.connect() as connection:
            rows = connection.execute("SELECT uid, data_json FROM questions").fetchall()
        for row in rows:
            question = json.loads(row["data_json"])
            taxonomy.apply_to_question(question)
            if question.get("classificacao_planilha", {}).get("status") == "revisar":
                review += 1
            self.update_question(row["uid"], question)
            updated += 1
        return {"updated": updated, "review": review}


    def archive_question(self, uid: str, *, kind: str = "anulada", reason: str = "") -> bool:
        """Retira a questão da base ativa e mantém uma cópia de auditoria.

        A remoção da tabela ``questions`` aciona as cascatas do ciclo de estudos e
        do Telegram. O registro arquivado impede que a mesma questão anulada seja
        importada novamente de forma silenciosa.
        """
        now = utc_now()
        with self.connect() as connection:
            row = connection.execute(
                "SELECT uid, source_key, source_code, fingerprint, data_json FROM questions WHERE uid = ?",
                (uid,),
            ).fetchone()
            if not row:
                return False
            question = json.loads(row["data_json"])
            review = question.setdefault("revisao", {})
            review["status"] = str(kind or "anulada")
            question["exclusao"] = {
                "tipo": str(kind or "anulada"),
                "motivo": str(reason or ""),
                "data": now,
            }
            connection.execute(
                """
                INSERT INTO excluded_questions (
                    id, original_uid, source_key, source_code, fingerprint,
                    exclusion_kind, exclusion_reason, excluded_at, data_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid.uuid4()),
                    row["uid"],
                    row["source_key"],
                    row["source_code"],
                    row["fingerprint"],
                    str(kind or "anulada"),
                    str(reason or ""),
                    now,
                    json.dumps(question, ensure_ascii=False),
                ),
            )
            self._remove_semantic_assets(connection, uid)
            connection.execute("DELETE FROM questions WHERE uid = ?", (uid,))
        return True

    def excluded_count(self, kind: str | None = None) -> int:
        with self.connect() as connection:
            if kind:
                return int(connection.execute(
                    "SELECT COUNT(*) FROM excluded_questions WHERE exclusion_kind = ?", (kind,)
                ).fetchone()[0])
            return int(connection.execute("SELECT COUNT(*) FROM excluded_questions").fetchone()[0])

    def delete_question(self, uid: str) -> None:
        with self.connect() as connection:
            self._remove_semantic_assets(connection, uid)
            connection.execute("DELETE FROM questions WHERE uid = ?", (uid,))

    def all_questions(self, approved_only: bool = False) -> list[dict]:
        query = "SELECT data_json FROM questions"
        if approved_only:
            query += " WHERE review_status != 'pendente'"
        query += " ORDER BY exam_year DESC, source_code ASC"
        with self.connect() as connection:
            rows = connection.execute(query).fetchall()
        return [json.loads(row[0]) for row in rows]


    def create_manual_question(self, taxonomy: SpreadsheetTaxonomy | None = None) -> str:
        import hashlib

        code = "MANUAL-" + datetime.now().strftime("%Y%m%d%H%M%S%f")
        fingerprint = hashlib.sha256(code.encode("utf-8")).hexdigest()
        question = {
            "id": code,
            "codigo_origem": code,
            "numero_origem": None,
            "materia": "",
            "aula_planilha": "",
            "assunto": "",
            "assuntos": [],
            "trilha_assuntos": [],
            "banca": "",
            "ano": None,
            "orgao": "",
            "prova": "",
            "cargo": "",
            "area": "",
            "especialidade": "",
            "turno": "",
            "tipo": "multipla_escolha",
            "enunciado": "Nova questão — substitua este texto pelo enunciado.",
            "alternativas": [
                {"chave": "A", "texto": "Alternativa A"},
                {"chave": "B", "texto": "Alternativa B"},
            ],
            "gabarito": "A",
            "explicacao": "",
            "fingerprint": fingerprint,
            "fonte": {"plataforma": "QuestFlow Studio", "arquivo": "Questão manual", "pagina_inicial": None, "codigo": code},
            "origem_questao": "manual",
            "proveniencia": {"tipo": "manual", "fonte_primaria": "QuestFlow Studio", "verificada": True},
            "curadoria": {"status": "revisar", "responsavel": "", "notas": ""},
            "comentario_meta": {"origem": "sem_comentario"},
            "tags": [],
            "referencias_legais": [],
            "classificacao_planilha": {
                "status": "revisar",
                "confianca": 0.0,
                "metodo": "manual",
                "fonte": taxonomy.source_name if taxonomy else "Edição manual",
            },
            "revisao": {"status": "pendente", "confianca": 1.0, "alertas": ["Complete e revise a questão manual."]},
            "telegram": {"modo": "quiz", "pergunta": "Nova questão", "opcoes": ["Alternativa A", "Alternativa B"], "indice_correto": 0},
        }
        result = self.import_extraction({"source_file": "Questão manual", "questions": [question], "schema": "questflow.manual.v1"})
        if result["inserted"] != 1:
            raise RuntimeError("Não foi possível criar a questão manual.")
        with self.connect() as connection:
            row = connection.execute("SELECT uid FROM questions WHERE source_code = ?", (code,)).fetchone()
        if not row:
            raise RuntimeError("A questão manual foi criada, mas não pôde ser localizada.")
        return str(row["uid"])


    def import_database(self, source_path: str | Path) -> dict:
        source = Path(source_path)
        if not source.exists():
            raise FileNotFoundError(source)
        try:
            with closing(sqlite3.connect(source, timeout=30)) as connection:
                connection.row_factory = sqlite3.Row
                connection.execute("PRAGMA busy_timeout = 30000")
                tables = {
                    row[0]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table'"
                    ).fetchall()
                }
                if "questions" not in tables:
                    raise ValueError("O arquivo não contém a tabela de questões do QuestFlow PDF Importer.")
                columns = {
                    row[1]
                    for row in connection.execute("PRAGMA table_info(questions)").fetchall()
                }
                if "data_json" not in columns:
                    raise ValueError("A tabela questions não possui a coluna data_json esperada.")
                rows = connection.execute("SELECT data_json FROM questions").fetchall()
        except sqlite3.DatabaseError as error:
            raise ValueError("O arquivo selecionado não é um banco SQLite válido.") from error

        questions: list[dict] = []
        invalid = 0
        for row in rows:
            try:
                item = json.loads(row["data_json"])
            except (TypeError, json.JSONDecodeError):
                invalid += 1
                continue
            if isinstance(item, dict):
                questions.append(item)
            else:
                invalid += 1
        result = self.import_extraction(
            {
                "source_file": source.name,
                "questions": questions,
                "schema": "questflow.sqlite.migration.v1",
            }
        )
        result["invalid"] = invalid
        result["source_total"] = len(rows)
        return result

    def backup(self, destination: str | Path) -> Path:
        output = Path(destination)
        output.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as source:
            with closing(sqlite3.connect(output, timeout=30)) as target:
                target.execute("PRAGMA busy_timeout = 30000")
                source.backup(target)
                target.commit()
        return output

    def recent_imports(self, limit: int = 20) -> list[dict]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM imports ORDER BY imported_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(row) for row in rows]
