import { useCallback, useEffect, useRef, useState } from 'react'
import { AgentEvent, ApiError, AuthStatus, Emotions, api } from './lib/api'
import { useSocket } from './lib/socket'
import { Avatar } from './components/Avatar'
import { Camera } from './components/Camera'
import { EmotionGrid } from './components/Emotions'
import { HeadPad } from './components/Joystick'
import { AgentLog } from './components/Log'
import { Login } from './components/Login'

type Thought = { id: number; kind: 'start' | 'text' | 'tool' | 'end' | 'timeout'; text: string }

export default function App() {
  const [auth, setAuth] = useState<AuthStatus | null>(null)
  const [emotions, setEmotions] = useState<Emotions | null>(null)
  const [toast, setToast] = useState<string>('')
  const [thoughts, setThoughts] = useState<Thought[]>([])
  const [askBusy, setAskBusy] = useState(false)
  const [ask, setAsk] = useState('')
  const [say, setSay] = useState('')
  const [roll, setRoll] = useState(0)
  const [body, setBody] = useState(0)
  const [antR, setAntR] = useState(0)
  const [antL, setAntL] = useState(0)
  const [vol, setVol] = useState<number | null>(null)
  const seq = useRef(0)

  const onAgent = useCallback((e: AgentEvent) => {
    setThoughts((t) => {
      const id = ++seq.current
      if (e.event === 'start') { setAskBusy(true); return [{ id, kind: 'start', text: e.text || '' }] }
      if (e.event === 'text') {
        const last = t[t.length - 1]
        if (last && last.kind === 'text') return [...t.slice(0, -1), { ...last, text: last.text + (e.text || '') }]
        return [...t, { id, kind: 'text', text: e.text || '' }]
      }
      if (e.event === 'tool') return [...t, { id, kind: 'tool', text: `${e.name} ${e.input || ''}`.trim() }]
      if (e.event === 'end') { setAskBusy(false); return [...t, { id, kind: 'end', text: e.ok ? `done in ${e.seconds}s` : `failed: ${e.error}` }] }
      if (e.event === 'timeout') { setAskBusy(false); return [...t, { id, kind: 'timeout', text: `timed out after ${e.seconds}s` }] }
      return t
    })
  }, [])

  const { state, hello, rows, events, connected } = useSocket(onAgent)
  const can = !!(hello?.can_control)
  const refreshAuth = useCallback(() => { api.auth().then(setAuth).catch(() => {}) }, [])
  useEffect(() => { refreshAuth(); api.emotions().then(setEmotions).catch(() => {}) }, [refreshAuth])
  useEffect(() => { if (!toast) return; const t = setTimeout(() => setToast(''), 3500); return () => clearTimeout(t) }, [toast])

  const ctl = async (what: string, body: unknown = {}) => {
    try { const r = await api.control(what, body); return r } catch (e: any) {
      setToast(e instanceof ApiError ? (e.status === 401 ? 'sign in to drive' : e.status === 429 ? 'slow down (or an ask is running)' : e.message) : String(e))
      return null
    }
  }
  const look = (yaw: number, pitch: number) => ctl('look', { yaw, pitch, roll, body_yaw: body, duration: 0.8 })
  const home = () => { setRoll(0); setBody(0); setAntR(0); setAntL(0); return ctl('home') }
  const doAsk = async () => { const t = ask.trim(); if (!t) return; setThoughts([]); const r = await ctl('ask', { text: t }); if (r) setAsk('') }
  const doSay = async () => { const t = say.trim(); if (!t) return; const r = await ctl('say', { text: t }); if (r) { setSay(''); setToast(r.engine === 'piper-local' ? `speaking (${r.seconds}s)` : (r.warning || 'queued — no voice backend')) } }

  const s = state
  const playing = s?.now_playing ?? null
  const reel = s?.reel
  const online = !!s?.ok

  return (
    <div className="app">
      <header>
        <div className="brand"><span className="logo">🤖</span><div><h1>TINY <span className="muted">· Reachy Mini</span></h1>
          <div className="sub">{online ? <span className="ok">● live</span> : <span className="bad">● daemon offline</span>} · {connected ? 'ws' : 'ws reconnecting'} · {s?.wifi?.ssid ?? '—'} · daemon {s?.daemon?.version ?? '?'} @ {s?.daemon?.loop_hz ?? 0} Hz · motors {s?.control_mode ?? '?'}{s?.moves_running ? ` · ${s.moves_running} move${s.moves_running > 1 ? 's' : ''} running` : ''}</div></div></div>
        <div className="actions">
          <button className="btn stop" disabled={!can} onClick={() => ctl('stop')}>■ STOP</button>
          <Login auth={auth} onChange={refreshAuth} />
        </div>
      </header>
      {!can && <div className="banner">👀 You're watching live. Controls unlock for the owner after sign-in.</div>}

      <main>
        <section className="card cam">
          <Camera ok={!!s?.camera?.ok} fps={s?.camera?.fps ?? 0} error={s?.camera?.error ?? null} />
          {playing && <div className="nowplaying">▶ {playing.name} <span className="muted">{playing.family}</span></div>}
        </section>

        <section className="card avatar-card">
          <Avatar head={s?.head ?? null} antennas={s?.antennas ?? null} bodyYaw={s?.body_yaw ?? null} playing={playing?.name ?? null} />
          <div className="gauges">
            {(['roll', 'pitch', 'yaw'] as const).map((k) => (
              <Gauge key={k} label={k} value={s?.head?.[k] ?? 0} max={k === 'yaw' ? 180 : 40} />
            ))}
            <Gauge label="body" value={s?.body_yaw ?? 0} max={160} />
            <Gauge label="ant R" value={s?.antennas?.[0] ?? 0} max={150} />
            <Gauge label="ant L" value={s?.antennas?.[1] ?? 0} max={150} />
          </div>
        </section>

        <section className="card">
          <h2>🎬 Demo reel <span className="muted small">{reel?.total_s ?? 0}s scripted show</span></h2>
          <div className="reel">
            {reel?.running
              ? <button className="btn stop wide" disabled={!can} onClick={() => ctl('reel', { action: 'abort' })}>■ abort reel · {reel.elapsed}s</button>
              : <button className="btn primary wide" disabled={!can} onClick={() => ctl('reel', { action: 'start' })}>▶ play the show</button>}
            <ol className="timeline">
              {(reel?.steps ?? []).map((st, i) => <li key={i} className={reel?.running ? (i < reel.step ? 'done' : i === reel.step ? 'now' : '') : ''}>{st}</li>)}
            </ol>
          </div>
        </section>

        <section className="card">
          <h2>🕹 Head</h2>
          <HeadPad can={can} onLook={look} yaw={s?.head?.yaw ?? 0} pitch={s?.head?.pitch ?? 0} />
          <Slider label="roll" v={roll} min={-40} max={40} set={setRoll} can={can} onDone={(v) => ctl('look', { roll: v, yaw: s?.head?.yaw ?? 0, pitch: s?.head?.pitch ?? 0, body_yaw: body })} />
          <Slider label="body" v={body} min={-160} max={160} set={setBody} can={can} onDone={(v) => ctl('look', { roll, yaw: s?.head?.yaw ?? 0, pitch: s?.head?.pitch ?? 0, body_yaw: v, duration: 1.2 })} />
          <div className="btnrow">
            <button className="btn" disabled={!can} onClick={home}>⌂ home</button>
            <button className="btn" disabled={!can} onClick={() => ctl('look', { yaw: 40, duration: 1 })}>◄ left</button>
            <button className="btn" disabled={!can} onClick={() => ctl('look', { yaw: -40, duration: 1 })}>right ►</button>
            <button className="btn" disabled={!can} onClick={() => ctl('look', { pitch: -25, duration: 1 })}>▲ up</button>
            <button className="btn" disabled={!can} onClick={() => ctl('look', { pitch: 25, duration: 1 })}>▼ down</button>
          </div>
        </section>

        <section className="card">
          <h2>📡 Antennas</h2>
          <Slider label="right" v={antR} min={-150} max={150} set={setAntR} can={can} onDone={(v) => ctl('antennas', { right: v, left: antL })} />
          <Slider label="left" v={antL} min={-150} max={150} set={setAntL} can={can} onDone={(v) => ctl('antennas', { right: antR, left: v })} />
          <div className="btnrow">
            <button className="btn" disabled={!can} onClick={() => { setAntR(0); setAntL(0); ctl('antennas', { right: 0, left: 0 }) }}>neutral</button>
            <button className="btn" disabled={!can} onClick={() => { setAntR(45); setAntL(-45); ctl('antennas', { right: 45, left: -45 }) }}>perk</button>
            <button className="btn" disabled={!can} onClick={() => { setAntR(-60); setAntL(60); ctl('antennas', { right: -60, left: 60 }) }}>droop</button>
            <button className="btn" disabled={!can} onClick={async () => { for (const [r, l] of [[40, -40], [-40, 40], [40, -40], [0, 0]]) { await ctl('antennas', { right: r, left: l, duration: 0.3 }); await new Promise((z) => setTimeout(z, 350)) } }}>wiggle</button>
          </div>
        </section>

        <section className="card wide2">
          <h2>🎭 Emotions <span className="muted small">{emotions?.names.length ?? 0} recorded moves</span></h2>
          <EmotionGrid emotions={emotions} playing={playing} can={can} onPlay={(n) => ctl('express', { name: n })} />
        </section>

        <section className="card">
          <h2>🗣 Say <span className="muted small">the voice persona speaks it</span></h2>
          <div className="inline">
            <input value={say} onChange={(e) => setSay(e.target.value)} placeholder="Hello Ahlsell, I'm TINY…" disabled={!can} onKeyDown={(e) => e.key === 'Enter' && doSay()} />
            <button className="btn primary" disabled={!can || !say.trim()} onClick={doSay}>say</button>
          </div>
          <h2 style={{ marginTop: 14 }}>⚙️ System</h2>
          <div className="btnrow">
            <button className="btn" disabled={!can} onClick={() => ctl('wake')}>☀ wake</button>
            <button className="btn" disabled={!can} onClick={() => confirm('Sleep the robot? The thinker persona depends on it being awake.') && ctl('sleep')}>🌙 sleep</button>
            <button className="btn" disabled={!can} onClick={() => ctl('motors', { mode: 'enabled' })}>motors on</button>
            <button className="btn" disabled={!can} onClick={() => confirm('Disable motors? The head will go limp.') && ctl('motors', { mode: 'disabled' })}>motors off</button>
          </div>
          <Slider label="volume" v={vol ?? 70} min={0} max={100} set={(v) => setVol(v)} can={can} onDone={(v) => ctl('volume', { level: v })} unit="%" />
        </section>

        <section className="card">
          <h2>💭 Ask TINY <span className="muted small">one Strands agent turn · watch it think</span></h2>
          <div className="inline">
            <input value={ask} onChange={(e) => setAsk(e.target.value)} placeholder="Who are you? Look at the camera and tell me what you see…" disabled={!can || askBusy} onKeyDown={(e) => e.key === 'Enter' && doAsk()} />
            <button className="btn primary" disabled={!can || askBusy || !ask.trim()} onClick={doAsk}>{askBusy ? '…' : 'ask'}</button>
          </div>
          <div className="thoughts">
            {thoughts.length === 0 && <div className="muted">{askBusy ? 'thinking…' : 'the agent\'s reply, tool calls and reasoning stream here'}</div>}
            {thoughts.map((t) => <div key={t.id} className={`th ${t.kind}`}>{t.kind === 'tool' ? '🔧 ' : t.kind === 'start' ? '❯ ' : t.kind === 'end' ? '✓ ' : ''}{t.text}</div>)}
          </div>
        </section>

        <section className="card wide2">
          <h2>🧠 Shared brain <span className="muted small">live agent_log — thinker · telegram · voice · dashboard</span></h2>
          <AgentLog rows={rows} events={events} />
        </section>
      </main>

      <footer className="muted small">reachy.cagatay.my · dashboard {hello?.version ?? ''} · uptime {Math.round((s?.uptime_s ?? 0) / 60)} min · {s?.camera?.clients ?? 0} viewer{(s?.camera?.clients ?? 0) === 1 ? '' : 's'} · public read-only, owner drives</footer>
      {toast && <div className="toast">{toast}</div>}
    </div>
  )
}

function Gauge({ label, value, max }: { label: string; value: number; max: number }) {
  const pct = Math.max(-1, Math.min(1, value / max))
  return (
    <div className="gauge">
      <span className="g-label">{label}</span>
      <div className="g-bar"><div className="g-mid" /><div className="g-fill" style={pct >= 0 ? { left: '50%', width: `${pct * 50}%` } : { right: '50%', width: `${-pct * 50}%` }} /></div>
      <span className="g-val">{value.toFixed(0)}°</span>
    </div>
  )
}

function Slider({ label, v, min, max, set, can, onDone, unit = '°' }: { label: string; v: number; min: number; max: number; set: (v: number) => void; can: boolean; onDone: (v: number) => void; unit?: string }) {
  return (
    <label className="slider">
      <span>{label}</span>
      <input type="range" min={min} max={max} value={v} disabled={!can} onChange={(e) => set(Number(e.target.value))}
        onPointerUp={(e) => onDone(Number((e.target as HTMLInputElement).value))} onKeyUp={(e) => onDone(Number((e.target as HTMLInputElement).value))} />
      <b>{v}{unit}</b>
    </label>
  )
}
