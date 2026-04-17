const CACHE_NAME = 'travel-hub-v20';
const STATIC_CACHE = 'travel-hub-static-v20';
const MEDIA_CACHE = 'travel-hub-media-v3';
const DYNAMIC_CACHE = 'travel-hub-dynamic-v3';

const log = (msg, data = '') => console.log(`[SW v20] ${msg}`, data);

const EMERGENCY_STYLES = `
    body { background: #0a192f; color: #fff; font-family: sans-serif; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; text-align: center; }
    .container { padding: 30px; border: 2px solid #ff4d4d; border-radius: 12px; background: #112240; box-shadow: 0 10px 30px rgba(0,0,0,0.5); max-width: 80%; }
    .indicator { background: #ff4d4d; color: white; padding: 5px 10px; border-radius: 4px; font-weight: bold; margin-bottom: 20px; display: inline-block; }
    h1 { color: #fff; margin-top: 0; }
    p { color: #8892b0; line-height: 1.6; }
    .btn { display: inline-block; margin-top: 20px; padding: 12px 24px; background: #ff4d4d; color: #fff; text-decoration: none; border-radius: 4px; font-weight: bold; }
`;

const EMERGENCY_SHELL_HTML = `
<!DOCTYPE html>
<html lang="de">
<head>
    <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>RESCUE v20</title>
    <style>${EMERGENCY_STYLES}</style>
</head>
<body>
    <div class="container">
        <div class="indicator">RESCUE MODE v20</div>
        <h1>Verbindung blockiert</h1>
        <p>Die App konnte nicht geladen werden. Bitte nutze den Reset-Button in den Einstellungen oder lade die Seite online neu.</p>
        <a href="/" class="btn">Erneut versuchen</a>
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
    log('Rescue Install v20...');
    self.skipWaiting();
    event.waitUntil(caches.open(STATIC_CACHE).then((cache) => {
        return Promise.allSettled(ASSETS.map(url => cache.add(url)));
    }));
});

self.addEventListener('activate', (event) => {
    log('Rescue Active v20!');
    event.waitUntil(Promise.all([
        self.clients.claim(),
        caches.keys().then((keys) => {
            return Promise.all(
                keys.filter(k => ![STATIC_CACHE, MEDIA_CACHE, DYNAMIC_CACHE, CACHE_NAME].includes(k)).map(k => caches.delete(k))
            );
        })
    ]));
});

// Helper for Network Timeout - Pure Promise, no async keywords here
const timeoutResponse = (ms, fallbackHtml) => new Promise((resolve) => {
    setTimeout(() => {
        resolve(new Response(fallbackHtml, {
            status: 200,
            headers: { 'Content-Type': 'text/html' }
        }));
    }, ms);
});

self.addEventListener('fetch', (event) => {
    if (event.request.method !== 'GET') return;
    const url = new URL(event.request.url);

    // 1. Navigation Rescue - With 2s Network Race
    if (event.request.mode === 'navigate') {
        event.respondWith(
            Promise.race([
                fetch(event.request),
                timeoutResponse(2000, EMERGENCY_SHELL_HTML)
            ]).then((response) => {
                if (response && response.status === 200) {
                    const copy = response.clone();
                    caches.open(STATIC_CACHE).then(cache => cache.put(event.request, copy));
                }
                return response;
            }).catch(() => {
                return caches.match('/').then(res => res || caches.match('/login/')).then(res => {
                    return res || new Response(EMERGENCY_SHELL_HTML, { headers: { 'Content-Type': 'text/html' }});
                });
            })
        );
        return;
    }

    // 2. Asset Bunker Strategy
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
                    return caches.match(event.request).then(res => {
                        return res || new Response('<div class="p-3 bg-danger text-white">Offline: v20 Fallback</div>', { headers: {'Content-Type': 'text/html'}});
                    });
                }
                return new Response('', { status: 408 });
            });

            return cachedResponse || fetchPromise;
        })
    );
});
