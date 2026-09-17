# Documentation design proof

These scripts test a **local static documentation build**, never the robot
cockpit. They refuse non-loopback base URLs and block non-read HTTP requests.
No tokens, hardware, microphone or camera are required. Screenshots are written
to disk; the command output is text/JSON only.

## Prepare

Use the documentation dependencies from the existing Pages workflow, plus
Playwright and axe-core in your development environment:

```sh
npm install --no-save playwright axe-core
npx playwright install chromium
mkdocs build --strict
python -m pytest tests/test_docs.py -q
```

The robot test suites are **not** prerequisites for documentation changes.
Some robot tests construct real clients even when their startup hooks are off.

## Preview with working instant navigation

Material uses the configured site URL for instant navigation. A production
build served under localhost can silently turn the navigation test into full
page reloads. Override it **in memory** for the preview, without changing
`mkdocs.yml`:

```sh
python - <<'PY'
from mkdocs.config import load_config
from mkdocs.commands.build import build
build(load_config('mkdocs.yml', site_url='http://127.0.0.1:8767/', strict=True))
PY
python -m http.server 8767 --bind 127.0.0.1 --directory site
```

Like any existing docs build, this runs the reference-generation hook. Inspect
`git diff` afterwards; never overwrite another contributor's source edits.
Use a separate terminal for the proofs:

```sh
BASE_URL=http://127.0.0.1:8767/ node docs/scripts/visual-proof.mjs
BASE_URL=http://127.0.0.1:8767/ node docs/scripts/accessibility-proof.mjs
```

`PLAYWRIGHT_MODULE` may point to an existing `playwright/index.mjs` and
`AXE_PATH` to an existing `axe-core/axe.min.js`. `PROOF_DIR` overrides the
output directory (defaults are separate directories under `/tmp`).

## What is checked

- Home, quickstart, dashboard API, environment reference and motion tool page
  at 390 / 768 / 1440 pixels in both color schemes.
- Page overflow, uncaught JavaScript errors and real Mermaid node labels.
  The visual probe retains references to Material's closed shadow roots for
  inspection; it does not change their mode or replace the renderer.
- Axe WCAG 2 A/AA and 2.1 AA rules. No violations are ignored. The report keeps
  `incomplete` entries for manual review: **zero automated violations is not a
  full accessibility certification**.
- Keyboard-selected illustrated poses, pressed states, focus outline and
  44-pixel targets; reduced-motion behavior; genuine instant navigation and
  back (the JavaScript window must survive); visible search results; mobile
  drawer; no-JavaScript fallback and a mobile 404.

## Human review and publication

Inspect the saved PNGs on an image-capable surface. Check typography, cropping,
hierarchy, control boundaries and long-page rhythm; record **who actually
looked**. A generated screenshot is not a visual review.

Keep the companion labeled as an illustration, not telemetry or a simulation.
Its buttons only change local SVG poses and a code label; they never execute
robot commands. The live dashboard and real screenshots remain separate.

After preview checks, rebuild with the production `mkdocs.yml` before releasing.
Changes to cache-versioned assets need matching config references. Keep
Material as the sole Mermaid renderer; do not load a second CDN renderer.
