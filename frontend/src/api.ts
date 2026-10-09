export type Kind = 'movie' | 'series' | 'game'
export type Status = 'want' | 'active' | 'done' | 'paused'
export type User = { id: number; username: string; role: 'admin' | 'friend'; language: 'ru' | 'en' }
export type Item = {
  id: number; kind: Kind; title: string; year: number | null; status: Status;
  description: string; genres: string; image_url: string | null; source_url: string | null;
  season_number: number | null; episode_number: number | null;
  source: 'tmdb' | 'rawg' | null; external_id: string | null;
  notes?: { id: number; text: string; username: string; created_at: string }[];
  history?: { status: Status; username: string; created_at: string }[]
}
export type Candidate = Omit<Item, 'id' | 'status' | 'season_number' | 'episode_number'>

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch('/api' + path, {
    credentials: 'include',
    ...options,
    headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'PlayWatch', ...options.headers }
  })
  if (response.status === 204) return undefined as T
  const data = await response.json().catch(() => ({}))
  if (!response.ok) {
    const raw = data.detail
    const message = typeof raw === 'string' ? raw : Array.isArray(raw) ? raw.map((e: { msg: string }) => e.msg).join(', ') : 'Request failed'
    throw new Error(message)
  }
  return data as T
}

export const json = (body: unknown, method = 'POST'): RequestInit => ({ method, body: JSON.stringify(body) })
