// Full-screen passkey gate: nothing else renders until this calls onAuth (scout.cagatay.my pattern). Styled as a Strands card.
// Server side is gated too (dashboard/auth.py + the _gate middleware): this card is the UI for it, not the security.
import { useCallback, useEffect, useState } from 'react'
import { startAuthentication, startRegistration } from '@simplewebauthn/browser'
import { AuthStatus, api, setToken } from '../lib/api'
import { Wordmark } from './Brand'

async function post(url: string, body: unknown) {
  const r = await fetch(url, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body), credentials: 'same-origin' })
  const d = await r.json().catch(() => ({}))
  if (!r.ok) throw new Error(d.message || d.detail?.error || d.error || r.statusText)
  return d
}

export function Gate({ onAuth }: { onAuth: (a: AuthStatus) => void }) {
  const [st, setSt] = useState<AuthStatus | null>(null)
  const [busy, setBusy] = useState(true)
  const [msg, setMsg] = useState('')
  const [err, setErr] = useState(false)
  const [mode, setMode] = useState<'passkey' | 'token' | 'enrol-more'>('passkey')
  const [tok, setTok] = useState('')
  const [reg, setReg] = useState('')

  const check = useCallback(async () => {
    const a = await api.auth()
    setSt(a)
    if (a.authenticated) onAuth(a)
    return a
  }, [onAuth])

  useEffect(() => {
    check().catch(() => { setMsg('dashboard unreachable, retrying'); setErr(true) }).finally(() => setBusy(false))
    const t = setInterval(() => { if (!document.hidden) check().catch(() => {}) }, 15000)   // a robot reboot / expired session self-heals
    return () => clearInterval(t)
  }, [check])

  const say = (m: string, bad = false) => { setMsg(m); setErr(bad) }
  const run = async (fn: () => Promise<void>) => { setBusy(true); try { await fn() } catch (e: any) { say(e?.name === 'NotAllowedError' ? 'cancelled, try again' : (e?.message || String(e)), true) } finally { setBusy(false) } }

  const login = () => run(async () => {
    say('waiting for your passkey')
    const opts = await post('/api/auth/login/begin', {})
    const cred = await startAuthentication({ optionsJSON: opts })
    await post('/api/auth/login/complete', cred)
    say('signed in'); await check()
  })
  const enrol = () => run(async () => {
    say('creating a passkey on this device')
    const opts = await post('/api/auth/register/begin', { token: reg.trim() })
    const cred = await startRegistration({ optionsJSON: opts })
    await post('/api/auth/register/complete', { ...cred, label: navigator.platform || 'passkey' })
    say('passkey enrolled'); await check()
  })
  const useToken = () => run(async () => {
    setToken(tok.trim())
    const a = await api.auth()
    if (!a.authenticated) { setToken(''); throw new Error('token refused') }
    say('signed in'); await check()
  })

  const first = !!st && !st.has_credentials && st.registration_open      // TOFU: first device becomes the owner
  const primary = mode === 'token' ? useToken : (mode === 'enrol-more' || first) ? enrol : login
  const label = busy ? 'working' : mode === 'token' ? 'Use token' : (mode === 'enrol-more' || first) ? 'Enrol this device' : 'Continue with passkey'
  const sub = !st ? 'checking the session'
    : mode === 'token' ? 'Paste the owner token. It stays in this tab only.'
    : mode === 'enrol-more' ? 'Add this phone or laptop to the people who may drive the robot.'
    : first ? 'No passkey yet. The first device to enrol becomes the owner.'
    : st.has_credentials ? 'The cockpit for the Reachy Mini: live camera, digital twin, head and antenna control, the agent timeline. Sign in with your passkey.'
    : 'Passkeys are off on this deployment. Sign in with the owner token.'
  const canPasskey = !!st?.passkeys && (st.has_credentials || st.registration_open)

  // Mode-specific copy. The team mate sees the passkey card first; the two other paths are quiet links below.
  const title = mode === 'token' ? 'Sign in with a token' : mode === 'enrol-more' ? 'Enrol this device' : first ? 'Set up the first passkey' : 'Sign in'
  const hint = mode === 'enrol-more' ? <>Ask the owner for the one-time enrolment token (<code>REACHY_REG_TOKEN</code>), paste it here, then confirm with Face ID, Touch ID or your security key. After that this device signs in with the passkey alone.</>
    : mode === 'token' ? <>The owner token is the machine key for scripts. People should enrol a passkey instead.</>
    : null
  const link = (text: string, to: typeof mode) => <a role="button" tabIndex={0} onClick={() => { setMode(to); say('') }} onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setMode(to); say('') } }}>{text}</a>

  return (
    <div className="auth-gate" data-testid="auth-gate">
      <main className="auth-card" aria-labelledby="gate-title">
        <div className="auth-brand"><Wordmark /><span className="project">/ reachy</span></div>
        <h1 id="gate-title">{title}</h1>
        <p className="auth-sub">{sub}</p>
        {mode === 'token' && <div className="auth-field"><label htmlFor="gate-token">Owner token</label>
          <input id="gate-token" type="password" autoComplete="off" placeholder="REACHY_TOKEN" value={tok} onChange={(e) => setTok(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && tok && useToken()} data-testid="gate-token" /></div>}
        {mode === 'enrol-more' && <div className="auth-field"><label htmlFor="gate-reg">Enrolment token</label>
          <input id="gate-reg" type="password" autoComplete="off" placeholder="REACHY_REG_TOKEN" value={reg} onChange={(e) => setReg(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && reg.trim() && enrol()} data-testid="gate-reg" /></div>}
        {hint && <p className="auth-hint">{hint}</p>}
        <button className="auth-btn" disabled={busy || (mode === 'token' && !tok.trim()) || (mode === 'enrol-more' && !reg.trim()) || (mode === 'passkey' && !canPasskey && !!st)} onClick={primary} data-testid="gate-primary">{label}</button>
        <div className={'auth-msg' + (err ? ' err' : '')} data-testid="gate-msg" role="status" aria-live="polite">{msg}</div>
        <div className="auth-links">
          {mode !== 'passkey' && link('back to passkey', 'passkey')}
          {mode === 'passkey' && st?.has_credentials && st.registration_open && link('enrol another device', 'enrol-more')}
          {mode !== 'token' && link('use a token', 'token')}
        </div>
        <p className="auth-foot">Passkeys are passwordless: the key stays on your device and the robot only learns its public half. Every control write is logged with your name.</p>
      </main>
    </div>
  )
}
