/**
 * SIGVER - Reclamos: lista por pestañas (con caché para ver sin señal) y
 * envío de la evidencia del técnico para que el supervisor valide en el admin.
 */
import { estado } from './estado.js?v=123';
import { fetchConToken, fetchConTimeout, esErrorDeRed, describirErrorServidor } from './api.js?v=123';
import { comprimirImagen, escapeHtml } from './util.js?v=123';
import {
    abrirModal, abrirPanel, cerrarMenu, cerrarModal, esEscritorio, marcarNav, menuAbierto, ponerBadge,
    registrarAcciones, showToast,
} from './ui.js?v=123';
import { esGestor } from './sesion.js?v=123';
import { cerrarTarjetaEquipo } from './mapa.js?v=123';

const GRUPOS_RECLAMOS = {
    abiertos: ['ABIERTO', 'ASIGNADO'],
    proceso: ['EN_PROCESO', 'PENDIENTE_VALIDACION'],
    cerrados: ['CERRADO', 'RECHAZADO'],
};
const NOMBRE_PESTANA = { abiertos: 'Abiertos', proceso: 'En proceso', cerrados: 'Cerrados' };
const TEXTO_VACIO = {
    abiertos: 'No hay reclamos abiertos.',
    proceso: 'No hay reclamos en proceso.',
    cerrados: 'Todavía no hay reclamos cerrados.',
};
const CLASE_PRIORIDAD = { CRITICA: 'chip-critica', ALTA: 'chip-alta', MEDIA: 'chip-media', BAJA: 'chip-baja' };
const TEXTO_PRIORIDAD = { CRITICA: 'Crítica', ALTA: 'Alta', MEDIA: 'Media', BAJA: 'Baja' };

let ultimosReclamos = [];
let pestanaReclamos = 'abiertos';
let reclamoAValidarId = null;

// ==========================================
// Lista
// ==========================================
export async function cargarMisReclamos({ silencioso = false } = {}) {
    const contenedor = document.getElementById('lista-reclamos');
    if (!silencioso) contenedor.innerHTML = '<div class="empty-state">Buscando reclamos...</div>';

    // Sin internet: lo último guardado en el celular
    if (!navigator.onLine) {
        const guardados = localStorage.getItem('sigver_reclamos_cache');
        if (guardados) {
            renderizarListaReclamos(JSON.parse(guardados));
        } else {
            contenedor.innerHTML = '<div class="empty-state error"><i class="fa-solid fa-wifi" aria-hidden="true"></i>Sin conexión y sin reclamos guardados en este dispositivo.</div>';
        }
        return;
    }

    try {
        renderizarListaReclamos(await traerReclamos());
    } catch (err) {
        console.error('Error en reclamos:', err);
        contenedor.innerHTML = '<div class="empty-state error"><i class="fa-solid fa-circle-exclamation" aria-hidden="true"></i>No se pudieron cargar los reclamos. Intentá de nuevo.</div>';
    }
}

// Baja la lista y la guarda para verla sin señal. Devuelve la lista.
async function traerReclamos() {
    // El servidor ya filtra por rol. Al técnico le acotamos a "sus" reclamos;
    // el supervisor ve todos los de sus agencias.
    const personalId = estado.usuario?.personal_id;
    const filtro = personalId && !esGestor()
        ? `?responsable_asignado=${encodeURIComponent(personalId)}`
        : '';
    const res = await fetchConToken(`/api/operaciones/reclamos/${filtro}`);
    if (!res.ok) throw new Error('Error HTTP: ' + res.status);
    const data = await res.json();
    const reclamos = data.results || data;
    localStorage.setItem('sigver_reclamos_cache', JSON.stringify(reclamos));
    return reclamos;
}

// ==========================================
// Aviso de reclamos nuevos: al abrir la app, al volver a ella y cada 5 minutos
// (sin notificaciones push: solo mientras la app está abierta)
// ==========================================
const ESTADOS_PENDIENTES = ['ABIERTO', 'ASIGNADO', 'EN_PROCESO'];
const CADA_CUANTO_REVISAR_MS = 5 * 60 * 1000;
let ultimaRevision = 0;
let avisoIniciado = false;

function leerCacheReclamos() {
    try {
        return JSON.parse(localStorage.getItem('sigver_reclamos_cache') || 'null');
    } catch {
        return null;
    }
}

export async function revisarReclamosNuevos() {
    if (!navigator.onLine) {
        const guardados = leerCacheReclamos();
        if (guardados) actualizarContador(guardados);
        return;
    }
    ultimaRevision = Date.now();
    const anteriores = leerCacheReclamos();
    try {
        const reclamos = await traerReclamos();
        actualizarContador(reclamos);
        if (anteriores) {
            // Nuevos para mí = no estaban en la lista anterior (o volvieron a mis manos)
            const antes = new Map(anteriores.map((r) => [r.id, r.estado]));
            const nuevos = reclamos.filter((r) => ESTADOS_PENDIENTES.includes(r.estado)
                && (!antes.has(r.id) || !ESTADOS_PENDIENTES.includes(antes.get(r.id))));
            if (nuevos.length === 1) {
                showToast(`Tenés un reclamo nuevo: ${nuevos[0].equipo_nro ? 'ETC ' + nuevos[0].equipo_nro : nuevos[0].id_reclamo}.`, 'warning');
            } else if (nuevos.length > 1) {
                showToast(`Tenés ${nuevos.length} reclamos nuevos.`, 'warning');
            }
        }
        // Si la lista está abierta, se actualiza sin que el técnico la recargue
        if (document.getElementById('sheet-reclamos')?.classList.contains('active')) {
            renderizarListaReclamos(reclamos);
        }
    } catch (err) {
        console.warn('[Reclamos] No se pudo revisar si hay nuevos:', err);
    }
}

export function iniciarAvisoReclamos() {
    revisarReclamosNuevos();
    if (avisoIniciado) return;
    avisoIniciado = true;
    const revisarSiCorresponde = () => {
        if (document.visibilityState === 'visible' && Date.now() - ultimaRevision > 60000) {
            revisarReclamosNuevos();
        }
    };
    document.addEventListener('visibilitychange', revisarSiCorresponde);
    window.addEventListener('online', revisarSiCorresponde);
    setInterval(() => {
        if (document.visibilityState === 'visible') revisarReclamosNuevos();
    }, CADA_CUANTO_REVISAR_MS);
}

function actualizarContador(reclamos) {
    const n = reclamos.filter((r) => ESTADOS_PENDIENTES.includes(r.estado)).length;
    ponerBadge('nav-badge-reclamos', n);
}

function htmlReclamo(r) {
    const prioridad = (r.prioridad || '').toUpperCase();
    const enValidacion = r.estado === 'PENDIENTE_VALIDACION';
    const estadoTexto = enValidacion ? 'en validación' : (r.estado || '').replace(/_/g, ' ').toLowerCase();
    const fecha = r.fecha_reclamo ? new Date(r.fecha_reclamo).toLocaleDateString('es-PY') : '';
    const plazo = htmlPlazo(r);
    const equipo = r.equipo_nro ? `<span class="reclamo-equipo">ETC ${escapeHtml(r.equipo_nro)}</span>` : '';

    // Si el supervisor lo devolvió, el técnico ve qué tiene que corregir
    const devolucion = r.estado === 'EN_PROCESO' ? ultimaDevolucion(r) : null;
    const aviso = devolucion
        ? `<div class="popup-nota aviso"><i class="fa-solid fa-rotate-left" aria-hidden="true"></i> Devuelto por ${escapeHtml(devolucion.usuario_nombre)}: ${escapeHtml(devolucion.comentario)}</div>`
        : '';
    const rechazo = r.estado === 'RECHAZADO' && r.motivo_rechazo
        ? `<div class="popup-nota"><i class="fa-solid fa-ban" aria-hidden="true"></i> Rechazado: ${escapeHtml(r.motivo_rechazo)}</div>`
        : '';

    let pie = '';
    const esMio = r.responsable_asignado && r.responsable_asignado === estado.usuario?.personal_id;
    if (enValidacion) {
        pie = '<div class="popup-nota"><i class="fa-solid fa-user-check" aria-hidden="true"></i> Esperando que el supervisor lo valide.</div>';
    } else if (esMio && r.estado === 'EN_PROCESO') {
        pie = `<button type="button" class="btn btn-success btn-block solo-campo" data-accion="finalizar-reclamo" data-id="${escapeHtml(r.id)}">
                    <i class="fa-solid fa-check" aria-hidden="true"></i> Finalizar reclamo
                </button>`;
    } else if (esMio && ['ABIERTO', 'ASIGNADO'].includes(r.estado)) {
        pie = `<button type="button" class="btn btn-primary btn-block solo-campo" data-accion="iniciar-reclamo" data-id="${escapeHtml(r.id)}">
                    <i class="fa-solid fa-play" aria-hidden="true"></i> Iniciar trabajo
                </button>`;
    }

    return `
        <article class="reclamo-card">
            <div class="reclamo-meta">
                <span class="chip ${CLASE_PRIORIDAD[prioridad] || ''}">${prioridad === 'CRITICA' ? '<i class="fa-solid fa-triangle-exclamation" aria-hidden="true"></i>' : ''}${escapeHtml(TEXTO_PRIORIDAD[prioridad] || prioridad)}</span>
                <span class="chip ${enValidacion ? 'chip-sync' : ''}" style="text-transform: capitalize;">${enValidacion ? '<i class="fa-solid fa-hourglass-half" aria-hidden="true"></i>' : ''}${escapeHtml(estadoTexto)}</span>
                ${plazo}
                <span class="reclamo-fecha">${escapeHtml(fecha)}</span>
            </div>
            <div>
                <div class="reclamo-titulo">${equipo}${escapeHtml(r.id_reclamo)}</div>
                <div class="reclamo-desc">${escapeHtml(r.descripcion)}</div>
            </div>
            ${aviso}${rechazo}
            ${pie}
        </article>`;
}

// Plazo según la prioridad (lo calcula el servidor). Solo mientras el trabajo
// está pendiente: en validación o terminado ya no corre.
const ESTADOS_CON_PLAZO = ['ABIERTO', 'ASIGNADO', 'EN_PROCESO'];

function textoDuracion(ms) {
    const horas = Math.floor(ms / 3600000);
    if (horas >= 24) return `${Math.floor(horas / 24)} d`;
    if (horas >= 1) return `${horas} h`;
    return `${Math.max(1, Math.floor(ms / 60000))} min`;
}

function htmlPlazo(r) {
    if (!r.fecha_limite || !ESTADOS_CON_PLAZO.includes(r.estado)) return '';
    const restante = new Date(r.fecha_limite) - Date.now();
    if (restante < 0) {
        return `<span class="chip chip-critica"><i class="fa-solid fa-hourglass-end" aria-hidden="true"></i>Vencido hace ${textoDuracion(-restante)}</span>`;
    }
    const clase = restante < 86400000 ? 'chip-alta' : '';
    return `<span class="chip ${clase}"><i class="fa-solid fa-hourglass-half" aria-hidden="true"></i>Vence en ${textoDuracion(restante)}</span>`;
}

function ultimaDevolucion(r) {
    const historial = r.historial || [];
    for (let i = historial.length - 1; i >= 0; i--) {
        const h = historial[i];
        if (h.estado_anterior === 'PENDIENTE_VALIDACION' && h.estado_nuevo === 'EN_PROCESO') return h;
        if (h.estado_nuevo) return null;   // hubo otro cambio de estado después
    }
    return null;
}

function renderizarListaReclamos(reclamos) {
    const contenedor = document.getElementById('lista-reclamos');
    const sub = document.getElementById('reclamos-sub');

    ultimosReclamos = reclamos;
    const contar = (grupo) => reclamos.filter((r) => GRUPOS_RECLAMOS[grupo].includes(r.estado)).length;
    const nAbiertos = contar('abiertos');
    actualizarContador(reclamos);
    if (sub) sub.textContent = nAbiertos === 1 ? '1 abierto' : `${nAbiertos} abiertos`;

    document.querySelectorAll('.tabs-reclamos .tab').forEach((t) => {
        const grupo = t.dataset.tab;
        const n = grupo === 'cerrados' ? 0 : contar(grupo);
        t.textContent = n > 0 ? `${NOMBRE_PESTANA[grupo]} · ${n}` : NOMBRE_PESTANA[grupo];
        t.classList.toggle('activo', grupo === pestanaReclamos);
    });

    const visibles = reclamos.filter((r) => GRUPOS_RECLAMOS[pestanaReclamos].includes(r.estado));
    // Primero los que requieren acción; al final los que esperan validación
    visibles.sort((a, b) => (a.estado === 'PENDIENTE_VALIDACION') - (b.estado === 'PENDIENTE_VALIDACION'));

    contenedor.innerHTML = visibles.length
        ? visibles.map(htmlReclamo).join('')
        : `<div class="empty-state ok"><i class="fa-solid fa-circle-check" aria-hidden="true"></i>${TEXTO_VACIO[pestanaReclamos]}</div>`;
}

document.querySelector('.tabs-reclamos').addEventListener('click', (e) => {
    const tab = e.target.closest('.tab');
    if (!tab) return;
    pestanaReclamos = tab.dataset.tab;
    renderizarListaReclamos(ultimosReclamos);
});

export function abrirReclamos() {
    const estabaAbiertoElMenu = menuAbierto();
    cerrarMenu();
    cerrarTarjetaEquipo();
    marcarNav('reclamos');
    setTimeout(() => {
        abrirPanel('sheet-reclamos');
        cargarMisReclamos();
    }, estabaAbiertoElMenu && !esEscritorio() ? 300 : 0);
}

// ==========================================
// Evidencia del técnico: «Iniciar trabajo» (foto del estado inicial) y
// «Finalizar» (foto del trabajo terminado + ubicación). El supervisor valida en el admin.
// ==========================================
const MODOS_EVIDENCIA = {
    iniciar: {
        titulo: 'Iniciar trabajo',
        texto: 'Sacá una foto de cómo encontraste el equipo antes de intervenir.',
        foto: 'Foto del estado inicial',
        boton: 'Iniciar trabajo',
        estado: 'EN_PROCESO',
        campoFoto: 'foto_evidencia_antes',
        exito: 'Trabajo iniciado.',
    },
    finalizar: {
        titulo: 'Finalizar reclamo',
        texto: 'El supervisor va a revisar la foto y la ubicación antes de cerrar el reclamo.',
        foto: 'Foto del trabajo terminado',
        boton: 'Enviar a validación',
        estado: 'PENDIENTE_VALIDACION',
        campoFoto: 'foto_evidencia_despues',
        exito: 'Reclamo enviado a validación del supervisor.',
    },
};
let modoEvidencia = 'finalizar';
let posicionEvidencia = null;   // {lat, lng, precision} del GPS

function abrirModalEvidencia(reclamoId, modo) {
    const m = MODOS_EVIDENCIA[modo];
    reclamoAValidarId = reclamoId;
    modoEvidencia = modo;
    document.getElementById('titulo-evidencia').textContent = m.titulo;
    document.getElementById('evidencia-texto').textContent = m.texto;
    document.getElementById('evidencia-foto-titulo').textContent = m.foto;
    document.getElementById('btn-enviar-validacion').textContent = m.boton;
    document.getElementById('evidencia-grupo-obs').style.display = modo === 'finalizar' ? '' : 'none';
    document.getElementById('reclamo-obs-cierre').value = '';
    document.getElementById('reclamo-foto-cierre').value = '';
    const preview = document.getElementById('reclamo-foto-preview');
    preview.removeAttribute('src');
    preview.style.display = 'none';
    document.querySelector('#reclamo-foto-label span').textContent = 'Tomar o elegir foto';
    abrirModal('modal-evidencia-reclamo', { alCerrar: cerrarModalEvidencia });
    if (modo === 'finalizar') tomarUbicacion();
    else mostrarGps('');
}

function cerrarModalEvidencia() {
    cerrarModal('modal-evidencia-reclamo');
    reclamoAValidarId = null;
    posicionEvidencia = null;
}

function mostrarGps(texto, ok = false) {
    const p = document.getElementById('evidencia-gps');
    p.classList.toggle('ok', ok);
    p.innerHTML = texto;
}

// La ubicación prueba que el trabajo se hizo en el lugar. Si el GPS no
// responde se puede enviar igual: el supervisor lo ve como «sin GPS».
function tomarUbicacion() {
    posicionEvidencia = null;
    if (!navigator.geolocation) {
        mostrarGps('<i class="fa-solid fa-location-crosshairs" aria-hidden="true"></i> Este dispositivo no tiene GPS: se enviará sin ubicación.');
        return;
    }
    mostrarGps('<span class="spinner"></span> Obteniendo tu ubicación...');
    const idReclamo = reclamoAValidarId;
    navigator.geolocation.getCurrentPosition((pos) => {
        if (reclamoAValidarId !== idReclamo) return;   // el modal ya se cerró
        posicionEvidencia = {
            lat: pos.coords.latitude, lng: pos.coords.longitude, precision: pos.coords.accuracy,
        };
        mostrarGps(`<i class="fa-solid fa-location-dot" aria-hidden="true"></i> Ubicación lista (±${Math.round(pos.coords.accuracy)} m)`, true);
    }, () => {
        if (reclamoAValidarId !== idReclamo) return;
        mostrarGps('<i class="fa-solid fa-location-crosshairs" aria-hidden="true"></i> Sin ubicación GPS: se enviará igual, el supervisor lo verá.');
    }, { enableHighAccuracy: true, timeout: 20000, maximumAge: 60000 });
}

document.getElementById('reclamo-foto-cierre').addEventListener('change', (e) => {
    const file = e.target.files[0];
    const preview = document.getElementById('reclamo-foto-preview');
    if (!file) {
        preview.style.display = 'none';
        return;
    }
    const reader = new FileReader();
    reader.onload = (ev) => {
        preview.src = ev.target.result;
        preview.style.display = 'block';
    };
    reader.readAsDataURL(file);
    document.querySelector('#reclamo-foto-label span').textContent = 'Cambiar foto';
});

document.getElementById('btn-cancelar-evidencia').addEventListener('click', cerrarModalEvidencia);

document.getElementById('btn-enviar-validacion').addEventListener('click', async () => {
    const btn = document.getElementById('btn-enviar-validacion');
    const archivo = document.getElementById('reclamo-foto-cierre').files[0];
    const m = MODOS_EVIDENCIA[modoEvidencia];

    if (!reclamoAValidarId) return;
    if (!archivo) {
        showToast(`Falta la ${m.foto.toLowerCase()}.`, 'error');
        return;
    }
    // Solo en línea: así nos aseguramos de que la foto llegue al servidor
    if (!navigator.onLine) {
        showToast('Sin conexión. Intentá de nuevo cuando tengas señal.', 'warning');
        return;
    }

    btn.disabled = true;
    btn.innerHTML = '<span class="spinner"></span> Enviando...';

    try {
        const foto = await comprimirImagen(archivo);
        const formData = new FormData();
        formData.append('estado', m.estado);
        formData.append(m.campoFoto, foto, foto.name || `${m.campoFoto}_${reclamoAValidarId}.jpg`);
        if (modoEvidencia === 'finalizar') {
            formData.append('observaciones_cierre', document.getElementById('reclamo-obs-cierre').value.trim());
            if (posicionEvidencia) {
                formData.append('gps_latitud', posicionEvidencia.lat);
                formData.append('gps_longitud', posicionEvidencia.lng);
                formData.append('gps_precision_m', posicionEvidencia.precision);
            }
        }
        // Las horas (inicio y ejecución) las pone el servidor: el reloj del celular puede estar mal

        // Sin Content-Type: el navegador arma el multipart con su boundary
        const res = await fetchConTimeout(`/api/operaciones/reclamos/${reclamoAValidarId}/`, {
            method: 'PATCH',
            body: formData,
        }, 30000);

        if (res.ok) {
            showToast(m.exito, 'success');
            cerrarModalEvidencia();
            cargarMisReclamos();
        } else {
            showToast('No se pudo enviar: ' + await describirErrorServidor(res), 'error');
        }
    } catch (err) {
        if (esErrorDeRed(err)) {
            showToast('Se cortó la conexión. Intentá de nuevo cuando tengas señal.', 'warning');
        } else {
            showToast('Error inesperado: ' + err.message, 'error');
        }
    } finally {
        btn.disabled = false;
        btn.textContent = m.boton;
    }
});

registrarAcciones({
    'abrir-reclamos': abrirReclamos,
    'recargar-reclamos': () => cargarMisReclamos(),
    'iniciar-reclamo': (el) => abrirModalEvidencia(el.dataset.id, 'iniciar'),
    'finalizar-reclamo': (el) => abrirModalEvidencia(el.dataset.id, 'finalizar'),
});
