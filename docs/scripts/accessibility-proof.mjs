/** DOM-only accessibility/interaction checks. Does not visit any robot.
 * Serve a strict build with site_url=BASE_URL (needed for genuine instant nav).
 * npm install --no-save playwright axe-core
 * BASE_URL=http://127.0.0.1:8767/ node docs/scripts/accessibility-proof.mjs
 * Existing installs: PLAYWRIGHT_MODULE and AXE_PATH. Outputs JSON + PNG files.
 */
import fs from 'node:fs/promises';
import path from 'node:path';
import {createRequire} from 'node:module';
import assert from 'node:assert/strict';
const require = createRequire(import.meta.url);
const {chromium} = await import(process.env.PLAYWRIGHT_MODULE || 'playwright');
const axePath = process.env.AXE_PATH || require.resolve('axe-core/axe.min.js');
const base = new URL(process.env.BASE_URL || 'http://127.0.0.1:8767/');
assert(['127.0.0.1', 'localhost', '[::1]'].includes(base.hostname), 'BASE_URL must be a local static docs preview');
assert(base.protocol === 'http:' && !base.username && !base.password, 'Use an HTTP preview without credentials');
const out = process.env.PROOF_DIR || '/tmp/reachy-docs-accessibility';
await fs.mkdir(out, {recursive: true});
const browser = await chromium.launch();
const reports = [];
async function makePage(options = {}) {
  const page = await browser.newPage(options);
  await page.route('**/*', route => {
    const url = new URL(route.request().url());
      if (!['GET', 'HEAD'].includes(route.request().method())) return route.abort();
    return url.origin === base.origin || ['unpkg.com', 'fonts.googleapis.com', 'fonts.gstatic.com', 'github.com'].includes(url.hostname)
      ? route.continue() : route.abort();
  });
  return page;
}
try {
  for (const width of [390, 768, 1440]) {
    const page = await makePage({viewport: {width, height: 900}, reducedMotion: 'reduce'});
    const errors = []; page.on('pageerror', e => errors.push(e.message));
    for (const url of ['', 'start/quickstart/', 'reference/api/', 'reference/env/', 'reference/tools/reachy_motion/']) {
      await page.goto(new URL(url, base).href, {waitUntil: 'networkidle'});
      await page.addScriptTag({path: axePath});
      for (const scheme of ['default', 'slate']) {
        await page.evaluate(s => document.body.setAttribute('data-md-color-scheme', s), scheme);
        const result = await page.evaluate(async () => {
          const result = await window.axe.run(document, {runOnly: {type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21aa']}});
          return {
            violations: result.violations.map(v => ({id: v.id, nodes: v.nodes.map(n => ({target: n.target, message: n.failureSummary}))})),
            // Manual review items are kept, NOT counted as passed checks.
            incomplete: result.incomplete.map(v => ({id: v.id, count: v.nodes.length})),
            overflow: document.documentElement.scrollWidth - innerWidth,
          };
        });
        reports.push({test: 'axe', width, url, scheme, ...result});
        assert.deepEqual(result.violations, [], `${width} ${url} ${scheme}`);
        assert.equal(result.overflow, 0);
      }
    }
    await page.goto(base.href, {waitUntil: 'networkidle'});
    await page.waitForSelector('.rh-hero > .rh-companion');
    assert.equal(await page.getByRole('heading', {level: 1, name: "I'm TINY. I live on the desk.", exact: true}).count(), 1);
    const listening = page.getByRole('button', {name: 'Listening', exact: true});
    await listening.focus(); await page.keyboard.press('Enter');
    assert.equal(await listening.getAttribute('aria-pressed'), 'true');
    assert.equal(await page.getByRole('button', {name: 'Curious', exact: true}).getAttribute('aria-pressed'), 'false');
    assert.equal(await page.locator('[data-pose-code]').textContent(), 'reachy_antennas(45, 45)');
    const motion = await page.locator('.rh-robot-head').evaluate(e => getComputedStyle(e).transitionDuration);
    assert.equal(motion, '0s');
    assert((await listening.boundingBox()).height >= 44);
    const focus = await listening.evaluate(e => ({color: getComputedStyle(e).outlineColor, width: getComputedStyle(e).outlineWidth, style: getComputedStyle(e).outlineStyle}));
    assert.equal(focus.style, 'solid'); assert(parseFloat(focus.width) >= 2);
    reports.push({test: 'keyboard gesture / 44px target / reduced motion', width, motion, focus});

    // Don't infer instant nav from the URL alone: the same window must survive.
    await page.evaluate(() => { window.__proofNavigation = 'same-window'; });
    await page.getByRole('link', {name: 'Run it yourself', exact: true}).click();
    await page.waitForFunction(() => document.querySelector('h1')?.textContent.toLowerCase().includes('quickstart'));
    assert.equal(await page.evaluate(() => window.__proofNavigation), 'same-window');
    assert.equal(await page.locator('.rh-companion').count(), 0);
    await page.goBack();
    await page.waitForSelector('.rh-hero > .rh-companion');
    assert.equal(await page.locator('.rh-companion').count(), 1);
    await page.getByRole('button', {name: 'Resting', exact: true}).click();
    assert.equal(await page.locator('[data-pose-code]').textContent(), 'reachy_home()');
    reports.push({test: 'instant navigation / back / no duplicate companion', width});

    // A visible search result, not merely detached/hidden result markup.
    await page.evaluate(() => scrollTo(0, 0));
    await page.waitForFunction(() => scrollY === 0);
    await page.waitForTimeout(300);
    if (width < 960) {
      await page.locator('.md-header__button[for="__search"]').click();
    } else {
      await page.getByPlaceholder('Search').click();
    }
    await page.getByPlaceholder('Search').fill('tracking');
    await page.waitForFunction(() => document.querySelector('#__search').checked && document.querySelector('.md-search-result__item')?.getBoundingClientRect().height > 0).catch(async error => {
      console.error(await page.evaluate(() => ({width: innerWidth, checked: document.querySelector('#__search').checked, active: document.activeElement.outerHTML, meta: document.querySelector('.md-search-result__meta')?.textContent})));
      throw error;
    });
    reports.push({test: 'visible search after instant navigation', width, results: await page.locator('.md-search-result__item').count()});
    await page.keyboard.press('Escape');
    if (width < 1220) {
      await page.locator('.md-header__button[for="__drawer"]').click();
      await page.waitForFunction(() => document.querySelector('#__drawer').checked);
      const nav = page.locator('.md-sidebar--primary');
      assert(await nav.isVisible());
      reports.push({test: 'mobile drawer', width, open: true});
      await page.locator('.md-overlay').click({position: {x: width - 10, y: 200}});
      await page.waitForFunction(() => !document.querySelector('#__drawer').checked);
    }
    assert.deepEqual(errors, []);
    await page.screenshot({path: path.join(out, `home-reduced-${width}.png`), fullPage: true});
    await page.close();
  }
  const nojs = await makePage({javaScriptEnabled: false, viewport: {width: 390, height: 844}});
  await nojs.goto(base.href);
  assert(await nojs.locator('.rh-companion').isVisible());
  assert(!(await nojs.locator('.rh-pose-controls').isVisible()));
  assert.equal(await nojs.evaluate(() => document.documentElement.scrollWidth - innerWidth), 0);
  await nojs.screenshot({path: path.join(out, 'home-no-js.png'), fullPage: true});
  reports.push({test: 'static illustration, no dead controls, no-JS mobile overflow', passed: true});
  await nojs.close();
  const lost = await makePage({viewport: {width: 390, height: 844}});
  await lost.goto(new URL('404.html', base).href);
  assert.equal(await lost.locator('h1').count(), 1);
  assert.equal(await lost.evaluate(() => document.documentElement.scrollWidth - innerWidth), 0);
  await lost.screenshot({path: path.join(out, '404-mobile.png'), fullPage: true});
  reports.push({test: '404 heading / mobile layout', passed: true});
  await lost.close();
} finally {
  await browser.close();
  await fs.writeFile(path.join(out, 'accessibility.json'), JSON.stringify(reports, null, 2));
}
console.log(JSON.stringify({passed: reports.length, out, note: 'Automated checks only; axe incomplete entries require review.'}));
