const CACHE = 'pca-ga-v11';
const STATIC = [
  './',
  './research.html',
  './manifest.json',
  './icon.svg',
  './icon-192.png',
  './icon-512.png',
  './icon-maskable-512.png',
  './assets/pca-style.css',
  './assets/pca-nav.js',
  './assets/constitution-links.css',
  './assets/constitution-links.js',
  './assets/research-store.js',
  './assets/research-workspace.js',
  './assets/search-record.js',
  './assets/home-search.js',
  './app/search_index.json',
  './app/case_summaries_1.json',
  './app/case_summaries_2.json'
];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(STATIC)));
  self.skipWaiting();
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k.startsWith('pca-ga-') && k !== CACHE).map(k => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener('fetch', e => {
  // Network-first; cache on success; serve cache on failure.
  e.respondWith(
    fetch(e.request)
      .then(r => {
        if (r.ok) caches.open(CACHE).then(c => c.put(e.request, r.clone()));
        return r;
      })
      .catch(() => caches.match(e.request))
  );
});
