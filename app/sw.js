// Compatibility worker for the former PCA GA Minutes search app at /app/.
// It revalidates the redirect so installed copies move to the root search promptly.
const VERSION = 'pca-app-v5';
const SHELL = ['./index.html'];

self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(VERSION).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k.startsWith('pca-app-') && k !== VERSION).map((k) => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (e) => {
  const req = e.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  // Only handle requests within our scope; let the rest hit the network normally
  // (e.g. links out to the verbatim minutes pages).
  if (!url.pathname.includes('/app/')) return;

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

  // The search now lives at the site root. Always revalidate this compatibility
  // route so previously installed copies receive the redirect immediately.
  e.respondWith(fetch(req).catch(() => caches.match(req)));
});
