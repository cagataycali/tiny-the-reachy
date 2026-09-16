import { useRef, useState } from 'react'

// Drag pad: x → yaw (±60°), y → pitch (±35°). Fires on release (a goto per gesture, not a stream).
export function HeadPad({ can, onLook, yaw, pitch }: { can: boolean; onLook: (yaw: number, pitch: number) => void; yaw: number; pitch: number }) {
  const ref = useRef<HTMLDivElement>(null)
  const [drag, setDrag] = useState<{ x: number; y: number } | null>(null)
  const toAngles = (e: React.PointerEvent) => {
    const r = ref.current!.getBoundingClientRect()
    const nx = Math.max(-1, Math.min(1, ((e.clientX - r.left) / r.width) * 2 - 1))
    const ny = Math.max(-1, Math.min(1, ((e.clientY - r.top) / r.height) * 2 - 1))
    return { nx, ny }
  }
  const px = drag ? drag.x : -Math.max(-1, Math.min(1, yaw / 60))
  const py = drag ? drag.y : Math.max(-1, Math.min(1, pitch / 35))
  return (
    <div ref={ref} className={`pad ${can ? '' : 'disabled'}`}
      onPointerDown={(e) => { if (!can) return; (e.target as Element).setPointerCapture?.(e.pointerId); const { nx, ny } = toAngles(e); setDrag({ x: nx, y: ny }) }}
      onPointerMove={(e) => { if (!drag) return; const { nx, ny } = toAngles(e); setDrag({ x: nx, y: ny }) }}
      onPointerUp={(e) => { if (!drag) return; const { nx, ny } = toAngles(e); setDrag(null); onLook(-nx * 60, ny * 35) }}
      onPointerCancel={() => setDrag(null)}>
      <div className="pad-grid" />
      <div className="pad-dot" style={{ left: `${(px + 1) * 50}%`, top: `${(py + 1) * 50}%` }} />
      <span className="pad-label">drag · yaw ±60° / pitch ±35°</span>
    </div>
  )
}
