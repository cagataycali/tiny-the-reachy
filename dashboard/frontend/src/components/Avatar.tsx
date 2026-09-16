import { Head } from '../lib/api'

// A lightweight SVG head + antennas mirroring live roll/pitch/yaw/antennas. Not a twin — a face.
export function Avatar({ head, antennas, bodyYaw, playing }: { head: Head | null; antennas: [number, number] | null; bodyYaw: number | null; playing: string | null }) {
  const h = head ?? { roll: 0, pitch: 0, yaw: 0, x_mm: 0, y_mm: 0, z_mm: 0 }
  const [ar, al] = antennas ?? [0, 0]
  // yaw → horizontal shift + squash, pitch → vertical shift, roll → rotation
  const yawX = Math.max(-1, Math.min(1, h.yaw / 90))
  const pitchY = Math.max(-1, Math.min(1, h.pitch / 40))
  const eyeDx = yawX * 14, eyeDy = pitchY * 8
  const headSquash = 1 - Math.abs(yawX) * 0.18
  return (
    <svg viewBox="0 0 200 200" className="avatar" aria-label="head avatar">
      <defs>
        <radialGradient id="g" cx="50%" cy="40%"><stop offset="0%" stopColor="#f6f6fa" /><stop offset="100%" stopColor="#c9c9d6" /></radialGradient>
      </defs>
      {/* body / base, rotates with body yaw */}
      <g transform={`translate(100 168) rotate(${(bodyYaw ?? 0) / 4})`}>
        <ellipse rx="52" ry="14" fill="#1e1e2a" stroke="#3a3a4d" />
        <rect x="-46" y="-2" width="92" height="4" rx="2" fill="#5eead4" opacity="0.6" />
      </g>
      <g transform={`translate(100 ${100 - h.z_mm * 0.6 + pitchY * 6}) rotate(${h.roll})`}>
        {/* antennas: right is drawn on the viewer's left? no — robot's right is viewer's right in a mirror; keep robot frame */}
        <g transform="translate(-34 -46)"><line x1="0" y1="0" x2={Math.sin((-al * Math.PI) / 180) * 42} y2={-Math.cos((al * Math.PI) / 180) * 42} stroke="#5eead4" strokeWidth="4" strokeLinecap="round" /><circle cx={Math.sin((-al * Math.PI) / 180) * 42} cy={-Math.cos((al * Math.PI) / 180) * 42} r="5" fill="#5eead4" /></g>
        <g transform="translate(34 -46)"><line x1="0" y1="0" x2={Math.sin((-ar * Math.PI) / 180) * 42} y2={-Math.cos((ar * Math.PI) / 180) * 42} stroke="#f472b6" strokeWidth="4" strokeLinecap="round" /><circle cx={Math.sin((-ar * Math.PI) / 180) * 42} cy={-Math.cos((ar * Math.PI) / 180) * 42} r="5" fill="#f472b6" /></g>
        {/* head */}
        <g transform={`translate(${yawX * 10} 0) scale(${headSquash} 1)`}>
          <rect x="-58" y="-50" width="116" height="100" rx="34" fill="url(#g)" stroke="#8a8aa0" strokeWidth="2" />
          <rect x="-46" y="-30" width="92" height="52" rx="18" fill="#101018" />
          {/* eyes */}
          <g transform={`translate(${eyeDx} ${eyeDy})`}>
            <circle cx="-20" cy="-4" r={playing ? 11 : 9} fill="#5eead4" className="eye" />
            <circle cx="20" cy="-4" r={playing ? 11 : 9} fill="#5eead4" className="eye" />
            <circle cx="-17" cy="-7" r="3" fill="#fff" /><circle cx="23" cy="-7" r="3" fill="#fff" />
          </g>
        </g>
      </g>
      <text x="100" y="196" textAnchor="middle" fontSize="10" fill="#8a8aa0" fontFamily="ui-monospace,monospace">
        r {h.roll.toFixed(0)}° p {h.pitch.toFixed(0)}° y {h.yaw.toFixed(0)}° · body {(bodyYaw ?? 0).toFixed(0)}°
      </text>
    </svg>
  )
}
