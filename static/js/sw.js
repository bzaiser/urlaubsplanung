const CACHE_NAME = 'travel-hub-v15';
const STATIC_CACHE = 'travel-hub-static-v15';
const MEDIA_CACHE = 'travel-hub-media-v3';
const DYNAMIC_CACHE = 'travel-hub-dynamic-v3';

// Hardcoded Emergency App Shell (Absolute safety)
const EMERGENCY_SHELL_HTML = `
<!DOCTYPE html>
<html lang="de">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Travel Hub - Offline Fallback</title>
    <style>
        body { background: #0a192f; color: #fff; font-family: sans-serif; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; text-align: center; }
        .container { padding: 30px; border: 1px solid #112240; border-radius: 12px; background: #112240; max-width: 80%; }
        h1 { color: #64ffda; }
        .btn { display: inline-block; margin-top: 20px; padding: 12px 24px; background: #64ffda; color: #0a192f; text-decoration: none; border-radius: 4px; font-weight: bold; }
    </style>
</head>
<body>
    <div class="container">
        <h1>Travel Hub Offline (v15)</h1>
        <p>Inhalt wird geladen, sobald du wieder Netz hast oder der Speicher bereit ist.</p>
        <a href="/" class="btn">Seite neu laden</a>
    </div>
</body>
</html>
`;

// Hardcoded Fallback for Diary Fragments
const DIARY_FALLBACK_HTML = `
<div class="modal-header border-secondary">
    <h5 class="modal-title text-warning"><i class="bi bi-wifi-off me-2"></i> Offline-Diary (v15)</h5>
    <button type="button" class="btn-close btn-close-white" onclick="if(window.closeModal){window.closeModal()}else{this.closest('.modal').style.display='none'}"></button>
</div>
<div class="modal-body bg-dark text-light">
    <div class="alert alert-warning py-2 small">Einträge werden sicher lokal gesichert.</div>
    <form id="diary-form-offline">
        <div class="mb-3"><textarea name="text" class="form-control bg-dark text-light border-secondary" rows="10" placeholder="Was hast du heute erlebt?"></textarea></div>
        <div class="mb-3"><label class="form-label text-secondary small text-uppercase fw-bold">Bilder hinzufügen</label><input type="file" name="images" class="form-control bg-dark text-light border-secondary" multiple accept="image/*"></div>
        <div class="d-grid gap-2">
            <button type="submit" class="btn btn-warning fw-bold">Lokal speichern</button>
            <button type="button" class="btn btn-outline-secondary" onclick="if(window.closeModal){window.closeModal()}">Abbrechen</button>
        </div>
    </form>
    <script>
        document.getElementById('diary-form-offline').addEventListener('submit', async function(e) {
            e.preventDefault();
            const formData = new FormData(this);
            const pathParts = window.location.pathname.split('/');
            const dayId = pathParts.find(p => !isNaN(p) && p !== '') || 'unknown';
            if (window.queueEntry) {
                const images = [];
                const files = formData.getAll('images');
                for (const file of files) { if (file.size > 0) { images.push({ name: file.name, type: file.type, blob: file }); } }
                await window.queueEntry(dayId, formData, images);
                if (window.showToast) window.showToast("✓ Lokal gespeichert (v15)");
                if (window.closeModal) window.closeModal();
            }
        });
    </script>
</div>
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

// Helper for Network Timeout with explicit Response return
const timeoutResponse = (ms, fallbackHtml) => new Promise((resolve) => {
    setTimeout(() => {
        resolve(new Response(fallbackHtml, {
            status: 200,
            statusText: 'Timeout Fallback',
            headers: { 'Content-Type': 'text/html' }
        }));
    }, ms);
});

self.addEventListener('fetch', (event) => {
    const url = new URL(event.request.url);
    if (event.request.method !== 'GET') return;

    // 1. Navigation Flow - With 2s Network-Race and GUARANTEED response
    if (event.request.mode === 'navigate') {
        event.respondWith(
            Promise.race([
                fetch(event.request),
                timeoutResponse(2500, EMERGENCY_SHELL_HTML)
            ]).catch(() => {
                return caches.match('/') || caches.match('/login/') || new Response(EMERGENCY_SHELL_HTML, { headers: { 'Content-Type': 'text/html' } });
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
                        timeoutResponse(3000, DIARY_FALLBACK_HTML)
                    ]).then((networkResponse) => {
                        if (networkResponse.ok) cache.put(event.request, networkResponse.clone());
                        return networkResponse;
                    }).catch(() => new Response(DIARY_FALLBACK_HTML, { headers: { 'Content-Type': 'text/html' } }));
                    
                    return cachedResponse || fetchPromise;
                });
            })
        );
        return;
    }

    // 3. Asset Default Strategy (GUARANTEE NO NULL RETURN)
    event.respondWith(
        caches.match(event.request).then((cachedResponse) => {
            if (cachedResponse) return cachedResponse;
            return fetch(event.request).catch(() => {
                // Return an empty success or error response to satisfy respondWith requirements
                return new Response('', { status: 408, statusText: 'Offline Fallback' });
            });
        })
    );
});
