import * as Crypto from 'expo-crypto';
import { router, useFocusEffect } from 'expo-router';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { ActivityIndicator, Alert, PanResponder, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { Button, Card, HeroCard, Metric, Muted, Pill, ProgressBar, Screen, ScreenHeader, SectionTitle, StatePanel, palette } from '../../src/components/ui';
import { useQuestFlow } from '../../src/context/QuestFlowContext';
import { cacheQuestion, enqueueEvent, getCachedQuestion, getLocalAttempt, getMeta, getOfflineStudyPackQuestions, listOfflineAttemptHistory, markAttemptAnsweredOffline, markOfflineStudyPackConsumed, offlineAttemptHistoryInfo, offlineStudyPackInfo, saveFeedback, saveLocalAttempt, setMeta, type OfflineAttemptHistoryItem } from '../../src/lib/db';
import { createLearningEvent } from '../../src/lib/events';
import { formatDuration, formatDurationShort } from '../../src/lib/format';
import { runAnswerSync } from '../../src/lib/sync';
import {
  ACTIVE_STUDY_SESSION_KEY,
  LAST_STUDY_SESSION_KEY,
  LEGACY_ACTIVE_STUDY_SESSION_KEY,
  LEGACY_LAST_STUDY_SESSION_KEY,
  emptyStudySessionStats,
  parsePersistedStudySession,
  sessionAccuracy,
  sessionModeDescription,
  sessionModeLabel,
  type PersistedStudySession,
  type StudySessionConfig,
  type StudySessionStats,
} from '../../src/lib/studySession';
import { useActiveResponseTimer } from '../../src/lib/useActiveResponseTimer';
import type { Confidence, Difficulty, Feedback, LearningEvent, MobileQuestion, StudySessionMode } from '../../src/lib/types';

const CONFIDENCE: Array<{ value: Confidence; label: string }> = [
  { value: 'low', label: 'Baixa' }, { value: 'medium', label: 'Média' }, { value: 'high', label: 'Alta' },
];
const DIFFICULTY: Array<{ value: Difficulty; label: string }> = [
  { value: 'easy', label: 'Fácil' }, { value: 'medium', label: 'Média' }, { value: 'hard', label: 'Difícil' },
];
const COUNTS = [5, 10, 15, 20];
const CACHED_QUESTION_POOL_KEY = 'cached_question_pool_v2';
const LEGACY_CACHED_BATCH_KEY = 'cached_question_batch_v1';
const RECENT_SESSION_HISTORY_KEY = 'recent_session_question_history_v1';
const MAX_CACHED_QUESTIONS = 120;
const ADAPTIVE_MICRO_BATCH_SIZE = 3;
const MODES: Array<{ value: StudySessionMode; icon: string; title: string }> = [
  { value: 'recommended', icon: '✦', title: 'Recomendado' },
  { value: 'review', icon: '↻', title: 'Revisões' },
  { value: 'errors', icon: '◎', title: 'Meus erros' },
  { value: 'subject', icon: '▦', title: 'Por matéria' },
];

type ViewMode = 'setup' | 'running' | 'summary' | 'offline_history';
type SessionSummary = { config: StudySessionConfig; stats: StudySessionStats; started_at: string; finished_at: string };

function studyTopicKey(question: MobileQuestion): string {
  return [question.subject, question.topic, question.lesson]
    .map((value) => String(value || '').trim().toLocaleLowerCase())
    .join('|');
}

async function readStringSet(key: string): Promise<Set<string>> {
  const raw = await getMeta(key);
  if (!raw) return new Set();
  try { return new Set((JSON.parse(raw) as string[]).map(String)); } catch { return new Set(); }
}

async function writeStringSet(key: string, values: Set<string>): Promise<void> {
  await setMeta(key, JSON.stringify(Array.from(values)));
}

async function readRecentSessionHistory(): Promise<string[][]> {
  const raw = await getMeta(RECENT_SESSION_HISTORY_KEY);
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) return [];
    return parsed.slice(0, 3).map((row) => Array.isArray(row) ? row.map(String) : []);
  } catch { return []; }
}

async function rememberSessionQuestions(refs: Array<{ id: string; revision: number }>): Promise<void> {
  const history = await readRecentSessionHistory();
  const next = [refs.map((ref) => String(ref.id)), ...history].slice(0, 3);
  await setMeta(RECENT_SESSION_HISTORY_KEY, JSON.stringify(next));
}

async function mergeCachedQuestionPool(batch: MobileQuestion[]): Promise<void> {
  let current: Array<{ id: string; revision: number }> = [];
  const raw = await getMeta(CACHED_QUESTION_POOL_KEY);
  if (raw) {
    try { current = JSON.parse(raw) as Array<{ id: string; revision: number }>; } catch { current = []; }
  }
  const merged = [...batch.map((q) => ({ id: q.question_id, revision: q.question_revision })), ...current];
  const seen = new Set<string>();
  const unique = merged.filter((ref) => {
    const key = `${ref.id}:${ref.revision}`;
    if (!ref.id || seen.has(key)) return false;
    seen.add(key);
    return true;
  }).slice(0, MAX_CACHED_QUESTIONS);
  await setMeta(CACHED_QUESTION_POOL_KEY, JSON.stringify(unique));
  // Mantém compatibilidade com instalações 0.8.x durante a primeira execução.
  await setMeta(LEGACY_CACHED_BATCH_KEY, JSON.stringify(batch.map((q) => ({ id: q.question_id, revision: q.question_revision }))));
}

function filterBatchForConfig(batch: MobileQuestion[], config: StudySessionConfig): MobileQuestion[] {
  const subject = config.subject.trim().toLocaleLowerCase();
  return batch.filter((question) => {
    if (config.mode === 'review') return Boolean(question.study_flags?.review_eligible ?? question.study_flags?.due);
    if (config.mode === 'errors') return Number(question.study_flags?.wrong_count || 0) > 0;
    if (config.mode === 'subject') return String(question.subject || '').trim().toLocaleLowerCase() === subject;
    return true;
  }).slice(0, config.count);
}

function selectionReasonLabel(reason: string | null | undefined): string {
  const normalized = String(reason || '').trim().toLocaleLowerCase('pt-BR');
  if (!normalized) return 'Selecionada pelo QuestFlow com base no seu histórico de estudo.';
  if (normalized.includes('correção/revisão marcada')) return 'Esta questão foi marcada para revisão antes de voltar ao fluxo normal.';
  if (normalized.includes('recuperação pós-erro')) return 'Você errou esta questão antes e ela chegou a um bom momento para tentar novamente.';
  if (normalized.includes('revisão fsrs vencida')) return 'Este conteúdo chegou ao momento de revisão para fortalecer a memória.';
  if (normalized.includes('questão nova')) return 'Esta é uma questão nova de um conteúdo que você já estudou.';
  if (normalized.includes('revisão antecipada por risco')) return 'O QuestFlow antecipou esta revisão porque a lembrança pode enfraquecer em breve.';
  if (normalized.includes('prioridade adaptativa')) return 'Selecionada pelo QuestFlow com base no seu histórico de estudo.';
  return 'Selecionada pelo QuestFlow porque este item ajuda a avançar a sua sessão atual.';
}

function transferReasonLabel(reason: string | null | undefined): string {
  const normalized = String(reason || '').trim().toLocaleLowerCase('pt-BR');
  if (normalized.includes('misconception')) return 'A formulação também verifica um conceito ligado a um erro recente.';
  if (normalized.includes('uncertain_knowledge')) return 'A formulação também verifica um conceito em que sua evidência ainda é incerta.';
  return 'Esta questão também verifica o mesmo conceito em uma formulação diferente.';
}

function summaryCoach(stats: StudySessionStats): string {
  const accuracy = sessionAccuracy(stats);
  if (stats.answered === 0) return 'Sessão encerrada sem respostas contabilizadas. Você pode iniciar um novo bloco quando quiser.';
  if (accuracy == null) return 'A sessão foi concluída. Continue sincronizando para consolidar os resultados no seu histórico.';
  if (accuracy >= 0.85) return 'Ótima sessão. O desempenho está forte; mantenha a regularidade e avance para o próximo bloco.';
  if (accuracy >= 0.65) return 'Boa base, com espaço para consolidar alguns pontos. Revise os erros antes da próxima sessão.';
  return 'Esta sessão revelou pontos frágeis. Priorize revisão dos erros antes de aumentar a quantidade de questões.';
}

export default function QuestionsScreen() {
  const { session, bootstrap, api, syncNow, syncing, lastSync } = useQuestFlow();
  const projectId = String(bootstrap?.active_project?.id || '');
  const subjects = useMemo(() => Array.from(new Set((bootstrap?.progress?.subjects || []).map((item) => item.label).filter(Boolean))).sort((a, b) => a.localeCompare(b)), [bootstrap?.progress?.subjects]);

  const [viewMode, setViewMode] = useState<ViewMode>('setup');
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState('');
  const [questions, setQuestions] = useState<MobileQuestion[]>([]);
  const [active, setActive] = useState<PersistedStudySession | null>(null);
  const [resumeCandidate, setResumeCandidate] = useState<PersistedStudySession | null>(null);
  const [summary, setSummary] = useState<SessionSummary | null>(null);
  const [setupMode, setSetupMode] = useState<StudySessionMode>('recommended');
  const [setupCount, setSetupCount] = useState(10);
  const [setupSubject, setSetupSubject] = useState('');
  const [feedback, setFeedbackState] = useState<Feedback | null>(null);
  const [explanationOpen, setExplanationOpen] = useState(false);
  const [awaitingFeedback, setAwaitingFeedback] = useState(false);
  const [prefetching, setPrefetching] = useState(false);
  const [questionScreenFocused, setQuestionScreenFocused] = useState(true);
  const [offlinePack, setOfflinePack] = useState<{ count: number; generated_at: string; pack_id: string; source: string } | null>(null);
  const [offlineHistoryInfo, setOfflineHistoryInfo] = useState<{ total: number; resolved: number; pending: number }>({ total: 0, resolved: 0, pending: 0 });
  const [offlineHistory, setOfflineHistory] = useState<OfflineAttemptHistoryItem[]>([]);
  const [offlineHistoryLoading, setOfflineHistoryLoading] = useState(false);
  const [offlineHistoryMessage, setOfflineHistoryMessage] = useState('');
  const [offlineExpandedAttempt, setOfflineExpandedAttempt] = useState('');

  const current = active ? questions[active.index] || null : null;
  const phase = active?.phase || 'answer';
  const selected = active?.selected ?? null;
  const confidence = active?.confidence ?? null;
  const difficulty = active?.difficulty ?? null;
  const eliminated = active?.eliminated ?? [];
  const { interaction, snapshot, live } = useActiveResponseTimer(
    current && active ? `${current.question_id}:${current.question_revision}:${active.attempt_id}` : 'none',
    questionScreenFocused && viewMode === 'running',
  );

  useFocusEffect(useCallback(() => {
    setQuestionScreenFocused(true);
    return () => setQuestionScreenFocused(false);
  }, []));


  useEffect(() => {
    refreshOfflineHistory(viewMode === 'offline_history').catch(() => undefined);
  }, [lastSync?.cursor, lastSync?.feedbackResolved]);

  const persistActive = async (next: PersistedStudySession) => {
    const stamped = { ...next, updated_at: new Date().toISOString() };
    setActive(stamped);
    await setMeta(ACTIVE_STUDY_SESSION_KEY, JSON.stringify(stamped));
    return stamped;
  };

  const clearActivePersisted = async () => {
    setActive(null);
    setResumeCandidate(null);
    await setMeta(ACTIVE_STUDY_SESSION_KEY, '');
  };

  const refreshOfflineHistory = async (withItems = false) => {
    const info = await offlineAttemptHistoryInfo();
    setOfflineHistoryInfo(info);
    if (withItems) setOfflineHistory(await listOfflineAttemptHistory(100));
    return info;
  };

  const openOfflineHistory = async () => {
    setOfflineHistoryLoading(true);
    setOfflineHistoryMessage('');
    setViewMode('offline_history');
    try { await refreshOfflineHistory(true); } finally { setOfflineHistoryLoading(false); }
  };

  const syncOfflineHistory = async () => {
    setOfflineHistoryLoading(true);
    setOfflineHistoryMessage('');
    try {
      const result = await syncNow();
      await refreshOfflineHistory(true);
      setOfflineHistoryMessage(result?.online && result.reachable && !result.failed
        ? (result.feedbackResolved ? `${result.feedbackResolved} resultado(s) offline atualizado(s).` : 'Sincronização concluída. Não há novos resultados disponíveis neste momento.')
        : 'Ainda não foi possível alcançar o QuestFlow. As respostas continuam preservadas no aparelho.');
    } finally {
      setOfflineHistoryLoading(false);
    }
  };

  const queue = async (eventType: LearningEvent['event_type'], payload: Record<string, unknown> = {}, overrides: Partial<LearningEvent> = {}) => {
    if (!session || !active) return null;
    const event = createLearningEvent({
      event_type: eventType,
      device_id: session.deviceId,
      session_id: active.session_id,
      attempt_id: active.attempt_id,
      exam_project_id: projectId,
      question_id: current?.question_id,
      question_revision: current?.question_revision,
      payload,
      ...overrides,
    });
    await enqueueEvent(event);
    return event;
  };

  const restoreInitialState = async () => {
    setLoading(true);
    try {
      const currentRaw = await getMeta(ACTIVE_STUDY_SESSION_KEY);
      const legacyRaw = currentRaw ? null : await getMeta(LEGACY_ACTIVE_STUDY_SESSION_KEY);
      const candidate = parsePersistedStudySession(currentRaw || legacyRaw);
      if (candidate && legacyRaw && !currentRaw) await setMeta(ACTIVE_STUDY_SESSION_KEY, JSON.stringify(candidate));
      setResumeCandidate(candidate);
      setOfflinePack(await offlineStudyPackInfo());
      setOfflineHistoryInfo(await offlineAttemptHistoryInfo());
      const rawSummary = await getMeta(LAST_STUDY_SESSION_KEY) || await getMeta(LEGACY_LAST_STUDY_SESSION_KEY);
      if (rawSummary) {
        try { setSummary(JSON.parse(rawSummary) as SessionSummary); } catch { /* ignore */ }
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { restoreInitialState().catch(() => setLoading(false)); }, []);

  useEffect(() => {
    if (!current || !session || !active || viewMode !== 'running') return;
    (async () => {
      const boundary = active.adaptive?.boundaries?.find((item) => active.index >= item.start_index && active.index <= item.end_index);
      await queue('question_presented', {
        position: active.index + 1,
        planned_questions: active.config.count,
        served_questions: questions.length,
        micro_batch_id: boundary?.batch_id || active.adaptive?.current_batch_id || null,
        micro_batch_position: boundary ? active.index - boundary.start_index + 1 : null,
        plan_revision: boundary?.plan_revision ?? active.adaptive?.plan_revision ?? null,
        strategy_profile: active.adaptive?.strategy_profile || null,
        session_mode: active.config.mode,
        selection: current.selection || null,
      });
      await queue('question_opened', {});
    })().catch(() => undefined);
  }, [current?.question_id, current?.question_revision, active?.index, active?.attempt_id, session?.deviceId, viewMode]);

  useEffect(() => {
    if (!feedback || !active) return;
    queue('result_seen', { is_correct: feedback.is_correct }).catch(() => undefined);
  }, [feedback?.attempt_id]);

  const blockedFilter = async (batch: MobileQuestion[]) => {
    const blockedTopics = await readStringSet('study_backlog_topic_keys_v1');
    const blockedCorrections = await readStringSet('correction_question_ids_v1');
    return batch.filter((question) => !blockedTopics.has(studyTopicKey(question)) && !blockedCorrections.has(question.question_id));
  };

  const rotatePreviousBlock = async (batch: MobileQuestion[], config: StudySessionConfig) => {
    if (config.mode === 'review' || config.mode === 'errors') return batch;
    const history = await readRecentSessionHistory();
    const previousBlock = new Set((history[0] || []).map(String));
    if (!previousBlock.size) return batch;
    return batch.filter((question) => !previousBlock.has(question.question_id));
  };

  const loadOfflineStudyPack = async (config: StudySessionConfig, excludedIds: string[] = [], limitOverride = 0): Promise<MobileQuestion[]> => {
    const stored = await getOfflineStudyPackQuestions();
    if (!stored.length) return [];
    const excluded = new Set(excludedIds.map(String));
    const compatible = filterBatchForConfig(stored, { ...config, count: MAX_CACHED_QUESTIONS })
      .filter((question) => !excluded.has(question.question_id));
    const rotated = await rotatePreviousBlock(compatible, config);
    return blockedFilter(rotated.slice(0, limitOverride > 0 ? limitOverride : config.count));
  };

  const loadCachedBatch = async (config: StudySessionConfig, excludedIds: string[] = [], limitOverride = 0): Promise<MobileQuestion[]> => {
    const poolRaw = await getMeta(CACHED_QUESTION_POOL_KEY);
    const legacyRaw = await getMeta(LEGACY_CACHED_BATCH_KEY);
    const raw = poolRaw || legacyRaw;
    if (!raw) return [];
    try {
      const refs = JSON.parse(raw) as Array<{ id: string; revision: number }>;
      const cached: MobileQuestion[] = [];
      for (const ref of refs) {
        const q = await getCachedQuestion(ref.id, ref.revision);
        if (q) cached.push(q);
      }
      const excluded = new Set(excludedIds.map(String));
      const compatible = filterBatchForConfig(cached, { ...config, count: MAX_CACHED_QUESTIONS }).filter((q) => !excluded.has(q.question_id));
      const rotated = await rotatePreviousBlock(compatible, config);
      return rotated.slice(0, limitOverride > 0 ? limitOverride : config.count);
    } catch { return []; }
  };

  const beginSession = async () => {
    const config: StudySessionConfig = { mode: setupMode, count: setupCount, subject: setupMode === 'subject' ? setupSubject : '' };
    if (config.mode === 'subject' && !config.subject) {
      setMessage('Escolha uma matéria antes de iniciar a sessão.');
      return;
    }
    setLoading(true);
    setMessage('');
    try {
      const sessionId = Crypto.randomUUID();
      let batch: MobileQuestion[] = [];
      let adaptive: PersistedStudySession['adaptive'] = null;
      if (api) {
        try {
          const planned = await api.startAdaptiveSession({
            session_id: sessionId,
            count: config.count,
            exam_project_id: projectId,
            mode: config.mode,
            subject: config.subject,
            micro_batch_size: ADAPTIVE_MICRO_BATCH_SIZE,
          });
          batch = planned.micro_batch?.questions || [];
          for (const question of batch) await cacheQuestion(question);
          await mergeCachedQuestionPool(batch);
          adaptive = {
            enabled: true,
            source: 'questflow_orchestrator',
            micro_batch_size: Number(planned.micro_batch_size || ADAPTIVE_MICRO_BATCH_SIZE),
            current_batch_id: String(planned.micro_batch?.batch_id || ''),
            current_batch_ordinal: Number(planned.micro_batch?.ordinal || 1),
            plan_revision: Number(planned.micro_batch?.plan_revision || 1),
            strategy_profile: String(planned.micro_batch?.strategy_profile || 'balanced'),
            goal: planned.goal || null,
            boundaries: batch.length ? [{ batch_id: String(planned.micro_batch?.batch_id || ''), start_index: 0, end_index: batch.length - 1, plan_revision: Number(planned.micro_batch?.plan_revision || 1) }] : [],
            prefetched: null,
          };
        } catch (error) {
          batch = await loadOfflineStudyPack(config, [], config.count);
          let source = 'studio_offline_pack';
          if (!batch.length) {
            batch = await loadCachedBatch(config, [], config.count);
            source = 'offline_fallback';
          }
          if (batch.length) {
            setMessage(source === 'studio_offline_pack'
              ? 'Sem conexão com o Studio. Usando a Reserva Offline escolhida pelo Learning Engine na última sincronização.'
              : 'Sem conexão com o Studio. Usando questões antigas ainda disponíveis no cache local.');
            adaptive = {
              enabled: false, source, micro_batch_size: batch.length,
              current_batch_id: source === 'studio_offline_pack' ? 'offline-pack' : 'offline-cache', current_batch_ordinal: 1, plan_revision: 0, strategy_profile: source, goal: null,
              boundaries: [{ batch_id: source === 'studio_offline_pack' ? 'offline-pack' : 'offline-cache', start_index: 0, end_index: batch.length - 1, plan_revision: 0 }], prefetched: null,
            };
          } else throw error;
        }
      } else {
        batch = await loadOfflineStudyPack(config, [], config.count);
        let source = 'studio_offline_pack';
        if (!batch.length) {
          batch = await loadCachedBatch(config, [], config.count);
          source = 'offline_fallback';
        }
        if (batch.length) adaptive = { enabled: false, source, micro_batch_size: batch.length, current_batch_id: source === 'studio_offline_pack' ? 'offline-pack' : 'offline-cache', current_batch_ordinal: 1, plan_revision: 0, strategy_profile: source, goal: null, boundaries: [{ batch_id: source === 'studio_offline_pack' ? 'offline-pack' : 'offline-cache', start_index: 0, end_index: batch.length - 1, plan_revision: 0 }], prefetched: null };
      }
      batch = await blockedFilter(filterBatchForConfig(
        await rotatePreviousBlock(batch, config),
        { ...config, count: MAX_CACHED_QUESTIONS },
      ));
      if (adaptive?.boundaries?.length && batch.length) {
        adaptive = {
          ...adaptive,
          boundaries: [{ batch_id: String(adaptive.boundaries[0]?.batch_id || adaptive.current_batch_id || ''), start_index: 0, end_index: batch.length - 1, plan_revision: Number(adaptive.boundaries[0]?.plan_revision ?? adaptive.plan_revision ?? 0) }],
        };
      }
      if (!batch.length) {
        setMessage(config.mode === 'review'
          ? 'Não há revisões disponíveis neste momento.'
          : config.mode === 'errors'
            ? 'Não encontrei questões com histórico de erro disponíveis para esta sessão.'
            : config.mode === 'subject'
              ? `Não há questões disponíveis para ${config.subject}.`
              : 'Nenhuma questão disponível para iniciar a sessão.');
        return;
      }
      const now = new Date().toISOString();
      const next: PersistedStudySession = {
        version: 3,
        session_id: sessionId,
        config: { ...config },
        question_refs: batch.map((q) => ({ id: q.question_id, revision: q.question_revision })),
        index: 0,
        stats: emptyStudySessionStats(),
        counted_attempt_ids: [],
        attempt_id: Crypto.randomUUID(),
        phase: 'answer',
        selected: null,
        eliminated: [],
        confidence: null,
        difficulty: null,
        submitted_active_seconds: 0,
        adaptive,
        started_at: now,
        updated_at: now,
      };
      setQuestions(batch);
      setFeedbackState(null);
      setExplanationOpen(false);
      setAwaitingFeedback(false);
      await persistActive(next);
      setResumeCandidate(null);
      setViewMode('running');
      if (session) {
        await enqueueEvent(createLearningEvent({
          event_type: 'session_started',
          device_id: session.deviceId,
          session_id: next.session_id,
          exam_project_id: projectId,
          payload: {
            planned_questions: config.count,
            source: 'mobile_0.11',
            adaptive_orchestrator: Boolean(adaptive?.enabled),
            micro_batch_size: adaptive?.micro_batch_size || null,
            session_goal: adaptive?.goal || null,
            session_mode: config.mode,
            session_mode_label: sessionModeLabel(config.mode),
            subject: config.subject || null,
          },
        }));
      }
    } catch (error) {
      setMessage((error as Error)?.message || 'Não foi possível iniciar a sessão.');
    } finally {
      setLoading(false);
    }
  };

  const restoreFeedbackForResume = async (candidate: PersistedStudySession) => {
    if (candidate.phase !== 'result') return;
    const local = await getLocalAttempt(candidate.attempt_id);
    if (local?.feedback_json) {
      try {
        const restoredFeedback = JSON.parse(local.feedback_json) as Feedback;
        setFeedbackState(restoredFeedback);
        await countFeedback(restoredFeedback, candidate);
        return;
      } catch { /* continue */ }
    }
    setAwaitingFeedback(true);
    if (!api) return;
    try {
      await syncNow();
      const result = await api.feedback(candidate.attempt_id);
      setFeedbackState(result);
      setAwaitingFeedback(false);
      await saveFeedback(candidate.attempt_id, result);
      await countFeedback(result, candidate);
    } catch {
      // The answer stays preserved locally; the user can retry from the result screen.
    }
  };

  const resumeSession = async (candidate = resumeCandidate) => {
    if (!candidate) return;
    setLoading(true);
    setMessage('');
    try {
      const restored: MobileQuestion[] = [];
      for (const ref of candidate.question_refs) {
        const question = await getCachedQuestion(ref.id, ref.revision);
        if (question) restored.push(question);
      }
      if (!restored.length || restored.length !== candidate.question_refs.length) {
        await clearActivePersisted();
        setMessage('A sessão anterior não pode ser retomada porque o lote local não está completo. Inicie uma nova sessão.');
        return;
      }
      setQuestions(restored);
      setActive(candidate);
      setFeedbackState(null);
      setExplanationOpen(false);
      setAwaitingFeedback(false);
      setViewMode('running');
      await restoreFeedbackForResume(candidate);
    } finally {
      setLoading(false);
    }
  };

  const discardResume = () => {
    Alert.alert('Descartar sessão interrompida?', 'O histórico já sincronizado permanece no QuestFlow. Apenas o ponto de retomada deste lote será removido.', [
      { text: 'Cancelar', style: 'cancel' },
      { text: 'Descartar', style: 'destructive', onPress: () => clearActivePersisted().catch(() => undefined) },
    ]);
  };

  const updateAnswerState = async (patch: Partial<PersistedStudySession>) => {
    if (!active) return;
    await persistActive({ ...active, ...patch });
  };

  const choose = async (choice: number) => {
    if (!active) return;
    interaction();
    const changed = active.selected !== null && active.selected !== choice;
    const nextEliminated = (active.eliminated || []).filter((item) => item !== choice);
    await updateAnswerState({ selected: choice, eliminated: nextEliminated });
    await queue(changed ? 'answer_changed' : 'answer_selected', { selected_index: choice, previous_index: active.selected });
  };

  const toggleEliminated = async (choice: number) => {
    if (!active || phase !== 'answer') return;
    interaction();
    const currentSet = new Set(active.eliminated || []);
    if (currentSet.has(choice)) currentSet.delete(choice); else currentSet.add(choice);
    const next = Array.from(currentSet).sort((a, b) => a - b);
    await updateAnswerState({ eliminated: next, selected: active.selected === choice && next.includes(choice) ? null : active.selected });
  };

  const countFeedback = async (result: Feedback, base = active) => {
    if (!base || base.counted_attempt_ids.includes(base.attempt_id)) return base;
    const stats = { ...base.stats };
    stats.answered += 1;
    if (result.is_correct) stats.correct += 1; else stats.wrong += 1;
    stats.active_seconds += Math.max(0, Number(base.submitted_active_seconds || result.timing.active_response_seconds || 0));
    const next = { ...base, stats, counted_attempt_ids: [...base.counted_attempt_ids, base.attempt_id] };
    await persistActive(next);
    return next;
  };

  const submit = async () => {
    if (!active || active.selected == null || !active.confidence || !current || !session) return;
    interaction();
    setMessage('');
    const timing = snapshot();
    await saveLocalAttempt({
      attemptId: active.attempt_id,
      questionId: current.question_id,
      questionRevision: current.question_revision,
      selectedIndex: active.selected,
      confidence: active.confidence,
      perceivedDifficulty: active.difficulty || undefined,
      answeredOffline: ['studio_offline_pack', 'offline_fallback'].includes(String(active.adaptive?.source || '')),
      offlineSource: ['studio_offline_pack', 'offline_fallback'].includes(String(active.adaptive?.source || '')) ? String(active.adaptive?.source || '') : '',
    });
    const responseEvents: LearningEvent[] = [];
    const confidenceEvent = await queue('confidence_reported', { confidence: active.confidence });
    if (confidenceEvent) responseEvents.push(confidenceEvent);
    if (active.difficulty) {
      const difficultyEvent = await queue('difficulty_reported', { perceived_difficulty: active.difficulty });
      if (difficultyEvent) responseEvents.push(difficultyEvent);
    }
    const answerEvent = await queue('answer_submitted', {
      selected_index: active.selected,
      confidence: active.confidence,
      perceived_difficulty: active.difficulty,
      ...timing,
    });
    if (answerEvent) responseEvents.push(answerEvent);
    const submitted = await persistActive({ ...active, phase: 'result', submitted_active_seconds: timing.active_response_seconds });
    const offlineOrigin = ['studio_offline_pack', 'offline_fallback'].includes(String(active.adaptive?.source || ''));
    // Em uma questão da Reserva Offline, salvar localmente é o estado normal. Não
    // mostre um spinner de "esperando o Studio" enquanto tentamos uma
    // sincronização oportunista em segundo plano.
    setAwaitingFeedback(!offlineOrigin);
    setFeedbackState(null);
    const sync = api
      ? await runAnswerSync(api, session.apiBaseUrl || 'default', projectId, active.attempt_id, responseEvents)
      : null;
    if (!sync?.online || !sync.reachable || sync.failed) {
      setAwaitingFeedback(false);
      await markAttemptAnsweredOffline(active.attempt_id, offlineOrigin ? String(active.adaptive?.source || '') : 'network_unavailable');
      await refreshOfflineHistory(false);
      setMessage('Resposta salva no aparelho. Não há conexão em andamento. Quando a sincronização voltar, o resultado ficará em “Respondidas offline”.');
      return;
    }
    if (sync.feedback) {
      setFeedbackState(sync.feedback);
      setAwaitingFeedback(false);
      await countFeedback(sync.feedback, submitted);
      // A resposta rápida já deixou a tentativa durável. Reserva offline,
      // bootstrap e demais eventos seguem no próximo ciclo sem competir com a
      // navegação da tela de questões.
    } else {
      setAwaitingFeedback(true);
      await fetchFeedback(submitted);
    }
    await refreshOfflineHistory(false);
  };

  const fetchFeedback = async (base = active) => {
    if (!api || !base) return;
    try {
      const result = await api.feedback(base.attempt_id);
      setFeedbackState(result);
      setAwaitingFeedback(false);
      await saveFeedback(base.attempt_id, result);
      await countFeedback(result, base);
      await refreshOfflineHistory(false);
    } catch (error) {
      setAwaitingFeedback(false);
      setMessage((error as Error)?.message || 'A resposta está salva, mas o feedback ainda não está disponível.');
    }
  };

  const retryFeedback = async () => {
    const sync = await syncNow();
    if (sync?.online && sync.reachable && !sync.failed) await fetchFeedback();
  };

  const markExplanationOpen = async () => {
    interaction();
    if (!explanationOpen) await queue('explanation_opened', {});
    setExplanationOpen((value) => !value);
  };

  const resetForNextQuestion = (base: PersistedStudySession, nextIndex: number, stats = base.stats): PersistedStudySession => ({
    ...base,
    index: nextIndex,
    stats,
    attempt_id: Crypto.randomUUID(),
    phase: 'answer',
    selected: null,
    eliminated: [],
    confidence: null,
    difficulty: null,
    submitted_active_seconds: 0,
  });

  const finalizeSession = async (stats: StudySessionStats, reason = 'completed') => {
    if (!active) return;
    const finished = new Date().toISOString();
    const finalSummary: SessionSummary = { config: active.config, stats, started_at: active.started_at, finished_at: finished };
    if (session) {
      await enqueueEvent(createLearningEvent({
        event_type: 'session_ended',
        device_id: session.deviceId,
        session_id: active.session_id,
        exam_project_id: projectId,
        payload: {
          reason,
          planned_questions: active.config.count,
          answered: stats.answered,
          correct: stats.correct,
          wrong: stats.wrong,
          skipped: stats.skipped,
          active_response_seconds: Math.round(stats.active_seconds * 10) / 10,
          session_mode: active.config.mode,
          subject: active.config.subject || null,
        },
      }));
    }
    await setMeta(LAST_STUDY_SESSION_KEY, JSON.stringify(finalSummary));
    await rememberSessionQuestions(active.question_refs);
    await clearActivePersisted();
    setQuestions([]);
    setFeedbackState(null);
    setSummary(finalSummary);
    setViewMode('summary');
    syncNow().catch(() => undefined);
  };

  const appendMicroBatch = async (base: PersistedStudySession, batch: MobileQuestion[], meta: { batch_id: string; ordinal: number; plan_revision: number; strategy_profile: string; goal?: import('../../src/lib/types').AdaptiveSessionGoal | null }): Promise<PersistedStudySession> => {
    if (!batch.length) return base;
    for (const question of batch) await cacheQuestion(question);
    await mergeCachedQuestionPool(batch);
    const questionMap = new Map(questions.map((question) => [`${question.question_id}:${question.question_revision}`, question]));
    const existingQuestions = base.question_refs
      .map((ref) => questionMap.get(`${ref.id}:${ref.revision}`))
      .filter((question): question is MobileQuestion => Boolean(question));
    const startIndex = existingQuestions.length;
    const mergedQuestions = [...existingQuestions, ...batch];
    setQuestions(mergedQuestions);
    const nextAdaptive = base.adaptive ? {
      ...base.adaptive,
      source: 'questflow_orchestrator',
      current_batch_id: meta.batch_id,
      current_batch_ordinal: meta.ordinal,
      plan_revision: meta.plan_revision,
      strategy_profile: meta.strategy_profile,
      goal: meta.goal || base.adaptive.goal,
      prefetched: null,
      boundaries: [...(base.adaptive.boundaries || []), { batch_id: meta.batch_id, start_index: startIndex, end_index: startIndex + batch.length - 1, plan_revision: meta.plan_revision }],
    } : null;
    return persistActive({
      ...base,
      adaptive: nextAdaptive,
      question_refs: [...base.question_refs, ...batch.map((q) => ({ id: q.question_id, revision: q.question_revision }))],
    });
  };

  const prefetchNextMicroBatch = async (base: PersistedStudySession) => {
    if (!api || !base.adaptive?.enabled || base.adaptive.prefetched || prefetching) return;
    if (base.question_refs.length >= base.config.count) return;
    setPrefetching(true);
    try {
      const planned = await api.nextAdaptiveMicroBatch(base.session_id, {
        purpose: 'prefetch',
        excluded_question_ids: base.question_refs.map((ref) => ref.id),
      });
      const batch = planned.micro_batch?.questions || [];
      if (!batch.length) return;
      for (const question of batch) await cacheQuestion(question);
      await mergeCachedQuestionPool(batch);
      const latest = active && active.session_id === base.session_id ? active : base;
      if (!latest.adaptive?.enabled || latest.adaptive.prefetched) return;
      await persistActive({
        ...latest,
        adaptive: {
          ...latest.adaptive,
          prefetched: {
            batch_id: String(planned.micro_batch?.batch_id || ''),
            ordinal: Number(planned.micro_batch?.ordinal || latest.adaptive.current_batch_ordinal + 1),
            plan_revision: Number(planned.micro_batch?.plan_revision || latest.adaptive.plan_revision + 1),
            strategy_profile: String(planned.micro_batch?.strategy_profile || latest.adaptive.strategy_profile),
            refs: batch.map((q) => ({ id: q.question_id, revision: q.question_revision })),
          },
        },
      });
    } catch {
      // Prefetch é otimização; falha não interrompe a sessão.
    } finally {
      setPrefetching(false);
    }
  };

  const loadNextAdaptiveMicroBatch = async (base: PersistedStudySession, forceReplan = false): Promise<boolean> => {
    const remaining = Math.max(0, base.config.count - base.question_refs.length);
    if (remaining <= 0) return false;
    let batch: MobileQuestion[] = [];
    if (api && base.adaptive?.enabled) {
      try {
        const prefetchedId = base.adaptive.prefetched?.batch_id || '';
        const planned = await api.nextAdaptiveMicroBatch(base.session_id, {
          purpose: 'active',
          prefetched_batch_id: prefetchedId,
          force_replan: forceReplan,
          excluded_question_ids: base.question_refs.map((ref) => ref.id),
        });
        batch = planned.micro_batch?.questions || [];
        if (batch.length) {
          const updated = await appendMicroBatch(base, batch, {
            batch_id: String(planned.micro_batch?.batch_id || ''),
            ordinal: Number(planned.micro_batch?.ordinal || (base.adaptive.current_batch_ordinal + 1)),
            plan_revision: Number(planned.micro_batch?.plan_revision || (base.adaptive.plan_revision + 1)),
            strategy_profile: String(planned.micro_batch?.strategy_profile || base.adaptive.strategy_profile),
            goal: planned.goal || base.adaptive.goal,
          });
          if (forceReplan) setMessage('O QuestFlow reajustou as próximas questões com base no que acabou de acontecer nesta sessão.');
          setFeedbackState(null);
          setExplanationOpen(false);
          setAwaitingFeedback(false);
          await persistActive(resetForNextQuestion(updated, base.question_refs.length));
          return true;
        }
      } catch {
        // Continua abaixo com fallback local seguro.
      }
    }
    batch = await loadCachedBatch(base.config, base.question_refs.map((ref) => ref.id), Math.min(base.adaptive?.micro_batch_size || ADAPTIVE_MICRO_BATCH_SIZE, remaining));
    batch = await blockedFilter(batch);
    if (!batch.length) return false;
    const meta = {
      batch_id: `offline-${Date.now()}`,
      ordinal: Number(base.adaptive?.current_batch_ordinal || 0) + 1,
      plan_revision: Number(base.adaptive?.plan_revision || 0),
      strategy_profile: 'offline_fallback',
    };
    const updated = await appendMicroBatch(base, batch, meta);
    setMessage('A conexão caiu. O QuestFlow continuou a sessão com um pequeno lote já armazenado e voltará a adaptar quando sincronizar.');
    setFeedbackState(null);
    setExplanationOpen(false);
    setAwaitingFeedback(false);
    await persistActive(resetForNextQuestion(updated, base.question_refs.length));
    return true;
  };

  const nextQuestion = async (forceReplan = false, baseOverride: PersistedStudySession | null = null) => {
    if (!active && !baseOverride) return;
    let currentActive = baseOverride || active!;
    if (current && currentActive.adaptive?.source === 'studio_offline_pack') {
      await markOfflineStudyPackConsumed(current.question_id, current.question_revision);
      setOfflinePack(await offlineStudyPackInfo());
    }
    if (currentActive.index + 1 < questions.length) {
      // Dentro do micro-lote, mantém interleaving decidido pelo QuestFlow. A única
      // exceção local é uma transferência conceitual já entregue no mesmo lote.
      if ((currentActive.confidence === 'low' || currentActive.confidence === 'medium') && current) {
        const currentSubject = String(current.subject || '').trim().toLocaleLowerCase();
        const currentTopic = String(current.topic || '').trim().toLocaleLowerCase();
        const transferIndex = questions.findIndex((question, index) =>
          index > currentActive.index + 1
          && question.question_id !== current.question_id
          && String(question.subject || '').trim().toLocaleLowerCase() === currentSubject
          && String(question.topic || '').trim().toLocaleLowerCase() === currentTopic,
        );
        if (transferIndex > currentActive.index + 1) {
          const reorderedQuestions = [...questions];
          const [transferQuestion] = reorderedQuestions.splice(transferIndex, 1);
          if (transferQuestion) reorderedQuestions.splice(currentActive.index + 1, 0, transferQuestion);
          const reorderedRefs = reorderedQuestions.map((question) => ({ id: question.question_id, revision: question.question_revision }));
          setQuestions(reorderedQuestions);
          currentActive = { ...currentActive, question_refs: reorderedRefs };
        }
      }
      setFeedbackState(null);
      setExplanationOpen(false);
      setAwaitingFeedback(false);
      const moved = await persistActive(resetForNextQuestion(currentActive, currentActive.index + 1));
      const boundary = moved.adaptive?.boundaries?.find((item) => item.end_index === moved.index);
      if (boundary && moved.question_refs.length < moved.config.count) prefetchNextMicroBatch(moved).catch(() => undefined);
      return;
    }
    const completed = currentActive.stats.answered + currentActive.stats.skipped;
    if (currentActive.adaptive?.enabled && completed < currentActive.config.count) {
      const loaded = await loadNextAdaptiveMicroBatch(currentActive, forceReplan);
      if (loaded) return;
    }
    await finalizeSession(currentActive.stats, 'completed');
  };

  const continueWithoutFeedback = async () => {
    if (!active) return;
    interaction();
    if (active.counted_attempt_ids.includes(active.attempt_id)) {
      await nextQuestion(false, active);
      return;
    }
    const stats = {
      ...active.stats,
      answered: active.stats.answered + 1,
      pending_results: Number(active.stats.pending_results || 0) + 1,
      active_seconds: active.stats.active_seconds + Math.max(0, Number(active.submitted_active_seconds || 0)),
    };
    const updated = await persistActive({
      ...active,
      stats,
      counted_attempt_ids: [...active.counted_attempt_ids, active.attempt_id],
    });
    setAwaitingFeedback(false);
    await refreshOfflineHistory(false);
    setMessage('Resposta guardada. O Studio corrigirá e recalibrará o Learning Engine assim que a sincronização voltar. Depois você verá o resultado em “Respondidas offline”.');
    await nextQuestion(false, updated);
  };

  const finishUnderstanding = async (gap: boolean) => {
    interaction();
    if (gap) await queue('learning_gap_reported', { learning_gap: true });
    await queue('explanation_finished', { understood: !gap, learning_gap: gap });
    const misconception = Boolean(feedback && !feedback.is_correct && active?.confidence === 'high');
    await nextQuestion(Boolean(gap || misconception));
    syncNow().catch(() => undefined);
  };

  const skip = async () => {
    if (!active) return;
    interaction();
    if (current && active.adaptive?.source === 'studio_offline_pack') {
      await markOfflineStudyPackConsumed(current.question_id, current.question_revision);
      setOfflinePack(await offlineStudyPackInfo());
    }
    await queue('question_skipped', { selected_index: active.selected });
    const stats = { ...active.stats, skipped: active.stats.skipped + 1 };
    if (active.index + 1 < questions.length) {
      setFeedbackState(null);
      const moved = await persistActive(resetForNextQuestion(active, active.index + 1, stats));
      const boundary = moved.adaptive?.boundaries?.find((item) => item.end_index === moved.index);
      if (boundary && moved.question_refs.length < moved.config.count) prefetchNextMicroBatch(moved).catch(() => undefined);
      syncNow().catch(() => undefined);
    } else if (active.adaptive?.enabled && stats.answered + stats.skipped < active.config.count) {
      const base = await persistActive({ ...active, stats });
      if (!await loadNextAdaptiveMicroBatch(base, false)) await finalizeSession(stats, 'completed_with_skips');
      syncNow().catch(() => undefined);
    } else {
      await finalizeSession(stats, 'completed_with_skips');
    }
  };

  const advanceRemoving = async (predicate: (question: MobileQuestion) => boolean) => {
    if (!active) return;
    const remaining = questions.filter((question, position) => position < active.index || !predicate(question));
    if (!remaining.length) {
      const base = await persistActive({
        ...active,
        question_refs: [],
        index: 0,
        adaptive: active.adaptive ? { ...active.adaptive, boundaries: [], prefetched: null } : null,
      });
      await syncNow();
      if (active.adaptive?.enabled && active.stats.answered + active.stats.skipped < active.config.count) {
        if (await loadNextAdaptiveMicroBatch(base, true)) return;
      }
      await finalizeSession(active.stats, 'preanswer_triage');
      return;
    }
    const nextIndex = Math.min(active.index, remaining.length - 1);
    setQuestions(remaining);
    setFeedbackState(null);
    setExplanationOpen(false);
    setAwaitingFeedback(false);
    await persistActive({
      ...resetForNextQuestion(active, nextIndex),
      question_refs: remaining.map((q) => ({ id: q.question_id, revision: q.question_revision })),
      config: active.adaptive?.enabled ? active.config : { ...active.config, count: remaining.length },
    });
  };

  const requestCorrection = async () => {
    if (!current) return;
    interaction();
    setMessage('');
    await queue('question_correction_requested', { source: 'mobile_preanswer', note: 'Solicitação feita antes de responder no aplicativo.' });
    const blocked = await readStringSet('correction_question_ids_v1');
    blocked.add(current.question_id);
    await writeStringSet('correction_question_ids_v1', blocked);
    const sync = await syncNow();
    setMessage(sync?.online && sync.reachable && !sync.failed
      ? 'Questão enviada para a fila de correções. Ela não foi contabilizada como tentativa.'
      : 'Solicitação salva no aparelho e será enviada quando a sincronização voltar.');
    const uid = current.question_id;
    await advanceRemoving((question) => question.question_id === uid);
  };

  const confirmCorrection = () => Alert.alert(
    'Corrigir questão',
    'A questão será retirada desta sessão e enviada para a fila de correções do Studio. Nenhum acerto ou erro será contabilizado.',
    [
      { text: 'Cancelar', style: 'cancel' },
      { text: 'Enviar para correção', style: 'destructive', onPress: () => requestCorrection().catch((error) => setMessage(error?.message || 'Não foi possível registrar a correção.')) },
    ],
  );

  const markNotStudied = async () => {
    if (!current) return;
    interaction();
    setMessage('');
    const key = studyTopicKey(current);
    await queue('topic_not_studied_reported', {
      subject: current.subject, topic: current.topic, lesson: current.lesson,
      reason: 'not_studied_yet', exclude_from_performance: true,
    });
    const blocked = await readStringSet('study_backlog_topic_keys_v1');
    blocked.add(key);
    await writeStringSet('study_backlog_topic_keys_v1', blocked);
    const sync = await syncNow();
    setMessage(sync?.online && sync.reachable && !sync.failed
      ? 'Assunto separado para estudo futuro e retirado desta sessão sem contar como erro.'
      : 'Marcação salva no aparelho. O assunto ficará fora desta sessão e será sincronizado depois.');
    await advanceRemoving((question) => studyTopicKey(question) === key);
  };

  const confirmNotStudied = () => Alert.alert(
    'Assunto ainda não estudado',
    'O QuestFlow não tratará esta questão como erro. O assunto será colocado na lista “Ainda não estudados” para você revisar depois.',
    [
      { text: 'Cancelar', style: 'cancel' },
      { text: 'Marcar para estudar', onPress: () => markNotStudied().catch((error) => setMessage(error?.message || 'Não foi possível marcar o assunto.')) },
    ],
  );

  const confirmEndEarly = () => {
    if (!active) return;
    Alert.alert('Encerrar sessão agora?', 'As respostas já realizadas permanecem no histórico. O lote atual será encerrado e você verá o resumo da sessão.', [
      { text: 'Continuar estudando', style: 'cancel' },
      { text: 'Encerrar sessão', style: 'destructive', onPress: () => finalizeSession(active.stats, 'ended_by_user').catch(() => undefined) },
    ]);
  };

  const selectedAlternative = useMemo(() => current?.alternatives.find((item) => item.index === selected), [current, selected]);
  const liveActiveTime = formatDurationShort(live.active_response_seconds, '0s');
  const phaseStep = phase === 'answer' ? 1 : phase === 'confidence' ? 2 : 3;

  if (loading) {
    return <Screen><View style={styles.center}><StatePanel state="loading" title="Preparando o QuestFlow" detail="Recuperando a sessão, a reserva offline e as configurações de estudo." /></View></Screen>;
  }

  if (viewMode === 'offline_history') {
    return (
      <Screen>
        <ScrollView contentContainerStyle={styles.content}>
          <ScreenHeader eyebrow="RESERVA OFFLINE" title="Respondidas offline" detail="Respostas preservadas localmente recebem resultado, gabarito e explicação quando o Studio volta a sincronizar." action={<Pill text={`${offlineHistoryInfo.pending} pendentes`} tone={offlineHistoryInfo.pending ? 'warning' : 'success'} />} />

          <HeroCard>
            <View style={styles.rowBetween}>
              <View style={{ flex: 1, gap: 5 }}>
                <Pill text="Histórico local" tone="info" />
                <Text style={styles.heroTitle}>{offlineHistoryInfo.resolved} corrigida(s) • {offlineHistoryInfo.pending} aguardando</Text>
                <Muted>O resultado vem do QuestFlow Studio depois que o Learning Engine processa a resposta. O aplicativo apenas guarda e apresenta esse retorno.</Muted>
              </View>
            </View>
            <Button title={syncing || offlineHistoryLoading ? 'Sincronizando…' : 'Sincronizar resultados agora'} onPress={() => syncOfflineHistory()} disabled={syncing || offlineHistoryLoading} />
            <Button title="Voltar para Questões" onPress={() => setViewMode('setup')} tone="secondary" />
          </HeroCard>

          {offlineHistoryMessage ? <StatePanel state={offlineHistoryMessage.includes('não') ? 'offline' : 'success'} title="Sincronização da reserva" detail={offlineHistoryMessage} /> : null}
          {offlineHistoryLoading && !offlineHistory.length ? <StatePanel state="loading" title="Atualizando histórico offline" detail="Buscando resultados processados pelo Studio." /> : null}

          {!offlineHistoryLoading && !offlineHistory.length ? (
            <StatePanel state="empty" title="Nenhuma resposta offline ainda" detail="Quando você responder sem conexão, a tentativa aparecerá aqui e continuará disponível depois da sincronização." />
          ) : null}

          {offlineHistory.map((item) => {
            const question = item.question;
            const result = item.feedback;
            const selectedKey = question?.alternatives?.find((alt) => alt.index === item.selected_index)?.key || (item.selected_index == null ? '—' : String.fromCharCode(65 + item.selected_index));
            const expanded = offlineExpandedAttempt === item.attempt_id;
            const title = question?.code || 'Questão offline';
            const subject = question?.subject || 'Matéria não informada';
            const topic = question?.topic || question?.lesson || '';
            return (
              <Card key={item.attempt_id} style={styles.offlineResultCard}>
                <View style={styles.rowBetween}>
                  <View style={{ flex: 1, gap: 4 }}>
                    <Text style={styles.offlineResultCode}>{title} • {subject}</Text>
                    {topic ? <Muted>{topic}</Muted> : null}
                  </View>
                  <Pill text={result ? (result.is_correct ? 'Correta' : 'Incorreta') : 'Aguardando'} tone={result ? (result.is_correct ? 'success' : 'danger') : 'warning'} />
                </View>
                {question?.statement ? <Text style={styles.offlineStatement} numberOfLines={expanded ? undefined : 3}>{question.statement}</Text> : null}
                <View style={styles.offlineAnswerRow}>
                  <View style={styles.offlineAnswerBox}><Text style={styles.offlineAnswerLabel}>Sua resposta</Text><Text style={styles.offlineAnswerValue}>{selectedKey}</Text></View>
                  <View style={styles.offlineAnswerBox}><Text style={styles.offlineAnswerLabel}>Gabarito</Text><Text style={styles.offlineAnswerValue}>{result?.correct_key || (result?.correct_index == null ? 'Aguardando' : String.fromCharCode(65 + result.correct_index))}</Text></View>
                </View>
                {result ? (
                  <>
                    <Button title={expanded ? 'Ocultar detalhes' : 'Ver resultado e explicação'} onPress={() => setOfflineExpandedAttempt(expanded ? '' : item.attempt_id)} tone="secondary" />
                    {expanded ? (
                      <View style={styles.offlineExplanation}>
                        <Text style={[styles.resultTitle, { color: result.is_correct ? palette.success : palette.danger }]}>{result.is_correct ? '✓ Você acertou' : '✕ Você errou'}</Text>
                        {result.explanation ? <Text style={styles.explanationText}>{result.explanation}</Text> : <Muted>Esta questão ainda não possui explicação cadastrada no QuestFlow.</Muted>}
                        <Muted>Resultado sincronizado {item.synced_at ? `em ${new Date(item.synced_at).toLocaleString('pt-BR')}` : 'com o Studio'}.</Muted>
                      </View>
                    ) : null}
                  </>
                ) : (
                  <Muted>Resposta preservada no aparelho. Assim que o Studio receber e processar a tentativa, este cartão será atualizado automaticamente na próxima sincronização.</Muted>
                )}
              </Card>
            );
          })}
        </ScrollView>
      </Screen>
    );
  }

  if (viewMode === 'setup') {
    return (
      <Screen>
        <ScrollView contentContainerStyle={styles.content}>
          <ScreenHeader eyebrow="STUDY SESSION" title="Questões" detail="Monte um bloco com objetivo claro. O QuestFlow mantém a sessão salva para você continuar depois." action={<Pill text={offlinePack?.count ? `${offlinePack.count} offline` : 'Adaptativo'} tone={offlinePack?.count ? 'info' : 'violet'} />} />

          {resumeCandidate ? (
            <HeroCard>
              <View style={styles.rowBetween}>
                <View style={{ flex: 1, gap: 5 }}>
                  <Pill text="Sessão interrompida" tone="warning" />
                  <Text style={styles.heroTitle}>Continue de onde parou</Text>
                  <Muted>{sessionModeLabel(resumeCandidate.config.mode)}{resumeCandidate.config.subject ? ` • ${resumeCandidate.config.subject}` : ''}</Muted>
                </View>
                <Text style={styles.resumeCounter}>{Math.min(resumeCandidate.index + 1, resumeCandidate.question_refs.length)}/{resumeCandidate.question_refs.length}</Text>
              </View>
              <ProgressBar value={(resumeCandidate.index + 1) / Math.max(1, resumeCandidate.question_refs.length)} tone="accent" />
              <Button title="Continuar sessão" onPress={() => resumeSession()} />
              <Button title="Descartar e criar nova" onPress={discardResume} tone="secondary" />
            </HeroCard>
          ) : null}

          {message ? <StatePanel state="info" title="Estado da sessão" detail={message} /> : null}

          <SectionTitle eyebrow="Objetivo" title="Como você quer estudar agora?" detail="A seleção altera quais questões entram no lote." />
          <View style={styles.modeGrid}>
            {MODES.map((item) => {
              const selectedMode = setupMode === item.value;
              return (
                <Pressable key={item.value} onPress={() => { setSetupMode(item.value); setMessage(''); }} style={[styles.modeCard, selectedMode && styles.modeCardSelected]}>
                  <Text style={styles.modeIcon}>{item.icon}</Text>
                  <Text style={styles.modeTitle}>{item.title}</Text>
                  <Muted>{sessionModeDescription(item.value)}</Muted>
                  {selectedMode ? <Pill text="Selecionado" tone="info" /> : null}
                </Pressable>
              );
            })}
          </View>

          {setupMode === 'subject' ? (
            <Card style={{ gap: 12 }}>
              <SectionTitle title="Escolha a matéria" detail="A sessão ficará concentrada apenas nessa matéria." />
              {subjects.length ? (
                <View style={styles.subjectChips}>
                  {subjects.map((subject) => (
                    <Pressable key={subject} onPress={() => { setSetupSubject(subject); setMessage(''); }} style={[styles.subjectChip, setupSubject === subject && styles.subjectChipSelected]}>
                      <Text style={[styles.subjectChipText, setupSubject === subject && styles.subjectChipTextSelected]}>{subject}</Text>
                    </Pressable>
                  ))}
                </View>
              ) : <Muted>O QuestFlow ainda não possui matérias suficientes na projeção Mobile para este filtro.</Muted>}
            </Card>
          ) : null}

          <Card style={{ gap: 12 }}>
            <SectionTitle title="Tamanho da sessão" detail="Escolha um bloco que caiba no tempo disponível agora." />
            <View style={styles.countRow}>
              {COUNTS.map((count) => (
                <Pressable key={count} onPress={() => setSetupCount(count)} style={[styles.countChip, setupCount === count && styles.countChipSelected]}>
                  <Text style={[styles.countValue, setupCount === count && styles.countValueSelected]}>{count}</Text>
                  <Text style={styles.countLabel}>questões</Text>
                </Pressable>
              ))}
            </View>
          </Card>

          {offlinePack?.count ? (
            <Card style={{ gap: 8 }}>
              <View style={styles.rowBetween}>
                <View style={{ flex: 1, gap: 4 }}>
                  <Text style={styles.preAnswerTitle}>Reserva Offline</Text>
                  <Muted>{offlinePack.count} questões disponíveis sem internet e sem o Studio aberto.</Muted>
                </View>
                <Pill text="Learning Engine" tone="success" />
              </View>
              <Muted>Essa sequência foi escolhida pelo QuestFlow Studio na última sincronização. O aplicativo não cria uma prioridade pedagógica própria.</Muted>
            </Card>
          ) : (
            <Card style={{ gap: 6 }}>
              <Text style={styles.preAnswerTitle}>Reserva Offline</Text>
              <Muted>Conecte e sincronize com o Studio para preparar questões que poderão ser respondidas sem internet.</Muted>
            </Card>
          )}

          <Card style={{ gap: 10 }}>
            <View style={styles.rowBetween}>
              <View style={{ flex: 1, gap: 4 }}>
                <Text style={styles.preAnswerTitle}>Questões respondidas offline</Text>
                <Muted>Consulte depois o que você acertou ou errou, o gabarito e a explicação de cada resposta feita sem conexão.</Muted>
              </View>
              {offlineHistoryInfo.pending ? <Pill text={`${offlineHistoryInfo.pending} aguardando`} tone="warning" /> : offlineHistoryInfo.resolved ? <Pill text={`${offlineHistoryInfo.resolved} corrigidas`} tone="success" /> : null}
            </View>
            <Button title={offlineHistoryInfo.total ? `Ver histórico (${offlineHistoryInfo.total})` : 'Abrir histórico offline'} onPress={() => openOfflineHistory()} tone="secondary" />
          </Card>

          <Button title={`Iniciar sessão de ${setupCount} questões`} onPress={() => beginSession()} />
        </ScrollView>
      </Screen>
    );
  }

  if (viewMode === 'summary' && summary) {
    const accuracy = sessionAccuracy(summary.stats);
    const pendingResults = Math.max(0, Number(summary.stats.pending_results || 0));
    const awaitingOnly = accuracy == null && pendingResults > 0;
    return (
      <Screen>
        <ScrollView contentContainerStyle={styles.content}>
          <ScreenHeader eyebrow="SESSÃO CONCLUÍDA" title="Resumo" detail={`${sessionModeLabel(summary.config.mode)}${summary.config.subject ? ` • ${summary.config.subject}` : ''}`} action={<Pill text={awaitingOnly ? 'Pendente' : 'Concluída'} tone={awaitingOnly ? 'warning' : 'success'} />} />

          <HeroCard>
            <Pill text={awaitingOnly ? 'Resultado pendente de sincronização' : 'Bloco finalizado'} tone={awaitingOnly ? 'warning' : 'success'} />
            <Text style={styles.summaryScore}>{awaitingOnly ? summary.stats.answered : `${Math.round((accuracy || 0) * 100)}%`}</Text>
            <Text style={styles.heroTitle}>{awaitingOnly ? 'questões respondidas nesta sessão' : 'de acerto nesta sessão'}</Text>
            <Muted>{summaryCoach(summary.stats)}</Muted>
            {awaitingOnly ? <Muted>A precisão será calculada após o aparelho receber o gabarito; nenhuma acurácia foi inventada.</Muted> : <ProgressBar value={accuracy || 0} tone={accuracy != null && accuracy >= 0.7 ? 'success' : 'warning'} height={10} />}
          </HeroCard>

          <View style={styles.metrics}>
            <Metric label="Respondidas" value={summary.stats.answered} tone="primary" />
            <Metric label="Acertos" value={summary.stats.correct} tone="success" />
            <Metric label="Erros" value={summary.stats.wrong} tone="danger" />
            <Metric label="Puladas" value={summary.stats.skipped} tone="warning" />
            {pendingResults ? <Metric label="Aguardando correção" value={pendingResults} tone="warning" /> : null}
          </View>

          <Card style={styles.summaryTimeCard}>
            <View style={styles.summaryTimeHeader}>
              <View style={styles.summaryTimeCopy}>
                <Text style={styles.summaryLabel}>Tempo ativo acumulado</Text>
                <Text style={styles.summaryTimeHint}>Tempo efetivo em que você esteve respondendo dentro da aba Questões.</Text>
              </View>
              <Pill text="Tempo útil" tone="info" />
            </View>
            <View style={styles.summaryTimeValueBox}>
              <Text
                style={styles.summaryTime}
                numberOfLines={1}
                adjustsFontSizeToFit
                minimumFontScale={0.72}
              >
                {formatDuration(summary.stats.active_seconds, { compact: true })}
              </Text>
            </View>
            <Muted style={styles.summaryTimeFootnote}>Pausas, troca de aba e tempo não elegível ficam fora deste total.</Muted>
          </Card>

          <Button title="Iniciar nova sessão" onPress={() => { setSummary(null); setMessage(''); setViewMode('setup'); }} />
          <Button title="Voltar para Hoje" onPress={() => router.replace('/(tabs)/today')} tone="secondary" />
        </ScrollView>
      </Screen>
    );
  }

  if (!active || !current) {
    return <Screen><View style={styles.center}><StatePanel state="empty" title="Nenhuma questão disponível" detail={message || 'Esta sessão não possui questões disponíveis.'} actionTitle="Voltar para sessões" onAction={() => setViewMode('setup')} /></View></Screen>;
  }

  return (
    <Screen>
      <ScrollView contentContainerStyle={styles.content} onTouchStart={interaction} onScrollBeginDrag={interaction} keyboardShouldPersistTaps="handled">
        <View style={styles.sessionTopline}>
          <View style={{ flex: 1, gap: 3 }}>
            <Text style={styles.kicker}>{sessionModeLabel(active.config.mode).toUpperCase()}</Text>
            <Muted>{active.config.subject || `${active.config.count} questões planejadas`}{active.adaptive?.goal?.estimated_minutes ? ` • ≈ ${active.adaptive.goal.estimated_minutes} min` : ''}</Muted>
          </View>
          <Pressable onPress={confirmEndEarly} hitSlop={12}><Text style={styles.endSession}>Encerrar</Text></Pressable>
        </View>

        <HeroCard>
          <View style={styles.rowBetween}>
            <View style={{ flex: 1, gap: 4 }}>
              <Text style={styles.subject}>{current.subject || 'Questão'}</Text>
              <Muted>{current.topic || current.lesson || current.code}</Muted>
            </View>
            <Pill text={`${Math.min(active.index + 1, active.config.count)}/${active.config.count}`} tone="info" />
          </View>
          <ProgressBar value={(Math.min(active.index, active.config.count - 1) + phaseStep / 3) / Math.max(1, active.config.count)} tone="accent" height={8} />
          <View style={styles.rowBetween}>
            <Muted>Etapa da questão</Muted>
            <Pill text={phase === 'answer' ? 'Responder' : phase === 'confidence' ? 'Confiança' : 'Resultado'} tone={phase === 'result' ? 'success' : 'violet'} />
          </View>
          <View style={styles.timerCard}>
            <View style={{ gap: 4, flex: 1 }}>
              <Text style={styles.timerLabel}>TEMPO ATIVO</Text>
              <Text style={styles.timerValue}>{liveActiveTime}</Text>
              <Muted>Só conta enquanto esta aba está aberta e você está interagindo com a questão.</Muted>
            </View>
            <Pill text={questionScreenFocused ? 'Ativo' : 'Pausado'} tone={questionScreenFocused ? 'success' : 'warning'} />
          </View>
        </HeroCard>

        {current.selection?.reason ? (
          <Card style={styles.selectionInsightCard}>
            <View style={styles.selectionInsightTop}>
              <View style={styles.selectionInsightIcon}><Text style={styles.selectionInsightIconText}>✦</Text></View>
              <View style={styles.selectionInsightCopy}>
                <Text style={styles.selectionInsightEyebrow}>POR QUE ESTA QUESTÃO?</Text>
                <Text style={styles.selectionInsightTitle}>{selectionReasonLabel(current.selection.reason)}</Text>
              </View>
              <Pill text="QuestFlow explica" tone="info" />
            </View>
            {current.selection.topic_transfer ? (
              <Muted>{transferReasonLabel(current.selection.transfer_reason)}</Muted>
            ) : null}
          </Card>
        ) : null}

        {active.adaptive?.goal ? (
          <Card style={styles.goalCard}>
            <Text style={styles.goalTitle}>{active.adaptive.goal.headline}</Text>
            <Muted>{(active.adaptive.goal.focus || []).slice(0, 3).join(' • ')}</Muted>
          </Card>
        ) : null}

        {message ? <StatePanel state="info" title="Atualização da sessão" detail={message} /> : null}

        <Card style={{ gap: 14 }}>
          <Text style={styles.statement}>{current.statement}</Text>
          <View style={{ gap: 10 }}>
            {current.alternatives.map((alt) => {
              const isSelected = selected === alt.index;
              const correct = feedback?.correct_index === alt.index;
              const wrongSelected = Boolean(feedback && isSelected && !feedback.is_correct);
              return (
                <SwipeStrikeOption
                  key={alt.index}
                  optionKey={alt.key || String.fromCharCode(65 + alt.index)}
                  text={alt.text}
                  disabled={phase === 'result'}
                  selected={isSelected}
                  struck={eliminated.includes(alt.index)}
                  correct={correct}
                  wrongSelected={wrongSelected}
                  onPress={() => choose(alt.index)}
                  onToggleStrike={() => toggleEliminated(alt.index)}
                />
              );
            })}
          </View>
          {phase === 'answer' ? <Muted>Deslize uma alternativa para a esquerda ou direita para riscá-la. Deslize novamente para desfazer.</Muted> : null}
        </Card>

        {phase === 'answer' ? (
          <Card style={{ gap: 10 }}>
            <Button title="Continuar" onPress={() => { interaction(); updateAnswerState({ phase: 'confidence' }).catch(() => undefined); }} disabled={selected == null} />
            <Button title="Pular Questão" onPress={skip} tone="secondary" />
            <Button title="Assunto ainda não Estudado" onPress={confirmNotStudied} tone="secondary" />
            <Button title="CORRIGIR QUESTÃO" onPress={confirmCorrection} tone="danger" />
            <Muted>Correção e conteúdo ainda não estudado não entram como erro no seu desempenho.</Muted>
          </Card>
        ) : null}

        {phase === 'confidence' ? (
          <Card style={{ gap: 16 }}>
            <View><Text style={styles.questionPrompt}>Quão confiante você está?</Text><Muted>A confiança ajuda o QuestFlow a distinguir domínio real de acertos frágeis.</Muted></View>
            <ChoiceRow items={CONFIDENCE} selected={confidence} onSelect={(value) => { interaction(); updateAnswerState({ confidence: value }).catch(() => undefined); }} />
            <View><Text style={styles.questionPrompt}>Como você achou a questão? <Text style={styles.optional}>(opcional)</Text></Text></View>
            <ChoiceRow items={DIFFICULTY} selected={difficulty} onSelect={(value) => { interaction(); updateAnswerState({ difficulty: value }).catch(() => undefined); }} />
            <Button title="Responder e ver resultado" onPress={submit} disabled={!confidence || syncing} />
            <Muted>Sua alternativa: {selectedAlternative?.key || '—'}. O gabarito ainda não foi enviado ao aparelho.</Muted>
          </Card>
        ) : null}

        {phase === 'result' ? (
          <Card style={{ gap: 14 }}>
            {feedback ? (
              <>
                <View style={styles.resultRow}>
                  <Text style={[styles.resultTitle, { color: feedback.is_correct ? palette.success : palette.danger }]}>{feedback.is_correct ? '✓ CORRETO' : '✕ INCORRETO'}</Text>
                  <Pill text={`Gabarito: ${feedback.correct_key || (feedback.correct_index == null ? '—' : String.fromCharCode(65 + feedback.correct_index))}`} tone={feedback.is_correct ? 'success' : 'danger'} />
                </View>
                <Muted>Tempo usado nas métricas: {feedback.timing.active_response_seconds == null ? 'não elegível' : formatDuration(feedback.timing.active_response_seconds)} • qualidade: {feedback.timing.quality}</Muted>
                {feedback.provisional ? <Card style={styles.provisional}><Text style={styles.provisionalText}>Feedback provisório disponível. Suas métricas serão confirmadas quando o QuestFlow receber esta resposta.</Text></Card> : null}
                {feedback.explanation ? <Button title={explanationOpen ? 'Ocultar explicação' : 'Abrir explicação'} onPress={markExplanationOpen} tone="secondary" /> : <Muted>Esta questão ainda não possui explicação cadastrada.</Muted>}
                {explanationOpen ? <View style={styles.explanation}><Text style={styles.explanationText}>{feedback.explanation}</Text></View> : null}
                <View style={{ gap: 10 }}>
                  <Button title="Entendi — próxima questão" onPress={() => finishUnderstanding(false)} />
                  <Button title="Ainda tenho dúvida / preciso revisar" onPress={() => finishUnderstanding(true)} tone="secondary" />
                </View>
              </>
            ) : (
              <>
                {awaitingFeedback ? <ActivityIndicator color={palette.primary} /> : null}
                <Text style={styles.questionPrompt}>Sua resposta está salva.</Text>
                <Muted>O gabarito não fica na Reserva Offline. Você pode continuar estudando; o Studio corrigirá esta resposta quando a conexão voltar.</Muted>
                <Button title="Continuar offline — próxima questão" onPress={continueWithoutFeedback} />
                <Button title="Sincronizar e buscar resultado" onPress={retryFeedback} disabled={syncing} tone="secondary" />
              </>
            )}
          </Card>
        ) : null}
      </ScrollView>
    </Screen>
  );
}

function SwipeStrikeOption({
  optionKey, text, disabled, selected, struck, correct, wrongSelected, onPress, onToggleStrike,
}: {
  optionKey: string; text: string; disabled: boolean; selected: boolean; struck: boolean; correct: boolean; wrongSelected: boolean; onPress: () => void; onToggleStrike: () => void;
}) {
  const panResponder = useMemo(() => PanResponder.create({
    onStartShouldSetPanResponder: () => false,
    onMoveShouldSetPanResponder: (_event, gesture) => !disabled && Math.abs(gesture.dx) > 12 && Math.abs(gesture.dx) > Math.abs(gesture.dy) * 1.15,
    onPanResponderRelease: (_event, gesture) => {
      if (!disabled && Math.abs(gesture.dx) >= 42) onToggleStrike();
    },
    onPanResponderTerminationRequest: () => true,
  }), [disabled, onToggleStrike]);

  return (
    <View {...panResponder.panHandlers}>
      <Pressable disabled={disabled} onPress={onPress} style={[styles.option, selected && styles.optionSelected, correct && styles.optionCorrect, wrongSelected && styles.optionWrong, struck && styles.optionStruck]}>
        <View style={[styles.optionBadge, selected && styles.optionBadgeSelected, struck && styles.optionBadgeStruck]}><Text style={[styles.optionKey, struck && styles.optionKeyStruck]}>{optionKey}</Text></View>
        <View style={styles.optionContent}>
          <Text style={[styles.optionText, struck && styles.optionTextStruck]}>{text}</Text>
          {struck ? <Text style={styles.optionEliminatedLabel}>✕ ALTERNATIVA ELIMINADA</Text> : null}
        </View>
      </Pressable>
    </View>
  );
}

function ChoiceRow<T extends string>({ items, selected, onSelect }: { items: Array<{ value: T; label: string }>; selected: T | null; onSelect: (value: T) => void }) {
  return <View style={styles.choiceRow}>{items.map((item) => <Pressable key={item.value} onPress={() => onSelect(item.value)} style={[styles.choice, selected === item.value && styles.choiceSelected]}><Text style={styles.choiceText}>{item.label}</Text></Pressable>)}</View>;
}

const styles = StyleSheet.create({
  content: { paddingVertical: 14, gap: 14, paddingBottom: 34 },
  titleBlock: { gap: 4 },
  kicker: { color: palette.accent, fontSize: 11, fontWeight: '900', letterSpacing: 1.2 },
  center: { flex: 1, minHeight: 520, alignItems: 'center', justifyContent: 'center', gap: 16 },
  centerCompact: { minHeight: 160, alignItems: 'center', justifyContent: 'center', gap: 12 },
  rowBetween: { flexDirection: 'row', gap: 10, alignItems: 'center', justifyContent: 'space-between' },
  heroTitle: { color: palette.text, fontSize: 21, fontWeight: '900', letterSpacing: -0.3 },
  resumeCounter: { color: palette.text, fontSize: 27, fontWeight: '900' },
  modeGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 10 },
  modeCard: { width: '48%', minWidth: 150, gap: 8, padding: 14, borderRadius: 20, backgroundColor: palette.surface, borderWidth: 1, borderColor: palette.border },
  modeCardSelected: { borderColor: palette.primary, backgroundColor: 'rgba(243,181,74,0.18)' },
  modeIcon: { color: palette.accent, fontSize: 24, fontWeight: '900' },
  modeTitle: { color: palette.text, fontSize: 17, fontWeight: '900' },
  subjectChips: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  subjectChip: { borderRadius: 999, paddingHorizontal: 13, paddingVertical: 9, backgroundColor: palette.surface2, borderWidth: 1, borderColor: palette.border },
  subjectChipSelected: { borderColor: palette.accent2, backgroundColor: 'rgba(33,184,154,0.12)' },
  subjectChipText: { color: palette.muted, fontSize: 13, fontWeight: '800' },
  subjectChipTextSelected: { color: palette.text },
  countRow: { flexDirection: 'row', gap: 8 },
  countChip: { flex: 1, alignItems: 'center', gap: 2, paddingVertical: 12, borderRadius: 16, backgroundColor: palette.surface2, borderWidth: 1, borderColor: palette.border },
  countChipSelected: { borderColor: palette.primary, backgroundColor: 'rgba(243,181,74,0.22)' },
  countValue: { color: palette.text, fontSize: 21, fontWeight: '900' },
  countValueSelected: { color: palette.primarySoft },
  countLabel: { color: palette.muted, fontSize: 10, fontWeight: '700' },
  metrics: { flexDirection: 'row', gap: 8, flexWrap: 'wrap' },
  offlineResultCard: { gap: 12 },
  offlineResultCode: { color: palette.text, fontSize: 16, fontWeight: '900' },
  offlineStatement: { color: palette.text, fontSize: 15, lineHeight: 22 },
  offlineAnswerRow: { flexDirection: 'row', gap: 10 },
  offlineAnswerBox: { flex: 1, borderRadius: 14, padding: 11, backgroundColor: palette.surface2, borderWidth: 1, borderColor: palette.border, gap: 3 },
  offlineAnswerLabel: { color: palette.muted, fontSize: 10, fontWeight: '800', textTransform: 'uppercase' },
  offlineAnswerValue: { color: palette.text, fontSize: 17, fontWeight: '900' },
  offlineExplanation: { gap: 10, padding: 13, borderRadius: 16, backgroundColor: palette.bgAlt, borderWidth: 1, borderColor: palette.border },
  summaryScore: { color: palette.text, fontSize: 50, fontWeight: '900', letterSpacing: -2 },
  summaryTimeCard: { gap: 12, overflow: 'hidden' },
  summaryTimeHeader: { flexDirection: 'row', alignItems: 'flex-start', justifyContent: 'space-between', gap: 12 },
  summaryTimeCopy: { flex: 1, minWidth: 0, gap: 4 },
  summaryLabel: { color: palette.accent, fontSize: 11, fontWeight: '900', textTransform: 'uppercase', letterSpacing: 0.85, flexShrink: 1 },
  summaryTimeHint: { color: palette.muted, fontSize: 13, lineHeight: 19, flexShrink: 1 },
  summaryTimeValueBox: { minHeight: 64, justifyContent: 'center', paddingHorizontal: 14, paddingVertical: 9, borderRadius: 16, backgroundColor: 'rgba(33,184,154,0.10)', borderWidth: 1, borderColor: 'rgba(33,184,154,0.22)' },
  summaryTime: { color: palette.text, fontSize: 31, lineHeight: 38, fontWeight: '900', letterSpacing: -0.6, flexShrink: 1 },
  summaryTimeFootnote: { fontSize: 12, lineHeight: 18 },
  sessionTopline: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingHorizontal: 2 },
  selectionInsightCard: { gap: 9, borderColor: 'rgba(85,169,214,0.24)', backgroundColor: '#F7FBFD' },
  selectionInsightTop: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  selectionInsightIcon: { width: 34, height: 34, borderRadius: 12, alignItems: 'center', justifyContent: 'center', backgroundColor: 'rgba(85,169,214,0.13)' },
  selectionInsightIconText: { color: palette.violet, fontSize: 16, fontWeight: '900' },
  selectionInsightCopy: { flex: 1, minWidth: 0, gap: 2 },
  selectionInsightEyebrow: { color: palette.violet, fontSize: 9, fontWeight: '900', letterSpacing: 0.9 },
  selectionInsightTitle: { color: palette.text, fontSize: 13, lineHeight: 18, fontWeight: '800' },
  goalCard: { gap: 5, borderColor: 'rgba(220,151,46,0.24)' },
  goalTitle: { color: palette.text, fontSize: 14, fontWeight: '900', lineHeight: 20 },
  endSession: { color: palette.danger, fontSize: 13, fontWeight: '900' },
  subject: { color: palette.text, fontSize: 21, fontWeight: '900' },
  timerCard: { backgroundColor: 'rgba(246,242,233,0.88)', borderRadius: 18, padding: 14, borderWidth: 1, borderColor: 'rgba(37,40,58,0.08)', flexDirection: 'row', gap: 10, alignItems: 'flex-start' },
  timerLabel: { color: palette.muted, fontSize: 12, fontWeight: '800', textTransform: 'uppercase', letterSpacing: 0.5 },
  timerValue: { color: palette.text, fontSize: 24, fontWeight: '900' },
  statement: { color: palette.text, fontSize: 17, lineHeight: 26, fontWeight: '600' },
  option: { flexDirection: 'row', gap: 12, borderWidth: 1, borderColor: palette.border, borderRadius: 18, padding: 14, backgroundColor: palette.surface2, alignItems: 'flex-start' },
  optionSelected: { borderColor: palette.primary, borderWidth: 2, backgroundColor: 'rgba(243,181,74,0.18)' },
  optionCorrect: { borderColor: palette.success, backgroundColor: 'rgba(33,184,154,0.13)' },
  optionWrong: { borderColor: palette.danger, backgroundColor: 'rgba(239,120,104,0.13)' },
  optionBadge: { width: 34, height: 34, borderRadius: 12, backgroundColor: 'rgba(243,181,74,0.16)', alignItems: 'center', justifyContent: 'center' },
  optionBadgeSelected: { backgroundColor: 'rgba(243,181,74,0.28)' },
  optionBadgeStruck: { backgroundColor: 'rgba(255,107,125,0.20)', borderWidth: 1, borderColor: 'rgba(255,107,125,0.75)' },
  optionKey: { color: palette.primarySoft, fontWeight: '900' },
  optionKeyStruck: { color: palette.danger },
  optionContent: { flex: 1, gap: 6 },
  optionText: { color: palette.text, lineHeight: 21 },
  optionStruck: { opacity: 0.82, borderWidth: 2, borderColor: 'rgba(255,107,125,0.78)', backgroundColor: 'rgba(255,107,125,0.08)' },
  optionTextStruck: { color: palette.muted, textDecorationLine: 'line-through', textDecorationStyle: 'solid', textDecorationColor: palette.danger },
  optionEliminatedLabel: { color: palette.danger, fontSize: 11, lineHeight: 15, fontWeight: '900', letterSpacing: 0.55 },
  questionPrompt: { color: palette.text, fontSize: 17, fontWeight: '800', lineHeight: 24 },
  optional: { color: palette.muted, fontSize: 13, fontWeight: '500' },
  choiceRow: { flexDirection: 'row', gap: 8 },
  choice: { flex: 1, paddingVertical: 12, borderRadius: 14, borderWidth: 1, borderColor: palette.border, alignItems: 'center', backgroundColor: palette.surface2 },
  choiceSelected: { borderColor: palette.primary, backgroundColor: 'rgba(255,138,42,0.17)' },
  choiceText: { color: palette.text, fontWeight: '800' },
  resultRow: { flexDirection: 'row', justifyContent: 'space-between', gap: 10, alignItems: 'center' },
  resultTitle: { fontSize: 22, fontWeight: '900' },
  explanation: { borderLeftWidth: 3, borderLeftColor: palette.primary, paddingLeft: 14 },
  explanationText: { color: palette.text, fontSize: 15, lineHeight: 23 },
  message: { color: palette.warning, fontWeight: '700', lineHeight: 20 },
  provisional: { borderColor: palette.warning, backgroundColor: palette.surface2 },
  provisionalText: { color: palette.warning, fontWeight: '700', lineHeight: 20 },
  preAnswerTitle: { color: palette.text, fontSize: 15, fontWeight: '900' },
  preAnswerActions: { flexDirection: 'row', gap: 8, flexWrap: 'wrap' },
  preAnswerButton: { flex: 1, minWidth: 150 },
});
