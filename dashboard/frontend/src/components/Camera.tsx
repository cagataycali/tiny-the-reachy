import { useEffect, useState } from 'react'
import { streamUrl, type Tracking } from '../lib/api'

export function Camera({ ok, fps, error, tracking }: { ok: boolean; fps: number; error: string | null; tracking?: Tracking }) {
  const [nonce, setNonce] = useState(0)
  useEffect(() => { if (!ok) { const t = setTimeout(() => setNonce((n) => n + 1), 3000); return () => clearTimeout(t) } }, [ok, nonce])
  return (
    <div className="camera">
      {ok ? <img src={streamUrl('/api/stream', `n=${nonce}`)} alt="live camera" onError={() => setTimeout(() => setNonce((n) => n + 1), 2000)} />
        : <div className="camera-off">📷 camera {error ? `— ${error}` : 'warming up…'}</div>}
      <span className="badge tl">{ok ? `LIVE · ${fps.toFixed(0)} fps` : 'OFFLINE'}</span>
      {ok && tracking?.enabled && <FaceMarker t={tracking} />}
    </div>
  )
}

/** Face marker from the DAEMON's tracker (get_tracked_face): x,y ∈ [-1,1], +x right, +y down → % of the frame. */
export function FaceMarker({ t }: { t: Tracking }) {
  if (!t.detected || t.x == null || t.y == null) {
    return <span className={`face-state ${t.paused ? 'paused' : ''}`} data-testid="face-state">👁 {t.paused ? `tracking paused (${(t.holds || []).join(', ')})` : 'looking for a face…'}</span>
  }
  const left = (t.x + 1) * 50, top = (t.y + 1) * 50
  return (
    <>
      <span className={`face-box ${t.paused ? 'paused' : ''}`} data-testid="face-box" style={{ left: `${left}%`, top: `${top}%` }} />
      <span className="face-state on" data-testid="face-state">👁 face {t.paused ? '· paused while ' + (t.holds || []).join(', ') : 'locked'}</span>
    </>
  )
}
