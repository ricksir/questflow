import * as Network from 'expo-network';
import { OUTBOX_BATCH_SIZE } from './config';
import { getMeta, listOfflineAttemptsAwaitingFeedback, listOutbox, markOutboxError, removeOutbox, replaceOfflineStudyPack, saveFeedback, setMeta } from './db';
import type { LearningEvent } from './types';

export type SyncResult = {
  online: boolean;
  reachable: boolean;
  pushed: number;
  failed: number;
  cursor: number;
  feedbackResolved: number;
  message: string;
};

export type AnswerSyncResult = SyncResult & {
  feedback: import('./types').Feedback | null;
};

function cursorKey(transportKey: string): string {
  const normalized = String(transportKey || 'default').replace(/[^a-zA-Z0-9._-]/g, '_').slice(0, 120);
  return `sync_cursor:${normalized}`;
}

export async function runSync(api: ReturnType<typeof import('./api').createApi>, transportKey = 'default', examProjectId = ''): Promise<SyncResult> {
  const metaKey = cursorKey(transportKey);
  const network = await Network.getNetworkStateAsync();
  if (!network.isConnected) {
    return { online: false, reachable: false, pushed: 0, failed: 0, cursor: Number((await getMeta(metaKey)) || 0), feedbackResolved: 0, message: 'Sem rede. Dados preservados no aparelho.' };
  }

  const rows = await listOutbox(OUTBOX_BATCH_SIZE);
  const cursor = Number((await getMeta(metaKey)) || 0);
  const events: LearningEvent[] = [];
  for (const row of rows) {
    try { events.push(JSON.parse(row.event_json) as LearningEvent); } catch { /* invalid row remains for diagnosis */ }
  }

  try {
    const response = await api.sync(cursor, events, examProjectId, 30);
    if (response?.offline_study_pack?.questions) {
      await replaceOfflineStudyPack(response.offline_study_pack);
    }
    const accepted = new Set<string>(response?.push?.accepted || []);
    const duplicates = new Set<string>(response?.push?.duplicates || []);
    const acknowledged = rows.map((row) => row.event_id).filter((id) => accepted.has(id) || duplicates.has(id));
    await removeOutbox(acknowledged);

    const failedItems: Array<{ event_id?: string; error?: string }> = response?.push?.failed || [];
    for (const failed of failedItems) {
      if (failed.event_id) await markOutboxError([failed.event_id], failed.error || 'Falha de sincronização');
    }

    const nextCursor = Number(response?.pull?.cursor ?? cursor);
    await setMeta(metaKey, String(nextCursor));

    // Depois que o Studio aplicou as respostas, reconcilia também resultados de
    // tentativas feitas offline. Assim nenhuma resposta fica "órfã" só porque já
    // não é a questão atualmente aberta quando a conexão retorna.
    let feedbackResolved = 0;
    const pendingFeedback = await listOfflineAttemptsAwaitingFeedback(50);
    for (const attempt of pendingFeedback) {
      try {
        const result = await api.feedback(attempt.attempt_id);
        await saveFeedback(attempt.attempt_id, result);
        feedbackResolved += 1;
      } catch {
        // Pode haver um pequeno atraso entre ingestão e disponibilidade do feedback.
        // A tentativa permanece local e será reconciliada no próximo sync.
      }
    }

    const baseMessage = failedItems.length ? 'Sincronização parcial; eventos com erro permanecem na fila.' : 'Sincronizado.';
    return {
      online: true,
      reachable: true,
      pushed: acknowledged.length,
      failed: failedItems.length,
      cursor: nextCursor,
      feedbackResolved,
      message: feedbackResolved ? `${baseMessage} ${feedbackResolved} resultado(s) offline atualizado(s).` : baseMessage,
    };
  } catch (error) {
    if (rows.length) await markOutboxError(rows.map((row) => row.event_id), (error as Error)?.message || 'Falha de rede');
    return { online: true, reachable: false, pushed: 0, failed: rows.length, cursor, feedbackResolved: 0, message: (error as Error)?.message || 'Falha ao sincronizar.' };
  }
}

/**
 * Confirma somente os eventos da resposta atual e recebe o feedback na mesma
 * requisição. Não reconstrói o pacote offline nem recarrega o bootstrap; essas
 * tarefas seguem depois pelo sync normal e não bloqueiam a interação.
 */
export async function runAnswerSync(
  api: ReturnType<typeof import('./api').createApi>,
  transportKey: string,
  examProjectId: string,
  attemptId: string,
  events: LearningEvent[],
): Promise<AnswerSyncResult> {
  const metaKey = cursorKey(transportKey);
  const cursor = Number((await getMeta(metaKey)) || 0);
  const network = await Network.getNetworkStateAsync();
  if (!network.isConnected) {
    return { online: false, reachable: false, pushed: 0, failed: 0, cursor, feedbackResolved: 0, feedback: null, message: 'Sem rede. Resposta preservada no aparelho.' };
  }
  try {
    const response = await api.sync(cursor, events, examProjectId, 0, {
      refreshOfflinePack: false,
      feedbackAttemptId: attemptId,
      timeoutMs: 6_000,
      pullLimit: 1,
    });
    const accepted = new Set<string>(response?.push?.accepted || []);
    const duplicates = new Set<string>(response?.push?.duplicates || []);
    const acknowledged = events.map((event) => event.event_id).filter((id) => accepted.has(id) || duplicates.has(id));
    await removeOutbox(acknowledged);
    const failedItems: Array<{ event_id?: string; error?: string }> = response?.push?.failed || [];
    for (const failed of failedItems) {
      if (failed.event_id) await markOutboxError([failed.event_id], failed.error || 'Falha de sincronização');
    }
    const nextCursor = Number(response?.pull?.cursor ?? cursor);
    await setMeta(metaKey, String(nextCursor));
    const feedback = response?.feedback || null;
    if (feedback) await saveFeedback(attemptId, feedback);
    return {
      online: true,
      reachable: true,
      pushed: acknowledged.length,
      failed: failedItems.length,
      cursor: nextCursor,
      feedbackResolved: feedback ? 1 : 0,
      feedback,
      message: feedback ? 'Resposta confirmada.' : 'Resposta sincronizada; feedback ainda indisponível.',
    };
  } catch (error) {
    const ids = events.map((event) => event.event_id);
    if (ids.length) await markOutboxError(ids, (error as Error)?.message || 'Falha de rede');
    return { online: true, reachable: false, pushed: 0, failed: events.length, cursor, feedbackResolved: 0, feedback: null, message: (error as Error)?.message || 'Falha ao confirmar a resposta.' };
  }
}
