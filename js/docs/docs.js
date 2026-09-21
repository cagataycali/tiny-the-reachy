/* docs.js — progressive enhancers for the docs chapter (every page except the landing). No dependencies.
   Opt-in by markup; everything degrades to the plain markup without JS. Re-runs on Material's instant navigation (document$).
   1. <div class="cards" markdown> table </div>            → grid of cards (col 1 title · col 2 where · last col body; the row's last link = the card's link)
   2. h2 "3. Talk to it" (≥ 3 of them)                     → numbered step rail
   3. <div class="filterable" data-id="env" data-key="1" markdown> table </div>
                                                            → filter box + `#env-NAME` row anchors on column data-key (1-based) + status/gate/method pills
      (table cells: `robot` `sim` `code` `stale` words in a "status" column → pills; GET/POST/… in a "method" column → method pills)
   4. reference/tools/*: every `## tool_name` block          → tool card (signature · envelope facts pulled from the text · "fires while speaking")
   5. <figure class="anatomy" data-anatomy="body" data-base="../../"> → exploded twin layers with hotspots (ANATOMY below)
   6. <div class="emotions" data-src="../../js/landing/emotions.json"> → the recorded-move library, filterable
   7. .mermaid wider than its box → scroll hint · 8. first-sight rise (transform only) · a11y: Material landmark/region nits */
(() => {
  const $$ = (sel, root = document) => [...root.querySelectorAll(sel)]
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]))
  const outerOf = (t) => t.closest('.md-typeset__scrollwrap') || t.closest('.md-typeset__table') || t  // Material: scrollwrap > table-wrap > table
  const slug = (s) => s.trim().replace(/[^A-Za-z0-9_.-]+/g, '-').replace(/-{2,}/g, '-').replace(/^-|-$/g, '')

  // ── 1. cards
  function cards(root) {
    for (const wrap of $$('.cards', root)) {
      const table = wrap.querySelector('table')
      if (!table || wrap.querySelector('.card')) continue
      const grid = document.createElement('div')
      grid.className = 'cards__grid'
      for (const tr of table.tBodies[0].rows) {
        const [c0, c1, ...rest] = [...tr.cells]
        const links = $$('a[href]', tr)
        const link = links.at(-1)
        const card = document.createElement(link ? 'a' : 'div')
        card.className = 'card'
        if (link) card.href = link.getAttribute('href')
        const body = rest.length ? rest.at(-1) : null
        if (body && link && body.contains(link)) { link.remove(); body.innerHTML = body.innerHTML.replace(/\s*(→|⇢)\s*$/, '') }
        card.innerHTML = `<p class="card__title">${c0.innerHTML}</p>` + (c1 ? `<p class="card__where">${c1.innerHTML}</p>` : '') + (body ? `<p class="card__body">${body.innerHTML}</p>` : '')
          + (link ? `<span class="card__go" aria-hidden="true">${esc(link.textContent.trim())} ⇢</span>` : '')
        grid.append(card)
      }
      wrap.append(grid)
      ;(table.closest('.md-typeset__scrollwrap') || table.closest('.md-typeset__table') || table).style.display = 'none'
    }
  }

  // ── 2. steps
  function steps(root) {
    const hs = $$('h2', root).filter((h) => /^\d+\s*[.·]\s/.test(h.textContent.trim()))
    if (hs.length < 3) return
    hs.forEach((h, i) => {
      const m = h.textContent.trim().match(/^(\d+)\s*[.·]\s*/)
      h.classList.add('step'); h.dataset.step = m[1]
      const t = h.firstChild
      if (t && t.nodeType === 3) t.textContent = t.textContent.replace(/^\s*\d+\s*[.·]\s*/, '')
      if (i === hs.length - 1) h.classList.add('step--last')
    })
  }

  // ── 3. filterable tables: anchors, pills, filter box
  const STATUS = [[/^(robot|proven|live)\b/i, 'robot', 'robot'], [/^sim\b/i, 'sim', 'sim'], [/^(code|inferred)\b/i, 'code', 'from code'], [/^(stale|todo|recheck)\b/i, 'stale', 'stale'],
    [/^(✅\s*)?public\b/i, 'public', 'public'], [/^(🔒\s*)?key\b/i, 'key', 'key'], [/^(🔒\s*)?owner\b/i, 'key', 'owner']]
  const METHOD = /^(GET|POST|PUT|PATCH|DELETE|WS)\b/
  function pills(table) {
    const head = [...table.tHead?.rows[0]?.cells || []].map((c) => c.textContent.trim().toLowerCase())
    const statusCol = head.findIndex((h) => h.startsWith('status') || h === 'proof' || h.startsWith('anonymous') || h === 'gate')
    const methodCol = head.findIndex((h) => h.startsWith('method') || h === 'verb')
    for (const tr of table.tBodies[0].rows) {
      if (statusCol >= 0 && tr.cells[statusCol]) {
        const td = tr.cells[statusCol], txt = td.textContent.trim()
        for (const [re, cls, label] of STATUS) if (re.test(txt)) { const rest = txt.replace(re, '').replace(/^[\s·—-]+/, ''); td.innerHTML = `<span class="pill pill--${cls}">${label}</span>${rest ? ` <span class="muted">${esc(rest)}</span>` : ''}`; break }
      }
      if (methodCol >= 0 && tr.cells[methodCol]) {
        const td = tr.cells[methodCol], txt = td.textContent.trim().toUpperCase(), m = txt.match(METHOD)
        if (m) td.innerHTML = `<span class="pill pill--method pill--${m[1].toLowerCase()}">${m[1]}</span>`
      }
    }
  }
  function filterable(root) {
    for (const wrap of $$('.filterable', root)) {
      const tables = $$('table', wrap)
      if (!tables.length || wrap.querySelector('.filter')) continue
      const id = wrap.dataset.id || 'row', keyCol = Math.max(0, (parseInt(wrap.dataset.key, 10) || 1) - 1)  // data-key = 1-based column that names the row
      let rows = 0
      for (const t of tables) {
        pills(t)
        for (const tr of t.tBodies[0].rows) {
          rows++
          const c = tr.cells[keyCol]; if (!c) continue
          c.classList.add('cell--id')
          const key = slug(c.textContent)
          if (key && !tr.id) { tr.id = `${id}-${key}`; c.innerHTML = `<a class="row-anchor" href="#${tr.id}" aria-label="link to ${esc(c.textContent.trim())}">${c.innerHTML}</a>` }
        }
      }
      if (rows > 8) {
        const box = document.createElement('div')
        box.className = 'filter'
        box.innerHTML = `<label><span class="filter__label">filter</span><input type="search" placeholder="${esc(wrap.dataset.placeholder || 'name, value, note…')}" autocomplete="off" spellcheck="false" /></label><output aria-live="polite"></output>`
        wrap.prepend(box)  // above the first group heading, so a filter that empties the first group hides its heading too
        const input = box.querySelector('input'), out = box.querySelector('output')
        const all = tables.flatMap((t) => [...t.tBodies[0].rows])
        const apply = () => {
          const q = input.value.trim().toLowerCase(); let hits = 0
          for (const tr of all) { const hit = !q || tr.textContent.toLowerCase().includes(q); tr.hidden = !hit; if (hit) hits++ }
          for (const t of tables) {
            const any = [...t.tBodies[0].rows].some((r) => !r.hidden)
            const wrapEl = outerOf(t); wrapEl.classList.toggle('is-empty', !any)
            // a heading right before an emptied table hides with it
            const prev = wrapEl.previousElementSibling
            if (prev && /^H[2-4]$/.test(prev.tagName)) prev.classList.toggle('is-empty', !any)
          }
          out.textContent = q ? `${hits} of ${all.length}` : ''
        }
        input.addEventListener('input', apply)
        input.addEventListener('keydown', (e) => { if (e.key === 'Escape') { input.value = ''; apply() } })
      }
      if (location.hash.startsWith(`#${id}-`)) reveal(root, location.hash.slice(1))
    }
  }
  function reveal(root, id) {
    const tr = root.querySelector('#' + CSS.escape(id))
    if (!tr) return
    let d = tr.closest('details'); while (d) { d.open = true; d = d.parentElement?.closest('details') }
    tr.classList.add('is-target')
    requestAnimationFrame(() => tr.scrollIntoView({ block: 'center' }))
  }

  // ── 4. tool cards on the generated reference pages: `## tool_name` + signature fence + prose → one card with facts lifted from the text
  const FACTS = [
    [/clamp(?:ed|s)?\s+(?:to\s+)?\[?\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*\]?/i, (m) => ['clamp', `${m[1]} … ${m[2]}`]],
    [/\[(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\]\s*(?:°|deg|degrees)?/, (m) => ['range', `${m[1]} … ${m[2]}`]],
    [/(?:default|defaults to)\s+(\d+(?:\.\d+)?)\s*(s|ms|sec|seconds)\b/i, (m) => ['default', `${m[1]} ${m[2]}`]],
    [/timeout\s+(?:of\s+)?(\d+(?:\.\d+)?)\s*(s|ms|seconds)?/i, (m) => ['timeout', `${m[1]} ${m[2] || 's'}`]],
  ]
  function toolCards(root) {
    if (!/\/reference\/tools\/[^/]+\/?$/.test(location.pathname) || root.querySelector('.tool')) return
    const heads = $$('h2', root).filter((h) => h.querySelector('code') && !h.classList.contains('step'))
    if (!heads.length) return
    for (const h of heads) {
      const card = document.createElement('section'); card.className = 'tool'; card.setAttribute('aria-labelledby', h.id)
      const head = document.createElement('div'); head.className = 'tool__head'
      const nodes = []; let n = h.nextElementSibling
      while (n && n.tagName !== 'H2') { nodes.push(n); n = n.nextElementSibling }
      h.replaceWith(card); head.append(h); card.append(head)
      const text = nodes.map((x) => x.textContent).join(' ')
      const tags = []
      if (/while (?:it |TINY )?(?:speaks|talking|speaking)|simultaneous|same turn/i.test(text)) tags.push(['robot', 'fires while speaking'])
      if (/clamp/i.test(text)) tags.push(['code', 'clamped'])
      if (/daemon/i.test(text)) tags.push(['code', 'via daemon'])
      if (tags.length) head.insertAdjacentHTML('beforeend', `<span class="tool__tags">${tags.map(([c, t]) => `<span class="pill pill--${c}">${t}</span>`).join('')}</span>`)
      const facts = []
      for (const [re, fn] of FACTS) { const m = text.match(re); if (m) { const [k, v] = fn(m); if (!facts.some((f) => f[0] === k)) facts.push([k, v]) } }
      const sig = nodes.find((x) => x.matches('.highlight, pre'))
      const args = sig ? (sig.textContent.match(/\n\s+([a-z_]+)\s*:/g) || []).length : 0
      if (args) facts.unshift(['args', String(args)])
      for (const x of nodes) card.append(x)
      if (facts.length) (sig || head).insertAdjacentHTML('afterend', `<ul class="tool__facts" aria-label="facts pulled from the docstring">${facts.map(([k, v]) => `<li><b>${esc(k)}</b> ${esc(v)}</li>`).join('')}</ul>`)
    }
  }

  // ── 5. body anatomy: the landing's exploded twin layers (docs/assets/landing/body/*.webp, read-only reuse) with hotspots → the page that proves each fact.
  const ANATOMY = {
    body: {
      layers: ['base', 'stewart', 'head', 'antennas'],
      alt: 'The Reachy Mini twin exploded into four layers: base body, Stewart platform, head with camera, and the two antennas',
      spots: [
        { x: 66, y: 17, n: 1, k: 'Antennas', v: 'two servos, degrees, the “ears” — every recorded emotion moves them', href: '../../reference/tools/reachy_expression/', layer: 'antennas' },
        { x: 64, y: 43, n: 2, k: 'Head · camera', v: 'wide camera in the face; the daemon\'s face tracker (≥ 1.10) steers the gaze', href: '../../reference/tools/head_tracking/', layer: 'head' },
        { x: 63, y: 63, n: 3, k: 'Stewart platform', v: '6-DOF neck — x y z roll pitch yaw, clamped before the daemon sees them', href: '../../reference/tools/reachy_motion/', layer: 'stewart' },
        { x: 61, y: 80, n: 4, k: 'Body · CM4 · speaker · mics', v: 'rotating base, the CM4 that runs TINY, XMOS mic array + speaker', href: '../../reference/tools/reachy_audio/', layer: 'base' },
      ],
    },
  }
  function anatomy(root) {
    for (const fig of $$('[data-anatomy]', root)) {
      const spec = ANATOMY[fig.dataset.anatomy]
      if (!spec || fig.querySelector('.anatomy__stage')) continue
      const base = fig.dataset.base || '../'
      const imgs = spec.layers.map((l) => `<img src="${base}assets/landing/body/${l}.webp" width="1100" height="1300" alt="" data-layer="${l}" decoding="async" loading="lazy">`).join('')
      const spots = spec.spots.map((s) => `<a class="anatomy__spot" href="${s.href}" style="--x:${s.x}%;--y:${s.y}%" data-n="${s.n}" aria-label="${s.n} — ${esc(s.k)}: ${esc(s.v)}"><span class="anatomy__dot">${s.n}</span></a>`).join('')
      const legend = spec.spots.map((s) => `<li class="anatomy__row" data-n="${s.n}"><a href="${s.href}"><span class="anatomy__num">${s.n}</span><span class="anatomy__k">${esc(s.k)}</span><span class="anatomy__v">${esc(s.v)}</span></a></li>`).join('')
      const cap = fig.querySelector('figcaption')  // the markdown caption survives the render
      fig.innerHTML = `<div class="anatomy__stage"><div class="anatomy__layers" role="img" aria-label="${esc(spec.alt)}">${imgs}</div>${spots}</div><ol class="anatomy__legend">${legend}</ol>`  // links must not sit inside role=img (axe nested-interactive)
      if (cap) fig.append(cap)
      const rows = $$('.anatomy__row', fig), dots = $$('.anatomy__spot', fig), layers = $$('img[data-layer]', fig)
      const hi = (n) => {
        for (const el of [...rows, ...dots]) el.classList.toggle('is-hot', n != null && el.dataset.n === String(n))
        const spot = spec.spots.find((s) => String(s.n) === String(n))
        for (const img of layers) { const dim = spot && img.dataset.layer !== spot.layer; img.classList.toggle('is-dim', !!dim); img.style.setProperty('--dx', dim ? (layers.indexOf(img) % 2 ? '3%' : '-3%') : '0') }
      }
      for (const el of [...rows, ...dots]) {
        el.addEventListener('pointerenter', () => hi(el.dataset.n)); el.addEventListener('pointerleave', () => hi(null))
        el.addEventListener('focusin', () => hi(el.dataset.n)); el.addEventListener('focusout', () => hi(null))
      }
    }
  }

  // ── 6. emotion gallery: the recorded-move library from the landing's emotions.json (read-only reuse), each with its own description, filterable
  async function emotions(root) {
    for (const box of $$('.emotions', root)) {
      if (box.querySelector('.emotions__grid')) continue
      let data
      try { data = await (await fetch(box.dataset.src || '../../js/landing/emotions.json')).json() } catch { continue }
      const moves = data.moves || []
      const families = [...new Set(moves.map((m) => m.name.replace(/\d+$/, '')))]
      box.innerHTML = `<div class="filter"><label><span class="filter__label">filter</span><input type="search" placeholder="curious, dance, sad… (${moves.length} moves, ${families.length} families)" autocomplete="off" spellcheck="false"></label><output aria-live="polite"></output></div>`
        + `<ul class="emotions__grid">${moves.map((m) => `<li data-name="${esc(m.name)}"><span class="emotion__name"><code>${esc(m.name)}</code><span class="emotion__dur">${m.duration ? m.duration.toFixed(1) + ' s' : ''}${m.sound ? ' · sound' : ''}</span></span><span class="emotion__desc">${esc(m.description || '')}</span></li>`).join('')}</ul>`
        + `<p class="muted"><small>${esc(data.source || '')}${data.snapshot ? ` · snapshot ${esc(data.snapshot)}` : ''} — the library's own descriptions; <code>reachy_list_emotions</code> returns the same names.</small></p>`
      const input = box.querySelector('input'), out = box.querySelector('output'), items = $$('li', box)
      const apply = () => { const q = input.value.trim().toLowerCase(); let hits = 0; for (const li of items) { const hit = !q || li.textContent.toLowerCase().includes(q); li.hidden = !hit; if (hit) hits++ } out.textContent = q ? `${hits} of ${items.length}` : '' }
      input.addEventListener('input', apply)
      input.addEventListener('keydown', (e) => { if (e.key === 'Escape') { input.value = ''; apply() } })
    }
  }

  // ── 7. mermaid scroll hint (Material renders into a CLOSED shadow root: children never show → the hint lives on a wrapper)
  function diagrams(root) {
    const hosts = $$('.mermaid', root)
    if (!hosts.length) return
    let tries = 0
    const tick = () => {
      let pending = false
      for (const h of hosts) {
        if (!h.isConnected) { pending = true; continue }
        const wide = h.scrollWidth > h.clientWidth + 8
        h.classList.toggle('is-scrollable', wide)
        if (wide && !h.parentElement.classList.contains('diagram')) {
          const wrap = document.createElement('div'); wrap.className = 'diagram'
          h.replaceWith(wrap); wrap.append(h)
          wrap.insertAdjacentHTML('beforeend', '<span class="mermaid__hint" aria-hidden="true">scroll ⇢</span>')
          h.addEventListener('scroll', () => wrap.classList.toggle('is-scrolled', h.scrollLeft > 24), { passive: true })
        }
      }
      if (pending) hosts.splice(0, hosts.length, ...$$('.mermaid', root))
      if (++tries < 30) setTimeout(tick, 250)
    }
    tick()
  }

  // ── 8. motion: blocks below the fold rise 14px into place once, on first sight. Opt-in (html.m-on): no-JS / reduced-motion readers get the static page.
  function motion(root) {
    if (!('IntersectionObserver' in window) || matchMedia('(prefers-reduced-motion: reduce)').matches) return
    const sel = '.card, .tool, .anatomy, .admonition, details, .md-typeset__table, .cards__grid, pre, .mermaid, .emotions__grid > li, h2'
    const els = $$(sel, root).filter((el) => !el.closest('.m-item') || el.matches('.card, .emotions__grid > li'))
    if (!els.length) return
    document.documentElement.classList.add('m-on')
    const pending = new Set()
    const io = new IntersectionObserver((entries) => { for (const e of entries) if (e.isIntersecting) land(e.target) }, { rootMargin: '0px 0px -8% 0px', threshold: 0.05 })
    const land = (el) => { el.classList.add('m-in'); pending.delete(el); io.unobserve(el); setTimeout(() => el.classList.remove('m-item', 'm-in'), 900) }
    const sweep = () => { for (const el of pending) if (el.getBoundingClientRect().bottom < 0) land(el); if (!pending.size) removeEventListener('scroll', sweep) }
    addEventListener('scroll', sweep, { passive: true })
    let i = 0
    for (const el of els) {
      el.classList.add('m-item')
      if (el.getBoundingClientRect().top < innerHeight) { el.classList.add('m-in'); continue }
      el.style.setProperty('--m-d', `${Math.min(i++ % 4, 3) * 40}ms`)
      pending.add(el); io.observe(el)
    }
  }

  function a11y(root) {
    document.querySelector('.md-search[role="dialog"]:not([aria-label])')?.setAttribute('aria-label', 'Search')
    $$('.md-code__nav', root).forEach((n, i) => n.setAttribute('aria-label', `Code block ${i + 1} actions`))
    $$('.md-typeset__scrollwrap', root).forEach((w) => { if (w.scrollWidth > w.clientWidth + 1) { w.tabIndex = 0; w.setAttribute('role', 'region'); w.setAttribute('aria-label', 'wide table, scrolls sideways') } })
    for (const strip of $$('.tabbed-labels', root)) { if (strip.scrollWidth > strip.clientWidth + 1) { strip.tabIndex = 0; strip.setAttribute('role', 'group'); strip.setAttribute('aria-label', 'tabs, scroll sideways') } }
  }

  function run() {
    const root = document.querySelector('.md-content .md-typeset')
    if (!root || root.closest('.landing') || document.getElementById('landing')) return
    for (const fn of [cards, steps, filterable, toolCards, anatomy, diagrams]) { try { fn(root) } catch (e) { console.warn(`docs.js ${fn.name} failed`, e) } }  // one broken enhancer must never take the others down
    emotions(root).then(() => motion(root))  // gallery cells join the rise once they exist
    a11y(root)
  }
  if (window.document$?.subscribe) window.document$.subscribe(run)
  else if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', run)
  else run()
  window.addEventListener('hashchange', () => { const m = location.hash.match(/^#([a-z]+-.+)$/); if (m) reveal(document, m[1]) })
})()
