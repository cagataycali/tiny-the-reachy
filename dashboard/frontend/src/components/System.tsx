// Telemetry strip (CM4 host + persona services) and the Lock card (passkeys / session / demo mode).
import { useEffect, useState } from 'react'
import { startRegistration } from '@simplewebauthn/browser'
import { AuthStatus, State, api } from '../lib/api'

const SVC_LABEL: Record<string, string> = { 'tiny-voice': '🎙 voice', 'tiny-telegram': '💬 telegram', 'tiny-thinker': '🧠 thinker', 'tiny-mhs': '🕸 mesh', 'tiny-tts': '🔊 tts', 'reachy-tunnel': '☁ tunnel' }

function bars(dbm: number | null): string { if (dbm == null) return '—'; return dbm > -55 ? '▂▄▆█' : dbm > -65 ? '▂▄▆' : dbm > -75 ? '▂▄' : '▂' }
function fmtUp(s: number | null | undefined): string { if (!s) return '—'; const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60); return h ? `${h}h${m.toString().padStart(2, '0')}` : `${m}m` }

export function Telemetry({ s }: { s: State | null }) {
  const sys = s?.system, svc = s?.services ?? {}
  const warn = (v: number | null | undefined, hi: number) => (v != null && v >= hi ? 'warn' : '')
  return (
    <div className="telemetry" data-testid="telemetry">
      <span className={`tm ${warn(sys?.cpu_c, 70)}`} title="CM4 CPU temperature">🌡 {sys?.cpu_c ?? '—'}°C</span>
      <span className={`tm ${warn(sys?.load1, (sys?.cores ?? 4) * 0.9)}`} title="load average (1 min)">⚙ {sys?.load1 ?? '—'}</span>
      <span className={`tm ${warn(sys?.mem_used_pct, 85)}`} title="memory used">▤ {sys?.mem_used_pct ?? '—'}%</span>
      <span className={`tm ${sys?.disk_free_gb != null && sys.disk_free_gb < 1 ? 'warn' : ''}`} title="disk free">💾 {sys?.disk_free_gb ?? '—'} GB</span>
      <span className="tm" title={`Wi-Fi ${s?.wifi?.ssid ?? ''} ${sys?.wifi_signal_dbm ?? ''} dBm`}>📶 {bars(sys?.wifi_signal_dbm ?? null)} {s?.wifi?.ssid ?? '—'}</span>
      <span className="tm" title="CM4 uptime">⏱ {fmtUp(sys?.host_uptime_s)}</span>
      <span className="tm svcs" title="persona services (systemd --user)">
        {Object.keys(SVC_LABEL).map((k) => <span key={k} className={`svc ${svc[k] === 'active' ? 'on' : svc[k] ? 'off' : 'unk'}`} title={`${k}: ${svc[k] ?? 'unknown'}`}>{SVC_LABEL[k]}</span>)}
      </span>
    </div>
  )
}

export function LockCard({ auth, can, demo, onDemo, onToast }: { auth: AuthStatus | null; can: boolean; demo: boolean; onDemo: (on: boolean) => Promise<unknown>; onToast: (m: string) => void }) {
  const [creds, setCreds] = useState<{ id: string; label: string; created: string; sign_count: number }[] | null>(null)
  const [reg, setReg] = useState('')
  const [busy, setBusy] = useState(false)
  const load = async () => { if (!can || !auth?.passkeys) return; try { setCreds((await api.credentials()).credentials) } catch { setCreds([]) } }
  useEffect(() => { load() }, [can, auth?.passkeys])
  const remove = async (id: string, label: string) => {
    if (!confirm(`Remove passkey "${label}"? That device can no longer drive.`)) return
    try { await api.deleteCredential(id); onToast('passkey removed'); load() } catch (e: any) { onToast(e.message) }
  }
  const enrol = async () => {
    setBusy(true)
    try {
      const post = async (url: string, body: unknown) => { const r = await fetch(url, { method: 'POST', headers: { 'content-type': 'application/json', ...(sessionStorage.getItem('reachy_token') ? { authorization: `Bearer ${sessionStorage.getItem('reachy_token')}` } : {}) }, body: JSON.stringify(body), credentials: 'same-origin' }); const d = await r.json(); if (!r.ok) throw new Error(d.message || d.detail?.error || r.statusText); return d }
      const opts = await post('/api/auth/register/begin', { token: reg })
      const cred = await startRegistration({ optionsJSON: opts })
      await post('/api/auth/register/complete', { ...cred, label: prompt('Label for this passkey', navigator.platform || 'passkey') || 'passkey' })
      onToast('passkey enrolled ✓'); setReg(''); load()
    } catch (e: any) { onToast(e.message) } finally { setBusy(false) }
  }
  return (
    <div className="lock" data-testid="lock">
      <div className="lockrow">
        <span className={`dot ${can ? 'on' : ''}`} /> {can ? <>unlocked · <b>{auth?.who}</b> drives</> : <>locked · public view</>}
        <span className="muted small"> · rp {auth?.rp_id ?? '—'} · {auth?.passkeys ? (auth.has_credentials ? 'passkeys' : 'passkeys (none enrolled, TOFU open)') : 'passkeys off'}{auth?.token_configured ? ' · token' : ''}</span>
      </div>
      <div className="lockrow demo">
        <label className="switch" title="Demo mode pauses the thinker persona so it never overlaps your moves">
          <input type="checkbox" checked={demo} disabled={!can} onChange={(e) => onDemo(e.target.checked)} data-testid="demo-toggle" />
          <span className="track" /> 🎪 demo mode {demo ? <b className="ok">ON · thinker paused</b> : <span className="muted">off · thinker emotes every ~30 s</span>}
        </label>
      </div>
      {can && auth?.passkeys && (
        <div className="creds">
          <div className="muted small">Passkeys that can drive TINY:</div>
          {creds === null ? <div className="muted small">…</div> : creds.length === 0 ? <div className="muted small">none — you are on the owner token</div> : creds.map((c) => (
            <div key={c.id} className="cred"><span>🔑 {c.label}</span><span className="muted small">{c.created?.slice(0, 10)} · used {c.sign_count}×</span><button className="btn ghost small" onClick={() => remove(c.id, c.label)}>remove</button></div>
          ))}
          <div className="inline">
            {auth.has_credentials && <input placeholder="enrolment token (REACHY_REG_TOKEN)" value={reg} onChange={(e) => setReg(e.target.value)} />}
            <button className="btn" disabled={busy || (auth.has_credentials && !reg)} onClick={enrol}>＋ enrol this device</button>
          </div>
        </div>
      )}
      <div className="muted small keys">⌨ shortcuts: <kbd>←</kbd><kbd>→</kbd><kbd>↑</kbd><kbd>↓</kbd> look · <kbd>H</kbd> home · <kbd>Space</kbd> stop · <kbd>D</kbd> demo · <kbd>/</kbd> ask</div>
    </div>
  )
}
