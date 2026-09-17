// Thin client for dashboard/server.py. The bearer token (owner) lives in sessionStorage; passkey sessions are cookies.
export type Head = { x_mm: number; y_mm: number; z_mm: number; roll: number; pitch: number; yaw: number }
export type NowPlaying = { name: string; started: number; family: string } | null
export type Reel = { running: boolean; step: number; steps: string[]; elapsed: number; total_s: number; aborted: string | null }
export type State = {
  ok: boolean; error?: string; control_mode: string | null; head: Head | null; body_yaw: number | null
  antennas: [number, number] | null; moves_running: number; now_playing: NowPlaying
  joints: number[] | null; target: number[] | null; head_rad: Record<string, number> | null
  daemon: { state?: string; version?: string; loop_hz?: number; media_released?: boolean }
  wifi: { ssid: string | null }; uptime_s: number; demo?: boolean
  system?: { cpu_c: number | null; load1: number | null; cores?: number; mem_used_pct: number | null; disk_free_gb: number | null; disk_used_pct?: number; wifi_signal_dbm: number | null; host_uptime_s: number | null }
  services?: Record<string, string>; camera: { ok: boolean; fps: number; error: string | null; clients: number }
  reel: Reel; t: number
}
export type LogRow = { id: number; persona: string; role: string; text: string; meta: any; ts: string }
export type Event = { t: number; kind: string; who: string; text: string; seq?: number }
export type AgentEvent = { type: 'agent'; event: 'start' | 'text' | 'tool' | 'end' | 'timeout'; text?: string; name?: string
  input?: string; reply?: string; ok?: boolean; error?: string; seconds?: number; who?: string; t: number }
export type Emotions = { names: string[]; groups: { family: string; moves: string[] }[]; now_playing: NowPlaying }
export type AuthStatus = { who: string | null; authenticated: boolean; open: boolean; token_configured: boolean
  passkeys: boolean; rp_id: string | null; has_credentials: boolean; registration_open: boolean }

const TOKEN_KEY = 'reachy_token'
export const getToken = () => sessionStorage.getItem(TOKEN_KEY) || ''
export const setToken = (t: string) => t ? sessionStorage.setItem(TOKEN_KEY, t) : sessionStorage.removeItem(TOKEN_KEY)

function headers(json = true): HeadersInit {
  const h: Record<string, string> = {}
  if (json) h['content-type'] = 'application/json'
  const t = getToken(); if (t) h['authorization'] = `Bearer ${t}`
  return h
}

export class ApiError extends Error { constructor(public status: number, msg: string) { super(msg) } }

async function req<T>(method: string, url: string, body?: unknown): Promise<T> {
  const r = await fetch(url, { method, headers: headers(body !== undefined), body: body === undefined ? undefined : JSON.stringify(body), credentials: 'same-origin' })
  const text = await r.text()
  let data: any = null; try { data = text ? JSON.parse(text) : null } catch { data = { raw: text } }
  if (!r.ok) throw new ApiError(r.status, (data && (data.detail?.error || data.error || data.message || data.detail)) || `${r.status}`)
  return data as T
}

export const api = {
  state: () => req<State>('GET', '/api/state'),
  emotions: () => req<Emotions>('GET', '/api/emotions'),
  log: (n = 60) => req<{ rows: LogRow[]; events: Event[] }>('GET', `/api/log?n=${n}`),
  auth: () => req<AuthStatus>('GET', '/api/auth/status'),
  logout: () => req('POST', '/api/auth/logout', {}),
  control: (what: string, body: unknown = {}) => req<any>('POST', `/api/control/${what}`, body),
  credentials: () => req<{ credentials: { id: string; label: string; created: string; sign_count: number }[] }>('GET', '/api/auth/credentials'),
  deleteCredential: (id: string) => req('DELETE', `/api/auth/credentials/${id}`),
}

export function wsUrl(): string {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  const t = getToken()
  return `${proto}://${location.host}/ws${t ? `?token=${encodeURIComponent(t)}` : ''}`
}
