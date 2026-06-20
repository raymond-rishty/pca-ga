// Page-scoped service worker for the GA53 overture pages. Scope: /pca-ga/ga53/
// Registered by each overture page (via the ga53-overture layout) so a result tapped in the app
// is cached for offline reading. Deliberately SEPARATE from the app worker (/ga53/app/) — each
// ignores the other's territory so the two caches never fight.
const VERSION = 'pca-ga53-pages-v2';

self.addEventListener('install', () => self.skipWaiting());

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k.startsWith('pca-ga53-pages') && k !== VERSION).map((k) => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (e) => {
  const req = e.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  if (!url.pathname.includes('/ga53/')) return;       // only our area
  if (url.pathname.includes('/ga53/app/')) return;     // the app worker owns the app

  // cache-first for instant offline reading; refresh the copy in the background
  e.respondWith(
    caches.match(req).then((hit) => {
      const net = fetch(req).then((res) => {
        const copy = res.clone();
        caches.open(VERSION).then((c) => c.put(req, copy));
        return res;
      }).catch(() => hit);
      return hit || net;
    })
  );
});
