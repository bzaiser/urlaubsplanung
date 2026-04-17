const CACHE_NAME = 'travel-hub-v11';
const STATIC_CACHE = 'travel-hub-static-v11';
const MEDIA_CACHE = 'travel-hub-media-v3';
const DYNAMIC_CACHE = 'travel-hub-dynamic-v3';

// Hardcoded Fallback HTML for Diary (Expedition Mode)
const DIARY_FALLBACK_HTML = `
<div class="modal-header border-secondary">
    <h5 class="modal-title text-warning">
        <i class="bi bi-wifi-off me-2"></i> Offline-Tagebuch (v11)
    </h5>
    <button type="button" class="btn-close btn-close-white" onclick="closeModal()"></button>
</div>
<div class="modal-body bg-dark text-light">
    <div class="alert alert-warning py-2 small">
        <i class="bi bi-exclamation-triangle me-2"></i>
        Kein Netz? Kein Problem. Schreibe einfach los!
    </div>
    <form id="diary-form-offline">
        <div class="mb-3">
            <textarea name="text" class="form-control bg-dark text-light border-secondary" rows="10" placeholder="Was hast du heute erlebt?"></textarea>
        </div>
        <div class="mb-3">
            <label class="form-label text-secondary small text-uppercase fw-bold">Bilder hinzufügen</label>
            <input type="file" name="images" class="form-control bg-dark text-light border-secondary" multiple accept="image/*">
        </div>
        <div class="d-grid gap-2">
            <button type="submit" class="btn btn-warning fw-bold">Lokal speichern</button>
            <button type="button" class="btn btn-outline-secondary" onclick="closeModal()">Abbrechen</button>
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
                if (window.showToast) showToast("✓ Lokal gespeichert (Offline-Backup)");
                closeModal();
                if (window.updateSyncIndicator) window.updateSyncIndicator();
            }
        });
    </script>
</div>
`;

const ASSETS = [
    '/',
    '/login/',
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
    event.waitUntil(caches.open(STATIC_CACHE).then((cache) => cache.addAll(ASSETS)));
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

    // 1. Navigation Flow
    if (event.request.mode === 'navigate') {
        event.respondWith(fetch(event.request).catch(() => caches.match('/') || caches.match('/login/')));
        return;
    }

    // 2. Diary Interceptor (Rock Solid Fallback)
    if (url.pathname.includes('/diary/') || url.pathname.includes('/day/')) {
        event.respondWith(
            caches.open(DYNAMIC_CACHE).then((cache) => {
                return cache.match(event.request).then((cachedResponse) => {
                    const fetchPromise = fetch(event.request).then((networkResponse) => {
                        cache.put(event.request, networkResponse.clone());
                        return networkResponse;
                    }).catch(() => {
                        // THE MAGIC FALLBACK: If network fails and nothing in cache, return our hardcoded UI
                        return new Response(DIARY_FALLBACK_HTML, {
                            headers: { 'Content-Type': 'text/html' }
                        });
                    });
                    return cachedResponse || fetchPromise;
                });
            })
        );
        return;
    }

    // 3. Defaults
    event.respondWith(caches.match(event.request).then((res) => res || fetch(event.request)));
});
