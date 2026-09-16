import { useEffect, useRef } from 'react'
import { Event, LogRow } from '../lib/api'

const COLOR: Record<string, string> = { thinker: '#a78bfa', telegram: '#60a5fa', voice: '#f472b6', dashboard: '#5eead4', shell: '#fbbf24' }

export function AgentLog({ rows, events }: { rows: LogRow[]; events: Event[] }) {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => { ref.current?.scrollTo({ top: ref.current.scrollHeight }) }, [rows.length, events.length])
  const merged = [
    ...rows.map((r) => ({ k: `r${r.id}`, ts: r.ts.replace('T', ' ').slice(11, 19), who: r.persona, role: r.role, text: r.text })),
    ...events.filter((e) => e.kind === 'error').map((e) => ({ k: `e${e.seq}`, ts: new Date(e.t * 1000).toISOString().slice(11, 19), who: e.who, role: 'error', text: e.text })),
  ].sort((a, b) => a.ts.localeCompare(b.ts)).slice(-120)
  return (
    <div className="log" ref={ref}>
      {merged.length === 0 && <div className="muted">no agent activity yet</div>}
      {merged.map((r) => (
        <div key={r.k} className={`row role-${r.role}`}>
          <span className="ts">{r.ts}</span>
          <span className="who" style={{ color: COLOR[r.who] ?? '#9ca3af' }}>{r.who}</span>
          <span className="txt">{r.text}</span>
        </div>
      ))}
    </div>
  )
}
