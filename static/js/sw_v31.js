const CACHE_NAME = 'travel-hub-v31';
const STATIC_CACHE = 'travel-hub-static-v31';
const MEDIA_CACHE = 'travel-hub-media-v31';
const DYNAMIC_CACHE = 'travel-hub-dynamic-v31';

const log = (msg, data = '') => console.log(`[SW v31] ${msg}`, data);

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
        <div class="indicator">OFFLINE-MODUS (v31)</div>
        <h1>Inhalt nicht im Cache</h1>
        <p>Dieses Element ist aktuell nicht offline verfügbar. Bitte stellen Sie eine Verbindung her.</p>
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
    log('Installing Software v31 (Import-Fix)...');
    self.skipWaiting();
    event.waitUntil(caches.open(STATIC_CACHE).then((cache) => {
        return Promise.allSettled(ASSETS.map(url => cache.add(url)));
    }));
});

self.addEventListener('activate', (event) => {
    log('v31 Activated. Clearing old caches...');
    event.waitUntil(Promise.all([
        self.clients.claim(),
        caches.keys().then((keys) => {
            return Promise.all(
                keys.filter(k => ![STATIC_CACHE, MEDIA_CACHE, DYNAMIC_CACHE, CACHE_NAME].includes(k)).map(k => caches.delete(k))
            );
        })
    ]));
});

const isBypassed = (url) => {
    return url.includes('/edit/') || url.includes('/delete/') || url.includes('/create/') || url.includes('/import/') || url.includes('?t=');
};

self.addEventListener('fetch', (event) => {
    // --- SPECIAL HANDLING: HTMX Fragments (Stale-While-Revalidate) ---
    const isHtmx = event.request.headers.get('HX-Request') === 'true';

    // MUTATION GUARD: If we POST/PUT/DELETE, we MUST clear the dynamic cache to avoid stale fragments
    if (event.request.method !== 'GET') {
        event.respondWith(
            fetch(event.request).then(response => {
                if (response.ok) {
                    log('Mutation detected. Purging DYNAMIC_CACHE for consistency.');
                    caches.delete(DYNAMIC_CACHE);
                }
                return response;
            })
        );
        return;
    }
    
    // GUARD: Only handle http/https requests
    if (!event.request.url.startsWith('http')) return;

    const url = new URL(event.request.url);

    if (isBypassed(url.pathname)) {
        event.respondWith(fetch(event.request));
        return;
    }

    // 1. NAVIGATION (Page Loads) -> Network First, then Cache
    if (event.request.mode === 'navigate') {
        event.respondWith(
            fetch(event.request).then(response => {
                if (response.ok && response.status === 200) {
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

    // 2. HTMX FRAGMENTS (Tab Switching) -> Stale-While-Revalidate (Ultra Fast)
    if (isHtmx) {
        event.respondWith(
            caches.match(event.request).then(cachedResponse => {
                const networkFetch = fetch(event.request).then(networkResponse => {
                    if (networkResponse && networkResponse.status === 200) {
                        const copy = networkResponse.clone();
                        caches.open(DYNAMIC_CACHE).then(cache => cache.put(event.request, copy));
                    }
                    return networkResponse;
                });
                
                // Return cache immediately if available, otherwise wait for network
                return cachedResponse || networkFetch;
            })
        );
        return;
    }

    // 3. STATICS & MEDIA -> Cache First or Network
    event.respondWith(
        fetch(event.request).then((networkResponse) => {
            if (networkResponse && networkResponse.status === 200) {
                const cacheToUse = url.pathname.includes('/media/') ? MEDIA_CACHE : 
                                  (url.pathname.includes('/static/') ? STATIC_CACHE : DYNAMIC_CACHE);
                const responseClone = networkResponse.clone();
                caches.open(cacheToUse).then(cache => cache.put(event.request, responseClone));
            }
            return networkResponse;
        }).catch(() => {
            return caches.match(event.request).then((cachedResponse) => {
                const isPage = event.request.mode === 'navigate';
                if (isPage && !cachedResponse) {
                    return new Response(EMERGENCY_SHELL_HTML, { headers: { 'Content-Type': 'text/html' } });
                }
                return cachedResponse || new Response('', { status: 408 });
            });
        })
    );
});
