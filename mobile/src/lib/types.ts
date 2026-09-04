export type Confidence = 'low' | 'medium' | 'high';
export type Difficulty = 'easy' | 'medium' | 'hard';
export type StudySessionMode = 'recommended' | 'review' | 'errors' | 'subject';

export type MobileQuestion = {
  question_id: string;
  question_revision: number;
  code: string;
  subject: string;
  topic: string;
  lesson: string;
  statement: string;
  question_type: string;
  alternatives: Array<{ index: number; key: string; text: string }>;
  has_explanation: boolean;
  study_flags?: { due?: boolean; review_eligible?: boolean; wrong_count?: number; sent_count?: number };
  offline_eligibility?: { policy?: string; kind?: 'never_answered' | 'studio_spacing_due' | string; answered_before?: boolean; due_at?: string; fsrs_state?: string };
  selection?: {
    policy?: string;
    source?: string;
    core_policy?: string;
    bucket?: number;
    reason?: string;
    recent_exposure_penalty?: number;
    topic_transfer?: boolean;
    core_rank?: number;
    strategy_profile?: string;
    expected_active_seconds?: number;
    transfer_reason?: string;
    plan_revision?: number;
    micro_batch_position?: number;
  };
};


export type OfflineStudyPack = {
  contract: 'questflow.mobile.offline_study_pack.v1' | string;
  pack_id: string;
  generated_at: string;
  exam_project_id: string;
  requested_count: number;
  eligible_count?: number;
  eligibility_policy?: string;
  selection_policy: string;
  core_policy: string;
  source: 'studio_learning_engine' | string;
  adaptive_while_offline: boolean;
  questions: MobileQuestion[];
};

export type AdaptiveSessionGoal = {
  type: 'adaptive' | string;
  headline: string;
  questions_target: number;
  estimated_minutes: number;
  focus: string[];
  strategy_profile?: string;
};

export type AdaptiveMicroBatch = {
  batch_id: string;
  ordinal: number;
  plan_revision: number;
  purpose: 'active' | 'prefetch' | string;
  strategy_profile: string;
  state_signature?: string;
  questions: MobileQuestion[];
  completed?: boolean;
  prefetch_promoted?: boolean;
  prefetch_reused?: boolean;
};

export type AdaptiveSessionProjection = {
  contract: 'questflow.mobile.adaptive_session.v1' | string;
  orchestrator?: string;
  session_id: string;
  target_questions?: number;
  micro_batch_size?: number;
  goal: AdaptiveSessionGoal;
  micro_batch: AdaptiveMicroBatch;
};

export type MobilePriority = {
  subject_id: string;
  label: string;
  status: 'needs_attention' | 'monitor' | 'stable' | string;
  mastery: { level: string; confidence: string; estimate?: number };
  performance: { accuracy: number | null; attempts: number };
  memory: { status: string; due_count: number; retrievability?: number };
  priority: { level: string; score: number; reasons: string[] };
  recommended_action: { type: string; question_count: number };
  insight?: {
    recent_accuracy: number | null;
    trend_delta: number | null;
    recent_sample: number;
    last_answered_at: string;
    difficulty: { easy: number; medium: number; hard: number; known: number };
    learning_gap: { marked: number; known: number };
    weak_topics: Array<{ name: string; accuracy: number; attempts: number }>;
  };
  exam_project_id: string;
};

export type MobileStudyBacklogItem = {
  backlog_id: string;
  topic_key: string;
  exam_project_id: string;
  subject: string;
  topic: string;
  lesson: string;
  source_question_id: string;
  mark_count: number;
  first_marked_at: string;
  last_marked_at: string;
};

export type ProgressProjection = {
  contract: string;
  generated_at: string;
  exam_project_id: string;
  study_backlog: { pending_count: number; items: MobileStudyBacklogItem[] };
  summary: {
    attempts: number;
    correct: number;
    wrong: number;
    accuracy: number | null;
    avg_active_response_seconds: number | null;
    timing_samples: number;
    timing_samples_excluded: number;
    today_attempts: number;
    coach_text: string;
    timing_note: string;
  };
  subjects: MobilePriority[];
  recent_activity: MobileRecentActivity[];
};

export type AnalyticsTimelinePoint = {
  period_start: string;
  response_index?: number;
  attempts: number;
  accuracy: number | null;
  is_correct?: boolean;
  cumulative_accuracy?: number | null;
  retention: number | null;
  due_reviews: number | null;
  active_minutes: number;
  timing_samples: number;
};

export type AnalyticsSubject = {
  subject_id: string;
  label: string;
  attempts: number;
  accuracy: number | null;
  retention: number | null;
  mastery: number | null;
  due_reviews: number;
  sample_confidence: 'low' | 'medium' | 'high';
};

export type AnalyticsSnapshotV2 = {
  contract: 'questflow.analytics.v2' | string;
  generated_at: string;
  exam_project_id: string;
  range: 'all' | '4w' | '8w' | '12w' | '24w' | string;
  grain: 'attempt' | 'day' | 'week' | string;
  summary: {
    attempts: number;
    correct: number;
    accuracy: number | null;
    retention_current: number | null;
    due_reviews: number;
    active_minutes: number;
  };
  timeline: AnalyticsTimelinePoint[];
  subjects: AnalyticsSubject[];
  priority_breakdown: Array<{
    subject_id: string;
    label: string;
    total: number;
    memory_risk: number;
    performance_gap: number;
    mastery_gap: number;
    evidence_gap: number;
  }>;
  projection_band: {
    estimate: number | null;
    low: number | null;
    high: number | null;
    confidence: number | null;
    sample_size: number;
    label: string;
  };
  review_queue: Array<{ subject_id: string; label: string; due_count: number; priority: string; question_count: number }>;
  sample_size: number;
  source_freshness: {
    latest_answered_at: string | null;
    generated_at: string;
    attempt_history: 'available' | 'empty' | string;
    retention_history: 'not_collected' | 'available' | string;
    note: string;
  };
};

export type TodayProjection = {
  contract: string;
  generated_at: string;
  exam_project_id: string;
  top_priority: MobilePriority | null;
  today: { reviews_due: number; recommended_questions: number; not_studied_topics?: number };
  coach: { headline: string; what_happened: string; why_it_matters: string; next_action: string; question_count: number };
  focus: MobilePriority[];
  recent_activity: MobileRecentActivity[];
};


export type MobileRecentActivity = {
  attempt_id: string;
  question_id: string;
  code: string;
  subject: string;
  answered_at: string;
  is_correct: boolean;
  active_response_seconds: number | null;
  timing_quality: string;
};



export type BootstrapProjection = {
  contract: string;
  schema_version: number;
  identity: { account_id: string; tenant_id: string; learner_id: string };
  active_project: null | {
    id: string;
    name: string;
    agency?: string;
    role?: string;
    board?: string;
    exam_date?: string;
    status?: string;
    active?: number | boolean;
  };
  today: TodayProjection;
  progress: ProgressProjection;
  analytics?: AnalyticsSnapshotV2;
  devices: number;
  sync: {
    event_cursor: number;
    idempotent_events: boolean;
    offline_outbox_supported: boolean;
    offline_study_pack_supported?: boolean;
    offline_study_pack_policy?: string;
    transport?: 'studio_lan' | 'cloud_bridge' | string;
    cloud_bridge?: { enabled: boolean; base_url?: string; state?: string; protocol?: string; last_sync_at?: string; studio_required_for_pairing?: boolean; offline_study_pack?: boolean };
    last_studio_publish_at?: string;
    pending_remote_events?: number;
  };
  privacy: { location: boolean; contacts: boolean; microphone: boolean; advertising_id: boolean };
};

export type PairingExchange = {
  access_token: string;
  token_type: 'Bearer' | string;
  expires_at: string;
  device_id: string;
  identity: { account_id: string; tenant_id: string; learner_id: string };
  api: string;
  server_fingerprint?: string;
  cloud_bridge?: { enabled?: boolean; base_url?: string; state?: string; protocol?: string; offline_study_pack?: boolean };
};

export type Feedback = {
  provisional?: boolean;
  source?: string;
  attempt_id: string;
  question_id: string;
  question_revision: number;
  selected_indices: number[];
  is_correct: boolean;
  correct_index: number | null;
  correct_key: string;
  explanation: string;
  timing: {
    active_response_seconds: number | null;
    wall_response_seconds: number | null;
    idle_seconds: number | null;
    quality: string;
  };
};

export type LearningEvent = {
  event_id: string;
  schema_version: 1;
  event_type:
    | 'session_started'
    | 'session_ended'
    | 'question_presented'
    | 'question_opened'
    | 'answer_selected'
    | 'answer_changed'
    | 'answer_submitted'
    | 'confidence_reported'
    | 'difficulty_reported'
    | 'result_seen'
    | 'explanation_opened'
    | 'explanation_finished'
    | 'learning_gap_reported'
    | 'question_skipped'
    | 'question_correction_requested'
    | 'topic_not_studied_reported'
    | 'topic_study_completed'
    | 'hint_requested'
    | 'scaffold_used';
  device_id: string;
  session_id?: string;
  attempt_id?: string;
  exam_project_id?: string;
  question_id?: string;
  question_revision?: number;
  occurred_at: string;
  sequence_no: number;
  client: { platform: string; version: string };
  payload: Record<string, unknown>;
};

export type OutboxRow = {
  event_id: string;
  event_json: string;
  created_at: string;
  attempts: number;
  last_error: string | null;
};
