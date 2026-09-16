import { useState } from 'react'
import { startAuthentication, startRegistration } from '@simplewebauthn/browser'
import { AuthStatus, api, setToken } from '../lib/api'

export function Login({ auth, onChange }: { auth: AuthStatus | null; onChange: () => void }) {
  const [open, setOpen] = useState(false)
  const [msg, setMsg] = useState('')
  const [reg, setReg] = useState('')
  const [tok, setTok] = useState('')
  const post = async (url: string, body: unknown) => {
    const r = await fetch(url, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body), credentials: 'same-origin' })
    const d = await r.json(); if (!r.ok) throw new Error(d.message || d.detail?.error || r.statusText); return d
  }
  const login = async () => {
    try { setMsg('…'); const opts = await post('/api/auth/login/begin', {}); const cred = await startAuthentication({ optionsJSON: opts })
      await post('/api/auth/login/complete', cred); setMsg('signed in ✓'); setOpen(false); onChange(); location.reload() } catch (e: any) { setMsg(e.message) }
  }
  const enrol = async () => {
    try { setMsg('…'); const opts = await post('/api/auth/register/begin', { token: reg }); const cred = await startRegistration({ optionsJSON: opts })
      await post('/api/auth/register/complete', { ...cred, label: navigator.platform || 'passkey' }); setMsg('passkey enrolled ✓'); setOpen(false); onChange(); location.reload() } catch (e: any) { setMsg(e.message) }
  }
  const useToken = () => { setToken(tok.trim()); setOpen(false); location.reload() }
  const logout = async () => { setToken(''); try { await api.logout() } catch {} location.reload() }
  if (auth?.authenticated) return <button className="btn ghost" onClick={logout}>🔓 {auth.who} · sign out</button>
  return (
    <>
      <button className="btn primary" onClick={() => setOpen(true)}>🔐 Sign in to drive</button>
      {open && (
        <div className="modal" onClick={() => setOpen(false)}>
          <div className="sheet" onClick={(e) => e.stopPropagation()}>
            <h3>Sign in</h3>
            <p className="muted">Anyone can watch. Only the owner drives — with a passkey (Face ID / Touch ID) or the owner token.</p>
            {auth?.passkeys && auth.has_credentials && <button className="btn primary wide" onClick={login}>Use passkey</button>}
            {auth?.passkeys && auth.registration_open && (
              <div className="stack">
                <div className="muted small">{auth.has_credentials ? 'Enrol another device (needs the enrolment token):' : 'No passkey yet — first enrolment is open (TOFU):'}</div>
                {auth.has_credentials && <input placeholder="enrolment token" value={reg} onChange={(e) => setReg(e.target.value)} />}
                <button className="btn wide" onClick={enrol}>Enrol this device's passkey</button>
              </div>
            )}
            <div className="stack">
              <div className="muted small">Owner token (kept in this tab only):</div>
              <input type="password" placeholder="REACHY_TOKEN" value={tok} onChange={(e) => setTok(e.target.value)} />
              <button className="btn wide" onClick={useToken} disabled={!tok}>Use token</button>
            </div>
            {msg && <div className="msg">{msg}</div>}
          </div>
        </div>
      )}
    </>
  )
}
