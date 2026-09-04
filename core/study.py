from __future__ import annotations

import json
import math
import random
import re
import sqlite3
import unicodedata
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable

from .storage import QuestFlowDatabase
from .adaptive_engine import (
    DEFAULT_TARGET_RETENTION,
    MemoryState,
    OnlineRecallModel,
    adaptive_priority_score,
    forgetting_curve,
    update_memory_state,
)
from .fsrs_adapter import (
    DEFAULT_MAXIMUM_INTERVAL,
    batch_retrievability,
    current_retrievability,
    fsrs_available,
    fsrs_version,
    optimizer_available,
    optimize_review_logs,
    review_with_fsrs,
)
from .topic_bandit import BANDIT_VERSION, TopicState, topic_priority
from .gamification import GAME_ENGINE_VERSION, calculate_reward, level_from_xp
from .schema_migrations import apply_migration, ensure_columns
from .calibration import calibration_report as build_calibration_report
from .learner_model import (
    MODEL_VERSION as LEARNER_MODEL_VERSION,
    fusion_priority,
    item_difficulty_label,
    mastery_confidence,
    mastery_label,
    theta_percentile,
    update_bkt,
    update_irt_online,
    evidence_status,
    predict_success_selective,
    counterfactual_practice_plan,
)
from .recommender import (
    MODEL_VERSION as RECOMMENDER_VERSION,
    blended_projection,
    diversity_adjusted_value,
    multiobjective_priority,
)
from .learning_analytics import (
    DASHBOARD_ANALYTICS_VERSION,
    DEFAULT_COVERAGE_TARGET,
    DEFAULT_PERFORMANCE_TARGET,
    DEFAULT_RECENT_WINDOW,
    exam_urgency as analytics_exam_urgency,
    sample_confidence,
    subject_priority as analytics_subject_priority,
    trend_delta as analytics_trend_delta,
    weighted_recent_accuracy,
)


def utc_now_dt() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def utc_now() -> str:
    return utc_now_dt().isoformat()


def _iso_after(*, hours: float = 0, days: float = 0) -> str:
    return (utc_now_dt() + timedelta(hours=hours, days=days)).isoformat()


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None



def bayesian_error_probability(correct: int, wrong: int, *, alpha: float = 1.5, beta: float = 1.5) -> float:
    """Estimate error probability with a Beta prior so tiny samples do not dominate."""
    correct = max(0, int(correct))
    wrong = max(0, int(wrong))
    return (wrong + alpha) / (correct + wrong + alpha + beta)


def recency_priority(age_days: float, *, half_life_days: float = 14.0) -> float:
    """Smoothly increase priority as an item becomes older."""
    age_days = max(0.0, float(age_days))
    half_life_days = max(0.25, float(half_life_days))
    return 1.0 - math.exp(-math.log(2.0) * age_days / half_life_days)


def adaptive_interval_days(*, streak: int, ease: float, correct: int, wrong: int) -> float:
    """Conservative SM-2-inspired interval adjusted by Bayesian error probability."""
    streak = max(1, int(streak))
    ease = min(3.2, max(1.3, float(ease)))
    bases = (1.0, 3.0, 7.0, 14.0, 30.0, 60.0, 90.0)
    base = bases[min(streak - 1, len(bases) - 1)]
    error_probability = bayesian_error_probability(correct, wrong)
    reliability_factor = max(0.55, 1.15 - error_probability)
    ease_factor = max(0.70, min(1.35, ease / 2.5))
    return round(max(0.5, min(180.0, base * reliability_factor * ease_factor)), 2)


def _answer_index(question: dict) -> int | None:
    alternatives = question.get("alternativas", [])
    if not isinstance(alternatives, list):
        return None
    telegram = question.get("telegram", {})
    if isinstance(telegram, dict):
        value = telegram.get("indice_correto")
        if isinstance(value, int) and 0 <= value < len(alternatives):
            return value
    answer = str(question.get("gabarito", "")).strip().upper()
    keys = [str(item.get("chave", "")).strip().upper() for item in alternatives if isinstance(item, dict)]
    return keys.index(answer) if answer in keys else None


@dataclass(slots=True)
class SelectionFilters:
    subjects: list[str]
    topic: str = ""
    approved_only: bool = True
    strategy: str = "auditor_inteligente"
    recycle_when_empty: bool = True
    recommendation_mode: str = "equilibrado"
    board: str = ""
    exclude_uids: tuple[str, ...] = ()
    include_uids: tuple[str, ...] = ()


class StudyRepository:
    """Persistência do ciclo, das respostas e da repetição espaçada."""

    def __init__(self, database: QuestFlowDatabase):
        self.database = database
        self.initialize()

    def initialize(self) -> None:
        with self.database.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS study_state (
                    question_uid TEXT PRIMARY KEY,
                    sent_count INTEGER NOT NULL DEFAULT 0,
                    correct_count INTEGER NOT NULL DEFAULT 0,
                    wrong_count INTEGER NOT NULL DEFAULT 0,
                    streak INTEGER NOT NULL DEFAULT 0,
                    last_sent_at TEXT,
                    last_answered_at TEXT,
                    due_at TEXT,
                    ease REAL NOT NULL DEFAULT 2.5,
                    suspended INTEGER NOT NULL DEFAULT 0,
                    FOREIGN KEY(question_uid) REFERENCES questions(uid) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS telegram_deliveries (
                    id TEXT PRIMARY KEY,
                    cycle_id TEXT NOT NULL,
                    question_uid TEXT NOT NULL,
                    poll_id TEXT UNIQUE,
                    chat_id TEXT NOT NULL,
                    message_id INTEGER,
                    sent_at TEXT NOT NULL,
                    direct_poll INTEGER NOT NULL DEFAULT 1,
                    status TEXT NOT NULL DEFAULT 'enviado',
                    error_text TEXT,
                    FOREIGN KEY(question_uid) REFERENCES questions(uid) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS telegram_attempts (
                    id TEXT PRIMARY KEY,
                    delivery_id TEXT NOT NULL,
                    question_uid TEXT NOT NULL,
                    poll_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    username TEXT,
                    selected_indices_json TEXT NOT NULL,
                    is_correct INTEGER NOT NULL,
                    answered_at TEXT NOT NULL,
                    UNIQUE(delivery_id, user_id),
                    FOREIGN KEY(delivery_id) REFERENCES telegram_deliveries(id) ON DELETE CASCADE,
                    FOREIGN KEY(question_uid) REFERENCES questions(uid) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS study_cycles (
                    id TEXT PRIMARY KEY,
                    cycle_kind TEXT NOT NULL,
                    scheduled_for TEXT,
                    scheduled_date TEXT,
                    requested_via TEXT NOT NULL DEFAULT 'programa',
                    planned_count INTEGER NOT NULL DEFAULT 0,
                    sent_count INTEGER NOT NULL DEFAULT 0,
                    error_count INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'iniciado',
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    notes TEXT
                );

                CREATE TABLE IF NOT EXISTS telegram_review_requests (
                    id TEXT PRIMARY KEY,
                    question_uid TEXT NOT NULL,
                    chat_id TEXT,
                    user_id TEXT,
                    username TEXT,
                    message_id INTEGER,
                    source TEXT NOT NULL DEFAULT 'botao_telegram',
                    status TEXT NOT NULL DEFAULT 'pendente',
                    note TEXT,
                    requested_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    opened_at TEXT,
                    resolved_at TEXT,
                    FOREIGN KEY(question_uid) REFERENCES questions(uid) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS telegram_callback_inbox (
                    id TEXT PRIMARY KEY,
                    update_id INTEGER UNIQUE,
                    callback_id TEXT,
                    callback_data TEXT,
                    payload_json TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pendente',
                    attempt_count INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT,
                    next_retry_at TEXT,
                    received_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    processed_at TEXT
                );

                CREATE TABLE IF NOT EXISTS telegram_outbox (
                    id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    chat_id TEXT NOT NULL,
                    text TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pendente',
                    attempt_count INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT,
                    next_retry_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    sent_at TEXT
                );

                CREATE TABLE IF NOT EXISTS flow_runtime (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS adaptive_model_state (
                    id INTEGER PRIMARY KEY CHECK(id = 1),
                    model_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS topic_learning_state (
                    subject TEXT NOT NULL,
                    topic TEXT NOT NULL,
                    correct_count INTEGER NOT NULL DEFAULT 0,
                    wrong_count INTEGER NOT NULL DEFAULT 0,
                    exposure_count INTEGER NOT NULL DEFAULT 0,
                    last_seen_at TEXT,
                    last_score REAL NOT NULL DEFAULT 0.0,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY(subject, topic)
                );

                CREATE TABLE IF NOT EXISTS learner_profile (
                    id INTEGER PRIMARY KEY CHECK(id = 1),
                    total_xp INTEGER NOT NULL DEFAULT 0,
                    level INTEGER NOT NULL DEFAULT 1,
                    best_streak INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS xp_events (
                    id TEXT PRIMARY KEY,
                    question_uid TEXT NOT NULL,
                    xp INTEGER NOT NULL,
                    reason TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(question_uid) REFERENCES questions(uid) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS qf_question_currency (
                    question_uid TEXT PRIMARY KEY,
                    status TEXT NOT NULL DEFAULT 'vigente',
                    reference_date TEXT,
                    reason TEXT,
                    source_kind TEXT NOT NULL DEFAULT 'manual',
                    reviewed_at TEXT,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(question_uid) REFERENCES questions(uid) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_qf_question_currency_status
                    ON qf_question_currency(status, updated_at DESC);

                CREATE INDEX IF NOT EXISTS idx_study_due ON study_state(due_at);
                CREATE INDEX IF NOT EXISTS idx_study_suspended_due ON study_state(suspended, due_at);
                CREATE INDEX IF NOT EXISTS idx_delivery_sent ON telegram_deliveries(sent_at);
                CREATE INDEX IF NOT EXISTS idx_delivery_poll ON telegram_deliveries(poll_id);
                CREATE INDEX IF NOT EXISTS idx_attempt_answered ON telegram_attempts(answered_at);
                CREATE INDEX IF NOT EXISTS idx_cycle_scheduled_date ON study_cycles(scheduled_date, cycle_kind, status);
                CREATE INDEX IF NOT EXISTS idx_review_request_status ON telegram_review_requests(status, requested_at);
                CREATE INDEX IF NOT EXISTS idx_review_request_question ON telegram_review_requests(question_uid);
                CREATE INDEX IF NOT EXISTS idx_callback_inbox_status ON telegram_callback_inbox(status, next_retry_at, received_at);
                CREATE INDEX IF NOT EXISTS idx_outbox_status ON telegram_outbox(status, next_retry_at, created_at);
                CREATE INDEX IF NOT EXISTS idx_topic_learning_priority ON topic_learning_state(last_score DESC, updated_at);
                CREATE INDEX IF NOT EXISTS idx_xp_events_created ON xp_events(created_at);
                """
            )
            apply_migration(
                connection,
                component="study",
                version=1,
                name="delivery retry and unanswered columns",
                callback=lambda conn: ensure_columns(
                    conn,
                    "telegram_deliveries",
                    {
                        "attempt_count": "INTEGER NOT NULL DEFAULT 1",
                        "last_attempt_at": "TEXT",
                        "next_retry_at": "TEXT",
                        "error_category": "TEXT",
                        "is_retryable": "INTEGER NOT NULL DEFAULT 0",
                        "resolved_by_delivery_id": "TEXT",
                        "parent_delivery_id": "TEXT",
                        "resend_reason": "TEXT",
                        "unanswered_resend_count": "INTEGER NOT NULL DEFAULT 0",
                        "last_unanswered_check_at": "TEXT",
                    },
                ),
            )
            apply_migration(
                connection,
                component="study",
                version=2,
                name="adaptive and correction state columns",
                callback=lambda conn: ensure_columns(
                    conn,
                    "study_state",
                    {
                        "correction_priority": "INTEGER NOT NULL DEFAULT 0",
                        "correction_requested_at": "TEXT",
                        "correction_resolved_at": "TEXT",
                        "memory_difficulty": "REAL NOT NULL DEFAULT 5.0",
                        "memory_stability": "REAL NOT NULL DEFAULT 1.0",
                        "memory_retrievability": "REAL NOT NULL DEFAULT 0.9",
                        "response_time_ema": "REAL NOT NULL DEFAULT 0.0",
                        "adaptive_prediction": "REAL NOT NULL DEFAULT 0.5",
                        "adaptive_priority": "REAL NOT NULL DEFAULT 0.0",
                        "adaptive_model_version": "TEXT NOT NULL DEFAULT 'qf-adaptive-1'",
                        "fsrs_card_json": "TEXT",
                        "fsrs_due_at": "TEXT",
                        "fsrs_rating": "INTEGER",
                        "fsrs_version": "TEXT",
                    },
                ),
            )
            apply_migration(
                connection,
                component="study",
                version=3,
                name="feedback and calibration attempt columns",
                callback=lambda conn: ensure_columns(
                    conn,
                    "telegram_attempts",
                    {
                        "feedback_sent_at": "TEXT",
                        "feedback_message_id": "INTEGER",
                        "predicted_probability": "REAL",
                        "prediction_model_version": "TEXT",
                        "response_seconds": "REAL",
                        # Needed by later analytics migrations on a brand-new 6.9 database.
                        # Existing databases receive the full mobile timing schema in v12.
                        "timing_quality": "TEXT",
                        "timing_source": "TEXT",
                    },
                ),
            )

            def _create_study_indexes(conn: sqlite3.Connection) -> None:
                conn.executescript(
                    """
                    CREATE INDEX IF NOT EXISTS idx_delivery_status_retry ON telegram_deliveries(status, next_retry_at);
                    CREATE INDEX IF NOT EXISTS idx_delivery_parent ON telegram_deliveries(parent_delivery_id);
                    CREATE INDEX IF NOT EXISTS idx_study_correction_priority ON study_state(correction_priority, suspended, due_at);
                    CREATE INDEX IF NOT EXISTS idx_study_adaptive_priority ON study_state(adaptive_priority DESC);
                    CREATE INDEX IF NOT EXISTS idx_attempt_prediction ON telegram_attempts(predicted_probability, answered_at);
                    """
                )

            apply_migration(
                connection,
                component="study",
                version=4,
                name="adaptive study and calibration indexes",
                callback=_create_study_indexes,
            )

            def _create_coverage_indexes(conn: sqlite3.Connection) -> None:
                conn.executescript(
                    """
                    CREATE INDEX IF NOT EXISTS idx_delivery_question_status_sent
                        ON telegram_deliveries(question_uid, status, sent_at);
                    CREATE INDEX IF NOT EXISTS idx_attempt_question_answered
                        ON telegram_attempts(question_uid, answered_at);
                    """
                )

            apply_migration(
                connection,
                component="study",
                version=5,
                name="lesson coverage read indexes",
                callback=_create_coverage_indexes,
            )

            def _fsrs6_schema(conn: sqlite3.Connection) -> None:
                ensure_columns(
                    conn,
                    "study_state",
                    {
                        "fsrs_state": "TEXT NOT NULL DEFAULT 'new'",
                        "fsrs_lapses": "INTEGER NOT NULL DEFAULT 0",
                        "last_selection_reason": "TEXT",
                        "last_selection_bucket": "TEXT",
                    },
                )
                ensure_columns(
                    conn,
                    "telegram_attempts",
                    {
                        "confidence": "TEXT",
                        "error_type": "TEXT",
                        "fsrs_rating": "INTEGER",
                        "fsrs_review_log_json": "TEXT",
                        "fsrs_predicted_probability": "REAL",
                    },
                )
                conn.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS fsrs_optimizer_state (
                        id INTEGER PRIMARY KEY CHECK(id = 1),
                        parameters_json TEXT,
                        desired_retention REAL,
                        review_count INTEGER NOT NULL DEFAULT 0,
                        question_count INTEGER NOT NULL DEFAULT 0,
                        trained_at TEXT,
                        fsrs_version TEXT,
                        status TEXT NOT NULL DEFAULT 'aguardando',
                        error_text TEXT,
                        updated_at TEXT NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS studied_scope (
                        subject_norm TEXT NOT NULL,
                        lesson_norm TEXT NOT NULL,
                        trail TEXT,
                        source_row INTEGER,
                        updated_at TEXT NOT NULL,
                        PRIMARY KEY(subject_norm, lesson_norm, trail, source_row)
                    );
                    CREATE TABLE IF NOT EXISTS lesson_learning_state (
                        subject TEXT NOT NULL,
                        lesson TEXT NOT NULL,
                        correct_count INTEGER NOT NULL DEFAULT 0,
                        wrong_count INTEGER NOT NULL DEFAULT 0,
                        exposure_count INTEGER NOT NULL DEFAULT 0,
                        last_seen_at TEXT,
                        last_score REAL NOT NULL DEFAULT 0.0,
                        updated_at TEXT NOT NULL,
                        PRIMARY KEY(subject, lesson)
                    );
                    CREATE INDEX IF NOT EXISTS idx_study_fsrs_state_due
                        ON study_state(fsrs_state, suspended, due_at);
                    CREATE INDEX IF NOT EXISTS idx_attempt_fsrs_log
                        ON telegram_attempts(fsrs_review_log_json, answered_at);
                    CREATE INDEX IF NOT EXISTS idx_studied_scope_subject_lesson
                        ON studied_scope(subject_norm, lesson_norm);
                    CREATE INDEX IF NOT EXISTS idx_lesson_learning_seen
                        ON lesson_learning_state(subject, lesson, last_seen_at);
                    """
                )
                conn.execute(
                    """
                    INSERT OR IGNORE INTO fsrs_optimizer_state(
                        id, review_count, question_count, status, updated_at
                    ) VALUES (1, 0, 0, 'aguardando', ?)
                    """,
                    (utc_now(),),
                )

            apply_migration(
                connection,
                component="study",
                version=6,
                name="FSRS-6 optimizer, relearning and studied scope",
                callback=_fsrs6_schema,
            )

            def _learning_analytics_schema(conn: sqlite3.Connection) -> None:
                ensure_columns(
                    conn,
                    "telegram_attempts",
                    {
                        "perceived_difficulty": "TEXT",
                        "learning_gap": "INTEGER",
                        "meta_updated_at": "TEXT",
                    },
                )
                conn.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS subject_analytics_daily (
                        subject TEXT NOT NULL,
                        day TEXT NOT NULL,
                        attempts INTEGER NOT NULL DEFAULT 0,
                        correct INTEGER NOT NULL DEFAULT 0,
                        wrong INTEGER NOT NULL DEFAULT 0,
                        avg_response_seconds REAL,
                        easy_count INTEGER NOT NULL DEFAULT 0,
                        medium_count INTEGER NOT NULL DEFAULT 0,
                        hard_count INTEGER NOT NULL DEFAULT 0,
                        learning_gap_count INTEGER NOT NULL DEFAULT 0,
                        updated_at TEXT NOT NULL,
                        PRIMARY KEY(subject, day)
                    );
                    CREATE INDEX IF NOT EXISTS idx_subject_analytics_day
                        ON subject_analytics_daily(day, subject);
                    CREATE INDEX IF NOT EXISTS idx_attempt_learning_meta
                        ON telegram_attempts(perceived_difficulty, learning_gap, answered_at);
                    """
                )
                # Migração dos dados já existentes: materializa a série diária
                # sem alterar nenhum histórico bruto. Novas respostas atualizam
                # somente o dia/matéria afetado.
                conn.execute("DELETE FROM subject_analytics_daily")
                conn.execute(
                    """
                    INSERT INTO subject_analytics_daily(
                        subject, day, attempts, correct, wrong, avg_response_seconds,
                        easy_count, medium_count, hard_count, learning_gap_count, updated_at
                    )
                    SELECT COALESCE(NULLIF(TRIM(q.subject), ''), 'Matéria não informada') AS subject,
                           substr(a.answered_at, 1, 10) AS day,
                           COUNT(*) AS attempts,
                           COALESCE(SUM(CASE WHEN a.is_correct = 1 THEN 1 ELSE 0 END), 0) AS correct,
                           COALESCE(SUM(CASE WHEN a.is_correct = 0 THEN 1 ELSE 0 END), 0) AS wrong,
                           AVG(CASE WHEN a.timing_quality IN ('valid','active_filtered') THEN NULLIF(a.response_seconds, 0) END) AS avg_response_seconds,
                           COALESCE(SUM(CASE WHEN a.perceived_difficulty = 'facil' THEN 1 ELSE 0 END), 0),
                           COALESCE(SUM(CASE WHEN a.perceived_difficulty = 'media' THEN 1 ELSE 0 END), 0),
                           COALESCE(SUM(CASE WHEN a.perceived_difficulty = 'dificil' THEN 1 ELSE 0 END), 0),
                           COALESCE(SUM(CASE WHEN a.learning_gap = 1 THEN 1 ELSE 0 END), 0),
                           ?
                    FROM telegram_attempts a
                    JOIN questions q ON q.uid = a.question_uid
                    WHERE a.answered_at IS NOT NULL AND substr(a.answered_at, 1, 10) <> ''
                    GROUP BY COALESCE(NULLIF(TRIM(q.subject), ''), 'Matéria não informada'), substr(a.answered_at, 1, 10)
                    """,
                    (utc_now(),),
                )

            apply_migration(
                connection,
                component="study",
                version=7,
                name="learning analytics trend, recency and metacognition",
                callback=_learning_analytics_schema,
            )

            def _learner_model_schema(conn: sqlite3.Connection) -> None:
                ensure_columns(
                    conn,
                    "study_state",
                    {
                        "kt_mastery": "REAL",
                        "kt_confidence": "REAL NOT NULL DEFAULT 0.0",
                        "irt_information": "REAL NOT NULL DEFAULT 0.0",
                        "learner_fusion_priority": "REAL NOT NULL DEFAULT 0.0",
                        "learner_model_version": "TEXT",
                    },
                )
                conn.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS concept_mastery (
                        concept_key TEXT PRIMARY KEY,
                        concept_type TEXT NOT NULL,
                        subject TEXT NOT NULL,
                        label TEXT NOT NULL,
                        mastery REAL NOT NULL DEFAULT 0.20,
                        confidence REAL NOT NULL DEFAULT 0.0,
                        exposure_count INTEGER NOT NULL DEFAULT 0,
                        correct_count INTEGER NOT NULL DEFAULT 0,
                        wrong_count INTEGER NOT NULL DEFAULT 0,
                        slip REAL NOT NULL DEFAULT 0.10,
                        guess REAL NOT NULL DEFAULT 0.20,
                        learn_rate REAL NOT NULL DEFAULT 0.14,
                        last_seen_at TEXT,
                        updated_at TEXT NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS learner_ability (
                        subject TEXT PRIMARY KEY,
                        theta REAL NOT NULL DEFAULT 0.0,
                        standard_error REAL NOT NULL DEFAULT 2.5,
                        attempt_count INTEGER NOT NULL DEFAULT 0,
                        correct_count INTEGER NOT NULL DEFAULT 0,
                        wrong_count INTEGER NOT NULL DEFAULT 0,
                        updated_at TEXT NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS question_irt (
                        question_uid TEXT PRIMARY KEY,
                        difficulty REAL NOT NULL DEFAULT 0.0,
                        discrimination REAL NOT NULL DEFAULT 1.0,
                        information REAL NOT NULL DEFAULT 0.25,
                        attempt_count INTEGER NOT NULL DEFAULT 0,
                        correct_count INTEGER NOT NULL DEFAULT 0,
                        wrong_count INTEGER NOT NULL DEFAULT 0,
                        updated_at TEXT NOT NULL,
                        FOREIGN KEY(question_uid) REFERENCES questions(uid) ON DELETE CASCADE
                    );
                    CREATE TABLE IF NOT EXISTS learner_model_events (
                        attempt_id TEXT PRIMARY KEY,
                        question_uid TEXT NOT NULL,
                        subject TEXT NOT NULL,
                        is_correct INTEGER NOT NULL,
                        mastery_after REAL,
                        theta_after REAL,
                        item_difficulty_after REAL,
                        item_information REAL,
                        model_version TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        FOREIGN KEY(question_uid) REFERENCES questions(uid) ON DELETE CASCADE
                    );
                    CREATE INDEX IF NOT EXISTS idx_concept_mastery_subject
                        ON concept_mastery(subject, mastery, confidence);
                    CREATE INDEX IF NOT EXISTS idx_question_irt_information
                        ON question_irt(information DESC, attempt_count);
                    CREATE INDEX IF NOT EXISTS idx_learner_events_question
                        ON learner_model_events(question_uid, created_at);
                    CREATE INDEX IF NOT EXISTS idx_study_learner_priority
                        ON study_state(learner_fusion_priority DESC, due_at);
                    """
                )

            apply_migration(
                connection,
                component="study",
                version=8,
                name="FSRS + Bayesian Knowledge Tracing + regularized online IRT",
                callback=_learner_model_schema,
            )

            def _stage4_schema(conn: sqlite3.Connection) -> None:
                ensure_columns(
                    conn,
                    "telegram_deliveries",
                    {"source": "TEXT NOT NULL DEFAULT 'telegram'"},
                )
                ensure_columns(
                    conn,
                    "telegram_attempts",
                    {"source": "TEXT NOT NULL DEFAULT 'telegram'"},
                )
                conn.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS adaptive_simulation_sessions (
                        id TEXT PRIMARY KEY,
                        mode TEXT NOT NULL DEFAULT 'equilibrado',
                        target_count INTEGER NOT NULL DEFAULT 10,
                        subject_filter_json TEXT NOT NULL DEFAULT '[]',
                        board_filter TEXT,
                        status TEXT NOT NULL DEFAULT 'em_andamento',
                        answered_count INTEGER NOT NULL DEFAULT 0,
                        correct_count INTEGER NOT NULL DEFAULT 0,
                        current_question_uid TEXT,
                        config_json TEXT NOT NULL DEFAULT '{}',
                        projection_json TEXT,
                        created_at TEXT NOT NULL,
                        started_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        finished_at TEXT,
                        FOREIGN KEY(current_question_uid) REFERENCES questions(uid) ON DELETE SET NULL
                    );
                    CREATE TABLE IF NOT EXISTS adaptive_simulation_items (
                        id TEXT PRIMARY KEY,
                        session_id TEXT NOT NULL,
                        ordinal INTEGER NOT NULL,
                        question_uid TEXT NOT NULL,
                        recommendation_score REAL NOT NULL DEFAULT 0.0,
                        recommendation_json TEXT NOT NULL DEFAULT '{}',
                        learner_snapshot_json TEXT NOT NULL DEFAULT '{}',
                        selected_index INTEGER,
                        correct_index INTEGER,
                        is_correct INTEGER,
                        response_seconds REAL,
                        confidence TEXT,
                        presented_at TEXT NOT NULL,
                        answered_at TEXT,
                        UNIQUE(session_id, ordinal),
                        UNIQUE(session_id, question_uid),
                        FOREIGN KEY(session_id) REFERENCES adaptive_simulation_sessions(id) ON DELETE CASCADE,
                        FOREIGN KEY(question_uid) REFERENCES questions(uid) ON DELETE CASCADE
                    );
                    CREATE INDEX IF NOT EXISTS idx_sim_session_status
                        ON adaptive_simulation_sessions(status, updated_at);
                    CREATE INDEX IF NOT EXISTS idx_sim_items_session
                        ON adaptive_simulation_items(session_id, ordinal);
                    CREATE INDEX IF NOT EXISTS idx_delivery_source
                        ON telegram_deliveries(source, sent_at);
                    CREATE INDEX IF NOT EXISTS idx_attempt_source
                        ON telegram_attempts(source, answered_at);
                    """
                )

            apply_migration(
                connection,
                component="study",
                version=9,
                name="multiobjective recommender and adaptive simulations",
                callback=_stage4_schema,
            )

            def _learner_uncertainty_schema(conn: sqlite3.Connection) -> None:
                ensure_columns(
                    conn,
                    "telegram_attempts",
                    {
                        "learner_predicted_probability": "REAL",
                        "learner_prediction_confidence": "REAL",
                        "learner_prediction_low": "REAL",
                        "learner_prediction_high": "REAL",
                        "learner_prediction_status": "TEXT",
                        "learner_prediction_reason": "TEXT",
                        "learner_prediction_version": "TEXT",
                    },
                )
                conn.executescript(
                    """
                    CREATE INDEX IF NOT EXISTS idx_attempt_learner_prediction
                        ON telegram_attempts(learner_prediction_status, learner_predicted_probability, answered_at);
                    """
                )

            apply_migration(
                connection,
                component="study",
                version=10,
                name="selective learner predictions, abstention and calibration",
                callback=_learner_uncertainty_schema,
            )

            def _tutor_scaffolding_schema(conn: sqlite3.Connection) -> None:
                ensure_columns(
                    conn,
                    "study_state",
                    {
                        "scaffold_dependency": "REAL NOT NULL DEFAULT 0.0",
                        "scaffold_last_level": "INTEGER",
                        "scaffold_session_count": "INTEGER NOT NULL DEFAULT 0",
                        "scaffold_solved_count": "INTEGER NOT NULL DEFAULT 0",
                    },
                )
                conn.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS tutor_scaffold_sessions (
                        id TEXT PRIMARY KEY,
                        question_uid TEXT NOT NULL,
                        representation TEXT NOT NULL DEFAULT 'texto',
                        user_prompt TEXT NOT NULL DEFAULT '',
                        media_notes TEXT NOT NULL DEFAULT '',
                        status TEXT NOT NULL DEFAULT 'em_andamento',
                        current_level INTEGER NOT NULL DEFAULT 0,
                        max_level_reached INTEGER NOT NULL DEFAULT 0,
                        solved_level INTEGER,
                        online INTEGER NOT NULL DEFAULT 0,
                        learner_snapshot_json TEXT NOT NULL DEFAULT '{}',
                        started_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        completed_at TEXT,
                        FOREIGN KEY(question_uid) REFERENCES questions(uid) ON DELETE CASCADE
                    );
                    CREATE TABLE IF NOT EXISTS tutor_scaffold_events (
                        id TEXT PRIMARY KEY,
                        session_id TEXT NOT NULL,
                        question_uid TEXT NOT NULL,
                        level INTEGER NOT NULL,
                        event_type TEXT NOT NULL,
                        representation TEXT NOT NULL DEFAULT 'texto',
                        content_preview TEXT,
                        metadata_json TEXT NOT NULL DEFAULT '{}',
                        created_at TEXT NOT NULL,
                        FOREIGN KEY(session_id) REFERENCES tutor_scaffold_sessions(id) ON DELETE CASCADE,
                        FOREIGN KEY(question_uid) REFERENCES questions(uid) ON DELETE CASCADE
                    );
                    CREATE INDEX IF NOT EXISTS idx_scaffold_sessions_question
                        ON tutor_scaffold_sessions(question_uid, updated_at DESC);
                    CREATE INDEX IF NOT EXISTS idx_scaffold_sessions_status
                        ON tutor_scaffold_sessions(status, updated_at DESC);
                    CREATE INDEX IF NOT EXISTS idx_scaffold_events_session
                        ON tutor_scaffold_events(session_id, created_at);
                    CREATE INDEX IF NOT EXISTS idx_scaffold_events_question
                        ON tutor_scaffold_events(question_uid, created_at DESC);
                    """
                )

            apply_migration(
                connection,
                component="study",
                version=11,
                name="progressive tutor scaffolding and learner support signal",
                callback=_tutor_scaffolding_schema,
            )

            def _mobile_timing_schema(conn: sqlite3.Connection) -> None:
                ensure_columns(
                    conn,
                    "telegram_attempts",
                    {
                        "account_id": "TEXT",
                        "tenant_id": "TEXT",
                        "learner_id": "TEXT",
                        "exam_project_id": "TEXT",
                        "device_id": "TEXT",
                        "session_id": "TEXT",
                        "question_revision": "INTEGER NOT NULL DEFAULT 1",
                        "response_wall_seconds": "REAL",
                        "response_idle_seconds": "REAL",
                        "timing_quality": "TEXT",
                        "timing_source": "TEXT",
                    },
                )
                # Tempos anteriores à 6.9.0 não distinguiam tela aberta de tempo
                # efetivamente ativo. Eles são preservados, mas deixam de entrar
                # nas médias/modelos de velocidade até possuírem medição confiável.
                conn.execute(
                    """
                    UPDATE telegram_attempts
                    SET timing_quality = COALESCE(timing_quality, 'legacy_unverified'),
                        timing_source = COALESCE(timing_source, 'legacy_wall_clock')
                    WHERE response_seconds IS NOT NULL
                    """
                )
                conn.executescript(
                    """
                    CREATE INDEX IF NOT EXISTS idx_attempt_timing_quality
                        ON telegram_attempts(timing_quality, answered_at);
                    CREATE INDEX IF NOT EXISTS idx_attempt_mobile_identity
                        ON telegram_attempts(tenant_id, learner_id, exam_project_id, answered_at);
                    CREATE INDEX IF NOT EXISTS idx_attempt_device_session
                        ON telegram_attempts(device_id, session_id, answered_at);
                    """
                )

            apply_migration(
                connection,
                component="study",
                version=12,
                name="mobile identity revision and active response timing quality gate",
                callback=_mobile_timing_schema,
            )
            connection.execute("INSERT OR IGNORE INTO study_state(question_uid) SELECT uid FROM questions")
            connection.execute(
                "INSERT OR IGNORE INTO learner_profile(id, total_xp, level, best_streak, updated_at) VALUES (1, 0, 1, 0, ?)",
                (utc_now(),),
            )

    def sync_questions(self) -> None:
        with self.database.connect() as connection:
            connection.execute("INSERT OR IGNORE INTO study_state(question_uid) SELECT uid FROM questions")

    def get_runtime(self, key: str, default: str = "") -> str:
        with self.database.connect() as connection:
            row = connection.execute("SELECT value FROM flow_runtime WHERE key = ?", (str(key),)).fetchone()
        return str(row[0]) if row and row[0] is not None else default

    def set_runtime(self, key: str, value: str) -> None:
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO flow_runtime(key, value, updated_at) VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
                """,
                (str(key), str(value), utc_now()),
            )

    def _load_adaptive_model(self, connection: sqlite3.Connection | None = None) -> OnlineRecallModel:
        if connection is None:
            with self.database.connect() as owned:
                row = owned.execute("SELECT model_json FROM adaptive_model_state WHERE id = 1").fetchone()
        else:
            row = connection.execute("SELECT model_json FROM adaptive_model_state WHERE id = 1").fetchone()
        return OnlineRecallModel.from_json(row[0] if row else None)

    def _save_adaptive_model(self, connection: sqlite3.Connection, model: OnlineRecallModel) -> None:
        connection.execute(
            """
            INSERT INTO adaptive_model_state(id, model_json, updated_at) VALUES (1, ?, ?)
            ON CONFLICT(id) DO UPDATE SET model_json = excluded.model_json, updated_at = excluded.updated_at
            """,
            (model.to_json(), utc_now()),
        )

    def adaptive_model_summary(self) -> dict:
        model = self._load_adaptive_model()
        return {
            "version": model.version,
            "samples": model.samples,
            "weights": dict(model.weights),
        }

    def set_target_retention(self, value: float) -> float:
        normalized = min(0.97, max(0.70, float(value)))
        self.set_runtime("target_retention", f"{normalized:.4f}")
        return normalized

    def set_learning_preferences(
        self,
        *,
        target_retention: float | None = None,
        retention_mode: str | None = None,
        exam_date: str | None = None,
        daily_minutes: int | None = None,
        maximum_interval_days: int | None = None,
        relearning_minutes: int | None = None,
        studied_only: bool | None = None,
        early_review_enabled: bool | None = None,
    ) -> dict:
        """Sincroniza preferências do scheduler para uso fora da camada de UI."""
        if target_retention is not None:
            self.set_target_retention(float(target_retention))
        if retention_mode is not None:
            mode = str(retention_mode or "manual").strip().lower()
            self.set_runtime("target_retention_mode", "optimized" if mode == "optimized" else "manual")
        if exam_date is not None:
            text = str(exam_date or "").strip()
            if text:
                try:
                    datetime.fromisoformat(text).date()
                except ValueError:
                    text = ""
            self.set_runtime("exam_date", text)
        if daily_minutes is not None:
            self.set_runtime("daily_study_minutes", str(max(5, min(600, int(daily_minutes)))))
        if maximum_interval_days is not None:
            self.set_runtime("fsrs_maximum_interval_days", str(max(1, min(36500, int(maximum_interval_days)))))
        if relearning_minutes is not None:
            self.set_runtime("fsrs_relearning_minutes", str(max(1, min(1440, int(relearning_minutes)))))
        if studied_only is not None:
            self.set_runtime("studied_only", "1" if studied_only else "0")
        if early_review_enabled is not None:
            self.set_runtime("early_review_enabled", "1" if early_review_enabled else "0")
        return self.learning_preferences()

    def learning_preferences(self) -> dict:
        try:
            manual_retention = float(self.get_runtime("target_retention", str(DEFAULT_TARGET_RETENTION)) or DEFAULT_TARGET_RETENTION)
        except (TypeError, ValueError):
            manual_retention = DEFAULT_TARGET_RETENTION
        try:
            daily_minutes = int(self.get_runtime("daily_study_minutes", "45") or 45)
        except (TypeError, ValueError):
            daily_minutes = 45
        try:
            maximum_interval = int(self.get_runtime("fsrs_maximum_interval_days", "365") or 365)
        except (TypeError, ValueError):
            maximum_interval = 365
        try:
            relearning = int(self.get_runtime("fsrs_relearning_minutes", "10") or 10)
        except (TypeError, ValueError):
            relearning = 10
        return {
            "manual_retention": min(0.97, max(0.70, manual_retention)),
            "retention_mode": self.get_runtime("target_retention_mode", "optimized") or "optimized",
            "exam_date": self.get_runtime("exam_date", ""),
            "daily_minutes": max(5, min(600, daily_minutes)),
            "maximum_interval_days": max(1, min(36500, maximum_interval)),
            "relearning_minutes": max(1, min(1440, relearning)),
            "studied_only": self.get_runtime("studied_only", "1") != "0",
            "early_review_enabled": self.get_runtime("early_review_enabled", "0") == "1",
        }

    def _optimizer_row(self, connection: sqlite3.Connection | None = None) -> sqlite3.Row | None:
        query = "SELECT * FROM fsrs_optimizer_state WHERE id = 1"
        if connection is None:
            with self.database.connect() as owned:
                return owned.execute(query).fetchone()
        return connection.execute(query).fetchone()

    def fsrs_parameters(self, connection: sqlite3.Connection | None = None) -> tuple[float, ...] | None:
        row = self._optimizer_row(connection)
        if not row or not str(row["parameters_json"] or "").strip():
            return None
        try:
            values = tuple(float(value) for value in json.loads(str(row["parameters_json"])))
        except Exception:
            return None
        return values if len(values) == 21 else None

    def effective_target_retention(self, connection: sqlite3.Connection | None = None) -> float:
        preferences = self.learning_preferences()
        value = float(preferences["manual_retention"])
        if str(preferences["retention_mode"]).lower() == "optimized":
            row = self._optimizer_row(connection)
            if row and row["desired_retention"] is not None:
                try:
                    value = float(row["desired_retention"])
                except (TypeError, ValueError):
                    pass
        return min(0.97, max(0.70, value))

    def _exam_due_cap(self, now: datetime | None = None) -> datetime | None:
        text = self.get_runtime("exam_date", "").strip()
        if not text:
            return None
        try:
            exam_day = datetime.fromisoformat(text).date()
        except ValueError:
            return None
        current = (now or utc_now_dt()).astimezone(timezone.utc)
        cap = datetime.combine(exam_day, datetime.min.time(), tzinfo=timezone.utc) - timedelta(hours=12)
        return max(current + timedelta(minutes=1), cap)

    def refresh_studied_scope(self, taxonomy_tasks: Iterable[dict]) -> dict:
        """Atualiza escopo estudado sem apagar conhecimento por ausência na planilha.

        Desde 6.15.0 a planilha é fonte de catálogo, não fonte absoluta do estado
        do aluno. Evidência positiva pode acrescentar conteúdo estudado; célula
        vazia em snapshot posterior nunca remove um registro já conhecido.
        """
        rows: list[tuple[str, str, str, int, str]] = []
        updated = utc_now()
        for index, raw in enumerate(taxonomy_tasks or []):
            task = dict(raw)
            studied = bool(task.get("estudado")) or any([
                int(task.get("ch_efetiva_min", 0) or 0) > 0,
                int(task.get("questoes_feitas", 0) or 0) > 0,
                int(task.get("acertos", 0) or 0) > 0,
                bool(str(task.get("data", "") or "").strip()),
            ])
            subject = str(task.get("materia", "") or "").strip()
            lesson = str(task.get("aula", "") or "").strip()
            if not studied or not subject or not lesson:
                continue
            rows.append((
                self._norm_coverage_text(subject), self._norm_lesson(lesson),
                str(task.get("trilha", "") or ""), int(task.get("row", index + 1) or index + 1), updated,
            ))
        with self.database.connect() as connection:
            if rows:
                connection.executemany(
                    "INSERT OR REPLACE INTO studied_scope(subject_norm, lesson_norm, trail, source_row, updated_at) VALUES (?, ?, ?, ?, ?)",
                    rows,
                )
            # Rehydrate from the separated Learner State when the catalog tables exist.
            tables = {str(r[0]) for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
            if {"course_catalog_lessons", "course_learner_state"} <= tables:
                durable = connection.execute(
                    """SELECT c.subject,c.lesson,c.trail,c.source_row
                       FROM course_learner_state l JOIN course_catalog_lessons c ON c.lesson_key=l.lesson_key
                       WHERE l.studied=1"""
                ).fetchall()
                durable_rows = [
                    (self._norm_coverage_text(r[0]), self._norm_lesson(r[1]), str(r[2] or ""), int(r[3] or 0), updated)
                    for r in durable if str(r[0] or "").strip() and str(r[1] or "").strip()
                ]
                if durable_rows:
                    connection.executemany(
                        "INSERT OR REPLACE INTO studied_scope(subject_norm, lesson_norm, trail, source_row, updated_at) VALUES (?, ?, ?, ?, ?)",
                        durable_rows,
                    )
        self.set_runtime("studied_scope_initialized", "1")
        with self.database.connect() as connection:
            count = int(connection.execute("SELECT COUNT(*) FROM studied_scope").fetchone()[0])
            groups = int(connection.execute("SELECT COUNT(*) FROM (SELECT 1 FROM studied_scope GROUP BY subject_norm,lesson_norm)").fetchone()[0])
        return {"groups": groups, "rows": count, "updated_at": updated}

    def _studied_scope(self) -> set[tuple[str, str]]:
        with self.database.connect() as connection:
            rows = connection.execute("SELECT DISTINCT subject_norm, lesson_norm FROM studied_scope").fetchall()
        return {(str(row[0]), str(row[1])) for row in rows}

    def fsrs_optimizer_status(self) -> dict:
        row = self._optimizer_row()
        parameters = self.fsrs_parameters()
        with self.database.connect() as connection:
            counts = connection.execute(
                """
                SELECT COUNT(*) AS total_reviews,
                       SUM(CASE WHEN fsrs_review_log_json IS NOT NULL THEN 1 ELSE 0 END) AS log_reviews,
                       COUNT(DISTINCT question_uid) AS question_count
                FROM telegram_attempts
                """
            ).fetchone()
        total_reviews = int(counts["total_reviews"] or 0) if counts else 0
        log_reviews = int(counts["log_reviews"] or 0) if counts else 0
        questions = int(counts["question_count"] or 0) if counts else 0
        return {
            "available": fsrs_available(), "optimizer_available": optimizer_available(),
            "fsrs_version": fsrs_version(), "parameters_active": bool(parameters),
            "parameters": list(parameters) if parameters else [],
            "desired_retention": float(row["desired_retention"]) if row and row["desired_retention"] is not None else None,
            "trained_review_count": int(row["review_count"] or 0) if row else 0,
            "current_review_logs": log_reviews, "total_reviews": total_reviews,
            "question_count": questions, "trained_at": str(row["trained_at"] or "") if row else "",
            "status": str(row["status"] or "aguardando") if row else "aguardando",
            "error": str(row["error_text"] or "") if row else "",
            "effective_retention": self.effective_target_retention(),
        }

    def should_optimize_fsrs(self, *, min_reviews: int = 50, min_questions: int = 10, min_new_reviews: int = 30) -> bool:
        status = self.fsrs_optimizer_status()
        if not status["available"] or not status["optimizer_available"]:
            return False
        total = int(status["total_reviews"])
        if total < max(10, int(min_reviews)) or int(status["question_count"]) < max(3, int(min_questions)):
            return False
        return total - int(status["trained_review_count"]) >= max(1, int(min_new_reviews))

    def rebuild_question_fsrs(
        self,
        question_uid: str,
        *,
        parameters: tuple[float, ...] | None = None,
        desired_retention: float | None = None,
    ) -> dict:
        """Reconstrói o cartão FSRS a partir do histórico objetivo da questão.

        Isto permite aplicar confiança retrospectiva, migrar históricos antigos e
        reagendar todo o banco após uma nova otimização sem duplicar revisões.
        """
        if not fsrs_available():
            return {"ok": False, "error": "Py-FSRS indisponível."}
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT a.id, a.is_correct, a.answered_at, a.confidence, a.error_type,
                       a.response_seconds, a.timing_quality, a.timing_source, d.sent_at
                FROM telegram_attempts a
                LEFT JOIN telegram_deliveries d ON d.id = a.delivery_id
                WHERE a.question_uid = ?
                ORDER BY a.answered_at ASC, a.id ASC
                """,
                (str(question_uid),),
            ).fetchall()
            if not rows:
                connection.execute(
                    "UPDATE study_state SET fsrs_card_json = NULL, fsrs_due_at = NULL, fsrs_state = 'new', fsrs_lapses = 0 WHERE question_uid = ?",
                    (str(question_uid),),
                )
                return {"ok": True, "reviews": 0, "state": "new"}

            prefs = self.learning_preferences()
            retention = float(desired_retention if desired_retention is not None else self.effective_target_retention(connection))
            params = parameters if parameters is not None else self.fsrs_parameters(connection)
            maximum_interval = int(prefs.get("maximum_interval_days", DEFAULT_MAXIMUM_INTERVAL) or DEFAULT_MAXIMUM_INTERVAL)
            relearning_minutes = int(prefs.get("relearning_minutes", 10) or 10)
            card_json: str | None = None
            correct_before = wrong_before = 0
            last_result = None
            response_ema = 0.0
            streak = 0
            last_answered = None
            for row in rows:
                answered = _parse_iso(row["answered_at"]) or utc_now_dt()
                timing_quality = str(row["timing_quality"] or "legacy_unverified")
                timing_eligible = timing_quality in {"valid", "active_filtered"}
                stored_response = row["response_seconds"]
                response_seconds = (
                    max(0.0, float(stored_response))
                    if timing_eligible and stored_response is not None
                    else 0.0
                )
                if timing_eligible and response_seconds > 0:
                    response_ema = response_seconds if response_ema <= 0 else (0.72 * response_ema + 0.28 * response_seconds)
                prior_accuracy = (correct_before + 1.0) / (correct_before + wrong_before + 2.0)
                exam_cap = self._exam_due_cap(answered)
                interval_limit = maximum_interval
                if exam_cap is not None:
                    interval_limit = min(interval_limit, max(1, int((exam_cap - answered).total_seconds() // 86400) + 1))
                fsrs_prediction = current_retrievability(
                    card_json, desired_retention=retention, parameters=params, now=answered
                )
                result = review_with_fsrs(
                    card_json, correct=bool(row["is_correct"]), response_seconds=response_seconds,
                    prior_accuracy=prior_accuracy, desired_retention=retention, now=answered,
                    confidence=str(row["confidence"] or ""), parameters=params,
                    relearning_steps_minutes=(relearning_minutes,), maximum_interval=interval_limit, due_cap=exam_cap,
                )
                if result is None:
                    return {"ok": False, "error": "Falha ao reconstruir revisão com Py-FSRS."}
                card_json = result.card_json
                last_result = result
                connection.execute(
                    "UPDATE telegram_attempts SET fsrs_rating = ?, fsrs_review_log_json = ?, fsrs_predicted_probability = ? WHERE id = ?",
                    (result.rating, result.review_log_json, fsrs_prediction, str(row["id"])),
                )
                if row["is_correct"]:
                    correct_before += 1; streak += 1
                else:
                    wrong_before += 1; streak = 0
                last_answered = str(row["answered_at"] or "")

            if last_result is None:
                return {"ok": False, "error": "Histórico FSRS vazio."}
            connection.execute(
                """
                UPDATE study_state
                SET correct_count = ?, wrong_count = ?, streak = ?, last_answered_at = ?, due_at = ?,
                    memory_difficulty = ?, memory_stability = ?, memory_retrievability = ?, response_time_ema = ?,
                    fsrs_card_json = ?, fsrs_due_at = ?, fsrs_rating = ?, fsrs_version = ?, fsrs_state = ?, fsrs_lapses = ?
                WHERE question_uid = ?
                """,
                (
                    correct_before, wrong_before, streak, last_answered, last_result.due_at,
                    last_result.difficulty, last_result.stability, last_result.retrievability, response_ema,
                    last_result.card_json, last_result.due_at, last_result.rating, last_result.scheduler_version,
                    last_result.scheduler_state, wrong_before, str(question_uid),
                ),
            )
        return {
            "ok": True, "reviews": len(rows), "due_at": last_result.due_at,
            "state": last_result.scheduler_state, "rating": last_result.rating,
            "stability": last_result.stability, "difficulty": last_result.difficulty,
        }

    def rebuild_all_fsrs_states(
        self,
        *,
        parameters: tuple[float, ...] | None = None,
        desired_retention: float | None = None,
    ) -> dict:
        with self.database.connect() as connection:
            uids = [str(row[0]) for row in connection.execute(
                "SELECT DISTINCT question_uid FROM telegram_attempts ORDER BY question_uid"
            ).fetchall()]
        ok = failed = reviews = 0
        for uid in uids:
            result = self.rebuild_question_fsrs(uid, parameters=parameters, desired_retention=desired_retention)
            if result.get("ok"):
                ok += 1; reviews += int(result.get("reviews", 0) or 0)
            else:
                failed += 1
        return {"ok": failed == 0, "questions": ok, "failed": failed, "reviews": reviews}

    def optimize_fsrs(self, *, force: bool = False) -> dict:
        """Treina os 21 parâmetros FSRS e retenção ótima com todo o histórico real."""
        if not fsrs_available() or not optimizer_available():
            return {"ok": False, "error": "Py-FSRS com o extra optimizer não está disponível."}
        status = self.fsrs_optimizer_status()
        if not force and (int(status["total_reviews"]) < 50 or int(status["question_count"]) < 10):
            return {
                "ok": False, "waiting": True, "review_count": int(status["total_reviews"]),
                "question_count": int(status["question_count"]),
                "error": "Aguardando histórico suficiente para personalizar o FSRS (50 revisões em 10 questões).",
            }
        with self.database.connect() as connection:
            connection.execute(
                "UPDATE fsrs_optimizer_state SET status = 'otimizando', error_text = NULL, updated_at = ? WHERE id = 1",
                (utc_now(),),
            )
        # Migra históricos das versões antigas para ReviewLog oficial antes do treino.
        rebuilt = self.rebuild_all_fsrs_states(parameters=self.fsrs_parameters(), desired_retention=self.effective_target_retention())
        if not rebuilt.get("ok"):
            return {"ok": False, "error": "Não foi possível migrar todo o histórico para ReviewLog FSRS.", "rebuild": rebuilt}
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT fsrs_review_log_json, question_uid FROM telegram_attempts WHERE fsrs_review_log_json IS NOT NULL ORDER BY answered_at"
            ).fetchall()
        logs = [str(row["fsrs_review_log_json"] or "") for row in rows if str(row["fsrs_review_log_json"] or "").strip()]
        questions = len({str(row["question_uid"]) for row in rows})
        result = optimize_review_logs(logs, optimize_retention=True)
        if result is None:
            with self.database.connect() as connection:
                connection.execute(
                    "UPDATE fsrs_optimizer_state SET status = 'erro', error_text = ?, updated_at = ? WHERE id = 1",
                    ("O otimizador FSRS não conseguiu calcular parâmetros válidos.", utc_now()),
                )
            return {"ok": False, "error": "O otimizador FSRS não conseguiu calcular parâmetros válidos."}
        retention = float(result.desired_retention if result.desired_retention is not None else self.effective_target_retention())
        trained_at = utc_now()
        with self.database.connect() as connection:
            connection.execute(
                """
                UPDATE fsrs_optimizer_state
                SET parameters_json = ?, desired_retention = ?, review_count = ?, question_count = ?,
                    trained_at = ?, fsrs_version = ?, status = 'ativo', error_text = NULL, updated_at = ?
                WHERE id = 1
                """,
                (json.dumps(list(result.parameters)), retention, len(logs), questions, trained_at, result.scheduler_version, trained_at),
            )
        # Reagenda todos os cartões com os novos parâmetros aprendidos.
        rescheduled = self.rebuild_all_fsrs_states(parameters=tuple(result.parameters), desired_retention=retention)
        return {
            "ok": bool(rescheduled.get("ok")), "parameters": list(result.parameters),
            "desired_retention": retention, "review_count": len(logs), "question_count": questions,
            "trained_at": trained_at, "fsrs_version": result.scheduler_version, "rescheduled": rescheduled,
        }

    def learner_profile(self, connection: sqlite3.Connection | None = None) -> dict:
        if connection is None:
            with self.database.connect() as owned:
                row = owned.execute(
                    "SELECT total_xp, level, best_streak, updated_at FROM learner_profile WHERE id = 1"
                ).fetchone()
        else:
            row = connection.execute(
                "SELECT total_xp, level, best_streak, updated_at FROM learner_profile WHERE id = 1"
            ).fetchone()
        if not row:
            return {"total_xp": 0, "level": 1, "best_streak": 0, "progress": 0.0}
        level, progress = level_from_xp(int(row["total_xp"] or 0))
        return {
            "total_xp": int(row["total_xp"] or 0),
            "level": level,
            "best_streak": int(row["best_streak"] or 0),
            "progress": progress,
            "updated_at": row["updated_at"],
        }

    def _award_xp(
        self,
        connection: sqlite3.Connection,
        *,
        event_id: str,
        question_uid: str,
        correct: bool,
        difficulty: float,
        response_seconds: float,
        streak: int,
        first_attempt: bool,
    ) -> dict:
        existing = connection.execute("SELECT xp FROM xp_events WHERE id = ?", (event_id,)).fetchone()
        profile = self.learner_profile(connection)
        if existing:
            return {
                "xp": int(existing["xp"] or 0),
                "total_xp": profile["total_xp"],
                "level": profile["level"],
                "level_progress": profile["progress"],
                "duplicate": True,
            }
        reward = calculate_reward(
            correct=correct,
            difficulty=difficulty,
            response_seconds=response_seconds,
            streak=streak,
            first_attempt=first_attempt,
            total_xp_before=profile["total_xp"],
        )
        now = utc_now()
        connection.execute(
            "INSERT INTO xp_events(id, question_uid, xp, reason, created_at) VALUES (?, ?, ?, ?, ?)",
            (event_id, question_uid, reward.xp, reward.rationale, now),
        )
        total = profile["total_xp"] + reward.xp
        level, progress = level_from_xp(total)
        connection.execute(
            """
            UPDATE learner_profile
            SET total_xp = ?, level = ?, best_streak = MAX(best_streak, ?), updated_at = ?
            WHERE id = 1
            """,
            (total, level, max(0, int(streak)), now),
        )
        return {
            "xp": reward.xp,
            "total_xp": total,
            "level": level,
            "level_progress": progress,
            "title": reward.title,
            "rationale": reward.rationale,
            "duplicate": False,
        }

    def _learner_concepts_for_question(self, connection: sqlite3.Connection, question_uid: str) -> list[dict]:
        row = connection.execute(
            "SELECT subject, lesson, primary_topic FROM questions WHERE uid = ?",
            (str(question_uid),),
        ).fetchone()
        if not row:
            return []
        subject = str(row["subject"] or "Matéria não informada").strip() or "Matéria não informada"
        subject_norm = self._norm_coverage_text(subject) or "MATERIA NAO INFORMADA"
        concepts: list[dict] = []
        seen: set[str] = set()

        def add(kind: str, label: str, *, weight: float) -> None:
            clean = str(label or "").strip()
            if not clean:
                return
            norm = self._norm_coverage_text(clean)
            key = f"{kind}|{subject_norm}|{norm}" if kind != "materia" else f"materia|{subject_norm}"
            if key in seen:
                return
            seen.add(key)
            concepts.append({"key": key, "type": kind, "subject": subject, "label": clean, "weight": float(weight)})

        add("materia", subject, weight=1.0)
        lesson = str(row["lesson"] or "").strip()
        topic = str(row["primary_topic"] or "").strip()
        if lesson and lesson.upper() not in {"SEM AULA", "N/A"}:
            add("aula", lesson, weight=1.15)
        if topic and topic.upper() not in {"SEM ASSUNTO", "N/A"}:
            add("assunto", topic, weight=1.55)

        # Se a Curadoria 2.0 já construiu o grafo, reutilizamos os conceitos
        # pedagógicos. Banca/órgão não entram no KT porque são metadados, não
        # conhecimentos a dominar.
        try:
            graph_rows = connection.execute(
                """
                SELECT n.node_type, n.label
                FROM qf_question_concepts qc
                JOIN qf_knowledge_nodes n ON n.id = qc.node_id
                WHERE qc.question_uid = ?
                ORDER BY qc.weight DESC, n.node_type, n.label
                LIMIT 20
                """,
                (str(question_uid),),
            ).fetchall()
            weights = {"materia": 1.0, "aula": 1.15, "assunto": 1.55, "topico": 1.65, "referencia_legal": 1.2, "tag": 0.7}
            for grow in graph_rows:
                kind = str(grow["node_type"] or "").strip().lower()
                if kind in weights:
                    add(kind, str(grow["label"] or ""), weight=weights[kind])
        except sqlite3.Error:
            pass
        return concepts

    def _update_learner_model_event(
        self,
        connection: sqlite3.Connection,
        *,
        attempt_id: str,
        question_uid: str,
        correct: bool,
        answered_at: str | None = None,
    ) -> dict:
        event_id = str(attempt_id or "").strip()
        if not event_id:
            return {"ok": False, "reason": "sem_evento"}
        if connection.execute("SELECT 1 FROM learner_model_events WHERE attempt_id = ?", (event_id,)).fetchone():
            return {"ok": True, "duplicate": True}

        qrow = connection.execute(
            "SELECT COALESCE(NULLIF(TRIM(subject), ''), 'Matéria não informada') AS subject FROM questions WHERE uid = ?",
            (str(question_uid),),
        ).fetchone()
        if not qrow:
            return {"ok": False, "reason": "questao_ausente"}
        subject = str(qrow["subject"])
        when = str(answered_at or utc_now())
        concepts = self._learner_concepts_for_question(connection, str(question_uid))
        weighted_mastery = 0.0
        weighted_confidence = 0.0
        weight_total = 0.0
        concept_snapshots: list[dict] = []
        for concept in concepts:
            current = connection.execute(
                "SELECT * FROM concept_mastery WHERE concept_key = ?",
                (concept["key"],),
            ).fetchone()
            prior = float(current["mastery"] if current else 0.20)
            slip = float(current["slip"] if current else 0.10)
            guess = float(current["guess"] if current else 0.20)
            learn = float(current["learn_rate"] if current else 0.14)
            exposures = int(current["exposure_count"] if current else 0)
            correct_count = int(current["correct_count"] if current else 0) + (1 if correct else 0)
            wrong_count = int(current["wrong_count"] if current else 0) + (0 if correct else 1)
            update = update_bkt(prior, bool(correct), slip=slip, guess=guess, learn=learn)
            new_exposures = exposures + 1
            confidence = mastery_confidence(new_exposures)
            connection.execute(
                """
                INSERT INTO concept_mastery(
                    concept_key, concept_type, subject, label, mastery, confidence,
                    exposure_count, correct_count, wrong_count, slip, guess, learn_rate,
                    last_seen_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(concept_key) DO UPDATE SET
                    mastery=excluded.mastery, confidence=excluded.confidence,
                    exposure_count=excluded.exposure_count, correct_count=excluded.correct_count,
                    wrong_count=excluded.wrong_count, last_seen_at=excluded.last_seen_at,
                    updated_at=excluded.updated_at
                """,
                (
                    concept["key"], concept["type"], subject, concept["label"], update.mastery,
                    confidence, new_exposures, correct_count, wrong_count, update.slip,
                    update.guess, update.learn, when, when,
                ),
            )
            weight = float(concept["weight"])
            weighted_mastery += update.mastery * weight
            weighted_confidence += confidence * weight
            weight_total += weight
            concept_snapshots.append({"key": concept["key"], "mastery": update.mastery, "confidence": confidence})

        question_mastery = (weighted_mastery / weight_total) if weight_total else None
        question_confidence = (weighted_confidence / weight_total) if weight_total else 0.0

        ability = connection.execute("SELECT * FROM learner_ability WHERE subject = ?", (subject,)).fetchone()
        theta = float(ability["theta"] if ability else 0.0)
        ability_attempts = int(ability["attempt_count"] if ability else 0)
        ability_correct = int(ability["correct_count"] if ability else 0)
        ability_wrong = int(ability["wrong_count"] if ability else 0)
        item = connection.execute("SELECT * FROM question_irt WHERE question_uid = ?", (str(question_uid),)).fetchone()
        difficulty = float(item["difficulty"] if item else 0.0)
        discrimination = float(item["discrimination"] if item else 1.0)
        item_attempts = int(item["attempt_count"] if item else 0)
        item_correct = int(item["correct_count"] if item else 0)
        item_wrong = int(item["wrong_count"] if item else 0)
        irt = update_irt_online(
            theta, difficulty, discrimination, bool(correct),
            ability_attempts=ability_attempts, item_attempts=item_attempts,
        )
        connection.execute(
            """
            INSERT INTO learner_ability(subject, theta, standard_error, attempt_count, correct_count, wrong_count, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(subject) DO UPDATE SET theta=excluded.theta, standard_error=excluded.standard_error,
                attempt_count=excluded.attempt_count, correct_count=excluded.correct_count,
                wrong_count=excluded.wrong_count, updated_at=excluded.updated_at
            """,
            (subject, irt.theta, irt.standard_error, ability_attempts + 1,
             ability_correct + (1 if correct else 0), ability_wrong + (0 if correct else 1), when),
        )
        connection.execute(
            """
            INSERT INTO question_irt(question_uid, difficulty, discrimination, information, attempt_count, correct_count, wrong_count, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(question_uid) DO UPDATE SET difficulty=excluded.difficulty,
                discrimination=excluded.discrimination, information=excluded.information,
                attempt_count=excluded.attempt_count, correct_count=excluded.correct_count,
                wrong_count=excluded.wrong_count, updated_at=excluded.updated_at
            """,
            (str(question_uid), irt.difficulty, irt.discrimination, irt.information,
             item_attempts + 1, item_correct + (1 if correct else 0), item_wrong + (0 if correct else 1), when),
        )
        srow = connection.execute(
            "SELECT memory_retrievability, due_at FROM study_state WHERE question_uid = ?",
            (str(question_uid),),
        ).fetchone()
        retrieval = float(srow["memory_retrievability"] or 0.0) if srow else None
        due_dt = _parse_iso(srow["due_at"] if srow else None)
        overdue = bool(due_dt is not None and due_dt <= utc_now_dt())
        fusion = fusion_priority(
            mastery=question_mastery,
            mastery_confidence_value=question_confidence,
            retrievability=retrieval,
            irt_information=irt.information,
            overdue=overdue,
        )
        connection.execute(
            """
            UPDATE study_state SET kt_mastery = ?, kt_confidence = ?, irt_information = ?,
                learner_fusion_priority = ?, learner_model_version = ?
            WHERE question_uid = ?
            """,
            (question_mastery, question_confidence, irt.information, fusion, LEARNER_MODEL_VERSION, str(question_uid)),
        )
        connection.execute(
            """
            INSERT INTO learner_model_events(
                attempt_id, question_uid, subject, is_correct, mastery_after, theta_after,
                item_difficulty_after, item_information, model_version, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (event_id, str(question_uid), subject, 1 if correct else 0, question_mastery,
             irt.theta, irt.difficulty, irt.information, LEARNER_MODEL_VERSION, when),
        )
        return {
            "ok": True, "mastery": question_mastery, "confidence": question_confidence,
            "theta": irt.theta, "theta_scale": theta_percentile(irt.theta),
            "difficulty": irt.difficulty, "difficulty_label": item_difficulty_label(irt.difficulty),
            "discrimination": irt.discrimination, "information": irt.information,
            "fusion_priority": fusion, "concepts": concept_snapshots,
        }

    def ensure_learner_model_current(self) -> dict:
        """Mantém KT/IRT coerentes com o histórico bruto de tentativas.

        A primeira abertura após a migração 5.9 -> 6.0 reconstrói o modelo
        automaticamente. Depois disso, respostas novas são processadas
        incrementalmente. Se uma sincronização trouxer tentativas antigas fora
        de ordem (ou remover histórico), fazemos rebuild completo para preservar
        a ordem temporal do BKT/IRT. O FSRS não é alterado por esta rotina.
        """
        with self.database.connect() as connection:
            attempt_count = int(connection.execute("SELECT COUNT(*) FROM telegram_attempts").fetchone()[0] or 0)
            event_count = int(connection.execute("SELECT COUNT(*) FROM learner_model_events").fetchone()[0] or 0)
            prediction_count = int(connection.execute(
                "SELECT COUNT(*) FROM telegram_attempts WHERE learner_predicted_probability IS NOT NULL"
            ).fetchone()[0] or 0)
            if attempt_count == 0 and event_count == 0:
                return {"ok": True, "action": "none", "attempts": 0, "events": 0, "predictions": 0}

            missing_rows = connection.execute(
                """
                SELECT a.id, a.question_uid, a.is_correct, a.answered_at
                FROM telegram_attempts a
                LEFT JOIN learner_model_events e ON e.attempt_id = a.id
                WHERE e.attempt_id IS NULL
                ORDER BY a.answered_at ASC, a.id ASC
                """
            ).fetchall()
            extra_events = int(connection.execute(
                """
                SELECT COUNT(*) FROM learner_model_events e
                LEFT JOIN telegram_attempts a ON a.id=e.attempt_id
                WHERE a.id IS NULL
                """
            ).fetchone()[0] or 0)
            last_event = connection.execute("SELECT MAX(created_at) FROM learner_model_events").fetchone()[0]

        if prediction_count < attempt_count:
            rebuilt = self.rebuild_learner_model()
            return {
                "ok": True, "action": "rebuilt_predictions", "attempts": attempt_count,
                "events": int(rebuilt.get("events", 0)), "predictions": int(rebuilt.get("prediction_samples", 0)),
                "rebuilt_events": int(rebuilt.get("rebuilt_events", 0)),
            }

        if not missing_rows and not extra_events and attempt_count == event_count:
            return {"ok": True, "action": "none", "attempts": attempt_count, "events": event_count, "predictions": prediction_count}

        # Dados apagados ou tentativa faltante anterior ao último evento exigem
        # replay cronológico para não enviesar a atualização sequencial.
        earliest_missing = str(missing_rows[0]["answered_at"] or "") if missing_rows else ""
        if extra_events or event_count > attempt_count or (last_event and earliest_missing and earliest_missing <= str(last_event)):
            rebuilt = self.rebuild_learner_model()
            return {"ok": True, "action": "rebuilt", "attempts": attempt_count, "events": int(rebuilt.get("events", 0)), "rebuilt_events": int(rebuilt.get("rebuilt_events", 0))}

        # Somente eventos novos em ordem temporal: atualização incremental.
        with self.database.connect() as connection:
            processed = 0
            for row in missing_rows:
                result = self._update_learner_model_event(
                    connection, attempt_id=str(row["id"]), question_uid=str(row["question_uid"]),
                    correct=bool(row["is_correct"]), answered_at=str(row["answered_at"] or utc_now()),
                )
                if result.get("ok") and not result.get("duplicate"):
                    processed += 1
        return {"ok": True, "action": "incremental", "attempts": attempt_count, "events": event_count + processed, "processed": processed}

    def rebuild_learner_model(self) -> dict:
        """Reconstrói KT/IRT e previsões seletivas sem tocar no histórico FSRS."""
        with self.database.connect() as connection:
            connection.execute("DELETE FROM learner_model_events")
            connection.execute("DELETE FROM concept_mastery")
            connection.execute("DELETE FROM learner_ability")
            connection.execute("DELETE FROM question_irt")
            connection.execute(
                "UPDATE study_state SET kt_mastery=NULL, kt_confidence=0.0, irt_information=0.0, learner_fusion_priority=0.0, learner_model_version=NULL"
            )
            connection.execute(
                """UPDATE telegram_attempts SET learner_predicted_probability=NULL,
                       learner_prediction_confidence=NULL, learner_prediction_low=NULL,
                       learner_prediction_high=NULL, learner_prediction_status=NULL,
                       learner_prediction_reason=NULL, learner_prediction_version=NULL"""
            )
            rows = connection.execute(
                """
                SELECT id, question_uid, is_correct, answered_at, fsrs_predicted_probability
                FROM telegram_attempts
                ORDER BY answered_at ASC, id ASC
                """
            ).fetchall()
            history: dict[str, list[int]] = {}
            for row in rows:
                uid = str(row["question_uid"])
                correct_before, wrong_before = history.get(uid, [0, 0])
                concepts = self._learner_concepts_for_question(connection, uid)
                weighted_mastery = weighted_confidence = weight_total = 0.0
                for concept in concepts:
                    crow = connection.execute(
                        "SELECT mastery, confidence FROM concept_mastery WHERE concept_key=?", (concept["key"],)
                    ).fetchone()
                    if crow:
                        weight = float(concept.get("weight") or 1.0)
                        weighted_mastery += float(crow["mastery"] or 0.0) * weight
                        weighted_confidence += float(crow["confidence"] or 0.0) * weight
                        weight_total += weight
                mastery_before = weighted_mastery / weight_total if weight_total else None
                confidence_before = weighted_confidence / weight_total if weight_total else 0.0
                qrow = connection.execute(
                    "SELECT COALESCE(NULLIF(TRIM(subject),''),'Matéria não informada') AS subject FROM questions WHERE uid=?", (uid,)
                ).fetchone()
                subject = str(qrow["subject"] if qrow else "Matéria não informada")
                ability = connection.execute(
                    "SELECT theta,standard_error,attempt_count FROM learner_ability WHERE subject=?", (subject,)
                ).fetchone()
                item = connection.execute(
                    "SELECT difficulty,discrimination,attempt_count FROM question_irt WHERE question_uid=?", (uid,)
                ).fetchone()
                hist_n = correct_before + wrong_before
                prediction = predict_success_selective(
                    mastery=mastery_before,
                    mastery_confidence_value=confidence_before,
                    retrievability=None if row["fsrs_predicted_probability"] is None else float(row["fsrs_predicted_probability"]),
                    fsrs_reviews=hist_n,
                    theta=None if ability is None else float(ability["theta"] or 0.0),
                    difficulty=None if item is None else float(item["difficulty"] or 0.0),
                    discrimination=None if item is None else float(item["discrimination"] or 1.0),
                    ability_standard_error=None if ability is None else float(ability["standard_error"] or 2.5),
                    ability_attempts=0 if ability is None else int(ability["attempt_count"] or 0),
                    item_attempts=0 if item is None else int(item["attempt_count"] or 0),
                    historical_accuracy=(correct_before + 1.0) / (hist_n + 2.0),
                    history_attempts=hist_n,
                )
                connection.execute(
                    """UPDATE telegram_attempts SET learner_predicted_probability=?, learner_prediction_confidence=?,
                           learner_prediction_low=?, learner_prediction_high=?, learner_prediction_status=?,
                           learner_prediction_reason=?, learner_prediction_version=? WHERE id=?""",
                    (prediction.probability, prediction.confidence, prediction.interval_low, prediction.interval_high,
                     prediction.status, json.dumps(list(prediction.reasons), ensure_ascii=False), prediction.version, str(row["id"])),
                )
                self._update_learner_model_event(
                    connection, attempt_id=str(row["id"]), question_uid=uid,
                    correct=bool(row["is_correct"]), answered_at=str(row["answered_at"] or utc_now()),
                )
                if bool(row["is_correct"]):
                    correct_before += 1
                else:
                    wrong_before += 1
                history[uid] = [correct_before, wrong_before]
        dashboard = self.learner_model_dashboard()
        return {"ok": True, **dashboard, "rebuilt_events": len(rows), "prediction_samples": len(rows)}

    # ---------------------- Tutor 6.7: scaffolding progressivo -----------
    @staticmethod
    def _scaffold_dependency_from_level(level: int | None, *, revealed: bool = False) -> float:
        if level is None:
            return 0.0
        normalized = max(0.0, min(1.0, float(level) / 5.0))
        if revealed:
            normalized = max(normalized, 1.0)
        return round(normalized, 4)

    def start_scaffold_session(
        self, question_uid: str, *, representation: str = "texto", user_prompt: str = "", media_notes: str = "", online: bool = False, learner_snapshot: dict | None = None
    ) -> dict:
        uid = str(question_uid or "").strip()
        if not uid:
            raise ValueError("Questão não informada para o scaffolding.")
        rep = str(representation or "texto").strip().casefold()
        if rep not in {"texto", "flashcard", "passo_a_passo", "visual"}:
            rep = "texto"
        now = utc_now()
        session_id = str(uuid.uuid4())
        with self.database.connect() as connection:
            exists = connection.execute("SELECT 1 FROM questions WHERE uid=?", (uid,)).fetchone()
            if not exists:
                raise ValueError("Questão não encontrada.")
            connection.execute(
                """INSERT INTO tutor_scaffold_sessions(
                       id, question_uid, representation, user_prompt, media_notes, status, current_level, max_level_reached, online,
                       learner_snapshot_json, started_at, updated_at
                   ) VALUES (?, ?, ?, ?, ?, 'em_andamento', 0, 0, ?, ?, ?, ?)""",
                (session_id, uid, rep, str(user_prompt or "")[:3000], str(media_notes or "")[:6000], 1 if online else 0, json.dumps(learner_snapshot or {}, ensure_ascii=False, default=str), now, now),
            )
            connection.execute(
                "UPDATE study_state SET scaffold_session_count=COALESCE(scaffold_session_count,0)+1 WHERE question_uid=?",
                (uid,),
            )
        return self.scaffold_session(session_id)

    def record_scaffold_event(
        self, session_id: str, *, level: int, event_type: str, content_preview: str = "", metadata: dict | None = None
    ) -> dict:
        sid = str(session_id or "").strip()
        lvl = max(0, min(5, int(level)))
        kind = str(event_type or "hint_shown").strip().casefold()
        now = utc_now()
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT question_uid, representation, status, max_level_reached FROM tutor_scaffold_sessions WHERE id=?",
                (sid,),
            ).fetchone()
            if not row:
                raise ValueError("Sessão de scaffolding não encontrada.")
            uid = str(row["question_uid"])
            rep = str(row["representation"] or "texto")
            connection.execute(
                """INSERT INTO tutor_scaffold_events(
                       id, session_id, question_uid, level, event_type, representation, content_preview, metadata_json, created_at
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (str(uuid.uuid4()), sid, uid, lvl, kind, rep, str(content_preview or "")[:1200],
                 json.dumps(metadata or {}, ensure_ascii=False, default=str), now),
            )
            connection.execute(
                """UPDATE tutor_scaffold_sessions SET current_level=?, max_level_reached=MAX(max_level_reached, ?),
                       updated_at=? WHERE id=?""",
                (lvl, lvl, now, sid),
            )
            if kind in {"solved", "resolved"}:
                dependency = self._scaffold_dependency_from_level(lvl)
                connection.execute(
                    """UPDATE tutor_scaffold_sessions SET status='resolvido', solved_level=?, completed_at=?, updated_at=? WHERE id=?""",
                    (lvl, now, now, sid),
                )
                connection.execute(
                    """UPDATE study_state SET scaffold_dependency=?, scaffold_last_level=?,
                           scaffold_solved_count=COALESCE(scaffold_solved_count,0)+1 WHERE question_uid=?""",
                    (dependency, lvl, uid),
                )
            elif kind in {"revealed", "full_explanation"}:
                dependency = self._scaffold_dependency_from_level(5, revealed=True)
                connection.execute(
                    """UPDATE tutor_scaffold_sessions SET status='explicacao_revelada', current_level=5,
                           max_level_reached=MAX(max_level_reached,5), completed_at=?, updated_at=? WHERE id=?""",
                    (now, now, sid),
                )
                connection.execute(
                    "UPDATE study_state SET scaffold_dependency=?, scaffold_last_level=5 WHERE question_uid=?",
                    (dependency, uid),
                )
        return self.scaffold_session(sid)

    def scaffold_session(self, session_id: str) -> dict:
        sid = str(session_id or "").strip()
        with self.database.connect() as connection:
            row = connection.execute("SELECT * FROM tutor_scaffold_sessions WHERE id=?", (sid,)).fetchone()
            if not row:
                raise ValueError("Sessão de scaffolding não encontrada.")
            events = connection.execute(
                "SELECT id, level, event_type, representation, content_preview, metadata_json, created_at FROM tutor_scaffold_events WHERE session_id=? ORDER BY created_at, id",
                (sid,),
            ).fetchall()
        result = dict(row)
        for key in ("learner_snapshot_json",):
            try:
                result[key[:-5]] = json.loads(str(result.get(key) or "{}"))
            except Exception:
                result[key[:-5]] = {}
            result.pop(key, None)
        result["events"] = []
        for event in events:
            item = dict(event)
            try:
                item["metadata"] = json.loads(str(item.pop("metadata_json", "{}") or "{}"))
            except Exception:
                item["metadata"] = {}
            result["events"].append(item)
        result["independence_score"] = round(1.0 - self._scaffold_dependency_from_level(
            result.get("solved_level") if result.get("solved_level") is not None else result.get("max_level_reached"),
            revealed=str(result.get("status")) == "explicacao_revelada",
        ), 4)
        return result

    def scaffolding_signal(self, question_uid: str, *, recent_limit: int = 8) -> dict:
        uid = str(question_uid or "").strip()
        with self.database.connect() as connection:
            rows = connection.execute(
                """SELECT status, max_level_reached, solved_level, updated_at
                   FROM tutor_scaffold_sessions WHERE question_uid=?
                   ORDER BY updated_at DESC LIMIT ?""",
                (uid, max(1, min(30, int(recent_limit or 8)))),
            ).fetchall()
        if not rows:
            return {
                "sessions": 0, "resolved_sessions": 0, "average_support": 0.0, "independence_score": 1.0,
                "last_level": None, "signal": "sem_historico", "high_support": False,
            }
        weights=[]
        dependencies=[]
        resolved=0
        for idx,row in enumerate(rows):
            status=str(row["status"] or "")
            solved=row["solved_level"]
            level=int(solved if solved is not None else row["max_level_reached"] or 0)
            dep=self._scaffold_dependency_from_level(level, revealed=status=="explicacao_revelada")
            w=1.0/(1.0+idx*0.35)
            weights.append(w); dependencies.append(dep*w)
            if status=="resolvido": resolved+=1
        avg=sum(dependencies)/max(1e-9,sum(weights))
        independence=max(0.0,min(1.0,1.0-avg))
        last_level=int(rows[0]["solved_level"] if rows[0]["solved_level"] is not None else rows[0]["max_level_reached"] or 0)
        return {
            "sessions": len(rows), "resolved_sessions": resolved, "average_support": round(avg,4),
            "independence_score": round(independence,4), "last_level": last_level,
            "signal": "alta_dependencia" if avg>=0.68 else ("apoio_moderado" if avg>=0.34 else "boa_independencia"),
            "high_support": bool(avg>=0.68),
        }

    def scaffolding_dashboard(self) -> dict:
        with self.database.connect() as connection:
            rows=connection.execute(
                """SELECT question_uid, status, max_level_reached, solved_level, updated_at
                   FROM tutor_scaffold_sessions ORDER BY updated_at DESC"""
            ).fetchall()
        if not rows:
            return {"sessions":0,"resolved":0,"revealed":0,"avg_support":0.0,"independent_resolutions":0,"high_support_resolutions":0}
        deps=[]; resolved=0; revealed=0; independent=0; high=0
        for row in rows:
            status=str(row["status"] or "")
            level=int(row["solved_level"] if row["solved_level"] is not None else row["max_level_reached"] or 0)
            dep=self._scaffold_dependency_from_level(level, revealed=status=="explicacao_revelada")
            deps.append(dep)
            if status=="resolvido":
                resolved+=1
                if level<=1: independent+=1
                if level>=4: high+=1
            elif status=="explicacao_revelada": revealed+=1
        return {
            "sessions":len(rows), "resolved":resolved, "revealed":revealed,
            "avg_support":round(sum(deps)/len(deps),4), "independent_resolutions":independent,
            "high_support_resolutions":high,
        }

    def evidence_collection_plan(self, concept_key: str, *, candidate_limit: int = 10) -> dict:
        """Explica uma abstenção e monta uma coleta diagnóstica acionável.

        Abstenção não é erro nem domínio baixo: significa apenas que a amostra
        ainda não permite uma conclusão confiável. A leitura deste plano não
        altera o estado de estudo nem cria eventos de Cloud Sync.
        """
        key = str(concept_key or "").strip()
        if not key:
            raise ValueError("Conceito não informado para coleta de evidência.")
        with self.database.connect() as connection:
            row = connection.execute(
                """SELECT concept_key, concept_type, subject, label, mastery, confidence,
                          exposure_count, correct_count, wrong_count, last_seen_at
                   FROM concept_mastery WHERE concept_key=?""",
                (key,),
            ).fetchone()
            if not row:
                raise ValueError("Conceito não encontrado no Learner Model.")
            concept = dict(row)
            exposures = int(concept.get("exposure_count") or 0)
            confidence = float(concept.get("confidence") or 0.0)
            assessment = evidence_status(confidence=confidence, exposures=exposures)
            subject = str(concept.get("subject") or "").strip()
            qrows = connection.execute(
                """SELECT q.uid, q.source_code, q.subject, q.lesson, q.primary_topic, q.board,
                          COALESCE(s.correct_count,0) AS correct_count,
                          COALESCE(s.wrong_count,0) AS wrong_count, s.last_answered_at,
                          COALESCE(s.irt_information,0) AS irt_information,
                          COALESCE(s.learner_fusion_priority,0) AS learner_fusion_priority
                   FROM questions q JOIN study_state s ON s.question_uid=q.uid
                   WHERE q.subject=? AND COALESCE(s.suspended,0)=0
                     AND q.review_status IN ('aprovado','aprovada','aprovado_automaticamente','autoaprovado','autoaprovada')
                     AND COALESCE((SELECT qc.status FROM qf_question_currency qc WHERE qc.question_uid=q.uid), 'vigente')
                         NOT IN ('desatualizada','anulada','controversa')
                   ORDER BY COALESCE(s.irt_information,0) DESC,
                            COALESCE(s.learner_fusion_priority,0) DESC, q.source_code
                   LIMIT 500""",
                (subject,),
            ).fetchall()
            candidates: list[dict] = []
            now = datetime.now(timezone.utc)
            for qrow in qrows:
                uid = str(qrow["uid"])
                if key not in {str(item.get("key") or "") for item in self._learner_concepts_for_question(connection, uid)}:
                    continue
                attempts = int(qrow["correct_count"] or 0) + int(qrow["wrong_count"] or 0)
                info = max(0.0, float(qrow["irt_information"] or 0.0))
                priority = max(0.0, float(qrow["learner_fusion_priority"] or 0.0))
                last = _parse_iso(str(qrow["last_answered_at"] or ""))
                days = 999.0 if last is None else max(0.0, (now - last).total_seconds() / 86400.0)
                novelty = 1.0 if attempts == 0 else max(0.0, min(1.0, days / 30.0))
                score = 36.0 * min(1.0, info / 0.75) + 34.0 * min(1.0, priority / 100.0) + 30.0 * novelty
                candidates.append({
                    "uid": uid, "code": str(qrow["source_code"] or ""),
                    "subject": str(qrow["subject"] or ""), "lesson": str(qrow["lesson"] or ""),
                    "topic": str(qrow["primary_topic"] or ""), "board": str(qrow["board"] or ""),
                    "attempts": attempts, "irt_information": round(info, 4),
                    "priority": round(priority, 2), "diagnostic_score": round(score, 2),
                })
            candidates.sort(key=lambda item: (-float(item["diagnostic_score"]), int(item["attempts"]), item["code"]))

        missing_minimum = max(0, 3 - exposures)
        suggested_count = max(missing_minimum, 2 if confidence < 0.35 else 1) if assessment.get("abstain") else 0
        suggested_count = min(5, max(0, suggested_count))
        selected = candidates[:max(1, min(20, int(candidate_limit or 10)))]
        return {
            "concept_key": key, "concept_type": str(concept.get("concept_type") or ""),
            "subject": subject, "label": str(concept.get("label") or ""),
            "mastery": round(float(concept.get("mastery") or 0.0), 4),
            "confidence": round(confidence, 4), "exposures": exposures,
            "correct": int(concept.get("correct_count") or 0), "wrong": int(concept.get("wrong_count") or 0),
            "evidence": assessment, "is_problem": False,
            "explanation": "Não é um problema no programa. O modelo está se abstendo porque ainda há pouca evidência para afirmar seu domínio com segurança.",
            "minimum_evidence": 3, "missing_minimum": missing_minimum,
            "recommended_questions": suggested_count, "candidates": selected,
            "candidate_uids": [str(item["uid"]) for item in selected],
            "can_start": bool(selected and suggested_count > 0), "version": LEARNER_MODEL_VERSION,
        }

    @staticmethod
    def _scaffold_retention_bucket(hours: float) -> tuple[str, str]:
        h = max(0.0, float(hours))
        if h < 6.0: return "imediato", "Até 6 h"
        if h < 48.0: return "1d", "6–48 h"
        if h < 120.0: return "3d", "2–5 dias"
        if h < 336.0: return "7d", "5–14 dias"
        return "30d", "14+ dias"

    def scaffolding_benchmark(self) -> dict:
        """Benchmark observacional do scaffolding usando revisões posteriores reais."""
        with self.database.connect() as connection:
            sessions = connection.execute(
                """SELECT id, question_uid, representation, status, max_level_reached, solved_level,
                          started_at, completed_at, updated_at
                   FROM tutor_scaffold_sessions
                   WHERE status IN ('resolvido','explicacao_revelada')
                   ORDER BY COALESCE(completed_at,updated_at), id"""
            ).fetchall()
            observations: list[dict] = []
            for session in sessions:
                completed_text = str(session["completed_at"] or session["updated_at"] or "")
                completed = _parse_iso(completed_text)
                if completed is None: continue
                next_session = connection.execute(
                    "SELECT started_at FROM tutor_scaffold_sessions WHERE question_uid=? AND id<>? AND started_at>? ORDER BY started_at LIMIT 1",
                    (str(session["question_uid"]), str(session["id"]), completed_text),
                ).fetchone()
                cutoff = str(next_session["started_at"] or "") if next_session else ""
                if cutoff:
                    attempts = connection.execute(
                        "SELECT id,is_correct,answered_at,source FROM telegram_attempts WHERE question_uid=? AND answered_at>? AND answered_at<? ORDER BY answered_at",
                        (str(session["question_uid"]), completed_text, cutoff),
                    ).fetchall()
                else:
                    attempts = connection.execute(
                        "SELECT id,is_correct,answered_at,source FROM telegram_attempts WHERE question_uid=? AND answered_at>? ORDER BY answered_at",
                        (str(session["question_uid"]), completed_text),
                    ).fetchall()
                seen_buckets: set[str] = set()
                level = int(session["solved_level"] if session["solved_level"] is not None else session["max_level_reached"] or 0)
                revealed = str(session["status"] or "") == "explicacao_revelada"
                support_group = "apoio_alto" if revealed or level >= 4 else ("apoio_moderado" if level >= 2 else "independente")
                for attempt in attempts:
                    answered = _parse_iso(str(attempt["answered_at"] or ""))
                    if answered is None: continue
                    hours = max(0.0, (answered - completed).total_seconds() / 3600.0)
                    bucket, bucket_label = self._scaffold_retention_bucket(hours)
                    if bucket in seen_buckets: continue
                    seen_buckets.add(bucket)
                    observations.append({
                        "session_id": str(session["id"]), "question_uid": str(session["question_uid"]),
                        "representation": str(session["representation"] or "texto"), "level": level,
                        "support_group": support_group, "revealed": revealed, "bucket": bucket,
                        "bucket_label": bucket_label, "hours_after": round(hours,2),
                        "is_correct": bool(attempt["is_correct"]), "attempt_id": str(attempt["id"]),
                        "source": str(attempt["source"] or ""),
                    })

        def aggregate(items: list[dict], key_name: str) -> list[dict]:
            groups: dict[str, dict] = {}
            for item in items:
                key = str(item.get(key_name) or "não informado")
                row = groups.setdefault(key, {"key":key,"samples":0,"correct":0,"delayed_samples":0,"delayed_correct":0})
                row["samples"] += 1; row["correct"] += 1 if item.get("is_correct") else 0
                if str(item.get("bucket")) != "imediato":
                    row["delayed_samples"] += 1; row["delayed_correct"] += 1 if item.get("is_correct") else 0
            output=[]
            for row in groups.values():
                n=int(row["samples"]); d=int(row["delayed_samples"])
                row["accuracy"] = round(int(row["correct"])/max(1,n),4)
                row["delayed_accuracy"] = None if not d else round(int(row["delayed_correct"])/d,4)
                output.append(row)
            output.sort(key=lambda item:(-int(item["delayed_samples"]),-int(item["samples"]),str(item["key"])))
            return output

        by_support=aggregate(observations,"support_group")
        by_representation=aggregate(observations,"representation")
        by_delay=aggregate(observations,"bucket")
        delayed=[item for item in observations if str(item.get("bucket"))!="imediato"]
        delayed_accuracy=None if not delayed else round(sum(1 for item in delayed if item.get("is_correct"))/len(delayed),4)
        recommendations=[]
        if len(delayed)<8:
            recommendations.append("Ainda há poucas revisões posteriores para comparar estratégias com estabilidade. Continue usando o Tutor e revisando normalmente.")
        else:
            qualified=[item for item in by_support if int(item.get("delayed_samples") or 0)>=3]
            if qualified:
                best=max(qualified,key=lambda item:float(item.get("delayed_accuracy") or 0.0))
                labels={"independente":"pouco apoio (níveis 0–1)","apoio_moderado":"apoio moderado (níveis 2–3)","apoio_alto":"apoio alto (níveis 4–5)"}
                recommendations.append(f"Até agora, {labels.get(str(best['key']),str(best['key']))} apresenta a maior taxa observada de acerto posterior ({float(best.get('delayed_accuracy') or 0)*100:.0f}%).")
        return {
            "sessions":len(sessions),"observations":len(observations),"delayed_observations":len(delayed),
            "delayed_accuracy":delayed_accuracy,"by_support":by_support,"by_representation":by_representation,
            "by_delay":by_delay,"recommendations":recommendations,"minimum_samples_for_comparison":8,
            "method":"observational post-scaffolding retention benchmark",
            "caveat":"Associação observacional, não prova causal. O nível de ajuda também depende da dificuldade inicial de cada questão.",
            "version":"qf-scaffold-benchmark-1",
        }

    def question_learning_state(self, question_uid: str) -> dict:
        uid = str(question_uid)
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT q.subject, q.primary_topic, s.kt_mastery, s.kt_confidence,
                       s.memory_retrievability, s.irt_information, s.learner_fusion_priority,
                       i.difficulty, i.discrimination, i.attempt_count AS irt_attempts,
                       a.theta, a.standard_error, a.attempt_count AS ability_attempts
                FROM questions q
                JOIN study_state s ON s.question_uid=q.uid
                LEFT JOIN question_irt i ON i.question_uid=q.uid
                LEFT JOIN learner_ability a ON a.subject=q.subject
                WHERE q.uid=?
                """, (uid,),
            ).fetchone()
            if not row:
                raise ValueError("Questão não encontrada.")
            concepts = self._learner_concepts_for_question(connection, uid)
            concept_rows = []
            for concept in concepts:
                crow = connection.execute(
                    "SELECT mastery, confidence, exposure_count FROM concept_mastery WHERE concept_key=?",
                    (concept["key"],),
                ).fetchone()
                if crow:
                    c_conf = float(crow["confidence"] or 0.0)
                    c_exp = int(crow["exposure_count"] or 0)
                    concept_rows.append({
                        "type": concept["type"], "label": concept["label"],
                        "mastery": float(crow["mastery"] or 0.0),
                        "confidence": c_conf,
                        "exposures": c_exp,
                        "evidence": evidence_status(confidence=c_conf, exposures=c_exp),
                    })
        mastery = None if row["kt_mastery"] is None else float(row["kt_mastery"])
        confidence = float(row["kt_confidence"] or 0.0)
        difficulty = None if row["difficulty"] is None else float(row["difficulty"])
        max_exposures = max([int(item.get("exposures") or 0) for item in concept_rows] or [0])
        assessment = evidence_status(
            confidence=confidence, exposures=max_exposures,
            standard_error=None if row["standard_error"] is None else float(row["standard_error"]),
        )
        scaffolding = self.scaffolding_signal(uid)
        support = float(scaffolding.get("average_support") or 0.0)
        support_adjusted_confidence = max(0.0, min(1.0, confidence * (1.0 - 0.22 * support)))
        support_adjusted_mastery = None if mastery is None else max(0.0, min(1.0, mastery * (1.0 - 0.10 * support)))
        support_adjusted_priority = max(0.0, min(100.0, float(row["learner_fusion_priority"] or 0.0) + 16.0 * support))
        return {
            "version": LEARNER_MODEL_VERSION,
            "mastery": mastery,
            "mastery_confidence": confidence,
            "mastery_label": "Evidência insuficiente" if assessment["abstain"] else mastery_label(mastery or 0.0, confidence),
            "evidence": assessment,
            "retrievability": None if row["memory_retrievability"] is None else float(row["memory_retrievability"]),
            "theta": None if row["theta"] is None else float(row["theta"]),
            "theta_scale": None if row["theta"] is None else theta_percentile(float(row["theta"])),
            "ability_standard_error": None if row["standard_error"] is None else float(row["standard_error"]),
            "ability_attempts": int(row["ability_attempts"] or 0),
            "item_difficulty": difficulty,
            "item_difficulty_label": "Sem dados" if difficulty is None else item_difficulty_label(difficulty),
            "item_discrimination": None if row["discrimination"] is None else float(row["discrimination"]),
            "item_information": float(row["irt_information"] or 0.0),
            "irt_attempts": int(row["irt_attempts"] or 0),
            "fusion_priority": float(row["learner_fusion_priority"] or 0.0),
            "support_adjusted_priority": support_adjusted_priority,
            "support_adjusted_mastery": support_adjusted_mastery,
            "support_adjusted_confidence": support_adjusted_confidence,
            "scaffolding": scaffolding,
            "concepts": concept_rows,
        }

    def learner_model_dashboard(self) -> dict:
        with self.database.connect() as connection:
            concepts = connection.execute(
                """
                SELECT concept_key, concept_type, subject, label, mastery, confidence,
                       exposure_count, correct_count, wrong_count, last_seen_at
                FROM concept_mastery ORDER BY mastery ASC, confidence DESC
                """
            ).fetchall()
            abilities = connection.execute(
                "SELECT subject, theta, standard_error, attempt_count, correct_count, wrong_count, updated_at FROM learner_ability ORDER BY theta ASC"
            ).fetchall()
            informative = connection.execute(
                """
                SELECT i.question_uid, i.difficulty, i.discrimination, i.information, i.attempt_count,
                       q.source_code, q.subject, q.primary_topic, s.kt_mastery, s.kt_confidence,
                       s.memory_retrievability, s.learner_fusion_priority
                FROM question_irt i
                JOIN questions q ON q.uid = i.question_uid
                JOIN study_state s ON s.question_uid = i.question_uid
                ORDER BY i.information DESC, s.learner_fusion_priority DESC
                LIMIT 15
                """
            ).fetchall()
            state = connection.execute(
                """
                SELECT COUNT(*) AS total,
                       AVG(kt_mastery) AS avg_mastery,
                       AVG(kt_confidence) AS avg_confidence,
                       AVG(irt_information) AS avg_information,
                       AVG(learner_fusion_priority) AS avg_fusion,
                       SUM(CASE WHEN learner_model_version IS NOT NULL THEN 1 ELSE 0 END) AS modeled
                FROM study_state
                """
            ).fetchone()
            event_count = int(connection.execute("SELECT COUNT(*) FROM learner_model_events").fetchone()[0] or 0)

        concept_items: list[dict] = []
        for row in concepts:
            item = dict(row)
            item["evidence"] = evidence_status(
                confidence=float(item.get("confidence") or 0.0),
                exposures=int(item.get("exposure_count") or 0),
            )
            item["mastery_label"] = (
                "Evidência insuficiente" if item["evidence"]["abstain"]
                else mastery_label(float(item.get("mastery") or 0.0), float(item.get("confidence") or 0.0))
            )
            concept_items.append(item)
        reliable = [item for item in concept_items if not bool(item["evidence"].get("abstain"))]
        uncertain = [item for item in concept_items if bool(item["evidence"].get("abstain"))]
        cautious = [item for item in reliable if item["evidence"].get("status") == "estimativa_cautelosa"]
        strong = sum(1 for item in reliable if float(item.get("mastery") or 0) >= 0.85)
        gaps = sum(1 for item in reliable if float(item.get("mastery") or 0) < 0.50)
        weakest = sorted(reliable, key=lambda item: (float(item.get("mastery") or 0), -float(item.get("confidence") or 0)))[:12]
        uncertain_preview = sorted(
            uncertain,
            key=lambda item: (-int(item.get("exposure_count") or 0), float(item.get("confidence") or 0)),
        )[:12]
        ability_items = []
        for row in abilities:
            item = dict(row)
            item["theta_scale"] = round(theta_percentile(float(item.get("theta") or 0)), 1)
            item["accuracy"] = round((int(item.get("correct_count") or 0) / max(1, int(item.get("attempt_count") or 0))) * 100.0, 1)
            item["evidence"] = evidence_status(
                confidence=max(0.0, min(1.0, 1.0 - max(0.0, float(item.get("standard_error") or 2.5) - 0.25) / 2.75)),
                exposures=int(item.get("attempt_count") or 0),
                standard_error=float(item.get("standard_error") or 2.5),
            )
            ability_items.append(item)
        info_items = []
        for row in informative:
            item = dict(row)
            item["difficulty_label"] = item_difficulty_label(float(item.get("difficulty") or 0))
            info_items.append(item)
        calibration = self.calibration_report(source="learner")
        counterfactual = self.counterfactual_learning_plan(target_mastery=0.80, limit=6)
        scaffolding = self.scaffolding_dashboard()
        scaffolding_benchmark = self.scaffolding_benchmark()
        return {
            "version": LEARNER_MODEL_VERSION,
            "method": "FSRS + Bayesian Knowledge Tracing + IRT 2PL pessoal + predição seletiva calibrável",
            "events": event_count,
            "concepts": len(concept_items),
            "reliable_concepts": len(reliable),
            "cautious_concepts": len(cautious),
            "abstained_concepts": len(uncertain),
            "strong_concepts": strong,
            "gap_concepts": gaps,
            "modeled_questions": int(state["modeled"] or 0) if state else 0,
            "avg_mastery": float(state["avg_mastery"] or 0.0) if state else 0.0,
            "avg_confidence": float(state["avg_confidence"] or 0.0) if state else 0.0,
            "avg_information": float(state["avg_information"] or 0.0) if state else 0.0,
            "avg_fusion_priority": float(state["avg_fusion"] or 0.0) if state else 0.0,
            "weakest_concepts": weakest,
            "uncertain_concepts": uncertain_preview,
            "abilities": ability_items,
            "informative_questions": info_items,
            "scaffolding": scaffolding,
            "scaffolding_benchmark": scaffolding_benchmark,
            "calibration": calibration,
            "counterfactual_plan": counterfactual,
            "decision_rule": "Quando a evidência é insuficiente, o QuestFlow se abstém de classificar domínio e prioriza questões diagnósticas.",
            "caveat": "A IRT é pessoal e regularizada; a abstenção evita falsa precisão. Recomendações contrafactuais são estimativas de planejamento, não garantias causais.",
        }

    def counterfactual_learning_plan(self, *, target_mastery: float = 0.80, limit: int = 6) -> dict:
        target = max(0.55, min(0.95, float(target_mastery)))
        amount = max(1, min(12, int(limit)))
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT concept_key, concept_type, subject, label, mastery, confidence,
                       exposure_count, slip, guess, learn_rate, last_seen_at
                FROM concept_mastery
                ORDER BY confidence ASC, mastery ASC, exposure_count ASC
                """
            ).fetchall()
            candidates: list[dict] = []
            for row in rows:
                item = dict(row)
                plan = counterfactual_practice_plan(
                    mastery=float(item.get("mastery") or 0.20),
                    confidence=float(item.get("confidence") or 0.0),
                    exposures=int(item.get("exposure_count") or 0),
                    target_mastery=target,
                    slip=float(item.get("slip") or 0.10),
                    guess=float(item.get("guess") or 0.20),
                    learn=float(item.get("learn_rate") or 0.14),
                )
                if plan["action"] == "manter":
                    continue
                priority = (
                    (1.0 - float(item.get("mastery") or 0.20)) * (0.45 + 0.55 * float(item.get("confidence") or 0.0))
                    + (1.0 - float(item.get("confidence") or 0.0)) * 0.55
                )
                candidates.append({**item, "plan": plan, "priority": priority})
            candidates.sort(key=lambda item: (-float(item["priority"]), float(item.get("mastery") or 0.0)))
            output: list[dict] = []
            for item in candidates[:amount]:
                label = str(item.get("label") or "")
                subject = str(item.get("subject") or "")
                if str(item.get("concept_type") or "") == "materia":
                    qrows = connection.execute(
                        """SELECT q.uid, q.source_code, q.subject, q.lesson, q.primary_topic,
                                  COALESCE(s.learner_fusion_priority,0) AS priority
                           FROM questions q JOIN study_state s ON s.question_uid=q.uid
                           WHERE q.subject=? AND COALESCE(s.suspended,0)=0
                           ORDER BY priority DESC, q.source_code LIMIT 4""",
                        (subject,),
                    ).fetchall()
                else:
                    qrows = connection.execute(
                        """SELECT DISTINCT q.uid, q.source_code, q.subject, q.lesson, q.primary_topic,
                                  COALESCE(s.learner_fusion_priority,0) AS priority
                           FROM questions q
                           JOIN study_state s ON s.question_uid=q.uid
                           LEFT JOIN qf_question_concepts qc ON qc.question_uid=q.uid
                           LEFT JOIN qf_knowledge_nodes n ON n.id=qc.node_id
                           WHERE q.subject=? AND COALESCE(s.suspended,0)=0 AND (
                               UPPER(COALESCE(q.primary_topic,''))=UPPER(?) OR
                               UPPER(COALESCE(q.lesson,''))=UPPER(?) OR
                               UPPER(COALESCE(n.label,''))=UPPER(?)
                           )
                           ORDER BY priority DESC, q.source_code LIMIT 4""",
                        (subject, label, label, label),
                    ).fetchall()
                output.append({
                    "concept_key": str(item.get("concept_key") or ""),
                    "concept_type": str(item.get("concept_type") or ""),
                    "subject": subject,
                    "label": label,
                    "mastery": round(float(item.get("mastery") or 0.0), 4),
                    "confidence": round(float(item.get("confidence") or 0.0), 4),
                    "exposures": int(item.get("exposure_count") or 0),
                    "plan": item["plan"],
                    "suggested_questions": [dict(row) for row in qrows],
                })
        return {
            "target_mastery": round(target, 4),
            "items": output,
            "count": len(output),
            "method": "BKT counterfactual simulation + evidence-first diagnostics",
            "caveat": "O plano estima a menor prática útil sob o modelo atual; ele deve ser recalculado após novas respostas.",
            "version": LEARNER_MODEL_VERSION,
        }

    def calibration_report(self, *, bin_count: int = 10, source: str = "adaptive") -> dict:
        """Mede se probabilidades pré-resposta correspondem à frequência real.

        Para o Learner Model 6.6, a calibração é reportada em dois recortes:
        *overall* (todas as previsões) e *selective* (somente previsões nas quais
        o modelo decidiu não se abster). Isso torna visível o trade-off entre
        cobertura e confiabilidade.
        """
        source_key = str(source or "adaptive").lower()
        if source_key == "learner":
            with self.database.connect() as connection:
                rows = connection.execute(
                    """SELECT learner_predicted_probability AS probability, is_correct,
                              learner_prediction_confidence AS confidence,
                              learner_prediction_status AS status
                       FROM telegram_attempts
                       WHERE learner_predicted_probability IS NOT NULL
                       ORDER BY answered_at"""
                ).fetchall()
            predictions = [float(row["probability"]) for row in rows]
            outcomes = [bool(row["is_correct"]) for row in rows]
            overall = build_calibration_report(predictions, outcomes, bin_count=bin_count).to_dict()
            accepted = [row for row in rows if str(row["status"] or "") != "evidencia_insuficiente"]
            selective = build_calibration_report(
                [float(row["probability"]) for row in accepted],
                [bool(row["is_correct"]) for row in accepted],
                bin_count=bin_count,
            ).to_dict()
            total = len(rows)
            accepted_n = len(accepted)
            mean_conf = (
                sum(float(row["confidence"] or 0.0) for row in rows) / total if total else 0.0
            )
            if accepted_n < 20:
                quality = "evidencia_insuficiente"
                label = "Ainda sem amostra suficiente para avaliar calibração"
            elif float(selective.get("expected_calibration_error") or 0.0) <= 0.06:
                quality = "boa"
                label = "Calibração seletiva boa"
            elif float(selective.get("expected_calibration_error") or 0.0) <= 0.12:
                quality = "moderada"
                label = "Calibração seletiva moderada"
            else:
                quality = "recalibrar"
                label = "Calibração precisa de atenção"
            return {
                "source": "learner",
                "samples": total,
                "accepted_samples": accepted_n,
                "abstained_samples": total - accepted_n,
                "coverage": round(accepted_n / total, 4) if total else 0.0,
                "abstention_rate": round((total - accepted_n) / total, 4) if total else 0.0,
                "mean_prediction_confidence": round(mean_conf, 4),
                "overall": overall,
                "selective": selective,
                "quality": quality,
                "quality_label": label,
                "lower_brier_is_better": True,
                "lower_ece_is_better": True,
                "caveat": "Amostras abstidas continuam auditadas, mas não são tratadas como conclusões confiáveis do modelo.",
            }

        column = "fsrs_predicted_probability" if source_key == "fsrs" else "predicted_probability"
        with self.database.connect() as connection:
            rows = connection.execute(
                f"SELECT {column} AS probability, is_correct FROM telegram_attempts WHERE {column} IS NOT NULL ORDER BY answered_at"
            ).fetchall()
        report = build_calibration_report(
            [float(row["probability"]) for row in rows],
            [bool(row["is_correct"]) for row in rows],
            bin_count=bin_count,
        )
        payload = report.to_dict()
        payload["source"] = "fsrs" if column.startswith("fsrs_") else "adaptive"
        return payload

    def calibration_comparison(self) -> dict:
        adaptive = self.calibration_report(source="adaptive")
        fsrs = self.calibration_report(source="fsrs")
        learner = self.calibration_report(source="learner")

        def _metric(payload: dict, key: str) -> float | None:
            try:
                value = payload.get(key)
                return None if value is None else float(value)
            except (TypeError, ValueError):
                return None

        candidates: list[tuple[str, float]] = []
        for name, payload in (("adaptativo", adaptive), ("fsrs", fsrs)):
            if int(payload.get("samples", 0) or 0) >= 10:
                value = _metric(payload, "brier")
                if value is not None:
                    candidates.append((name, value))
        learner_sel = learner.get("selective", {}) if isinstance(learner, dict) else {}
        if int(learner.get("accepted_samples", 0) or 0) >= 10:
            value = _metric(learner_sel, "brier")
            if value is not None:
                candidates.append(("learner_seletivo", value))
        winner = min(candidates, key=lambda item: item[1])[0] if candidates else "insuficiente"
        return {
            "adaptive": adaptive,
            "fsrs": fsrs,
            "learner": learner,
            "lower_brier_is_better": True,
            "best_calibrated": winner,
            "note": "O Learner Model é comparado apenas nas previsões em que decidiu não se abster.",
        }

    def adaptive_dashboard(self) -> dict:
        """Resumo adaptativo, carga diária, calibração e estado do FSRS."""
        now = utc_now()
        with self.database.connect() as connection:
            totals = connection.execute(
                """
                SELECT COUNT(*) AS total,
                       SUM(CASE WHEN sent_count = 0 THEN 1 ELSE 0 END) AS new_count,
                       SUM(CASE WHEN sent_count > 0 AND (due_at IS NULL OR due_at <= ?) THEN 1 ELSE 0 END) AS due_count,
                       SUM(CASE WHEN fsrs_state = 'relearning' AND due_at <= ? THEN 1 ELSE 0 END) AS relearning_due,
                       SUM(CASE WHEN suspended = 1 THEN 1 ELSE 0 END) AS suspended_count,
                       AVG(memory_stability) AS avg_stability, AVG(memory_difficulty) AS avg_difficulty,
                       AVG(adaptive_prediction) AS avg_prediction, MAX(streak) AS best_streak,
                       SUM(correct_count) AS correct_count, SUM(wrong_count) AS wrong_count
                FROM study_state
                """,
                (now, now),
            ).fetchone()
            subjects = connection.execute(
                """
                SELECT q.subject, COUNT(*) AS question_count, AVG(s.adaptive_prediction) AS avg_prediction,
                       AVG(s.adaptive_priority) AS avg_priority,
                       SUM(CASE WHEN s.sent_count > 0 AND (s.due_at IS NULL OR s.due_at <= ?) THEN 1 ELSE 0 END) AS due_count
                FROM study_state s JOIN questions q ON q.uid = s.question_uid
                WHERE COALESCE(s.suspended, 0) = 0
                GROUP BY q.subject ORDER BY avg_priority DESC, due_count DESC LIMIT 8
                """,
                (now,),
            ).fetchall()
            topic_totals = connection.execute(
                "SELECT COUNT(*) AS topics, SUM(exposure_count) AS exposures FROM topic_learning_state"
            ).fetchone()
            response = connection.execute(
                "SELECT AVG(CASE WHEN timing_quality IN ('valid','active_filtered') THEN NULLIF(response_seconds, 0) END) AS avg_response FROM telegram_attempts"
            ).fetchone()
            studied_groups = int(connection.execute("SELECT COUNT(DISTINCT subject_norm || '|' || lesson_norm) FROM studied_scope").fetchone()[0] or 0)

        model = self.adaptive_model_summary()
        profile = self.learner_profile()
        calibration = self.calibration_report()
        calibration_comparison = self.calibration_comparison()
        optimizer = self.fsrs_optimizer_status()
        preferences = self.learning_preferences()
        attempts = int((totals["correct_count"] or 0) + (totals["wrong_count"] or 0)) if totals else 0
        correct = int(totals["correct_count"] or 0) if totals else 0
        due_count = int(totals["due_count"] or 0) if totals else 0
        new_count = int(totals["new_count"] or 0) if totals else 0
        avg_response = float(response["avg_response"] or 60.0) if response else 60.0
        avg_response = max(20.0, min(300.0, avg_response))
        daily_capacity = max(1, int((int(preferences["daily_minutes"]) * 60) // avg_response))
        exam_date = str(preferences.get("exam_date") or "")
        days_to_exam = None
        if exam_date:
            try:
                exam_day = datetime.fromisoformat(exam_date).date()
                days_to_exam = max(0, (exam_day - utc_now_dt().date()).days)
            except ValueError:
                days_to_exam = None
        if days_to_exam is not None and days_to_exam > 0:
            horizon = max(1, min(days_to_exam, 30))
            needed = math.ceil((due_count + new_count) / horizon)
            recommended_daily = max(due_count if due_count <= daily_capacity else min(due_count, daily_capacity), needed)
        else:
            recommended_daily = math.ceil(due_count / 3) + min(5, new_count)
        recommended_daily = max(1, min(daily_capacity, recommended_daily)) if (due_count + new_count) else 0

        return {
            "total": int(totals["total"] or 0) if totals else 0,
            "new_count": new_count, "due_count": due_count,
            "relearning_due": int(totals["relearning_due"] or 0) if totals else 0,
            "suspended_count": int(totals["suspended_count"] or 0) if totals else 0,
            "avg_stability": float(totals["avg_stability"] or 0.0) if totals else 0.0,
            "avg_difficulty": float(totals["avg_difficulty"] or 0.0) if totals else 0.0,
            "avg_prediction": float(totals["avg_prediction"] or 0.0) if totals else 0.0,
            "best_streak": int(totals["best_streak"] or 0) if totals else 0,
            "attempts": attempts, "accuracy": (correct / attempts) if attempts else 0.0,
            "model": model, "profile": profile, "calibration": calibration,
            "calibration_comparison": calibration_comparison,
            "fsrs_available": fsrs_available(), "fsrs_optimizer": optimizer,
            "effective_target_retention": optimizer.get("effective_retention"),
            "preferences": preferences, "days_to_exam": days_to_exam,
            "daily_capacity": daily_capacity, "recommended_daily_questions": recommended_daily,
            "avg_response_seconds": round(avg_response, 1), "studied_groups": studied_groups,
            "topic_bandit_version": BANDIT_VERSION, "game_engine_version": GAME_ENGINE_VERSION,
            "topic_count": int(topic_totals["topics"] or 0) if topic_totals else 0,
            "topic_exposures": int(topic_totals["exposures"] or 0) if topic_totals else 0,
            "subjects": [dict(row) for row in subjects],
        }

    def recommended_cycle_size(self, configured_limit: int) -> int:
        """Dimensiona o ciclo sem exceder a capacidade diária estimada."""
        base = max(1, int(configured_limit))
        dashboard = self.adaptive_dashboard()
        recommended = int(dashboard.get("recommended_daily_questions", 0) or 0)
        if recommended <= 0:
            return base
        # O ciclo individual não deve explodir só porque há backlog; ele pode subir
        # até 50% do configurado e no máximo 40 questões.
        return max(1, min(40, max(base, min(recommended, int(math.ceil(base * 1.5))))))

    def enqueue_callback_update(self, update_id: int, callback: dict) -> str:
        """Persiste o clique antes de processá-lo, evitando perda em reinícios/falhas."""
        now = utc_now()
        callback_id = str(callback.get("id", "") or "")
        callback_data = str(callback.get("data", "") or "")
        with self.database.connect() as connection:
            existing = connection.execute(
                "SELECT id FROM telegram_callback_inbox WHERE update_id = ?",
                (int(update_id),),
            ).fetchone()
            if existing:
                return str(existing["id"])
            item_id = str(uuid.uuid4())
            connection.execute(
                """
                INSERT INTO telegram_callback_inbox(
                    id, update_id, callback_id, callback_data, payload_json,
                    status, received_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, 'pendente', ?, ?)
                """,
                (
                    item_id, int(update_id), callback_id, callback_data,
                    json.dumps(callback, ensure_ascii=False), now, now,
                ),
            )
        return item_id

    def pending_callback_updates(self, limit: int = 100, *, due_only: bool = True) -> list[dict]:
        where = "status IN ('pendente', 'erro')"
        values: list = []
        if due_only:
            where += " AND (next_retry_at IS NULL OR next_retry_at <= ?)"
            values.append(utc_now())
        values.append(max(1, min(int(limit), 1000)))
        with self.database.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT * FROM telegram_callback_inbox
                WHERE {where}
                ORDER BY received_at ASC
                LIMIT ?
                """,
                values,
            ).fetchall()
        result: list[dict] = []
        for row in rows:
            item = dict(row)
            try:
                item["payload"] = json.loads(item.get("payload_json") or "{}")
            except json.JSONDecodeError:
                item["payload"] = {}
            result.append(item)
        return result

    def mark_callback_processed(self, item_id: str) -> None:
        now = utc_now()
        with self.database.connect() as connection:
            connection.execute(
                """
                UPDATE telegram_callback_inbox
                SET status = 'processado', processed_at = ?, updated_at = ?, next_retry_at = NULL
                WHERE id = ?
                """,
                (now, now, str(item_id)),
            )

    def mark_callback_error(self, item_id: str, error: str, *, retry_minutes: int = 5) -> None:
        now_dt = utc_now_dt()
        retry_at = (now_dt + timedelta(minutes=max(1, int(retry_minutes)))).isoformat()
        with self.database.connect() as connection:
            connection.execute(
                """
                UPDATE telegram_callback_inbox
                SET status = 'erro', attempt_count = attempt_count + 1, last_error = ?,
                    next_retry_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (str(error)[:2000], retry_at, now_dt.isoformat(), str(item_id)),
            )

    def enqueue_outbox_message(self, chat_id: str, text: str, *, kind: str = "mensagem") -> str:
        now = utc_now()
        item_id = str(uuid.uuid4())
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO telegram_outbox(
                    id, kind, chat_id, text, status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, 'pendente', ?, ?)
                """,
                (item_id, str(kind), str(chat_id), str(text)[:4000], now, now),
            )
        return item_id

    def pending_outbox_messages(self, limit: int = 100, *, due_only: bool = True) -> list[dict]:
        where = "status IN ('pendente', 'erro')"
        values: list = []
        if due_only:
            where += " AND (next_retry_at IS NULL OR next_retry_at <= ?)"
            values.append(utc_now())
        values.append(max(1, min(int(limit), 1000)))
        with self.database.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT * FROM telegram_outbox
                WHERE {where}
                ORDER BY created_at ASC
                LIMIT ?
                """,
                values,
            ).fetchall()
        return [dict(row) for row in rows]

    def mark_outbox_sent(self, item_id: str) -> None:
        now = utc_now()
        with self.database.connect() as connection:
            connection.execute(
                """
                UPDATE telegram_outbox
                SET status = 'enviado', sent_at = ?, updated_at = ?, next_retry_at = NULL
                WHERE id = ?
                """,
                (now, now, str(item_id)),
            )

    def mark_outbox_error(self, item_id: str, error: str, *, retry_minutes: int = 5) -> None:
        now_dt = utc_now_dt()
        retry_at = (now_dt + timedelta(minutes=max(1, int(retry_minutes)))).isoformat()
        with self.database.connect() as connection:
            connection.execute(
                """
                UPDATE telegram_outbox
                SET status = 'erro', attempt_count = attempt_count + 1, last_error = ?,
                    next_retry_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (str(error)[:2000], retry_at, now_dt.isoformat(), str(item_id)),
            )

    def create_review_request(
        self,
        question_uid: str,
        *,
        chat_id: str = "",
        user_id: str = "",
        username: str = "",
        message_id: int | None = None,
        source: str = "botao_telegram",
        note: str = "",
    ) -> dict:
        """Cria ou reativa uma solicitação de correção sem duplicar cliques repetidos."""
        uid = str(question_uid).strip()
        if not uid:
            raise ValueError("Questão não informada para correção.")
        now = utc_now()
        with self.database.connect() as connection:
            question = connection.execute(
                "SELECT uid FROM questions WHERE uid = ?", (uid,)
            ).fetchone()
            if not question:
                raise ValueError("A questão indicada pelo Telegram não existe mais na base.")
            existing = connection.execute(
                """
                SELECT id FROM telegram_review_requests
                WHERE question_uid = ? AND COALESCE(user_id, '') = ?
                  AND status IN ('pendente', 'aberta')
                ORDER BY requested_at DESC LIMIT 1
                """,
                (uid, str(user_id)),
            ).fetchone()
            if existing:
                request_id = str(existing["id"])
                connection.execute(
                    """
                    UPDATE telegram_review_requests
                    SET chat_id = ?, username = ?, message_id = ?, source = ?, note = ?,
                        status = 'pendente', requested_at = ?, updated_at = ?, resolved_at = NULL
                    WHERE id = ?
                    """,
                    (
                        str(chat_id), str(username), message_id, str(source), str(note)[:2000],
                        now, now, request_id,
                    ),
                )
            else:
                request_id = str(uuid.uuid4())
                connection.execute(
                    """
                    INSERT INTO telegram_review_requests(
                        id, question_uid, chat_id, user_id, username, message_id, source,
                        status, note, requested_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, 'pendente', ?, ?, ?)
                    """,
                    (
                        request_id, uid, str(chat_id), str(user_id), str(username), message_id,
                        str(source), str(note)[:2000], now, now,
                    ),
                )
            connection.execute(
                """
                UPDATE study_state
                SET suspended = 1, correction_priority = 0, correction_requested_at = ?,
                    correction_resolved_at = NULL
                WHERE question_uid = ?
                """,
                (now, uid),
            )
        result = self.get_review_request(request_id)
        if not result:
            raise RuntimeError("Não foi possível registrar a solicitação de correção.")
        return result

    def get_review_request(self, request_id: str) -> dict | None:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT r.*, q.source_code, q.subject, q.primary_topic, q.statement,
                       q.review_status, q.board, q.exam_year, q.agency
                FROM telegram_review_requests r
                JOIN questions q ON q.uid = r.question_uid
                WHERE r.id = ?
                """,
                (str(request_id),),
            ).fetchone()
        return dict(row) if row else None

    def list_review_requests(self, status: str = "ativas", limit: int = 1000) -> list[dict]:
        status = str(status or "ativas")
        clauses = []
        values: list = []
        if status == "ativas":
            clauses.append("r.status IN ('pendente', 'aberta')")
        elif status != "todas":
            clauses.append("r.status = ?")
            values.append(status)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        values.append(max(1, min(int(limit), 5000)))
        with self.database.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT r.*, q.source_code, q.subject, q.primary_topic, q.statement,
                       q.review_status, q.board, q.exam_year, q.agency
                FROM telegram_review_requests r
                JOIN questions q ON q.uid = r.question_uid
                {where}
                ORDER BY CASE r.status WHEN 'pendente' THEN 0 WHEN 'aberta' THEN 1 ELSE 2 END,
                         r.requested_at DESC
                LIMIT ?
                """,
                values,
            ).fetchall()
        return [dict(row) for row in rows]

    def pending_review_count(self) -> int:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) FROM telegram_review_requests WHERE status IN ('pendente', 'aberta')"
            ).fetchone()
        return int(row[0]) if row else 0

    def mark_review_opened(self, request_id: str) -> None:
        now = utc_now()
        with self.database.connect() as connection:
            connection.execute(
                """
                UPDATE telegram_review_requests
                SET status = 'aberta', opened_at = COALESCE(opened_at, ?), updated_at = ?
                WHERE id = ? AND status = 'pendente'
                """,
                (now, now, str(request_id)),
            )

    def _reactivate_corrected_question(self, connection: sqlite3.Connection, question_uid: str, now: str) -> None:
        """Recoloca a questão corrigida no ciclo, com prioridade na próxima vez que a matéria for selecionada."""
        connection.execute(
            """
            UPDATE study_state
            SET suspended = 0, due_at = ?, correction_priority = 1,
                correction_resolved_at = ?
            WHERE question_uid = ?
            """,
            (now, now, str(question_uid)),
        )

    def resolve_review_request(self, request_id: str) -> None:
        now = utc_now()
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT question_uid FROM telegram_review_requests WHERE id = ?",
                (str(request_id),),
            ).fetchone()
            connection.execute(
                """
                UPDATE telegram_review_requests
                SET status = 'resolvida', resolved_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (now, now, str(request_id)),
            )
            if row:
                self._reactivate_corrected_question(connection, str(row["question_uid"]), now)

    def resolve_review_requests_for_question(self, question_uid: str) -> int:
        now = utc_now()
        with self.database.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE telegram_review_requests
                SET status = 'resolvida', resolved_at = ?, updated_at = ?
                WHERE question_uid = ? AND status IN ('pendente', 'aberta')
                """,
                (now, now, str(question_uid)),
            )
            if int(cursor.rowcount or 0) > 0:
                self._reactivate_corrected_question(connection, str(question_uid), now)
        return int(cursor.rowcount or 0)

    def delete_review_request(self, request_id: str) -> None:
        with self.database.connect() as connection:
            connection.execute(
                "DELETE FROM telegram_review_requests WHERE id = ?", (str(request_id),)
            )

    def begin_cycle(
        self,
        cycle_id: str,
        cycle_kind: str,
        planned_count: int,
        *,
        scheduled_for: str | None = None,
        scheduled_date: str | None = None,
        requested_via: str = "programa",
    ) -> None:
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO study_cycles(
                    id, cycle_kind, scheduled_for, scheduled_date, requested_via,
                    planned_count, sent_count, error_count, status, started_at
                ) VALUES (?, ?, ?, ?, ?, ?, 0, 0, 'iniciado', ?)
                """,
                (
                    cycle_id,
                    cycle_kind,
                    scheduled_for,
                    scheduled_date,
                    requested_via,
                    max(0, int(planned_count)),
                    utc_now(),
                ),
            )

    def finish_cycle(self, cycle_id: str, sent: int, errors: int, status: str, notes: str = "") -> None:
        with self.database.connect() as connection:
            connection.execute(
                """
                UPDATE study_cycles
                SET sent_count = ?, error_count = ?, status = ?, finished_at = ?, notes = ?
                WHERE id = ?
                """,
                (max(0, int(sent)), max(0, int(errors)), str(status), utc_now(), str(notes)[:2000], cycle_id),
            )

    def daily_cycle_done(self, scheduled_date: str) -> bool:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT 1 FROM study_cycles
                WHERE scheduled_date = ? AND cycle_kind IN ('diario', 'recuperacao')
                  AND sent_count > 0 AND status IN ('concluido', 'parcial')
                LIMIT 1
                """,
                (scheduled_date,),
            ).fetchone()
        return bool(row)

    @staticmethod
    def _subject_clause(subjects: Iterable[str], values: list) -> str:
        normalized = [item.strip() for item in subjects if item and item.strip()]
        if not normalized:
            return ""
        placeholders = ",".join("?" for _ in normalized)
        values.extend(normalized)
        return f"q.subject IN ({placeholders})"

    def _base_clauses(
        self,
        filters: SelectionFilters,
        values: list,
        *,
        review_status: str | None = None,
    ) -> list[str]:
        clauses = ["COALESCE(s.suspended, 0) = 0", "q.answer IS NOT NULL", "q.answer != ''"]
        subject_clause = self._subject_clause(filters.subjects, values)
        if subject_clause:
            clauses.append(subject_clause)
        if filters.topic.strip():
            term = f"%{filters.topic.strip()}%"
            clauses.append("(q.primary_topic LIKE ? OR q.topics_text LIKE ? OR q.lesson LIKE ? OR q.statement LIKE ?)")
            values.extend([term, term, term, term])
        if str(filters.board or "").strip():
            clauses.append("UPPER(COALESCE(q.board, '')) = UPPER(?)")
            values.append(str(filters.board).strip())
        included = [str(uid).strip() for uid in (filters.include_uids or ()) if str(uid).strip()]
        if included:
            placeholders = ",".join("?" for _ in included)
            clauses.append(f"q.uid IN ({placeholders})")
            values.extend(included)
        excluded = [str(uid).strip() for uid in (filters.exclude_uids or ()) if str(uid).strip()]
        if excluded:
            placeholders = ",".join("?" for _ in excluded)
            clauses.append(f"q.uid NOT IN ({placeholders})")
            values.extend(excluded)
        if review_status == "aprovado":
            clauses.append("q.review_status IN ('aprovado', 'aprovada')")
        elif review_status == "aprovado_automaticamente":
            clauses.append("q.review_status IN ('aprovado_automaticamente', 'autoaprovado', 'autoaprovada')")
        elif review_status:
            clauses.append("q.review_status = ?")
            values.append(str(review_status))
        elif filters.approved_only:
            clauses.append(
                "q.review_status IN ('aprovado', 'aprovada', 'aprovado_automaticamente', 'autoaprovado', 'autoaprovada')"
            )
        # 6.5: questões desatualizadas/anuladas/controversas permanecem no Banco
        # Editorial e nas estatísticas históricas, mas não entram em novas
        # seleções de aprendizagem até revisão humana.
        clauses.append("COALESCE((SELECT qc.status FROM qf_question_currency qc WHERE qc.question_uid=q.uid), 'vigente') NOT IN ('desatualizada','anulada','controversa')")
        return clauses

    def _selection_query(
        self,
        filters: SelectionFilters,
        limit: int,
        due_only: bool,
        *,
        review_status: str | None = None,
    ) -> tuple[str, list]:
        values: list = []
        clauses = self._base_clauses(filters, values, review_status=review_status)
        if due_only:
            clauses.append("(s.sent_count = 0 OR s.due_at IS NULL OR s.due_at <= ?)")
            values.append(utc_now())

        strategy = filters.strategy.strip().lower()
        if strategy == "novas_primeiro":
            order = "s.sent_count ASC, COALESCE(s.last_sent_at, '') ASC, RANDOM()"
        elif strategy == "erros_primeiro":
            order = "s.wrong_count DESC, s.sent_count ASC, COALESCE(s.last_answered_at, '') ASC, RANDOM()"
        elif strategy == "aleatorio":
            order = "RANDOM()"
        else:
            order = (
                "CASE WHEN s.wrong_count > s.correct_count THEN 0 WHEN s.sent_count = 0 THEN 1 ELSE 2 END ASC, "
                "s.wrong_count DESC, s.sent_count ASC, COALESCE(s.due_at, '') ASC, RANDOM()"
            )

        query = f"""
            SELECT q.uid, q.data_json, q.subject, q.primary_topic, q.lesson, q.review_status, q.board,
                   s.sent_count, s.correct_count, s.wrong_count,
                   s.streak, s.last_sent_at, s.last_answered_at, s.due_at, s.correction_priority,
                   s.memory_difficulty, s.memory_stability, s.memory_retrievability,
                   s.response_time_ema, s.adaptive_prediction, s.adaptive_priority,
                   s.kt_mastery, s.kt_confidence, s.irt_information, s.learner_fusion_priority, s.learner_model_version,
                   s.scaffold_dependency, s.scaffold_last_level, s.scaffold_session_count, s.scaffold_solved_count
            FROM questions q
            JOIN study_state s ON s.question_uid = q.uid
            WHERE {' AND '.join(clauses)}
            ORDER BY COALESCE(s.correction_priority, 0) DESC, {order}
            LIMIT ?
        """
        values.append(max(1, int(limit)))
        return query, values

    @staticmethod
    def _row_to_question(row: sqlite3.Row) -> dict:
        question = json.loads(row["data_json"])
        question["database_uid"] = row["uid"]
        question["study_state"] = {
            "sent_count": row["sent_count"],
            "correct_count": row["correct_count"],
            "wrong_count": row["wrong_count"],
            "streak": row["streak"],
            "last_sent_at": row["last_sent_at"],
            "last_answered_at": row["last_answered_at"] if "last_answered_at" in row.keys() else None,
            "due_at": row["due_at"],
            "memory_difficulty": row["memory_difficulty"] if "memory_difficulty" in row.keys() else 5.0,
            "memory_stability": row["memory_stability"] if "memory_stability" in row.keys() else 1.0,
            "memory_retrievability": row["memory_retrievability"] if "memory_retrievability" in row.keys() else 0.9,
            "response_time_ema": row["response_time_ema"] if "response_time_ema" in row.keys() else 0.0,
            "adaptive_prediction": row["adaptive_prediction"] if "adaptive_prediction" in row.keys() else 0.5,
            "adaptive_priority": row["adaptive_priority"] if "adaptive_priority" in row.keys() else 0.0,
            "kt_mastery": row["kt_mastery"] if "kt_mastery" in row.keys() else None,
            "kt_confidence": row["kt_confidence"] if "kt_confidence" in row.keys() else 0.0,
            "irt_information": row["irt_information"] if "irt_information" in row.keys() else 0.0,
            "learner_fusion_priority": row["learner_fusion_priority"] if "learner_fusion_priority" in row.keys() else 0.0,
            "learner_model_version": row["learner_model_version"] if "learner_model_version" in row.keys() else None,
            "scaffold_dependency": row["scaffold_dependency"] if "scaffold_dependency" in row.keys() else 0.0,
            "scaffold_last_level": row["scaffold_last_level"] if "scaffold_last_level" in row.keys() else None,
            "scaffold_session_count": row["scaffold_session_count"] if "scaffold_session_count" in row.keys() else 0,
            "scaffold_solved_count": row["scaffold_solved_count"] if "scaffold_solved_count" in row.keys() else 0,
        }
        return question

    def _auditor_intelligent_selection(
        self,
        filters: SelectionFilters,
        limit: int,
        *,
        review_status: str | None = None,
        persist_state: bool = True,
    ) -> list[dict]:
        """Scheduler adaptativo com vencimento real, escopo estudado e interleaving ponderado.

        A ordem entre classes é rígida: correções -> relearning vencido -> revisões
        vencidas -> novas de conteúdo estudado -> antecipações. A diversidade atua
        *dentro* da classe, sem permitir que uma questão futura ultrapasse uma
        revisão já vencida apenas por ter score maior.
        """
        values: list = []
        clauses = self._base_clauses(filters, values, review_status=review_status)
        query = f"""
            SELECT q.uid, q.data_json, q.subject, q.primary_topic, q.lesson, q.review_status, q.board,
                   s.sent_count, s.correct_count, s.wrong_count, s.streak,
                   s.last_sent_at, s.last_answered_at, s.due_at, s.correction_priority,
                   s.memory_difficulty, s.memory_stability, s.memory_retrievability,
                   s.response_time_ema, s.adaptive_prediction, s.adaptive_priority,
                   s.fsrs_state, s.fsrs_lapses, s.fsrs_card_json,
                   s.kt_mastery, s.kt_confidence, s.irt_information, s.learner_fusion_priority, s.learner_model_version
            FROM questions q
            JOIN study_state s ON s.question_uid = q.uid
            WHERE {' AND '.join(clauses)}
        """
        with self.database.connect() as connection:
            rows = connection.execute(query, values).fetchall()
            topic_rows = connection.execute(
                "SELECT subject, topic, correct_count, wrong_count, exposure_count, last_seen_at FROM topic_learning_state"
            ).fetchall()
            lesson_rows = connection.execute(
                "SELECT subject, lesson, correct_count, wrong_count, exposure_count, last_seen_at FROM lesson_learning_state"
            ).fetchall()
        if not rows:
            return []

        prefs = self.learning_preferences()
        scope_initialized = self.get_runtime("studied_scope_initialized", "0") == "1"
        studied_scope = self._studied_scope() if bool(prefs.get("studied_only")) and scope_initialized else set()
        if bool(prefs.get("studied_only")) and scope_initialized:
            rows = [
                row for row in rows
                if (
                    self._norm_coverage_text(str(row["subject"] or "")),
                    self._norm_lesson(str(row["lesson"] or "")),
                ) in studied_scope
            ]
        if not rows:
            return []

        board_counts: dict[str, int] = {}
        subject_board_counts: dict[tuple[str, str], int] = {}
        subject_totals: dict[str, int] = {}
        for row in rows:
            subject_key = str(row["subject"] or "SEM MATÉRIA").strip() or "SEM MATÉRIA"
            board_key = str(row["board"] or "NÃO INFORMADA").strip() or "NÃO INFORMADA"
            board_counts[board_key] = board_counts.get(board_key, 0) + 1
            subject_board_counts[(subject_key, board_key)] = subject_board_counts.get((subject_key, board_key), 0) + 1
            subject_totals[subject_key] = subject_totals.get(subject_key, 0) + 1

        topic_states = {
            (str(item["subject"] or "SEM MATÉRIA"), str(item["topic"] or "SEM ASSUNTO")): item
            for item in topic_rows
        }
        lesson_states = {
            (str(item["subject"] or "SEM MATÉRIA"), str(item["lesson"] or "SEM AULA")): item
            for item in lesson_rows
        }
        total_topic_exposures = sum(int(item["exposure_count"] or 0) for item in topic_rows)
        total_lesson_exposures = sum(int(item["exposure_count"] or 0) for item in lesson_rows)
        now = utc_now_dt()
        model = self._load_adaptive_model()
        rng = random.Random(int(now.strftime("%Y%m%d%H")))
        fsrs_retention = self.effective_target_retention()
        fsrs_params = self.fsrs_parameters()
        fsrs_retrievability = batch_retrievability(
            {str(row["uid"]): row["fsrs_card_json"] for row in rows},
            desired_retention=fsrs_retention,
            parameters=fsrs_params,
            now=now,
        )
        candidates: list[dict] = []
        subject_metrics: dict[str, dict[str, float | datetime | None]] = {}
        state_updates: list[tuple[float, float, float, str]] = []
        exam_text = str(prefs.get("exam_date") or "").strip()
        scheduler_days_to_exam: int | None = None
        if exam_text:
            try:
                scheduler_days_to_exam = max(0, (datetime.fromisoformat(exam_text).date() - now.date()).days)
            except ValueError:
                scheduler_days_to_exam = None
        scheduler_exam_urgency = analytics_exam_urgency(scheduler_days_to_exam)

        for row in rows:
            subject = str(row["subject"] or "SEM MATÉRIA").strip() or "SEM MATÉRIA"
            lesson = str(row["lesson"] or "SEM AULA").strip() or "SEM AULA"
            topic = str(row["primary_topic"] or lesson or "SEM ASSUNTO").strip() or "SEM ASSUNTO"
            correct_count = int(row["correct_count"] or 0)
            wrong_count = int(row["wrong_count"] or 0)
            attempts = correct_count + wrong_count
            sent_count = int(row["sent_count"] or 0)
            is_new = sent_count == 0
            due_dt = _parse_iso(row["due_at"])
            last_sent = _parse_iso(row["last_sent_at"])
            last_answered = _parse_iso(row["last_answered_at"])
            is_due_review = (not is_new) and (due_dt is None or due_dt <= now)
            overdue_days = 0.0 if due_dt is None else max(0.0, (now - due_dt).total_seconds() / 86400.0)
            reference_time = last_answered or last_sent
            elapsed_days = 0.0 if reference_time is None else max(0.0, (now - reference_time).total_seconds() / 86400.0)
            correction = bool(int(row["correction_priority"] or 0))
            fsrs_state = str(row["fsrs_state"] or "new").strip().lower()

            memory = MemoryState.from_mapping({
                "difficulty": row["memory_difficulty"],
                "stability_days": row["memory_stability"],
                "retrievability": row["memory_retrievability"],
                "response_time_ema": row["response_time_ema"],
                "review_count": attempts,
            })
            retrievability = fsrs_retrievability.get(
                str(row["uid"]),
                forgetting_curve(elapsed_days, memory.stability_days),
            )
            historical_accuracy = (correct_count + 1.0) / (attempts + 2.0)
            features = model.features(
                state=memory,
                elapsed_days=elapsed_days,
                historical_accuracy=historical_accuracy,
                response_seconds=memory.response_time_ema,
                is_new=is_new,
                autoapproved=str(row["review_status"] or "").lower() != "aprovado",
            )
            predicted = model.predict(features)
            score = adaptive_priority_score(
                predicted_recall=predicted,
                retrievability=retrievability,
                overdue_days=overdue_days,
                is_new=is_new,
                sent_count=sent_count,
                correction_priority=correction,
                review_status=str(row["review_status"] or ""),
            )
            # QuestFlow 6: dentro da mesma classe FSRS, prioriza lacunas de
            # domínio e itens informativos. A hierarquia de vencimento continua
            # rígida e nunca é substituída pela IRT/KT.
            learner_fusion = float(row["learner_fusion_priority"] or 0.0) if "learner_fusion_priority" in row.keys() else 0.0
            if learner_fusion > 0.0:
                score += 0.55 * learner_fusion
            # O scaffolding é evidência de dependência de apoio, não substitui KT/FSRS.
            # Ele apenas aumenta moderadamente a prioridade de prática independente.
            scaffold_dependency = float(row["scaffold_dependency"] or 0.0) if "scaffold_dependency" in row.keys() else 0.0
            if scaffold_dependency > 0.0:
                score += 9.0 * max(0.0, min(1.0, scaffold_dependency))
            strategy = str(filters.strategy or "adaptativo").strip().lower()
            if strategy == "erros_primeiro":
                score += wrong_count * 26.0
            elif strategy == "novas_primeiro" and is_new:
                score += 42.0
            elif strategy == "aleatorio":
                score += rng.random() * 60.0

            topic_row = topic_states.get((subject, topic))
            topic_age = 999.0
            if topic_row:
                seen = _parse_iso(topic_row["last_seen_at"])
                topic_age = 999.0 if seen is None else max(0.0, (now - seen).total_seconds() / 86400.0)
                topic_state = TopicState(
                    subject=subject, topic=topic,
                    correct=int(topic_row["correct_count"] or 0), wrong=int(topic_row["wrong_count"] or 0),
                    exposures=int(topic_row["exposure_count"] or 0), last_seen_days=topic_age,
                )
            else:
                topic_state = TopicState(subject=subject, topic=topic)
            score += topic_priority(
                topic_state,
                total_exposures=max(1, total_topic_exposures),
                coverage_gap=1.0 if topic_state.exposures == 0 else 0.0,
                predicted_recall=predicted,
            )

            lesson_row = lesson_states.get((subject, lesson))
            if lesson_row:
                seen = _parse_iso(lesson_row["last_seen_at"])
                lesson_age = 999.0 if seen is None else max(0.0, (now - seen).total_seconds() / 86400.0)
                lesson_state = TopicState(
                    subject=subject, topic=lesson,
                    correct=int(lesson_row["correct_count"] or 0), wrong=int(lesson_row["wrong_count"] or 0),
                    exposures=int(lesson_row["exposure_count"] or 0), last_seen_days=lesson_age,
                )
            else:
                lesson_state = TopicState(subject=subject, topic=lesson)
            score += 0.55 * topic_priority(
                lesson_state,
                total_exposures=max(1, total_lesson_exposures),
                coverage_gap=1.0 if lesson_state.exposures == 0 else 0.0,
                predicted_recall=predicted,
            )

            board = str(row["board"] or "NÃO INFORMADA").strip() or "NÃO INFORMADA"
            subject_total = max(1, int(subject_totals.get(subject, 1)))
            observed_incidence = subject_board_counts.get((subject, board), 0) / subject_total
            coverage_gap = 0.60 / math.sqrt(1.0 + max(0, topic_state.exposures)) + 0.40 / math.sqrt(1.0 + max(0, lesson_state.exposures))
            recommendation = multiobjective_priority(
                mastery=None if row["kt_mastery"] is None else float(row["kt_mastery"]),
                mastery_confidence=float(row["kt_confidence"] or 0.0),
                retrievability=retrievability,
                coverage_gap=coverage_gap,
                board_incidence=observed_incidence,
                irt_information=float(row["irt_information"] or 0.0),
                exam_urgency=scheduler_exam_urgency,
                days_since_seen=None if reference_time is None else elapsed_days,
                mode=str(filters.recommendation_mode or "equilibrado"),
            )
            # O score multiobjetivo ordena somente dentro da classe FSRS. A classe
            # continua definida abaixo por correction/relearning/due/new/early.
            score += 1.15 * recommendation.score

            if correction:
                bucket = 0
                reason = "Correção/revisão marcada manualmente"
            elif fsrs_state == "relearning" and (due_dt is None or due_dt <= now):
                bucket = 1
                reason = "Recuperação pós-erro (relearning) vencida"
            elif is_due_review:
                bucket = 2
                if overdue_days >= 1:
                    reason = f"Revisão FSRS vencida há {overdue_days:.1f} dia(s)"
                else:
                    reason = "Revisão FSRS vencida"
            elif is_new:
                bucket = 3
                reason = "Questão nova de conteúdo já estudado"
            else:
                bucket = 4
                remaining = 0.0 if due_dt is None else max(0.0, (due_dt - now).total_seconds() / 86400.0)
                reason = f"Revisão antecipada por risco (vence em {remaining:.1f} dia(s))"

            metrics = subject_metrics.setdefault(subject, {
                "wrong": 0.0, "attempts": 0.0, "risk": 0.0, "new": 0.0,
                "count": 0.0, "oldest": None, "latest_review": None, "correction": 0.0,
                "retention_sum": 0.0, "due": 0.0,
            })
            metrics["wrong"] = float(metrics["wrong"] or 0.0) + wrong_count
            metrics["attempts"] = float(metrics["attempts"] or 0.0) + attempts
            metrics["risk"] = float(metrics["risk"] or 0.0) + (1.0 - predicted)
            metrics["retention_sum"] = float(metrics["retention_sum"] or 0.0) + retrievability
            metrics["new"] = float(metrics["new"] or 0.0) + (1.0 if is_new else 0.0)
            metrics["due"] = float(metrics["due"] or 0.0) + (1.0 if bucket in (1, 2) else 0.0)
            metrics["count"] = float(metrics["count"] or 0.0) + 1.0
            metrics["correction"] = float(metrics["correction"] or 0.0) + (1.0 if correction else 0.0)
            oldest = metrics["oldest"]
            if last_sent is None or oldest is None or (isinstance(oldest, datetime) and last_sent < oldest):
                metrics["oldest"] = last_sent
            latest_review = metrics["latest_review"]
            if last_answered is not None and (latest_review is None or (isinstance(latest_review, datetime) and last_answered > latest_review)):
                metrics["latest_review"] = last_answered

            score += rng.random() * 0.25
            candidates.append({
                "row": row, "subject": subject, "lesson": lesson, "topic": topic, "board": board,
                "bucket": bucket, "reason": reason, "score": score,
                "prediction": predicted, "retrievability": retrievability,
                "recommendation": recommendation,
            })
            state_updates.append((retrievability, predicted, score, str(row["uid"])))

        def _subject_risk(subject: str) -> float:
            m = subject_metrics[subject]
            attempts = float(m["attempts"] or 0.0)
            wrong = float(m["wrong"] or 0.0)
            count = max(1.0, float(m["count"] or 1.0))
            current_accuracy = None if attempts <= 0 else max(0.0, min(1.0, (attempts - wrong) / attempts))
            retention = max(0.0, min(1.0, float(m["retention_sum"] or 0.0) / count))
            coverage = max(0.0, min(1.0, 1.0 - float(m["new"] or 0.0) / count))
            latest_review = m["latest_review"]
            days_since_review = None if latest_review is None else max(0.0, (now - latest_review).total_seconds() / 86400.0)
            priority = analytics_subject_priority(
                retention=retention, recent_accuracy=current_accuracy, coverage=coverage,
                days_since_review=days_since_review, exam_urgency=scheduler_exam_urgency,
                due_count=int(m["due"] or 0), attempts=int(attempts), studied=True,
                performance_target=DEFAULT_PERFORMANCE_TARGET,
            )
            return priority.score + float(m["correction"] or 0.0) * 100.0

        for item in candidates:
            item["score"] = float(item["score"]) + 0.65 * _subject_risk(str(item["subject"]))

        # Pré-visualizações (dashboard/recomendador) são estritamente read-only.
        # Só uma seleção operacional (Telegram/simulado) pode materializar esses
        # campos derivados no SQLite. Mesmo quando persistidos, o Cloud Sync
        # ignora esses campos transitórios.
        if persist_state and state_updates:
            with self.database.connect() as connection:
                connection.executemany(
                    "UPDATE study_state SET memory_retrievability = ?, adaptive_prediction = ?, adaptive_priority = ? WHERE question_uid = ?",
                    state_updates,
                )

        # Se antecipação estiver desativada, ela só é usada como último recurso de
        # reciclagem e nunca passa à frente de algo vencido/novo.
        early_allowed = bool(prefs.get("early_review_enabled"))
        primary_exists = any(int(item["bucket"]) < 4 for item in candidates)
        if not early_allowed and (primary_exists or not filters.recycle_when_empty):
            candidates = [item for item in candidates if int(item["bucket"]) < 4]

        selected: list[dict] = []
        selected_uids: set[str] = set()
        subject_counts: dict[str, int] = {}
        topic_counts: dict[tuple[str, str], int] = {}
        lesson_counts: dict[tuple[str, str], int] = {}
        board_selected_counts: dict[str, int] = {}
        last_subject = ""
        last_topic: tuple[str, str] | None = None

        for bucket in (0, 1, 2, 3, 4):
            pool = [item for item in candidates if int(item["bucket"]) == bucket]
            while pool and len(selected) < limit:
                best = None
                best_value = -1e30
                for item in pool:
                    uid = str(item["row"]["uid"])
                    if uid in selected_uids:
                        continue
                    subject = str(item["subject"])
                    topic_key = (subject, str(item["topic"]))
                    lesson_key = (subject, str(item["lesson"]))
                    board_key = str(item.get("board") or "NÃO INFORMADA")
                    value = diversity_adjusted_value(
                        float(item["score"]),
                        subject_count=subject_counts.get(subject, 0),
                        topic_count=topic_counts.get(topic_key, 0),
                        lesson_count=lesson_counts.get(lesson_key, 0),
                        board_count=board_selected_counts.get(board_key, 0),
                        same_as_last_subject=(subject == last_subject and len({str(p["subject"]) for p in pool}) > 1),
                        same_as_last_topic=(topic_key == last_topic and len({(str(p["subject"]), str(p["topic"])) for p in pool}) > 1),
                    )
                    if value > best_value:
                        best_value = value
                        best = item
                if best is None:
                    break
                pool.remove(best)
                selected.append(best)
                uid = str(best["row"]["uid"])
                selected_uids.add(uid)
                last_subject = str(best["subject"])
                last_topic = (last_subject, str(best["topic"]))
                subject_counts[last_subject] = subject_counts.get(last_subject, 0) + 1
                topic_counts[last_topic] = topic_counts.get(last_topic, 0) + 1
                lesson_key = (last_subject, str(best["lesson"]))
                lesson_counts[lesson_key] = lesson_counts.get(lesson_key, 0) + 1
                board_key = str(best.get("board") or "NÃO INFORMADA")
                board_selected_counts[board_key] = board_selected_counts.get(board_key, 0) + 1
            if len(selected) >= limit:
                break

        if persist_state and selected:
            with self.database.connect() as connection:
                connection.executemany(
                    "UPDATE study_state SET last_selection_reason = ?, last_selection_bucket = ? WHERE question_uid = ?",
                    [(str(item["reason"]), str(item["bucket"]), str(item["row"]["uid"])) for item in selected],
                )

        output: list[dict] = []
        for item in selected:
            question = self._row_to_question(item["row"])
            question["selection_reason"] = str(item["reason"])
            question["selection_bucket"] = int(item["bucket"])
            question["predicted_recall"] = round(float(item["prediction"]), 4)
            question["retrievability"] = round(float(item["retrievability"]), 4)
            st = question.get("study_state", {})
            if st.get("kt_mastery") is not None:
                question["knowledge_mastery"] = round(float(st.get("kt_mastery") or 0.0), 4)
                question["knowledge_confidence"] = round(float(st.get("kt_confidence") or 0.0), 4)
            question["irt_information"] = round(float(st.get("irt_information") or 0.0), 4)
            question["learner_fusion_priority"] = round(float(st.get("learner_fusion_priority") or 0.0), 2)
            recommendation = item.get("recommendation")
            if recommendation is not None:
                question["recommendation_score"] = float(recommendation.score)
                question["recommendation_components"] = dict(recommendation.components)
                question["recommendation_signals"] = dict(recommendation.signals)
                question["recommendation_reasons"] = list(recommendation.reasons)
                question["recommendation_mode"] = str(recommendation.mode)
                question["recommendation_version"] = str(recommendation.version)
            output.append(question)
        return output

    def _select_status_tier(
        self,
        filters: SelectionFilters,
        limit: int,
        review_status: str,
        *,
        persist_state: bool = True,
    ) -> list[dict]:
        if limit <= 0:
            return []
        if filters.strategy.strip().lower() in {"auditor_inteligente", "adaptativo"}:
            result = self._auditor_intelligent_selection(
                filters,
                limit,
                review_status=review_status,
                persist_state=persist_state,
            )
            if result or not filters.recycle_when_empty:
                return result
        query, values = self._selection_query(
            filters,
            limit,
            due_only=True,
            review_status=review_status,
        )
        with self.database.connect() as connection:
            rows = connection.execute(query, values).fetchall()
            if not rows and filters.recycle_when_empty:
                query, values = self._selection_query(
                    filters,
                    limit,
                    due_only=False,
                    review_status=review_status,
                )
                rows = connection.execute(query, values).fetchall()
        return [self._row_to_question(row) for row in rows]

    def select_questions(self, filters: SelectionFilters, limit: int, *, persist_state: bool = True) -> list[dict]:
        """Seleciona questões preservando precedência FSRS.

        ``persist_state=False`` torna a seleção estritamente read-only e deve ser
        usado por dashboards/pré-visualizações. Seleções operacionais (Telegram e
        simulado) mantêm o padrão ``True``.
        """
        self.sync_questions()
        limit = max(1, int(limit))
        if filters.approved_only:
            approved = self._select_status_tier(filters, limit, "aprovado", persist_state=persist_state)
            remaining = max(0, limit - len(approved))
            if remaining:
                approved.extend(
                    self._select_status_tier(
                        filters,
                        remaining,
                        "aprovado_automaticamente",
                        persist_state=persist_state,
                    )
                )
            return approved

        strict_studied = self.learning_preferences().get("studied_only", True) and self.get_runtime("studied_scope_initialized", "0") == "1"
        if filters.strategy.strip().lower() in {"auditor_inteligente", "adaptativo"} or strict_studied:
            result = self._auditor_intelligent_selection(filters, limit, persist_state=persist_state)
            if result or not filters.recycle_when_empty or strict_studied:
                return result
        query, values = self._selection_query(filters, limit, due_only=True)
        with self.database.connect() as connection:
            rows = connection.execute(query, values).fetchall()
            if not rows and filters.recycle_when_empty:
                query, values = self._selection_query(filters, limit, due_only=False)
                rows = connection.execute(query, values).fetchall()
        return [self._row_to_question(row) for row in rows]

    def record_delivery(
        self,
        question_uid: str,
        chat_id: str,
        send_result: dict,
        cycle_id: str,
        *,
        parent_delivery_id: str | None = None,
        attempt_count: int = 1,
        resend_reason: str | None = None,
        unanswered_resend_count: int = 0,
    ) -> dict:
        delivery_id = str(uuid.uuid4())
        sent_at = utc_now()
        poll_data = send_result.get("poll", {}).get("result", {})
        poll = poll_data.get("poll", {}) if isinstance(poll_data, dict) else {}
        poll_id = str(poll.get("id", "") or "")
        message_id = poll_data.get("message_id") if isinstance(poll_data, dict) else None
        direct_poll = 1 if send_result.get("direct_poll", True) else 0
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO telegram_deliveries(
                    id, cycle_id, question_uid, poll_id, chat_id, message_id,
                    sent_at, direct_poll, status, attempt_count, last_attempt_at,
                    parent_delivery_id, resend_reason, unanswered_resend_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'enviado', ?, ?, ?, ?, ?)
                """,
                (
                    delivery_id,
                    cycle_id,
                    question_uid,
                    poll_id or None,
                    str(chat_id),
                    message_id,
                    sent_at,
                    direct_poll,
                    max(1, int(attempt_count)),
                    sent_at,
                    parent_delivery_id,
                    str(resend_reason or "") or None,
                    max(0, int(unanswered_resend_count)),
                ),
            )
            if parent_delivery_id:
                connection.execute(
                    """
                    UPDATE telegram_deliveries
                    SET status = ?, resolved_by_delivery_id = ?, next_retry_at = NULL,
                        last_attempt_at = ?, last_unanswered_check_at = ?
                    WHERE id = ?
                    """,
                    (
                        "reenviado_sem_resposta" if resend_reason == "sem_resposta" else "reenviado",
                        delivery_id, sent_at, sent_at, parent_delivery_id,
                    ),
                )
            connection.execute(
                """
                UPDATE study_state
                SET sent_count = sent_count + 1, last_sent_at = ?, due_at = ?,
                    correction_priority = 0
                WHERE question_uid = ?
                """,
                (sent_at, _iso_after(hours=12), question_uid),
            )
        return {
            "delivery_id": delivery_id,
            "poll_id": poll_id,
            "message_id": message_id,
            "sent_at": sent_at,
            "parent_delivery_id": parent_delivery_id,
            "resend_reason": resend_reason,
            "unanswered_resend_count": max(0, int(unanswered_resend_count)),
        }

    def unanswered_deliveries_due(
        self,
        *,
        wait_hours: float = 24.0,
        max_resends: int = 2,
        limit: int = 20,
        min_sent_at: str | None = None,
    ) -> list[dict]:
        """Retorna somente o envio sem resposta mais recente de cada questão."""
        wait_hours = max(0.25, float(wait_hours))
        max_resends = max(0, int(max_resends))
        if max_resends <= 0:
            return []
        now_dt = utc_now_dt()
        cutoff = (now_dt - timedelta(hours=wait_hours)).isoformat()
        check_cutoff = (now_dt - timedelta(minutes=5)).isoformat()
        clauses = [
            "d.status = 'enviado'",
            "d.resolved_by_delivery_id IS NULL",
            "d.sent_at <= ?",
            "COALESCE(d.unanswered_resend_count, 0) < ?",
            "(d.last_unanswered_check_at IS NULL OR d.last_unanswered_check_at <= ?)",
            "COALESCE(s.suspended, 0) = 0",
            "NOT EXISTS (SELECT 1 FROM telegram_attempts a WHERE a.delivery_id = d.id)",
            "NOT EXISTS (SELECT 1 FROM telegram_deliveries newer "
            "WHERE newer.question_uid = d.question_uid AND newer.sent_at > d.sent_at "
            "AND newer.status IN ('enviado', 'reenviado', 'reenviado_sem_resposta'))",
        ]
        values: list = [cutoff, max_resends, check_cutoff]
        if min_sent_at:
            clauses.append("d.sent_at >= ?")
            values.append(str(min_sent_at))
        values.append(max(1, min(int(limit), 100)))
        with self.database.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT d.*, q.data_json, q.source_code, q.subject, q.primary_topic
                FROM telegram_deliveries d
                JOIN questions q ON q.uid = d.question_uid
                JOIN study_state s ON s.question_uid = d.question_uid
                WHERE {' AND '.join(clauses)}
                ORDER BY d.sent_at ASC
                LIMIT ?
                """,
                values,
            ).fetchall()
        result: list[dict] = []
        for row in rows:
            item = dict(row)
            item["question"] = json.loads(item.pop("data_json"))
            result.append(item)
        return result

    def mark_unanswered_check(self, delivery_id: str) -> None:
        with self.database.connect() as connection:
            connection.execute(
                "UPDATE telegram_deliveries SET last_unanswered_check_at = ? WHERE id = ?",
                (utc_now(), str(delivery_id)),
            )

    @staticmethod
    def _norm_coverage_text(value: str) -> str:
        raw = unicodedata.normalize("NFKD", str(value or ""))
        raw = "".join(char for char in raw if not unicodedata.combining(char))
        return re.sub(r"\s+", " ", raw).strip().upper()

    @classmethod
    def _norm_lesson(cls, value: str) -> str:
        text = cls._norm_coverage_text(value)
        match = re.search(r"\bAULA\s*(\d{1,3})\b", text)
        return f"AULA {int(match.group(1)):02d}" if match else text

    @classmethod
    def _coverage_tokens(cls, value: str) -> set[str]:
        stopwords = {
            "A", "O", "AS", "OS", "DE", "DA", "DO", "DAS", "DOS", "E", "EM",
            "NO", "NA", "NOS", "NAS", "PARA", "POR", "COM", "SEM", "ATE", "APOS",
            "AULA", "PARTE", "TEORIA", "ESTUDO", "REVISAO", "RESOLUCAO", "QUESTAO",
            "QUESTOES", "PDF", "TOPICO", "FINAL", "INICIO", "INCLUSIVE", "EXCLUSIVE",
        }
        normalized = cls._norm_coverage_text(value)
        return {
            token
            for token in re.findall(r"[A-Z0-9]{2,}", normalized)
            if token not in stopwords
        }

    @classmethod
    def _coverage_group_id(cls, trail: object, subject: object, lesson: object) -> str:
        """Identificador estável para uma aula estudada dentro de uma trilha.

        A cobertura detalhada continua existindo por tarefa, mas a interface pode
        agrupar todas as partes da mesma ``trilha + matéria + aula`` sem perder a
        capacidade de validar o contexto de uma importação.
        """
        trail_norm = cls._norm_coverage_text(trail)
        subject_norm = cls._norm_coverage_text(subject)
        lesson_norm = cls._norm_lesson(lesson)
        return f"{trail_norm}::{subject_norm}::{lesson_norm}"

    @classmethod
    def _task_question_similarity(cls, task: dict, question: dict) -> float:
        description = str(task.get("descricao", "") or "")
        reference = str(question.get("taxonomy_reference", "") or "")
        if reference and cls._norm_coverage_text(reference) == cls._norm_coverage_text(description):
            return 2.0
        if reference and description:
            norm_ref = cls._norm_coverage_text(reference)
            norm_desc = cls._norm_coverage_text(description)
            if norm_ref in norm_desc or norm_desc in norm_ref:
                return 1.5

        task_text = " | ".join(
            [description, *[str(item) for item in task.get("segmentos", []) if str(item).strip()]]
        )
        question_text = " | ".join(
            str(question.get(key, "") or "")
            for key in ("primary_topic", "topics_text", "source_topics", "taxonomy_reference")
        )
        task_tokens = cls._coverage_tokens(task_text)
        question_tokens = cls._coverage_tokens(question_text)
        if not task_tokens or not question_tokens:
            return 0.0
        overlap = len(task_tokens & question_tokens)
        if overlap == 0:
            return 0.0
        containment = overlap / max(1, min(len(task_tokens), len(question_tokens)))
        jaccard = overlap / max(1, len(task_tokens | question_tokens))
        return round(0.72 * containment + 0.28 * jaccard, 4)

    def studied_content_coverage(self, taxonomy_tasks: Iterable[dict]) -> dict:
        """Compare only completed/studied spreadsheet tasks with the question bank.

        ``CICLO_REG`` is treated as the source of truth for what the student has
        actually studied.  A task becomes eligible only when the spreadsheet
        snapshot carries evidence such as effective study time, date, questions
        completed or hits.  Questions are assigned to the most specific matching
        task so multiple parts of the same lesson do not all count the same bank
        question.
        """
        studied: list[dict] = []
        for raw in taxonomy_tasks or []:
            task = dict(raw)
            is_studied = bool(task.get("estudado")) or any(
                [
                    int(task.get("ch_efetiva_min", 0) or 0) > 0,
                    int(task.get("questoes_feitas", 0) or 0) > 0,
                    int(task.get("acertos", 0) or 0) > 0,
                    bool(str(task.get("data", "") or "").strip()),
                ]
            )
            if not is_studied:
                continue
            subject = str(task.get("materia", "") or "").strip()
            if not subject:
                continue
            task["_subject_norm"] = self._norm_coverage_text(subject)
            task["_lesson_norm"] = self._norm_lesson(str(task.get("aula", "") or ""))
            task["_task_id"] = f"{task.get('trilha', '')}:{task.get('row', len(studied) + 1)}"
            task["_group_id"] = self._coverage_group_id(task.get("trilha", ""), subject, task.get("aula", ""))
            studied.append(task)

        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT uid, source_code, subject, lesson, primary_topic, topics_text,
                       review_status, data_json
                FROM questions
                WHERE TRIM(COALESCE(subject, '')) != ''
                ORDER BY subject COLLATE NOCASE, lesson COLLATE NOCASE, source_code COLLATE NOCASE
                """
            ).fetchall()

        question_rows: list[dict] = []
        for row in rows:
            item = dict(row)
            try:
                payload = json.loads(str(item.pop("data_json") or "{}"))
            except Exception:
                payload = {}
            classification = payload.get("classificacao_planilha", {}) if isinstance(payload.get("classificacao_planilha"), dict) else {}
            source_topics = payload.get("assuntos_origem", [])
            if isinstance(source_topics, list):
                source_topics_text = " | ".join(str(value) for value in source_topics if str(value).strip())
            else:
                source_topics_text = str(source_topics or "")
            study_context = payload.get("contexto_importacao_estudos", {}) if isinstance(payload.get("contexto_importacao_estudos"), dict) else {}
            item.update(
                {
                    "taxonomy_reference": str(classification.get("referencia", "") or ""),
                    "study_group_id": str(
                        classification.get("contexto_group_id", "")
                        or study_context.get("group_id", "")
                        or ""
                    ),
                    "source_topics": source_topics_text,
                    "_subject_norm": self._norm_coverage_text(item.get("subject", "")),
                    "_lesson_norm": self._norm_lesson(item.get("lesson", "")),
                }
            )
            question_rows.append(item)

        stats: dict[str, dict] = {
            task["_task_id"]: {
                "question_count": 0,
                "approved_count": 0,
                "pending_count": 0,
                "question_codes": [],
            }
            for task in studied
        }
        unassigned_by_bucket: dict[tuple[str, str], int] = {}

        for question in question_rows:
            candidates = [
                task
                for task in studied
                if task["_subject_norm"] == question["_subject_norm"]
                and (not task["_lesson_norm"] or task["_lesson_norm"] == question["_lesson_norm"])
            ]
            if not candidates:
                continue
            selected: dict | None = None
            authoritative_group = str(question.get("study_group_id", "") or "").strip()
            if authoritative_group:
                grouped_candidates = [task for task in candidates if task.get("_group_id") == authoritative_group]
                if grouped_candidates:
                    # O PDF foi importado para a aula inteira. A questão precisa
                    # contar uma única vez dentro do grupo, mas não deve ser
                    # artificialmente vinculada a uma parte específica da aula.
                    # Para manter a cobertura detalhada compatível, usamos a parte
                    # semanticamente mais próxima; sem sinal suficiente, a primeira
                    # tarefa do grupo recebe apenas a contagem técnica.
                    scored = sorted(
                        ((self._task_question_similarity(task, question), task) for task in grouped_candidates),
                        key=lambda pair: (pair[0], -int(pair[1].get("row", 0) or 0)),
                        reverse=True,
                    )
                    selected = scored[0][1] if scored else grouped_candidates[0]
            if selected is None and len(candidates) == 1:
                selected = candidates[0]
            elif selected is None:
                scored = sorted(
                    ((self._task_question_similarity(task, question), task) for task in candidates),
                    key=lambda pair: (pair[0], -int(pair[1].get("row", 0) or 0)),
                    reverse=True,
                )
                best_score, best_task = scored[0]
                second_score = scored[1][0] if len(scored) > 1 else 0.0
                if best_score >= 1.0 or (best_score >= 0.18 and best_score - second_score >= 0.03):
                    selected = best_task

            if selected is None:
                bucket = (question["_subject_norm"], question["_lesson_norm"])
                unassigned_by_bucket[bucket] = unassigned_by_bucket.get(bucket, 0) + 1
                continue

            item_stats = stats[selected["_task_id"]]
            item_stats["question_count"] += 1
            if str(question.get("review_status", "")) == "pendente":
                item_stats["pending_count"] += 1
            else:
                item_stats["approved_count"] += 1
            code = str(question.get("source_code", "") or "").strip()
            if code and code not in item_stats["question_codes"]:
                item_stats["question_codes"].append(code)

        report: list[dict] = []
        for task in studied:
            task_stats = stats[task["_task_id"]]
            question_count = int(task_stats["question_count"] or 0)
            goal = max(0, int(task.get("meta_questoes", 0) or 0))
            if goal > 0:
                missing = max(0, goal - question_count)
                if missing == 0:
                    status = "coberto"
                elif question_count == 0:
                    status = "faltam_questoes"
                else:
                    status = "cobertura_parcial"
                missing_exact = True
            else:
                missing = None
                status = "sem_questoes" if question_count == 0 else "coberto_sem_meta"
                missing_exact = False

            lesson_norm = task["_lesson_norm"]
            bucket = (task["_subject_norm"], lesson_norm)
            topics = [str(value).strip() for value in task.get("segmentos", []) if str(value).strip()]
            content = " até ".join(topics[:2]) if topics else str(task.get("descricao", "") or "").strip()
            report.append(
                {
                    "task_id": task["_task_id"],
                    "row": int(task.get("row", 0) or 0),
                    "trilha": str(task.get("trilha", "") or ""),
                    "tarefa": str(task.get("tarefa", "") or ""),
                    "data": str(task.get("data", "") or ""),
                    "subject": str(task.get("materia", "") or ""),
                    "lesson": str(task.get("aula", "") or ""),
                    "content": content,
                    "description": str(task.get("descricao", "") or ""),
                    "task_type": str(task.get("tipo", "") or ""),
                    "effective_minutes": int(task.get("ch_efetiva_min", 0) or 0),
                    "effective_time": str(task.get("ch_efetiva", "") or ""),
                    "questions_done": int(task.get("questoes_feitas", 0) or 0),
                    "correct_answers": int(task.get("acertos", 0) or 0),
                    "performance": float(task.get("desempenho", 0) or 0),
                    "question_goal": goal,
                    "goal_source": str(task.get("meta_origem", "") or ""),
                    "bank_question_count": question_count,
                    "approved_count": int(task_stats["approved_count"] or 0),
                    "pending_count": int(task_stats["pending_count"] or 0),
                    "missing_question_count": missing,
                    "missing_exact": missing_exact,
                    "unassigned_lesson_count": int(unassigned_by_bucket.get(bucket, 0)),
                    "question_codes": task_stats["question_codes"][:50],
                    "status": status,
                    "needs_attention": status in {"faltam_questoes", "cobertura_parcial", "sem_questoes"},
                    "study_evidence": list(task.get("evidencias_estudo", []) or []),
                }
            )

        report.sort(
            key=lambda item: (
                int(item.get("needs_attention", False)) * -1,
                self._norm_coverage_text(item.get("subject", "")),
                self._norm_lesson(item.get("lesson", "")),
                int(item.get("row", 0) or 0),
            )
        )
        subjects = {self._norm_coverage_text(item.get("subject", "")) for item in report if item.get("subject")}
        summary = {
            "studied_contents": len(report),
            "studied_subjects": len(subjects),
            "contents_needing_questions": sum(1 for item in report if item["needs_attention"]),
            "contents_without_questions": sum(1 for item in report if item["status"] == "sem_questoes"),
            "partial_contents": sum(1 for item in report if item["status"] == "cobertura_parcial"),
            "covered_contents": sum(1 for item in report if item["status"] in {"coberto", "coberto_sem_meta"}),
            "known_missing_questions": sum(
                int(item["missing_question_count"] or 0)
                for item in report
                if item["missing_question_count"] is not None
            ),
            "unassigned_bank_questions": sum(unassigned_by_bucket.values()),
        }
        return {"items": report, "summary": summary}

    def studied_lesson_group_coverage(self, taxonomy_tasks: Iterable[dict]) -> dict:
        """Agrupa a cobertura por ``trilha + matéria + aula``.

        Uma aula pode aparecer em várias linhas do CICLO_REG (teoria parte 1,
        parte 2, revisão, resolução de questões). Para importar o PDF de questões,
        essas linhas representam uma única unidade prática: a aula. Este relatório
        soma a evidência de estudo e conta cada questão do banco apenas uma vez.
        """
        detailed = self.studied_content_coverage(taxonomy_tasks)
        groups: dict[str, dict] = {}

        for item in detailed.get("items", []):
            subject = str(item.get("subject", "") or "").strip()
            lesson = str(item.get("lesson", "") or "").strip()
            trail = str(item.get("trilha", "") or "").strip()
            # Sem aula identificada, não fundimos tarefas diferentes apenas por
            # matéria/trilha; isso evita juntar conteúdos heterogêneos.
            group_id = self._coverage_group_id(trail, subject, lesson) if lesson else f"task::{item.get('task_id', '')}"
            group = groups.setdefault(
                group_id,
                {
                    "group_id": group_id,
                    "task_ids": [],
                    "rows": [],
                    "tarefas": [],
                    "trilha": trail,
                    "subject": subject,
                    "lesson": lesson,
                    "content_parts": [],
                    "descriptions": [],
                    "effective_minutes": 0,
                    "questions_done": 0,
                    "correct_answers": 0,
                    "question_goal": 0,
                    "goal_known_count": 0,
                    "bank_question_count": 0,
                    "approved_count": 0,
                    "pending_count": 0,
                    "question_codes": [],
                    "study_evidence": [],
                },
            )
            task_id = str(item.get("task_id", "") or "")
            if task_id and task_id not in group["task_ids"]:
                group["task_ids"].append(task_id)
            row = int(item.get("row", 0) or 0)
            if row and row not in group["rows"]:
                group["rows"].append(row)
            tarefa = str(item.get("tarefa", "") or "").strip()
            if tarefa and tarefa not in group["tarefas"]:
                group["tarefas"].append(tarefa)
            content = str(item.get("content", "") or item.get("description", "") or "").strip()
            if content and content not in group["content_parts"]:
                group["content_parts"].append(content)
            description = str(item.get("description", "") or "").strip()
            if description and description not in group["descriptions"]:
                group["descriptions"].append(description)
            group["effective_minutes"] += int(item.get("effective_minutes", 0) or 0)
            group["questions_done"] += int(item.get("questions_done", 0) or 0)
            group["correct_answers"] += int(item.get("correct_answers", 0) or 0)
            goal = max(0, int(item.get("question_goal", 0) or 0))
            group["question_goal"] += goal
            if goal > 0:
                group["goal_known_count"] += 1
            group["bank_question_count"] += int(item.get("bank_question_count", 0) or 0)
            group["approved_count"] += int(item.get("approved_count", 0) or 0)
            group["pending_count"] += int(item.get("pending_count", 0) or 0)
            for code in item.get("question_codes", []) or []:
                code_text = str(code or "").strip()
                if code_text and code_text not in group["question_codes"]:
                    group["question_codes"].append(code_text)
            for evidence in item.get("study_evidence", []) or []:
                evidence_text = str(evidence or "").strip()
                if evidence_text and evidence_text not in group["study_evidence"]:
                    group["study_evidence"].append(evidence_text)

        report: list[dict] = []
        for group in groups.values():
            task_count = len(group["task_ids"])
            goal = int(group["question_goal"] or 0)
            bank_count = int(group["bank_question_count"] or 0)
            all_goals_known = task_count > 0 and int(group["goal_known_count"] or 0) == task_count
            if goal > 0:
                missing = max(0, goal - bank_count)
                if missing == 0:
                    status = "coberto" if all_goals_known else "coberto_sem_meta"
                elif bank_count == 0:
                    status = "faltam_questoes"
                else:
                    status = "cobertura_parcial"
                missing_exact = all_goals_known
            else:
                missing = None
                status = "sem_questoes" if bank_count == 0 else "coberto_sem_meta"
                missing_exact = False

            minutes = int(group["effective_minutes"] or 0)
            hours, remainder = divmod(minutes, 60)
            if hours and remainder:
                effective_time = f"{hours}h{remainder:02d}"
            elif hours:
                effective_time = f"{hours}h"
            elif remainder:
                effective_time = f"{remainder}min"
            else:
                effective_time = ""
            done = int(group["questions_done"] or 0)
            correct = int(group["correct_answers"] or 0)
            performance = round((correct / done) * 100.0, 2) if done > 0 else 0.0
            parts = list(group["content_parts"])
            if not parts:
                content = "Conteúdo da aula não informado"
            elif len(parts) == 1:
                content = parts[0]
            else:
                content = f"{len(parts)} conteúdos estudados nesta aula: " + " • ".join(parts)

            report.append(
                {
                    **group,
                    "task_count": task_count,
                    "content": content,
                    "description": " | ".join(group["descriptions"]),
                    "effective_time": effective_time,
                    "performance": performance,
                    "missing_question_count": missing,
                    "missing_exact": missing_exact,
                    "status": status,
                    "needs_attention": status in {"faltam_questoes", "cobertura_parcial", "sem_questoes"},
                    "question_codes": group["question_codes"][:100],
                }
            )

        report.sort(
            key=lambda item: (
                int(item.get("needs_attention", False)) * -1,
                self._norm_coverage_text(item.get("subject", "")),
                self._norm_lesson(item.get("lesson", "")),
                min(item.get("rows", [0]) or [0]),
            )
        )
        subjects = {self._norm_coverage_text(item.get("subject", "")) for item in report if item.get("subject")}
        summary = {
            "studied_contents": len(report),
            "studied_groups": len(report),
            "studied_tasks": len(detailed.get("items", [])),
            "studied_subjects": len(subjects),
            "contents_needing_questions": sum(1 for item in report if item["needs_attention"]),
            "contents_without_questions": sum(1 for item in report if item["status"] == "sem_questoes"),
            "partial_contents": sum(1 for item in report if item["status"] == "cobertura_parcial"),
            "covered_contents": sum(1 for item in report if item["status"] in {"coberto", "coberto_sem_meta"}),
            "known_missing_questions": sum(
                int(item["missing_question_count"] or 0)
                for item in report
                if item["missing_question_count"] is not None
            ),
            "unassigned_bank_questions": int(detailed.get("summary", {}).get("unassigned_bank_questions", 0) or 0),
        }
        return {"items": report, "summary": summary, "detailed": detailed}

    def lesson_coverage(self, taxonomy_tasks: Iterable[dict]) -> list[dict]:
        """Cruza aulas da planilha com banco, envios e respostas do Telegram."""
        planned: dict[tuple[str, str], dict] = {}
        for task in taxonomy_tasks or []:
            subject = str(task.get("materia", "") or "").strip()
            lesson = str(task.get("aula", "") or "").strip()
            if not subject or not lesson:
                continue
            key = (self._norm_coverage_text(subject), self._norm_lesson(lesson))
            item = planned.setdefault(
                key,
                {
                    "subject": subject,
                    "lesson": lesson,
                    "task_count": 0,
                    "topics": [],
                },
            )
            item["task_count"] += 1
            description = str(task.get("descricao", "") or "").strip()
            segments = [str(part).strip() for part in task.get("segmentos", []) if str(part).strip()]
            for value in segments or ([description] if description else []):
                if value and value not in item["topics"]:
                    item["topics"].append(value)

        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT q.uid, q.subject, q.lesson, q.review_status,
                       COALESCE(ds.delivery_count, 0) AS delivery_count,
                       ds.last_sent_at,
                       COALESCE(ast.answer_count, 0) AS answer_count
                FROM questions q
                LEFT JOIN (
                    SELECT question_uid,
                           COUNT(*) AS delivery_count,
                           MAX(sent_at) AS last_sent_at
                    FROM telegram_deliveries
                    WHERE status IN ('enviado', 'reenviado', 'reenviado_sem_resposta')
                       OR resolved_by_delivery_id IS NOT NULL
                    GROUP BY question_uid
                ) ds ON ds.question_uid = q.uid
                LEFT JOIN (
                    SELECT question_uid, COUNT(*) AS answer_count
                    FROM telegram_attempts
                    GROUP BY question_uid
                ) ast ON ast.question_uid = q.uid
                """
            ).fetchall()

        observed: dict[tuple[str, str], dict] = {}
        for row in rows:
            key = (self._norm_coverage_text(row["subject"]), self._norm_lesson(row["lesson"]))
            if not key[0] or not key[1]:
                continue
            item = observed.setdefault(
                key,
                {
                    "question_count": 0,
                    "approved_count": 0,
                    "pending_count": 0,
                    "sent_question_count": 0,
                    "delivery_count": 0,
                    "answered_question_count": 0,
                    "last_sent_at": "",
                },
            )
            item["question_count"] += 1
            if str(row["review_status"]) == "pendente":
                item["pending_count"] += 1
            else:
                item["approved_count"] += 1
            deliveries = int(row["delivery_count"] or 0)
            answers = int(row["answer_count"] or 0)
            if deliveries:
                item["sent_question_count"] += 1
                item["delivery_count"] += deliveries
            if answers:
                item["answered_question_count"] += 1
            sent_at = str(row["last_sent_at"] or "")
            if sent_at and sent_at > item["last_sent_at"]:
                item["last_sent_at"] = sent_at

        report: list[dict] = []
        for key, planned_item in planned.items():
            stats = observed.get(key, {})
            question_count = int(stats.get("question_count", 0))
            sent_count = int(stats.get("sent_question_count", 0))
            if question_count == 0:
                status = "sem_questoes"
            elif sent_count == 0:
                status = "com_questoes_nao_enviadas"
            elif sent_count < question_count:
                status = "envio_parcial"
            else:
                status = "todas_enviadas"
            report.append(
                {
                    **planned_item,
                    "question_count": question_count,
                    "approved_count": int(stats.get("approved_count", 0)),
                    "pending_count": int(stats.get("pending_count", 0)),
                    "sent_question_count": sent_count,
                    "delivery_count": int(stats.get("delivery_count", 0)),
                    "answered_question_count": int(stats.get("answered_question_count", 0)),
                    "last_sent_at": str(stats.get("last_sent_at", "")),
                    "status": status,
                    "topics_text": " | ".join(planned_item.get("topics", [])[:8]),
                }
            )
        report.sort(key=lambda item: (self._norm_coverage_text(item["subject"]), self._norm_lesson(item["lesson"])))
        return report

    def record_delivery_error(
        self,
        question_uid: str,
        chat_id: str,
        error: str,
        cycle_id: str,
        *,
        category: str = "desconhecido",
        retryable: bool = False,
        next_retry_at: str | None = None,
        attempt_count: int = 1,
        parent_delivery_id: str | None = None,
    ) -> str:
        delivery_id = str(uuid.uuid4())
        now = utc_now()
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO telegram_deliveries(
                    id, cycle_id, question_uid, chat_id, sent_at, status, error_text,
                    error_category, is_retryable, next_retry_at, attempt_count,
                    last_attempt_at, parent_delivery_id
                ) VALUES (?, ?, ?, ?, ?, 'erro', ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    delivery_id,
                    cycle_id,
                    question_uid,
                    str(chat_id),
                    now,
                    str(error)[:2000],
                    str(category)[:120],
                    1 if retryable else 0,
                    next_retry_at,
                    max(1, int(attempt_count)),
                    now,
                    parent_delivery_id,
                ),
            )
            if parent_delivery_id:
                connection.execute(
                    """
                    UPDATE telegram_deliveries
                    SET attempt_count = MAX(attempt_count, ?), last_attempt_at = ?,
                        error_text = ?, error_category = ?, is_retryable = ?, next_retry_at = ?
                    WHERE id = ?
                    """,
                    (
                        max(1, int(attempt_count)),
                        now,
                        str(error)[:2000],
                        str(category)[:120],
                        1 if retryable else 0,
                        next_retry_at,
                        parent_delivery_id,
                    ),
                )
        return delivery_id

    def get_delivery(self, delivery_id: str) -> dict | None:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT d.*, q.data_json, q.source_code, q.subject, q.primary_topic
                FROM telegram_deliveries d
                JOIN questions q ON q.uid = d.question_uid
                WHERE d.id = ?
                """,
                (str(delivery_id),),
            ).fetchone()
        if not row:
            return None
        item = dict(row)
        item["question"] = json.loads(item.pop("data_json"))
        return item

    def failed_deliveries(self, limit: int = 100, *, due_only: bool = False) -> list[dict]:
        where = "d.status = 'erro' AND d.resolved_by_delivery_id IS NULL"
        values: list = []
        if due_only:
            where += " AND d.is_retryable = 1 AND (d.next_retry_at IS NULL OR d.next_retry_at <= ?) AND COALESCE(s.suspended, 0) = 0"
            values.append(utc_now())
        values.append(max(1, int(limit)))
        with self.database.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT d.id, d.cycle_id, d.question_uid, d.chat_id, d.sent_at, d.status,
                       d.error_text, d.error_category, d.is_retryable, d.next_retry_at,
                       d.attempt_count, d.last_attempt_at, d.parent_delivery_id,
                       q.source_code, q.subject, q.primary_topic, q.statement
                FROM telegram_deliveries d
                JOIN questions q ON q.uid = d.question_uid
                JOIN study_state s ON s.question_uid = d.question_uid
                WHERE {where}
                ORDER BY COALESCE(d.next_retry_at, d.sent_at) ASC
                LIMIT ?
                """,
                values,
            ).fetchall()
        return [dict(row) for row in rows]

    def schedule_retry(self, delivery_id: str, next_retry_at: str, *, retryable: bool = True) -> None:
        with self.database.connect() as connection:
            connection.execute(
                """
                UPDATE telegram_deliveries
                SET next_retry_at = ?, is_retryable = ?, status = 'erro'
                WHERE id = ? AND resolved_by_delivery_id IS NULL
                """,
                (next_retry_at, 1 if retryable else 0, str(delivery_id)),
            )

    def mark_retry_started(self, delivery_id: str) -> int:
        now = utc_now()
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT attempt_count FROM telegram_deliveries WHERE id = ?",
                (str(delivery_id),),
            ).fetchone()
            attempt = int(row[0] if row else 0) + 1
            connection.execute(
                """
                UPDATE telegram_deliveries
                SET status = 'reenviando', attempt_count = ?, last_attempt_at = ?, next_retry_at = NULL
                WHERE id = ?
                """,
                (attempt, now, str(delivery_id)),
            )
        return attempt

    def restore_retry_error(
        self,
        delivery_id: str,
        error: str,
        *,
        category: str,
        retryable: bool,
        next_retry_at: str | None,
    ) -> None:
        with self.database.connect() as connection:
            connection.execute(
                """
                UPDATE telegram_deliveries
                SET status = 'erro', error_text = ?, error_category = ?, is_retryable = ?,
                    next_retry_at = ?, last_attempt_at = ?
                WHERE id = ?
                """,
                (
                    str(error)[:2000],
                    str(category)[:120],
                    1 if retryable else 0,
                    next_retry_at,
                    utc_now(),
                    str(delivery_id),
                ),
            )

    def _recompute_question_state(
        self,
        connection: sqlite3.Connection,
        question_uid: str,
        *,
        train_model: bool = True,
        event_key: str | None = None,
    ) -> dict:
        rows = connection.execute(
            """
            SELECT a.id AS attempt_id, a.is_correct, a.answered_at, a.confidence, a.error_type,
                   a.fsrs_rating, a.fsrs_review_log_json, a.response_seconds, a.timing_quality,
                   a.timing_source, d.sent_at
            FROM telegram_attempts a
            LEFT JOIN telegram_deliveries d ON d.id = a.delivery_id
            WHERE a.question_uid = ?
            ORDER BY a.answered_at DESC
            """,
            (question_uid,),
        ).fetchall()
        correct = sum(1 for row in rows if row["is_correct"])
        wrong = len(rows) - correct
        streak = 0
        for row in rows:
            if row["is_correct"]:
                streak += 1
            else:
                break

        state_row = connection.execute(
            """
            SELECT s.*, q.review_status, q.subject, q.primary_topic, q.lesson
            FROM study_state s JOIN questions q ON q.uid = s.question_uid
            WHERE s.question_uid = ?
            """,
            (question_uid,),
        ).fetchone()
        latest = rows[0] if rows else None
        if not latest or not state_row:
            return {"correct_count": correct, "wrong_count": wrong, "streak": streak, "due_at": None, "last_answered_at": None}

        target_retention = self.effective_target_retention(connection)

        answered_dt = _parse_iso(latest["answered_at"]) or utc_now_dt()
        previous_dt = _parse_iso(rows[1]["answered_at"]) if len(rows) > 1 else _parse_iso(state_row["last_answered_at"])
        if previous_dt and previous_dt >= answered_dt:
            previous_dt = None
        elapsed_days = 0.0 if previous_dt is None else max(0.0, (answered_dt - previous_dt).total_seconds() / 86400.0)
        timing_quality = str(latest["timing_quality"] or "legacy_unverified")
        timing_eligible = timing_quality in {"valid", "active_filtered"}
        stored_response = latest["response_seconds"]
        response_seconds = (
            max(0.0, float(stored_response))
            if timing_eligible and stored_response is not None
            else 0.0
        )

        memory = MemoryState.from_mapping({
            "difficulty": state_row["memory_difficulty"], "stability_days": state_row["memory_stability"],
            "retrievability": state_row["memory_retrievability"], "response_time_ema": state_row["response_time_ema"],
            "review_count": max(0, len(rows) - 1),
        })
        prior_correct = correct - (1 if latest["is_correct"] else 0)
        prior_wrong = wrong - (0 if latest["is_correct"] else 1)
        prior_accuracy = (prior_correct + 1.0) / (prior_correct + prior_wrong + 2.0)
        model = self._load_adaptive_model(connection)
        model_response_seconds = response_seconds if timing_eligible else (memory.response_time_ema if memory.response_time_ema > 0 else 45.0)
        features = model.features(
            state=memory, elapsed_days=elapsed_days, historical_accuracy=prior_accuracy,
            response_seconds=model_response_seconds, is_new=(prior_correct + prior_wrong) == 0,
            autoapproved=str(state_row["review_status"] or "").lower() != "aprovado",
        )
        prediction_before = model.predict(features)
        current_params = self.fsrs_parameters(connection)
        fsrs_prediction_before = current_retrievability(
            state_row["fsrs_card_json"] if "fsrs_card_json" in state_row.keys() else None,
            desired_retention=target_retention, parameters=current_params, now=answered_dt,
        )
        ability_before = connection.execute(
            "SELECT theta, standard_error, attempt_count FROM learner_ability WHERE subject = ?",
            (str(state_row["subject"] or "Matéria não informada"),),
        ).fetchone()
        item_before = connection.execute(
            "SELECT difficulty, discrimination, attempt_count FROM question_irt WHERE question_uid = ?",
            (str(question_uid),),
        ).fetchone()
        learner_prediction = predict_success_selective(
            mastery=None if state_row["kt_mastery"] is None else float(state_row["kt_mastery"]),
            mastery_confidence_value=float(state_row["kt_confidence"] or 0.0),
            retrievability=fsrs_prediction_before,
            fsrs_reviews=prior_correct + prior_wrong,
            theta=None if ability_before is None else float(ability_before["theta"] or 0.0),
            difficulty=None if item_before is None else float(item_before["difficulty"] or 0.0),
            discrimination=None if item_before is None else float(item_before["discrimination"] or 1.0),
            ability_standard_error=None if ability_before is None else float(ability_before["standard_error"] or 2.5),
            ability_attempts=0 if ability_before is None else int(ability_before["attempt_count"] or 0),
            item_attempts=0 if item_before is None else int(item_before["attempt_count"] or 0),
            historical_accuracy=prior_accuracy,
            history_attempts=prior_correct + prior_wrong,
        )
        if latest["attempt_id"]:
            connection.execute(
                """UPDATE telegram_attempts SET predicted_probability = ?, fsrs_predicted_probability = ?,
                       learner_predicted_probability = ?, learner_prediction_confidence = ?,
                       learner_prediction_low = ?, learner_prediction_high = ?, learner_prediction_status = ?,
                       learner_prediction_reason = ?, learner_prediction_version = ?,
                       prediction_model_version = ? WHERE id = ?""",
                (prediction_before, fsrs_prediction_before, learner_prediction.probability,
                 learner_prediction.confidence, learner_prediction.interval_low, learner_prediction.interval_high,
                 learner_prediction.status, json.dumps(list(learner_prediction.reasons), ensure_ascii=False),
                 learner_prediction.version, model.version, latest["attempt_id"]),
            )
        if train_model:
            model.update(features, bool(latest["is_correct"]))
            self._save_adaptive_model(connection, model)

        # DSR é mantido apenas como continuidade de emergência. Em uma instalação
        # saudável o resultado abaixo é imediatamente substituído pelo Py-FSRS.
        next_memory, interval_days = update_memory_state(
            memory, correct=bool(latest["is_correct"]), elapsed_days=elapsed_days,
            response_seconds=response_seconds if timing_eligible else None, target_retention=target_retention,
        )
        due_at = (answered_dt + timedelta(days=interval_days)).isoformat()
        prefs = self.learning_preferences()
        maximum_interval = int(prefs.get("maximum_interval_days", DEFAULT_MAXIMUM_INTERVAL) or DEFAULT_MAXIMUM_INTERVAL)
        exam_cap = self._exam_due_cap(answered_dt)
        if exam_cap is not None:
            days_to_exam = max(1, int((exam_cap - answered_dt).total_seconds() // 86400) + 1)
            maximum_interval = min(maximum_interval, days_to_exam)
        relearning_minutes = int(prefs.get("relearning_minutes", 10) or 10)
        fsrs_result = review_with_fsrs(
            state_row["fsrs_card_json"] if "fsrs_card_json" in state_row.keys() else None,
            correct=bool(latest["is_correct"]), response_seconds=response_seconds if timing_eligible else 0.0,
            prior_accuracy=prior_accuracy, prior_attempts=prior_correct + prior_wrong,
            desired_retention=target_retention, now=answered_dt,
            confidence=str(latest["confidence"] or ""), parameters=current_params,
            relearning_steps_minutes=(relearning_minutes,), maximum_interval=maximum_interval,
            due_cap=exam_cap,
        )
        fsrs_state = "relearning" if not bool(latest["is_correct"]) else "review"
        fsrs_lapses = int(state_row["fsrs_lapses"] or 0) + (0 if latest["is_correct"] else 1)
        if fsrs_result is not None:
            due_at = fsrs_result.due_at
            fsrs_state = fsrs_result.scheduler_state
            next_memory = MemoryState(
                difficulty=fsrs_result.difficulty, stability_days=fsrs_result.stability,
                retrievability=fsrs_result.retrievability,
                response_time_ema=next_memory.response_time_ema, review_count=next_memory.review_count,
            )
            connection.execute(
                "UPDATE telegram_attempts SET fsrs_rating = ?, fsrs_review_log_json = ? WHERE id = ?",
                (fsrs_result.rating, fsrs_result.review_log_json, latest["attempt_id"]),
            )

        ease_delta = 0.04 if latest["is_correct"] else -0.18
        adaptive_priority = adaptive_priority_score(
            predicted_recall=prediction_before, retrievability=next_memory.retrievability,
            overdue_days=0.0, is_new=False, sent_count=int(state_row["sent_count"] or 0),
            correction_priority=bool(state_row["correction_priority"]), review_status=str(state_row["review_status"] or ""),
        )
        connection.execute(
            """
            UPDATE study_state
            SET correct_count = ?, wrong_count = ?, streak = ?, last_answered_at = ?, due_at = ?,
                ease = MIN(3.2, MAX(1.3, ease + ?)), memory_difficulty = ?, memory_stability = ?,
                memory_retrievability = ?, response_time_ema = ?, adaptive_prediction = ?, adaptive_priority = ?,
                adaptive_model_version = ?, fsrs_card_json = ?, fsrs_due_at = ?, fsrs_rating = ?, fsrs_version = ?,
                fsrs_state = ?, fsrs_lapses = ?
            WHERE question_uid = ?
            """,
            (
                correct, wrong, streak, latest["answered_at"], due_at, ease_delta,
                next_memory.difficulty, next_memory.stability_days, next_memory.retrievability,
                next_memory.response_time_ema, prediction_before, adaptive_priority, model.version,
                fsrs_result.card_json if fsrs_result is not None else state_row["fsrs_card_json"],
                fsrs_result.due_at if fsrs_result is not None else None,
                fsrs_result.rating if fsrs_result is not None else None,
                fsrs_result.scheduler_version if fsrs_result is not None else state_row["fsrs_version"],
                fsrs_state, fsrs_lapses, question_uid,
            ),
        )

        subject = str(state_row["subject"] or "SEM MATÉRIA").strip() or "SEM MATÉRIA"
        lesson = str(state_row["lesson"] or "SEM AULA").strip() or "SEM AULA"
        topic = str(state_row["primary_topic"] or lesson or "SEM ASSUNTO").strip() or "SEM ASSUNTO"
        topic_correct = 1 if latest["is_correct"] else 0
        topic_wrong = 0 if latest["is_correct"] else 1
        topic_score_value = topic_priority(
            TopicState(subject=subject, topic=topic, correct=correct, wrong=wrong, exposures=max(1, len(rows)), last_seen_days=0.0),
            total_exposures=max(1, len(rows)), predicted_recall=prediction_before,
        )
        connection.execute(
            """
            INSERT INTO topic_learning_state(subject, topic, correct_count, wrong_count, exposure_count, last_seen_at, last_score, updated_at)
            VALUES (?, ?, ?, ?, 1, ?, ?, ?)
            ON CONFLICT(subject, topic) DO UPDATE SET
                correct_count = correct_count + excluded.correct_count,
                wrong_count = wrong_count + excluded.wrong_count,
                exposure_count = exposure_count + 1, last_seen_at = excluded.last_seen_at,
                last_score = excluded.last_score, updated_at = excluded.updated_at
            """,
            (subject, topic, topic_correct, topic_wrong, latest["answered_at"], topic_score_value, utc_now()),
        )
        lesson_score_value = topic_priority(
            TopicState(subject=subject, topic=lesson, correct=correct, wrong=wrong, exposures=max(1, len(rows)), last_seen_days=0.0),
            total_exposures=max(1, len(rows)), predicted_recall=prediction_before,
        )
        connection.execute(
            """
            INSERT INTO lesson_learning_state(subject, lesson, correct_count, wrong_count, exposure_count, last_seen_at, last_score, updated_at)
            VALUES (?, ?, ?, ?, 1, ?, ?, ?)
            ON CONFLICT(subject, lesson) DO UPDATE SET
                correct_count = correct_count + excluded.correct_count,
                wrong_count = wrong_count + excluded.wrong_count,
                exposure_count = exposure_count + 1, last_seen_at = excluded.last_seen_at,
                last_score = excluded.last_score, updated_at = excluded.updated_at
            """,
            (subject, lesson, topic_correct, topic_wrong, latest["answered_at"], lesson_score_value, utc_now()),
        )

        reward = None
        learner_update = None
        if train_model and event_key:
            reward = self._award_xp(
                connection, event_id=event_key, question_uid=question_uid, correct=bool(latest["is_correct"]),
                difficulty=next_memory.difficulty, response_seconds=response_seconds if timing_eligible else 0.0, streak=streak,
                first_attempt=(prior_correct + prior_wrong) == 0,
            )
            learner_update = self._update_learner_model_event(
                connection, attempt_id=str(event_key), question_uid=question_uid,
                correct=bool(latest["is_correct"]), answered_at=str(latest["answered_at"] or utc_now()),
            )
        return {
            "correct_count": correct, "wrong_count": wrong, "streak": streak, "due_at": due_at,
            "last_answered_at": latest["answered_at"],
            "response_seconds": round(response_seconds, 2) if timing_eligible else None,
            "timing_quality": timing_quality,
            "memory_difficulty": round(next_memory.difficulty, 4), "memory_stability": round(next_memory.stability_days, 4),
            "predicted_recall": round(prediction_before, 4), "target_retention": target_retention,
            "model_samples": model.samples, "scheduler": "fsrs" if fsrs_result is not None else "dsr_fallback",
            "fsrs_version": fsrs_result.scheduler_version if fsrs_result is not None else None,
            "fsrs_state": fsrs_state, "fsrs_rating": fsrs_result.rating if fsrs_result is not None else None,
            "confidence": str(latest["confidence"] or ""), "error_type": str(latest["error_type"] or ""),
            "learner_prediction": {
                "probability": learner_prediction.probability, "confidence": learner_prediction.confidence,
                "low": learner_prediction.interval_low, "high": learner_prediction.interval_high,
                "status": learner_prediction.status, "abstain": learner_prediction.abstain,
                "reasons": list(learner_prediction.reasons), "version": learner_prediction.version,
            },
            "reward": reward, "learner_model": learner_update,
        }

    def record_attempt_meta(
        self,
        attempt_id: str,
        *,
        confidence: str | None = None,
        error_type: str | None = None,
        perceived_difficulty: str | None = None,
        learning_gap: bool | int | None = None,
    ) -> dict:
        """Registra metacognição sem substituir a evidência objetiva da resposta.

        Confiança altera o rating FSRS retrospectivamente; dificuldade percebida
        e lacuna de estudo alimentam Learning Analytics/priorização, mas não
        falsificam o acerto/erro nem criam uma revisão adicional.
        """
        confidence_map = {"sabia": "sabia", "duvida": "duvida", "dúvida": "duvida", "chutei": "chutei"}
        error_map = {"nao_sabia": "nao_sabia", "não_sabia": "nao_sabia", "confundi": "confundi", "desatencao": "desatencao", "desatenção": "desatencao"}
        difficulty_map = {
            "facil": "facil", "fácil": "facil", "easy": "facil",
            "media": "media", "média": "media", "medio": "media", "médio": "media", "medium": "media",
            "dificil": "dificil", "difícil": "dificil", "hard": "dificil",
        }
        with self.database.connect() as connection:
            row = connection.execute("SELECT question_uid FROM telegram_attempts WHERE id = ?", (str(attempt_id),)).fetchone()
            if not row:
                return {"ok": False, "error": "Tentativa não encontrada."}
            fields, values = [], []
            if confidence is not None:
                value = confidence_map.get(str(confidence).strip().casefold())
                if value:
                    fields.append("confidence = ?"); values.append(value)
            if error_type is not None:
                value = error_map.get(str(error_type).strip().casefold())
                if value:
                    fields.append("error_type = ?"); values.append(value)
            if perceived_difficulty is not None:
                value = difficulty_map.get(str(perceived_difficulty).strip().casefold())
                if value:
                    fields.append("perceived_difficulty = ?"); values.append(value)
            if learning_gap is not None:
                gap = 1 if bool(learning_gap) else 0
                fields.append("learning_gap = ?"); values.append(gap)
            if fields:
                fields.append("meta_updated_at = ?"); values.append(utc_now())
                values.append(str(attempt_id))
                connection.execute(f"UPDATE telegram_attempts SET {', '.join(fields)} WHERE id = ?", values)
            question_uid = str(row["question_uid"])
            self._refresh_subject_daily_for_attempt(connection, str(attempt_id))
        state = self.rebuild_question_fsrs(question_uid) if confidence is not None else {"ok": True}
        return {
            "ok": True, "attempt_id": str(attempt_id), "question_uid": question_uid, "state": state,
            "confidence": confidence, "error_type": error_type,
            "perceived_difficulty": perceived_difficulty, "learning_gap": learning_gap,
        }

    def relearning_due_questions(self, *, limit: int = 6) -> list[dict]:
        """Retorna somente recuperações pós-erro efetivamente vencidas."""
        now = utc_now()
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT q.uid, q.data_json, q.subject, q.primary_topic, q.lesson, q.review_status,
                       s.sent_count, s.correct_count, s.wrong_count, s.streak, s.last_sent_at,
                       s.last_answered_at, s.due_at, s.memory_difficulty, s.memory_stability,
                       s.memory_retrievability, s.response_time_ema, s.adaptive_prediction, s.adaptive_priority
                FROM study_state s JOIN questions q ON q.uid = s.question_uid
                WHERE COALESCE(s.suspended, 0) = 0 AND s.fsrs_state = 'relearning'
                  AND s.due_at IS NOT NULL AND s.due_at <= ?
                  AND NOT EXISTS (
                      SELECT 1 FROM telegram_deliveries d
                      WHERE d.question_uid = q.uid AND d.status = 'enviado'
                        AND NOT EXISTS (SELECT 1 FROM telegram_attempts a WHERE a.delivery_id = d.id)
                  )
                ORDER BY s.due_at ASC, s.wrong_count DESC
                LIMIT ?
                """,
                (now, max(1, int(limit))),
            ).fetchall()
        result=[]
        for row in rows:
            q=self._row_to_question(row); q["selection_reason"]="Recuperação pós-erro vencida"; q["selection_bucket"]=1; result.append(q)
        return result

    def record_poll_answer(self, poll_answer: dict) -> dict | None:
        poll_id = str(poll_answer.get("poll_id", "") or "")
        selected = poll_answer.get("option_ids", [])
        if not poll_id or not isinstance(selected, list) or not selected:
            return None
        user = poll_answer.get("user") or {}
        voter_chat = poll_answer.get("voter_chat") or {}
        user_id = str(user.get("id") or voter_chat.get("id") or "desconhecido")
        username = str(user.get("username") or user.get("first_name") or voter_chat.get("title") or "")
        answered_at = utc_now()

        with self.database.connect() as connection:
            delivery = connection.execute(
                """
                SELECT d.id, d.question_uid, d.chat_id, d.message_id, q.data_json
                FROM telegram_deliveries d JOIN questions q ON q.uid = d.question_uid
                WHERE d.poll_id = ?
                """,
                (poll_id,),
            ).fetchone()
            if not delivery:
                return None
            question = json.loads(delivery["data_json"])
            correct_index = _answer_index(question)
            if correct_index is None:
                return None
            selected_indices = [int(item) for item in selected]
            is_correct = 1 if correct_index in selected_indices else 0
            existing = connection.execute(
                "SELECT id, feedback_sent_at, feedback_message_id FROM telegram_attempts WHERE delivery_id = ? AND user_id = ?",
                (delivery["id"], user_id),
            ).fetchone()
            if existing:
                connection.execute(
                    """
                    UPDATE telegram_attempts
                    SET selected_indices_json = ?, is_correct = ?, answered_at = ?, username = ?
                    WHERE id = ?
                    """,
                    (json.dumps(selected_indices), is_correct, answered_at, username, existing["id"]),
                )
                attempt_id = existing["id"]
            else:
                attempt_id = str(uuid.uuid4())
                connection.execute(
                    """
                    INSERT INTO telegram_attempts(
                        id, delivery_id, question_uid, poll_id, user_id, username,
                        selected_indices_json, is_correct, answered_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        attempt_id,
                        delivery["id"],
                        delivery["question_uid"],
                        poll_id,
                        user_id,
                        username,
                        json.dumps(selected_indices),
                        is_correct,
                        answered_at,
                    ),
                )
            state = self._recompute_question_state(
                connection,
                delivery["question_uid"],
                train_model=not bool(existing),
                event_key=attempt_id if not existing else None,
            )
            self._refresh_subject_daily_for_attempt(connection, str(attempt_id))
        return {
            "attempt_id": attempt_id,
            "question_uid": delivery["question_uid"],
            "poll_id": poll_id,
            "user_id": user_id,
            "username": username,
            "selected_indices": selected_indices,
            "correct_index": correct_index,
            "is_correct": bool(is_correct),
            "state": state,
            "question": question,
            "chat_id": str(delivery["chat_id"] or ""),
            "message_id": delivery["message_id"],
            "feedback_already_sent": bool(existing and existing["feedback_sent_at"]),
        }

    def record_local_practice_attempt(
        self,
        question_uid: str,
        selected_index: int,
        *,
        session_id: str = "",
        confidence: str = "",
        response_seconds: float | None = None,
        perceived_difficulty: str = "",
        learning_gap: bool | None = None,
        source: str = "simulado_adaptativo",
        attempt_id_override: str = "",
        correct_index_override: int | None = None,
        timing_meta: dict | None = None,
        question_revision: int = 1,
        exam_project_id: str = "",
        device_id: str = "",
        account_id: str = "",
        tenant_id: str = "",
        learner_id: str = "",
        defer_projections: bool = False,
    ) -> dict:
        """Registra uma tentativa local usando o mesmo FSRS/KT/IRT do Telegram.

        O nome legado das tabelas ``telegram_*`` é preservado por compatibilidade,
        mas a coluna ``source`` distingue tentativas locais. Entregas locais não
        aparecem no histórico operacional do Telegram.
        """
        uid = str(question_uid or "").strip()
        if not uid:
            raise ValueError("Questão não informada.")
        now = utc_now()
        attempt_id = str(attempt_id_override or uuid.uuid4())
        delivery_id = str(uuid.uuid4())
        poll_id = f"local:{str(session_id or 'practice')}:{attempt_id}"
        clean_source = str(source or "local").strip() or "local"
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT data_json FROM questions WHERE uid = ?", (uid,)
            ).fetchone()
            if not row:
                raise ValueError("Questão não encontrada.")
            question = json.loads(row["data_json"])
            correct_index = int(correct_index_override) if correct_index_override is not None else _answer_index(question)
            if correct_index is None:
                raise ValueError("A questão não possui gabarito utilizável.")
            alternatives = question.get("alternativas", []) if isinstance(question.get("alternativas"), list) else []
            selected = int(selected_index)
            if selected < 0 or (correct_index_override is None and selected >= max(1, len(alternatives))):
                raise ValueError("Alternativa selecionada é inválida.")
            is_correct = 1 if selected == int(correct_index) else 0

            duplicate = connection.execute("SELECT id FROM telegram_attempts WHERE id = ?", (attempt_id,)).fetchone()
            if duplicate:
                existing_state = connection.execute("SELECT * FROM study_state WHERE question_uid = ?", (uid,)).fetchone()
                return {
                    "attempt_id": attempt_id, "delivery_id": "", "question_uid": uid,
                    "selected_index": selected, "correct_index": int(correct_index),
                    "is_correct": bool(is_correct), "state": dict(existing_state) if existing_state else {},
                    "question": question, "source": clean_source, "duplicate": True,
                }

            connection.execute(
                """
                INSERT INTO telegram_deliveries(
                    id, cycle_id, question_uid, poll_id, chat_id, message_id, sent_at,
                    direct_poll, status, attempt_count, last_attempt_at, source
                ) VALUES (?, ?, ?, ?, 'local', NULL, ?, 0, 'simulado_local', 1, ?, ?)
                """,
                (delivery_id, str(session_id or "local_practice"), uid, poll_id, now, now, clean_source),
            )
            connection.execute(
                """
                UPDATE study_state
                SET sent_count = sent_count + 1, last_sent_at = ?, correction_priority = 0
                WHERE question_uid = ?
                """,
                (now, uid),
            )
            connection.execute(
                """
                INSERT INTO telegram_attempts(
                    id, delivery_id, question_uid, poll_id, user_id, username,
                    selected_indices_json, is_correct, answered_at, confidence,
                    perceived_difficulty, learning_gap, response_seconds, meta_updated_at, source,
                    account_id, tenant_id, learner_id, exam_project_id, device_id, session_id,
                    question_revision, response_wall_seconds, response_idle_seconds, timing_quality, timing_source
                ) VALUES (?, ?, ?, ?, ?, 'QuestFlow local', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    attempt_id, delivery_id, uid, poll_id, str(learner_id or 'local-user'),
                    json.dumps([selected]), is_correct, now,
                    str(confidence or "") or None, str(perceived_difficulty or "") or None,
                    None if learning_gap is None else (1 if learning_gap else 0),
                    None if response_seconds is None else max(0.0, float(response_seconds)),
                    now, clean_source, str(account_id or '') or None, str(tenant_id or '') or None,
                    str(learner_id or '') or None, str(exam_project_id or '') or None, str(device_id or '') or None,
                    str(session_id or '') or None, max(1, int(question_revision or 1)),
                    None if not timing_meta or timing_meta.get('wall_seconds') is None else max(0.0, float(timing_meta.get('wall_seconds'))),
                    None if not timing_meta or timing_meta.get('idle_seconds') is None else max(0.0, float(timing_meta.get('idle_seconds'))),
                    str((timing_meta or {}).get('quality') or ('valid' if response_seconds is not None and timing_meta else 'legacy_unverified')),
                    str((timing_meta or {}).get('source') or ('active_timer' if timing_meta else 'legacy_unverified')),
                ),
            )
            if defer_projections:
                state_row = connection.execute(
                    "SELECT * FROM study_state WHERE question_uid = ?", (uid,)
                ).fetchone()
                state = dict(state_row) if state_row else {}
            else:
                state = self.project_local_practice_attempt(
                    connection, attempt_id, question_uid=uid
                )["state"]
        return {
            "attempt_id": attempt_id, "delivery_id": delivery_id, "question_uid": uid,
            "selected_index": selected, "correct_index": int(correct_index),
            "is_correct": bool(is_correct), "state": state, "question": question,
            "source": clean_source, "projection_pending": bool(defer_projections),
        }

    def project_local_practice_attempt(
        self,
        connection: sqlite3.Connection,
        attempt_id: str,
        *,
        question_uid: str = "",
    ) -> dict:
        """Materializa FSRS/KT/IRT e analytics de uma tentativa já persistida.

        O chamador controla a transação para que a projeção e o checkpoint do
        evento sejam confirmados juntos. Isso permite ao Mobile receber o
        gabarito logo após a gravação canônica da tentativa sem perder a
        capacidade de retomar a projeção após encerramento inesperado.
        """
        attempt_key = str(attempt_id or "").strip()
        if not attempt_key:
            raise ValueError("Tentativa não informada para projeção.")
        uid = str(question_uid or "").strip()
        if not uid:
            row = connection.execute(
                "SELECT question_uid FROM telegram_attempts WHERE id = ?", (attempt_key,)
            ).fetchone()
            if not row:
                raise ValueError("Tentativa não encontrada para projeção.")
            uid = str(row["question_uid"] or "")
        state = self._recompute_question_state(
            connection, uid, train_model=True, event_key=attempt_key
        )
        self._refresh_subject_daily_for_attempt(connection, attempt_key)
        return {"ok": True, "attempt_id": attempt_key, "question_uid": uid, "state": state}

    def mark_attempt_feedback_sent(self, attempt_id: str, message_id: int | None = None) -> None:
        with self.database.connect() as connection:
            connection.execute(
                """
                UPDATE telegram_attempts
                SET feedback_sent_at = ?, feedback_message_id = ?
                WHERE id = ?
                """,
                (utc_now(), message_id, str(attempt_id)),
            )

    def user_answered_poll(self, poll_id: str, user_id: str) -> bool:
        if not poll_id or not user_id:
            return False
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM telegram_attempts WHERE poll_id = ? AND user_id = ? LIMIT 1",
                (str(poll_id), str(user_id)),
            ).fetchone()
        return bool(row)

    def _refresh_subject_daily_for_attempt(self, connection: sqlite3.Connection, attempt_id: str) -> None:
        row = connection.execute(
            """
            SELECT COALESCE(NULLIF(TRIM(q.subject), ''), 'Matéria não informada') AS subject,
                   substr(a.answered_at, 1, 10) AS day
            FROM telegram_attempts a JOIN questions q ON q.uid = a.question_uid
            WHERE a.id = ?
            """,
            (str(attempt_id),),
        ).fetchone()
        if not row or not str(row["day"] or "").strip():
            return
        subject, day = str(row["subject"]), str(row["day"])
        aggregate = connection.execute(
            """
            SELECT COUNT(*) AS attempts,
                   COALESCE(SUM(CASE WHEN a.is_correct = 1 THEN 1 ELSE 0 END), 0) AS correct,
                   COALESCE(SUM(CASE WHEN a.is_correct = 0 THEN 1 ELSE 0 END), 0) AS wrong,
                   AVG(CASE WHEN a.timing_quality IN ('valid','active_filtered') THEN NULLIF(a.response_seconds, 0) END) AS avg_response_seconds,
                   COALESCE(SUM(CASE WHEN a.perceived_difficulty = 'facil' THEN 1 ELSE 0 END), 0) AS easy_count,
                   COALESCE(SUM(CASE WHEN a.perceived_difficulty = 'media' THEN 1 ELSE 0 END), 0) AS medium_count,
                   COALESCE(SUM(CASE WHEN a.perceived_difficulty = 'dificil' THEN 1 ELSE 0 END), 0) AS hard_count,
                   COALESCE(SUM(CASE WHEN a.learning_gap = 1 THEN 1 ELSE 0 END), 0) AS learning_gap_count
            FROM telegram_attempts a JOIN questions q ON q.uid = a.question_uid
            WHERE COALESCE(NULLIF(TRIM(q.subject), ''), 'Matéria não informada') = ?
              AND substr(a.answered_at, 1, 10) = ?
            """,
            (subject, day),
        ).fetchone()
        if not aggregate or int(aggregate["attempts"] or 0) <= 0:
            connection.execute("DELETE FROM subject_analytics_daily WHERE subject = ? AND day = ?", (subject, day))
            return
        connection.execute(
            """
            INSERT INTO subject_analytics_daily(
                subject, day, attempts, correct, wrong, avg_response_seconds,
                easy_count, medium_count, hard_count, learning_gap_count, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(subject, day) DO UPDATE SET
                attempts = excluded.attempts, correct = excluded.correct, wrong = excluded.wrong,
                avg_response_seconds = excluded.avg_response_seconds, easy_count = excluded.easy_count,
                medium_count = excluded.medium_count, hard_count = excluded.hard_count,
                learning_gap_count = excluded.learning_gap_count, updated_at = excluded.updated_at
            """,
            (subject, day, int(aggregate["attempts"] or 0), int(aggregate["correct"] or 0),
             int(aggregate["wrong"] or 0), aggregate["avg_response_seconds"],
             int(aggregate["easy_count"] or 0), int(aggregate["medium_count"] or 0),
             int(aggregate["hard_count"] or 0), int(aggregate["learning_gap_count"] or 0), utc_now()),
        )

    def rebuild_subject_analytics_daily(self) -> dict:
        """Reconstrói a série agregada sem tocar no histórico bruto de respostas."""
        updated = utc_now()
        with self.database.connect() as connection:
            connection.execute("DELETE FROM subject_analytics_daily")
            connection.execute(
                """
                INSERT INTO subject_analytics_daily(
                    subject, day, attempts, correct, wrong, avg_response_seconds,
                    easy_count, medium_count, hard_count, learning_gap_count, updated_at
                )
                SELECT COALESCE(NULLIF(TRIM(q.subject), ''), 'Matéria não informada'),
                       substr(a.answered_at, 1, 10), COUNT(*),
                       COALESCE(SUM(CASE WHEN a.is_correct = 1 THEN 1 ELSE 0 END), 0),
                       COALESCE(SUM(CASE WHEN a.is_correct = 0 THEN 1 ELSE 0 END), 0),
                       AVG(CASE WHEN a.timing_quality IN ('valid','active_filtered') THEN NULLIF(a.response_seconds, 0) END),
                       COALESCE(SUM(CASE WHEN a.perceived_difficulty = 'facil' THEN 1 ELSE 0 END), 0),
                       COALESCE(SUM(CASE WHEN a.perceived_difficulty = 'media' THEN 1 ELSE 0 END), 0),
                       COALESCE(SUM(CASE WHEN a.perceived_difficulty = 'dificil' THEN 1 ELSE 0 END), 0),
                       COALESCE(SUM(CASE WHEN a.learning_gap = 1 THEN 1 ELSE 0 END), 0), ?
                FROM telegram_attempts a JOIN questions q ON q.uid = a.question_uid
                WHERE a.answered_at IS NOT NULL AND substr(a.answered_at, 1, 10) <> ''
                GROUP BY COALESCE(NULLIF(TRIM(q.subject), ''), 'Matéria não informada'), substr(a.answered_at, 1, 10)
                """,
                (updated,),
            )
            rows = int(connection.execute("SELECT COUNT(*) FROM subject_analytics_daily").fetchone()[0] or 0)
        return {"ok": True, "rows": rows, "updated_at": updated}

    def stats(self) -> dict:
        self.sync_questions()
        with self.database.connect() as connection:
            total = connection.execute("SELECT COUNT(*) FROM study_state WHERE suspended = 0").fetchone()[0]
            sent = connection.execute("SELECT COALESCE(SUM(sent_count), 0) FROM study_state").fetchone()[0]
            correct = connection.execute("SELECT COALESCE(SUM(correct_count), 0) FROM study_state").fetchone()[0]
            wrong = connection.execute("SELECT COALESCE(SUM(wrong_count), 0) FROM study_state").fetchone()[0]
            due = connection.execute(
                "SELECT COUNT(*) FROM study_state WHERE suspended = 0 AND (sent_count = 0 OR due_at IS NULL OR due_at <= ?)",
                (utc_now(),),
            ).fetchone()[0]
            deliveries = connection.execute("SELECT COUNT(*) FROM telegram_deliveries WHERE status = 'enviado'").fetchone()[0]
            errors = connection.execute("SELECT COUNT(*) FROM telegram_deliveries WHERE status = 'erro'").fetchone()[0]
            daily_cycles = connection.execute(
                "SELECT COUNT(*) FROM study_cycles WHERE cycle_kind IN ('diario','recuperacao') AND sent_count > 0"
            ).fetchone()[0]
        attempts = int(correct) + int(wrong)
        accuracy = (int(correct) / attempts * 100) if attempts else 0.0
        return {
            "questions": int(total),
            "sent": int(sent),
            "correct": int(correct),
            "wrong": int(wrong),
            "attempts": attempts,
            "accuracy": accuracy,
            "due": int(due),
            "deliveries": int(deliveries),
            "errors": int(errors),
            "daily_cycles": int(daily_cycles),
        }

    def activity_summary(self) -> dict:
        """Resumo explicável das respostas, canais e tempo ativo confiável."""
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT COUNT(*) AS attempts,
                       COALESCE(SUM(is_correct),0) AS correct,
                       COALESCE(SUM(CASE WHEN is_correct=0 THEN 1 ELSE 0 END),0) AS wrong,
                       AVG(CASE WHEN timing_quality IN ('valid','active_filtered') THEN NULLIF(response_seconds,0) END) AS avg_active_seconds,
                       SUM(CASE WHEN timing_quality IN ('valid','active_filtered') AND response_seconds IS NOT NULL THEN 1 ELSE 0 END) AS speed_samples,
                       SUM(CASE WHEN response_seconds IS NOT NULL AND COALESCE(timing_quality,'') NOT IN ('valid','active_filtered') THEN 1 ELSE 0 END) AS excluded_timing,
                       SUM(CASE WHEN source LIKE 'mobile_%' THEN 1 ELSE 0 END) AS mobile_attempts,
                       SUM(CASE WHEN COALESCE(source,'telegram')='telegram' THEN 1 ELSE 0 END) AS telegram_attempts,
                       SUM(CASE WHEN source='desktop' OR source='local' THEN 1 ELSE 0 END) AS desktop_attempts,
                       SUM(CASE WHEN substr(answered_at,1,10)=substr(?,1,10) THEN 1 ELSE 0 END) AS today_attempts
                FROM telegram_attempts
                """,
                (utc_now(),),
            ).fetchone()
            recent = connection.execute(
                """
                SELECT a.id,a.question_uid,a.answered_at,a.is_correct,a.response_seconds,a.timing_quality,a.source,
                       COALESCE(NULLIF(TRIM(q.source_code),''),'Sem código') AS codigo,
                       COALESCE(NULLIF(TRIM(q.subject),''),'Matéria não informada') AS materia
                FROM telegram_attempts a LEFT JOIN questions q ON q.uid=a.question_uid
                ORDER BY a.answered_at DESC LIMIT 8
                """
            ).fetchall()
        attempts=int(row['attempts'] or 0); correct=int(row['correct'] or 0); wrong=int(row['wrong'] or 0)
        return {
            'attempts': attempts, 'correct': correct, 'wrong': wrong,
            'accuracy': round((correct/attempts*100.0),1) if attempts else None,
            'avg_active_seconds': round(float(row['avg_active_seconds']),1) if row['avg_active_seconds'] is not None else None,
            'speed_samples': int(row['speed_samples'] or 0), 'excluded_timing': int(row['excluded_timing'] or 0),
            'mobile_attempts': int(row['mobile_attempts'] or 0), 'telegram_attempts': int(row['telegram_attempts'] or 0),
            'desktop_attempts': int(row['desktop_attempts'] or 0), 'today_attempts': int(row['today_attempts'] or 0),
            'recent_attempts': [dict(x) for x in recent],
        }

    def subject_stats(self, limit: int = 12) -> list[dict]:
        """Learning analytics por matéria, com prioridade explicável.

        A leitura combina histórico objetivo, janela recente, FSRS, escopo
        realmente estudado, cobertura do banco e sinais metacognitivos. O
        resultado continua compatível com a UI antiga (accuracy/attempts), mas
        adiciona as métricas do dashboard 5.7.
        """
        self.sync_questions()
        now_dt = utc_now_dt()
        now_iso = now_dt.isoformat()
        prefs = self.learning_preferences()
        retention_target = self.effective_target_retention()
        performance_target = DEFAULT_PERFORMANCE_TARGET
        coverage_target = DEFAULT_COVERAGE_TARGET

        exam_date = str(prefs.get("exam_date") or "").strip()
        days_to_exam: int | None = None
        if exam_date:
            try:
                days_to_exam = max(0, (datetime.fromisoformat(exam_date).date() - now_dt.date()).days)
            except ValueError:
                days_to_exam = None
        global_exam_urgency = analytics_exam_urgency(days_to_exam)

        with self.database.connect() as connection:
            question_rows = connection.execute(
                """
                SELECT q.uid, COALESCE(NULLIF(TRIM(q.subject), ''), 'Matéria não informada') AS subject,
                       COALESCE(NULLIF(TRIM(q.lesson), ''), 'SEM AULA') AS lesson,
                       COALESCE(NULLIF(TRIM(q.primary_topic), ''), 'SEM ASSUNTO') AS topic,
                       s.sent_count, s.correct_count, s.wrong_count, s.last_sent_at, s.last_answered_at,
                       s.due_at, s.fsrs_card_json, s.memory_retrievability, s.suspended
                FROM questions q JOIN study_state s ON s.question_uid = q.uid
                WHERE COALESCE(s.suspended, 0) = 0
                ORDER BY subject, q.uid
                """
            ).fetchall()
            attempt_rows = connection.execute(
                """
                SELECT a.id, a.question_uid, a.is_correct, a.answered_at, a.response_seconds,
                       a.confidence, a.error_type, a.perceived_difficulty, a.learning_gap,
                       COALESCE(NULLIF(TRIM(q.subject), ''), 'Matéria não informada') AS subject,
                       COALESCE(NULLIF(TRIM(q.lesson), ''), 'SEM AULA') AS lesson,
                       COALESCE(NULLIF(TRIM(q.primary_topic), ''), 'SEM ASSUNTO') AS topic
                FROM telegram_attempts a JOIN questions q ON q.uid = a.question_uid
                ORDER BY a.answered_at ASC, a.id ASC
                """
            ).fetchall()
            studied_rows = connection.execute(
                "SELECT DISTINCT subject_norm, lesson_norm FROM studied_scope"
            ).fetchall()
            daily_rows = connection.execute(
                """
                SELECT subject, day, attempts, correct, wrong, avg_response_seconds,
                       easy_count, medium_count, hard_count, learning_gap_count
                FROM subject_analytics_daily ORDER BY day ASC
                """
            ).fetchall()
            lesson_rows = connection.execute(
                """SELECT subject, lesson, correct_count, wrong_count, exposure_count, last_seen_at, last_score
                   FROM lesson_learning_state WHERE exposure_count > 0"""
            ).fetchall()
            topic_rows = connection.execute(
                """SELECT subject, topic, correct_count, wrong_count, exposure_count, last_seen_at, last_score
                   FROM topic_learning_state WHERE exposure_count > 0"""
            ).fetchall()

        cards = {str(row["uid"]): str(row["fsrs_card_json"]) for row in question_rows if str(row["fsrs_card_json"] or "").strip()}
        fsrs_retention = batch_retrievability(
            cards, desired_retention=retention_target, parameters=self.fsrs_parameters(), now=now_dt
        )

        subjects: dict[str, dict] = {}
        question_info: dict[str, tuple[str, str]] = {}
        for row in question_rows:
            subject = str(row["subject"]); uid = str(row["uid"]); lesson = str(row["lesson"])
            item = subjects.setdefault(subject, {
                "subject": subject, "questions": 0, "sent": 0, "state_correct": 0, "state_wrong": 0,
                "question_rows": [], "attempts_rows": [], "daily_rows": [], "lessons": [], "topics": [],
            })
            item["questions"] += 1
            item["sent"] += int(row["sent_count"] or 0)
            item["state_correct"] += int(row["correct_count"] or 0)
            item["state_wrong"] += int(row["wrong_count"] or 0)
            item["question_rows"].append(row)
            question_info[uid] = (subject, lesson)
        for row in attempt_rows:
            subject = str(row["subject"])
            subjects.setdefault(subject, {
                "subject": subject, "questions": 0, "sent": 0, "state_correct": 0, "state_wrong": 0,
                "question_rows": [], "attempts_rows": [], "daily_rows": [], "lessons": [], "topics": [],
            })["attempts_rows"].append(row)
        for row in daily_rows:
            subject = str(row["subject"])
            if subject in subjects:
                subjects[subject]["daily_rows"].append(row)
        for row in lesson_rows:
            subject = str(row["subject"] or "")
            if subject in subjects:
                subjects[subject]["lessons"].append(row)
        for row in topic_rows:
            subject = str(row["subject"] or "")
            if subject in subjects:
                subjects[subject]["topics"].append(row)

        studied_by_subject: dict[str, set[str]] = {}
        for row in studied_rows:
            studied_by_subject.setdefault(str(row["subject_norm"]), set()).add(str(row["lesson_norm"]))

        result: list[dict] = []
        for subject, data in subjects.items():
            attempts = list(data["attempts_rows"])
            outcomes = [1 if row["is_correct"] else 0 for row in attempts]
            attempts_count = len(outcomes)
            correct = sum(outcomes)
            wrong = attempts_count - correct
            historical_accuracy = (correct / attempts_count) if attempts_count else None

            recent_rows = attempts[-DEFAULT_RECENT_WINDOW:]
            previous_rows = attempts[-(DEFAULT_RECENT_WINDOW * 2):-DEFAULT_RECENT_WINDOW] if attempts_count > DEFAULT_RECENT_WINDOW else []
            recent_outcomes = [1 if row["is_correct"] else 0 for row in recent_rows]
            previous_outcomes = [1 if row["is_correct"] else 0 for row in previous_rows]
            recent_accuracy = (sum(recent_outcomes) / len(recent_outcomes)) if recent_outcomes else None
            current_performance = weighted_recent_accuracy(recent_outcomes) if recent_outcomes else None
            delta_pp = analytics_trend_delta(recent_outcomes, previous_outcomes)

            last_answered_dt = _parse_iso(attempts[-1]["answered_at"]) if attempts else None
            days_since_review = None if last_answered_dt is None else max(0.0, (now_dt - last_answered_dt).total_seconds() / 86400.0)
            last_sent_values = [_parse_iso(row["last_sent_at"]) for row in data["question_rows"] if row["last_sent_at"]]
            last_sent_dt = max((value for value in last_sent_values if value), default=None)

            retention_values: list[float] = []
            due_count = due_7d = due_30d = 0
            for row in data["question_rows"]:
                uid = str(row["uid"])
                if uid in fsrs_retention:
                    retention_values.append(float(fsrs_retention[uid]))
                elif int(row["correct_count"] or 0) + int(row["wrong_count"] or 0) > 0:
                    try:
                        retention_values.append(max(0.0, min(1.0, float(row["memory_retrievability"] or 0.0))))
                    except (TypeError, ValueError):
                        pass
                due_dt = _parse_iso(row["due_at"])
                if int(row["sent_count"] or 0) > 0 and due_dt is not None:
                    if due_dt <= now_dt:
                        due_count += 1
                    if due_dt <= now_dt + timedelta(days=7):
                        due_7d += 1
                    if due_dt <= now_dt + timedelta(days=30):
                        due_30d += 1
            retention = (sum(retention_values) / len(retention_values)) if retention_values else None

            answered_uids = {str(row["question_uid"]) for row in attempts}
            bank_coverage = (len(answered_uids) / int(data["questions"])) if int(data["questions"]) else 0.0
            subject_norm = self._norm_coverage_text(subject)
            studied_lessons = studied_by_subject.get(subject_norm, set())
            practiced_studied_lessons: set[str] = set()
            available_studied_lessons: set[str] = set()
            for qrow in data["question_rows"]:
                lesson_norm = self._norm_lesson(str(qrow["lesson"] or ""))
                if lesson_norm in studied_lessons:
                    available_studied_lessons.add(lesson_norm)
                    if str(qrow["uid"]) in answered_uids:
                        practiced_studied_lessons.add(lesson_norm)
            studied_coverage = (len(practiced_studied_lessons) / len(studied_lessons)) if studied_lessons else None
            effective_coverage = studied_coverage if studied_coverage is not None else bank_coverage

            difficulty_values = [str(row["perceived_difficulty"] or "") for row in recent_rows if str(row["perceived_difficulty"] or "").strip()]
            hard_count = sum(1 for value in difficulty_values if value == "dificil")
            medium_count = sum(1 for value in difficulty_values if value == "media")
            easy_count = sum(1 for value in difficulty_values if value == "facil")
            hard_ratio = (hard_count / len(difficulty_values)) if difficulty_values else 0.0
            gap_marked = sum(1 for row in recent_rows if row["learning_gap"] == 1)
            gap_known = sum(1 for row in recent_rows if row["learning_gap"] is not None)
            learning_gap_ratio = (gap_marked / gap_known) if gap_known else 0.0

            priority = analytics_subject_priority(
                retention=retention, recent_accuracy=current_performance, coverage=effective_coverage,
                days_since_review=days_since_review, exam_urgency=global_exam_urgency, due_count=due_count,
                attempts=attempts_count, studied=bool(studied_lessons), hard_ratio=hard_ratio,
                learning_gap_ratio=learning_gap_ratio, performance_target=performance_target,
            )
            priority_score = priority.score
            priority_label = priority.label
            priority_tone = priority.tone
            if not studied_lessons and attempts_count == 0:
                priority_score = min(priority_score, 25.0)
                priority_label = "Aguardando estudo"
                priority_tone = "neutral"

            # Tendência semanal: últimas 8 semanas com atividade, usando a série
            # diária materializada pela migração 7.
            weekly: dict[str, dict] = {}
            for drow in data["daily_rows"]:
                try:
                    day_dt = datetime.fromisoformat(str(drow["day"])).date()
                except ValueError:
                    continue
                monday = day_dt - timedelta(days=day_dt.weekday())
                key = monday.isoformat()
                bucket = weekly.setdefault(key, {"correct": 0, "attempts": 0, "date": monday})
                bucket["correct"] += int(drow["correct"] or 0)
                bucket["attempts"] += int(drow["attempts"] or 0)
            trend_points = []
            for key in sorted(weekly)[-8:]:
                bucket = weekly[key]
                value = (bucket["correct"] / bucket["attempts"] * 100.0) if bucket["attempts"] else 0.0
                trend_points.append({
                    "date": key, "label": bucket["date"].strftime("%d/%m"),
                    "accuracy": round(value, 1), "attempts": int(bucket["attempts"]),
                })

            # Projeção de cobertura do banco até a prova, baseada somente em
            # primeiras exposições recentes. É apresentada como projeção, não
            # como probabilidade de aprovação.
            projection = None
            if days_to_exam is not None and days_to_exam > 0 and int(data["questions"]) > 0:
                first_seen: dict[str, datetime] = {}
                for row in attempts:
                    answered = _parse_iso(row["answered_at"])
                    uid = str(row["question_uid"])
                    if answered and (uid not in first_seen or answered < first_seen[uid]):
                        first_seen[uid] = answered
                history_start = min(first_seen.values(), default=now_dt)
                observation_days = max(1, min(30, (now_dt.date() - history_start.date()).days + 1))
                cutoff = now_dt - timedelta(days=observation_days)
                new_recent = sum(1 for value in first_seen.values() if value >= cutoff)
                pace = new_recent / observation_days
                projected_unique = min(int(data["questions"]), len(answered_uids) + int(round(pace * days_to_exam)))
                target_unique = int(math.ceil(int(data["questions"]) * coverage_target))
                needed = max(0, target_unique - len(answered_uids))
                projection = {
                    "days_to_exam": days_to_exam,
                    "pace_new_questions_day": round(pace, 2),
                    "projected_bank_coverage": round(projected_unique / int(data["questions"]), 4),
                    "target_bank_coverage": coverage_target,
                    "needed_new_questions_day": round(needed / days_to_exam, 2),
                }

            def _weak(rows: list[sqlite3.Row], label_key: str) -> list[dict]:
                values = []
                for row in rows:
                    c = int(row["correct_count"] or 0); w = int(row["wrong_count"] or 0); total = c + w
                    if total <= 0:
                        continue
                    values.append({
                        "name": str(row[label_key] or "Não informado"),
                        "accuracy": round(c / total * 100.0, 1),
                        "attempts": total,
                        "last_seen_at": str(row["last_seen_at"] or ""),
                    })
                values.sort(key=lambda item: (item["accuracy"], -item["attempts"], item["name"]))
                return values[:3]

            has_answers = attempts_count > 0
            if not has_answers:
                performance_label = "Sem respostas"
                performance_tone = "neutral"
            elif recent_accuracy is not None and recent_accuracy < 0.60:
                performance_label = "Atenção"; performance_tone = "danger"
            elif recent_accuracy is not None and recent_accuracy < 0.80:
                performance_label = "Em evolução"; performance_tone = "warning"
            else:
                performance_label = "Bom desempenho"; performance_tone = "success"

            result.append({
                "subject": subject, "materia": subject, "questions": int(data["questions"]), "sent": int(data["sent"]),
                "correct": correct, "wrong": wrong, "attempts": attempts_count,
                "accuracy": round((historical_accuracy or 0.0) * 100.0, 2), "has_answers": has_answers,
                "historical_accuracy": None if historical_accuracy is None else round(historical_accuracy * 100.0, 2),
                "recent_accuracy": None if recent_accuracy is None else round(recent_accuracy * 100.0, 2),
                "current_performance": None if current_performance is None else round(current_performance * 100.0, 2),
                "trend_delta_pp": None if delta_pp is None else round(delta_pp, 2), "trend": trend_points,
                "last_review_at": last_answered_dt.isoformat() if last_answered_dt else "",
                "last_sent_at": last_sent_dt.isoformat() if last_sent_dt else "",
                "days_since_review": None if days_since_review is None else round(days_since_review, 2),
                "retention": None if retention is None else round(retention * 100.0, 2),
                "retention_sample": len(retention_values), "retention_target": round(retention_target * 100.0, 1),
                "due_count": due_count, "due_7d": due_7d, "due_30d": due_30d,
                "unique_practiced": len(answered_uids), "bank_coverage": round(bank_coverage * 100.0, 2),
                "studied": bool(studied_lessons), "studied_lessons": len(studied_lessons),
                "available_studied_lessons": len(available_studied_lessons),
                "practiced_studied_lessons": len(practiced_studied_lessons),
                "studied_coverage": None if studied_coverage is None else round(studied_coverage * 100.0, 2),
                "effective_coverage": round(effective_coverage * 100.0, 2),
                "performance_target": round(performance_target * 100.0, 1),
                "coverage_target": round(coverage_target * 100.0, 1),
                "priority_score": round(priority_score, 1), "priority_label": priority_label,
                "priority_tone": priority_tone, "priority_components": priority.components,
                "priority_reasons": priority.reasons, "performance_label": performance_label,
                "performance_tone": performance_tone, "sample_confidence": sample_confidence(attempts_count),
                "difficulty_recent": {"facil": easy_count, "media": medium_count, "dificil": hard_count, "known": len(difficulty_values)},
                "learning_gap_recent": {"marked": gap_marked, "known": gap_known},
                "weak_lessons": _weak(data["lessons"], "lesson"), "weak_topics": _weak(data["topics"], "topic"),
                "projection": projection, "days_to_exam": days_to_exam,
                "analytics_version": DASHBOARD_ANALYTICS_VERSION,
            })

        result.sort(key=lambda item: (-float(item["priority_score"]), -int(item["due_count"]), str(item["subject"])))
        return result[:max(1, int(limit))]

    def recent_deliveries(self, limit: int = 100) -> list[dict]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT d.id, d.question_uid, d.question_uid AS uid, d.cycle_id,
                       d.sent_at, d.status, d.error_text, d.error_text AS last_error,
                       d.error_category, d.is_retryable, d.next_retry_at,
                       d.attempt_count, d.attempt_count AS attempts, d.last_attempt_at,
                       d.resolved_by_delivery_id, d.parent_delivery_id, d.poll_id,
                       COALESCE(NULLIF(TRIM(q.source_code), ''), 'NÃO ENCONTRADO') AS source_code,
                       COALESCE(NULLIF(TRIM(q.source_code), ''), 'NÃO ENCONTRADO') AS codigo,
                       COALESCE(NULLIF(TRIM(q.subject), ''), 'Matéria não encontrada') AS subject,
                       COALESCE(NULLIF(TRIM(q.subject), ''), 'Matéria não encontrada') AS materia,
                       COALESCE(NULLIF(TRIM(q.primary_topic), ''), 'Assunto não encontrado') AS primary_topic,
                       q.statement,
                       CASE WHEN q.uid IS NULL THEN 0 ELSE 1 END AS question_found,
                       COUNT(a.id) AS answers,
                       COALESCE(SUM(a.is_correct), 0) AS correct_answers,
                       COALESCE(SUM(a.is_correct), 0) AS correct
                FROM telegram_deliveries d
                LEFT JOIN questions q ON q.uid = d.question_uid
                LEFT JOIN telegram_attempts a ON a.delivery_id = d.id
                WHERE COALESCE(d.source, 'telegram') = 'telegram'
                GROUP BY d.id
                ORDER BY d.sent_at DESC
                LIMIT ?
                """,
                (max(1, int(limit)),),
            ).fetchall()
        return [dict(row) for row in rows]

    def reset_progress(self) -> dict:
        """Reinicia integralmente o aprendizado sem apagar o banco de questões.

        A operação é transacional. Ela zera histórico, repetição espaçada,
        estado adaptativo, gamificação e filas operacionais antigas do Telegram.
        Solicitações de correção são preservadas e questões ainda em correção
        permanecem suspensas. O offset do Telegram também é preservado para que
        atualizações antigas não sejam processadas novamente após o reinício.
        """
        now = utc_now()
        with self.database.connect() as connection:
            before = {
                "attempts": int(connection.execute("SELECT COUNT(*) FROM telegram_attempts").fetchone()[0]),
                "deliveries": int(connection.execute("SELECT COUNT(*) FROM telegram_deliveries").fetchone()[0]),
                "cycles": int(connection.execute("SELECT COUNT(*) FROM study_cycles").fetchone()[0]),
                "xp_events": int(connection.execute("SELECT COUNT(*) FROM xp_events").fetchone()[0]),
                "topics": int(connection.execute("SELECT COUNT(*) FROM topic_learning_state").fetchone()[0]),
                "lessons": int(connection.execute("SELECT COUNT(*) FROM lesson_learning_state").fetchone()[0]),
                "analytics_days": int(connection.execute("SELECT COUNT(*) FROM subject_analytics_daily").fetchone()[0]),
                "learner_events": int(connection.execute("SELECT COUNT(*) FROM learner_model_events").fetchone()[0]),
                "concept_mastery": int(connection.execute("SELECT COUNT(*) FROM concept_mastery").fetchone()[0]),
            }

            # Apague primeiro os registros dependentes e filas que poderiam
            # reaplicar respostas de um ciclo anterior depois do reinício.
            connection.execute("DELETE FROM adaptive_simulation_items")
            connection.execute("DELETE FROM adaptive_simulation_sessions")
            connection.execute("DELETE FROM telegram_attempts")
            connection.execute("DELETE FROM telegram_deliveries")
            connection.execute("DELETE FROM study_cycles")
            connection.execute("DELETE FROM telegram_callback_inbox")
            connection.execute("DELETE FROM telegram_outbox")
            connection.execute("DELETE FROM xp_events")
            connection.execute("DELETE FROM topic_learning_state")
            connection.execute("DELETE FROM lesson_learning_state")
            connection.execute("DELETE FROM subject_analytics_daily")
            connection.execute("DELETE FROM learner_model_events")
            connection.execute("DELETE FROM concept_mastery")
            connection.execute("DELETE FROM learner_ability")
            connection.execute("DELETE FROM question_irt")
            connection.execute("DELETE FROM adaptive_model_state")
            connection.execute(
                """UPDATE fsrs_optimizer_state SET parameters_json = NULL, desired_retention = NULL,
                   review_count = 0, question_count = 0, trained_at = NULL, fsrs_version = NULL,
                   status = 'aguardando', error_text = NULL, updated_at = ? WHERE id = 1""",
                (now,),
            )

            # O offset evita que o listener trate novamente mensagens antigas.
            connection.execute(
                """DELETE FROM flow_runtime WHERE key NOT IN (
                    'telegram_update_offset', 'target_retention', 'target_retention_mode',
                    'exam_date', 'daily_study_minutes', 'fsrs_maximum_interval_days',
                    'fsrs_relearning_minutes', 'studied_only', 'early_review_enabled',
                    'studied_scope_initialized'
                )"""
            )

            connection.execute(
                """
                UPDATE learner_profile
                SET total_xp = 0, level = 1, best_streak = 0, updated_at = ?
                WHERE id = 1
                """,
                (now,),
            )

            connection.execute(
                """
                UPDATE study_state
                SET sent_count = 0, correct_count = 0, wrong_count = 0, streak = 0,
                    last_sent_at = NULL, last_answered_at = NULL, due_at = NULL,
                    ease = 2.5, suspended = 0, correction_priority = 0,
                    correction_requested_at = NULL, correction_resolved_at = NULL,
                    memory_difficulty = 5.0, memory_stability = 1.0,
                    memory_retrievability = 0.9, response_time_ema = 0.0,
                    adaptive_prediction = 0.5, adaptive_priority = 0.0,
                    adaptive_model_version = 'qf-adaptive-1',
                    fsrs_card_json = NULL, fsrs_due_at = NULL,
                    fsrs_rating = NULL, fsrs_version = NULL, fsrs_state = 'new',
                    fsrs_lapses = 0, last_selection_reason = NULL, last_selection_bucket = NULL,
                    kt_mastery = NULL, kt_confidence = 0.0, irt_information = 0.0,
                    learner_fusion_priority = 0.0, learner_model_version = NULL
                """
            )

            # Correções são dados editoriais e não fazem parte do progresso.
            # Preserve-as e mantenha suspensas somente as questões ainda abertas.
            connection.execute(
                """
                UPDATE study_state
                SET suspended = 1, correction_requested_at = ?
                WHERE question_uid IN (
                    SELECT question_uid FROM telegram_review_requests
                    WHERE status IN ('pendente', 'aberta')
                )
                """,
                (now,),
            )

            active_corrections = int(connection.execute(
                "SELECT COUNT(*) FROM telegram_review_requests WHERE status IN ('pendente', 'aberta')"
            ).fetchone()[0])

        return {
            "reset_at": now,
            "cleared": before,
            "active_corrections_preserved": active_corrections,
        }

    def suspend_question(self, uid: str, suspended: bool = True) -> None:
        self.sync_questions()
        with self.database.connect() as connection:
            connection.execute(
                "UPDATE study_state SET suspended = ? WHERE question_uid = ?",
                (1 if suspended else 0, uid),
            )
