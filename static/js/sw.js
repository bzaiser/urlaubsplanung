const CACHE_NAME = 'travel-hub-v8';
const STATIC_CACHE = 'travel-hub-static-v8';
const MEDIA_CACHE = 'travel-hub-media-v1';
const DYNAMIC_CACHE = 'travel-hub-dynamic-v1';

const ASSETS = [
    '/',
    '/static/css/base.css',
    '/static/img/placeholder_day.png',
    '/static/js/offline_manager.js',
    'https://fonts.googleapis.com/css2?family=Inter:wght@400;600&family=Outfit:wght@600&display=swap',
    'https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css',
    'https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.min.css',
    'https://unpkg.com/htmx.org@1.9.11'
];

self.addEventListener('install', (event) => {
    self.skipWaiting();
    event.waitUntil(
        caches.open(STATIC_CACHE).then((cache) => {
            return cache.addAll(ASSETS);
        })
    );
});

self.addEventListener('activate', (event) => {
    event.waitUntil(
        caches.keys().then((keys) => {
            return Promise.all(
                keys.filter(k => k !== STATIC_CACHE && k !== MEDIA_CACHE && k !== DYNAMIC_CACHE && k !== CACHE_NAME)
                    .map(k => caches.delete(k))
            );
        })
    );
});

self.addEventListener('fetch', (event) => {
    const url = new URL(event.request.url);

    // Skip non-GET requests (like POST syncs) - they are handled by offline_manager.js
    if (event.request.method !== 'GET') return;

    // 1. Media Caching (Images) - Cache First, then network
    if (url.pathname.includes('/media/')) {
        event.respondWith(
            caches.open(MEDIA_CACHE).then((cache) => {
                return cache.match(event.request).then((response) => {
                    return response || fetch(event.request).then((networkResponse) => {
                        cache.put(event.request, networkResponse.clone());
                        return networkResponse;
                    });
                });
            })
        );
        return;
    }

    // 2. Dynamic Content (Diary Modals etc) - Stale While Revalidate
    if (url.pathname.includes('/day/') || url.pathname.includes('/diary/')) {
        event.respondWith(
            caches.open(DYNAMIC_CACHE).then((cache) => {
                return cache.match(event.request).then((cachedResponse) => {
                    const fetchPromise = fetch(event.request).then((networkResponse) => {
                        cache.put(event.request, networkResponse.clone());
                        return networkResponse;
                    });
                    return cachedResponse || fetchPromise;
                });
            })
        );
        return;
    }

    // 3. Static Assets & App Shell - Network First, fallback to cache
    event.respondWith(
        fetch(event.request)
            .then((response) => {
                // Optionally update static cache here if needed
                return response;
            })
            .catch(() => {
                return caches.match(event.request);
            })
    );
});
