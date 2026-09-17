/* Progressive enhancement only: no network, hardware, storage or animation loop.
   Material keeps ownership of navigation/search and Mermaid. */
(() => {
  if (window.__tinyDesign) return;
  window.__tinyDesign = true;
  const poses = {
    curious: 'reachy_look(roll=15)',
    listening: 'reachy_antennas(45, 45)',
    resting: 'reachy_home()',
  };
  function enhance() {
    // Material inserts its navigation progress bar dynamically without a name.
    // Name it after the current document emission; do not replace its lifecycle.
    queueMicrotask(() => {
      document.querySelector('.md-progress')?.setAttribute('aria-label', 'Loading page');
      // Material wraps tables during the same emission. A reference table
      // without links otherwise has no keyboard-reachable horizontal scroll.
      for (const table of document.querySelectorAll('.md-typeset__scrollwrap')) {
        table.tabIndex = 0;
        table.setAttribute('role', 'region');
        table.setAttribute('aria-label', 'Scrollable table');
      }
    });
    // Markdown's tab strip can overflow on a phone. Give keyboard users a
    // scroll target without changing Material's radio/label tab behaviour.
    for (const strip of document.querySelectorAll('.tabbed-labels')) {
      strip.tabIndex = 0;
      strip.setAttribute('role', 'group');
      strip.setAttribute('aria-label', 'Code example tabs');
    }
    const scene = document.querySelector('.rh-companion');
    if (!scene || scene.dataset.ready) return;
    scene.dataset.ready = 'true';
    const hero = document.querySelector('.rh-hero');
    if (hero) {
      hero.prepend(scene);
      hero.classList.add('rh-hero--companion');
    }
    const controls = scene.querySelector('.rh-pose-controls');
    if (!controls) return;
    controls.hidden = false;
    controls.addEventListener('click', event => {
      const button = event.target.closest('button[data-pose-choice]');
      if (!button || !controls.contains(button)) return;
      const pose = button.dataset.poseChoice;
      if (!poses[pose]) return;
      scene.dataset.pose = pose;
      for (const choice of controls.querySelectorAll('button')) {
        choice.setAttribute('aria-pressed', String(choice === button));
      }
      scene.querySelector('[data-pose-code]').textContent = poses[pose];
    });
  }
  if (typeof document$ !== 'undefined') document$.subscribe(enhance);
  else if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', enhance, {once: true});
  else enhance();
})();
