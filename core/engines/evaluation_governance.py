from __future__ import annotations

"""Motor de avaliação e governança da IA.

Toda saída do AI Engine entra como rascunho, recebe uma avaliação independente
e somente muda para aprovada por ação humana explícita.
"""

import hashlib
import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from core.schema_migrations import apply_migration

GOVERNANCE_VERSION = "qf-ai-governance-6"
EVALUATOR_VERSION = "qf-claim-evidence-evaluator-2"
GENERATION_CRITIC_VERSION = "qf-generation-critic-2"
GOLD_EVALUATOR_VERSION = "qf-gold-regression-2"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _tokens(value: Any) -> set[str]:
    text = str(value or "").casefold()
    return {item for item in re.findall(r"[a-záéíóúâêôãõç0-9]{4,}", text) if item not in {"para", "como", "questao", "questão", "sobre", "esta", "esse", "isso", "uma", "com", "pela", "pelo"}}


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)


_NEGATIONS = {"nao", "não", "nunca", "jamais", "vedado", "vedada", "proibido", "proibida", "exceto", "salvo"}
_CLAIM_STOP = {"portanto", "assim", "logo", "entao", "então", "resposta", "fundamentacao", "fundamentação", "conclusao", "conclusão"}


def _normalized_words(value: Any) -> list[str]:
    return [x for x in re.findall(r"[a-záéíóúâêôãõç0-9§ºª]+", str(value or "").casefold()) if len(x) >= 2]


def _legal_refs(value: Any) -> list[str]:
    text = str(value or "").casefold()
    refs: list[str] = []
    for pattern, prefix in (
        (r"\bart(?:igo)?\.?\s*(\d+[a-z]?)", "art"),
        (r"§\s*(\d+[ºo]?)", "par"),
        (r"\binciso\s+([ivxlcdm]+|\d+)", "inc"),
        (r"\b(?:lei|lc|decreto|ec)\s*(?:n[ºo°]\.?\s*)?(\d+[\./-]?\d*)", "norma"),
    ):
        for match in re.findall(pattern, text, flags=re.I):
            token = re.sub(r"\s+", "", str(match))
            ref = f"{prefix}:{token}"
            if ref not in refs:
                refs.append(ref)
    return refs


def _has_negation(value: Any) -> bool:
    words = set(_normalized_words(value))
    return bool(words & _NEGATIONS)


def _split_sentences(value: Any) -> list[str]:
    text = str(value or "").replace("\r", "\n")
    # Markdown headings/bullets are boundaries too. Keep substantive units only.
    chunks = re.split(r"(?:\n\s*(?:[-*•]|\d+[.)])\s+)|(?:\n{2,})|(?<=[.!?;:])\s+(?=[A-ZÁÉÍÓÚÂÊÔÃÕÇ*])", text)
    result: list[str] = []
    for chunk in chunks:
        clean = re.sub(r"[*_`#>]", "", chunk).strip(" \t\n-•")
        clean = re.sub(r"\s+", " ", clean)
        if len(clean) < 18 or len(_normalized_words(clean)) < 3:
            continue
        if clean.casefold().strip(" :") in _CLAIM_STOP:
            continue
        if clean not in result:
            result.append(clean[:1600])
    return result[:40]


def _claim_type(text: str) -> str:
    low = str(text or "").casefold()
    if "gabarito" in low or re.search(r"\balternativa\s+[a-e]\b", low):
        return "gabarito"
    if _legal_refs(low):
        return "juridica"
    if any(x in low for x in ("próxima ação", "proxima acao", "revise", "memorize", "faça", "faca", "tente", "estude")):
        return "pedagogica"
    return "factual"


def _claim_weight(kind: str) -> float:
    return {"gabarito": 1.35, "juridica": 1.25, "factual": 1.0, "pedagogica": 0.55}.get(kind, 1.0)


def _evidence_units(sources: list[dict] | None, source_texts: list[str] | None = None) -> list[dict]:
    units: list[dict] = []
    normalized_sources = list(sources or [])
    if not normalized_sources:
        normalized_sources = [{"title": f"Fonte {i+1}", "content": text, "source_ref": f"legacy:{i}"} for i, text in enumerate(source_texts or [])]
    for index, src in enumerate(normalized_sources[:30]):
        if not isinstance(src, dict):
            src = {"title": f"Fonte {index+1}", "content": str(src)}
        content = re.sub(r"\s+", " ", str(src.get("content") or "")).strip()
        metadata = src.get("metadata") if isinstance(src.get("metadata"), dict) else {}
        title = str(src.get("title") or src.get("source_label") or f"Fonte {index+1}")
        source_ref = str(src.get("source_ref") or src.get("id") or src.get("url") or f"source:{index}")
        source_kind = str(src.get("source_kind") or metadata.get("source_kind") or "")
        for sent_index, sentence in enumerate(_split_sentences(content) or ([content[:1200]] if content else [])):
            units.append({
                "source_index": index, "sentence_index": sent_index, "title": title, "source_ref": source_ref,
                "source_kind": source_kind, "content": sentence, "metadata": metadata,
            })
    return units[:800]


def _similarity(claim: str, evidence: str) -> float:
    c = _tokens(claim); e = _tokens(evidence)
    if not c or not e:
        return 0.0
    containment = len(c & e) / max(1, len(c))
    jaccard = len(c & e) / max(1, len(c | e))
    refs = set(_legal_refs(claim)); erefs = set(_legal_refs(evidence))
    ref_bonus = 0.22 if refs and refs <= erefs else (0.10 if refs & erefs else 0.0)
    nums = set(re.findall(r"\b\d+(?:[.,]\d+)?%?\b", claim)); enums = set(re.findall(r"\b\d+(?:[.,]\d+)?%?\b", evidence))
    num_bonus = 0.10 if nums and nums <= enums else 0.0
    return min(1.0, containment * 0.62 + jaccard * 0.28 + ref_bonus + num_bonus)


def _relation_for_pair(claim: str, evidence: str, score: float) -> str:
    if score < 0.24:
        return "insuficiente"
    claim_neg = _has_negation(claim); ev_neg = _has_negation(evidence)
    # Contradiction is only asserted when the lexical/structural match is strong;
    # otherwise disagreement is classified as insufficient evidence.
    if score >= 0.48 and claim_neg != ev_neg:
        return "contradiz"
    return "suporta" if score >= 0.38 else "insuficiente"


class EvaluationGovernanceEngine:
    engine_id = "evaluation_governance"
    name = "Evaluation & Governance Engine"
    version = GOVERNANCE_VERSION

    def __init__(self, database: Any):
        self.database = database
        self.initialize()

    def initialize(self) -> None:
        def schema(connection):
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS qf_ai_interactions (
                    id TEXT PRIMARY KEY,
                    question_uid TEXT NOT NULL,
                    interaction_type TEXT NOT NULL,
                    tutor_mode TEXT,
                    provider TEXT NOT NULL,
                    model TEXT,
                    prompt_sha256 TEXT NOT NULL,
                    prompt_text TEXT NOT NULL,
                    response_text TEXT NOT NULL,
                    learner_context_json TEXT NOT NULL DEFAULT '{}',
                    sources_json TEXT NOT NULL DEFAULT '[]',
                    diagnosis_json TEXT NOT NULL DEFAULT '{}',
                    status TEXT NOT NULL DEFAULT 'rascunho',
                    human_note TEXT,
                    created_at TEXT NOT NULL,
                    reviewed_at TEXT,
                    FOREIGN KEY(question_uid) REFERENCES questions(uid) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS qf_ai_evaluations (
                    id TEXT PRIMARY KEY,
                    interaction_id TEXT NOT NULL,
                    evaluator TEXT NOT NULL,
                    evaluator_model TEXT NOT NULL,
                    groundedness REAL NOT NULL DEFAULT 0,
                    answer_alignment REAL NOT NULL DEFAULT 0,
                    source_coverage REAL NOT NULL DEFAULT 0,
                    pedagogical_quality REAL NOT NULL DEFAULT 0,
                    overall_score REAL NOT NULL DEFAULT 0,
                    flags_json TEXT NOT NULL DEFAULT '[]',
                    details_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(interaction_id) REFERENCES qf_ai_interactions(id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS qf_error_diagnoses (
                    id TEXT PRIMARY KEY,
                    attempt_id TEXT,
                    question_uid TEXT NOT NULL,
                    error_type TEXT NOT NULL,
                    confidence REAL NOT NULL DEFAULT 0,
                    signals_json TEXT NOT NULL DEFAULT '[]',
                    intervention TEXT,
                    explanation TEXT,
                    model_version TEXT NOT NULL,
                    human_status TEXT NOT NULL DEFAULT 'nao_revisado',
                    human_error_type TEXT,
                    created_at TEXT NOT NULL,
                    reviewed_at TEXT,
                    FOREIGN KEY(question_uid) REFERENCES questions(uid) ON DELETE CASCADE,
                    FOREIGN KEY(attempt_id) REFERENCES telegram_attempts(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_qf_ai_interactions_question ON qf_ai_interactions(question_uid, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_qf_ai_interactions_status ON qf_ai_interactions(status, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_qf_ai_evaluations_interaction ON qf_ai_evaluations(interaction_id, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_qf_error_diagnoses_question ON qf_error_diagnoses(question_uid, created_at DESC);
                CREATE UNIQUE INDEX IF NOT EXISTS idx_qf_error_diagnoses_attempt ON qf_error_diagnoses(attempt_id) WHERE attempt_id IS NOT NULL;
                """
            )

        with self.database.connect() as connection:
            apply_migration(
                connection,
                component="ai_governance",
                version=1,
                name="Tutor IA audit, independent evaluation and error diagnosis",
                callback=schema,
            )

            def stage5_schema(conn):
                conn.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS qf_generation_drafts (
                        id TEXT PRIMARY KEY,
                        seed_question_uid TEXT,
                        subject TEXT,
                        topic TEXT,
                        board_style TEXT,
                        question_type TEXT NOT NULL,
                        generator_model TEXT NOT NULL,
                        prompt_sha256 TEXT NOT NULL,
                        source_refs_json TEXT NOT NULL DEFAULT '[]',
                        source_snapshot_json TEXT NOT NULL DEFAULT '[]',
                        error_profile_json TEXT NOT NULL DEFAULT '{}',
                        draft_json TEXT NOT NULL,
                        validation_json TEXT NOT NULL DEFAULT '{}',
                        validation_score REAL NOT NULL DEFAULT 0,
                        status TEXT NOT NULL DEFAULT 'rascunho',
                        human_note TEXT,
                        published_question_uid TEXT,
                        created_at TEXT NOT NULL,
                        validated_at TEXT,
                        reviewed_at TEXT,
                        published_at TEXT,
                        FOREIGN KEY(seed_question_uid) REFERENCES questions(uid) ON DELETE SET NULL,
                        FOREIGN KEY(published_question_uid) REFERENCES questions(uid) ON DELETE SET NULL
                    );
                    CREATE TABLE IF NOT EXISTS qf_gold_questions (
                        id TEXT PRIMARY KEY,
                        question_uid TEXT NOT NULL UNIQUE,
                        label TEXT,
                        expected_answer TEXT NOT NULL,
                        expected_topic TEXT,
                        source_snapshot_json TEXT NOT NULL DEFAULT '[]',
                        notes TEXT,
                        active INTEGER NOT NULL DEFAULT 1,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        FOREIGN KEY(question_uid) REFERENCES questions(uid) ON DELETE CASCADE
                    );
                    CREATE TABLE IF NOT EXISTS qf_gold_runs (
                        id TEXT PRIMARY KEY,
                        run_id TEXT NOT NULL,
                        gold_id TEXT NOT NULL,
                        model TEXT NOT NULL,
                        predicted_answer TEXT,
                        response_text TEXT,
                        answer_correct INTEGER,
                        source_supported INTEGER,
                        score REAL NOT NULL DEFAULT 0,
                        flags_json TEXT NOT NULL DEFAULT '[]',
                        created_at TEXT NOT NULL,
                        FOREIGN KEY(gold_id) REFERENCES qf_gold_questions(id) ON DELETE CASCADE
                    );
                    CREATE INDEX IF NOT EXISTS idx_qf_generation_status ON qf_generation_drafts(status, created_at DESC);
                    CREATE INDEX IF NOT EXISTS idx_qf_gold_active ON qf_gold_questions(active, created_at DESC);
                    CREATE INDEX IF NOT EXISTS idx_qf_gold_run ON qf_gold_runs(run_id, created_at DESC);
                    """
                )

            apply_migration(
                connection,
                component="ai_governance",
                version=2,
                name="controlled generation drafts independent critic and gold regression set",
                callback=stage5_schema,
            )


            def stage651_schema(conn):
                conn.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS qf_ai_provider_metrics (
                        id TEXT PRIMARY KEY,
                        interaction_id TEXT,
                        provider TEXT NOT NULL,
                        model TEXT,
                        operation TEXT NOT NULL,
                        status TEXT NOT NULL,
                        latency_ms REAL NOT NULL DEFAULT 0,
                        input_tokens INTEGER NOT NULL DEFAULT 0,
                        output_tokens INTEGER NOT NULL DEFAULT 0,
                        cache_read_tokens INTEGER NOT NULL DEFAULT 0,
                        estimated_cost_usd REAL,
                        structured_output INTEGER NOT NULL DEFAULT 0,
                        prompt_injection_flags INTEGER NOT NULL DEFAULT 0,
                        error_code TEXT,
                        created_at TEXT NOT NULL,
                        FOREIGN KEY(interaction_id) REFERENCES qf_ai_interactions(id) ON DELETE SET NULL
                    );
                    CREATE INDEX IF NOT EXISTS idx_qf_ai_provider_metrics_time ON qf_ai_provider_metrics(created_at DESC);
                    CREATE INDEX IF NOT EXISTS idx_qf_ai_provider_metrics_provider ON qf_ai_provider_metrics(provider, model, created_at DESC);
                    """
                )

            apply_migration(
                connection,
                component="ai_governance",
                version=3,
                name="AI gateway telemetry privacy safety and structured output metrics",
                callback=stage651_schema,
            )


            def stage661_schema(conn):
                conn.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS qf_ai_claims (
                        id TEXT PRIMARY KEY,
                        interaction_id TEXT NOT NULL,
                        claim_index INTEGER NOT NULL,
                        claim_text TEXT NOT NULL,
                        claim_type TEXT NOT NULL,
                        verdict TEXT NOT NULL,
                        confidence REAL NOT NULL DEFAULT 0,
                        temporal_status TEXT NOT NULL DEFAULT 'nao_aplicavel',
                        official_answer_status TEXT NOT NULL DEFAULT 'nao_aplicavel',
                        evidence_count INTEGER NOT NULL DEFAULT 0,
                        best_evidence_score REAL NOT NULL DEFAULT 0,
                        details_json TEXT NOT NULL DEFAULT '{}',
                        created_at TEXT NOT NULL,
                        FOREIGN KEY(interaction_id) REFERENCES qf_ai_interactions(id) ON DELETE CASCADE
                    );
                    CREATE TABLE IF NOT EXISTS qf_ai_claim_evidence (
                        id TEXT PRIMARY KEY,
                        claim_id TEXT NOT NULL,
                        source_index INTEGER NOT NULL DEFAULT 0,
                        source_title TEXT,
                        source_ref TEXT,
                        relation TEXT NOT NULL,
                        score REAL NOT NULL DEFAULT 0,
                        excerpt TEXT NOT NULL,
                        metadata_json TEXT NOT NULL DEFAULT '{}',
                        FOREIGN KEY(claim_id) REFERENCES qf_ai_claims(id) ON DELETE CASCADE
                    );
                    CREATE TABLE IF NOT EXISTS qf_gold_expectations (
                        gold_id TEXT PRIMARY KEY,
                        suite TEXT NOT NULL DEFAULT 'geral',
                        risk_level TEXT NOT NULL DEFAULT 'normal',
                        min_claim_support REAL NOT NULL DEFAULT 60,
                        required_refs_json TEXT NOT NULL DEFAULT '[]',
                        forbidden_patterns_json TEXT NOT NULL DEFAULT '[]',
                        expected_currency_status TEXT NOT NULL DEFAULT 'vigente',
                        updated_at TEXT NOT NULL,
                        FOREIGN KEY(gold_id) REFERENCES qf_gold_questions(id) ON DELETE CASCADE
                    );
                    CREATE TABLE IF NOT EXISTS qf_gold_run_evaluations (
                        run_item_id TEXT PRIMARY KEY,
                        claim_support_score REAL NOT NULL DEFAULT 0,
                        supported_claims INTEGER NOT NULL DEFAULT 0,
                        contradicted_claims INTEGER NOT NULL DEFAULT 0,
                        insufficient_claims INTEGER NOT NULL DEFAULT 0,
                        temporal_flags INTEGER NOT NULL DEFAULT 0,
                        details_json TEXT NOT NULL DEFAULT '{}',
                        created_at TEXT NOT NULL,
                        FOREIGN KEY(run_item_id) REFERENCES qf_gold_runs(id) ON DELETE CASCADE
                    );
                    CREATE INDEX IF NOT EXISTS idx_qf_ai_claims_interaction ON qf_ai_claims(interaction_id, claim_index);
                    CREATE INDEX IF NOT EXISTS idx_qf_ai_claims_verdict ON qf_ai_claims(verdict, created_at DESC);
                    CREATE INDEX IF NOT EXISTS idx_qf_ai_claim_evidence_claim ON qf_ai_claim_evidence(claim_id, score DESC);
                    """
                )
                # Backfill richer expectations for pre-6.6.1 Gold Questions.
                rows = conn.execute(
                    """SELECT g.id,q.data_json FROM qf_gold_questions g
                       JOIN questions q ON q.uid=g.question_uid
                       LEFT JOIN qf_gold_expectations x ON x.gold_id=g.id
                       WHERE x.gold_id IS NULL"""
                ).fetchall()
                for row in rows:
                    try:
                        question = json.loads(row["data_json"] or "{}")
                    except Exception:
                        question = {}
                    raw_refs = list(question.get("referencias_legais") or []) if isinstance(question.get("referencias_legais"), list) else []
                    detected_refs = _legal_refs(" ".join(str(x) for x in raw_refs) + " " + str(question.get("enunciado") or "") + " " + str(question.get("explicacao") or ""))
                    suite = "juridica" if detected_refs else (str(question.get("materia") or "geral").strip().casefold().replace(" ", "_")[:80] or "geral")
                    conn.execute(
                        """INSERT OR IGNORE INTO qf_gold_expectations(gold_id,suite,risk_level,min_claim_support,required_refs_json,forbidden_patterns_json,expected_currency_status,updated_at)
                           VALUES(?,?,?,?,?,?,?,?)""",
                        (str(row["id"]), suite, "alto" if detected_refs else "normal", 65.0 if detected_refs else 58.0, _json(detected_refs), _json([]), "vigente", utc_now()),
                    )

            apply_migration(
                connection,
                component="ai_governance",
                version=4,
                name="claim evidence temporal evaluator and gold regression governance 2",
                callback=stage661_schema,
            )


            def stage6171_schema(conn):
                columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(qf_ai_interactions)").fetchall()}
                additions = {
                    "edited_response_text": "TEXT",
                    "edited_at": "TEXT",
                    "edit_note": "TEXT",
                    "question_snapshot_sha256": "TEXT",
                    "question_snapshot_json": "TEXT NOT NULL DEFAULT '{}'",
                    "question_updated_at": "TEXT",
                }
                for column, ddl in additions.items():
                    if column not in columns:
                        conn.execute(f"ALTER TABLE qf_ai_interactions ADD COLUMN {column} {ddl}")
                conn.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS qf_ai_response_revisions (
                        id TEXT PRIMARY KEY,
                        interaction_id TEXT NOT NULL,
                        revision_no INTEGER NOT NULL,
                        editor_kind TEXT NOT NULL DEFAULT 'human',
                        response_text TEXT NOT NULL,
                        note TEXT,
                        created_at TEXT NOT NULL,
                        FOREIGN KEY(interaction_id) REFERENCES qf_ai_interactions(id) ON DELETE CASCADE,
                        UNIQUE(interaction_id, revision_no)
                    );
                    CREATE INDEX IF NOT EXISTS idx_qf_ai_response_revisions_interaction
                        ON qf_ai_response_revisions(interaction_id, revision_no DESC);
                    """
                )
                # Existing interactions predate snapshot support. The interaction
                # creation timestamp is a safe baseline: if a question was edited
                # later, the historical Tutor draft is considered stale.
                conn.execute(
                    "UPDATE qf_ai_interactions SET question_updated_at=created_at "
                    "WHERE question_updated_at IS NULL OR TRIM(question_updated_at)=''"
                )

            apply_migration(
                connection,
                component="ai_governance",
                version=5,
                name="editable Tutor drafts with immutable AI original and question-version staleness",
                callback=stage6171_schema,
            )

            def stage6171_legacy_snapshot_baseline(conn):
                """Backfill a conservative content baseline for pre-6.17.1 Tutor rows.

                Older interactions do not contain a historical question snapshot.  Using
                ``questions.updated_at > interaction.created_at`` as a proxy is unsafe
                because ``updated_at`` is also refreshed by maintenance/synchronisation
                operations that do not change pedagogical content.  That produced false
                "questão alterada" warnings immediately after upgrading.

                For those legacy rows we therefore capture the *current* pedagogical
                question content once, at migration time, and use its SHA-256 as a
                forward-looking baseline.  We intentionally label this provenance as a
                legacy upgrade baseline: it is not presented as the exact historical
                question version used when the old Tutor response was originally made.
                Any content edit made after this baseline is captured will change the
                hash and correctly stale the old response.
                """

                columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(qf_ai_interactions)").fetchall()}
                additions = {
                    "question_snapshot_origin": "TEXT NOT NULL DEFAULT 'generation'",
                    "question_snapshot_captured_at": "TEXT",
                }
                for column, ddl in additions.items():
                    if column not in columns:
                        conn.execute(f"ALTER TABLE qf_ai_interactions ADD COLUMN {column} {ddl}")

                now = utc_now()
                rows = conn.execute(
                    """
                    SELECT i.id,i.question_uid,q.updated_at,q.data_json
                    FROM qf_ai_interactions i
                    JOIN questions q ON q.uid=i.question_uid
                    WHERE i.question_snapshot_sha256 IS NULL OR TRIM(i.question_snapshot_sha256)=''
                    """
                ).fetchall()
                for row in rows:
                    try:
                        question = json.loads(row["data_json"] or "{}")
                    except Exception:
                        question = {}
                    payload = self._snapshot_payload(question if isinstance(question, dict) else {})
                    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
                    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
                    conn.execute(
                        """
                        UPDATE qf_ai_interactions
                        SET question_snapshot_sha256=?,question_snapshot_json=?,question_updated_at=?,
                            question_snapshot_origin='legacy_upgrade_baseline_6171',question_snapshot_captured_at=?
                        WHERE id=?
                        """,
                        (digest, _json(payload), str(row["updated_at"] or now), now, str(row["id"])),
                    )

                # Interactions created with snapshot support already have an exact
                # generation-time content hash.  Make their provenance explicit.
                conn.execute(
                    """
                    UPDATE qf_ai_interactions
                    SET question_snapshot_origin=CASE
                            WHEN question_snapshot_origin IS NULL OR TRIM(question_snapshot_origin)='' THEN 'generation'
                            ELSE question_snapshot_origin
                        END,
                        question_snapshot_captured_at=COALESCE(NULLIF(question_snapshot_captured_at,''),created_at)
                    WHERE question_snapshot_sha256 IS NOT NULL AND TRIM(question_snapshot_sha256)<>''
                    """
                )

            apply_migration(
                connection,
                component="ai_governance",
                version=6,
                name="legacy Tutor content-hash baseline without timestamp false positives",
                callback=stage6171_legacy_snapshot_baseline,
            )

    def record_diagnosis(self, *, question_uid: str, attempt_id: str | None, diagnosis: dict) -> dict:
        diagnose_id = str(uuid.uuid4())
        with self.database.connect() as connection:
            if attempt_id:
                existing = connection.execute("SELECT id FROM qf_error_diagnoses WHERE attempt_id=?", (str(attempt_id),)).fetchone()
                if existing:
                    diagnose_id = str(existing["id"])
                    connection.execute(
                        """
                        UPDATE qf_error_diagnoses SET error_type=?, confidence=?, signals_json=?, intervention=?,
                            explanation=?, model_version=?, created_at=? WHERE id=?
                        """,
                        (
                            str(diagnosis.get("error_type", "indeterminado")), float(diagnosis.get("confidence", 0) or 0),
                            _json(diagnosis.get("signals", [])), str(diagnosis.get("intervention", "")),
                            str(diagnosis.get("explanation", "")), str(diagnosis.get("version", "qf-error-diagnosis-1")),
                            utc_now(), diagnose_id,
                        ),
                    )
                else:
                    connection.execute(
                        """INSERT INTO qf_error_diagnoses(id,attempt_id,question_uid,error_type,confidence,signals_json,intervention,explanation,model_version,created_at)
                           VALUES(?,?,?,?,?,?,?,?,?,?)""",
                        (diagnose_id, str(attempt_id), str(question_uid), str(diagnosis.get("error_type", "indeterminado")),
                         float(diagnosis.get("confidence", 0) or 0), _json(diagnosis.get("signals", [])), str(diagnosis.get("intervention", "")),
                         str(diagnosis.get("explanation", "")), str(diagnosis.get("version", "qf-error-diagnosis-1")), utc_now()),
                    )
            else:
                connection.execute(
                    """INSERT INTO qf_error_diagnoses(id,attempt_id,question_uid,error_type,confidence,signals_json,intervention,explanation,model_version,created_at)
                       VALUES(?,?,?,?,?,?,?,?,?,?)""",
                    (diagnose_id, None, str(question_uid), str(diagnosis.get("error_type", "indeterminado")),
                     float(diagnosis.get("confidence", 0) or 0), _json(diagnosis.get("signals", [])), str(diagnosis.get("intervention", "")),
                     str(diagnosis.get("explanation", "")), str(diagnosis.get("version", "qf-error-diagnosis-1")), utc_now()),
                )
        return {"id": diagnose_id, **diagnosis}

    @staticmethod
    def _snapshot_payload(question: dict) -> dict:
        source = question.get("fonte") if isinstance(question.get("fonte"), dict) else {}
        return {
            "codigo_origem": str(question.get("codigo_origem") or question.get("id") or ""),
            "materia": str(question.get("materia") or ""),
            "assunto": str(question.get("assunto") or ""),
            "aula_planilha": str(question.get("aula_planilha") or ""),
            "enunciado": str(question.get("enunciado") or ""),
            "alternativas": question.get("alternativas") if isinstance(question.get("alternativas"), list) else [],
            "gabarito": str(question.get("gabarito") or ""),
            "explicacao": str(question.get("explicacao") or ""),
            "fonte_codigo": str(source.get("codigo") or ""),
        }

    def _question_snapshot(self, question_uid: str) -> dict:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT updated_at,data_json FROM questions WHERE uid=?", (str(question_uid),)
            ).fetchone()
        if not row:
            return {"updated_at": "", "sha256": "", "payload": {}}
        try:
            question = json.loads(row["data_json"] or "{}")
        except Exception:
            question = {}
        payload = self._snapshot_payload(question if isinstance(question, dict) else {})
        canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
        return {
            "updated_at": str(row["updated_at"] or ""),
            "sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
            "payload": payload,
        }

    @staticmethod
    def _interaction_is_stale(item: dict, current_snapshot: dict) -> bool:
        stored_hash = str(item.get("question_snapshot_sha256") or "").strip()
        current_hash = str(current_snapshot.get("sha256") or "").strip()
        if stored_hash and current_hash:
            return stored_hash != current_hash
        baseline = str(item.get("question_updated_at") or item.get("created_at") or "").strip()
        current_updated = str(current_snapshot.get("updated_at") or "").strip()
        return bool(baseline and current_updated and current_updated > baseline)

    def record_interaction(
        self,
        *,
        question_uid: str,
        interaction_type: str,
        mode: str,
        provider: str,
        model: str,
        prompt_text: str,
        response_text: str,
        learner_context: dict,
        sources: list[dict],
        diagnosis: dict,
    ) -> str:
        interaction_id = str(uuid.uuid4())
        digest = hashlib.sha256(str(prompt_text).encode("utf-8")).hexdigest()
        created_at = utc_now()
        snapshot = self._question_snapshot(str(question_uid))
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO qf_ai_interactions(
                    id,question_uid,interaction_type,tutor_mode,provider,model,prompt_sha256,prompt_text,response_text,
                    learner_context_json,sources_json,diagnosis_json,status,created_at,question_snapshot_sha256,
                    question_snapshot_json,question_updated_at,question_snapshot_origin,question_snapshot_captured_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (interaction_id, str(question_uid), str(interaction_type), str(mode), str(provider), str(model), digest,
                 str(prompt_text), str(response_text), _json(learner_context), _json(sources), _json(diagnosis), "rascunho", created_at,
                 str(snapshot.get("sha256") or ""), _json(snapshot.get("payload") or {}), str(snapshot.get("updated_at") or created_at),
                 "generation", created_at),
            )
        return interaction_id

    def _question_reference_context(self, question_uid: str) -> dict:
        """Resolve temporal/currentness context without requiring another engine."""
        result = {"reference_date": "", "currency_status": "vigente", "currency_reason": "", "exam_year": 0}
        with self.database.connect() as connection:
            q = connection.execute("SELECT exam_year,data_json FROM questions WHERE uid=?", (str(question_uid),)).fetchone()
            if q:
                try:
                    result["exam_year"] = int(q["exam_year"] or 0)
                except Exception:
                    result["exam_year"] = 0
                try:
                    payload = json.loads(q["data_json"] or "{}")
                except Exception:
                    payload = {}
                temporal = payload.get("contexto_temporal") if isinstance(payload.get("contexto_temporal"), dict) else {}
                result["reference_date"] = str(temporal.get("data_prova") or payload.get("data_prova") or "")
            try:
                cur = connection.execute("SELECT status,reference_date,reason FROM qf_question_currency WHERE question_uid=?", (str(question_uid),)).fetchone()
            except Exception:
                cur = None
            if cur:
                result["currency_status"] = str(cur["status"] or "vigente")
                result["currency_reason"] = str(cur["reason"] or "")
                if str(cur["reference_date"] or ""):
                    result["reference_date"] = str(cur["reference_date"])
            # Active project is a better current study reference than today's date.
            if not result["reference_date"]:
                try:
                    project = connection.execute("SELECT exam_date FROM qf_exam_projects WHERE is_active=1 ORDER BY updated_at DESC LIMIT 1").fetchone()
                except Exception:
                    project = None
                if project and str(project["exam_date"] or ""):
                    result["reference_date"] = str(project["exam_date"])
        if not result["reference_date"] and result["exam_year"]:
            result["reference_date"] = f"{int(result['exam_year']):04d}-12-31"
        return result

    def _claim_evaluation_payload(
        self, *, response_text: str, mode: str, official_answer: str,
        source_texts: list[str] | None = None, sources: list[dict] | None = None,
        question_context: dict | None = None,
    ) -> dict:
        response = str(response_text or "").strip()
        answer = str(official_answer or "").strip().upper()
        mode = str(mode or "")
        context = dict(question_context or {})
        units = _evidence_units(sources, source_texts)
        claims_raw = _split_sentences(response)
        answer_mentions = re.findall(r"(?:gabarito|alternativa|resposta)\s*[:=-]?\s*([a-e]|certo|errado|c|e)\b", response.casefold(), flags=re.I)
        if answer_mentions and not any(_claim_type(item) == "gabarito" for item in claims_raw):
            claims_raw.insert(0, f"Gabarito: {str(answer_mentions[-1]).upper()}")
        # If structured prose is very short, still evaluate the whole response as one claim.
        if not claims_raw and response:
            claims_raw = [response[:1600]]
        claims: list[dict] = []
        flags: list[str] = []
        reference_date = str(context.get("reference_date") or "")
        currency_status = str(context.get("currency_status") or "vigente")
        if currency_status in {"desatualizada", "anulada", "controversa"}:
            flags.append(f"questao_com_estado_temporal_restritivo:{currency_status}")
        elif currency_status == "potencialmente_desatualizada":
            flags.append("questao_potencialmente_desatualizada_requer_revisao")

        for idx, text in enumerate(claims_raw[:32]):
            kind = _claim_type(text)
            refs = _legal_refs(text)
            scored = []
            for unit in units:
                score = _similarity(text, unit["content"])
                if score <= 0.10:
                    continue
                relation = _relation_for_pair(text, unit["content"], score)
                scored.append({**unit, "score": score, "relation": relation})
            scored.sort(key=lambda x: (x["score"], x["relation"] == "contradiz", x["relation"] == "suporta"), reverse=True)
            if refs:
                evidence_refs = set()
                for unit in units:
                    evidence_refs.update(_legal_refs(unit.get("content") or ""))
                missing_refs = [ref for ref in refs if ref not in evidence_refs]
                if missing_refs:
                    flags.append("referencia_legal_nao_encontrada_nas_evidencias:" + ",".join(missing_refs))
            best = scored[0] if scored else None
            verdict = "insuficiente"
            confidence = 0.18
            if best:
                verdict = str(best["relation"])
                confidence = min(0.99, 0.30 + float(best["score"]) * 0.70)

            official_status = "nao_aplicavel"
            normalized = text.casefold()
            if kind == "gabarito" and answer:
                mentioned = re.findall(r"(?:gabarito|alternativa|resposta)\s*[:=-]?\s*([a-e]|certo|errado|c|e)\b", normalized, flags=re.I)
                if mentioned:
                    pred = str(mentioned[-1]).upper()
                    pred = {"CERTO":"C", "ERRADO":"E"}.get(pred, pred)
                    official_status = "alinhado" if pred == answer else "contradiz_gabarito"
                    if official_status == "contradiz_gabarito":
                        verdict = "contradiz"; confidence = max(confidence, 0.98)
                        flags.append(f"afirmacao_contradiz_gabarito:{idx+1}")
                    elif verdict == "insuficiente":
                        # Official key is an authoritative check for the conclusion, even when sources are sparse.
                        verdict = "suporta"; confidence = max(confidence, 0.92)
                else:
                    official_status = "gabarito_nao_explicitado"

            temporal_status = "nao_aplicavel"
            temporal_candidates = [item for item in scored[:8] if str(item.get("source_kind") or "") == "legislation" or (item.get("metadata") or {}).get("effective_from")]
            if refs or temporal_candidates:
                if not reference_date:
                    temporal_status = "sem_data_referencia"
                elif temporal_candidates:
                    valid = []
                    invalid = []
                    for item in temporal_candidates:
                        meta = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
                        start = str(meta.get("effective_from") or "")
                        end = str(meta.get("effective_to") or "")
                        if (not start or start <= reference_date) and (not end or end >= reference_date):
                            valid.append(item)
                        else:
                            invalid.append(item)
                    if valid:
                        temporal_status = "vigente_na_data"
                        # Prefer temporally valid evidence when it exists.
                        valid.sort(key=lambda x: x["score"], reverse=True)
                        if valid[0]["score"] >= (best["score"] if best else 0) * 0.82:
                            best = valid[0]
                            if verdict != "contradiz":
                                verdict = str(best["relation"])
                    elif invalid:
                        temporal_status = "fonte_fora_da_vigencia"
                        if verdict == "suporta":
                            verdict = "insuficiente"
                        flags.append(f"afirmacao_com_fonte_fora_da_vigencia:{idx+1}")
                else:
                    temporal_status = "sem_fonte_legislativa"

            evidence_rows = []
            for item in scored[:3]:
                evidence_rows.append({
                    "source_index": int(item.get("source_index") or 0), "source_title": str(item.get("title") or "Fonte"),
                    "source_ref": str(item.get("source_ref") or ""), "relation": str(item.get("relation") or "insuficiente"),
                    "score": round(float(item.get("score") or 0), 4), "excerpt": str(item.get("content") or "")[:900],
                    "metadata": item.get("metadata") if isinstance(item.get("metadata"), dict) else {},
                })
            claims.append({
                "index": idx, "text": text, "type": kind, "verdict": verdict,
                "confidence": round(float(confidence), 3), "legal_refs": refs,
                "temporal_status": temporal_status, "official_answer_status": official_status,
                "best_evidence_score": round(float(best.get("score") if best else 0), 4),
                "evidence": evidence_rows,
            })

        supported = [c for c in claims if c["verdict"] == "suporta"]
        contradicted = [c for c in claims if c["verdict"] == "contradiz"]
        insufficient = [c for c in claims if c["verdict"] == "insuficiente"]
        weighted_total = sum(_claim_weight(c["type"]) for c in claims) or 1.0
        weighted_supported = sum(_claim_weight(c["type"]) * c["confidence"] for c in supported)
        weighted_contradicted = sum(_claim_weight(c["type"]) * c["confidence"] for c in contradicted)
        support_ratio = weighted_supported / weighted_total
        contradiction_ratio = weighted_contradicted / weighted_total
        groundedness = max(0.0, min(100.0, support_ratio * 112.0 - contradiction_ratio * 78.0)) if claims else 18.0
        claim_coverage = (len(supported) + len(contradicted)) / max(1, len(claims))
        source_coverage = max(0.0, min(100.0, claim_coverage * 100.0 - len(insufficient) * 2.0))

        response_norm = response.casefold()
        if mode == "socratico":
            leaks = bool(answer and (f"gabarito {answer.casefold()}" in response_norm or f"alternativa {answer.casefold()}" in response_norm))
            answer_alignment = 35.0 if leaks else 96.0
            if leaks: flags.append("modo_socratico_revelou_gabarito")
        elif answer:
            answer_claims = [c for c in claims if c["type"] == "gabarito"]
            if any(c["official_answer_status"] == "contradiz_gabarito" for c in answer_claims):
                answer_alignment = 5.0
            elif any(c["official_answer_status"] == "alinhado" for c in answer_claims):
                answer_alignment = 100.0
            else:
                answer_alignment = 72.0
        else:
            answer_alignment = 78.0

        pedagogy = 52.0
        if any(c["type"] == "pedagogica" for c in claims): pedagogy += 14.0
        if any(marker in response_norm for marker in ("por que", "regra", "exceção", "excecao", "próximo", "proximo", "atenção", "atencao")): pedagogy += 13.0
        if 180 <= len(response) <= 6000: pedagogy += 11.0
        pedagogical_quality = min(100.0, pedagogy)
        if contradicted:
            flags.append(f"afirmacoes_contraditas:{len(contradicted)}")
        if insufficient:
            flags.append(f"afirmacoes_sem_evidencia_suficiente:{len(insufficient)}")
        temporal_bad = sum(1 for c in claims if c["temporal_status"] == "fonte_fora_da_vigencia")
        overall = round(max(0.0, groundedness * .39 + answer_alignment * .29 + source_coverage * .16 + pedagogical_quality * .16 - temporal_bad * 6.0), 1)
        return {
            "version": EVALUATOR_VERSION, "groundedness": round(groundedness, 1), "answer_alignment": round(answer_alignment, 1),
            "source_coverage": round(source_coverage, 1), "pedagogical_quality": round(pedagogical_quality, 1),
            "overall_score": overall, "flags": list(dict.fromkeys(flags)),
            "status": "revisar" if overall < 76 or contradicted or temporal_bad else "apto_para_revisao_humana",
            "claim_summary": {"total": len(claims), "supported": len(supported), "contradicted": len(contradicted), "insufficient": len(insufficient), "support_rate": round(len(supported)/max(1,len(claims))*100,1)},
            "claims": claims, "reference_context": context,
            "method": "claim_evidence_verdicts_not_response_level_overlap",
        }

    def _persist_claims(self, interaction_id: str, evaluation: dict) -> None:
        claims = list(evaluation.get("claims") or [])
        with self.database.connect() as connection:
            connection.execute("DELETE FROM qf_ai_claims WHERE interaction_id=?", (str(interaction_id),))
            for claim in claims:
                claim_id = str(uuid.uuid4())
                evidence = list(claim.get("evidence") or [])
                connection.execute(
                    """INSERT INTO qf_ai_claims(id,interaction_id,claim_index,claim_text,claim_type,verdict,confidence,temporal_status,official_answer_status,evidence_count,best_evidence_score,details_json,created_at)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (claim_id, str(interaction_id), int(claim.get("index") or 0), str(claim.get("text") or ""), str(claim.get("type") or "factual"),
                     str(claim.get("verdict") or "insuficiente"), float(claim.get("confidence") or 0), str(claim.get("temporal_status") or "nao_aplicavel"),
                     str(claim.get("official_answer_status") or "nao_aplicavel"), len(evidence), float(claim.get("best_evidence_score") or 0),
                     _json({k:v for k,v in claim.items() if k != "evidence"}), utc_now()),
                )
                for ev in evidence:
                    connection.execute(
                        """INSERT INTO qf_ai_claim_evidence(id,claim_id,source_index,source_title,source_ref,relation,score,excerpt,metadata_json)
                           VALUES(?,?,?,?,?,?,?,?,?)""",
                        (str(uuid.uuid4()), claim_id, int(ev.get("source_index") or 0), str(ev.get("source_title") or ""), str(ev.get("source_ref") or ""),
                         str(ev.get("relation") or "insuficiente"), float(ev.get("score") or 0), str(ev.get("excerpt") or "")[:1200], _json(ev.get("metadata") or {})),
                    )

    def evaluate(
        self,
        interaction_id: str,
        *,
        response_text: str,
        mode: str,
        official_answer: str,
        source_texts: list[str],
        diagnosis: dict,
        sources: list[dict] | None = None,
        question_context: dict | None = None,
    ) -> dict:
        context = self._question_reference_context(str(interaction_id and self.interaction_question_uid(interaction_id) or ""))
        context.update(dict(question_context or {}))
        evaluation = self._claim_evaluation_payload(
            response_text=response_text, mode=mode, official_answer=official_answer,
            source_texts=source_texts, sources=sources, question_context=context,
        )
        flags = list(evaluation.get("flags") or [])
        with self.database.connect() as connection:
            connection.execute(
                """INSERT INTO qf_ai_evaluations(id,interaction_id,evaluator,evaluator_model,groundedness,answer_alignment,
                    source_coverage,pedagogical_quality,overall_score,flags_json,details_json,created_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                (str(uuid.uuid4()), str(interaction_id), "QuestFlow claim/evidence evaluator", EVALUATOR_VERSION,
                 evaluation["groundedness"], evaluation["answer_alignment"], evaluation["source_coverage"],
                 evaluation["pedagogical_quality"], evaluation["overall_score"], _json(flags), _json(evaluation), utc_now()),
            )
        self._persist_claims(str(interaction_id), evaluation)
        return evaluation

    def interaction_question_uid(self, interaction_id: str) -> str:
        with self.database.connect() as connection:
            row = connection.execute("SELECT question_uid FROM qf_ai_interactions WHERE id=?", (str(interaction_id),)).fetchone()
        return str(row["question_uid"] or "") if row else ""

    def edit_interaction_response(self, interaction_id: str, *, response_text: str, note: str = "") -> dict:
        text = str(response_text or "").strip()
        if not text:
            raise ValueError("O texto do Tutor não pode ficar vazio.")
        iid = str(interaction_id or "").strip()
        if not iid:
            raise ValueError("Interação de IA não informada.")
        now = utc_now()
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT id,response_text,edited_response_text FROM qf_ai_interactions WHERE id=?", (iid,)
            ).fetchone()
            if not row:
                raise ValueError("Interação de IA não encontrada.")
            next_no = int(connection.execute(
                "SELECT COALESCE(MAX(revision_no),0)+1 FROM qf_ai_response_revisions WHERE interaction_id=?", (iid,)
            ).fetchone()[0] or 1)
            connection.execute(
                """INSERT INTO qf_ai_response_revisions(id,interaction_id,revision_no,editor_kind,response_text,note,created_at)
                   VALUES(?,?,?,?,?,?,?)""",
                (str(uuid.uuid4()), iid, next_no, "human", text, str(note or "")[:2000], now),
            )
            connection.execute(
                """UPDATE qf_ai_interactions
                   SET edited_response_text=?,edited_at=?,edit_note=?,status='rascunho',reviewed_at=NULL
                   WHERE id=?""",
                (text, now, str(note or "")[:2000], iid),
            )
        return self.interaction(iid)

    def response_revisions(self, interaction_id: str) -> list[dict]:
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT revision_no,editor_kind,response_text,note,created_at FROM qf_ai_response_revisions WHERE interaction_id=? ORDER BY revision_no",
                (str(interaction_id),),
            ).fetchall()
        return [dict(row) for row in rows]

    def latest_interaction(self, question_uid: str, *, interaction_type: str = "tutor") -> dict | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT id FROM qf_ai_interactions WHERE question_uid=? AND interaction_type=? ORDER BY created_at DESC LIMIT 1",
                (str(question_uid), str(interaction_type)),
            ).fetchone()
        return self.interaction(str(row["id"])) if row else None

    def review_interaction(self, interaction_id: str, *, decision: str, note: str = "") -> dict:
        decision_norm = str(decision or "").strip().casefold()
        if decision_norm not in {"aprovar", "rejeitar", "rascunho"}:
            raise ValueError("Decisão inválida.")
        if decision_norm == "aprovar":
            current = self.interaction(str(interaction_id))
            if bool(current.get("question_changed")):
                raise ValueError("A questão foi alterada após a geração deste rascunho. Gere uma nova orientação com a versão atual antes de aprovar.")
        status = {"aprovar": "aprovado", "rejeitar": "rejeitado", "rascunho": "rascunho"}[decision_norm]
        with self.database.connect() as connection:
            changed = connection.execute(
                "UPDATE qf_ai_interactions SET status=?, human_note=?, reviewed_at=? WHERE id=?",
                (status, str(note or "")[:2000], utc_now(), str(interaction_id)),
            ).rowcount
        if not changed:
            raise ValueError("Interação de IA não encontrada.")
        return {"id": str(interaction_id), "status": status, "human_note": str(note or "")}

    def recent_audit(self, *, limit: int = 20) -> list[dict]:
        limit = max(1, min(100, int(limit or 20)))
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT i.id,i.question_uid,i.interaction_type,i.tutor_mode,i.provider,i.model,i.prompt_sha256,
                       i.status,i.human_note,i.created_at,i.reviewed_at,i.edited_at,i.question_updated_at,
                       i.question_snapshot_sha256,i.question_snapshot_origin,i.question_snapshot_captured_at,
                       CASE WHEN i.edited_response_text IS NOT NULL AND TRIM(i.edited_response_text)<>'' THEN 1 ELSE 0 END AS has_human_edit,
                       q.source_code,q.subject,q.primary_topic,q.updated_at AS current_question_updated_at,
                       e.overall_score,e.groundedness,e.answer_alignment,e.source_coverage,e.pedagogical_quality,e.flags_json,
                       (SELECT COUNT(*) FROM qf_ai_claims c WHERE c.interaction_id=i.id AND c.verdict='suporta') AS supported_claims,
                       (SELECT COUNT(*) FROM qf_ai_claims c WHERE c.interaction_id=i.id AND c.verdict='contradiz') AS contradicted_claims,
                       (SELECT COUNT(*) FROM qf_ai_claims c WHERE c.interaction_id=i.id AND c.verdict='insuficiente') AS insufficient_claims
                FROM qf_ai_interactions i
                JOIN questions q ON q.uid=i.question_uid
                LEFT JOIN qf_ai_evaluations e ON e.id=(
                    SELECT e2.id FROM qf_ai_evaluations e2 WHERE e2.interaction_id=i.id ORDER BY e2.created_at DESC LIMIT 1
                )
                ORDER BY i.created_at DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            try:
                item["flags"] = json.loads(item.pop("flags_json") or "[]")
            except Exception:
                item["flags"] = []
            current_snapshot = self._question_snapshot(str(item.get("question_uid") or ""))
            item["question_changed"] = self._interaction_is_stale(item, current_snapshot)
            item["has_human_edit"] = bool(item.get("has_human_edit"))
            result.append(item)
        return result

    def interaction(self, interaction_id: str) -> dict:
        with self.database.connect() as connection:
            row = connection.execute("SELECT * FROM qf_ai_interactions WHERE id=?", (str(interaction_id),)).fetchone()
            if not row:
                raise ValueError("Interação de IA não encontrada.")
            item = dict(row)
            ev = connection.execute("SELECT * FROM qf_ai_evaluations WHERE interaction_id=? ORDER BY created_at DESC LIMIT 1", (str(interaction_id),)).fetchone()
            claim_rows = connection.execute("SELECT * FROM qf_ai_claims WHERE interaction_id=? ORDER BY claim_index", (str(interaction_id),)).fetchall()
            claim_evidence = {}
            for claim_row in claim_rows:
                ev_rows = connection.execute("SELECT * FROM qf_ai_claim_evidence WHERE claim_id=? ORDER BY score DESC LIMIT 5", (str(claim_row["id"]),)).fetchall()
                claim_evidence[str(claim_row["id"])] = [dict(x) for x in ev_rows]
        for key in ("learner_context_json", "sources_json", "diagnosis_json"):
            try:
                item[key.removesuffix("_json")] = json.loads(item.get(key) or ("[]" if key == "sources_json" else "{}"))
            except Exception:
                item[key.removesuffix("_json")] = [] if key == "sources_json" else {}
            item.pop(key, None)
        try:
            item["question_snapshot"] = json.loads(item.get("question_snapshot_json") or "{}")
        except Exception:
            item["question_snapshot"] = {}
        item.pop("question_snapshot_json", None)
        current_snapshot = self._question_snapshot(str(item.get("question_uid") or ""))
        item["question_changed"] = self._interaction_is_stale(item, current_snapshot)
        item["current_question"] = current_snapshot.get("payload") or {}
        item["current_question_updated_at"] = str(current_snapshot.get("updated_at") or "")
        item["display_response_text"] = str(item.get("edited_response_text") or item.get("response_text") or "")
        item["has_human_edit"] = bool(str(item.get("edited_response_text") or "").strip())
        item["revisions"] = self.response_revisions(str(item.get("id") or ""))
        claims=[]
        for claim_row in claim_rows:
            claim=dict(claim_row)
            try:
                details=json.loads(claim.pop("details_json") or "{}")
            except Exception:
                details={}
            evidence=[]
            for ev_row in claim_evidence.get(str(claim.get("id") or ""), []):
                ev_item=dict(ev_row)
                try: ev_item["metadata"]=json.loads(ev_item.pop("metadata_json") or "{}")
                except Exception: ev_item["metadata"]={}
                evidence.append(ev_item)
            claim["details"]=details; claim["evidence"]=evidence
            claims.append(claim)
        item["claims"]=claims
        if ev:
            evaluation = dict(ev)
            try:
                evaluation["flags"] = json.loads(evaluation.pop("flags_json") or "[]")
                evaluation["details"] = json.loads(evaluation.pop("details_json") or "{}")
            except Exception:
                pass
            item["evaluation"] = evaluation
        return item

    def error_profile(self, *, subject: str = "", topic: str = "") -> dict:
        subject = str(subject or "").strip()
        topic = str(topic or "").strip()
        clauses = []
        values: list[object] = []
        if subject:
            clauses.append("q.subject=? COLLATE NOCASE")
            values.append(subject)
        if topic:
            clauses.append("q.primary_topic=? COLLATE NOCASE")
            values.append(topic)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        with self.database.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT d.error_type, COUNT(*) AS qty, AVG(d.confidence) AS confidence
                FROM qf_error_diagnoses d JOIN questions q ON q.uid=d.question_uid
                {where}
                GROUP BY d.error_type ORDER BY qty DESC, confidence DESC
                """, values,
            ).fetchall()
        items = [{"error_type": str(row["error_type"]), "count": int(row["qty"] or 0), "confidence": round(float(row["confidence"] or 0), 3)} for row in rows]
        return {"subject": subject, "topic": topic, "total": sum(item["count"] for item in items), "items": items}

    def create_generation_draft(self, *, seed_question_uid: str | None, subject: str, topic: str, board_style: str,
                                question_type: str, generator_model: str, prompt_text: str, sources: list[dict],
                                error_profile: dict, draft: dict) -> dict:
        draft_id = str(uuid.uuid4())
        digest = hashlib.sha256(str(prompt_text).encode("utf-8")).hexdigest()
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO qf_generation_drafts(
                    id,seed_question_uid,subject,topic,board_style,question_type,generator_model,prompt_sha256,
                    source_refs_json,source_snapshot_json,error_profile_json,draft_json,status,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (draft_id, str(seed_question_uid) if seed_question_uid else None, str(subject), str(topic), str(board_style),
                 str(question_type), str(generator_model), digest, _json([src.get("id") for src in sources]), _json(sources),
                 _json(error_profile), _json(draft), "rascunho", utc_now()),
            )
        return self.generation_draft(draft_id)

    def generation_draft(self, draft_id: str) -> dict:
        with self.database.connect() as connection:
            row = connection.execute("SELECT * FROM qf_generation_drafts WHERE id=?", (str(draft_id),)).fetchone()
        if not row:
            raise ValueError("Rascunho de geração não encontrado.")
        item = dict(row)
        for key in ("source_refs_json", "source_snapshot_json", "error_profile_json", "draft_json", "validation_json"):
            target = key.removesuffix("_json")
            try:
                item[target] = json.loads(item.get(key) or ("[]" if "source" in key else "{}"))
            except Exception:
                item[target] = [] if "source" in key else {}
            item.pop(key, None)
        return item

    def generation_drafts(self, limit: int = 30) -> list[dict]:
        safe = max(1, min(200, int(limit or 30)))
        with self.database.connect() as connection:
            rows = connection.execute("SELECT id FROM qf_generation_drafts ORDER BY created_at DESC LIMIT ?", (safe,)).fetchall()
        return [self.generation_draft(str(row["id"])) for row in rows]

    def validate_generation_draft(self, draft_id: str) -> dict:
        item = self.generation_draft(draft_id)
        draft = item.get("draft") or {}
        sources = item.get("source_snapshot") or []
        source_text = "\n".join(str(src.get("content") or "") for src in sources if isinstance(src, dict))
        source_tokens = _tokens(source_text)
        statement = str(draft.get("enunciado") or "")
        alternatives = [alt for alt in (draft.get("alternativas") or []) if isinstance(alt, dict)]
        answer = str(draft.get("gabarito") or "").upper().strip()
        keys = [str(alt.get("chave") or "").upper().strip() for alt in alternatives]
        flags: list[str] = []
        critical: list[str] = []
        correct_text = ""
        if answer in keys:
            correct_text = str(alternatives[keys.index(answer)].get("texto") or "")
        elif str(draft.get("tipo") or "").casefold().find("certo") >= 0 and answer in {"C", "E"}:
            correct_text = statement
        else:
            critical.append("gabarito_inconsistente")
        overlap = len(_tokens(correct_text) & source_tokens) / max(1, len(_tokens(correct_text))) if correct_text else 0.0
        legacy_groundedness = min(100.0, overlap * 125.0)
        exam_date_pre = str((draft.get("contexto_temporal") or {}).get("data_prova") or "").strip() if isinstance(draft.get("contexto_temporal"), dict) else ""
        claim_validation = self._claim_evaluation_payload(
            response_text=(f"Gabarito: {answer}. " + str(correct_text or statement)),
            mode="geracao_controlada", official_answer=answer, sources=sources, source_texts=[source_text],
            question_context={"reference_date": exam_date_pre, "currency_status": "vigente"},
        )
        groundedness = round(float(claim_validation.get("groundedness") or 0) * .78 + legacy_groundedness * .22, 1)
        claim_summary = claim_validation.get("claim_summary") or {}
        if int(claim_summary.get("contradicted") or 0):
            critical.append("afirmacoes_da_explicacao_contraditas_pelas_fontes")
        if groundedness < 55:
            critical.append("resposta_correta_pouco_fundamentada_nas_fontes_selecionadas")
        elif int(claim_summary.get("insufficient") or 0):
            flags.append(f"afirmacoes_sem_evidencia_suficiente:{int(claim_summary.get('insufficient') or 0)}")
        normalized_alts = [re.sub(r"\W+", " ", str(alt.get("texto") or "").casefold()).strip() for alt in alternatives]
        if alternatives and len(set(normalized_alts)) != len(normalized_alts):
            critical.append("alternativas_duplicadas")
        if alternatives and len(alternatives) < 4:
            flags.append("menos_de_quatro_alternativas")
        legal_refs = re.findall(r"\bart(?:igo)?\.?\s*(\d+[a-z]?)", (statement + " " + " ".join(normalized_alts)).casefold(), flags=re.I)
        unsupported = [ref for ref in legal_refs if ref.casefold() not in source_text.casefold()]
        if unsupported:
            critical.append("referencias_legais_sem_suporte:" + ",".join(sorted(set(unsupported))))
        exam_date = str((draft.get("contexto_temporal") or {}).get("data_prova") or "").strip() if isinstance(draft.get("contexto_temporal"), dict) else ""
        legislation_sources = [src for src in sources if isinstance(src, dict) and str(src.get("source_kind") or "") == "legislation"]
        if legislation_sources and not exam_date:
            flags.append("fonte_legislativa_sem_data_de_prova_para_validacao_temporal")
        if legislation_sources and exam_date:
            for src in legislation_sources:
                meta = src.get("metadata") if isinstance(src.get("metadata"), dict) else {}
                start = str(meta.get("effective_from") or "")
                end = str(meta.get("effective_to") or "")
                if start and exam_date < start:
                    critical.append(f"norma_ainda_nao_vigente_na_data_da_prova:{meta.get('canonical_key') or src.get('title')}")
                if end and exam_date > end:
                    critical.append(f"norma_ja_revogada_na_data_da_prova:{meta.get('canonical_key') or src.get('title')}")
        source_count = len(sources)
        diversity = len({str(src.get("source_ref") or src.get("id") or "") for src in sources if isinstance(src, dict)})
        source_score = min(100.0, 45.0 + source_count * 12.0 + max(0, diversity - 1) * 6.0)
        wording = 92.0 if 35 <= len(statement) <= 900 else 68.0
        distractor_score = 100.0
        if alternatives:
            correct_norm = set(_tokens(correct_text))
            sims = []
            for alt in alternatives:
                if str(alt.get("chave") or "").upper() == answer:
                    continue
                toks = _tokens(alt.get("texto"))
                sims.append(len(correct_norm & toks) / max(1, len(correct_norm | toks)))
            if sims and max(sims) > 0.84:
                flags.append("distrator_muito_proximo_da_resposta")
                distractor_score = 72.0
        overall = round(groundedness * .38 + source_score * .20 + wording * .16 + distractor_score * .18 + (100 if not critical else 25) * .08, 1)
        validation = {
            "version": GENERATION_CRITIC_VERSION, "overall_score": overall, "groundedness": round(groundedness,1),
            "source_score": round(source_score,1), "wording": wording, "distractor_quality": distractor_score,
            "flags": flags, "critical_flags": critical, "source_count": source_count,
            "status": "apto_para_revisao_humana" if overall >= 78 and not critical else "revisar",
            "independent_model": True,
            "claim_evaluation": {"version": claim_validation.get("version"), "claim_summary": claim_summary,
                                  "flags": claim_validation.get("flags", []), "claims": claim_validation.get("claims", [])},
        }
        status = "validado" if validation["status"] == "apto_para_revisao_humana" else "rascunho"
        with self.database.connect() as connection:
            connection.execute(
                "UPDATE qf_generation_drafts SET validation_json=?,validation_score=?,status=?,validated_at=? WHERE id=?",
                (_json(validation), overall, status, utc_now(), str(draft_id)),
            )
        return validation

    def review_generation_draft(self, draft_id: str, *, decision: str, note: str = "") -> dict:
        item = self.generation_draft(draft_id)
        decision = str(decision or "").casefold().strip()
        if decision not in {"aprovar", "rejeitar", "rascunho"}:
            raise ValueError("Decisão inválida.")
        validation = item.get("validation") or {}
        if decision == "aprovar" and (float(item.get("validation_score") or 0) < 78 or validation.get("critical_flags")):
            raise ValueError("O rascunho ainda não passou pela validação independente da Etapa 5.")
        status = {"aprovar":"aprovado", "rejeitar":"rejeitado", "rascunho":"rascunho"}[decision]
        with self.database.connect() as connection:
            connection.execute("UPDATE qf_generation_drafts SET status=?,human_note=?,reviewed_at=? WHERE id=?",
                               (status, str(note or "")[:2000], utc_now(), str(draft_id)))
        return self.generation_draft(draft_id)

    def mark_generation_published(self, draft_id: str, question_uid: str) -> dict:
        with self.database.connect() as connection:
            connection.execute("UPDATE qf_generation_drafts SET status='publicado',published_question_uid=?,published_at=? WHERE id=?",
                               (str(question_uid), utc_now(), str(draft_id)))
        return self.generation_draft(draft_id)

    def add_gold_question(self, question: dict, *, sources: list[dict] | None = None, label: str = "", notes: str = "") -> dict:
        uid = str(question.get("database_uid") or "")
        if not uid:
            raise ValueError("Questão precisa estar salva no banco para entrar no conjunto ouro.")
        answer = str(question.get("gabarito") or "").upper().strip()
        if not answer:
            raise ValueError("Questão ouro precisa ter gabarito definido.")
        now = utc_now()
        with self.database.connect() as connection:
            row = connection.execute("SELECT id FROM qf_gold_questions WHERE question_uid=?", (uid,)).fetchone()
            gold_id = str(row["id"]) if row else str(uuid.uuid4())
            connection.execute(
                """
                INSERT INTO qf_gold_questions(id,question_uid,label,expected_answer,expected_topic,source_snapshot_json,notes,active,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(question_uid) DO UPDATE SET label=excluded.label,expected_answer=excluded.expected_answer,
                    expected_topic=excluded.expected_topic,source_snapshot_json=excluded.source_snapshot_json,notes=excluded.notes,active=1,updated_at=excluded.updated_at
                """,
                (gold_id, uid, str(label or question.get("codigo_origem") or "Questão ouro"), answer,
                 str(question.get("assunto") or ""), _json(sources or []), str(notes or ""), 1, now, now),
            )
            raw_refs = list(question.get("referencias_legais") or []) if isinstance(question.get("referencias_legais"), list) else []
            detected_refs = _legal_refs(" ".join(str(x) for x in raw_refs) + " " + str(question.get("enunciado") or "") + " " + str(question.get("explicacao") or ""))
            suite = "juridica" if detected_refs else (str(question.get("materia") or "geral").strip().casefold().replace(" ", "_")[:80] or "geral")
            connection.execute(
                """INSERT INTO qf_gold_expectations(gold_id,suite,risk_level,min_claim_support,required_refs_json,forbidden_patterns_json,expected_currency_status,updated_at)
                   VALUES(?,?,?,?,?,?,?,?)
                   ON CONFLICT(gold_id) DO UPDATE SET suite=excluded.suite,required_refs_json=excluded.required_refs_json,updated_at=excluded.updated_at""",
                (gold_id, suite, "alto" if detected_refs else "normal", 65.0 if detected_refs else 58.0, _json(detected_refs), _json([]), "vigente", now),
            )
        return self.gold_question(gold_id)

    def gold_question(self, gold_id: str) -> dict:
        with self.database.connect() as connection:
            row = connection.execute(
                """SELECT g.*,q.source_code,q.subject,q.primary_topic,q.data_json FROM qf_gold_questions g
                   JOIN questions q ON q.uid=g.question_uid WHERE g.id=?""", (str(gold_id),)
            ).fetchone()
            expectation = connection.execute("SELECT * FROM qf_gold_expectations WHERE gold_id=?", (str(gold_id),)).fetchone()
        if not row:
            raise ValueError("Questão ouro não encontrada.")
        item = dict(row)
        try: item["sources"] = json.loads(item.pop("source_snapshot_json") or "[]")
        except Exception: item["sources"] = []
        try: item["question"] = json.loads(item.pop("data_json") or "{}")
        except Exception: item["question"] = {}
        if expectation:
            exp = dict(expectation)
            for key in ("required_refs_json", "forbidden_patterns_json"):
                try: exp[key.removesuffix("_json")] = json.loads(exp.pop(key) or "[]")
                except Exception: exp[key.removesuffix("_json")] = []
            item["expectations"] = exp
        else:
            item["expectations"] = {"suite":"geral","risk_level":"normal","min_claim_support":58.0,"required_refs":[],"forbidden_patterns":[],"expected_currency_status":"vigente"}
        return item

    def gold_questions(self, active_only: bool = True) -> list[dict]:
        with self.database.connect() as connection:
            rows = connection.execute("SELECT id FROM qf_gold_questions" + (" WHERE active=1" if active_only else "") + " ORDER BY created_at DESC").fetchall()
        return [self.gold_question(str(row["id"])) for row in rows]

    def record_gold_run(self, *, run_id: str, gold_id: str, model: str, predicted_answer: str,
                        response_text: str, answer_correct: bool | None, source_supported: bool | None,
                        score: float, flags: list[str]) -> dict:
        row_id = str(uuid.uuid4())
        with self.database.connect() as connection:
            connection.execute(
                """INSERT INTO qf_gold_runs(id,run_id,gold_id,model,predicted_answer,response_text,answer_correct,source_supported,score,flags_json,created_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (row_id,str(run_id),str(gold_id),str(model),str(predicted_answer),str(response_text),
                 None if answer_correct is None else int(bool(answer_correct)), None if source_supported is None else int(bool(source_supported)),
                 float(score),_json(flags),utc_now()),
            )
        return {"id":row_id,"run_id":run_id,"gold_id":gold_id,"model":model,"predicted_answer":predicted_answer,
                "answer_correct":answer_correct,"source_supported":source_supported,"score":score,"flags":flags}

    def record_gold_claim_evaluation(self, run_item_id: str, evaluation: dict) -> dict:
        summary = dict(evaluation.get("claim_summary") or {})
        row = {
            "run_item_id": str(run_item_id),
            "claim_support_score": float(evaluation.get("groundedness") or 0),
            "supported_claims": int(summary.get("supported") or 0),
            "contradicted_claims": int(summary.get("contradicted") or 0),
            "insufficient_claims": int(summary.get("insufficient") or 0),
            "temporal_flags": sum(1 for flag in (evaluation.get("flags") or []) if "vigencia" in str(flag) or "temporal" in str(flag)),
        }
        with self.database.connect() as connection:
            connection.execute(
                """INSERT INTO qf_gold_run_evaluations(run_item_id,claim_support_score,supported_claims,contradicted_claims,insufficient_claims,temporal_flags,details_json,created_at)
                   VALUES(?,?,?,?,?,?,?,?)
                   ON CONFLICT(run_item_id) DO UPDATE SET claim_support_score=excluded.claim_support_score,
                     supported_claims=excluded.supported_claims,contradicted_claims=excluded.contradicted_claims,
                     insufficient_claims=excluded.insufficient_claims,temporal_flags=excluded.temporal_flags,
                     details_json=excluded.details_json,created_at=excluded.created_at""",
                (row["run_item_id"], row["claim_support_score"], row["supported_claims"], row["contradicted_claims"],
                 row["insufficient_claims"], row["temporal_flags"], _json(evaluation), utc_now()),
            )
        return row

    def gold_dashboard(self) -> dict:
        with self.database.connect() as connection:
            total = int(connection.execute("SELECT COUNT(*) FROM qf_gold_questions WHERE active=1").fetchone()[0])
            last_run = connection.execute("SELECT run_id,MAX(created_at) created_at FROM qf_gold_runs GROUP BY run_id ORDER BY created_at DESC LIMIT 1").fetchone()
            summary = None
            if last_run:
                row = connection.execute(
                    """SELECT COUNT(*) n,AVG(r.score) avg_score,SUM(CASE WHEN r.answer_correct=1 THEN 1 ELSE 0 END) correct,
                              AVG(ge.claim_support_score) claim_support,
                              SUM(COALESCE(ge.supported_claims,0)) supported,
                              SUM(COALESCE(ge.contradicted_claims,0)) contradicted,
                              SUM(COALESCE(ge.insufficient_claims,0)) insufficient,
                              SUM(COALESCE(ge.temporal_flags,0)) temporal_flags
                       FROM qf_gold_runs r LEFT JOIN qf_gold_run_evaluations ge ON ge.run_item_id=r.id
                       WHERE r.run_id=?""", (last_run["run_id"],)
                ).fetchone()
                summary = {
                    "run_id":str(last_run["run_id"]),"created_at":str(last_run["created_at"]),"cases":int(row["n"] or 0),
                    "average_score":round(float(row["avg_score"] or 0),1),"correct":int(row["correct"] or 0),
                    "claim_support_score":round(float(row["claim_support"] or 0),1),
                    "supported_claims":int(row["supported"] or 0),"contradicted_claims":int(row["contradicted"] or 0),
                    "insufficient_claims":int(row["insufficient"] or 0),"temporal_flags":int(row["temporal_flags"] or 0),
                }
        return {"active_gold_questions":total,"last_run":summary,"evaluator":GOLD_EVALUATOR_VERSION,
                "method":"answer_accuracy_plus_claim_evidence_regression"}

    def record_provider_metric(self, *, provider: str, model: str, operation: str, status: str,
                               interaction_id: str | None = None, latency_ms: float = 0,
                               usage: dict | None = None, estimated_cost_usd: float | None = None,
                               structured_output: bool = False, prompt_injection_flags: int = 0,
                               error_code: str = "") -> dict:
        metric_id = str(uuid.uuid4())
        usage = dict(usage or {})
        with self.database.connect() as connection:
            connection.execute(
                """INSERT INTO qf_ai_provider_metrics(
                       id,interaction_id,provider,model,operation,status,latency_ms,input_tokens,output_tokens,
                       cache_read_tokens,estimated_cost_usd,structured_output,prompt_injection_flags,error_code,created_at
                   ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (metric_id, str(interaction_id) if interaction_id else None, str(provider), str(model), str(operation), str(status),
                 float(latency_ms or 0), int(usage.get("input_tokens") or 0), int(usage.get("output_tokens") or 0),
                 int(usage.get("cache_read_tokens") or 0), None if estimated_cost_usd is None else float(estimated_cost_usd),
                 int(bool(structured_output)), int(prompt_injection_flags or 0), str(error_code or "")[:160], utc_now()),
            )
        return {"id": metric_id, "provider": provider, "model": model, "operation": operation, "status": status}

    def provider_telemetry(self, *, days: int = 30) -> dict:
        days = max(1, min(365, int(days or 30)))
        with self.database.connect() as connection:
            rows = connection.execute(
                """SELECT provider,model,COUNT(*) calls,
                          SUM(CASE WHEN status='ok' THEN 1 ELSE 0 END) ok_calls,
                          AVG(latency_ms) avg_latency_ms,
                          SUM(input_tokens) input_tokens,SUM(output_tokens) output_tokens,
                          SUM(cache_read_tokens) cache_read_tokens,
                          SUM(COALESCE(estimated_cost_usd,0)) estimated_cost_usd,
                          SUM(prompt_injection_flags) prompt_injection_flags,
                          SUM(structured_output) structured_calls
                   FROM qf_ai_provider_metrics
                   WHERE julianday(created_at) >= julianday('now', ?)
                   GROUP BY provider,model ORDER BY calls DESC, provider""",
                (f"-{days} days",),
            ).fetchall()
            total = connection.execute(
                """SELECT COUNT(*) calls,SUM(input_tokens) input_tokens,SUM(output_tokens) output_tokens,
                          SUM(COALESCE(estimated_cost_usd,0)) cost,SUM(prompt_injection_flags) injection_flags,
                          AVG(latency_ms) avg_latency
                   FROM qf_ai_provider_metrics WHERE julianday(created_at) >= julianday('now', ?)""",
                (f"-{days} days",),
            ).fetchone()
        items=[]
        for row in rows:
            calls=int(row["calls"] or 0); ok=int(row["ok_calls"] or 0)
            items.append({
                "provider":str(row["provider"]),"model":str(row["model"] or ""),"calls":calls,
                "success_rate":round(ok/max(1,calls)*100,1),"avg_latency_ms":round(float(row["avg_latency_ms"] or 0),1),
                "input_tokens":int(row["input_tokens"] or 0),"output_tokens":int(row["output_tokens"] or 0),
                "cache_read_tokens":int(row["cache_read_tokens"] or 0),
                "estimated_cost_usd":round(float(row["estimated_cost_usd"] or 0),6),
                "prompt_injection_flags":int(row["prompt_injection_flags"] or 0),
                "structured_calls":int(row["structured_calls"] or 0),
            })
        return {
            "days":days,"calls":int(total["calls"] or 0),"input_tokens":int(total["input_tokens"] or 0),
            "output_tokens":int(total["output_tokens"] or 0),"estimated_cost_usd":round(float(total["cost"] or 0),6),
            "prompt_injection_flags":int(total["injection_flags"] or 0),"avg_latency_ms":round(float(total["avg_latency"] or 0),1),
            "items":items,
            "cost_note":"Custos só são estimados quando você configura os preços por 1M tokens; o QuestFlow não congela tabelas comerciais no código.",
        }

    def dashboard(self) -> dict:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT COUNT(*) AS total,
                       SUM(CASE WHEN status='rascunho' THEN 1 ELSE 0 END) AS drafts,
                       SUM(CASE WHEN status='aprovado' THEN 1 ELSE 0 END) AS approved,
                       SUM(CASE WHEN status='rejeitado' THEN 1 ELSE 0 END) AS rejected
                FROM qf_ai_interactions
                """
            ).fetchone()
            diag = connection.execute("SELECT COUNT(*) FROM qf_error_diagnoses").fetchone()[0]
            avg = connection.execute("SELECT AVG(overall_score) FROM qf_ai_evaluations").fetchone()[0]
            generated = connection.execute("SELECT COUNT(*) FROM qf_generation_drafts").fetchone()[0]
            gold = connection.execute("SELECT COUNT(*) FROM qf_gold_questions WHERE active=1").fetchone()[0]
        return {
            "interactions": int(row["total"] or 0), "drafts": int(row["drafts"] or 0),
            "approved": int(row["approved"] or 0), "rejected": int(row["rejected"] or 0),
            "diagnoses": int(diag or 0), "average_evaluation": round(float(avg or 0), 1),
            "generation_drafts": int(generated or 0), "gold_questions": int(gold or 0),
            "telemetry_30d": self.provider_telemetry(days=30),
            "policy": "human_in_the_loop",
        }

    def health(self) -> dict:
        dashboard = self.dashboard()
        return {"id": self.engine_id, "name": self.name, "version": self.version, "status": "ready", "metrics": dashboard}
