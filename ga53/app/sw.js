// Service worker for the GA53 Overtures (2026) app. Scoped to /pca-ga/ga53/app/.
// Shell is cache-first (instant offline launch); the overture index is network-first
// (so a fresh build is picked up) with cache fallback when offline.
// Kept SEPARATE from the main corpus app's cache — GA53 is proposals, not the adopted record.
const VERSION = 'pca-ga53-v5';
const SHELL = ['./', './index.html', '../manifest.json', './icon.svg', './icon-192.png', './icon-512.png', './icon-180.png', './icon-maskable-512.png'];

self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(VERSION).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== VERSION).map((k) => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (e) => {
  const req = e.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  // Only handle requests within our scope; let links out to the overture pages hit the network.
  // shared notes module lives one level up (outside /app/) — cache it so the app works offline
  if (url.pathname.endsWith('/notes.js')) {
    e.respondWith(caches.match(req).then((h) => h || fetch(req).then((res) => {
      const c = res.clone(); caches.open(VERSION).then((cc) => cc.put(req, c)); return res;
    })));
    return;
  }
  if (!url.pathname.includes('/ga53/app/')) return;

  if (url.pathname.endsWith('search_index.json')) {
    e.respondWith(
      fetch(req).then((res) => {
        const copy = res.clone();
        caches.open(VERSION).then((c) => c.put(req, copy));
        return res;
      }).catch(() => caches.match(req))
    );
    return;
  }

  e.respondWith(
    caches.match(req).then((hit) => hit || fetch(req).then((res) => {
      const copy = res.clone();
      caches.open(VERSION).then((c) => c.put(req, copy));
      return res;
    }))
  );
});
