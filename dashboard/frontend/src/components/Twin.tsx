// The live digital twin: MuJoCo-WASM kinematics + three.js meshes, mirroring the real Reachy Mini.
// Motor targets come from the WS state (state.joints, rad) at 10 Hz; the sim runs at 2× wall time so the
// Stewart platform catches up within a frame or two. Pointer drag orbits; wheel/pinch zooms.
import { useEffect, useRef, useState } from 'react'
import * as THREE from 'three'
import { MOTOR_JOINTS, ReachySim, TwinGeoms, mujocoSource, unpackMesh } from '../lib/mujoco'

export type TwinStatus = { phase: 'loading' | 'ready' | 'error'; detail: string; fps?: number; lagDeg?: number; source?: string | null }

export default function Twin({ joints, onStatus, height = 260, paused = false, maxFps = 0, autoOrbit = true }: {
  joints: number[] | null | undefined; onStatus?: (s: TwinStatus) => void; height?: number
  /** paused = keep the sim mirroring but skip rendering (hidden PiP) · maxFps caps the render rate (PiP ≤ 30) · autoOrbit = slow idle spin */
  paused?: boolean; maxFps?: number; autoOrbit?: boolean }) {
  const host = useRef<HTMLDivElement>(null)
  const ctl = useRef({ paused, maxFps, autoOrbit }); ctl.current = { paused, maxFps, autoOrbit }
  const simRef = useRef<ReachySim | null>(null)
  const jointsRef = useRef<number[] | null>(null)
  const [status, setStatus] = useState<TwinStatus>({ phase: 'loading', detail: 'starting' })
  const statusCb = useRef(onStatus); statusCb.current = onStatus
  const set = (s: TwinStatus) => { setStatus(s); statusCb.current?.(s) }

  // latest joints → sim targets (10 Hz from the socket)
  useEffect(() => {
    if (joints && joints.length >= 9) { jointsRef.current = joints; simRef.current?.setTargets(joints) }
  }, [joints])

  useEffect(() => {
    const el = host.current!
    let alive = true, raf = 0
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: 'high-performance' })
    renderer.setPixelRatio(Math.min(devicePixelRatio, 2))
    renderer.shadowMap.enabled = true
    renderer.setClearColor(0x000000, 0)
    el.appendChild(renderer.domElement)
    const scene = new THREE.Scene()
    const cam = new THREE.PerspectiveCamera(32, 1, 0.01, 10)
    cam.up.set(0, 0, 1)
    scene.add(new THREE.HemisphereLight(0xaab4d4, 0x1a1a22, 1.1))
    const key = new THREE.DirectionalLight(0xffffff, 1.6); key.position.set(0.6, -0.5, 0.9); key.castShadow = true
    key.shadow.mapSize.set(1024, 1024); key.shadow.camera.near = 0.05; key.shadow.camera.far = 3
    for (const k of ['left', 'right', 'top', 'bottom'] as const) (key.shadow.camera as any)[k] = k === 'left' || k === 'bottom' ? -0.4 : 0.4
    scene.add(key)
    const fill = new THREE.DirectionalLight(0x88aaff, 0.5); fill.position.set(-0.6, 0.4, 0.5); scene.add(fill)
    // floor disc + grid
    const floor = new THREE.Mesh(new THREE.CircleGeometry(0.22, 64), new THREE.MeshStandardMaterial({ color: 0x14141c, roughness: 0.9, metalness: 0 }))
    floor.receiveShadow = true; floor.position.z = -0.0005; scene.add(floor)
    const grid = new THREE.PolarGridHelper(0.22, 8, 4, 48, 0x2a2a3a, 0x1e1e2a); grid.rotateX(Math.PI / 2); scene.add(grid)

    const resize = () => { const w = el.clientWidth || 320, h = el.clientHeight || height; renderer.setSize(w, h, false); cam.aspect = w / h; cam.fov = w < h ? Math.min(58, 32 * (h / w) * 0.85) : 32; cam.updateProjectionMatrix() }   // portrait hosts widen the FOV so the antennas stay in frame
    resize(); const ro = new ResizeObserver(resize); ro.observe(el)

    const orbit = { yaw: 0.55, pitch: 0.32, dist: 0.62 }
    let dragging = false, lx = 0, ly = 0, pinch = 0
    const onDown = (e: PointerEvent) => { dragging = true; lx = e.clientX; ly = e.clientY; el.setPointerCapture(e.pointerId) }
    const onMove = (e: PointerEvent) => { if (!dragging) return; orbit.yaw -= (e.clientX - lx) * 0.008; orbit.pitch = Math.max(-0.2, Math.min(1.3, orbit.pitch + (e.clientY - ly) * 0.006)); lx = e.clientX; ly = e.clientY }
    const onUp = () => { dragging = false }
    const onWheel = (e: WheelEvent) => { e.preventDefault(); orbit.dist = Math.max(0.3, Math.min(1.6, orbit.dist * (1 + e.deltaY * 0.001))) }
    const onTouch = (e: TouchEvent) => { if (e.touches.length === 2) { const d = Math.hypot(e.touches[0].clientX - e.touches[1].clientX, e.touches[0].clientY - e.touches[1].clientY); if (pinch) orbit.dist = Math.max(0.3, Math.min(1.6, orbit.dist * (pinch / d))); pinch = d; e.preventDefault() } else pinch = 0 }
    el.addEventListener('pointerdown', onDown); el.addEventListener('pointermove', onMove); el.addEventListener('pointerup', onUp)
    el.addEventListener('pointercancel', onUp); el.addEventListener('wheel', onWheel, { passive: false }); el.addEventListener('touchmove', onTouch, { passive: false })

    let sim: ReachySim | null = null
    const bodyGroups: (THREE.Group | null)[] = []

    ;(async () => {
      try {
        set({ phase: 'loading', detail: 'model' })
        const geomsJ = await fetch('/model/geoms.json').then((r) => { if (!r.ok) throw new Error(`geoms.json ${r.status}`); return r.json() as Promise<TwinGeoms> })
        const [xml, pack] = await Promise.all([          // versioned by sha → immutable-cached by the server
          fetch(`/model/twin.xml?v=${geomsJ.xml_sha ?? ''}`).then((r) => { if (!r.ok) throw new Error(`twin.xml ${r.status}`); return r.text() }),
          fetch(`/model/${geomsJ.pack}?v=${geomsJ.sha}`).then((r) => { if (!r.ok) throw new Error(`meshes.bin ${r.status}`); return r.arrayBuffer() }),
        ])
        set({ phase: 'loading', detail: 'physics engine' })
        sim = await ReachySim.create(xml)
        if (!alive) return
        // meshes → per-body groups
        const geoCache = new Map<string, THREE.BufferGeometry>()
        for (const name of geomsJ.meshes) {
          const [off, len] = geomsJ.offsets[name]
          const m = unpackMesh(pack, off, len)
          const g = new THREE.BufferGeometry()
          g.setAttribute('position', new THREE.BufferAttribute(m.vertices, 3))
          g.setIndex(new THREE.BufferAttribute(m.indices, 1))
          g.computeVertexNormals()
          geoCache.set(name, g)
        }
        for (let b = 0; b < sim.nbody; b++) { const grp = new THREE.Group(); scene.add(grp); bodyGroups.push(grp) }
        for (const g of geomsJ.geoms) {
          const bid = sim.bodyId[g.body]; const geo = geoCache.get(g.mesh)
          if (bid == null || !geo) continue
          const [r, gg, bb, a] = g.rgba
          const white = r > 0.9 && gg > 0.9 && bb > 0.9
          const mat = new THREE.MeshStandardMaterial({ color: new THREE.Color(r, gg, bb), roughness: white ? 0.45 : 0.6, metalness: white ? 0.05 : 0.2, transparent: a < 1, opacity: a })
          const mesh = new THREE.Mesh(geo, mat)
          mesh.castShadow = true; mesh.receiveShadow = true
          mesh.position.set(g.pos[0], g.pos[1], g.pos[2])
          mesh.quaternion.set(g.quat[1], g.quat[2], g.quat[3], g.quat[0])   // MuJoCo wxyz → three xyzw
          bodyGroups[bid]!.add(mesh)
        }
        simRef.current = sim
        if (jointsRef.current) sim.setTargets(jointsRef.current)
        ;(window as any).__reachyTwin = { sim, fps: () => lastFps, paused: () => ctl.current.paused, joints: () => sim!.joints(), head: () => sim!.headEuler(), lag: () => sim!.lag(), trace: () => sim!.trace, names: MOTOR_JOINTS, source: () => mujocoSource }
        set({ phase: 'ready', detail: 'mirroring', source: mujocoSource })
      } catch (e: any) {
        console.error(e); set({ phase: 'error', detail: String(e?.message ?? e) })
      }
    })()

    // physics on its own clock (10 ms) so a slow renderer / throttled tab never delays the mirror
    let simLast = performance.now()
    const simTimer = setInterval(() => {
      const now = performance.now(); const dt = Math.min(0.1, (now - simLast) / 1000); simLast = now
      if (sim?.targets) sim.step(dt)
    }, 10)
    let last = performance.now(), frames = 0, tHz = last, lastFps = 0, lastRender = 0
    const m4 = new THREE.Matrix4(), q = new THREE.Quaternion()
    const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches
    const tick = (now: number) => {
      if (!alive) return
      raf = requestAnimationFrame(tick)
      const c = ctl.current
      if (c.paused) { last = now; return }                                   // hidden: sim keeps mirroring, no GPU work
      if (c.maxFps > 0 && now - lastRender < 1000 / c.maxFps - 1) return     // PiP: cap the render rate
      lastRender = now
      const dt = Math.min(0.1, (now - last) / 1000); last = now
      if (sim) {
        const xp = sim.bodyXpos(), xm = sim.bodyXmat()
        for (let b = 1; b < bodyGroups.length; b++) {
          const grp = bodyGroups[b]; if (!grp) continue
          m4.set(xm[b * 9], xm[b * 9 + 1], xm[b * 9 + 2], 0, xm[b * 9 + 3], xm[b * 9 + 4], xm[b * 9 + 5], 0, xm[b * 9 + 6], xm[b * 9 + 7], xm[b * 9 + 8], 0, 0, 0, 0, 1)
          q.setFromRotationMatrix(m4)
          grp.position.set(xp[b * 3], xp[b * 3 + 1], xp[b * 3 + 2]); grp.quaternion.copy(q)
        }
        frames++
        if (now - tHz > 1000) { set({ phase: 'ready', detail: sim.targets ? 'mirroring' : 'waiting for state', fps: frames, lagDeg: (sim.lag() * 180) / Math.PI, source: mujocoSource }); lastFps = frames; frames = 0; tHz = now }
      }
      const tgt = new THREE.Vector3(0, 0, 0.13)
      if (!dragging && c.autoOrbit && !reduced) orbit.yaw += dt * 0.05
      cam.position.set(tgt.x + orbit.dist * Math.cos(orbit.pitch) * Math.cos(orbit.yaw), tgt.y + orbit.dist * Math.cos(orbit.pitch) * Math.sin(orbit.yaw), tgt.z + orbit.dist * Math.sin(orbit.pitch))
      cam.lookAt(tgt)
      renderer.render(scene, cam)
    }
    raf = requestAnimationFrame(tick)

    return () => {
      alive = false; cancelAnimationFrame(raf); clearInterval(simTimer); ro.disconnect()
      el.removeEventListener('pointerdown', onDown); el.removeEventListener('pointermove', onMove); el.removeEventListener('pointerup', onUp)
      el.removeEventListener('pointercancel', onUp); el.removeEventListener('wheel', onWheel); el.removeEventListener('touchmove', onTouch)
      renderer.dispose(); el.innerHTML = ''; simRef.current = null
    }
  }, [])

  return (
    <div className="twin" ref={host} style={{ height }} data-testid="twin" data-phase={status.phase}>
      <div className={`twin-badge ${status.phase}`}>
        {status.phase === 'loading' && <>⟳ twin · {status.detail}…</>}
        {status.phase === 'ready' && <>◉ twin · {status.detail}{status.fps ? ` · ${status.fps} fps` : ''}{status.lagDeg != null ? ` · lag ${status.lagDeg.toFixed(1)}°` : ''}</>}
        {status.phase === 'error' && <>✗ twin · {status.detail}</>}
      </div>
    </div>
  )
}
