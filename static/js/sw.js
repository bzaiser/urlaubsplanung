const CACHE_NAME = 'travel-hub-v19';
const STATIC_CACHE = 'travel-hub-static-v19';
const MEDIA_CACHE = 'travel-hub-media-v3';
const DYNAMIC_CACHE = 'travel-hub-dynamic-v3';

const log = (msg, data = '') => console.log(`[SW v19] ${msg}`, data);

const EMERGENCY_STYLES = `
    body { background: #0a192f; color: #fff; font-family: sans-serif; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; text-align: center; }
    .container { padding: 30px; border: 2px solid #64ffda; border-radius: 12px; background: #112240; box-shadow: 0 10px 30px rgba(0,0,0,0.5); max-width: 80%; }
    .indicator { background: #ff4d4d; color: white; padding: 5px 10px; border-radius: 4px; font-weight: bold; margin-bottom: 20px; display: inline-block; }
    h1 { color: #64ffda; margin-top: 0; }
    p { color: #8892b0; line-height: 1.6; }
    .btn { display: inline-block; margin-top: 20px; padding: 12px 24px; background: #64ffda; color: #0a192f; text-decoration: none; border-radius: 4px; font-weight: bold; }
`;

const EMERGENCY_SHELL_HTML = `
<!DOCTYPE html>
<html lang="de">
<head>
    <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Travel Hub - OFFLINE v19</title>
    <style>${EMERGENCY_STYLES}</style>
</head>
<body>
    <div class="container">
        <div class="indicator">OFFLINE-MODUS AKTIV (v19)</div>
        <h1>Verbindung unterbrochen</h1>
        <p>Du bist gerade offline. Deine Timeline wird aus dem lokalen Bunker (v19) geladen.</p>
        <a href="/" class="btn">Hauptseite neu laden</a>
    </div>
</body>
</html>
`;

const ASSETS = [
    '/',
    '/login/',
    '/static/css/base.css',
    '/static/js/offline_manager.js',
    'https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css',
    'https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.min.css',
    'https://unpkg.com/htmx.org@1.9.11'
];

self.addEventListener('install', (event) => {
    log('Installing v19 (Iron Grip)...');
    self.skipWaiting();
    event.waitUntil(caches.open(STATIC_CACHE).then((cache) => {
        return Promise.allSettled(ASSETS.map(url => cache.add(url)));
    }));
});

self.addEventListener('activate', (event) => {
    log('Activating v19 - Taking control!');
    event.waitUntil(Promise.all([
        self.clients.claim(),
        caches.keys().then((keys) => Promise.all(
            keys.filter(k => ![STATIC_CACHE, MEDIA_CACHE, DYNAMIC_CACHE, CACHE_NAME].includes(k)).map(k => caches.delete(k))
        ))
    ]));
});

self.addEventListener('fetch', (event) => {
    const url = new URL(event.request.url);
    if (event.request.method !== 'GET') return;

    // 1. Navigation Race
    if (event.request.mode === 'navigate') {
        event.respondWith(
            fetch(event.request).then(response => {
                if (response.ok) {
                    const copy = response.clone();
                    caches.open(STATIC_CACHE).then(cache => cache.put(event.request, copy));
                }
                return response;
            }).catch(async () => {
                const fallback = await caches.match('/') || await caches.match('/login/');
                // If we serve a fallback from cache, append a tiny identification script
                if (fallback) return fallback;
                return new Response(EMERGENCY_SHELL_HTML, { headers: { 'Content-Type': 'text/html' } });
            })
        );
        return;
    }

    // 2. Bunker Strategy
    event.respondWith(
        caches.match(event.request).then((cachedResponse) => {
            const fetchPromise = fetch(event.request).then((networkResponse) => {
                if (networkResponse && networkResponse.status === 200) {
                    const cacheToUse = url.pathname.includes('/media/') ? MEDIA_CACHE : 
                                     (url.pathname.includes('/diary/') || url.pathname.includes('/day/')) ? DYNAMIC_CACHE : 
                                     STATIC_CACHE;
                    const responseClone = networkResponse.clone();
                    caches.open(cacheToUse).then(cache => cache.put(event.request, responseClone));
                }
                return networkResponse;
            }).catch(() => {
                if (url.pathname.includes('/diary/') || url.pathname.includes('/day/')) {
                    // Try to match the last successful diary fragment
                    return caches.match(event.request).then(res => res || new Response('<div class="p-3 bg-danger text-white">Offline: Tag nicht im Cache (v19)</div>', { headers: {'Content-Type': 'text/html'}}));
                }
                return new Response('', { status: 408 });
            });

            return cachedResponse || fetchPromise;
        })
    );
});
