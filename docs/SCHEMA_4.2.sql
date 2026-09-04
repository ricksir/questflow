-- QuestFlow Studio 4.2.0 schema snapshot
-- Gerado automaticamente pelo conjunto de migrações versionadas.

CREATE TABLE adaptive_model_state (
                    id INTEGER PRIMARY KEY CHECK(id = 1),
                    model_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

CREATE TABLE excluded_questions (
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

CREATE TABLE flow_runtime (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    updated_at TEXT NOT NULL
                );

CREATE TABLE imports (
                    id TEXT PRIMARY KEY,
                    source_file TEXT NOT NULL,
                    imported_at TEXT NOT NULL,
                    extracted_count INTEGER NOT NULL DEFAULT 0,
                    inserted_count INTEGER NOT NULL DEFAULT 0,
                    duplicate_count INTEGER NOT NULL DEFAULT 0,
                    pending_count INTEGER NOT NULL DEFAULT 0,
                    metadata_json TEXT NOT NULL
                );

CREATE TABLE learner_profile (
                    id INTEGER PRIMARY KEY CHECK(id = 1),
                    total_xp INTEGER NOT NULL DEFAULT 0,
                    level INTEGER NOT NULL DEFAULT 1,
                    best_streak INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL
                );

CREATE TABLE questions (
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

CREATE TABLE schema_migrations (
            component TEXT NOT NULL,
            version INTEGER NOT NULL,
            name TEXT NOT NULL,
            checksum TEXT NOT NULL,
            applied_at TEXT NOT NULL,
            PRIMARY KEY(component, version)
        );

CREATE TABLE study_cycles (
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

CREATE TABLE study_state (
                    question_uid TEXT PRIMARY KEY,
                    sent_count INTEGER NOT NULL DEFAULT 0,
                    correct_count INTEGER NOT NULL DEFAULT 0,
                    wrong_count INTEGER NOT NULL DEFAULT 0,
                    streak INTEGER NOT NULL DEFAULT 0,
                    last_sent_at TEXT,
                    last_answered_at TEXT,
                    due_at TEXT,
                    ease REAL NOT NULL DEFAULT 2.5,
                    suspended INTEGER NOT NULL DEFAULT 0, correction_priority INTEGER NOT NULL DEFAULT 0, correction_requested_at TEXT, correction_resolved_at TEXT, memory_difficulty REAL NOT NULL DEFAULT 5.0, memory_stability REAL NOT NULL DEFAULT 1.0, memory_retrievability REAL NOT NULL DEFAULT 0.9, response_time_ema REAL NOT NULL DEFAULT 0.0, adaptive_prediction REAL NOT NULL DEFAULT 0.5, adaptive_priority REAL NOT NULL DEFAULT 0.0, adaptive_model_version TEXT NOT NULL DEFAULT 'qf-adaptive-1', fsrs_card_json TEXT, fsrs_due_at TEXT, fsrs_rating INTEGER, fsrs_version TEXT,
                    FOREIGN KEY(question_uid) REFERENCES questions(uid) ON DELETE CASCADE
                );

CREATE TABLE telegram_attempts (
                    id TEXT PRIMARY KEY,
                    delivery_id TEXT NOT NULL,
                    question_uid TEXT NOT NULL,
                    poll_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    username TEXT,
                    selected_indices_json TEXT NOT NULL,
                    is_correct INTEGER NOT NULL,
                    answered_at TEXT NOT NULL, feedback_sent_at TEXT, feedback_message_id INTEGER, predicted_probability REAL, prediction_model_version TEXT, response_seconds REAL,
                    UNIQUE(delivery_id, user_id),
                    FOREIGN KEY(delivery_id) REFERENCES telegram_deliveries(id) ON DELETE CASCADE,
                    FOREIGN KEY(question_uid) REFERENCES questions(uid) ON DELETE CASCADE
                );

CREATE TABLE telegram_callback_inbox (
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

CREATE TABLE telegram_deliveries (
                    id TEXT PRIMARY KEY,
                    cycle_id TEXT NOT NULL,
                    question_uid TEXT NOT NULL,
                    poll_id TEXT UNIQUE,
                    chat_id TEXT NOT NULL,
                    message_id INTEGER,
                    sent_at TEXT NOT NULL,
                    direct_poll INTEGER NOT NULL DEFAULT 1,
                    status TEXT NOT NULL DEFAULT 'enviado',
                    error_text TEXT, attempt_count INTEGER NOT NULL DEFAULT 1, last_attempt_at TEXT, next_retry_at TEXT, error_category TEXT, is_retryable INTEGER NOT NULL DEFAULT 0, resolved_by_delivery_id TEXT, parent_delivery_id TEXT, resend_reason TEXT, unanswered_resend_count INTEGER NOT NULL DEFAULT 0, last_unanswered_check_at TEXT,
                    FOREIGN KEY(question_uid) REFERENCES questions(uid) ON DELETE CASCADE
                );

CREATE TABLE telegram_outbox (
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

CREATE TABLE telegram_review_requests (
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

CREATE TABLE topic_learning_state (
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

CREATE TABLE xp_events (
                    id TEXT PRIMARY KEY,
                    question_uid TEXT NOT NULL,
                    xp INTEGER NOT NULL,
                    reason TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(question_uid) REFERENCES questions(uid) ON DELETE CASCADE
                );

CREATE INDEX idx_attempt_answered ON telegram_attempts(answered_at);

CREATE INDEX idx_attempt_prediction ON telegram_attempts(predicted_probability, answered_at);

CREATE INDEX idx_callback_inbox_status ON telegram_callback_inbox(status, next_retry_at, received_at);

CREATE INDEX idx_cycle_scheduled_date ON study_cycles(scheduled_date, cycle_kind, status);

CREATE INDEX idx_delivery_parent ON telegram_deliveries(parent_delivery_id);

CREATE INDEX idx_delivery_poll ON telegram_deliveries(poll_id);

CREATE INDEX idx_delivery_sent ON telegram_deliveries(sent_at);

CREATE INDEX idx_delivery_status_retry ON telegram_deliveries(status, next_retry_at);

CREATE INDEX idx_excluded_fingerprint ON excluded_questions(fingerprint);

CREATE INDEX idx_excluded_kind ON excluded_questions(exclusion_kind);

CREATE INDEX idx_excluded_source_key ON excluded_questions(source_key);

CREATE INDEX idx_outbox_status ON telegram_outbox(status, next_retry_at, created_at);

CREATE INDEX idx_questions_agency ON questions(agency);

CREATE INDEX idx_questions_board ON questions(board);

CREATE INDEX idx_questions_lesson ON questions(lesson);

CREATE INDEX idx_questions_statement ON questions(statement);

CREATE INDEX idx_questions_status ON questions(review_status);

CREATE INDEX idx_questions_subject ON questions(subject);

CREATE INDEX idx_questions_taxonomy_status ON questions(taxonomy_status);

CREATE INDEX idx_questions_topic ON questions(primary_topic);

CREATE INDEX idx_questions_year ON questions(exam_year);

CREATE INDEX idx_review_request_question ON telegram_review_requests(question_uid);

CREATE INDEX idx_review_request_status ON telegram_review_requests(status, requested_at);

CREATE INDEX idx_study_adaptive_priority ON study_state(adaptive_priority DESC);

CREATE INDEX idx_study_correction_priority ON study_state(correction_priority, suspended, due_at);

CREATE INDEX idx_study_due ON study_state(due_at);

CREATE INDEX idx_study_suspended_due ON study_state(suspended, due_at);

CREATE INDEX idx_topic_learning_priority ON topic_learning_state(last_score DESC, updated_at);

CREATE INDEX idx_xp_events_created ON xp_events(created_at);
