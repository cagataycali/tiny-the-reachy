import { useEffect, useRef, useState } from 'react'
import { AgentEvent, Event, LogRow, State, wsUrl } from './api'

export type Hello = { who: string | null; can_control: boolean; version: string }

export function useSocket(onAgent: (e: AgentEvent) => void) {
  const [state, setState] = useState<State | null>(null)
  const [hello, setHello] = useState<Hello | null>(null)
  const [rows, setRows] = useState<LogRow[]>([])
  const [events, setEvents] = useState<Event[]>([])
  const [connected, setConnected] = useState(false)
  const onAgentRef = useRef(onAgent); onAgentRef.current = onAgent

  useEffect(() => {
    let sock: WebSocket | null = null; let closed = false; let timer: any
    const open = () => {
      sock = new WebSocket(wsUrl())
      sock.onopen = () => setConnected(true)
      sock.onclose = () => { setConnected(false); if (!closed) timer = setTimeout(open, 1500) }
      sock.onmessage = (m) => {
        let d: any; try { d = JSON.parse(m.data) } catch { return }
        switch (d.type) {
          case 'hello': setHello(d); break
          case 'state': setState(d); break
          case 'log': setRows((r) => [...r, ...d.rows].slice(-200)); break
          case 'event': setEvents((e) => [...e, d].slice(-100)); break
          case 'agent': onAgentRef.current(d); break
        }
      }
    }
    open()
    const ping = setInterval(() => { if (sock?.readyState === 1) sock.send('{"ping":1}') }, 15000)
    return () => { closed = true; clearTimeout(timer); clearInterval(ping); sock?.close() }
  }, [])
  return { state, hello, rows, events, connected }
}
