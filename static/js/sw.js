const CACHE_NAME = 'travel-hub-v16';
const STATIC_CACHE = 'travel-hub-static-v16';
const MEDIA_CACHE = 'travel-hub-media-v3';
const DYNAMIC_CACHE = 'travel-hub-dynamic-v3';

// Ultimate Emergency Styles (Embedded in SW to prevent 'blue links' look)
const EMERGENCY_STYLES = `
    body { background: #0a192f; color: #fff; font-family: sans-serif; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; text-align: center; }
    .container { padding: 30px; border: 1px solid #112240; border-radius: 12px; background: #112240; box-shadow: 0 10px 30px rgba(0,0,0,0.5); max-width: 80%; }
    h1 { color: #64ffda; margin-top: 0; }
    p { color: #8892b0; line-height: 1.6; }
    .btn { display: inline-block; margin-top: 20px; padding: 12px 24px; background: #64ffda; color: #0a192f; text-decoration: none; border-radius: 4px; font-weight: bold; font-size: 1rem; border: none; cursor: pointer; }
    .text-warning { color: #ffc107; }
    .bg-dark { background-color: #121212 !important; }
`;

const EMERGENCY_SHELL_HTML = `
<!DOCTYPE html>
<html lang="de">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Travel Hub - Bunker Mode</title>
    <style>${EMERGENCY_STYLES}</style>
</head>
<body>
    <div class="container">
        <h1>Travel Hub Offline (v16)</h1>
        <p>Wir befinden uns im Bunker-Modus. Inhalte werden geladen...</p>
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

// Helper for Network Timeout (for navigation)
const timeoutResponse = (ms, fallbackHtml) => new Promise((resolve) => {
    setTimeout(() => {
        resolve(new Response(fallbackHtml, {
            status: 200,
            headers: { 'Content-Type': 'text/html' }
        }));
    }, ms);
});

self.addEventListener('fetch', (event) => {
    const url = new URL(event.request.url);
    if (event.request.method !== 'GET') return;

    // 1. Navigation Race
    if (event.request.mode === 'navigate') {
        event.respondWith(
            Promise.race([
                fetch(event.request),
                timeoutResponse(2500, EMERGENCY_SHELL_HTML)
            ]).then((response) => {
                if (response.ok) {
                    const copy = response.clone();
                    caches.open(STATIC_CACHE).then(cache => cache.put(event.request, copy));
                }
                return response;
            }).catch(async () => {
                return caches.match('/') || caches.match('/login/') || new Response(EMERGENCY_SHELL_HTML, { headers: { 'Content-Type': 'text/html' } });
            })
        );
        return;
    }

    // 2. Bunker Strategy: Stale-While-Revalidate + Auto-Cache for EVERYTHING
    event.respondWith(
        caches.match(event.request).then((cachedResponse) => {
            const fetchPromise = fetch(event.request).then((networkResponse) => {
                if (networkResponse && networkResponse.status === 200) {
                    const cacheToUse = url.pathname.includes('/media/') ? MEDIA_CACHE : 
                                     (url.pathname.includes('/diary/') || url.pathname.includes('/day/')) ? DYNAMIC_CACHE : 
                                     STATIC_CACHE;
                    const responseClone = networkResponse.clone();
                    caches.open(cacheToUse).then((cache) => {
                        cache.put(event.request, responseClone);
                    });
                }
                return networkResponse;
            }).catch(() => {
                // Return a generic fallback response for diary fragments to avoid TypeError
                if (url.pathname.includes('/diary/') || url.pathname.includes('/day/')) {
                    // Try to match the emergency shell or return a simple fragment
                    return new Response('<div class="p-3 text-warning">Offline-Modus: Bitte lerne diesen Tag online einmal kurz an.</div>', {
                        headers: { 'Content-Type': 'text/html' }
                    });
                }
                return null; // Let the cache handle it
            });

            // Return cache first, or wait for fetch
            return cachedResponse || fetchPromise || new Response('', { status: 408 });
        })
    );
});
