import type { AdaptiveSessionGoal, Confidence, Difficulty, StudySessionMode } from './types';

export type StudySessionConfig = {
  mode: StudySessionMode;
  count: number;
  subject: string;
};

export type StudySessionStats = {
  answered: number;
  correct: number;
  wrong: number;
  skipped: number;
  pending_results: number;
  active_seconds: number;
};

export type AdaptiveSessionState = {
  enabled: boolean;
  source: 'questflow_orchestrator' | 'offline_fallback' | string;
  micro_batch_size: number;
  current_batch_id: string;
  current_batch_ordinal: number;
  plan_revision: number;
  strategy_profile: string;
  goal: AdaptiveSessionGoal | null;
  boundaries: Array<{ batch_id: string; start_index: number; end_index: number; plan_revision: number }>;
  prefetched?: {
    batch_id: string;
    ordinal: number;
    plan_revision: number;
    strategy_profile: string;
    refs: Array<{ id: string; revision: number }>;
  } | null;
};

export type PersistedStudySession = {
  version: 1 | 2 | 3;
  session_id: string;
  config: StudySessionConfig;
  question_refs: Array<{ id: string; revision: number }>;
  index: number;
  stats: StudySessionStats;
  counted_attempt_ids: string[];
  attempt_id: string;
  phase: 'answer' | 'confidence' | 'result';
  selected: number | null;
  eliminated: number[];
  confidence: Confidence | null;
  difficulty: Difficulty | null;
  submitted_active_seconds: number;
  adaptive?: AdaptiveSessionState | null;
  started_at: string;
  updated_at: string;
};

export const ACTIVE_STUDY_SESSION_KEY = 'active_study_session_v3';
export const LAST_STUDY_SESSION_KEY = 'last_study_session_summary_v3';
export const LEGACY_ACTIVE_STUDY_SESSION_KEY = 'active_study_session_v2';
export const LEGACY_LAST_STUDY_SESSION_KEY = 'last_study_session_summary_v2';

export function emptyStudySessionStats(): StudySessionStats {
  return { answered: 0, correct: 0, wrong: 0, skipped: 0, pending_results: 0, active_seconds: 0 };
}

export function sessionModeLabel(mode: StudySessionMode): string {
  return ({
    recommended: 'Recomendado',
    review: 'Revisões',
    errors: 'Erros',
    subject: 'Matéria específica',
  } as Record<StudySessionMode, string>)[mode];
}

export function sessionModeDescription(mode: StudySessionMode): string {
  return ({
    recommended: 'Mistura prioridade, memória e desempenho para escolher o melhor próximo lote.',
    review: 'Foca nas questões que chegaram ao momento de revisão.',
    errors: 'Traz questões com histórico de erro para consolidar pontos frágeis.',
    subject: 'Concentra a sessão em uma única matéria escolhida por você.',
  } as Record<StudySessionMode, string>)[mode];
}

export function sessionAccuracy(stats: StudySessionStats): number | null {
  const judged = stats.correct + stats.wrong;
  return judged ? stats.correct / judged : null;
}

export function normalizeSessionCount(value: number): number {
  return Math.max(1, Math.min(50, Math.round(Number(value) || 8)));
}

export function parsePersistedStudySession(raw: string | null): PersistedStudySession | null {
  if (!raw) return null;
  try {
    const value = JSON.parse(raw) as PersistedStudySession;
    if (!value || ![1, 2, 3].includes(Number(value.version)) || !value.session_id || !Array.isArray(value.question_refs)) return null;
    value.version = Number(value.version) === 3 ? 3 : Number(value.version) === 2 ? 2 : 1;
    value.config.count = normalizeSessionCount(value.config?.count || value.question_refs.length || 8);
    value.index = Math.max(0, Math.min(Number(value.index || 0), Math.max(0, value.question_refs.length - 1)));
    value.stats = { ...emptyStudySessionStats(), ...(value.stats || {}) };
    value.counted_attempt_ids = Array.isArray(value.counted_attempt_ids) ? value.counted_attempt_ids.map(String) : [];
    value.eliminated = Array.isArray(value.eliminated) ? value.eliminated.map(Number).filter(Number.isFinite) : [];
    if (value.version === 1 && !value.adaptive) value.adaptive = null;
    if (value.adaptive?.boundaries && !Array.isArray(value.adaptive.boundaries)) value.adaptive.boundaries = [];
    return value;
  } catch {
    return null;
  }
}
