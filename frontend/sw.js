/* MatrixHunt Ultimate - minimal offline shell.
 * Network-first for API calls and navigation so the dashboard never serves
 * stale offers, cache-first for static assets which are served from disk.
 */
const CACHE = 'matrixhunt-v5';
const SHELL = [
  '/',
  '/static/index.html',
  '/static/icon.svg',
  '/retro',
  '/pad',
  '/wiki',
  '/bookmarks',
  '/flash',
  '/db',
  '/view',
  '/tools/assets/api.js',
  '/tools/assets/theme.js',
  '/tools/assets/lang.js',
  '/tools/assets/outbound.js',
  '/tools/emulator-db.js',
  '/tools/assets/hardware-detect.js',
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE)
      .then((cache) => cache.addAll(SHELL))
      .catch(() => undefined)
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(
        keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))
      ))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const { request } = event;
  if (request.method !== 'GET') return;

  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;

  // Never cache live data.
  if (url.pathname.startsWith('/api/')) {
    event.respondWith(fetch(request).catch(() => new Response(
      JSON.stringify({ error: 'offline' }),
      { status: 503, headers: { 'Content-Type': 'application/json' } }
    )));
    return;
  }

  if (request.mode === 'navigate') {
    event.respondWith(
      fetch(request)
        .then((res) => {
          const copy = res.clone();
          caches.open(CACHE).then((c) => c.put(request, copy));
          return res;
        })
        .catch(() => caches.match(request).then((r) => r || caches.match('/')))
    );
    return;
  }

  event.respondWith(
    caches.match(request).then((cached) => cached || fetch(request).then((res) => {
      if (res.ok) {
        const copy = res.clone();
        caches.open(CACHE).then((c) => c.put(request, copy));
      }
      return res;
    }))
  );
});
