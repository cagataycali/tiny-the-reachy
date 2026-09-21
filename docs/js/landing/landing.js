// landing.js — scroll progress for the pinned stages (--p on every [data-stage]), hero parallax (--sy on <html>), and the
// lazily-live hero: on a desktop with WebGL, after the page is idle, the still (hero-curious1-f24.webp) is replaced by the
// SAME frame drawn by three.js from the cockpit twin's meshes (dashboard/frontend/public/model/, 1.1 MB, served at /model/ by
// docs/hooks/gen.py on_files) so the visitor can drag TINY around. Camera parameters are the
// ones render_twin.mjs used for the still (twin.js VIEWS.hero: one lens for every asset on the page) — no jump on hand-over.
// Vanilla, no deps; three.js arrives only through the dynamic import in twin.js. Reduced motion: still only, no orbit.
(() => {
  const doc = document.documentElement;
  const reduce = matchMedia("(prefers-reduced-motion: reduce)");
  const stages = Array.from(document.querySelectorAll("[data-stage]"));
  const hero = document.querySelector(".l-hero");
  let raf = 0;
  const clamp01 = (x) => (x < 0 ? 0 : x > 1 ? 1 : x);

  function update() {
    raf = 0;
    const vh = innerHeight || 1;
    for (const s of stages) {
      if (reduce.matches) { s.style.setProperty("--p", "1"); s.classList.add("is-static"); notes(s, 1); continue; }
      s.classList.remove("is-static");
      const r = s.getBoundingClientRect();
      if (r.bottom < -vh || r.top > vh * 2) continue;
      const travel = r.height - vh;
      const p = travel > 0 ? clamp01(-r.top / travel) : 1;
      s.style.setProperty("--p", p.toFixed(4));
      s.classList.toggle("is-live", p > 0 && p < 1);
      notes(s, p);
      handlers.get(s)?.(p);
    }
    if (hero) doc.style.setProperty("--sy", reduce.matches ? "0" : clamp01(scrollY / vh).toFixed(4));
  }
  // notes: [data-at] children light up once p passes their timestamp; the latest passed one is "now"
  function notes(stage, p) {
    let now = null;
    for (const n of stage.querySelectorAll("[data-at]")) { if (n.closest("[hidden]")) { n.classList.remove("is-on", "is-now"); continue; } const on = p >= +n.dataset.at; n.classList.toggle("is-on", on); if (on) now = n; }
    for (const n of stage.querySelectorAll("[data-at].is-now")) if (n !== now) n.classList.remove("is-now");
    now?.classList.add("is-now");
  }
  const handlers = new Map();

  // ---- 1 · the hero turns to you: paint pose round(p·24) of seq/hero, instrument strip from poses/curious1.json ---------
  const heroStage = document.getElementById("hero");
  let heroFrame = 0, heroPosesP = null, onHeroFrame = null;
  if (heroStage && !reduce.matches && heroStage.dataset.seq) {
    const N = +heroStage.dataset.frames, seq = heroStage.dataset.seq, imgs = new Array(N), wrap = heroStage.querySelector(".l-figwrap"), turn = heroStage.querySelector(".l-turn"), tctx = turn.getContext("2d");
    const strip = Object.fromEntries(Array.from(heroStage.querySelectorAll("[data-hro]")).map((b) => [b.dataset.hro, b]));
    heroPosesP = fetch(heroStage.dataset.poses).then((r) => r.json()).catch(() => null);
    let poses = null; heroPosesP.then((p) => { poses = p; paintStrip(); });
    const fmt = (v) => (v < 0 ? "−" : "") + Math.abs(Math.round(v));
    const paintStrip = () => { if (!poses) return; const h = poses.head[heroFrame], a = poses.antennas[heroFrame]; strip.t.textContent = poses.t[heroFrame].toFixed(1); strip.yaw.textContent = fmt(h.yaw); strip.roll.textContent = fmt(h.roll); strip.ant.textContent = `${fmt(a[0])} / ${fmt(a[1])}`; };
    let loaded = false, painted = -1;
    const load = () => { if (loaded) return; loaded = true; for (let i = 0; i < N; i++) { const im = new Image(); im.decoding = "async"; im.src = `${seq}${String(i).padStart(2, "0")}.webp`; im.decode().then(() => createImageBitmap(im)).then((bm) => { imgs[i] = bm; if (i === heroFrame) paint(); }).catch(() => { imgs[i] = im; }); } };
    const paint = () => { const im = imgs[heroFrame]; if (!im) return; if (painted !== heroFrame) { tctx.clearRect(0, 0, turn.width, turn.height); tctx.drawImage(im, 0, 0, turn.width, turn.height); painted = heroFrame; wrap.classList.add("is-turning"); } };
    // phones: the hero is not pinned and the figure leaves the screen first, so the turn completes within the first 45 % of travel
    const wide = matchMedia("(min-width: 60em)");
    handlers.set(heroStage, (p) => {
      const q = wide.matches ? p : Math.min(1, p / 0.45);
      heroFrame = Math.round(q * (N - 1));
      heroStage.classList.toggle("has-scrolled", p > 0.01);
      if (p > 0) load();
      paint(); paintStrip(); onHeroFrame?.(heroFrame);
    });
    // frames arrive after the page is idle so they never compete with the LCP still; a scroll before that loads them at once
    const idle = () => ("requestIdleCallback" in window ? requestIdleCallback(load, { timeout: 3000 }) : setTimeout(load, 800));
    if (document.readyState === "complete") setTimeout(idle, 600); else addEventListener("load", () => setTimeout(idle, 600), { once: true });
  }

  // ---- 2 · the emotion: two real moves behind a swatch; paint frame round(p·(N-1)) of the picked move's sequence; readout from its poses json
  const emo = document.getElementById("emotion");
  if (emo && !reduce.matches) {
    const frameBox = emo.querySelector(".l-frame"), canvas = emo.querySelector(".l-frame__canvas"), ctx = canvas.getContext("2d"), still = emo.querySelector(".l-frame__still");
    const ro = Object.fromEntries(Array.from(emo.querySelectorAll("[data-ro]")).map((b) => [b.dataset.ro, b]));
    const fmt = (v) => (v < 0 ? "−" : "") + Math.abs(Math.round(v));
    // one record per swatch button: frames + poses load lazily, only for the picked move (fear1 costs nothing until you ask)
    const moves = new Map(Array.from(emo.querySelectorAll(".l-swatch__b")).map((b) => [b.dataset.pick, { btn: b, name: b.dataset.pick, N: +b.dataset.frames, seq: b.dataset.seq, posesUrl: b.dataset.poses, still: b.dataset.still, imgs: new Array(+b.dataset.frames), poses: null, loaded: 0, armed: false }]));
    let cur = moves.get(emo.dataset.move), p = 0, painted = "";
    const paint = () => {
      const m = cur, wanted = Math.round(p * (m.N - 1)), im = m.imgs[wanted];
      if (!im || (im instanceof HTMLImageElement && (!im.complete || !im.naturalWidth))) return;
      const key = `${m.name}:${wanted}`;
      if (painted !== key) { ctx.clearRect(0, 0, canvas.width, canvas.height); ctx.drawImage(im, 0, 0, canvas.width, canvas.height); painted = key; frameBox.classList.add("is-live"); }
      if (m.poses) {
        const ps = m.poses, i = Math.min(ps.frames.length - 1, Math.round(wanted / (m.N - 1) * (ps.frames.length - 1)));
        const h = ps.head[i], a = ps.antennas[i];
        ro.name.textContent = m.name; ro.t.textContent = ps.t[i].toFixed(1); ro.yaw.textContent = fmt(h.yaw); ro.roll.textContent = fmt(h.roll);
        ro.ant.textContent = `${fmt(a[0])} / ${fmt(a[1])}`; ro.body.textContent = fmt(ps.body_yaw[i]);
      }
    };
    const arm = (m) => {
      if (m.armed) return; m.armed = true;
      fetch(m.posesUrl).then((r) => r.json()).then((j) => { m.poses = j; paint(); }).catch(() => {});
      // decode off the scroll path: each frame becomes an ImageBitmap once (else the first drawImage of a frame costs ~100 ms mid-scrub);
      // the wanted frame first, so a pick mid-scrub lands in one round trip
      const order = Array.from({ length: m.N }, (_, k) => k); const w = Math.round(p * (m.N - 1)); order.splice(order.indexOf(w), 1); order.unshift(w);
      for (const k of order) { const im = new Image(); im.decoding = "async"; im.src = `${m.seq}${String(k).padStart(2, "0")}.webp`; m.imgs[k] = im;
        im.onload = () => { const ready = () => { m.loaded++; paint(); }; if ("createImageBitmap" in window) createImageBitmap(im).then((bm) => { m.imgs[k] = bm; ready(); }, ready); else ready(); }; }
    };
    const pick = (name) => {
      const m = moves.get(name); if (!m || m === cur) return;
      cur = m; emo.dataset.move = name;
      for (const [n, mm] of moves) mm.btn.setAttribute("aria-pressed", String(n === name));
      for (const el of emo.querySelectorAll(".l-move")) el.hidden = el.dataset.move !== name;
      // the still under the canvas follows the move (its alt too) — and the canvas hides until the new move has painted
      frameBox.classList.remove("is-live"); still.src = m.still; const alt = still.dataset[`alt${name[0].toUpperCase()}${name.slice(1)}`]; if (alt) still.alt = alt;
      arm(m); schedule(); paint();
    };
    for (const m of moves.values()) m.btn.addEventListener("click", () => pick(m.name));
    new IntersectionObserver((es) => { if (es.some((e) => e.isIntersecting)) arm(cur); }, { rootMargin: "260% 0px" }).observe(emo);
    handlers.set(emo, (pp) => { p = pp; paint(); });
  } else if (emo) emo.classList.add("is-static");

  const schedule = () => { if (!raf) raf = requestAnimationFrame(update); };
  addEventListener("scroll", schedule, { passive: true });
  addEventListener("resize", schedule);
  reduce.addEventListener?.("change", schedule);
  update();

  // Material's shell on this page: name the search dialog, hide the (empty) progress bar from AT, make the skip link a nav landmark
  document.querySelector(".md-search")?.setAttribute("aria-label", "Search");
  document.querySelector(".md-progress")?.setAttribute("aria-hidden", "true");
  const skip = document.querySelector('[data-md-component="skip"]'); if (skip) { skip.setAttribute("role", "navigation"); skip.setAttribute("aria-label", "Skip links"); }

  // ---- the live hero -------------------------------------------------------------------------------------------------
  const wrap = document.getElementById("l-figwrap");
  if (!wrap || reduce.matches || !matchMedia("(min-width: 60em) and (hover: hover)").matches) return;
  const canvas = wrap.querySelector(".l-orbit");
  const base = document.querySelector('link[rel="stylesheet"][href*="landing.css"]').getAttribute("href").replace(/stylesheets\/landing\.css.*$/, "");
  const hasGL = (() => { try { const c = document.createElement("canvas"); return !!(c.getContext("webgl2") || c.getContext("webgl")); } catch { return false; } })();
  if (!hasGL) return;
  let started = false;
  const start = async () => {
    if (started) return; started = true;
    try {
      const T = await import(`${base}js/landing/twin.js`);
      const [model, poses] = await Promise.all([T.loadModel(`${base}model/`, { yieldEach: true }), heroPosesP || fetch(`${base}assets/landing/poses/curious1.json`).then((r) => r.json())]);
      const W = 1100, H = 1300, dpr = Math.min(devicePixelRatio || 1, 2);
      canvas.width = W * dpr / 2; canvas.height = H * dpr / 2;
      const stage = T.makeStage(canvas, { width: canvas.width, height: canvas.height, dpr: 1, shadows: true });
      const HOME = T.VIEWS.hero; Object.assign(stage.orbit, { yaw: HOME.yaw, pitch: HOME.pitch, dist: HOME.dist }); stage.orbit.target.set(...HOME.target); stage.look();
      const robot = T.buildRobot(model); stage.scene.add(robot.root);
      T.applyFrame(robot, poses, heroStage?.dataset.seq ? heroFrame : 24); stage.render();
      onHeroFrame = (f) => { T.applyFrame(robot, poses, f); if (wrap.classList.contains("is-live")) { dirty = true; requestAnimationFrame(paint); } };
      const hint = document.querySelector(".l-caption__hint"); if (hint) hint.hidden = false;
      wrap.classList.add("is-ready");
      // drag to orbit (yaw/pitch), like the cockpit twin; idle: a very slow drift back toward the still's view
      let dragging = false, lx = 0, ly = 0, idle = 0, dirty = false;
      const paint = () => { if (dirty) { stage.look(); stage.render(); dirty = false; } };
      wrap.addEventListener("pointerdown", (e) => { wrap.classList.add("is-live"); dragging = true; lx = e.clientX; ly = e.clientY; wrap.classList.add("is-dragging"); wrap.setPointerCapture(e.pointerId); });
      wrap.addEventListener("pointermove", (e) => { if (!dragging) return; stage.orbit.yaw -= (e.clientX - lx) * 0.008; stage.orbit.pitch = Math.max(-0.1, Math.min(1.1, stage.orbit.pitch + (e.clientY - ly) * 0.006)); lx = e.clientX; ly = e.clientY; dirty = true; idle = 0; requestAnimationFrame(paint); });
      const up = () => { dragging = false; wrap.classList.remove("is-dragging"); };
      wrap.addEventListener("pointerup", up); wrap.addEventListener("pointercancel", up);
      const drift = () => { if (!dragging && document.visibilityState === "visible") { const dy = HOME.yaw - stage.orbit.yaw, dp = HOME.pitch - stage.orbit.pitch; if (Math.abs(dy) > 0.002 || Math.abs(dp) > 0.002) { stage.orbit.yaw += dy * 0.03; stage.orbit.pitch += dp * 0.03; dirty = true; paint(); } } setTimeout(() => requestAnimationFrame(drift), 33); };
      setTimeout(drift, 1200);
      addEventListener("resize", () => { dirty = true; requestAnimationFrame(paint); });
    } catch (e) { console.warn("landing: live hero unavailable —", e); }
  };
  // after load + 2.5 s + idle (keeps the mesh unpack out of the LCP/TTI window), or on first intent
  const arm = () => setTimeout(() => ("requestIdleCallback" in window ? requestIdleCallback(start, { timeout: 4000 }) : start()), 2500);
  if (document.readyState === "complete") arm(); else addEventListener("load", arm, { once: true });
  wrap.addEventListener("pointerenter", start, { once: true });
})();
