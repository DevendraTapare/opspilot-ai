export type Data = Record<string, any>;

export async function api<T = Data>(path: string, method = 'GET', body?: unknown): Promise<T> {
  const response = await fetch(`/api/ops/${path}`, {
    method, cache: 'no-store', credentials: 'same-origin',
    headers: method === 'GET' ? {} : { 'Content-Type': 'application/json' },
    body: method === 'GET' ? undefined : JSON.stringify(body ?? {}),
  });
  const value = await response.json();
  if (!response.ok) throw new Error(typeof value.detail === 'string' ? value.detail : `HTTP_${response.status}`);
  return value as T;
}

export const short = (value?: string) => value ? value.slice(0, 8).toUpperCase() : '—';
export const human = (value?: string) => (value || 'unknown').replaceAll('_', ' ');
export const percent = (value?: number | null) => value == null ? '—' : `${(value * 100).toFixed(1)}%`;
export const number = (value?: number | null, suffix = '') => value == null ? '—' : `${Math.round(value).toLocaleString()}${suffix}`;
export const date = (value?: string) => value ? new Date(value.endsWith('Z') || /[+-]\d\d:\d\d$/.test(value) ? value : value + 'Z').toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit' }) : '—';
