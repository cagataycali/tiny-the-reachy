// Vendor the MuJoCo engine (mujoco.js + mujoco.wasm) into public/mujoco as the same-origin FALLBACK for
// src/lib/mujoco.ts (primary = jsDelivr). Not committed (10 MB): runs on postinstall. Source: the
// @mujoco/mujoco npm package (Apache-2.0, Google DeepMind), copied unmodified.
import { cpSync, existsSync, mkdirSync, writeFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
const root = join(dirname(fileURLToPath(import.meta.url)), '..')
const pkg = join(root, 'node_modules/@mujoco/mujoco')
const out = join(root, 'public/mujoco')
if (!existsSync(pkg)) { console.warn('vendor: @mujoco/mujoco not installed — CDN-only twin'); process.exit(0) }
mkdirSync(out, { recursive: true })
for (const f of ['mujoco.js', 'mujoco.wasm']) cpSync(join(pkg, f), join(out, f))
writeFileSync(join(out, 'LICENSE.note'), '@mujoco/mujoco — MuJoCo JavaScript/WebAssembly bindings, Copyright Google DeepMind, Apache-2.0.\nVendored unmodified by scripts/vendor.mjs. https://github.com/google-deepmind/mujoco\n')
console.log('vendor: mujoco.js + mujoco.wasm → public/mujoco')
