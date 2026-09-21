// landing.js — scroll progress for the pinned stages (--p on every [data-stage]), hero parallax (--sy on <html>), and the
// lazily-live hero: on a desktop with WebGL, after the page is idle, the still (hero-curious1-f24.webp) is replaced by the
// SAME frame drawn by three.js from the cockpit twin's meshes (dashboard/frontend/public/model/, 1.1 MB, served at /model/ by
// docs/hooks/gen.py on_files) so the visitor can drag TINY around. Camera parameters are the
// ones render_twin.mjs used for the still (dist 1.15, pitch .18, yaw .62, target z .19 y .06) — no jump on hand-over.
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
      if (reduce.matches) { s.style.setProperty("--p", "1"); continue; }
      const r = s.getBoundingClientRect();
      if (r.bottom < -vh || r.top > vh * 2) continue;
      const travel = r.height - vh;
      const p = travel > 0 ? clamp01(-r.top / travel) : 1;
      s.style.setProperty("--p", p.toFixed(4));
      s.classList.toggle("is-live", p > 0 && p < 1);
    }
    if (hero) doc.style.setProperty("--sy", reduce.matches ? "0" : clamp01(scrollY / vh).toFixed(4));
  }
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
      const [model, poses] = await Promise.all([T.loadModel(`${base}model/`), fetch(`${base}assets/landing/poses/curious1.json`).then((r) => r.json())]);
      const W = 1100, H = 1300, dpr = Math.min(devicePixelRatio || 1, 2);
      canvas.width = W * dpr / 2; canvas.height = H * dpr / 2;
      const stage = T.makeStage(canvas, { width: canvas.width, height: canvas.height, dpr: 1, shadows: true });
      Object.assign(stage.orbit, { yaw: 0.62, pitch: 0.18, dist: 1.15 }); stage.orbit.target.set(0, 0.06, 0.19); stage.look();
      const robot = T.buildRobot(model); stage.scene.add(robot.root);
      T.applyFrame(robot, poses, 24); stage.render();
      const hint = document.querySelector(".l-caption__hint"); if (hint) hint.hidden = false;
      wrap.classList.add("is-ready");
      // drag to orbit (yaw/pitch), like the cockpit twin; idle: a very slow drift back toward the still's view
      let dragging = false, lx = 0, ly = 0, idle = 0, dirty = false;
      const paint = () => { if (dirty) { stage.look(); stage.render(); dirty = false; } };
      wrap.addEventListener("pointerdown", (e) => { wrap.classList.add("is-live"); dragging = true; lx = e.clientX; ly = e.clientY; wrap.classList.add("is-dragging"); wrap.setPointerCapture(e.pointerId); });
      wrap.addEventListener("pointermove", (e) => { if (!dragging) return; stage.orbit.yaw -= (e.clientX - lx) * 0.008; stage.orbit.pitch = Math.max(-0.1, Math.min(1.1, stage.orbit.pitch + (e.clientY - ly) * 0.006)); lx = e.clientX; ly = e.clientY; dirty = true; idle = 0; requestAnimationFrame(paint); });
      const up = () => { dragging = false; wrap.classList.remove("is-dragging"); };
      wrap.addEventListener("pointerup", up); wrap.addEventListener("pointercancel", up);
      const drift = () => { if (!dragging && document.visibilityState === "visible") { const dy = 0.62 - stage.orbit.yaw, dp = 0.18 - stage.orbit.pitch; if (Math.abs(dy) > 0.002 || Math.abs(dp) > 0.002) { stage.orbit.yaw += dy * 0.03; stage.orbit.pitch += dp * 0.03; dirty = true; paint(); } } setTimeout(() => requestAnimationFrame(drift), 33); };
      setTimeout(drift, 1200);
      addEventListener("resize", () => { dirty = true; requestAnimationFrame(paint); });
    } catch (e) { console.warn("landing: live hero unavailable —", e); }
  };
  // after load + idle, or on first intent
  const arm = () => ("requestIdleCallback" in window ? requestIdleCallback(start, { timeout: 4000 }) : setTimeout(start, 2500));
  if (document.readyState === "complete") arm(); else addEventListener("load", arm, { once: true });
  wrap.addEventListener("pointerenter", start, { once: true });
})();
