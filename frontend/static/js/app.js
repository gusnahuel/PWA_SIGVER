/**
 * SIGVER - Punto de entrada de la PWA.
 *
 * Solo arranca la app: cada módulo se encarga de su parte de la pantalla
 * y registra sus propios botones (data-accion="...").
 *
 *   estado.js      datos compartidos (usuario, equipos, sitios, mapa)
 *   util.js        funciones puras (escapar HTML, UUID, fotos, distancias)
 *   api.js         llamadas al servidor con token, timeout y errores
 *   ui.js          toasts, paneles, menú, contadores, segmentados, acciones
 *   sesion.js      login, menú de usuario y cierre de sesión
 *   mapa.js        mapa, marcadores, filtros, tarjeta y popup del equipo
 *   busqueda.js    buscador de equipos
 *   verificacion-etc.js        formulario de ETC
 *   verificacion-regulador.js  formulario de reguladores (4 pasos)
 *   mediciones.js  termografías y ensayos PAT del regulador
 *   elementos.js   equipos del banco (datos de placa) del regulador
 *   reclamos.js    lista de reclamos y envío de evidencia
 *   sync.js        cola offline y sincronización automática
 *   actualizaciones.js  service worker y aviso de versión nueva
 */
import { cerrarMenu, cerrarPaneles, iniciarSegmentados, marcarNav, registrarAcciones, setStatus } from './ui.js?v=128';
import { haySesion, ocultarLogin, restaurarSesion } from './sesion.js?v=128';
import { iniciarMapa } from './mapa.js?v=128';
import { cargarFallas } from './verificacion-etc.js?v=128';
import { cargarPuntosTermografia } from './mediciones.js?v=128';
import { iniciarAvisoReclamos } from './reclamos.js?v=128';
import { actualizarContadorPendientes, iniciarSincronizacion } from './sync.js?v=128';
import { registrarServiceWorker } from './actualizaciones.js?v=128';
import './busqueda.js?v=128';
import './verificacion-regulador.js?v=128';

registrarAcciones({
    'ir-mapa': () => {
        cerrarPaneles();
        cerrarMenu();
        marcarNav('mapa');
    },
});

async function iniciarApp() {
    const loader = document.getElementById('loading-screen');
    loader.style.display = 'flex';
    document.getElementById('map').style.display = 'block';
    try {
        await Promise.all([
            iniciarMapa(),
            cargarFallas(),             // catálogos para usar sin señal
            cargarPuntosTermografia(),
        ]);
        iniciarAvisoReclamos();   // contador de la navegación y aviso de reclamos nuevos
        actualizarContadorPendientes();

        loader.style.opacity = '0';
        setTimeout(() => { loader.style.display = 'none'; }, 500);
    } catch (err) {
        console.error('Error:', err);
        setStatus('Error de conexión', true);
        loader.style.display = 'none';
    }
}

// ==========================================
// Arranque
// ==========================================
restaurarSesion();
iniciarSegmentados();
iniciarSincronizacion();
registrarServiceWorker();

if (haySesion()) {
    ocultarLogin();
    iniciarApp();
} else {
    document.getElementById('loading-screen').style.display = 'none';
}
