/**
 * SIGVER - Búsqueda de equipos (ETC y reguladores) por código, alimentador o subestación.
 */
import { estado } from './estado.js?v=121';
import { escapeHtml } from './util.js?v=121';
import { abrirPanel, cerrarMenu, esEscritorio, registrarAcciones } from './ui.js?v=121';
import { cerrarTarjetaEquipo } from './mapa.js?v=121';

const MIN_LETRAS = 2;
const MAX_RESULTADOS = 50; // más que esto traba los celulares de gama baja

function buscar(query, filtro) {
    const coincide = (...valores) => valores.some((v) => (v || '').toLowerCase().includes(query));
    const resultados = [];

    if (filtro === 'todos' || filtro === 'etc') {
        estado.equipos.forEach((f) => {
            if (!f.geometry) return;
            const p = f.properties;
            if (coincide(p.nro_equipo, p.alimentador_codigo, p.subestacion_codigo)) {
                resultados.push({
                    tipo: 'ETC',
                    titulo: `ETC ${p.nro_equipo}`,
                    subtitulo: `Subestación ${p.subestacion_codigo} | Alimentador ${p.alimentador_codigo}`,
                    coords: f.geometry.coordinates
                });
            }
        });
    }

    if (filtro === 'todos' || filtro === 'regulador') {
        estado.sitios.forEach((f) => {
            if (!f.geometry) return;
            const p = f.properties;
            if (coincide(p.id_sitio, p.cod_sitio, p.alimentador_codigo, p.subestacion_codigo)) {
                resultados.push({
                    tipo: 'Regulador',
                    titulo: `Regulador ${p.id_sitio}`,
                    subtitulo: `${p.cod_sitio} | Subestación ${p.subestacion_codigo}`,
                    coords: f.geometry.coordinates
                });
            }
        });
    }
    return resultados;
}

function htmlResultado(r) {
    const esEtc = r.tipo === 'ETC';
    return `
        <button type="button" class="result-item" data-accion="volar-a-equipo"
                data-lat="${Number(r.coords[1])}" data-lng="${Number(r.coords[0])}" data-tipo="${escapeHtml(r.tipo)}">
            <span class="result-icon ${esEtc ? 'etc' : 'regulador'}" aria-hidden="true"><i class="fa-solid ${esEtc ? 'fa-bolt' : 'fa-plug'}"></i></span>
            <span>
                <span class="result-title" style="display: block;">${escapeHtml(r.titulo)}</span>
                <span class="result-sub" style="display: block;">${escapeHtml(r.subtitulo)}</span>
            </span>
        </button>`;
}

function ejecutarBusqueda() {
    const query = document.getElementById('search-input').value.toLowerCase().trim();
    const filtro = document.getElementById('search-filter').value;
    const divResultados = document.getElementById('search-results');

    if (query.length < MIN_LETRAS) {
        divResultados.innerHTML = '<div class="empty-state"><i class="fa-solid fa-magnifying-glass" aria-hidden="true"></i>Escribí al menos 2 letras para buscar.</div>';
        return;
    }

    const resultados = buscar(query, filtro);
    if (resultados.length === 0) {
        divResultados.innerHTML = '<div class="empty-state"><i class="fa-solid fa-circle-question" aria-hidden="true"></i>No se encontraron equipos.</div>';
        return;
    }

    let html = resultados.slice(0, MAX_RESULTADOS).map(htmlResultado).join('');
    if (resultados.length > MAX_RESULTADOS) {
        html += `<p class="result-sub" style="text-align: center; margin-top: 12px;">Se muestran ${MAX_RESULTADOS} de ${resultados.length} resultados. Escribí más para filtrar.</p>`;
    }
    divResultados.innerHTML = html;
}

document.getElementById('search-input').addEventListener('input', ejecutarBusqueda);
document.getElementById('search-filter').addEventListener('change', ejecutarBusqueda);

function abrirBusqueda() {
    cerrarMenu();
    cerrarTarjetaEquipo();
    // Pequeña espera para que se cierre el menú antes de abrir el buscador
    setTimeout(() => {
        abrirPanel('search-sheet', { foco: document.getElementById('search-input') });
    }, esEscritorio() ? 0 : 300);
}

registrarAcciones({ 'abrir-busqueda': abrirBusqueda });
