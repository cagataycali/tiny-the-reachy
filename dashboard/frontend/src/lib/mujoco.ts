// MuJoCo-WASM loader + the Reachy Mini twin wrapper.
//
// Engine: official Google-DeepMind bindings @mujoco/mujoco (Apache-2.0). Loaded from jsDelivr first
// (CORS ok, 10 MB wasm cached at the edge — the CM4 behind the tunnel must not serve it on every visit),
// falling back to the same-origin copy in /public/mujoco (vendored from the npm package unmodified).
//
// Model: /model/twin.xml is Pollen's official reachy_mini.xml with every <geom> stripped — pure kinematics
// (19 bodies, 16 joints incl. the 7 passive Stewart ball joints + 5 closing constraints, 9 position
// actuators). three.js draws the visual meshes from /model/meshes.bin attached to body frames
// (dashboard/tools/build_twin_model.py). Motor targets = the daemon's PRESENT joint angles
// (state.joints: yaw_body, stewart_1..6, right_antenna, left_antenna in rad) → the passive chain and
// the head follow through the constraints, exactly like the real Stewart platform.

export interface TwinGeom { body: string; pos: [number, number, number]; quat: [number, number, number, number]; mesh: string; rgba: [number, number, number, number] }
export interface TwinGeoms { geoms: TwinGeom[]; meshes: string[]; pack: string; offsets: Record<string, [number, number]>; sha: string; xml_sha?: string }
export interface PackedMesh { vertices: Float32Array; indices: Uint16Array | Uint32Array }

export const MOTOR_JOINTS = ['yaw_body', 'stewart_1', 'stewart_2', 'stewart_3', 'stewart_4', 'stewart_5', 'stewart_6', 'right_antenna', 'left_antenna'] as const
export const MUJOCO_VERSION = '3.13.0'
export const MUJOCO_CDN = `https://cdn.jsdelivr.net/npm/@mujoco/mujoco@${MUJOCO_VERSION}`
/** sim seconds per wall second while the twin catches up — the real motors are faster than kp=50 in sim */
export const TIME_WARP = 3

function toArr(v: any): number[] {
  if (v == null) return []
  if (Array.isArray(v)) return v
  if (typeof v.length === 'number') return Array.from(v as ArrayLike<number>)
  return []
}

let _modulePromise: Promise<any> | null = null
export let mujocoSource: 'cdn' | 'local' | null = null

async function loadFrom(base: string, timeoutMs: number): Promise<any> {
  const jsUrl = `${base}/mujoco.js`
  const mod: any = await Promise.race([
    import(/* @vite-ignore */ jsUrl),
    new Promise((_, rej) => setTimeout(() => rej(new Error(`timeout loading ${jsUrl}`)), timeoutMs)),
  ])
  const factory = mod.default ?? mod
  return factory({ locateFile: (p: string, prefix: string) => (p.endsWith('.wasm') ? `${base}/mujoco.wasm` : prefix + p) })
}

export async function loadMujoco(): Promise<any> {
  if (!_modulePromise) {
    _modulePromise = (async () => {
      try {
        const m = await loadFrom(MUJOCO_CDN, 12000)
        mujocoSource = 'cdn'; return m
      } catch (e) {
        console.warn('mujoco: CDN failed, using same-origin copy', e)
        const m = await loadFrom(new URL('/mujoco', location.origin).href, 60000)
        mujocoSource = 'local'; return m
      }
    })()
    _modulePromise.catch(() => { _modulePromise = null })
  }
  return _modulePromise
}

/** Names from a MuJoCo name pool, in id order. Pure. */
export function decodeNames(names: Uint8Array | undefined, adr: number[], n: number): string[] {
  if (!names) return []
  const dec = new TextDecoder()
  const out: string[] = []
  for (let i = 0; i < n; i++) {
    let j = adr[i] ?? 0, e = j
    while (e < names.length && names[e] !== 0) e++
    out.push(dec.decode(names.slice(j, e)))
  }
  return out
}

/** Parse one RMB1 record (see build_twin_model.pack). Pure. */
export function unpackMesh(buf: ArrayBuffer, offset: number, length: number): PackedMesh {
  const dv = new DataView(buf, offset, length)
  if (dv.getUint8(0) !== 0x52 || dv.getUint8(1) !== 0x4d || dv.getUint8(2) !== 0x42 || dv.getUint8(3) !== 0x31) throw new Error('bad mesh magic')
  const nv = dv.getUint32(4, true), nf = dv.getUint32(8, true), itype = dv.getUint8(12)
  const vOff = offset + 16
  const vertices = new Float32Array(buf.slice(vOff, vOff + nv * 12))
  const iOff = vOff + nv * 12
  const indices = itype === 2 ? new Uint16Array(buf.slice(iOff, iOff + nf * 6)) : new Uint32Array(buf.slice(iOff, iOff + nf * 12))
  return { vertices, indices }
}

export class ReachySim {
  static __setModule(instance: any) { _modulePromise = Promise.resolve(instance) }
  mj: any; model: any; data: any
  nbody = 0
  bodyNames: string[] = []
  bodyId: Record<string, number> = {}
  private act: number[] = []           // actuator index per MOTOR_JOINTS slot
  private qadr: number[] = []          // qpos address per motor joint
  headSite = -1
  private headBody = -1
  targets: number[] | null = null
  private settled = false
  stepCount = 0

  private constructor(mj: any, model: any, data: any) {
    this.mj = mj; this.model = model; this.data = data
    this.nbody = Number(model.nbody)
    this.bodyNames = decodeNames(model.names, toArr(model.name_bodyadr), this.nbody)
    this.bodyNames.forEach((n, i) => { if (n) this.bodyId[n] = i })
    const nu = Number(model.nu), njnt = Number(model.njnt)
    const actNames = decodeNames(model.names, toArr(model.name_actuatoradr), nu)
    const jntNames = decodeNames(model.names, toArr(model.name_jntadr), njnt)
    const jq = toArr(model.jnt_qposadr)
    this.act = MOTOR_JOINTS.map((n) => actNames.indexOf(n))
    this.qadr = MOTOR_JOINTS.map((n) => { const j = jntNames.indexOf(n); return j >= 0 ? jq[j] : -1 })
    const nsite = Number(model.nsite ?? 0)
    const siteNames = decodeNames(model.names, toArr(model.name_siteadr), nsite)
    this.headSite = siteNames.indexOf('head')
    this.headBody = this.headSite >= 0 ? toArr(model.site_bodyid)[this.headSite] : -1
  }

  static async create(xml: string): Promise<ReachySim> {
    const mj = await loadMujoco()
    const model = mj.MjModel.from_xml_string(xml)
    const data = new mj.MjData(model)
    mj.mj_forward(model, data)
    return new ReachySim(mj, model, data)
  }

  get timestep(): number { return Number(this.model.opt?.timestep ?? 0.002) }

  /** New motor targets (rad, MOTOR_JOINTS order). The first set also snaps qpos so the twin starts right. */
  /** settle trace for e2e: {arrived, settled} wall ms per target change > 5° (last 20) */
  trace: { arrived: number; settled: number | null; stepDeg: number }[] = []
  setTargets(j: ArrayLike<number>): void {
    if (!j || j.length < 9) return
    const t = Array.from(j).slice(0, 9)
    if (this.targets) {
      let d = 0; for (let i = 0; i < 9; i++) d = Math.max(d, Math.abs(t[i] - this.targets[i]))
      if (d > 0.087) { this.trace.push({ arrived: performance.now(), settled: null, stepDeg: (d * 180) / Math.PI }); if (this.trace.length > 20) this.trace.shift() }
    }
    this.targets = t
    for (let i = 0; i < 9; i++) if (this.act[i] >= 0) this.data.ctrl[this.act[i]] = t[i]
    if (!this.settled) this.settle(t)
  }

  /** First pose: ramp the motors from the rest configuration to the target so the closed chain follows
   *  continuously (snapping qpos lets the Stewart platform land on the flipped branch — seen once,
   *  head yaw 175°). 0.6 s of sim, ~10 ms of CPU. Re-run if the head ever ends up inverted. */
  private settle(t: number[]): void {
    this.mj.mj_resetData(this.model, this.data)
    const N = 300
    for (let k = 1; k <= N; k++) {
      const a = Math.min(1, k / (N * 0.6))
      for (let i = 0; i < 9; i++) if (this.act[i] >= 0) this.data.ctrl[this.act[i]] = t[i] * a
      this.mj.mj_step(this.model, this.data)
    }
    this.settled = true
  }

  /** the 'head' site z-axis · world z — 1 upright, <0 flipped */
  headUp(): number { const i = this.headSite; if (i < 0) return 1; return toArr(this.data.site_xmat)[i * 9 + 8] }

  /** Advance by wall-clock dt (capped) at TIME_WARP; returns steps taken. */
  step(dtSeconds: number): number {
    const h = this.timestep
    const n = Math.min(Math.max(1, Math.round((dtSeconds * TIME_WARP) / h)), Math.round(0.3 / h))
    for (let i = 0; i < n; i++) this.mj.mj_step(this.model, this.data)
    this.stepCount += n
    if (this.settled && this.targets && this.headUp() < 0.3) { this.settle(this.targets); console.warn('twin: head flipped — re-settled from rest') }
    const open = this.trace[this.trace.length - 1]
    if (open && open.settled === null && this.lag() < 0.0175) open.settled = performance.now()   // within 1°
    return n
  }

  /** motor joint angles in the sim (rad), MOTOR_JOINTS order */
  joints(): number[] { const q = this.data.qpos; return this.qadr.map((a) => (a >= 0 ? q[a] : 0)) }
  /** max |target - actual| over the motors (rad) — the twin's own lag metric */
  lag(): number {
    if (!this.targets) return 0
    const j = this.joints(); let m = 0
    for (let i = 0; i < 9; i++) m = Math.max(m, Math.abs(j[i] - this.targets[i]))
    return m
  }
  bodyXpos(): number[] { return toArr(this.data.xpos) }
  bodyXmat(): number[] { return toArr(this.data.xmat) }
  headPos(): [number, number, number] {
    const p = toArr(this.data.site_xpos); const i = this.headSite
    return i >= 0 ? [p[i * 3], p[i * 3 + 1], p[i * 3 + 2]] : [0, 0, 0.15]
  }
  headBodyId(): number { return this.headBody }
  /** head yaw/pitch/roll in the world (deg) from the 'head' site frame (identity at rest, x forward, z up) */
  headEuler(): { roll: number; pitch: number; yaw: number } {
    const i = this.headSite; if (i < 0) return { roll: 0, pitch: 0, yaw: 0 }
    const m = toArr(this.data.site_xmat); const r = (k: number) => m[i * 9 + k]
    const yaw = Math.atan2(r(3), r(0)), pitch = Math.atan2(-r(6), Math.hypot(r(7), r(8))), roll = Math.atan2(r(7), r(8))
    const D = 180 / Math.PI
    return { roll: roll * D, pitch: pitch * D, yaw: yaw * D }
  }
  reset(): void { this.mj.mj_resetData(this.model, this.data); this.mj.mj_forward(this.model, this.data); this.settled = false }
}
