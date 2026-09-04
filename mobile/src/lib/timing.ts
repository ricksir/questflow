import { ACTIVE_IDLE_CUTOFF_MS, ACTIVE_TICK_MAX_MS } from './config';

export type TimerSnapshot = {
  wall_response_seconds: number;
  active_response_seconds: number;
  idle_seconds: number;
  max_idle_gap_seconds: number;
  interaction_count: number;
  timing_source: 'client_active_timer_v1';
};

export type TimerState = {
  startedAtMs: number;
  lastTickMs: number;
  lastInteractionMs: number;
  activeMs: number;
  maxIdleGapMs: number;
  interactionCount: number;
  foreground: boolean;
  questionScreenActive: boolean;
};

export function createTimer(nowMs: number): TimerState {
  return {
    startedAtMs: nowMs,
    lastTickMs: nowMs,
    lastInteractionMs: nowMs,
    activeMs: 0,
    maxIdleGapMs: 0,
    interactionCount: 1,
    foreground: true,
    questionScreenActive: true,
  };
}

export function tickTimer(state: TimerState, nowMs: number): TimerState {
  const elapsed = Math.max(0, Math.min(ACTIVE_TICK_MAX_MS, nowMs - state.lastTickMs));
  const idleGap = Math.max(0, nowMs - state.lastInteractionMs);
  const canCount = state.foreground && state.questionScreenActive && idleGap <= ACTIVE_IDLE_CUTOFF_MS;
  return {
    ...state,
    activeMs: state.activeMs + (canCount ? elapsed : 0),
    maxIdleGapMs: Math.max(state.maxIdleGapMs, idleGap),
    lastTickMs: nowMs,
  };
}

export function markInteraction(state: TimerState, nowMs: number): TimerState {
  const ticked = tickTimer(state, nowMs);
  return {
    ...ticked,
    lastInteractionMs: nowMs,
    interactionCount: ticked.interactionCount + 1,
  };
}

export function setForeground(state: TimerState, foreground: boolean, nowMs: number): TimerState {
  const ticked = tickTimer(state, nowMs);
  return {
    ...ticked,
    foreground,
    lastInteractionMs: foreground ? nowMs : ticked.lastInteractionMs,
    interactionCount: foreground ? ticked.interactionCount + 1 : ticked.interactionCount,
  };
}

export function setQuestionScreenActive(state: TimerState, active: boolean, nowMs: number): TimerState {
  const ticked = tickTimer(state, nowMs);
  return {
    ...ticked,
    questionScreenActive: active,
    lastInteractionMs: active ? nowMs : ticked.lastInteractionMs,
    interactionCount: active ? ticked.interactionCount + 1 : ticked.interactionCount,
  };
}

export function snapshotTimer(state: TimerState, nowMs: number): TimerSnapshot {
  const final = tickTimer(state, nowMs);
  const wallMs = Math.max(0, nowMs - final.startedAtMs);
  const activeMs = Math.min(wallMs, Math.max(0, final.activeMs));
  return {
    wall_response_seconds: Math.round(wallMs / 100) / 10,
    active_response_seconds: Math.round(activeMs / 100) / 10,
    idle_seconds: Math.round(Math.max(0, wallMs - activeMs) / 100) / 10,
    max_idle_gap_seconds: Math.round(final.maxIdleGapMs / 100) / 10,
    interaction_count: final.interactionCount,
    timing_source: 'client_active_timer_v1',
  };
}
