const CACHE_NAME = 'travel-hub-v14';
const STATIC_CACHE = 'travel-hub-static-v14';
const MEDIA_CACHE = 'travel-hub-media-v3';
const DYNAMIC_CACHE = 'travel-hub-dynamic-v3';

// Hardcoded Emergency App Shell (Fast as lightning)
const EMERGENCY_SHELL_HTML = `
<!DOCTYPE html>
<html lang="de">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Travel Hub - Offline Rescue</title>
    <style>
        body { background: #0a192f; color: #fff; font-family: sans-serif; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; text-align: center; }
        .container { padding: 30px; border: 1px solid #112240; border-radius: 12px; background: #112240; box-shadow: 0 10px 30px rgba(0,0,0,0.5); max-width: 80%; }
        h1 { color: #64ffda; margin-top: 0; }
        p { color: #8892b0; line-height: 1.6; }
        .btn { display: inline-block; margin-top: 20px; padding: 12px 24px; background: #64ffda; color: #0a192f; text-decoration: none; border-radius: 4px; font-weight: bold; transition: opacity 0.2s; }
        .btn-outline { background: transparent; border: 1px solid #64ffda; color: #64ffda; margin-left: 10px; }
        .version { margin-top: 20px; font-size: 0.7rem; color: #495670; }
    </style>
</head>
<body>
    <div class="container">
        <h1>Travel Hub Offline (v14)</h1>
        <p>Die Seite konnte nicht schnell genug geladen werden. Wir nutzen den Offline-Modus.</p>
        <a href="/" class="btn">Erneut versuchen</a>
        <div class="version">System-Status: Rescue Active (v14)</div>
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
    self.skipWaiting();
    event.waitUntil(caches.open(STATIC_CACHE).then((cache) => {
        return Promise.allSettled(ASSETS.map(url => cache.add(url)));
    }));
});

self.addEventListener('activate', (event) => {
    event.waitUntil(Promise.all([
        self.clients.claim(),
        caches.keys().then((keys) => Promise.all(
            keys.filter(k => ![STATIC_CACHE, MEDIA_CACHE, DYNAMIC_CACHE, CACHE_NAME].includes(k)).map(k => caches.delete(k))
        ))
    ]));
});

// Helper for Network Timeout
const timeout = (ms) => new Promise((_, reject) => setTimeout(() => reject(new Error('Timeout')), ms));

self.addEventListener('fetch', (event) => {
    const url = new URL(event.request.url);
    if (event.request.method !== 'GET') return;

    // 1. Navigation Flow - With 1.5s Network-Race
    if (event.request.mode === 'navigate') {
        event.respondWith(
            Promise.race([
                fetch(event.request),
                timeout(1500) // 1.5 Seconds max wait
            ]).catch(async () => {
                const fallback = await caches.match('/') || await caches.match('/login/');
                if (fallback) return fallback;
                return new Response(EMERGENCY_SHELL_HTML, { headers: { 'Content-Type': 'text/html' } });
            })
        );
        return;
    }

    // 2. Diary Interceptor
    if (url.pathname.includes('/diary/') || url.pathname.includes('/day/')) {
        event.respondWith(
            caches.open(DYNAMIC_CACHE).then((cache) => {
                return cache.match(event.request).then((cachedResponse) => {
                    const fetchPromise = Promise.race([
                        fetch(event.request),
                        timeout(2000) // 2 Seconds for modals
                    ]).then((networkResponse) => {
                        cache.put(event.request, networkResponse.clone());
                        return networkResponse;
                    }).catch(() => {
                        // Return a hardcoded string fallback (v13 style) or emergency response
                        return new Response('<h3>Offline-Modus aktiv</h3><p>Bitte nutze die v14 Notfall-Maske.</p>', { headers: { 'Content-Type': 'text/html' } });
                    });
                    return cachedResponse || fetchPromise;
                });
            })
        );
        return;
    }

    // 3. Fallbacks for assets
    event.respondWith(
        caches.match(event.request).then((res) => {
            return res || fetch(event.request).catch(() => null);
        })
    );
});
