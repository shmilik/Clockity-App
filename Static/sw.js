/* Clockity PWA Service Worker */
const CACHE_NAME = 'clockity-v1';

// Static assets to pre-cache on install
const PRECACHE_URLS = [
    '/',
    '/Static/custom_shift_required.js',
    '/Static/Images/clockity-logo.png',
    'https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700&display=swap',
    'https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css',
    'https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js',
    'https://cdn.jsdelivr.net/npm/fullcalendar@6.1.8/index.global.min.css',
    'https://cdn.jsdelivr.net/npm/fullcalendar@6.1.8/index.global.min.js'
];

// ── Install: pre-cache static assets ────────────────────────────────────────
self.addEventListener('install', function (event) {
    event.waitUntil(
        caches.open(CACHE_NAME).then(function (cache) {
            return cache.addAll(PRECACHE_URLS);
        }).then(function () {
            return self.skipWaiting();
        })
    );
});

// ── Activate: purge old caches ───────────────────────────────────────────────
self.addEventListener('activate', function (event) {
    event.waitUntil(
        caches.keys().then(function (cacheNames) {
            return Promise.all(
                cacheNames
                    .filter(function (name) { return name !== CACHE_NAME; })
                    .map(function (name) { return caches.delete(name); })
            );
        }).then(function () {
            return self.clients.claim();
        })
    );
});

// ── Fetch: network-first for API, cache-first for assets ────────────────────
self.addEventListener('fetch', function (event) {
    var url = new URL(event.request.url);

    // Skip non-GET requests and browser-extension requests
    if (event.request.method !== 'GET') return;
    if (!url.protocol.startsWith('http')) return;

    // API calls: network-first, no caching
    if (url.pathname.startsWith('/api/') || url.pathname.startsWith('/export/')) {
        event.respondWith(fetch(event.request));
        return;
    }

    // SocketIO: skip
    if (url.pathname.startsWith('/socket.io/')) return;

    // Static assets & pages: stale-while-revalidate
    event.respondWith(
        caches.open(CACHE_NAME).then(function (cache) {
            return cache.match(event.request).then(function (cachedResponse) {
                var networkFetch = fetch(event.request).then(function (networkResponse) {
                    if (networkResponse && networkResponse.status === 200 && networkResponse.type !== 'opaque') {
                        cache.put(event.request, networkResponse.clone());
                    }
                    return networkResponse;
                }).catch(function () {
                    // Offline fallback: return cached page if available
                    return cachedResponse;
                });

                // Return cached copy immediately while updating in background
                return cachedResponse || networkFetch;
            });
        })
    );
});
