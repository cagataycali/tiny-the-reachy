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
  reel: Reel; t: number; tracking?: Tracking
  /** perception (owned by the face-tracking/DoA/IMU lane; the dashboard renders nothing when absent/null) */
  doa?: Doa | null; imu?: Imu | null
  /** daemon pressure gauge (dashboard/daemonlink.py): fds of the reachy-mini daemon + sockets on :8000; warn = short text or null */
  pressure?: Pressure | null; stream?: StreamStatus | null; state_age_s?: number
  /** DoA turn-toward-speaker controller (dashboard/doa.py) */
  doa_turn?: DoaTurn | null
}
export type Pressure = { pid: number | null; fds: number | null; fd_limit: number | null; close_wait: number | null; established: number | null; warn: string | null }
export type StreamStatus = { connected: boolean; hz: number; frames: number; reconnects: number; age_s: number | null; error: string | null }
export type DoaTurn = { enabled: boolean; armed?: boolean; turns?: number; last_turn_t?: number | null; angle_deg?: number | null; speech?: boolean; why?: string | null; sign?: number }
/** ReSpeaker direction of arrival passed through from the daemon's state: angle in rad (0 = front), speech_detected */
export type Doa = { angle: number | null; speech_detected?: boolean | null }
/** IMU summary — consumed fields: lifted|picked_up, tilted (booleans); anything else is ignored */
export type Imu = { lifted?: boolean; picked_up?: boolean; tilted?: boolean; tilt_deg?: number | null; [k: string]: unknown }
/** daemon face tracking (reachy-mini ≥ 1.10): x,y = face centre in the camera frame, normalised to [-1, 1] */
export type Tracking = { enabled: boolean; paused?: boolean; holds?: string[]; detected: boolean; x: number | null; y: number | null
  roll?: number | null; weight?: number | null; available?: boolean | null; error?: string | null; face_age_s?: number | null; engine?: string }
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
  tracking: (enabled: boolean) => req<{ ok: boolean; tracking: Tracking }>('POST', '/api/tracking', { enabled }),
  credentials: () => req<{ credentials: { id: string; label: string; created: string; sign_count: number }[] }>('GET', '/api/auth/credentials'),
  deleteCredential: (id: string) => req('DELETE', `/api/auth/credentials/${id}`),
}

/** URL for <img>/<video>-style loads that cannot set headers: the passkey cookie rides along by itself, a bearer goes as ?token=. */
export function streamUrl(path = '/api/stream', extra = ''): string {
  const t = getToken()
  return `${path}?${extra}${extra ? '&' : ''}${t ? `token=${encodeURIComponent(t)}` : 'c=1'}`
}

export function wsUrl(): string {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  const t = getToken()
  return `${proto}://${location.host}/ws${t ? `?token=${encodeURIComponent(t)}` : ''}`
}
