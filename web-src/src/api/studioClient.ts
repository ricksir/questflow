export type StudioEnvelope<T> = {
  ok: boolean;
  contract?: 'questflow.studio.v1';
  operation?: string;
  module?: string;
  data?: T;
  error?: string;
  code?: string;
};

function sessionToken(): string {
  const fromQuery = new URLSearchParams(window.location.search).get('qf_token') ?? '';
  return fromQuery || window.sessionStorage.getItem('qf-http-token') || '';
}

export async function studioRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), 30_000);
  try {
    const response = await fetch(`/api/v1/studio/${path.replace(/^\//, '')}`, {
      ...init,
      cache: 'no-store',
      signal: controller.signal,
      headers: {
        Accept: 'application/json',
        'X-QuestFlow-Token': sessionToken(),
        ...(init.body ? { 'Content-Type': 'application/json' } : {}),
        ...(init.headers ?? {}),
      },
    });
    const envelope = await response.json() as StudioEnvelope<T>;
    if (!response.ok || envelope.ok === false) {
      throw new Error(envelope.error || `Falha no Studio (${response.status}).`);
    }
    return (envelope.data ?? envelope) as T;
  } finally {
    window.clearTimeout(timer);
  }
}

export function studioGet<T>(path: string): Promise<T> {
  return studioRequest<T>(path, { method: 'GET' });
}

export function studioPost<T>(path: string, body: Record<string, unknown>): Promise<T> {
  return studioRequest<T>(path, { method: 'POST', body: JSON.stringify(body) });
}

