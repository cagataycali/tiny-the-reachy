import { useEffect, useState } from 'react'
import { streamUrl } from '../lib/api'

export function Camera({ ok, fps, error }: { ok: boolean; fps: number; error: string | null }) {
  const [nonce, setNonce] = useState(0)
  useEffect(() => { if (!ok) { const t = setTimeout(() => setNonce((n) => n + 1), 3000); return () => clearTimeout(t) } }, [ok, nonce])
  return (
    <div className="camera">
      {ok ? <img src={streamUrl('/api/stream', `n=${nonce}`)} alt="live camera" onError={() => setTimeout(() => setNonce((n) => n + 1), 2000)} />
        : <div className="camera-off">📷 camera {error ? `— ${error}` : 'warming up…'}</div>}
      <span className="badge tl">{ok ? `LIVE · ${fps.toFixed(0)} fps` : 'OFFLINE'}</span>
    </div>
  )
}
