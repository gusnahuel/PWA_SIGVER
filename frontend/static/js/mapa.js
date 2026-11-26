/**
 * SIGVER - Mapa: capas, marcadores con clustering, filtros, tarjeta del
 * equipo (celular), popup (escritorio) y "mi ubicación".
 */
import { estado } from './estado.js?v=123';
import { fetchConToken } from './api.js?v=123';
import { escapeHtml, haceCuanto } from './util.js?v=123';
import { cerrarMenu, esEscritorio, registrarAcciones, setStatus, showToast } from './ui.js?v=123';
import { abrirFormularioVerificacion } from './verificacion-etc.js?v=123';
import { abrirFormularioRegulador } from './verificacion-regulador.js?v=123';

const API_INVENTARIO = '/api/inventario';
const CENTRO_PARAGUAY = [-27.16, -56.24];
const ZOOM_INICIAL = 10;
const DIAS_SIN_VERIFICAR = 30;
const ESTADOS_SITIO_PROBLEMA = ['OBSERVADO', 'CRITICO', 'FUERA_SERVICIO'];

let controlCapas = null;
let capaETCs = null;
let capaSitios = null;
let marcadoresETC = [];     // [{ marker, props }]
let marcadoresSitios = [];
let filtroMapa = 'todos';
let marcadorUsuario = null;

// ==========================================
// Reglas de negocio del mapa
// ==========================================
function tieneProblema(props) {
    return props.tipo === 'REGULADOR'
        ? ESTADOS_SITIO_PROBLEMA.includes(props.estado_general)
        : !!props.tiene_problema_actual;
}

function sinVerificar(props) {
    if (props.tipo === 'REGULADOR') return false; // el inventario de sitios no informa la fecha
    if (!props.fecha_ultima_verificacion) return true;
    const dias = (Date.now() - new Date(props.fecha_ultima_verificacion)) / 86400000;
    return dias > DIAS_SIN_VERIFICAR;
}

// ==========================================
// Íconos
// ==========================================
function createEtcIcon(props) {
    const abierto = props.estado_seccionador === 'ABIERTO';
    const clases = ['pin', 'pin-etc', abierto ? 'abierto' : '', props.tiene_problema_actual ? 'problema' : ''].join(' ');
    return L.divIcon({
        html: `<div class="${clases}"><i class="fa-solid fa-bolt" aria-hidden="true"></i></div>`,
        className: '',
        iconSize: [28, 28],
        iconAnchor: [14, 14],
        popupAnchor: [0, -14],
    });
}

function createReguladorIcon(props = {}) {
    const problema = ESTADOS_SITIO_PROBLEMA.includes(props.estado_general);
    return L.divIcon({
        html: `<div class="pin pin-reg ${problema ? 'problema' : ''}">R</div>`,
        className: '',
        iconSize: [28, 28],
        iconAnchor: [14, 14],
        popupAnchor: [0, -14],
    });
}

// Clusters neutros; borde rojo si adentro hay equipos con problema
function clusterIcon(cluster) {
    const count = cluster.getChildCount();
    const dim = count < 10 ? 38 : count < 50 ? 44 : 50;
    const conProblema = cluster.getAllChildMarkers().some((m) => m.options.conProblema);
    return L.divIcon({
        html: `<div class="pin-cluster ${conProblema ? 'con-problema' : ''}" style="width: ${dim}px; height: ${dim}px; font-size: ${count < 50 ? 14 : 15}px;">${count}</div>`,
        className: '',
        iconSize: [dim, dim],
    });
}

// ==========================================
// Mapa base y capas
// ==========================================
function crearMapa() {
    const map = L.map('map', {
        center: CENTRO_PARAGUAY,
        zoom: ZOOM_INICIAL,
        zoomControl: false,
    });

    const mapaSatelital = L.tileLayer(
        'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
        { maxZoom: 19, attribution: '&copy; Esri &mdash; SIGVER ANDE' }
    ).addTo(map);

    // Nombres de ciudades, rutas y límites (activada por defecto)
    const etiquetas = L.tileLayer(
        'https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}',
        { maxZoom: 19 }
    ).addTo(map);

    const calles = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 19 });

    controlCapas = L.control.layers(
        { 'Satelital (Esri)': mapaSatelital, 'Calles (OSM)': calles },
        { 'Nombres de Ciudades': etiquetas },
        { position: 'topright', collapsed: true }
    ).addTo(map);

    L.control.zoom({ position: 'bottomleft' }).addTo(map);
    return map;
}

function crearCapaCluster(extra = {}) {
    return L.markerClusterGroup({
        maxClusterRadius: 120,
        showCoverageOnHover: false,
        zoomToBoundsOnClick: true,
        spiderfyOnMaxZoom: true,
        disableClusteringAtZoom: 14,
        chunkedLoading: true,
        iconCreateFunction: clusterIcon,
        ...extra,
    });
}

// ==========================================
// Carga de equipos
// ==========================================
async function cargarCapa(ruta, tipo, crearIcono) {
    const res = await fetchConToken(`${API_INVENTARIO}/${ruta}/`);
    if (!res.ok) throw new Error(`Error HTTP ${res.status}`);
    const features = (await res.json()).features || [];

    const marcadores = [];
    features.forEach((f) => {
        if (!f.geometry) return; // sin coordenadas cargadas
        const [lng, lat] = f.geometry.coordinates;
        const p = { ...f.properties, tipo };
        f.properties = p;
        const marker = L.marker([lat, lng], { icon: crearIcono(p), conProblema: tieneProblema(p) });
        marker.on('click', () => alHacerClicEnEquipo(f, marker));
        marcadores.push({ marker, props: p });
    });
    return { features, marcadores };
}

async function cargarETCs() {
    const { features, marcadores } = await cargarCapa('equipos', 'ETC', createEtcIcon);
    estado.equipos = features;
    marcadoresETC = marcadores;
    return features.length;
}

async function cargarSitios() {
    const { features, marcadores } = await cargarCapa('sitios', 'REGULADOR', createReguladorIcon);
    estado.sitios = features;
    marcadoresSitios = marcadores;
    return features.length;
}

// Crea el mapa, las capas y carga los equipos. Devuelve la cantidad cargada.
export async function iniciarMapa() {
    const map = crearMapa();
    estado.mapa = map;
    capaETCs = crearCapaCluster({ chunkInterval: 100, chunkDelay: 50 }).addTo(map);
    capaSitios = crearCapaCluster().addTo(map);
    map.on('click', () => cerrarTarjetaEquipo());

    setStatus('Cargando...');
    const [nETCs, nSitios] = await Promise.all([cargarETCs(), cargarSitios()]);
    aplicarFiltroMapa();
    setStatus(`${nETCs + nSitios} equipos`);

    controlCapas.addOverlay(capaETCs, 'ETCs (Telecomandados)');
    controlCapas.addOverlay(capaSitios, 'Reguladores');
    return nETCs + nSitios;
}

// ==========================================
// Filtros (chips sobre el mapa)
// ==========================================
function aplicarFiltroMapa() {
    if (!capaETCs || !capaSitios) return;
    const pasa = (props) => {
        switch (filtroMapa) {
            case 'problemas': return tieneProblema(props);
            case 'sin_verificar': return sinVerificar(props);
            case 'reguladores': return props.tipo === 'REGULADOR';
            case 'etc': return props.tipo === 'ETC';
            default: return true;
        }
    };
    capaETCs.clearLayers();
    capaSitios.clearLayers();
    const etcs = marcadoresETC.filter((m) => pasa(m.props)).map((m) => m.marker);
    const sitios = marcadoresSitios.filter((m) => pasa(m.props)).map((m) => m.marker);
    capaETCs.addLayers(etcs);
    capaSitios.addLayers(sitios);
    if (filtroMapa !== 'todos' && etcs.length + sitios.length === 0) {
        showToast('Ningún equipo cumple este filtro.', 'warning');
    }
}

document.getElementById('filtros-mapa').addEventListener('click', (e) => {
    const chip = e.target.closest('.filtro-chip');
    if (!chip) return;
    filtroMapa = chip.dataset.filtro;
    document.querySelectorAll('.filtro-chip').forEach((c) => c.classList.toggle('activo', c === chip));
    cerrarTarjetaEquipo();
    aplicarFiltroMapa();
});

// ==========================================
// Detalle del equipo: popup en escritorio, tarjeta en el celular
// ==========================================
function htmlPopupEscritorio(f) {
    const p = f.properties;
    const esReg = p.tipo === 'REGULADOR';
    const filas = esReg
        ? [['fa-barcode', 'Código', p.cod_sitio], ['fa-tower-broadcast', 'Alimentador', p.alimentador_codigo],
           ['fa-circle-info', 'Estado', p.estado_general || 'Sin dato']]
        : [['fa-tower-broadcast', 'Alimentador', p.alimentador_codigo], ['fa-circle-info', 'Estado', p.estado_seccionador],
           ['fa-calendar-check', 'Última verif.', haceCuanto(p.fecha_ultima_verificacion)]];
    return `
        <div class="modern-popup">
            <div class="popup-header ${esReg ? 'header-regulador' : 'header-etc'}">
                <i class="fa-solid ${esReg ? 'fa-plug' : 'fa-bolt'}" aria-hidden="true"></i>
                ${esReg ? 'Regulador ' + escapeHtml(p.id_sitio) : 'ETC ' + escapeHtml(p.nro_equipo)}
            </div>
            <div class="popup-body">
                ${filas.map(([icono, label, valor]) => `
                    <div class="popup-row">
                        <span class="popup-label"><i class="fa-solid ${icono}" aria-hidden="true"></i> ${label}</span>
                        <span class="popup-value">${escapeHtml(valor ?? '-')}</span>
                    </div>`).join('')}
            </div>
            <div class="popup-footer">
                <div class="popup-nota"><i class="fa-solid fa-mobile-screen" aria-hidden="true"></i> La verificación se carga desde el celular.</div>
            </div>
        </div>`;
}

function alHacerClicEnEquipo(f, marker) {
    if (esEscritorio()) {
        L.popup().setLatLng(marker.getLatLng()).setContent(htmlPopupEscritorio(f)).openOn(estado.mapa);
    } else {
        mostrarTarjetaEquipo(f);
    }
}

export function mostrarTarjetaEquipo(f) {
    const p = f.properties;
    const [lng, lat] = f.geometry.coordinates;
    const esReg = p.tipo === 'REGULADOR';
    const problema = tieneProblema(p);
    const destino = `https://www.google.com/maps/dir/?api=1&destination=${Number(lat)},${Number(lng)}`;

    let chip, datos, botonVerificar;
    if (esReg) {
        const estadoSitio = p.estado_general ? p.estado_general.replace('_', ' ').toLowerCase() : 'sin dato';
        chip = `<span class="chip ${problema ? 'chip-critica' : 'chip-ok'}" style="text-transform: capitalize;">${escapeHtml(estadoSitio)}</span>`;
        datos = [
            ['Alimentador', p.alimentador_codigo, ''],
            ['Código', p.cod_sitio || '-', ''],
            ['Banco', (p.configuracion_banco || '-').replace(/_/g, ' ').toLowerCase(), ''],
        ];
        botonVerificar = `data-accion="verificar-regulador" data-id="${escapeHtml(p.componente_id)}" data-codigo="${escapeHtml(p.id_sitio)}"`;
    } else {
        const abierto = p.estado_seccionador === 'ABIERTO';
        chip = `<span class="chip ${abierto ? 'chip-media' : 'chip-baja'}">${abierto ? 'Abierto' : 'Cerrado'}</span>`;
        datos = [
            ['Alimentador', p.alimentador_codigo, ''],
            ['Última verif.', haceCuanto(p.fecha_ultima_verificacion), sinVerificar(p) ? 'alerta' : ''],
            ['Estado', problema ? 'Con problema' : 'Sin problemas', problema ? 'alerta' : 'bien'],
        ];
        botonVerificar = `data-accion="verificar-etc" data-id="${escapeHtml(f.id)}" data-codigo="${escapeHtml(p.nro_equipo)}"`;
    }

    const tarjeta = document.getElementById('tarjeta-equipo');
    tarjeta.innerHTML = `
        <div class="tarjeta-cabecera">
            <span class="tarjeta-icono ${esReg ? 'reg' : ''}"><i class="fa-solid ${esReg ? 'fa-plug' : 'fa-bolt'}" aria-hidden="true"></i></span>
            <div style="flex: 1; min-width: 0;">
                <div class="tarjeta-tipo">${esReg ? 'Regulador' : 'Equipo telecomandado'}</div>
                <div class="tarjeta-nombre">${esReg ? escapeHtml(p.id_sitio) : 'ETC ' + escapeHtml(p.nro_equipo)}</div>
            </div>
            ${chip}
            <button type="button" class="icon-action tarjeta-cerrar" data-accion="cerrar-tarjeta" aria-label="Cerrar"><i class="fa-solid fa-xmark" aria-hidden="true"></i></button>
        </div>
        <div class="tarjeta-datos">
            ${datos.map(([label, valor, clase]) => `
                <div class="dato ${clase}"><div class="dato-label">${label}</div><div class="dato-valor" style="text-transform: ${label === 'Banco' ? 'capitalize' : 'none'};">${escapeHtml(valor ?? '-')}</div></div>`).join('')}
        </div>
        <div class="tarjeta-acciones">
            <a class="btn btn-outline" href="${destino}" target="_blank" rel="noopener">
                <i class="fa-solid fa-diamond-turn-right" aria-hidden="true"></i> Cómo llegar
            </a>
            <button type="button" class="btn btn-primary" ${botonVerificar}>
                <i class="fa-solid fa-clipboard-check" aria-hidden="true"></i> Verificar
            </button>
        </div>`;
    tarjeta.classList.add('visible');
    document.body.classList.add('con-tarjeta');
}

export function cerrarTarjetaEquipo() {
    document.getElementById('tarjeta-equipo').classList.remove('visible');
    document.body.classList.remove('con-tarjeta');
}

// ==========================================
// Ir a un equipo (desde la búsqueda) y "mi ubicación"
// ==========================================
export function volarAEquipo(lat, lng, tipo) {
    const lista = tipo === 'ETC' ? estado.equipos : estado.sitios;
    const feature = lista.find((f) => f.geometry
        && Number(f.geometry.coordinates[1]) === lat && Number(f.geometry.coordinates[0]) === lng);
    if (!esEscritorio()) {
        document.getElementById('search-sheet').classList.remove('active');
        if (feature) mostrarTarjetaEquipo(feature); // en el celular se abre la tarjeta del equipo
    }
    estado.mapa.flyTo([lat, lng], 17, { duration: 1.5 });
}

function centrarEnMiUbicacion() {
    cerrarMenu();
    if (!navigator.geolocation) {
        showToast('Tu navegador no soporta geolocalización.', 'error');
        return;
    }
    showToast('Obteniendo tu ubicación GPS...', 'warning');

    navigator.geolocation.getCurrentPosition(
        (position) => {
            const { latitude: lat, longitude: lng, accuracy: precision } = position.coords;
            if (marcadorUsuario) estado.mapa.removeLayer(marcadorUsuario);

            marcadorUsuario = L.circleMarker([lat, lng], {
                radius: 8,
                fillColor: '#0ea5e9',
                color: '#ffffff',
                weight: 3,
                opacity: 1,
                fillOpacity: 1
            }).addTo(estado.mapa);

            marcadorUsuario.bindPopup(`
                <div style="font-family: 'Inter', sans-serif; padding: 4px 8px; text-align: center;">
                    <div style="color: #0ea5e9; font-weight: 800; font-size: 13px; margin-bottom: 2px;">Mi Ubicación</div>
                    <div style="color: #64748b; font-size: 11px;">Precisión: <b>±${Math.round(precision)} m</b></div>
                </div>
            `);

            estado.mapa.flyTo([lat, lng], 18, { duration: 1.5 });
            showToast('Ubicación encontrada.', 'success');
        },
        (error) => {
            console.error('Error GPS:', error);
            showToast('No se pudo obtener la ubicación. Revisá los permisos.', 'error');
        },
        { enableHighAccuracy: true, timeout: 10000, maximumAge: 0 }
    );
}

registrarAcciones({
    'cerrar-tarjeta': cerrarTarjetaEquipo,
    'verificar-etc': (el) => { cerrarTarjetaEquipo(); abrirFormularioVerificacion(el.dataset.id, el.dataset.codigo); },
    'verificar-regulador': (el) => { cerrarTarjetaEquipo(); abrirFormularioRegulador(el.dataset.id, el.dataset.codigo); },
    'volar-a-equipo': (el) => volarAEquipo(Number(el.dataset.lat), Number(el.dataset.lng), el.dataset.tipo),
    'mi-ubicacion': centrarEnMiUbicacion,
});
