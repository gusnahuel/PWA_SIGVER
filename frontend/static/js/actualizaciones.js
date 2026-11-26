/**
 * SIGVER - Service worker y aviso de versión nueva.
 *
 * La versión nueva NO se activa sola: queda "en espera" y se muestra un cartel.
 * Así nunca conviven el código viejo de la pestaña con el service worker nuevo,
 * y no se recarga la app con un formulario a medio cargar.
 */
import { showToast } from './ui.js?v=127';

let swEnEspera = null;
let recargandoPorActualizacion = false;

function hayFormularioAbierto() {
    const abierto = (id) => document.getElementById(id)?.classList.contains('active');
    const modalEvidencia = document.getElementById('modal-evidencia-reclamo');
    return abierto('sheet-verificacion') || abierto('sheet-regulador')
        || (modalEvidencia && modalEvidencia.style.display === 'flex');
}

function mostrarAvisoActualizacion(worker) {
    swEnEspera = worker;
    document.getElementById('aviso-actualizacion').hidden = false;
}

function vigilarActualizaciones(reg) {
    // Ya había una versión esperando (p. ej. se descargó en la visita anterior)
    if (reg.waiting && navigator.serviceWorker.controller) mostrarAvisoActualizacion(reg.waiting);

    reg.addEventListener('updatefound', () => {
        const nuevo = reg.installing;
        nuevo?.addEventListener('statechange', () => {
            // Sin controller = primera instalación: no hay nada que actualizar
            if (nuevo.state === 'installed' && navigator.serviceWorker.controller) {
                mostrarAvisoActualizacion(nuevo);
            }
        });
    });

    // La app suele quedar abierta todo el día en campo: buscar versiones al volver a ella
    document.addEventListener('visibilitychange', () => {
        if (document.visibilityState === 'visible' && navigator.onLine) reg.update().catch(() => {});
    });
}

export function registrarServiceWorker() {
    if (!('serviceWorker' in navigator)) return;

    document.getElementById('btn-actualizar-app')?.addEventListener('click', () => {
        if (hayFormularioAbierto()) {
            showToast('Guardá o cerrá el formulario antes de actualizar.', 'warning');
            return;
        }
        if (!swEnEspera) { location.reload(); return; }
        recargandoPorActualizacion = true;
        swEnEspera.postMessage({ tipo: 'ACTIVAR_VERSION_NUEVA' });
    });

    navigator.serviceWorker.addEventListener('controllerchange', () => {
        if (recargandoPorActualizacion) location.reload();
    });

    window.addEventListener('load', () => {
        navigator.serviceWorker.register('/sw.js', { updateViaCache: 'none' })
            .then((reg) => {
                vigilarActualizaciones(reg);
                reg.update().catch(() => {});
            })
            .catch((err) => console.warn('[PWA] SW no registrado:', err));
    });
}
