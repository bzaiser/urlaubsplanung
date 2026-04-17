const CACHE_NAME = 'travel-hub-v27';
const STATIC_CACHE = 'travel-hub-static-v27';
const MEDIA_CACHE = 'travel-hub-media-v4';
const DYNAMIC_CACHE = 'travel-hub-dynamic-v4';

const log = (msg, data = '') => console.log(`[SW v27] ${msg}`, data);

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
    <title>Travel Hub - Offline Fallback</title>
    <style>${EMERGENCY_STYLES}</style>
</head>
<body>
    <div class="container">
        <div class="indicator">OFFLINE-MODUS (v27)</div>
        <h1>Inhalt nicht im Cache</h1>
        <p>Dieses Element ist aktuell nicht offline verfügbar. Bitte stellen Sie eine Verbindung her, um die Synchronisierung zu vervollständigen.</p>
        <a href="/" class="btn">Zurück zur Übersicht</a>
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
    log('Installing Software v27...');
    self.skipWaiting();
    event.waitUntil(caches.open(STATIC_CACHE).then((cache) => {
        return Promise.allSettled(ASSETS.map(url => cache.add(url)));
    }));
});

self.addEventListener('activate', (event) => {
    log('v27 Activated.');
    event.waitUntil(Promise.all([
        self.clients.claim(),
        caches.keys().then((keys) => {
            return Promise.all(
                keys.filter(k => ![STATIC_CACHE, MEDIA_CACHE, DYNAMIC_CACHE, CACHE_NAME].includes(k)).map(k => caches.delete(k))
            );
        })
    ]));
});

self.addEventListener('fetch', (event) => {
    if (event.request.method !== 'GET') return;
    const url = new URL(event.request.url);

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
                return fallback || new Response(EMERGENCY_SHELL_HTML, { headers: { 'Content-Type': 'text/html' } });
            })
        );
        return;
    }

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
                    return caches.match(event.request).then(res => res || new Response(EMERGENCY_SHELL_HTML, { headers: {'Content-Type': 'text/html'}}));
                }
                return new Response('', { status: 408 });
            });

            return cachedResponse || fetchPromise;
        })
    );
});
