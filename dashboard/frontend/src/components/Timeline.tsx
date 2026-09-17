// ONE timeline for every persona: agent_log rows (voice · telegram · thinker · dashboard) + the live Ask stream.
// Roles: user / assistant / reasoning (collapsed) / tool (receipt: use + result paired by tool_use_id) / system.
import { useEffect, useMemo, useRef, useState } from 'react'
import { LogRow } from '../lib/api'

export const PERSONA: Record<string, { chip: string; color: string; label: string }> = {
  voice: { chip: '🎙', color: '#f472b6', label: 'voice' },
  telegram: { chip: '💬', color: '#60a5fa', label: 'telegram' },
  thinker: { chip: '🧠', color: '#a78bfa', label: 'thinker' },
  dashboard: { chip: '🖥', color: '#5eead4', label: 'dashboard' },
  shell: { chip: '⌨️', color: '#fbbf24', label: 'shell' },
  system: { chip: '⚙️', color: '#9ca3af', label: 'system' },
}
const personaOf = (p: string) => PERSONA[p] ?? { chip: '•', color: '#9ca3af', label: p }

export type Live = { id: number; kind: 'start' | 'text' | 'tool' | 'end' | 'timeout'; text: string; name?: string; input?: string }

type Item =
  | { k: string; ts: string; persona: string; role: 'user' | 'assistant' | 'system' | 'reasoning'; text: string; meta?: any }
  | { k: string; ts: string; persona: string; role: 'tool'; name: string; input: string; result?: string; status?: string; pending?: boolean }

function hhmmss(ts: string): string { return ts.replace('T', ' ').slice(11, 19) }

/** rows → items; tool use + result rows are paired by tool_use_id. Pure. */
export function buildItems(rows: LogRow[]): Item[] {
  const out: Item[] = []
  const open = new Map<string, Extract<Item, { role: 'tool' }>>()
  for (const r of rows) {
    const meta = r.meta || {}
    if (r.role === 'tool') {
      const tid = meta.tool_use_id || `${r.id}`
      if (meta.phase === 'result') {
        const u = open.get(tid)
        if (u) { u.result = r.text; u.status = meta.status; u.pending = false; continue }
        out.push({ k: `r${r.id}`, ts: hhmmss(r.ts), persona: r.persona, role: 'tool', name: meta.tool || 'tool', input: '', result: r.text, status: meta.status })
      } else {
        const name = meta.tool || (r.text.split(' ')[0] ?? 'tool')
        const input = meta.tool ? r.text.slice(name.length).trim() : r.text.slice(name.length).trim()
        const it: Extract<Item, { role: 'tool' }> = { k: `r${r.id}`, ts: hhmmss(r.ts), persona: r.persona, role: 'tool', name, input, pending: true }
        out.push(it); open.set(tid, it)
      }
    } else if (r.role === 'user' || r.role === 'assistant' || r.role === 'reasoning' || r.role === 'system') {
      // dashboard control rows are "[who] look yaw=…" system-ish noise → show as system
      const role = r.persona === 'dashboard' && meta.kind && meta.kind !== 'ask' ? 'system' : r.role
      out.push({ k: `r${r.id}`, ts: hhmmss(r.ts), persona: r.persona, role, text: r.text, meta })
    }
  }
  return out
}

export function Timeline({ rows, live, askBusy, can, onAsk, height = 420 }: {
  rows: LogRow[]; live: Live[]; askBusy: boolean; can: boolean; onAsk: (text: string) => Promise<boolean>; height?: number
}) {
  const ref = useRef<HTMLDivElement>(null)
  const [filter, setFilter] = useState<Set<string>>(new Set())
  const [follow, setFollow] = useState(true)
  const [showSys, setShowSys] = useState(false)
  const [ask, setAsk] = useState('')
  const items = useMemo(() => buildItems(rows), [rows])
  const personas = useMemo(() => Array.from(new Set(rows.map((r) => r.persona))).sort(), [rows])
  const visible = items.filter((it) => (filter.size === 0 || filter.has(it.persona)) && (showSys || it.role !== 'system'))

  useEffect(() => { if (follow) ref.current?.scrollTo({ top: ref.current.scrollHeight }) }, [visible.length, live.length, follow])
  const onScroll = () => { const el = ref.current; if (!el) return; setFollow(el.scrollHeight - el.scrollTop - el.clientHeight < 40) }
  const toggle = (p: string) => setFilter((f) => { const n = new Set(f); n.has(p) ? n.delete(p) : n.add(p); return n })
  const submit = async () => { const t = ask.trim(); if (!t) return; if (await onAsk(t)) setAsk('') }

  return (
    <div className="timeline" data-testid="timeline">
      <div className="tl-filters">
        {personas.map((p) => { const d = personaOf(p); return (
          <button key={p} className={`chip ${filter.size === 0 || filter.has(p) ? 'on' : ''}`} style={{ '--c': d.color } as any} onClick={() => toggle(p)} title={`filter ${p}`}>{d.chip} {d.label}</button>
        ) })}
        <label className="chip sys"><input type="checkbox" checked={showSys} onChange={(e) => setShowSys(e.target.checked)} /> system rows</label>
        {!follow && <button className="chip on" onClick={() => { setFollow(true); ref.current?.scrollTo({ top: ref.current.scrollHeight }) }}>↓ follow</button>}
      </div>
      <div className="tl-scroll" ref={ref} onScroll={onScroll} style={{ maxHeight: height }}>
        {visible.length === 0 && <div className="muted" style={{ padding: 12 }}>no agent activity yet — the personas' reasoning, tool calls and voice transcripts appear here live</div>}
        {visible.map((it) => <Row key={it.k} it={it} />)}
        {live.length > 0 && (
          <div className="tl-live">
            {live.map((l) => (
              l.kind === 'start' ? <div key={l.id} className="tl-row role-user"><Chip p="dashboard" /><div className="tl-body"><span className="tl-who">you</span>{l.text}</div></div>
              : l.kind === 'text' ? <div key={l.id} className="tl-row role-assistant streaming"><Chip p="dashboard" /><div className="tl-body"><span className="tl-who">TINY</span>{l.text}<span className="caret">▍</span></div></div>
              : l.kind === 'tool' ? <div key={l.id} className="tl-row role-tool"><Chip p="dashboard" /><div className="tl-body tool"><span className="tl-tool">🔧 {l.name ?? l.text}</span>{l.input && <code className="tl-in">{l.input}</code>}<span className="tl-pending">running…</span></div></div>
              : <div key={l.id} className={`tl-row role-system ${l.kind}`}><Chip p="dashboard" /><div className="tl-body muted">{l.kind === 'end' ? '✓ ' : '⏱ '}{l.text}</div></div>
            ))}
          </div>
        )}
      </div>
      <div className="tl-ask">
        <input value={ask} onChange={(e) => setAsk(e.target.value)} placeholder={can ? 'Ask TINY… (one Strands turn — watch it think and act)' : 'sign in to ask TINY'} disabled={!can || askBusy}
          onKeyDown={(e) => e.key === 'Enter' && submit()} data-testid="ask-input" />
        <button className="btn primary" disabled={!can || askBusy || !ask.trim()} onClick={submit}>{askBusy ? '…' : 'ask'}</button>
      </div>
    </div>
  )
}

function Chip({ p }: { p: string }) { const d = personaOf(p); return <span className="tl-chip" style={{ color: d.color }} title={d.label}>{d.chip}</span> }

function Row({ it }: { it: Item }) {
  const [open, setOpen] = useState(false)
  if (it.role === 'tool') {
    const ok = it.status ? it.status === 'success' : true
    return (
      <div className={`tl-row role-tool ${it.pending ? 'pending' : ''}`} data-role="tool">
        <span className="tl-ts">{it.ts}</span><Chip p={it.persona} />
        <div className="tl-body tool" onClick={() => setOpen(!open)}>
          <span className="tl-tool">🔧 {it.name}</span>
          {it.input && <code className="tl-in">{open || it.input.length < 140 ? it.input : it.input.slice(0, 140) + '…'}</code>}
          {it.pending ? <span className="tl-pending">running…</span>
            : it.result != null && <span className={`tl-res ${ok ? 'ok' : 'bad'}`}>{ok ? '→' : '✗'} {open || it.result.length < 160 ? it.result : it.result.slice(0, 160) + '…'}</span>}
        </div>
      </div>
    )
  }
  if (it.role === 'reasoning') {
    return (
      <div className="tl-row role-reasoning" data-role="reasoning">
        <span className="tl-ts">{it.ts}</span><Chip p={it.persona} />
        <div className="tl-body" onClick={() => setOpen(!open)}>
          <span className="tl-who">💭 reasoning</span>{open ? it.text : (it.text.length > 90 ? it.text.slice(0, 90) + '… (tap)' : it.text)}
        </div>
      </div>
    )
  }
  const who = it.role === 'user' ? (it.persona === 'voice' ? 'heard' : 'user') : it.role === 'assistant' ? (it.persona === 'voice' ? 'TINY said' : 'TINY') : ''
  return (
    <div className={`tl-row role-${it.role}`} data-role={it.role}>
      <span className="tl-ts">{it.ts}</span><Chip p={it.persona} />
      <div className="tl-body">{who && <span className="tl-who">{who}</span>}{it.text}</div>
    </div>
  )
}
