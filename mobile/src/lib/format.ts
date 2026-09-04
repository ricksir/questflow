export function formatDuration(value: number | null | undefined, opts?: { compact?: boolean; zeroLabel?: string; suffix?: string }) {
  if (value == null || Number.isNaN(Number(value))) return opts?.zeroLabel || '—';
  const seconds = Math.max(0, Math.round(Number(value)));
  if (seconds < 60) {
    const base = `${seconds} ${seconds === 1 ? 'segundo' : 'segundos'}`;
    return opts?.suffix ? `${base} ${opts.suffix}` : base;
  }
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const secs = seconds % 60;

  if (opts?.compact) {
    if (hours > 0) return `${hours}h ${minutes}min`;
    if (minutes > 0 && secs > 0) return `${minutes}min ${secs}s`;
    return `${minutes} min`;
  }

  const parts: string[] = [];
  if (hours > 0) parts.push(`${hours} ${hours === 1 ? 'hora' : 'horas'}`);
  if (minutes > 0) parts.push(`${minutes} ${minutes === 1 ? 'minuto' : 'minutos'}`);
  if (secs > 0 && hours === 0) parts.push(`${secs} ${secs === 1 ? 'segundo' : 'segundos'}`);
  const base = parts.join(' e ');
  return opts?.suffix ? `${base} ${opts.suffix}` : base;
}

export function formatDurationShort(value: number | null | undefined, fallback = '—') {
  if (value == null || Number.isNaN(Number(value))) return fallback;
  const seconds = Math.max(0, Math.round(Number(value)));
  if (seconds < 60) return `${seconds}s`;
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const secs = seconds % 60;
  if (hours > 0) return `${hours}h ${minutes}min`;
  if (secs === 0) return `${minutes}min`;
  return `${minutes}min ${secs}s`;
}

export function shortenMiddle(value: string | null | undefined, max = 40) {
  const text = String(value || '').trim();
  if (!text) return '—';
  if (text.length <= max) return text;
  const head = Math.ceil((max - 3) / 2);
  const tail = Math.floor((max - 3) / 2);
  return `${text.slice(0, head)}...${text.slice(-tail)}`;
}
