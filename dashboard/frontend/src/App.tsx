// v3 shell — mobile-first, camera-first, agent-as-overlay (scout.cagatay.my pattern, ported to React).
// Gate → Cockpit. Cockpit = topbar · full-bleed viewport (camera + twin PiP, swappable) with the mind overlay · cmdbar · slide-up docks.
// Desktop (≥ 960 px) shows the same components in two columns: viewport left, mind timeline + open dock right.
import { useCallback, useEffect, useRef, useState } from 'react'
import { AgentEvent, ApiError, AuthStatus, Emotions, LogRow, api, setToken } from './lib/api'
import { useSocket } from './lib/socket'
import { PiPViewport, usePiPPrefs } from './components/PiP'
import { EmotionGrid } from './components/Emotions'
import { HeadPad } from './components/Joystick'
import { Live, PERSONA, Timeline } from './components/Timeline'
import { LockCard, Telemetry } from './components/System'
import { Gate } from './components/Gate'

type Thought = Live
type Dock = null | 'look' | 'emotions' | 'say' | 'settings' | 'mind'

// Nothing renders until the gate lets us through; the cockpit unmounts again on lock / 401 / expired session.
export default function App() {
  const [auth, setAuth] = useState<AuthStatus | null>(null)
  const lock = useCallback(async () => { setToken(''); try { await api.logout() } catch {} setAuth(null) }, [])
  if (!auth?.authenticated) return <Gate onAuth={setAuth} />
  return <Cockpit auth={auth} onLock={lock} />
}

function useMedia(q: string) {
  const [m, setM] = useState(() => matchMedia(q).matches)
  useEffect(() => { const mq = matchMedia(q); const h = () => setM(mq.matches); mq.addEventListener('change', h); return () => mq.removeEventListener('change', h) }, [q])
  return m
}

function Cockpit({ auth, onLock }: { auth: AuthStatus; onLock: () => void }) {
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
  const [dock, setDock] = useState<Dock>(null)
  const [pip, setPip] = usePiPPrefs()                                  // twin ⇄ camera PiP (components/PiP.tsx)
  const [overlayOn, setOverlayOn] = useState(true)
  const [lift, setLift] = useState(0)                                 // mind bubbles lift above a bottom-corner PiP
  const seq = useRef(0)
  const wide = useMedia('(min-width: 960px)')

  const onAgent = useCallback((e: AgentEvent) => {
    setThoughts((t) => {
      const id = ++seq.current
      if (e.event === 'start') { setAskBusy(true); return [{ id, kind: 'start', text: e.text || '' }] }
      if (e.event === 'text') {
        const last = t[t.length - 1]
        if (last && last.kind === 'text') return [...t.slice(0, -1), { ...last, text: last.text + (e.text || '') }]
        return [...t, { id, kind: 'text', text: e.text || '' }]
      }
      if (e.event === 'tool') return [...t, { id, kind: 'tool', text: `${e.name} ${e.input || ''}`.trim(), name: e.name, input: e.input }]
      if (e.event === 'end' || e.event === 'timeout') setTimeout(() => setThoughts([]), 2500)
      if (e.event === 'end') { setAskBusy(false); return [...t, { id, kind: 'end', text: e.ok ? `done in ${e.seconds}s` : `failed: ${e.error}` }] }
      if (e.event === 'timeout') { setAskBusy(false); return [...t, { id, kind: 'timeout', text: `timed out after ${e.seconds}s` }] }
      return t
    })
  }, [])

  const { state, hello, rows, connected } = useSocket(onAgent)
  const can = !!(hello?.can_control)
  useEffect(() => { api.emotions().then(setEmotions).catch(() => {}) }, [])
  useEffect(() => { if (hello?.error) onLock() }, [hello, onLock])            // gated hello (4401) = session gone
  useEffect(() => { if (!toast) return; const t = setTimeout(() => setToast(''), 3500); return () => clearTimeout(t) }, [toast])
  // PWA shortcuts (?action=ask|reel)
  useEffect(() => {
    const a = new URLSearchParams(location.search).get('action'); if (!a) return
    history.replaceState(null, '', '/')
    if (a === 'ask') setTimeout(() => (document.querySelector('[data-testid=ask-input]') as HTMLInputElement | null)?.focus(), 800)
    if (a === 'reel') setTimeout(() => { if (can && confirm('Play the demo reel now?')) ctl('reel', { action: 'start' }) }, 1200)
  }, [can])
  // keyboard shortcuts (ignored while typing): ← → ↑ ↓ look · Space STOP · H home · D demo · / ask · T twin PiP · X swap · L look dock · E emotions · Esc close
  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName
      if (e.key === 'Escape') { setDock(null); (document.activeElement as HTMLElement | null)?.blur(); return }
      if (tag === 'INPUT' || tag === 'TEXTAREA' || e.metaKey || e.ctrlKey) return
      if (e.key === '/') { e.preventDefault(); (document.querySelector('[data-testid=ask-input]') as HTMLInputElement | null)?.focus(); return }
      if (e.key === 't' || e.key === 'T') { setPip((p) => (p.open ? { ...p, open: false, swapped: false } : { ...p, open: true })); return }
      if (e.key === 'x' || e.key === 'X') { setPip((p) => ({ ...p, swapped: !p.swapped, open: true })); return }
      if (e.key === 'l' || e.key === 'L') { setDock((d) => (d === 'look' ? null : 'look')); return }
      if (e.key === 'e' || e.key === 'E') { setDock((d) => (d === 'emotions' ? null : 'emotions')); return }
      if (!can) return
      const step = e.shiftKey ? 40 : 20
      const map: Record<string, () => unknown> = {
        ArrowLeft: () => look(step, 0), ArrowRight: () => look(-step, 0), ArrowUp: () => look(0, -step / 2), ArrowDown: () => look(0, step / 2),
        ' ': () => ctl('stop'), h: () => home(), H: () => home(), d: () => ctl('demo', { on: !state?.demo }), D: () => ctl('demo', { on: !state?.demo }),
        f: () => track(!state?.tracking?.enabled), F: () => track(!state?.tracking?.enabled),
      }
      const fn = map[e.key]; if (fn) { e.preventDefault(); fn() }
    }
    window.addEventListener('keydown', h); return () => window.removeEventListener('keydown', h)
  })

  const ctl = async (what: string, body: unknown = {}) => {
    try { const r = await api.control(what, body); return r } catch (e: any) {
      if (e instanceof ApiError && e.status === 401) { onLock(); return null }
      setToast(e instanceof ApiError ? (e.status === 429 ? 'slow down (or an ask is running)' : e.message) : String(e))
      return null
    }
  }
  const look = (yaw: number, pitch: number) => ctl('look', { yaw, pitch, roll, body_yaw: body, duration: 0.8 })
  const track = async (on: boolean) => {
    try { const r = await api.tracking(on); setToast(on ? (r.tracking?.detected ? 'following your face' : 'tracking ON — looking for a face') : 'tracking OFF'); return r } catch (e: any) {
      if (e instanceof ApiError && e.status === 401) { onLock(); return null }
      setToast(e instanceof ApiError ? e.message : String(e)); return null
    }
  }
  const home = () => { setRoll(0); setBody(0); setAntR(0); setAntL(0); return ctl('home') }
  const doSay = async () => { const t = say.trim(); if (!t) return; const r = await ctl('say', { text: t }); if (r) { setSay(''); setToast(r.engine === 'piper-local' ? `speaking (${r.seconds}s)` : (r.warning || 'queued — no voice backend')) } }
  const doAsk = async (text: string) => { setThoughts([]); const r = await ctl('ask', { text }); return !!r }
  const submitAsk = async () => { const t = ask.trim(); if (!t || askBusy) return; if (await doAsk(t)) setAsk('') }
  const toggleDock = (d: Dock) => setDock((cur) => (cur === d ? null : d))

  const s = state
  const playing = s?.now_playing ?? null
  const reel = s?.reel
  const online = !!s?.ok
  const sys = s?.system

  const dockBody = dock && dock !== 'mind' && (
    <>
      {dock === 'look' && (
        <div className="dock-look">
          <HeadPad can={can} onLook={look} yaw={s?.head?.yaw ?? 0} pitch={s?.head?.pitch ?? 0} />
          <Slider label="roll" v={roll} min={-40} max={40} set={setRoll} can={can} onDone={(v) => ctl('look', { roll: v, yaw: s?.head?.yaw ?? 0, pitch: s?.head?.pitch ?? 0, body_yaw: body })} />
          <Slider label="body" v={body} min={-160} max={160} set={setBody} can={can} onDone={(v) => ctl('look', { roll, yaw: s?.head?.yaw ?? 0, pitch: s?.head?.pitch ?? 0, body_yaw: v, duration: 1.2 })} />
          <div className="btnrow">
            <button className="btn" disabled={!can} onClick={home}>⌂ home</button>
            <button className="btn" disabled={!can} onClick={() => ctl('look', { yaw: 40, duration: 1 })}>◄</button>
            <button className="btn" disabled={!can} onClick={() => ctl('look', { yaw: -40, duration: 1 })}>►</button>
            <button className="btn" disabled={!can} onClick={() => ctl('look', { pitch: -25, duration: 1 })}>▲</button>
            <button className="btn" disabled={!can} onClick={() => ctl('look', { pitch: 25, duration: 1 })}>▼</button>
          </div>
          <div className="dock-sub">📡 antennas</div>
          <Slider label="right" v={antR} min={-150} max={150} set={setAntR} can={can} onDone={(v) => ctl('antennas', { right: v, left: antL })} />
          <Slider label="left" v={antL} min={-150} max={150} set={setAntL} can={can} onDone={(v) => ctl('antennas', { right: antR, left: v })} />
          <div className="btnrow">
            <button className="btn" disabled={!can} onClick={() => { setAntR(0); setAntL(0); ctl('antennas', { right: 0, left: 0 }) }}>neutral</button>
            <button className="btn" disabled={!can} onClick={() => { setAntR(45); setAntL(-45); ctl('antennas', { right: 45, left: -45 }) }}>perk</button>
            <button className="btn" disabled={!can} onClick={() => { setAntR(-60); setAntL(60); ctl('antennas', { right: -60, left: 60 }) }}>droop</button>
            <button className="btn" disabled={!can} onClick={async () => { for (const [r, l] of [[40, -40], [-40, 40], [40, -40], [0, 0]]) { await ctl('antennas', { right: r, left: l, duration: 0.3 }); await new Promise((z) => setTimeout(z, 350)) } }}>wiggle</button>
          </div>
        </div>
      )}
      {dock === 'emotions' && (
        <>
          <div className="reel">
            {reel?.running
              ? <button className="btn stop wide" disabled={!can} onClick={() => ctl('reel', { action: 'abort' })}>■ abort reel · {reel.elapsed}s</button>
              : <button className="btn primary wide" disabled={!can} onClick={() => ctl('reel', { action: 'start' })}>▶ play the {reel?.total_s ?? 0}s show</button>}
            {reel?.running && <ol className="timeline-steps">{(reel.steps ?? []).map((st, i) => <li key={i} className={i < reel.step ? 'done' : i === reel.step ? 'now' : ''}>{st}</li>)}</ol>}
          </div>
          <EmotionGrid emotions={emotions} playing={playing} can={can} onPlay={(n) => ctl('express', { name: n })} />
        </>
      )}
      {dock === 'say' && (
        <div className="dock-say">
          <div className="inline">
            <input value={say} onChange={(e) => setSay(e.target.value)} placeholder="Hello, I'm TINY…" disabled={!can} onKeyDown={(e) => e.key === 'Enter' && doSay()} autoFocus data-testid="say-input" />
            <button className="btn primary" disabled={!can || !say.trim()} onClick={doSay}>say</button>
          </div>
          <div className="chips" style={{ marginTop: 10 }}>
            {['Hello! I am TINY, a Reachy Mini.', 'Nice to meet you.', 'Watch this.', 'Thank you for coming.'].map((p) => <button key={p} className="chip" disabled={!can} onClick={() => setSay(p)}>{p}</button>)}
          </div>
          <Slider label="volume" v={vol ?? 70} min={0} max={100} set={(v) => setVol(v)} can={can} onDone={(v) => ctl('volume', { level: v })} unit="%" />
        </div>
      )}
      {dock === 'settings' && (
        <div className="dock-settings">
          <div className="dock-sub">⚡ robot</div>
          <div className="btnrow">
            <button className="btn" disabled={!can} onClick={() => ctl('wake')}>☀ wake</button>
            <button className="btn" disabled={!can} onClick={() => confirm('Sleep the robot? The thinker persona depends on it being awake.') && ctl('sleep')}>🌙 sleep</button>
            <button className="btn" disabled={!can} onClick={() => ctl('motors', { mode: 'enabled' })}>motors on</button>
            <button className="btn" disabled={!can} onClick={() => confirm('Disable motors? The head will go limp.') && ctl('motors', { mode: 'disabled' })}>motors off</button>
            <button className="btn" disabled={!can} onClick={() => ctl('motors', { mode: 'gravity_compensation' })}>gravity comp</button>
          </div>
          <div className="dock-sub">📈 telemetry</div>
          <Telemetry s={s} />
          <div className="dock-sub">🔐 lock &amp; demo</div>
          <LockCard auth={auth} can={can} demo={!!s?.demo} onDemo={(on) => ctl('demo', { on }).then((r) => { if (r) setToast(on ? 'demo mode ON — thinker paused' : 'thinker resumed') })} onToast={setToast} />
          <div className="dock-sub">🖥 display</div>
          <label className="switch"><input type="checkbox" checked={overlayOn} onChange={(e) => setOverlayOn(e.target.checked)} /><span className="track" /> agent overlay on the camera</label>
          <label className="switch"><input type="checkbox" checked={pip.open} onChange={(e) => setPip((p) => (e.target.checked ? { ...p, open: true } : { ...p, open: false, swapped: false }))} data-testid="set-pip-open" /><span className="track" /> digital twin PiP</label>
          <div className="btnrow" data-testid="set-pip-size">
            <span className="muted small" style={{ alignSelf: 'center' }}>twin size</span>
            {(wide ? ['S', 'M', 'L'] as const : ['S', 'M'] as const).map((z) => <button key={z} className={`btn small ${(pip.size ?? (wide ? 'M' : 'S')) === z ? 'primary' : ''}`} onClick={() => setPip((p) => ({ ...p, size: z, open: true }))}>{z === 'L' ? 'L · large' : z}</button>)}
            <button className="btn small" onClick={() => setPip((p) => ({ ...p, corner: 'tr', size: null }))}>reset</button>
          </div>
          <div className="muted small keys">shortcuts: <kbd>←</kbd><kbd>→</kbd><kbd>↑</kbd><kbd>↓</kbd> look · <kbd>space</kbd> STOP · <kbd>H</kbd> home · <kbd>D</kbd> demo · <kbd>F</kbd> face-track · <kbd>T</kbd> twin PiP · <kbd>X</kbd> swap · <kbd>L</kbd> look · <kbd>E</kbd> emotions · <kbd>/</kbd> ask · <kbd>esc</kbd> close</div>
          <button className="btn ghost wide" onClick={onLock}>🔒 lock · sign out ({auth.who})</button>
          <div className="muted small">reachy.cagatay.my · dashboard {hello?.version ?? ''} · uptime {Math.round((s?.uptime_s ?? 0) / 60)} min · {s?.camera?.clients ?? 0} viewer{(s?.camera?.clients ?? 0) === 1 ? '' : 's'}</div>
        </div>
      )}
    </>
  )
  const mindPanel = <Timeline rows={rows} live={thoughts} askBusy={askBusy} can={can} onAsk={doAsk} height={wide ? 10000 : 420} />

  return (
    <div className={`shell ${wide ? 'wide' : ''}`} data-testid="cockpit">
      <header className="topbar glass">
        <div className="brand"><span className="logo">🤖</span><div className="brand-txt"><strong>tiny</strong><small>{online ? 'live' : 'daemon offline'} · {connected ? 'ws' : 'reconnecting'}</small></div></div>
        <div className="stat-pills" data-testid="pills">
          <span className={`pill ${s?.control_mode === 'enabled' ? '' : 'warn'}`} title="motors">⚙ {s?.control_mode ?? '…'}</span>
          <span className={`pill ${(sys?.wifi_signal_dbm ?? 0) < -75 ? 'warn' : ''}`} title={`Wi-Fi ${s?.wifi?.ssid ?? ''}`}>📶 {sys?.wifi_signal_dbm ?? '—'}</span>
          <span className={`pill ${(sys?.cpu_c ?? 0) >= 70 ? 'crit' : ''}`} title="CM4 CPU temperature">🌡 {sys?.cpu_c != null ? `${Math.round(sys.cpu_c)}°` : '—'}</span>
          <button className={`pill ${s?.demo ? 'on' : ''}`} disabled={!can} onClick={() => ctl('demo', { on: !s?.demo }).then((r) => { if (r) setToast(!s?.demo ? 'demo mode ON — thinker paused' : 'thinker resumed') })} title="demo mode = pause the thinker persona">{s?.demo ? '🎬 demo' : '🧠 thinker'}</button>
          <button className={`pill ${s?.tracking?.enabled ? (s?.tracking?.detected ? 'on' : 'warn') : ''}`} disabled={!can || s?.tracking?.available === false} data-testid="track-pill" onClick={() => track(!s?.tracking?.enabled)}
            title={s?.tracking?.available === false ? `face tracking unavailable: ${s?.tracking?.error ?? 'daemon has no camera'}` : 'follow the closest face (daemon face tracking, F)'}>
            👁 {s?.tracking?.enabled ? (s?.tracking?.paused ? 'paused' : (s?.tracking?.detected ? 'face' : 'track')) : 'track'}</button>
        </div>
        <button className="icon-btn" onClick={onLock} title="lock — sign out" data-testid="lock-btn">🔒</button>
      </header>

      <main className="stage">
        <section className="viewport" data-testid="viewport">
          <PiPViewport s={s} pip={pip} setPip={setPip} onToast={setToast} onLift={setLift} />
          <div className="cam-overlay">
            <div className="overlay-top">
              <span className="chip on">{!pip.swapped ? `● LIVE ${s?.camera?.fps?.toFixed(0) ?? 0} fps` : '🧊 twin · mirrors the real motors'}</span>
              {playing && <span className="chip playing">▶ {playing.name}</span>}
              {reel?.running && <span className="chip">🎬 reel {reel.step + 1}/{reel.steps.length} · {reel.elapsed}s</span>}
              {s?.moves_running ? <span className="chip">{s.moves_running} move{s.moves_running > 1 ? 's' : ''}</span> : null}
              <button className="chip" onClick={() => setPip((p) => ({ ...p, swapped: !p.swapped, open: true }))} data-testid="view-toggle" title="swap camera ⇄ twin (X, or double-tap the PiP)">{!pip.swapped ? '⇄ 🧊 twin' : '⇄ 📷 camera'}</button>
            </div>
            {overlayOn && !wide && <MindOverlay rows={rows} live={thoughts} onOpen={() => setDock('mind')} lift={lift} />}
          </div>
          <button className="estop" disabled={!can} onClick={() => ctl('stop')} title="STOP every move (space)" data-testid="stop">■</button>
        </section>

        {wide && (
          <aside className="side glass">
            {dock && dock !== 'mind' ? <div className="side-dock"><div className="dock-head"><h2>{DOCK_TITLE[dock]}</h2><button className="icon-btn sm" onClick={() => setDock(null)}>✕</button></div><div className="dock-body">{dockBody}</div></div>
              : <div className="side-mind"><h2>🧠 TINY's mind <small className="muted">voice · telegram · thinker · dashboard</small></h2>{mindPanel}</div>}
          </aside>
        )}
      </main>

      <footer className="cmdbar glass">
        <div className="askbar">
          <input value={ask} onChange={(e) => setAsk(e.target.value)} placeholder={askBusy ? 'TINY is thinking…' : 'Ask TINY…'} disabled={!can || askBusy}
            onKeyDown={(e) => e.key === 'Enter' && submitAsk()} data-testid="ask-input" enterKeyHint="send" />
          <button className="send-btn" disabled={!can || askBusy || !ask.trim()} onClick={submitAsk} title="ask (one Strands turn, streamed)">{askBusy ? '…' : '↑'}</button>
        </div>
        <div className="cmd-icons">
          <button className={`icon-btn ${dock === 'look' ? 'on' : ''}`} onClick={() => toggleDock('look')} title="head & antennas (L)" data-testid="dock-look">🕹</button>
          <button className={`icon-btn ${dock === 'emotions' ? 'on' : ''}`} onClick={() => toggleDock('emotions')} title="emotions & reel (E)" data-testid="dock-emotions">🎭</button>
          <button className={`icon-btn ${dock === 'say' ? 'on' : ''}`} onClick={() => toggleDock('say')} title="say" data-testid="dock-say">🗣</button>
          {!wide && <button className={`icon-btn ${dock === 'mind' ? 'on' : ''}`} onClick={() => toggleDock('mind')} title="TINY's mind" data-testid="dock-mind">🧠</button>}
          <button className={`icon-btn ${dock === 'settings' ? 'on' : ''}`} onClick={() => toggleDock('settings')} title="settings" data-testid="dock-settings">⚙</button>
        </div>
      </footer>

      {dock && (!wide || dock === 'mind') && (
        <div className="sheet-wrap" onClick={() => setDock(null)}>
          <div className={`sheet glass ${dock === 'mind' || dock === 'emotions' ? 'tall' : ''}`} onClick={(e) => e.stopPropagation()} data-testid={`sheet-${dock}`}>
            <div className="dock-head"><span className="grab" /><h2>{DOCK_TITLE[dock]}</h2><button className="icon-btn sm" onClick={() => setDock(null)}>✕</button></div>
            <div className="dock-body">{dock === 'mind' ? mindPanel : dockBody}</div>
          </div>
        </div>
      )}
      {toast && <div className="toast">{toast}</div>}
    </div>
  )
}

const DOCK_TITLE: Record<Exclude<Dock, null>, string> = { look: '🕹 head & antennas', emotions: '🎭 emotions & reel', say: '🗣 say', settings: '⚙ settings', mind: "🧠 TINY's mind" }

/** The agent as an overlay: the last few mind rows as glass bubbles over the camera, auto-fading; tap → full timeline. */
function MindOverlay({ rows, live, onOpen, lift = 0 }: { rows: LogRow[]; live: Live[]; onOpen: () => void; lift?: number }) {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => { const t = setInterval(() => setNow(Date.now()), 2000); return () => clearInterval(t) }, [])
  const recent = rows.filter((r) => r.role !== 'system' && r.role !== 'reasoning' && r.text).slice(-3)
  const age = (ts: string) => (now - Date.parse(ts.endsWith('Z') ? ts : ts + 'Z')) / 1000
  const liveText = live.filter((l) => l.kind === 'text').map((l) => l.text).join('')
  const liveTool = [...live].reverse().find((l) => l.kind === 'tool')
  const asking = live.length > 0
  return (
    <div className="mind-overlay" onClick={onOpen} data-testid="mind-overlay" style={lift ? { marginBottom: lift, transition: 'margin-bottom .28s' } : undefined}>
      {!asking && recent.map((r) => {
        const a = age(r.ts), p = PERSONA[r.persona] ?? { chip: '•', color: '#9ca3af', label: r.persona }
        const faded = a > 90 ? 'faded' : a > 30 ? 'dim' : ''
        const role = r.role === 'tool' ? 'tool' : r.role === 'user' ? 'user' : 'bot'
        return <div key={r.id} className={`bubble ${role} ${faded}`} style={{ '--c': p.color } as any}><span className="b-who">{p.chip} {r.role === 'user' ? (r.persona === 'voice' ? 'heard' : 'user') : r.role === 'tool' ? '🔧' : 'TINY'}</span>{r.text.length > 220 ? r.text.slice(0, 220) + '…' : r.text}</div>
      })}
      {asking && (
        <>
          {live[0]?.kind === 'start' && <div className="bubble user" style={{ '--c': '#5eead4' } as any}><span className="b-who">you</span>{live[0].text}</div>}
          {liveTool && <div className="bubble tool"><span className="b-who">🔧 {liveTool.name}</span>{liveTool.input}</div>}
          <div className="bubble bot live" style={{ '--c': '#5eead4' } as any}><span className="b-who">TINY</span>{liveText || 'thinking'}<span className="caret">▍</span></div>
        </>
      )}
      {!asking && recent.length === 0 && <div className="bubble sys">🧠 TINY's mind is quiet — ask something below</div>}
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
