export type PairingPayload = {
  token: string;
  server: string;
  servers: string[];
  cloud: string;
  api: string;
};

function normalizeServer(value: string): string {
  const trimmed = String(value || '').trim().replace(/\/+$/, '');
  if (!trimmed) return '';
  if (!/^https?:\/\//i.test(trimmed)) return `http://${trimmed}`;
  return trimmed;
}

export function parsePairingValue(value: string): PairingPayload {
  const raw = String(value || '').trim();
  if (!raw) return { token: '', server: '', servers: [], cloud: '', api: 'v1' };

  if (raw.startsWith('questflow://')) {
    const query = raw.includes('?') ? raw.slice(raw.indexOf('?') + 1) : '';
    const params = new URLSearchParams(query);
    const servers = params.getAll('server').map(normalizeServer).filter(Boolean);
    return {
      token: params.get('token') || '',
      server: servers[0] || '',
      servers: Array.from(new Set(servers)),
      cloud: normalizeServer(params.get('cloud') || ''),
      api: params.get('api') || 'v1',
    };
  }

  // Textual fallback: a bare pairing token.
  return { token: raw, server: '', servers: [], cloud: '', api: 'v1' };
}

export function normalizeApiBase(value: string): string {
  return normalizeServer(value);
}
