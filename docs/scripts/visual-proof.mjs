/** DOM-only visual regression probe. Screenshots go to disk, never tool output.
 * npm install --no-save playwright; BASE_URL=http://127.0.0.1:8767/ node docs/scripts/visual-proof.mjs
 * PLAYWRIGHT_MODULE can point to an existing Playwright install. No robot calls.
 */
import fs from 'node:fs/promises';
import path from 'node:path';
import assert from 'node:assert/strict';
const {chromium} = await import(process.env.PLAYWRIGHT_MODULE || 'playwright');
const base = new URL(process.env.BASE_URL || 'http://127.0.0.1:8767/');
const out = process.env.PROOF_DIR || '/tmp/reachy-docs-proof';
await fs.mkdir(out, {recursive: true});
const browser = await chromium.launch({headless: true});
const results = [];
try {
  for (const width of [390, 768, 1440]) {
    const page = await browser.newPage({viewport: {width, height: 900}});
    const errors = [];
    page.on('pageerror', e => errors.push(e.message));
    // Allow only documentation dependencies, never a robot/private endpoint.
    await page.route('**/*', route => {
      const url = new URL(route.request().url());
      const allowed = url.origin === base.origin ||
        ['unpkg.com', 'fonts.googleapis.com', 'fonts.gstatic.com', 'github.com'].includes(url.hostname);
      return allowed ? route.continue() : route.abort();
    });
    // Keep test references WITHOUT changing shadow mode or rendering behaviour.
    await page.addInitScript(() => {
      window.__proofShadows = [];
      const attach = Element.prototype.attachShadow;
      Element.prototype.attachShadow = function (options) {
        const root = attach.call(this, options);
        window.__proofShadows.push({host: this, root});
        return root;
      };
    });
    for (const [name, url] of [['home', ''], ['manual', 'start/quickstart/'], ['api', 'reference/api/'], ['environment', 'reference/env/'], ['motion', 'reference/tools/reachy_motion/']]) {
      await page.goto(new URL(url, base).href, {waitUntil: 'networkidle'});
      if (name === 'home') await page.waitForFunction(() =>
        window.__proofShadows.some(({host, root}) => host.isConnected && root.querySelector('svg')));
      for (const scheme of ['default', 'slate']) {
        await page.evaluate(s => document.body.setAttribute('data-md-color-scheme', s), scheme);
        await page.waitForTimeout(150);
        const row = await page.evaluate(() => ({
          overflow: document.documentElement.scrollWidth - innerWidth,
          diagramCount: window.__proofShadows.filter(({host, root}) => host.isConnected && root.querySelector('svg')).length,
          diagrams: window.__proofShadows.filter(({host}) => host.isConnected).map(({host, root}) => ({
            width: host.getBoundingClientRect().width, height: host.getBoundingClientRect().height,
            labels: [...root.querySelectorAll('.nodeLabel')].map(e => e.textContent)
          })),
          h1: document.querySelector('h1')?.innerText,
        }));
        results.push({name, width, scheme, ...row, errors: [...errors]});
        await page.screenshot({path: path.join(out, `${name}-${width}-${scheme}.png`), fullPage: true});
        assert.equal(row.overflow, 0, `${name} ${width} ${scheme}: page overflow`);
        assert.equal(errors.length, 0, errors.join('\n'));
        if (name === 'home') {
          assert.equal(row.diagramCount, 1, 'one native Material diagram');
          assert(row.diagrams[0].height > 50, 'diagram has rendered height');
          assert(row.diagrams[0].labels.length > 5, 'actual diagram nodes, not an error SVG');
        }
      }
    }
    await page.close();
  }
} finally {
  await browser.close();
  await fs.writeFile(path.join(out, 'proof.json'), JSON.stringify(results, null, 2));
}
console.log(JSON.stringify({checks: results.length, output: out, errors: results.flatMap(r=>r.errors)}));
