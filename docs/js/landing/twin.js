// twin.js — draws TINY's real geometry (dashboard/frontend/public/model/meshes.bin, the cockpit twin's meshes) with three.js,
// posed from precomputed MuJoCo body poses (tools/landing/emotion_poses.py → assets/landing/poses/<move>.json).
// ONE module, two hosts: tools/landing/twin.html (Playwright, renders the hero still + frame sequences offline) and the landing
// page itself (lazy after LCP, drag to orbit like the cockpit). No physics here — poses are data, the same numbers the daemon's
// IK + MuJoCo produced. Colours are the geoms' own rgba (Pollen's MJCF materials), lit by a neutral studio rig.
import * as THREE from 'https://cdn.jsdelivr.net/npm/three@0.186.0/build/three.module.min.js'

export const MESH_MAGIC = 0x31424d52 // 'RMB1' LE

/** Parse one RMB1 record — same layout as lib/mujoco.ts unpackMesh (dashboard/tools/build_twin_model.py pack). */
export function unpackMesh(buf, offset, length) {
  const dv = new DataView(buf, offset, length)
  if (dv.getUint32(0, true) !== MESH_MAGIC) throw new Error('bad mesh magic')
  const nv = dv.getUint32(4, true), nf = dv.getUint32(8, true), itype = dv.getUint8(12)
  const vOff = offset + 16
  const vertices = new Float32Array(buf.slice(vOff, vOff + nv * 12))
  const iOff = vOff + nv * 12
  const indices = itype === 2 ? new Uint16Array(buf.slice(iOff, iOff + nf * 6)) : new Uint32Array(buf.slice(iOff, iOff + nf * 12))
  return { vertices, indices }
}

/** Load geoms.json + meshes.bin from `base` (…/model/). Returns { geoms, geometries: Map(name → BufferGeometry) }. */
export async function loadModel(base) {
  const geomsJ = await fetch(`${base}geoms.json`).then((r) => { if (!r.ok) throw new Error(`geoms.json ${r.status}`); return r.json() })
  const pack = await fetch(`${base}${geomsJ.pack}?v=${geomsJ.sha}`).then((r) => { if (!r.ok) throw new Error(`${geomsJ.pack} ${r.status}`); return r.arrayBuffer() })
  const geometries = new Map()
  for (const name of geomsJ.meshes) {
    const [off, len] = geomsJ.offsets[name]
    const m = unpackMesh(pack, off, len)
    const g = new THREE.BufferGeometry()
    g.setAttribute('position', new THREE.BufferAttribute(m.vertices, 3))
    g.setIndex(new THREE.BufferAttribute(m.indices, 1))
    g.computeVertexNormals()
    geometries.set(name, g)
  }
  return { geoms: geomsJ, geometries, bytes: pack.byteLength }
}

/** Build a scene: one Group per body (by name), meshes attached at their MJCF pos/quat. `style` = 'studio' | 'cockpit'. */
export function buildRobot(model, opts = {}) {
  const root = new THREE.Group()
  const bodies = new Map()
  const white = opts.shell ?? 0xf4f2ec
  for (const g of model.geoms.geoms) {
    let grp = bodies.get(g.body)
    if (!grp) { grp = new THREE.Group(); grp.name = g.body; bodies.set(g.body, grp); root.add(grp) }
    const geo = model.geometries.get(g.mesh); if (!geo) continue
    const [r, gg, b, a] = g.rgba
    const isWhite = r > 0.9 && gg > 0.9 && b > 0.9
    const isLens = a < 1
    const mat = new THREE.MeshPhysicalMaterial({
      color: isWhite ? new THREE.Color(white) : new THREE.Color(r, gg, b),
      roughness: isWhite ? 0.38 : isLens ? 0.05 : 0.55, metalness: isWhite ? 0 : isLens ? 0.1 : 0.25,
      clearcoat: isWhite ? 0.35 : 0, clearcoatRoughness: 0.35,
      transparent: isLens, opacity: isLens ? 0.55 : 1, transmission: isLens ? 0.4 : 0,
    })
    const mesh = new THREE.Mesh(geo, mat)
    mesh.castShadow = true; mesh.receiveShadow = true
    mesh.position.set(g.pos[0], g.pos[1], g.pos[2])
    mesh.quaternion.set(g.quat[1], g.quat[2], g.quat[3], g.quat[0]) // MuJoCo wxyz → three xyzw
    grp.add(mesh)
  }
  return { root, bodies }
}

/** Apply one pose frame: frames[i] = [x,y,z,qw,qx,qy,qz] per body in poses.bodies order. Bodies not in the frame stay. */
export function applyFrame(robot, poses, i) {
  const f = poses.frames[Math.max(0, Math.min(poses.frames.length - 1, i))]
  poses.bodies.forEach((name, k) => {
    const grp = robot.bodies.get(name); if (!grp) return
    const o = k * 7
    grp.position.set(f[o], f[o + 1], f[o + 2]); grp.quaternion.set(f[o + 4], f[o + 5], f[o + 6], f[o + 3])
  })
}

/** Studio: neutral key/fill/rim, soft ground shadow, transparent background. Camera looks at the head from the front-right. */
export function makeStage(canvas, { width, height, alpha = true, dpr = 1, shadows = true } = {}) {
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha, powerPreference: 'high-performance', preserveDrawingBuffer: true })
  renderer.setPixelRatio(dpr); renderer.setSize(width, height, false)
  renderer.shadowMap.enabled = shadows; renderer.shadowMap.type = THREE.PCFSoftShadowMap
  renderer.toneMapping = THREE.ACESFilmicToneMapping; renderer.toneMappingExposure = 1.05
  renderer.outputColorSpace = THREE.SRGBColorSpace
  renderer.setClearColor(0x000000, 0)
  const scene = new THREE.Scene()
  const cam = new THREE.PerspectiveCamera(28, width / height, 0.02, 10); cam.up.set(0, 0, 1)
  scene.add(new THREE.HemisphereLight(0xffffff, 0x8a8478, 0.9))
  const key = new THREE.DirectionalLight(0xfff4e6, 2.2); key.position.set(0.7, -0.6, 1.1); key.castShadow = shadows
  key.shadow.mapSize.set(2048, 2048); key.shadow.camera.near = 0.05; key.shadow.camera.far = 4; key.shadow.bias = -0.0005; key.shadow.radius = 4
  for (const k of ['left', 'right', 'top', 'bottom']) key.shadow.camera[k] = k === 'left' || k === 'bottom' ? -0.35 : 0.35
  scene.add(key)
  const fill = new THREE.DirectionalLight(0xdde9ff, 0.7); fill.position.set(-0.8, 0.5, 0.5); scene.add(fill)
  const rim = new THREE.DirectionalLight(0xffffff, 0.6); rim.position.set(-0.2, 0.9, 0.9); scene.add(rim)
  // ground: shadow-only disc (the robot's real footprint ≈ Ø 0.16 m; the disc is just where the shadow lands)
  const ground = new THREE.Mesh(new THREE.CircleGeometry(0.5, 72), new THREE.ShadowMaterial({ opacity: 0.22 }))
  ground.receiveShadow = true; ground.position.z = -0.0004; scene.add(ground)
  const orbit = { yaw: 0.62, pitch: 0.28, dist: 0.58, target: new THREE.Vector3(0, 0, 0.145) }
  const look = () => {
    const { yaw, pitch, dist, target } = orbit
    cam.position.set(target.x + dist * Math.cos(pitch) * Math.cos(yaw), target.y + dist * Math.cos(pitch) * Math.sin(yaw), target.z + dist * Math.sin(pitch))
    cam.lookAt(target)
  }
  look()
  const resize = (w, h) => { renderer.setSize(w, h, false); cam.aspect = w / h; cam.updateProjectionMatrix() }
  return { renderer, scene, cam, orbit, look, resize, render: () => renderer.render(scene, cam) }
}
