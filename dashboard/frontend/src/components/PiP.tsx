// Twin ⇄ camera picture-in-picture over the viewport.
// Two persistent LAYERS (camera, twin) share the viewport; one fills it ("main"), the other is a floating,
// draggable, corner-snapping card ("pip"). Swap = re-assign boxes (animated), so neither the MJPEG stream nor the
// MuJoCo sim ever restarts and the CM4 sees exactly one camera client. Prefs (corner, size, swapped, open) persist
// in localStorage (lib/pip.ts). Landscape phones get a side-by-side split instead of a floating card.
import { useCallback, useEffect, useLayoutEffect, useRef, useState, type CSSProperties, type Dispatch, type SetStateAction } from 'react'
import type { State } from '../lib/api'
import { Camera } from './Camera'
import Twin from './Twin'
import { Box, PAD, PiPPrefs, PiPSize, TOP_OFF, autoSize, bubbleLift, cornerBox, deg, isSplit, loadPrefs, nextSize, rad2deg, readoutH, savePrefs, snapCorner, splitBoxes } from '../lib/pip'

export function usePiPPrefs(): [PiPPrefs, Dispatch<SetStateAction<PiPPrefs>>] {
  const [p, setP] = useState<PiPPrefs>(loadPrefs)
  useEffect(() => savePrefs(p), [p])
  return [p, setP]
}

const SHORT_MODE: Record<string, string> = { enabled: 'on', disabled: 'off', gravity_compensation: 'g-comp' }

export function PiPViewport({ s, pip, setPip, onToast, onLift, stale = false }: { s: State | null; pip: PiPPrefs; setPip: Dispatch<SetStateAction<PiPPrefs>>; onToast?: (t: string) => void
  /** px the mind bubbles must lift so a bottom-corner card never covers them */
  onLift?: (px: number) => void
  /** true when the WS state is > 2.5 s old — the readout dims so frozen numbers are not mistaken for live ones */
  stale?: boolean }) {
  const host = useRef<HTMLDivElement>(null)
  const [dim, setDim] = useState({ w: 0, h: 0 })
  const [drag, setDrag] = useState<{ dx: number; dy: number } | null>(null)
  useLayoutEffect(() => {
    const el = host.current!; const m = () => setDim({ w: el.clientWidth, h: el.clientHeight })
    m(); const ro = new ResizeObserver(m); ro.observe(el); return () => ro.disconnect()
  }, [])
  const W = dim.w, H = dim.h, ready = W > 0 && H > 0
  const size: PiPSize = pip.size ?? autoSize(W)
  const split = pip.open && isSplit(W, H)
  const main: Box = split ? splitBoxes(W, H).main : { x: 0, y: 0, w: W, h: H }
  let card: Box = split ? splitBoxes(W, H).pip : cornerBox(pip.corner, size, W, H)
  if (drag && !split) card = { ...card, x: card.x + drag.dx, y: card.y + drag.dy }
  const camBox = pip.swapped ? card : main, twinBox = pip.swapped ? main : card
  const twinRole = pip.swapped ? 'main' : 'pip', camRole = pip.swapped ? 'pip' : 'main'
  const twinVisible = pip.open || pip.swapped
  const lift = ready ? bubbleLift(pip, size, split, cornerBox(pip.corner, size, W, H)) : 0
  useEffect(() => { onLift?.(lift) }, [lift, onLift])

  // first visit: a 3-second hint on how to use the card
  useEffect(() => {
    if (pip.hinted || !ready || !pip.open) return
    const t = setTimeout(() => { onToast?.('🧊 twin PiP — drag to a corner · double-tap to swap · T hides it'); setPip((p) => ({ ...p, hinted: true })) }, 1200)
    return () => clearTimeout(t)
  }, [pip.hinted, pip.open, ready, setPip, onToast])

  const swap = useCallback(() => setPip((p) => ({ ...p, swapped: !p.swapped, open: true })), [setPip])
  const close = useCallback(() => setPip((p) => ({ ...p, open: false, swapped: false })), [setPip])
  const cycle = useCallback(() => setPip((p) => ({ ...p, size: nextSize(p.size ?? autoSize(W), W, H) })), [setPip, W, H])
  const dbl = useDoubleTap(swap)

  // drag from the handle → snap to the nearest corner on release
  const dragStart = useRef<{ px: number; py: number } | null>(null)
  const onHandleDown = (e: React.PointerEvent) => { if (split) return; (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId); dragStart.current = { px: e.clientX, py: e.clientY }; setDrag({ dx: 0, dy: 0 }) }
  const onHandleMove = (e: React.PointerEvent) => { const st = dragStart.current; if (!st) return; setDrag({ dx: e.clientX - st.px, dy: e.clientY - st.py }) }
  const onHandleUp = (e: React.PointerEvent) => {
    const st = dragStart.current; if (!st) return; dragStart.current = null
    const moved = Math.hypot(e.clientX - st.px, e.clientY - st.py)
    if (moved > 6) { const cx = card.x + card.w / 2, cy = card.y + card.h / 2; setPip((p) => ({ ...p, corner: snapCorner(cx, cy, W, H) })) }
    setDrag(null); dbl(e)
  }

  const style = (b: Box, role: 'main' | 'pip'): CSSProperties => ({ left: b.x, top: b.y, width: b.w, height: b.h, borderRadius: role === 'pip' && !split ? 14 : 0 })
  const cls = (role: string, on = true) => `layer ${role} ${drag ? 'dragging' : ''} ${on ? '' : 'hidden'}`

  return (
    <div className={`pip-host ${split ? 'split' : ''}`} ref={host} data-testid="pip-host" data-open={pip.open} data-swapped={pip.swapped} data-corner={pip.corner} data-size={size} data-split={split}>
      {ready && (
        <>
          <div className={cls(camRole)} style={style(camBox, camRole)} data-testid="layer-cam" onPointerDownCapture={dbl.down} onPointerUpCapture={camRole === 'pip' ? dbl : undefined}>
            <Camera ok={!!s?.camera?.ok} fps={s?.camera?.fps ?? 0} error={s?.camera?.error ?? null} tracking={s?.tracking} />
          </div>
          <div className={cls(twinRole, twinVisible)} style={style(twinBox, twinRole)} data-testid="layer-twin" onPointerDownCapture={dbl.down} onPointerUpCapture={twinRole === 'pip' ? dbl : undefined}>
            <div className="twin-fill">
              <Twin joints={s?.joints} height={twinBox.h} paused={!twinVisible} maxFps={twinRole === 'pip' ? 30 : 0} autoOrbit={twinRole === 'main'} />
            </div>
            <TwinDetail s={s} />
          </div>
          {pip.open && (
            <>
              <div className={`pip-chrome ${drag ? 'dragging' : ''} ${split ? 'split' : ''}`} style={style(card, 'pip')} data-testid="pip-card">
                <div className="pip-handle" onPointerDown={onHandleDown} onPointerMove={onHandleMove} onPointerUp={onHandleUp} onPointerCancel={() => { dragStart.current = null; setDrag(null) }} data-testid="pip-handle">
                  <span className="pip-title">{pip.swapped ? '📷 camera' : '🧊 twin'}</span>
                  <span className="pip-grip" />
                  <button className="pip-btn" onPointerDown={(e) => e.stopPropagation()} onClick={swap} title="swap camera ⇄ twin (double-tap)" data-testid="pip-swap">⇄</button>
                  {!split && <button className="pip-btn" onPointerDown={(e) => e.stopPropagation()} onClick={cycle} title={`size ${size} → ${nextSize(size, W, H)}`} data-testid="pip-size">{size}</button>}
                  <button className="pip-btn" onPointerDown={(e) => e.stopPropagation()} onClick={close} title="close (T)" data-testid="pip-close">✕</button>
                </div>
              </div>
              <Readout s={s} box={card} split={split} dragging={!!drag} size={size} stale={stale} />
            </>
          )}
          {!pip.open && (
            <button className="chip pip-chip" style={{ top: TOP_OFF - 40, right: PAD }} onClick={() => setPip((p) => ({ ...p, open: true }))} title="show the digital twin (T)" data-testid="pip-chip">🧊 twin</button>
          )}
        </>
      )}
    </div>
  )
}

/** Detail strip under the card: head roll/pitch/yaw, body yaw, antennas, control-loop Hz, motor mode — straight from /api/state. */
function Readout({ s, box, split, dragging, size, stale }: { s: State | null; box: Box; split: boolean; dragging: boolean; size: PiPSize; stale: boolean }) {
  const h = s?.head, a = s?.antennas, hz = s?.daemon?.loop_hz, rh = readoutH(size)
  const st: CSSProperties = split ? { left: box.x + 8, top: box.y + box.h - rh - 8, width: box.w - 16 } : { left: box.x, top: box.y + box.h, width: box.w, height: rh }
  const mode = SHORT_MODE[s?.control_mode ?? ''] ?? (s?.control_mode ?? '—')
  return (
    <div className={`pip-readout ${size === 'S' ? 'two-rows' : ''} ${dragging ? 'dragging' : ''} ${split ? 'split' : ''} ${stale ? 'stale' : ''}`} style={st} data-testid="pip-readout" data-stale={stale}
      data-roll={h?.roll?.toFixed(1)} data-pitch={h?.pitch?.toFixed(1)} data-yaw={h?.yaw?.toFixed(1)} data-body={s?.body_yaw?.toFixed(1)}>
      <div className="ro-row"><span title="head roll">R {deg(h?.roll)}</span><span title="head pitch">P {deg(h?.pitch)}</span><span title="head yaw">Y {deg(h?.yaw)}</span></div>
      <div className="ro-row">
        <span title="body yaw">⟳{deg(s?.body_yaw)}</span>
        <span title="antennas right / left">📡{a ? `${a[0].toFixed(0)}/${a[1].toFixed(0)}` : '—'}</span>
        <span title="daemon control loop">{hz != null ? `${hz.toFixed(0)}Hz` : '—Hz'}</span>
        <span title="motor mode" className={s?.control_mode === 'enabled' ? '' : 'warn'}>⚙{mode}</span>
      </div>
    </div>
  )
}

/** Perception overlays on the twin — only when the state carries them (state.tracking / state.doa / state.imu; see docs/DASHBOARD.md). */
function TwinDetail({ s }: { s: State | null }) {
  const t = s?.tracking, d = s?.doa, imu = s?.imu
  const face = !!t?.enabled
  const doa = d && typeof d.angle === 'number' ? d : null
  const lifted = imu && (imu.lifted === true || imu.picked_up === true), tilted = imu && imu.tilted === true
  if (!face && !doa && !lifted && !tilted) return null
  return (
    <div className="twin-detail" data-testid="twin-detail">
      {face && (
        <div className={`gaze ${t!.detected ? 'on' : ''} ${t!.paused ? 'paused' : ''}`} data-testid="gaze" title="face position relative to the head's gaze (daemon tracker)">
          <span className="gaze-ring" />
          {t!.detected && t!.x != null && t!.y != null && <span className="gaze-dot" style={{ left: `${50 + t!.x * 40}%`, top: `${50 + t!.y * 40}%` }} data-testid="gaze-dot" />}
        </div>
      )}
      {doa && <DoaArc angle={doa.angle as number} speech={!!doa.speech_detected} />}
      {(lifted || tilted) && <span className="imu-badge" data-testid="imu-badge">{lifted ? '🫳 lifted' : '↗ tilted'}</span>}
    </div>
  )
}

/** Direction of arrival (ReSpeaker via the daemon): needle on a compass ring; angle in rad as delivered by state.doa.angle, 0 = front. */
function DoaArc({ angle, speech }: { angle: number; speech: boolean }) {
  const a = rad2deg(angle)
  // SVG: 0° = up (front of the robot); positive angle = counter-clockwise (robot's left) — see docs/DASHBOARD.md for the convention note
  const r = 17, cx = 22, cy = 22, rad = (-a * Math.PI) / 180
  const nx = cx + r * Math.sin(rad), ny = cy - r * Math.cos(rad)
  return (
    <div className={`doa ${speech ? 'on' : ''}`} data-testid="doa" data-angle={a.toFixed(0)} title="direction of arrival of speech">
      <svg viewBox="0 0 44 44" width="44" height="44">
        <circle cx={cx} cy={cy} r={r} className="doa-ring" />
        <path d={`M${cx} ${cy - r - 3} l-3 5 h6 z`} className="doa-front" />
        <line x1={cx} y1={cy} x2={nx} y2={ny} className="doa-needle" />
        <circle cx={nx} cy={ny} r="3" className="doa-tip" />
      </svg>
      <span className="doa-label">{speech ? '🗣' : '·'} {a.toFixed(0)}°</span>
    </div>
  )
}

/** Double-tap / double-click detector usable on pointer events (touch + mouse), ignoring drags. */
function useDoubleTap(cb: () => void) {
  const last = useRef(0), downAt = useRef<{ x: number; y: number } | null>(null)
  const up = useCallback((e: React.PointerEvent) => {
    const d = downAt.current
    if (d && Math.hypot(e.clientX - d.x, e.clientY - d.y) > 12) { last.current = 0; return }
    const now = performance.now()
    if (now - last.current < 350) { last.current = 0; cb() } else last.current = now
  }, [cb]) as ((e: React.PointerEvent) => void) & { down: (e: React.PointerEvent) => void }
  up.down = (e: React.PointerEvent) => { downAt.current = { x: e.clientX, y: e.clientY } }
  return up
}

