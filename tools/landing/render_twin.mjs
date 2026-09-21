// render_twin.mjs — headless render of TINY's real geometry at real recorded poses (landing assets).
// usage: node tools/landing/render_twin.mjs still  <move> <frame> <out.webp> [w] [h] [extra query e.g. "yaw=0.6&pitch=0.3"]
//        node tools/landing/render_twin.mjs seq    <move> <outdir> <n> [w] [h] [extra]   — n frames evenly over the move → 00..n-1.webp (RESUME=1 skips frames written in the last hour; SEQ_FROM/SEQ_TO = pose index range, default the whole move)
//        node tools/landing/render_twin.mjs probe  <move> <frame> <out.png> [w] [h] [extra]   — quick png for choosing a view
// Serves the worktree root on a random port (python http.server), opens tools/landing/twin.html in headless Chrome (WebGL via
// SwiftShader), screenshots the transparent canvas, converts to WebP with sharp. Prints the head euler for the frame drawn.
import { spawn } from 'node:child_process'
import { existsSync, mkdirSync, statSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { chromium } from '/Users/cagatay/.tiny/npm/node_modules/playwright/index.mjs'
import sharp from '/Users/cagatay/.tiny/npm/node_modules/sharp/dist/index.mjs'

const ROOT = resolve(new URL('.', import.meta.url).pathname, '../..')
const [mode, move, a3, a4, wArg, hArg, extra] = process.argv.slice(2)
const W = +(wArg || 1600), H = +(hArg || 1200)
const port = 8900 + Math.floor(Math.random() * 90)
const srv = spawn('python3', ['-m', 'http.server', String(port), '--bind', '127.0.0.1'], { cwd: ROOT, stdio: 'ignore' })
await new Promise((r) => setTimeout(r, 700))
const browser = await chromium.launch({ headless: true, args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] })
try {
  const page = await browser.newPage({ viewport: { width: W, height: H }, deviceScaleFactor: 1 })
  page.on('console', (m) => { if (m.type() === 'error') console.error('[page]', m.text()) })
  page.on('pageerror', (e) => console.error('[pageerror]', e.message))
  const url = `http://127.0.0.1:${port}/tools/landing/twin.html?move=${move}&w=${W}&h=${H}${extra ? '&' + extra : ''}`
  await page.goto(url); await page.waitForFunction(() => window.__ready === true, null, { timeout: 240000 })
  const info = await page.evaluate(() => ({ ...window.__model, frames: window.__poses.frames.length, duration: window.__poses.duration }))
  console.log('model', JSON.stringify(info))
  const shot = async (frame, out) => {
    const head = await page.evaluate((i) => window.__draw(i), frame)
    // full-page clip, not locator.screenshot: the latter waits for 'element stable' and times out at 30 s when SwiftShader is busy with the VSM blur
    const png = await page.screenshot({ omitBackground: true, clip: { x: 0, y: 0, width: W, height: H }, timeout: 120000 })
    mkdirSync(dirname(out), { recursive: true })
    if (out.endsWith('.png')) await sharp(png).png().toFile(out)
    else await (process.env.NOTRIM ? sharp(png) : sharp(png).trim({ threshold: 1 })).webp({ quality: +(process.env.WEBP_Q || 88), alphaQuality: 90, effort: 5 }).toFile(out)
    console.log(out, `${(statSync(out).size / 1024).toFixed(0)} KB`, 'frame', frame, 'head', JSON.stringify(head))
  }
  if (mode === 'still' || mode === 'probe') await shot(+a3, a4)
  else if (mode === 'seq') {
    const n = +a4
    for (let k = 0; k < n; k++) { const out = `${a3}/${String(k).padStart(2, '0')}.webp`; if (process.env.RESUME && existsSync(out) && statSync(out).mtimeMs > Date.now() - 3600e3) continue; const f0 = +(process.env.SEQ_FROM || 0), f1 = process.env.SEQ_TO ? +process.env.SEQ_TO : info.frames - 1; const frame = Math.round(f0 + (k / (n - 1)) * (f1 - f0)); await shot(frame, out) }
  }
} finally { await browser.close(); srv.kill() }
