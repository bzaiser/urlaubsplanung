const CACHE_NAME = 'travel-hub-v1';
const ASSETS = [
    '/',
    '/static/css/base.css',
    '/static/js/main.js',
    '/static/img/icon-160.png',
];

self.addEventListener('install', (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME).then((cache) => {
            return cache.addAll(ASSETS);
        })
    );
});

self.addEventListener('fetch', (event) => {
    event.respondWith(
        caches.match(event.request).then((response) => {
            return response || fetch(event.request);
        })
    );
});
