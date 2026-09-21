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
export async function loadModel(base, { yieldEach = false } = {}) {
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
    if (yieldEach) await new Promise((r) => setTimeout(r, 0)) // one mesh per task: the 1.1 MB unpack never becomes a >50 ms long task on the page
  }
  return { geoms: geomsJ, geometries, bytes: pack.byteLength }
}

/** Look-dev: one material per real part family, keyed by the MJCF mesh name + its rgba (Pollen's materials).
 *  The real robot: glossy cream 3D-printed shell · matte dark-grey printed foot/plates · black lens rings + glass · black
 *  spring-steel antenna coils · steel Stewart rods and balls · a bearing ring · Dynamixel XL-330 cases · one orange LED cap. */
export const SHELL = 0xf5f2ec
function materialFor(g, shell) {
  const [r, gg, b, a] = g.rgba, m = g.mesh
  const P = (o) => new THREE.MeshPhysicalMaterial(Object.assign({ color: new THREE.Color(r, gg, b), roughness: .55, metalness: 0 }, o))
  if (r > 0.9 && gg > 0.9 && b > 0.9) return P({ color: new THREE.Color(shell), roughness: .30, clearcoat: .7, clearcoatRoughness: .18, specularIntensity: .55 }) // printed shell, sprayed gloss
  if (a < 1) return P({ color: new THREE.Color(0x9fb4c4), roughness: .03, metalness: 0, transmission: .92, ior: 1.5, thickness: .004, transparent: true, opacity: 1 }) // lens glass
  if (/lens_cap/.test(m)) return P({ color: new THREE.Color(0x0b0c0e), roughness: .18, clearcoat: .9, clearcoatRoughness: .12 }) // black lens rings
  if (m === 'antenna') return P({ color: new THREE.Color(0x101113), roughness: .38, metalness: .55 }) // coated spring steel coil
  if (/stewart_link_rod/.test(m)) return P({ color: new THREE.Color(0xd9dde2), roughness: .28, metalness: 1 }) // steel rods
  if (/stewart_link_ball/.test(m)) return P({ color: new THREE.Color(0xb9bec6), roughness: .22, metalness: 1 }) // ball joints
  if (/bearing/.test(m)) return P({ color: new THREE.Color(0xc7cfd6), roughness: .34, metalness: .95 }) // 85×110 bearing ring
  if (/led_cap/.test(m)) return P({ roughness: .45, clearcoat: .4, emissive: new THREE.Color(r, gg, b), emissiveIntensity: .12 }) // Dynamixel LED cap
  if (/speaker|glasses_dolder/.test(m)) return P({ roughness: .9 }) // rubber / matte
  if (/3dprint|arducam_carter|stewart_arm/.test(m)) return P({ roughness: .82, metalness: 0 }) // matte dark PLA
  if (/^dc15_|^phs_|^bts2|^b3b/.test(m)) return P({ roughness: .5, metalness: .05, clearcoat: .15 }) // motor cases, screws
  if (/antenna_interface/.test(m)) return P({ roughness: .3, metalness: .9 })
  return P({ roughness: .55, metalness: .05 })
}

/** Build a scene: one Group per body (by name), meshes attached at their MJCF pos/quat. */
export function buildRobot(model, opts = {}) {
  const root = new THREE.Group()
  const bodies = new Map()
  const shell = opts.shell ?? SHELL
  for (const g of model.geoms.geoms) {
    let grp = bodies.get(g.body)
    if (!grp) { grp = new THREE.Group(); grp.name = g.body; bodies.set(g.body, grp); root.add(grp) }
    const geo = model.geometries.get(g.mesh); if (!geo) continue
    const mesh = new THREE.Mesh(geo, materialFor(g, shell))
    mesh.castShadow = g.rgba[3] >= 1; mesh.receiveShadow = true
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

/** The camera views every asset shares (still, frame sequences, body layers, live hero) — one lens for the whole page.
 *  fov 18° = a ~135 mm-equivalent portrait lens: less perspective on the head, the antennas stay parallel. */
export const FOV = 18
export const VIEWS = {
  hero:    { yaw: 0.62, pitch: 0.16, dist: 1.85, target: [0, 0.06, 0.19] },
  emotion: { yaw: 0.30, pitch: 0.14, dist: 2.0, target: [0, 0.02, 0.205] },
  body:    { yaw: 0.55, pitch: 0.14, dist: 2.0, target: [0, 0.0, 0.205] },
}

/** A small photographic room baked to a PMREM: one big softbox overhead-front, a cool fill panel left, a warm bounce right,
 *  a dim floor. Built from geometry (no HDR download) so the offline renderer and the live page light the shell identically. */
export function makeEnvironment(renderer) {
  const room = new THREE.Scene()
  room.background = new THREE.Color(0x1c1d20)
  const panel = (w, h, color, intensity, pos, look) => {
    const m = new THREE.Mesh(new THREE.PlaneGeometry(w, h), new THREE.MeshBasicMaterial({ color: new THREE.Color(color).multiplyScalar(intensity), side: THREE.DoubleSide }))
    m.position.set(...pos); m.lookAt(...look); room.add(m)
  }
  panel(3.2, 2.2, 0xfff6ea, 6.0, [0.6, -1.4, 2.6], [0, 0, 0.2])   // key softbox, high front-right
  panel(2.6, 3.0, 0xdbe6ff, 2.2, [-3.0, 0.8, 1.0], [0, 0, 0.2])   // cool fill, left
  panel(2.0, 2.4, 0xffe9d2, 1.4, [2.4, 2.6, 0.6], [0, 0, 0.2])    // warm bounce, back-right
  panel(3.0, 1.2, 0xffffff, 1.8, [0, 3.2, 1.6], [0, 0, 0.2])      // rim strip behind
  panel(6, 6, 0x6b6a66, 0.5, [0, 0, -0.3], [0, 0, 1])              // floor bounce
  const pmrem = new THREE.PMREMGenerator(renderer)
  const env = pmrem.fromScene(room, 0.035).texture
  pmrem.dispose()
  return env
}

/** Studio: image-based light from makeEnvironment + one soft key for the contact shadow, transparent background. */
export function makeStage(canvas, { width, height, alpha = true, dpr = 1, shadows = true, view = 'hero' } = {}) {
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha, powerPreference: 'high-performance', preserveDrawingBuffer: true })
  renderer.setPixelRatio(dpr); renderer.setSize(width, height, false)
  renderer.shadowMap.enabled = shadows; renderer.shadowMap.type = THREE.VSMShadowMap
  renderer.toneMapping = THREE.ACESFilmicToneMapping; renderer.toneMappingExposure = 1.12
  renderer.outputColorSpace = THREE.SRGBColorSpace
  renderer.setClearColor(0x000000, 0)
  const scene = new THREE.Scene()
  scene.environment = makeEnvironment(renderer); scene.environmentIntensity = 1.0
  const cam = new THREE.PerspectiveCamera(FOV, width / height, 0.05, 12); cam.up.set(0, 0, 1)
  // the key: matches the softbox direction, exists mainly for the contact shadow (VSM, wide blur = soft penumbra)
  const key = new THREE.DirectionalLight(0xfff4e6, 1.1); key.position.set(0.45, -0.9, 1.6); key.castShadow = shadows
  key.shadow.mapSize.set(2048, 2048); key.shadow.camera.near = 0.2; key.shadow.camera.far = 4; key.shadow.bias = -0.0002; key.shadow.normalBias = 0.002
  key.shadow.radius = 9; key.shadow.blurSamples = 24
  for (const k of ['left', 'right', 'top', 'bottom']) key.shadow.camera[k] = k === 'left' || k === 'bottom' ? -0.4 : 0.4
  scene.add(key)
  const rim = new THREE.DirectionalLight(0xffffff, 0.35); rim.position.set(-0.3, 1.0, 0.8); scene.add(rim)
  // ground: shadow-only disc + a soft contact-occlusion gradient under the foot (Ø 0.16 m real footprint)
  const ground = new THREE.Mesh(new THREE.CircleGeometry(0.7, 72), new THREE.ShadowMaterial({ opacity: 0.28 }))
  ground.receiveShadow = true; ground.position.z = -0.0006; scene.add(ground)
  const ao = new THREE.Mesh(new THREE.CircleGeometry(0.115, 64), new THREE.MeshBasicMaterial({ map: contactTexture(), transparent: true, depthWrite: false, opacity: 0.55 }))
  ao.position.z = -0.0003; if (shadows) scene.add(ao) // noshadow=1 layers (THE BODY) carry no ground at all
  const v = VIEWS[view] || VIEWS.hero
  const orbit = { yaw: v.yaw, pitch: v.pitch, dist: v.dist, target: new THREE.Vector3(...v.target) }
  const look = () => {
    const { yaw, pitch, dist, target } = orbit
    cam.position.set(target.x + dist * Math.cos(pitch) * Math.cos(yaw), target.y + dist * Math.cos(pitch) * Math.sin(yaw), target.z + dist * Math.sin(pitch))
    cam.lookAt(target)
  }
  look()
  const resize = (w, h) => { renderer.setSize(w, h, false); cam.aspect = w / h; cam.updateProjectionMatrix() }
  return { renderer, scene, cam, orbit, look, resize, render: () => renderer.render(scene, cam) }
}

function contactTexture() {
  const c = document.createElement('canvas'); c.width = c.height = 256
  const x = c.getContext('2d'), g = x.createRadialGradient(128, 128, 0, 128, 128, 128)
  g.addColorStop(0, 'rgba(20,18,16,1)'); g.addColorStop(0.45, 'rgba(20,18,16,.55)'); g.addColorStop(1, 'rgba(20,18,16,0)')
  x.fillStyle = g; x.fillRect(0, 0, 256, 256)
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; return t
}
