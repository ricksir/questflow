import { NETWORK_TIMEOUT_MS } from './config';
import type { AdaptiveSessionProjection, AnalyticsSnapshotV2, BootstrapProjection, Feedback, LearningEvent, MobileQuestion, OfflineStudyPack, PairingExchange, ProgressProjection, StudySessionMode, TodayProjection } from './types';

export class QuestFlowApiError extends Error {
  status: number;
  constructor(message: string, status = 0) {
    super(message);
    this.name = 'QuestFlowApiError';
    this.status = status;
  }
}

async function requestJson<T>(url: string, init: RequestInit = {}, timeoutMs = NETWORK_TIMEOUT_MS): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(url, {
      ...init,
      signal: controller.signal,
      headers: { 'Content-Type': 'application/json', ...(init.headers || {}) },
    });
    let payload: any = null;
    try { payload = await response.json(); } catch { /* handled below */ }
    if (!response.ok || payload?.ok === false) {
      throw new QuestFlowApiError(String(payload?.error || `Falha HTTP ${response.status}`), response.status);
    }
    return payload as T;
  } catch (error) {
    if (error instanceof QuestFlowApiError) throw error;
    if ((error as Error)?.name === 'AbortError') throw new QuestFlowApiError('O QuestFlow demorou demais para responder neste caminho de conexão.');
    throw new QuestFlowApiError((error as Error)?.message || 'Não foi possível conectar ao QuestFlow por este caminho.');
  } finally {
    clearTimeout(timer);
  }
}

export async function health(apiBaseUrl: string, timeoutMs = NETWORK_TIMEOUT_MS): Promise<{ ok: boolean; api: string; schema_version: number; server_fingerprint?: string; transport?: string; cloud_bridge?: boolean }> {
  return requestJson(`${apiBaseUrl}/api/v1/mobile/health`, {}, timeoutMs);
}


export async function exchangePairing(apiBaseUrl: string, pairingToken: string, device: Record<string, unknown>): Promise<PairingExchange> {
  return requestJson<PairingExchange & { ok: boolean }>(`${apiBaseUrl}/api/v1/mobile/pairing/exchange`, {
    method: 'POST',
    body: JSON.stringify({ pairing_token: pairingToken, device }),
  });
}

export function createApi(apiBaseUrl: string, accessToken: string) {
  const authHeaders = { Authorization: `Bearer ${accessToken}` };
  return {
    bootstrap: async (examProjectId = ''): Promise<BootstrapProjection> => {
      const suffix = examProjectId ? `?exam_project_id=${encodeURIComponent(examProjectId)}` : '';
      const result = await requestJson<{ ok: boolean; data: BootstrapProjection }>(`${apiBaseUrl}/api/v1/mobile/bootstrap${suffix}`, { headers: authHeaders });
      return result.data;
    },
    today: async (examProjectId = ''): Promise<TodayProjection> => {
      const suffix = examProjectId ? `?exam_project_id=${encodeURIComponent(examProjectId)}` : '';
      const result = await requestJson<{ ok: boolean; data: TodayProjection }>(`${apiBaseUrl}/api/v1/mobile/today${suffix}`, { headers: authHeaders });
      return result.data;
    },
    progress: async (examProjectId = ''): Promise<ProgressProjection> => {
      const suffix = examProjectId ? `?exam_project_id=${encodeURIComponent(examProjectId)}` : '';
      const result = await requestJson<{ ok: boolean; data: ProgressProjection }>(`${apiBaseUrl}/api/v1/mobile/progress${suffix}`, { headers: authHeaders });
      return result.data;
    },
    analytics: async (examProjectId = '', range = 'all', grain = 'attempt'): Promise<AnalyticsSnapshotV2> => {
      const params = new URLSearchParams({ range, grain });
      if (examProjectId) params.set('exam_project_id', examProjectId);
      const result = await requestJson<{ ok: boolean; data: AnalyticsSnapshotV2 }>(`${apiBaseUrl}/api/v1/mobile/analytics?${params.toString()}`, { headers: authHeaders });
      return result.data;
    },
    startAdaptiveSession: async (payload: { session_id: string; count: number; exam_project_id?: string; mode?: StudySessionMode; subject?: string; micro_batch_size?: number }): Promise<AdaptiveSessionProjection> => {
      const result = await requestJson<{ ok: boolean; data: AdaptiveSessionProjection }>(`${apiBaseUrl}/api/v1/mobile/study-sessions`, {
        method: 'POST',
        headers: authHeaders,
        body: JSON.stringify(payload),
      });
      return result.data;
    },
    nextAdaptiveMicroBatch: async (sessionId: string, payload: { purpose?: 'active' | 'prefetch'; prefetched_batch_id?: string; force_replan?: boolean; excluded_question_ids?: string[] }): Promise<AdaptiveSessionProjection> => {
      const result = await requestJson<{ ok: boolean; data: AdaptiveSessionProjection }>(`${apiBaseUrl}/api/v1/mobile/study-sessions/${encodeURIComponent(sessionId)}/micro-batches`, {
        method: 'POST',
        headers: authHeaders,
        body: JSON.stringify(payload),
      });
      return result.data;
    },
    questionBatch: async (count = 8, examProjectId = '', mode: StudySessionMode = 'recommended', subject = ''): Promise<MobileQuestion[]> => {
      const result = await requestJson<{ ok: boolean; data: { questions: MobileQuestion[] } }>(`${apiBaseUrl}/api/v1/mobile/question-batches`, {
        method: 'POST',
        headers: authHeaders,
        body: JSON.stringify({ count, exam_project_id: examProjectId, mode, subject }),
      });
      return result.data.questions || [];
    },
    feedback: async (attemptId: string): Promise<Feedback> => {
      const result = await requestJson<{ ok: boolean; data: Feedback }>(`${apiBaseUrl}/api/v1/mobile/attempts/${encodeURIComponent(attemptId)}/feedback`, { headers: authHeaders });
      return result.data;
    },
    sync: async (
      cursor: number,
      events: LearningEvent[],
      examProjectId = '',
      offlinePackSize = 30,
      options: { refreshOfflinePack?: boolean; feedbackAttemptId?: string; timeoutMs?: number; pullLimit?: number } = {},
    ): Promise<any & { offline_study_pack?: OfflineStudyPack | null; feedback?: Feedback | null }> => requestJson<any>(`${apiBaseUrl}/api/v1/mobile/sync`, {
      method: 'POST',
      headers: authHeaders,
      body: JSON.stringify({
        cursor, events, limit: options.pullLimit ?? 250,
        exam_project_id: examProjectId,
        refresh_offline_pack: options.refreshOfflinePack ?? true,
        offline_pack_size: offlinePackSize,
        feedback_attempt_id: options.feedbackAttemptId || '',
      }),
    }, options.timeoutMs ?? NETWORK_TIMEOUT_MS),
    disconnectSelf: async (deviceId: string) => requestJson<any>(`${apiBaseUrl}/api/v1/mobile/devices/${encodeURIComponent(deviceId)}`, {
      method: 'DELETE',
      headers: authHeaders,
    }),
    registerPushToken: async (pushToken: string, provider: string) => requestJson<any>(`${apiBaseUrl}/api/v1/mobile/devices/push-token`, {
      method: 'POST',
      headers: authHeaders,
      body: JSON.stringify({ push_token: pushToken, provider }),
    }),
  };
}
