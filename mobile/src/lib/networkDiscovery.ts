export function uniqueApiBases(values: string[]): string[] {
  const seen = new Set<string>();
  const result: string[] = [];
  for (const value of values) {
    const normalized = String(value || '').trim().replace(/\/+$/, '');
    if (!normalized || seen.has(normalized)) continue;
    seen.add(normalized);
    result.push(normalized);
  }
  return result;
}

export function ipv4Prefix(value: string): string {
  const match = String(value || '').trim().match(/^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$/);
  if (!match) return '';
  const octets = match.slice(1).map(Number);
  if (octets.some((part) => part < 0 || part > 255)) return '';
  return `${octets[0]}.${octets[1]}.${octets[2]}`;
}

export function apiBaseIpv4(value: string): string {
  try {
    const url = new URL(value);
    return /^\d{1,3}(\.\d{1,3}){3}$/.test(url.hostname) ? url.hostname : '';
  } catch {
    return '';
  }
}

export function apiBasesOnDeviceSubnet(deviceIp: string, values: string[]): string[] {
  const prefix = ipv4Prefix(deviceIp);
  if (!prefix) return [];
  return uniqueApiBases(values).filter((base) => apiBaseIpv4(base).startsWith(`${prefix}.`));
}

export function developmentServerApiBase(hostUri: string, port = 53155): string {
  const raw = String(hostUri || '').trim();
  if (!raw) return '';
  const withoutScheme = raw.replace(/^https?:\/\//i, '');
  const hostPart = withoutScheme.split('/')[0] ?? '';
  const host = (hostPart.split(':')[0] ?? '').replace(/^\[|\]$/g, '');
  if (!/^\d{1,3}(\.\d{1,3}){3}$/.test(host)) return '';
  return `http://${host}:${port}`;
}

export function ipv4SubnetCandidates(deviceIp: string, port = 53155, preferred: string[] = []): string[] {
  const prefix = ipv4Prefix(deviceIp);
  if (!prefix) return uniqueApiBases(preferred);
  const ownHost = Number(String(deviceIp).trim().split('.')[3] ?? '0');
  const generated: string[] = [];
  for (let host = 1; host <= 254; host += 1) {
    if (host === ownHost) continue;
    generated.push(`http://${prefix}.${host}:${port}`);
  }
  return uniqueApiBases([...preferred, ...generated]);
}
