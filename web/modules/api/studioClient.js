function sessionToken() {
    const fromQuery = new URLSearchParams(window.location.search).get('qf_token') ?? '';
    return fromQuery || window.sessionStorage.getItem('qf-http-token') || '';
}
export async function studioRequest(path, init = {}) {
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
        const envelope = await response.json();
        if (!response.ok || envelope.ok === false) {
            throw new Error(envelope.error || `Falha no Studio (${response.status}).`);
        }
        return (envelope.data ?? envelope);
    }
    finally {
        window.clearTimeout(timer);
    }
}
export function studioGet(path) {
    return studioRequest(path, { method: 'GET' });
}
export function studioPost(path, body) {
    return studioRequest(path, { method: 'POST', body: JSON.stringify(body) });
}
