/* TINY cockpit service worker — app shell only. Never touches /api, /ws or the MuJoCo model/engine.
   /assets/* are content-hashed (immutable) → cache-first; the shell ("/") is network-first with an offline fallback
   so a deploy is picked up on the next load and the gate still renders (and then says "dashboard unreachable") without network. */
const SHELL = 'tiny-shell-v3'
self.addEventListener('install', (e) => { self.skipWaiting(); e.waitUntil(caches.open(SHELL).then((c) => c.add('/').catch(() => {}))) })
self.addEventListener('activate', (e) => { e.waitUntil(caches.keys().then((ks) => Promise.all(ks.filter((k) => k !== SHELL).map((k) => caches.delete(k)))).then(() => self.clients.claim())) })
self.addEventListener('fetch', (e) => {
  const u = new URL(e.request.url)
  if (e.request.method !== 'GET' || u.origin !== location.origin) return
  if (u.pathname.startsWith('/api/') || u.pathname === '/ws' || u.pathname.startsWith('/model/') || u.pathname.startsWith('/mujoco/')) return
  if (u.pathname.startsWith('/assets/')) {
    e.respondWith(caches.open(SHELL).then(async (c) => (await c.match(e.request)) || fetch(e.request).then((r) => { if (r.ok) c.put(e.request, r.clone()); return r })))
    return
  }
  if (e.request.mode === 'navigate' || u.pathname === '/' || u.pathname === '/manifest.webmanifest' || u.pathname.endsWith('.png')) {
    e.respondWith(fetch(e.request).then((r) => { if (r.ok) caches.open(SHELL).then((c) => c.put(e.request, r.clone())); return r }).catch(() => caches.match(e.request).then((m) => m || caches.match('/'))))
  }
})
