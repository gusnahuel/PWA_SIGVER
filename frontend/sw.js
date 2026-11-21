/**
 * SIGVER - Service Worker
 * Estrategias de cacheo diferenciadas para PWA offline-first.
 */
const CACHE_NAME = 'sigver-v102'; 
const TILE_CACHE = 'sigver-tiles-v102';

// Recursos que se cachean al instalar (app shell)
const APP_SHELL = [
    '/',
    '/static/css/style.css',
    '/static/js/app.js',
    '/manifest.json',
];

// ==========================================
// INSTALL: cachear app shell
// ==========================================
self.addEventListener('install', (event) => {
    console.log('[SW] Instalando...');
    event.waitUntil(
        caches.open(CACHE_NAME).then((cache) => {
            return cache.addAll(APP_SHELL);
        }).then(() => self.skipWaiting())
    );
});

// ==========================================
// ACTIVATE: limpiar caches viejos
// ==========================================
self.addEventListener('activate', (event) => {
    console.log('[SW] Activado');
    event.waitUntil(
        caches.keys().then((cacheNames) => {
            return Promise.all(
                cacheNames
                    .filter((name) => name !== CACHE_NAME && name !== TILE_CACHE)
                    .map((name) => caches.delete(name))
            );
        }).then(() => self.clients.claim())
    );
});

// ==========================================
// FETCH: estrategias por tipo de recurso
// ==========================================
self.addEventListener('fetch', (event) => {
    const url = new URL(event.request.url);
    // Dejamos que falle naturalmente si no hay internet.
    if (event.request.method !== 'GET') {
        return; 
    }

    // 1. Tiles de Esri → Cache First (Stale-While-Revalidate)
    if (url.hostname.includes('arcgisonline.com') || url.hostname.includes('tile')) {
        event.respondWith(
            caches.open(TILE_CACHE).then((cache) => {
                return cache.match(event.request).then((cached) => {
                    const fetchPromise = fetch(event.request).then((response) => {
                        if (response.ok) {
                            cache.put(event.request, response.clone());
                        }
                        return response;
                    }).catch(() => cached);
                    return cached || fetchPromise;
                });
            })
        );
        return;
    }

    // 2. Librerías CDN (Leaflet, MarkerCluster) → Cache First
    if (url.hostname.includes('unpkg.com') || url.hostname.includes('cdn')) {
        event.respondWith(
            caches.match(event.request).then((cached) => {
                return cached || fetch(event.request).then((response) => {
                    return caches.open(CACHE_NAME).then((cache) => {
                        cache.put(event.request, response.clone());
                        return response;
                    });
                });
            })
        );
        return;
    }

    // 3. API → Network First (con fallback offline)
    if (url.pathname.startsWith('/api/')) {
        event.respondWith(
            fetch(event.request).then((response) => {
                // Cachear la respuesta exitosa
                const clone = response.clone();
                caches.open(CACHE_NAME).then((cache) => {
                    cache.put(event.request, clone);
                });
                return response;
            }).catch(() => {
                // Sin red: buscar en cache
                return caches.match(event.request).then((cached) => {
                    if (cached) return cached;
                    return new Response(
                        JSON.stringify({ error: 'offline', detail: 'Sin conexión' }),
                        { status: 503, headers: { 'Content-Type': 'application/json' } }
                    );
                });
            })
        );
        return;
    }

    // 4. Todo lo demás → Cache First (con fallback a red)
    event.respondWith(
        caches.match(event.request).then((cached) => {
            return cached || fetch(event.request);
        })
    );
});