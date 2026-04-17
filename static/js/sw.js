const CACHE_NAME = 'travel-hub-v17';
const STATIC_CACHE = 'travel-hub-static-v17';
const MEDIA_CACHE = 'travel-hub-media-v3';
const DYNAMIC_CACHE = 'travel-hub-dynamic-v3';

// Ultimate Emergency Styles (Embedded to prevent 'blue links')
const EMERGENCY_STYLES = `
    body { background: #0a192f; color: #fff; font-family: sans-serif; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; text-align: center; }
    .container { padding: 30px; border: 1px solid #112240; border-radius: 12px; background: #112240; box-shadow: 0 10px 30px rgba(0,0,0,0.5); max-width: 80%; }
    h1 { color: #64ffda; margin-top: 0; }
    p { color: #8892b0; line-height: 1.6; }
    .btn { display: inline-block; margin-top: 20px; padding: 12px 24px; background: #64ffda; color: #0a192f; text-decoration: none; border-radius: 4px; font-weight: bold; font-size: 1rem; border: none; cursor: pointer; }
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
        <h1>Travel Hub Offline (v17)</h1>
        <p>Inhalte werden geladen...</p>
        <a href="/" class="btn">Hauptseite neu laden</a>
    </div>
</body>
</html>
`;

const DIARY_FALLBACK_HTML = `
<div class="modal-header border-secondary">
    <h5 class="modal-title text-warning"><i class="bi bi-wifi-off me-2"></i> Offline-Diary (v17)</h5>
    <button type="button" class="btn-close btn-close-white" onclick="if(window.closeModal){window.closeModal()}else{this.closest('.modal').style.display='none'}"></button>
</div>
<div class="modal-body bg-dark text-light">
    <div class="alert alert-warning py-2 small">Einträge werden sicher lokal (v17) gesichert.</div>
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
                if (window.showToast) window.showToast("✓ Lokal gespeichert (v17)");
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

self.addEventListener('fetch', (event) => {
    const url = new URL(event.request.url);
    if (event.request.method !== 'GET') return;

    // 1. Navigation Flow - Robust & Fast
    if (event.request.mode === 'navigate') {
        event.respondWith(
            fetch(event.request).catch(async () => {
                const fallback = await caches.match('/') || await caches.match('/login/');
                return fallback || new Response(EMERGENCY_SHELL_HTML, { headers: { 'Content-Type': 'text/html' } });
            })
        );
        return;
    }

    // 2. Universal Strategy: Cache first, then Network + Auto-Update
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
                // Guaranteed fallback for diary entries
                if (url.pathname.includes('/diary/') || url.pathname.includes('/day/')) {
                    return new Response(DIARY_FALLBACK_HTML, { headers: { 'Content-Type': 'text/html' } });
                }
                // Default fallback response for other assets
                return new Response('', { status: 408, statusText: 'Offline Fallback' });
            });

            return cachedResponse || fetchPromise;
        })
    );
});
