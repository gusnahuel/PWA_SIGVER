/**
 * SIGVER - Trabajo sin conexión: cola de verificaciones (IndexedDB), contadores
 * de pendientes, estado de la conexión y sincronización automática.
 */
import { guardarVerificacionOffline, obtenerPendientes, eliminarDeOutbox } from './db.js?v=119';
import { fetchConTimeout, describirErrorServidor } from './api.js?v=119';
import { ponerBadge, registrarAcciones, showToast } from './ui.js?v=119';
import { estado } from './estado.js?v=119';

let isSyncing = false;
let cantidadPendientes = 0;

// Cola de reclamos resueltos offline de versiones viejas: [{id, fecha}] (acepta el formato [id])
function leerReclamosResueltosOffline() {
    try {
        const lista = JSON.parse(localStorage.getItem('sigver_reclamos_resueltos') || '[]');
        return lista.map((x) => (typeof x === 'string' ? { id: x, fecha: new Date().toISOString() } : x));
    } catch {
        return [];
    }
}

// ==========================================
// Cada verificación guardada sin señal lleva el id de quien la cargó
// ('propietario'). Si en el mismo celular entra otro usuario, las del primero
// quedan esperando y NO se envían con el token del segundo: el servidor asigna
// el responsable según quién está autenticado y quedarían a nombre de otro.
// ==========================================
function esPendientePropio(p) {
    // Las guardadas por versiones anteriores no tienen dueño: se envían como antes
    return !p.propietario || p.propietario === estado.usuario?.id;
}

export async function obtenerPendientesPropios() {
    return (await obtenerPendientes()).filter(esPendientePropio);
}

// ==========================================
// Contadores y cartel de conexión
// ==========================================
function actualizarPillConexion() {
    const pill = document.getElementById('pill-conexion');
    if (!pill) return;
    const partes = [];
    if (!navigator.onLine) partes.push('Sin conexión');
    if (cantidadPendientes > 0) partes.push(`${cantidadPendientes} pendiente${cantidadPendientes === 1 ? '' : 's'} de envío`);
    if (partes.length === 0) {
        pill.style.display = 'none';
        return;
    }
    pill.innerHTML = `<i class="fa-solid ${navigator.onLine ? 'fa-clock' : 'fa-wifi'}" aria-hidden="true"></i> ${partes.join(' · ')}`;
    pill.style.display = '';
}

export async function actualizarContadorPendientes() {
    try {
        const pendientes = await obtenerPendientesPropios();
        cantidadPendientes = pendientes.length;
        ponerBadge('badge-pendientes', cantidadPendientes);
        ponerBadge('nav-badge-pendientes', cantidadPendientes);
        actualizarPillConexion();
    } catch (err) {
        console.error('Error contando pendientes:', err);
    }
}

// ==========================================
// Envío de la cola al servidor
// ==========================================
function armarFormData(payload) {
    const formData = new FormData();
    if (payload.tipo === 'regulador') {
        const excluidos = ['tipo', 'foto_frontal', 'foto_entorno', 'foto_control_unico',
            'mediciones_termografia', 'ensayos_pat', 'estado_sync', 'timestamp_local',
            'ultimo_error', 'responsable', 'propietario'];
        for (const key in payload) {
            if (!excluidos.includes(key) && payload[key] !== null && payload[key] !== undefined) {
                formData.append(key, payload[key]);
            }
        }
        if (payload.foto_frontal) formData.append('foto_frontal', payload.foto_frontal);
        if (payload.foto_entorno) formData.append('foto_entorno', payload.foto_entorno);
        if (payload.foto_control_unico) formData.append('foto_control_unico', payload.foto_control_unico);
        if (payload.mediciones_termografia) formData.append('mediciones_termografia', JSON.stringify(payload.mediciones_termografia));
        if (payload.ensayos_pat) formData.append('ensayos_pat', JSON.stringify(payload.ensayos_pat));
        return { endpoint: '/api/operaciones/verificaciones/', formData };
    }

    formData.append('id_verificacion', payload.id_verificacion);
    formData.append('client_uuid', payload.client_uuid);
    formData.append('equipo_etc', payload.equipo_etc);
    formData.append('fecha_verificacion', payload.fecha_verificacion);
    formData.append('tiene_inconveniente', payload.tiene_inconveniente);
    formData.append('observaciones', payload.observaciones || '');
    formData.append('requiere_reclamo', payload.requiere_reclamo || false);
    formData.append('prioridad', payload.prioridad || '');
    if (payload.fallas) payload.fallas.forEach((id) => formData.append('fallas', id));
    if (payload.foto) formData.append('foto', payload.foto);
    ['gps_latitud', 'gps_longitud', 'gps_precision_m'].forEach((campo) => {
        if (payload[campo] !== undefined && payload[campo] !== null) formData.append(campo, payload[campo]);
    });
    return { endpoint: '/api/operaciones/verificaciones-etc/', formData };
}

export async function sincronizarPendientes(esManual = false) {
    if (isSyncing) return;

    if (!navigator.onLine) {
        if (esManual) showToast('No hay conexión a internet.', 'error');
        return;
    }

    console.log('[Sync] Iniciando sincronización. ¿Es manual?:', esManual);
    isSyncing = true;
    let datosSincronizados = false;

    try {
        // 1. Reclamos marcados como resueltos sin señal en versiones anteriores:
        // ahora finalizar exige foto y validación del supervisor, así que no se envían solos.
        const resueltosViejos = leerReclamosResueltosOffline();
        if (resueltosViejos.length > 0) {
            localStorage.removeItem('sigver_reclamos_resueltos');
            showToast(`${resueltosViejos.length} reclamo(s) marcados sin señal deben finalizarse de nuevo con foto.`, 'warning');
        }

        // 2. Verificaciones. Las rechazadas por el servidor (estado 'error')
        // solo se reintentan manualmente.
        const pendientes = (await obtenerPendientesPropios())
            .filter((p) => esManual || p.estado_sync !== 'error');

        if (pendientes.length > 0) {
            if (esManual) showToast(`Sincronizando ${pendientes.length} verificaciones...`, 'warning');
            datosSincronizados = true;
        }

        for (const payload of pendientes) {
            const { endpoint, formData } = armarFormData(payload);
            const res = await fetchConTimeout(endpoint, { method: 'POST', body: formData }, 30000);
            if (res.ok) {
                // 201 = creada; 200 = ya existía (reenvío idempotente por client_uuid)
                await eliminarDeOutbox(payload.client_uuid);
            } else if (res.status === 400 || res.status === 403) {
                // Queda guardada y marcada para revisión (antes se perdía sin aviso)
                const detalle = await describirErrorServidor(res);
                console.error('[Sync] Rechazada por el servidor:', payload.client_uuid, detalle);
                await guardarVerificacionOffline({ ...payload, estado_sync: 'error', ultimo_error: detalle });
                showToast(`Una verificación fue rechazada: ${detalle}`, 'error');
            }
        }

        if (datosSincronizados) {
            showToast(esManual ? 'Sincronización completada.' : 'Datos actualizados en el servidor (Automático).', 'success');
        } else if (esManual) {
            showToast('No hay datos pendientes para enviar.', 'warning');
        }
    } catch (err) {
        console.error('[Sync] Error:', err);
        if (esManual) showToast('Red inestable. Intentá de nuevo.', 'error');
    } finally {
        isSyncing = false;
        actualizarContadorPendientes();
    }
}

registrarAcciones({
    'sincronizar': () => sincronizarPendientes(true),
});

// ==========================================
// Detección de conexión y sincronización automática
// ==========================================
function actualizarEstadoConexion() {
    const badge = document.getElementById('status-badge');
    if (badge) {
        badge.style.display = 'inline-flex';
        if (navigator.onLine) {
            badge.classList.remove('offline');
            badge.textContent = 'En línea';
        } else {
            badge.classList.add('offline');
            badge.textContent = 'Sin conexión';
        }
    }
    // Si vuelve la red, esperamos 2 segundos para que la antena estabilice
    if (navigator.onLine) setTimeout(() => sincronizarPendientes(false), 2000);
    actualizarPillConexion();
}

// Sin almacenamiento persistente, Android puede vaciar IndexedDB cuando le
// falta espacio y se perderían las verificaciones guardadas sin señal.
// Chrome lo concede solo a la app instalada o muy usada; si lo niega, se vuelve
// a pedir en el próximo inicio.
async function pedirAlmacenamientoPersistente() {
    try {
        if (!navigator.storage?.persist || await navigator.storage.persisted()) return;
        const concedido = await navigator.storage.persist();
        console.info('[Sync] Almacenamiento persistente:', concedido ? 'concedido' : 'no concedido');
    } catch (err) {
        console.warn('[Sync] No se pudo pedir almacenamiento persistente:', err);
    }
}

export function iniciarSincronizacion() {
    pedirAlmacenamientoPersistente();
    window.addEventListener('online', actualizarEstadoConexion);
    window.addEventListener('offline', actualizarEstadoConexion);
    actualizarEstadoConexion();

    // Al iniciar, comprobar si hay datos pendientes
    setTimeout(actualizarContadorPendientes, 3000);

    // Al volver a la app (desbloquear el celular, cambiar de pestaña)
    document.addEventListener('visibilitychange', () => {
        if (document.visibilityState === 'visible' && navigator.onLine) {
            sincronizarPendientes(false);
        }
    });

    // Vigilante silencioso cada 20 segundos
    setInterval(async () => {
        if (!navigator.onLine || isSyncing) return;
        const reintentables = (await obtenerPendientesPropios()).filter((p) => p.estado_sync !== 'error');
        if (reintentables.length > 0 || leerReclamosResueltosOffline().length > 0) {
            sincronizarPendientes(false);
        }
    }, 20000);
}
