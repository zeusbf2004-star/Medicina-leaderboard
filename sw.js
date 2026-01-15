// Service Worker básico para PWA
const CACHE_NAME = 'competencia-medica-v1';
const urlsToCache = [
    '/'
];

// Instalación - cachear recursos básicos
self.addEventListener('install', event => {
    event.waitUntil(
        caches.open(CACHE_NAME)
            .then(cache => {
                console.log('Cache abierto');
                return cache.addAll(urlsToCache);
            })
            .catch(err => {
                console.log('Error en cache:', err);
            })
    );
    // Activar inmediatamente
    self.skipWaiting();
});

// Activación - limpiar caches antiguos
self.addEventListener('activate', event => {
    event.waitUntil(
        caches.keys().then(cacheNames => {
            return Promise.all(
                cacheNames.map(cacheName => {
                    if (cacheName !== CACHE_NAME) {
                        console.log('Eliminando cache antiguo:', cacheName);
                        return caches.delete(cacheName);
                    }
                })
            );
        })
    );
    // Tomar control inmediatamente
    self.clients.claim();
});

// Estrategia: Network first, fallback to cache
self.addEventListener('fetch', event => {
    event.respondWith(
        fetch(event.request)
            .then(response => {
                // Si la respuesta es válida, clonarla y cachearla
                if (response && response.status === 200) {
                    const responseClone = response.clone();
                    caches.open(CACHE_NAME)
                        .then(cache => {
                            cache.put(event.request, responseClone);
                        });
                }
                return response;
            })
            .catch(() => {
                // Si falla la red, buscar en cache
                return caches.match(event.request);
            })
    );
});
