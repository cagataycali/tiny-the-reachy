// Twin PiP proof (docs/DASHBOARD.md) — BASE=https://reachy.cagatay.my TOKEN=$REACHY_TOKEN node pip-proof.mjs [tag]. Never hard-code the token.
// Playwright is not a project dep: PW=<path to playwright/index.mjs> (default: the tiny npm sandbox)
const { chromium } = await import(process.env.PW || '/Users/cagatay/.tiny/npm/node_modules/playwright/index.mjs')
const BASE = process.env.BASE || 'https://reachy.cagatay.my', TOKEN = process.env.TOKEN, TAG = process.argv[2] || 'local'
const OUT = process.env.OUT || '/tmp/reachy-pip-proof'; await import('node:fs').then((fs) => fs.mkdirSync(OUT, { recursive: true }))
const checks = []; const ok = (name, cond, info = '') => { checks.push({ name, ok: !!cond, info }); console.log(`${cond ? '✓' : '✗'} ${name} ${info}`) }
const browser = await chromium.launch()
async function session(vp, mobile) {
  const ctx = await browser.newContext({ viewport: vp, isMobile: mobile, hasTouch: mobile, serviceWorkers: 'block' })
  const page = await ctx.newPage(); const errors = []; page.on('pageerror', (e) => errors.push(String(e)))
  const streams = []; page.on('request', (r) => { if (r.url().includes('/api/stream')) streams.push(r.url()) })
  await page.goto(BASE, { waitUntil: 'domcontentloaded' }); await page.waitForSelector('[data-testid=auth-gate], [data-testid=cockpit]')
  if (await page.$('[data-testid=auth-gate]')) { await page.click('.auth-links a:has-text("use a token")'); await page.fill('[data-testid=gate-token]', TOKEN); await page.click('[data-testid=gate-primary]') }
  await page.waitForSelector('[data-testid=cockpit]')
  return { ctx, page, errors, streams }
}
const box = (page, sel) => page.$eval(sel, (e) => { const r = e.getBoundingClientRect(); return { x: r.x, y: r.y, w: r.width, h: r.height } })
const attrs = (page) => page.$eval('[data-testid=pip-host]', (e) => ({ open: e.dataset.open, swapped: e.dataset.swapped, corner: e.dataset.corner, size: e.dataset.size, split: e.dataset.split }))
const overlap = (a, b) => a.x < b.x + b.w && a.x + a.w > b.x && a.y < b.y + b.h && a.y + a.h > b.y

// ── phone portrait 390×844 ──
{
  const { ctx, page, errors, streams } = await session({ width: 390, height: 844 }, true)
  await page.evaluate(() => localStorage.removeItem('reachy.pip.v1')); streams.length = 0; await page.reload({ waitUntil: 'domcontentloaded' }); await page.waitForSelector('[data-testid=pip-card]', { timeout: 15000 })
  await page.waitForFunction(() => document.querySelector('[data-testid=twin]')?.getAttribute('data-phase') === 'ready', null, { timeout: 40000 }).catch(() => {})
  await page.waitForTimeout(2500)
  let a = await attrs(page); ok('phone: PiP open, not swapped, corner tr, size S', a.open === 'true' && a.swapped === 'false' && a.corner === 'tr' && a.size === 'S', JSON.stringify(a))
  const vp = await box(page, '[data-testid=viewport]'), cam = await box(page, '[data-testid=layer-cam]'), tw = await box(page, '[data-testid=layer-twin]'), stop = await box(page, '[data-testid=stop]'), ro = await box(page, '[data-testid=pip-readout]')
  ok('phone: camera layer fills the viewport', Math.abs(cam.w - vp.w) < 3 && Math.abs(cam.h - vp.h) < 3, `${cam.w}x${cam.h} vs ${vp.w}x${vp.h}`)
  ok('phone: twin PiP ≈ 160×120 top-right', Math.abs(tw.w - 160) < 2 && Math.abs(tw.h - 120) < 2 && tw.x + tw.w > vp.x + vp.w - 14 && tw.y - vp.y < 60, JSON.stringify(tw))
  ok('phone: PiP + readout clear of STOP', !overlap(tw, stop) && !overlap(ro, stop))
  const phase = await page.$eval('[data-testid=twin]', (e) => e.getAttribute('data-phase')); ok('phone: twin ready', phase === 'ready', phase)
  const fps = await page.evaluate(() => window.__reachyTwin?.fps()); ok('phone: twin fps ≤ 30 in PiP', fps != null && fps <= 31, `fps=${fps}`)
  // readout matches /api/state
  // the robot may be moving (thinker emotes) → up to 5 attempts, readout must match one /api/state sample within 4°
  const close = (x, y) => Math.abs(x - y) < 4
  let rd, st, match = false
  for (let i = 0; i < 5 && !match; i++) {
    st = await page.evaluate(async () => (await fetch('/api/state', { headers: { authorization: 'Bearer ' + sessionStorage.getItem('reachy_token') } })).json())
    rd = await page.$eval('[data-testid=pip-readout]', (e) => ({ roll: +e.dataset.roll, pitch: +e.dataset.pitch, yaw: +e.dataset.yaw, body: +e.dataset.body, text: e.textContent }))
    match = st.head && close(rd.roll, st.head.roll) && close(rd.pitch, st.head.pitch) && close(rd.yaw, st.head.yaw) && close(rd.body, st.body_yaw)
    if (!match) await page.waitForTimeout(700)
  }
  ok('phone: readout roll/pitch/yaw/body within 4° of /api/state', match, `${JSON.stringify(rd)} vs ${JSON.stringify({ ...st.head, body: st.body_yaw, moving: st.moves_running })}`)
  ok('phone: readout shows Hz + motor mode', /Hz/.test(rd.text) && /⚙/.test(rd.text), rd.text)
  await page.screenshot({ path: `${OUT}/${TAG}-phone-pip.png` })
  // drag the handle to the bottom-left → snaps to bl and stays clear of STOP + cmdbar
  const hb = await box(page, '[data-testid=pip-handle]')
  await page.mouse.move(hb.x + 30, hb.y + hb.h / 2); await page.mouse.down(); await page.mouse.move(hb.x - 100, hb.y + 300, { steps: 8 }); await page.mouse.move(60, vp.y + vp.h - 120, { steps: 8 }); await page.mouse.up()
  await page.waitForTimeout(500); a = await attrs(page)
  const tw2 = await box(page, '[data-testid=layer-twin]'), ro2 = await box(page, '[data-testid=pip-readout]'), bar = await box(page, '.cmdbar')
  ok('phone: drag → snapped to bl', a.corner === 'bl', JSON.stringify(tw2))
  ok('phone: bl PiP clear of STOP and cmdbar', !overlap(tw2, stop) && !overlap(ro2, stop) && !overlap(ro2, bar) && tw2.x - vp.x < 14)
  const mind = await box(page, '[data-testid=mind-overlay]').catch(() => null)
  ok('phone: mind bubbles lifted above the bl PiP', !mind || mind.y + mind.h <= tw2.y + 2, mind ? `bubbles bottom ${Math.round(mind.y + mind.h)} vs pip top ${tw2.y}` : 'no overlay')
  const roClip = await page.$eval('[data-testid=pip-readout]', (e) => e.scrollHeight <= e.clientHeight + 1 && [...e.querySelectorAll('.ro-row')].every((r) => r.scrollWidth <= r.clientWidth + 1))
  ok('phone: readout text not clipped', roClip)
  await page.screenshot({ path: `${OUT}/${TAG}-phone-pip-bl.png` })
  // double-tap the PiP → swap
  await page.mouse.click(tw2.x + tw2.w / 2, tw2.y + tw2.h / 2 + 20, { clickCount: 2, delay: 80 }); await page.waitForTimeout(600); a = await attrs(page)
  const tw3 = await box(page, '[data-testid=layer-twin]'), cam3 = await box(page, '[data-testid=layer-cam]')
  ok('phone: double-tap → swapped (twin full-bleed, camera PiP)', a.swapped === 'true' && Math.abs(tw3.w - vp.w) < 3 && Math.abs(cam3.w - 160) < 2, JSON.stringify({ tw3, cam3 }))
  await page.screenshot({ path: `${OUT}/${TAG}-phone-swapped.png` })
  ok('phone: exactly one MJPEG stream opened across the swap', streams.length === 1, `streams=${streams.length}`)
  // X swaps back, T closes → chip, twin paused; T reopens
  await page.keyboard.press('x'); await page.waitForTimeout(400); a = await attrs(page); ok('phone: X → unswapped', a.swapped === 'false')
  await page.keyboard.press('t'); await page.waitForTimeout(400); a = await attrs(page)
  const chip = await page.$('[data-testid=pip-chip]'); const paused = await page.evaluate(() => window.__reachyTwin?.paused())
  ok('phone: T → closed, chip shown, twin paused', a.open === 'false' && !!chip && paused === true, `paused=${paused}`)
  await page.screenshot({ path: `${OUT}/${TAG}-phone-closed.png` })
  await page.click('[data-testid=pip-chip]'); await page.waitForTimeout(400); a = await attrs(page); ok('phone: chip → reopened', a.open === 'true')
  // persist across reload
  await page.reload({ waitUntil: 'domcontentloaded' }); await page.waitForSelector('[data-testid=pip-card]'); a = await attrs(page)
  ok('phone: prefs persisted (corner bl, open)', a.corner === 'bl' && a.open === 'true', JSON.stringify(a))
  ok('phone: 0 page errors', errors.length === 0, errors.join(' | '))
  await ctx.close()
}
// ── phone landscape 844×390 → split ──
{
  const { ctx, page, errors } = await session({ width: 844, height: 390 }, true)
  await page.evaluate(() => localStorage.removeItem('reachy.pip.v1')); await page.reload({ waitUntil: 'domcontentloaded' }); await page.waitForSelector('[data-testid=pip-card]'); await page.waitForTimeout(2500)
  const a = await attrs(page); const vp = await box(page, '[data-testid=viewport]'), cam = await box(page, '[data-testid=layer-cam]'), tw = await box(page, '[data-testid=layer-twin]')
  ok('landscape: split side-by-side', a.split === 'true' && Math.abs(cam.w - vp.w / 2) < 3 && Math.abs(tw.w - vp.w / 2) < 3 && tw.x > cam.x, JSON.stringify({ cam, tw }))
  await page.screenshot({ path: `${OUT}/${TAG}-phone-landscape.png` })
  ok('landscape: 0 page errors', errors.length === 0, errors.join(' | ')); await ctx.close()
}
// ── desktop 1440×900 ──
{
  const { ctx, page, errors } = await session({ width: 1440, height: 900 }, false)
  await page.evaluate(() => localStorage.removeItem('reachy.pip.v1')); await page.reload({ waitUntil: 'domcontentloaded' }); await page.waitForSelector('[data-testid=pip-card]')
  await page.waitForFunction(() => document.querySelector('[data-testid=twin]')?.getAttribute('data-phase') === 'ready', null, { timeout: 40000 }).catch(() => {}); await page.waitForTimeout(2000)
  let a = await attrs(page); const tw = await box(page, '[data-testid=layer-twin]')
  ok('desktop: size M 320×240', a.size === 'M' && Math.abs(tw.w - 320) < 2 && Math.abs(tw.h - 240) < 2, JSON.stringify(tw))
  await page.screenshot({ path: `${OUT}/${TAG}-desktop-pip.png` })
  await page.click('[data-testid=pip-size]'); await page.waitForTimeout(500); a = await attrs(page); const twL = await box(page, '[data-testid=layer-twin]')
  ok('desktop: size button → L 480×360', a.size === 'L' && Math.abs(twL.w - 480) < 2, JSON.stringify(twL))
  await page.screenshot({ path: `${OUT}/${TAG}-desktop-pip-L.png` })
  // wheel zoom inside the twin changes the camera distance (orbit) without errors
  await page.mouse.move(twL.x + twL.w / 2, twL.y + twL.h / 2); await page.mouse.wheel(0, -300); await page.waitForTimeout(300)
  await page.click('[data-testid=view-toggle]'); await page.waitForTimeout(600); a = await attrs(page); ok('desktop: view-toggle chip → swapped', a.swapped === 'true')
  await page.screenshot({ path: `${OUT}/${TAG}-desktop-swapped.png` })
  ok('desktop: 0 page errors', errors.length === 0, errors.join(' | ')); await ctx.close()
}
await browser.close()
const bad = checks.filter((c) => !c.ok); console.log(`\n${checks.length - bad.length}/${checks.length} checks passed`); process.exit(bad.length ? 1 : 0)
