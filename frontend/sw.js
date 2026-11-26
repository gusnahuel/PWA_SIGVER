/**
 * SIGVER - Service Worker
 * Estrategias de cacheo diferenciadas para PWA offline-first.
 */
const CACHE_NAME = 'sigver-v127';
const TILE_CACHE = 'sigver-tiles-v102'; // no cambiar: borraría los mapas offline

// Recursos que se cachean al instalar (app shell): con esto la app arranca
// completa sin conexión, incluso si nunca se abrió con señal más que una vez.
const APP_SHELL = [
    '/',
    // Con ?v=: nginx sirve /static/ como "immutable", hay que cambiar la URL en cada versión
    // (lo hace scripts/version.sh)
    '/static/css/tokens.css?v=127',
    '/static/css/style.css?v=127',
    '/static/js/app.js?v=127',
    '/static/js/db.js?v=127',
    // Módulos que importa app.js: si falta uno, la app no arranca sin conexión
    '/static/js/estado.js?v=127',
    '/static/js/util.js?v=127',
    '/static/js/api.js?v=127',
    '/static/js/ui.js?v=127',
    '/static/js/sesion.js?v=127',
    '/static/js/mapa.js?v=127',
    '/static/js/busqueda.js?v=127',
    '/static/js/gps.js?v=127',
    '/static/js/verificacion-etc.js?v=127',
    '/static/js/verificacion-regulador.js?v=127',
    '/static/js/mediciones.js?v=127',
    '/static/js/elementos.js?v=127',
    '/static/js/reclamos.js?v=127',
    '/static/js/sync.js?v=127',
    '/static/js/actualizaciones.js?v=127',
    '/manifest.json',
    '/static/icons/icon.svg?v=2',
    // Librerías propias (antes venían de CDNs y no estaban garantizadas offline)
    '/static/vendor/leaflet-1.9.4/leaflet.css',
    '/static/vendor/leaflet-1.9.4/leaflet.js',
    '/static/vendor/leaflet-1.9.4/images/layers.png',
    '/static/vendor/leaflet-1.9.4/images/layers-2x.png',
    '/static/vendor/markercluster-1.5.3/MarkerCluster.css',
    '/static/vendor/markercluster-1.5.3/MarkerCluster.Default.css',
    '/static/vendor/markercluster-1.5.3/leaflet.markercluster.js',
    '/static/vendor/inter-5.2.5/inter.css',
    '/static/vendor/inter-5.2.5/inter-latin-wght-normal.woff2',
    '/static/vendor/inter-5.2.5/inter-latin-ext-wght-normal.woff2',
    '/static/vendor/fontawesome-6.4.0/css/fontawesome.min.css',
    '/static/vendor/fontawesome-6.4.0/css/solid.min.css',
    '/static/vendor/fontawesome-6.4.0/webfonts/fa-solid-900.woff2',
];

// Versiones anteriores a la 108 no muestran el cartel "Actualizar": si venimos
// de una de ellas, activamos la nueva directamente (una sola vez, en la transición).
const VERSIONES_SIN_AVISO = /^sigver-v(\d+)$/;

// ==========================================
// INSTALL: cachear app shell
// ==========================================
self.addEventListener('install', (event) => {
    console.log('[SW] Instalando...');
    event.waitUntil(
        caches.open(CACHE_NAME)
            .then((cache) => cache.addAll(APP_SHELL))
            .then(() => caches.keys())
            .then((nombres) => {
                const vieja = nombres.some((n) => {
                    const m = n.match(VERSIONES_SIN_AVISO);
                    return m && Number(m[1]) < 108;
                });
                if (vieja) return self.skipWaiting();
                // Si no, queda "en espera" hasta que el usuario toque "Actualizar"
            })
    );
});

// La página pide activar la versión nueva (botón "Actualizar")
self.addEventListener('message', (event) => {
    if (event.data?.tipo === 'ACTIVAR_VERSION_NUEVA') self.skipWaiting();
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

    // 2. API → Network First (con fallback offline)
    if (url.pathname.startsWith('/api/')) {
        event.respondWith(
            fetch(event.request).then((response) => {
                // Cachear solo respuestas exitosas (antes se guardaban 401/500
                // y se servían como si fueran datos válidos al quedar offline)
                if (response.ok) {
                    const clone = response.clone();
                    caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
                }
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

    // 3. Admin y reportes de Django → siempre red (no cachear páginas con sesión)
    if (url.pathname.startsWith('/admin/') || url.pathname.startsWith('/reportes/')) {
        return;
    }

    // 4. Navegación (index.html) → Network First, para recibir actualizaciones
    if (event.request.mode === 'navigate') {
        event.respondWith(
            fetch(event.request).catch(() =>
                caches.match(event.request).then((cached) => cached || caches.match('/'))
            )
        );
        return;
    }

    // 5. Resto de estáticos propios → Cache First, guardando lo nuevo
    event.respondWith(
        caches.match(event.request).then((cached) => {
            return cached || fetch(event.request).then((response) => {
                if (response.ok && url.origin === self.location.origin) {
                    const clone = response.clone();
                    caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
                }
                return response;
            });
        })
    );
});