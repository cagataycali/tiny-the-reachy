// Picture-in-picture geometry + prefs for the twin/camera PiP (pure functions, no DOM).
// The viewport hosts two LAYERS (camera, twin). One is "main" (fills the viewport), the other is the PiP card.
// Swapping = re-assigning boxes; both layers stay mounted so the MJPEG stream and the MuJoCo sim never restart.
export type Corner = 'tl' | 'tr' | 'bl' | 'br'
export type PiPSize = 'S' | 'M' | 'L'
export type PiPPrefs = { corner: Corner; size: PiPSize | null; swapped: boolean; open: boolean; hinted?: boolean }
export type Box = { x: number; y: number; w: number; h: number }

export const PIP_KEY = 'reachy.pip.v1'
export const SIZES: Record<PiPSize, { w: number; h: number }> = { S: { w: 160, h: 120 }, M: { w: 320, h: 240 }, L: { w: 480, h: 360 } }
export const PAD = 10            // gap to the viewport edge
export const TOP_OFF = 50        // below the chip row (LIVE / playing / swap chips)
export const BOT_OFF = 84        // above the STOP button (60 px + 12 px) and the cmdbar edge
export const READOUT_H = 32      // max detail strip height under the card (part of the card's footprint); see readoutH()
/** S cards wrap the readout onto two rows; M/L fit one. */
export const readoutH = (size: PiPSize) => (size === 'S' ? 32 : 24)
export const DEFAULT_PREFS: PiPPrefs = { corner: 'tr', size: null, swapped: false, open: true }

export function loadPrefs(): PiPPrefs {
  try {
    const raw = localStorage.getItem(PIP_KEY); if (!raw) return { ...DEFAULT_PREFS }
    const p = JSON.parse(raw)
    return {
      corner: (['tl', 'tr', 'bl', 'br'] as Corner[]).includes(p.corner) ? p.corner : 'tr',
      size: p.size === 'S' || p.size === 'M' || p.size === 'L' ? p.size : null,
      swapped: !!p.swapped, open: p.open !== false, hinted: !!p.hinted,
    }
  } catch { return { ...DEFAULT_PREFS } }
}
export function savePrefs(p: PiPPrefs) { try { localStorage.setItem(PIP_KEY, JSON.stringify(p)) } catch {} }

/** Default size for a host: S on phones, M from 960 px (desktop side-panel layout). */
export function autoSize(hostW: number): PiPSize { return hostW >= 960 ? 'M' : 'S' }
export function sizesFor(hostW: number, hostH: number): PiPSize[] {
  const out: PiPSize[] = ['S', 'M']
  if (hostW >= 960 && hostH >= SIZES.L.h + TOP_OFF + BOT_OFF) out.push('L')
  return out
}
export function nextSize(cur: PiPSize, hostW: number, hostH: number): PiPSize {
  const all = sizesFor(hostW, hostH); const i = all.indexOf(cur)
  return all[(i + 1) % all.length]
}

/** Landscape phone: not enough height for a floating card → split the viewport in two side by side. */
export function isSplit(hostW: number, hostH: number): boolean { return hostW > hostH && hostH < 420 && hostW < 960 }

/** Card box (content only; the readout strip hangs READOUT_H below it) for a corner, clamped to the host. */
export function cornerBox(corner: Corner, size: PiPSize, hostW: number, hostH: number): Box {
  let { w, h } = SIZES[size]
  const ro = readoutH(size)
  const maxW = Math.max(80, hostW - 2 * PAD), maxH = Math.max(60, hostH - TOP_OFF - BOT_OFF - ro)
  const k = Math.min(1, maxW / w, maxH / h); w = Math.round(w * k); h = Math.round(h * k)
  const x = corner === 'tl' || corner === 'bl' ? PAD : hostW - PAD - w
  const y = corner === 'tl' || corner === 'tr' ? TOP_OFF : hostH - BOT_OFF - ro - h
  return { x, y, w, h }
}

/** Nearest corner for a card centre after a drag. */
export function snapCorner(cx: number, cy: number, hostW: number, hostH: number): Corner {
  const left = cx < hostW / 2, top = cy < hostH / 2
  return top ? (left ? 'tl' : 'tr') : (left ? 'bl' : 'br')
}

/** Pixels the mind bubbles must lift by so a bottom-corner card never covers them (0 when not needed). */
export function bubbleLift(p: PiPPrefs, size: PiPSize, split: boolean, card: Box): number {
  if (!p.open || split || (p.corner !== 'bl' && p.corner !== 'br')) return 0
  return card.h + readoutH(size) + (BOT_OFF - PAD) + 6      // the overlay already sits PAD above the edge; the card bottom is BOT_OFF above it
}

/** Side-by-side layout for landscape phones: main = left half, pip = right half (no readout strip below; it overlays). */
export function splitBoxes(hostW: number, hostH: number): { main: Box; pip: Box } {
  const half = Math.floor(hostW / 2)
  return { main: { x: 0, y: 0, w: half, h: hostH }, pip: { x: half, y: 0, w: hostW - half, h: hostH } }
}

export const deg = (v: number | null | undefined, d = 0) => (v == null || Number.isNaN(v) ? '—' : `${v.toFixed(d)}°`)
export const rad2deg = (r: number) => (r * 180) / Math.PI
