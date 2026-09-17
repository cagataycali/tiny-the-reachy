// Full-screen passkey gate — nothing else renders until this calls onAuth (scout.cagatay.my pattern).
// Server side is gated too (dashboard/auth.py + the _gate middleware): this card is the UI for it, not the security.
import { useCallback, useEffect, useState } from 'react'
import { startAuthentication, startRegistration } from '@simplewebauthn/browser'
import { AuthStatus, api, setToken } from '../lib/api'

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
    check().catch(() => { setMsg('dashboard unreachable — retrying'); setErr(true) }).finally(() => setBusy(false))
    const t = setInterval(() => { if (!document.hidden) check().catch(() => {}) }, 15000)   // a robot reboot / expired session self-heals
    return () => clearInterval(t)
  }, [check])

  const say = (m: string, bad = false) => { setMsg(m); setErr(bad) }
  const run = async (fn: () => Promise<void>) => { setBusy(true); try { await fn() } catch (e: any) { say(e?.name === 'NotAllowedError' ? 'cancelled — try again' : (e?.message || String(e)), true) } finally { setBusy(false) } }

  const login = () => run(async () => {
    say('waiting for your passkey…')
    const opts = await post('/api/auth/login/begin', {})
    const cred = await startAuthentication({ optionsJSON: opts })
    await post('/api/auth/login/complete', cred)
    say('signed in ✓'); await check()
  })
  const enrol = () => run(async () => {
    say('creating a passkey on this device…')
    const opts = await post('/api/auth/register/begin', { token: reg.trim() })
    const cred = await startRegistration({ optionsJSON: opts })
    await post('/api/auth/register/complete', { ...cred, label: navigator.platform || 'passkey' })
    say('passkey enrolled ✓'); await check()
  })
  const useToken = () => run(async () => {
    setToken(tok.trim())
    const a = await api.auth()
    if (!a.authenticated) { setToken(''); throw new Error('token refused') }
    say('signed in ✓'); await check()
  })

  const first = !!st && !st.has_credentials && st.registration_open      // TOFU: first device becomes the owner
  const primary = mode === 'token' ? useToken : (mode === 'enrol-more' || first) ? enrol : login
  const label = busy ? '…' : mode === 'token' ? '✦ Use token' : (mode === 'enrol-more' || first) ? '✦ Enrol this device' : '✦ Continue'
  const sub = !st ? 'authenticating…'
    : mode === 'token' ? 'Paste the owner token. It stays in this tab only.'
    : mode === 'enrol-more' ? 'Enrol another device — needs the enrolment token.'
    : first ? 'No passkey yet. The first device to enrol becomes the owner.'
    : st.has_credentials ? 'Authenticate with your passkey (Face ID / Touch ID / security key).'
    : 'Passkeys are off — sign in with the owner token.'
  const canPasskey = !!st?.passkeys && (st.has_credentials || st.registration_open)

  return (
    <div className="auth-gate" data-testid="auth-gate">
      <div className="auth-card glass">
        <div className="auth-logo">🤖</div>
        <h2>tiny</h2>
        <p className="auth-sub">{sub}</p>
        {mode === 'token' && <div className="auth-field"><label>Owner token</label>
          <input type="password" autoComplete="off" placeholder="REACHY_TOKEN" value={tok} onChange={(e) => setTok(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && tok && useToken()} data-testid="gate-token" /></div>}
        {mode === 'enrol-more' && <div className="auth-field"><label>Enrolment token</label>
          <input type="password" autoComplete="off" placeholder="REACHY_REG_TOKEN" value={reg} onChange={(e) => setReg(e.target.value)} /></div>}
        <button className="auth-btn" disabled={busy || (mode === 'token' && !tok.trim()) || (mode === 'passkey' && !canPasskey && !!st)} onClick={primary} data-testid="gate-primary">{label}</button>
        <div className={'auth-msg' + (err ? ' err' : '')} data-testid="gate-msg">{msg}</div>
        <div className="auth-links">
          {mode !== 'token' && <a onClick={() => { setMode('token'); say('') }}>use a token</a>}
          {mode !== 'passkey' && <a onClick={() => { setMode('passkey'); say('') }}>passkey</a>}
          {mode === 'passkey' && st?.has_credentials && st.registration_open && <a onClick={() => { setMode('enrol-more'); say('') }}>enrol another device</a>}
        </div>
        <p className="auth-foot">Passwordless · your key never leaves this device.</p>
      </div>
    </div>
  )
}
