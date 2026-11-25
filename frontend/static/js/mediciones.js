/**
 * SIGVER - Mediciones del formulario de reguladores (paso 3):
 * termografías y ensayos de puesta a tierra (PAT), con alta, edición y borrado.
 */
import { fetchConToken } from './api.js?v=121';
import { escapeHtml, generarIdLocal } from './util.js?v=121';
import { abrirModal, cerrarModal, registrarAcciones } from './ui.js?v=121';

let termografias = [];
let indiceEdicionTermografia = -1; // -1 = agregando una nueva
let ensayosPat = [];
let lecturasTemporales = [];       // lecturas del ensayo que se está editando en el modal
let indiceEdicionPat = -1;

// Copias para el envío y el resumen (el formulario no modifica las listas)
export function obtenerTermografias() { return [...termografias]; }
export function obtenerEnsayosPat() { return [...ensayosPat]; }

// Al abrir un regulador nuevo o después de guardar
export function reiniciarMediciones() {
    termografias = [];
    ensayosPat = [];
    actualizarListaTermografias();
    actualizarListaEnsayosPat();
}


// ==========================================
// Termografía
// ==========================================
export async function cargarPuntosTermografia() {
    if (!navigator.onLine) return;
    try {
        const res = await fetchConToken('/api/operaciones/puntos-termografia/');
        if (res.ok) {
            const data = await res.json();
            if (data.results) localStorage.setItem('sigver_puntos_ter', JSON.stringify(data.results));
        }
    } catch (err) {
        console.error('Error cargando puntos de termografía:', err);
    }
}

function llenarSelectPuntos() {
    const select = document.getElementById('term-punto');
    if (select.options.length > 0) return;
    const puntos = localStorage.getItem('sigver_puntos_ter');
    if (!puntos) {
        select.innerHTML = '<option value="">Error al cargar puntos</option>';
        return;
    }
    select.innerHTML = '<option value="">Seleccione un punto...</option>' + JSON.parse(puntos)
        .map((p) => `<option value="${escapeHtml(p.id_punto)}">${escapeHtml(p.id_punto)} - Fase ${escapeHtml(p.fase)} (${escapeHtml(p.tipo_elemento)})</option>`)
        .join('');
}

function actualizarListaTermografias() {
    const n = termografias.length;
    document.getElementById('reg-term-cuenta').textContent = n === 1 ? '1 punto' : `${n} puntos`;

    document.getElementById('lista-termografias').innerHTML = termografias.map((t, index) => {
        const delta = t.delta_temperatura_c;
        const color = delta === null || delta === undefined ? 'var(--text-muted)' : delta >= 10 ? '#b91c1c' : delta >= 5 ? '#b45309' : 'var(--success)';
        const detalle = [
            `${String(t.temperatura_punto_c).replace('.', ',')} °C`,
            t.temperatura_ambiente_c !== null ? `amb. ${String(t.temperatura_ambiente_c).replace('.', ',')} °C` : null,
            t.corriente_a !== null ? `${t.corriente_a} A` : null,
        ].filter(Boolean).join(' · ');
        return `
            <div class="medicion-item">
                <div class="med-texto">
                    <div class="med-titulo">${escapeHtml(t.punto)}</div>
                    <div class="med-sub">${escapeHtml(detalle)}</div>
                </div>
                <div class="med-delta" style="color: ${color};">${delta !== null && delta !== undefined ? 'Δ ' + escapeHtml(String(delta).replace('.', ',')) + '°' : ''}</div>
                <button type="button" class="icon-action" data-accion="editar-termografia" data-indice="${index}" aria-label="Editar"><i class="fa-solid fa-pen" aria-hidden="true"></i></button>
                <button type="button" class="icon-action danger" data-accion="eliminar-termografia" data-indice="${index}" aria-label="Eliminar"><i class="fa-solid fa-trash" aria-hidden="true"></i></button>
            </div>`;
    }).join('');
}

document.getElementById('btn-add-termografia').addEventListener('click', () => {
    indiceEdicionTermografia = -1;
    ['term-temp-punto', 'term-temp-amb', 'term-corriente', 'term-punto'].forEach((id) => {
        document.getElementById(id).value = '';
    });
    llenarSelectPuntos();
    abrirModal('modal-termografia');
});

document.getElementById('btn-cancelar-term').addEventListener('click', () => cerrarModal('modal-termografia'));

document.getElementById('btn-guardar-term').addEventListener('click', () => {
    const punto = document.getElementById('term-punto').value;
    const tempPunto = document.getElementById('term-temp-punto').value;
    const tempAmb = document.getElementById('term-temp-amb').value;
    const corriente = document.getElementById('term-corriente').value;

    if (!punto || !tempPunto) {
        alert('Por favor, selecciona un punto y la temperatura.');
        return;
    }

    const delta = tempPunto && tempAmb ? (parseFloat(tempPunto) - parseFloat(tempAmb)).toFixed(1) : null;
    const medicion = {
        id_medicion: indiceEdicionTermografia === -1 ? generarIdLocal('TERM') : termografias[indiceEdicionTermografia].id_medicion,
        punto,
        fecha_hora: new Date().toISOString(),
        corriente_a: corriente ? parseFloat(corriente) : null,
        temperatura_ambiente_c: tempAmb ? parseFloat(tempAmb) : null,
        temperatura_punto_c: parseFloat(tempPunto),
        delta_temperatura_c: delta ? parseFloat(delta) : null,
        nivel_termografico: 'Nivel 1',
        observaciones: ''
    };

    if (indiceEdicionTermografia === -1) termografias.push(medicion);
    else termografias[indiceEdicionTermografia] = medicion;

    actualizarListaTermografias();
    cerrarModal('modal-termografia');
});

function editarTermografia(index) {
    indiceEdicionTermografia = index;
    const term = termografias[index];
    llenarSelectPuntos();
    document.getElementById('term-punto').value = term.punto;
    document.getElementById('term-temp-punto').value = term.temperatura_punto_c;
    document.getElementById('term-temp-amb').value = term.temperatura_ambiente_c || '';
    document.getElementById('term-corriente').value = term.corriente_a || '';
    abrirModal('modal-termografia');
}

function eliminarTermografia(index) {
    if (confirm('¿Estás seguro de eliminar esta termografía?')) {
        termografias.splice(index, 1);
        actualizarListaTermografias();
    }
}

// ==========================================
// Ensayos PAT (puesta a tierra)
// ==========================================
function actualizarListaTemporalLecturas() {
    const div = document.getElementById('lista-lecturas-modal');
    if (lecturasTemporales.length === 0) {
        div.innerHTML = '<span style="color: var(--text-muted);">Todavía no hay lecturas.</span>';
        return;
    }
    div.innerHTML = lecturasTemporales.map((l, idx) => `
        <div class="item-row" style="background: var(--surface);"><span>${escapeHtml(l.distancia_m)} m: <b>${escapeHtml(l.valor_ohm)} Ω</b></span>
            <button type="button" class="icon-action danger" data-accion="eliminar-lectura" data-indice="${idx}" aria-label="Eliminar lectura"><i class="fa-solid fa-trash" aria-hidden="true"></i></button></div>`).join('');
}

function actualizarListaEnsayosPat() {
    const cuenta = document.getElementById('reg-pat-cuenta');
    const ultimo = ensayosPat[ensayosPat.length - 1];
    if (!ultimo) {
        cuenta.textContent = 'Sin ensayo';
        cuenta.className = 'chip';
    } else {
        const conforme = ultimo.resultado === 'CONFORME';
        cuenta.textContent = ultimo.resultado.replace('_', ' ').toLowerCase();
        cuenta.className = `chip ${conforme ? 'chip-ok' : ultimo.resultado === 'NO_CONFORME' ? 'chip-critica' : 'chip-media'}`;
        cuenta.style.textTransform = 'capitalize';
    }

    document.getElementById('lista-ensayos-pat').innerHTML = ensayosPat.map((e, index) => {
        const valores = e.lecturas.map((l) => l.valor_ohm).filter((v) => typeof v === 'number');
        const minimo = valores.length ? Math.min(...valores) : null;
        const detalle = [e.metodo_pat, e.condicion_suelo ? `suelo ${String(e.condicion_suelo).toLowerCase()}` : null,
            `${e.lecturas.length} lectura(s)`].filter(Boolean).join(' · ');
        return `
            <div class="medicion-item">
                <div class="med-texto">
                    <div class="med-titulo">Ensayo ${index + 1}</div>
                    <div class="med-sub">${escapeHtml(detalle)}</div>
                </div>
                <div class="med-delta" style="color: var(--ande-blue);">${minimo !== null ? escapeHtml(String(minimo).replace('.', ',')) + ' Ω' : ''}</div>
                <button type="button" class="icon-action" data-accion="editar-ensayo-pat" data-indice="${index}" aria-label="Editar"><i class="fa-solid fa-pen" aria-hidden="true"></i></button>
                <button type="button" class="icon-action danger" data-accion="eliminar-ensayo-pat" data-indice="${index}" aria-label="Eliminar"><i class="fa-solid fa-trash" aria-hidden="true"></i></button>
            </div>`;
    }).join('');
}

document.getElementById('btn-add-pat').addEventListener('click', () => {
    indiceEdicionPat = -1;
    lecturasTemporales = [];
    ['pat-metodo', 'pat-equipo', 'pat-lect-dist', 'pat-lect-val'].forEach((id) => {
        document.getElementById(id).value = '';
    });
    document.getElementById('lista-lecturas-modal').innerHTML = '';
    abrirModal('modal-pat');
});

document.getElementById('btn-cancelar-pat').addEventListener('click', () => cerrarModal('modal-pat'));

document.getElementById('btn-add-lectura').addEventListener('click', () => {
    const dist = document.getElementById('pat-lect-dist').value;
    const val = document.getElementById('pat-lect-val').value;
    if (!dist || !val) {
        alert('Por favor, completa distancia y valor de la lectura.');
        return;
    }
    lecturasTemporales.push({
        id_lectura: generarIdLocal('LECT'),
        tipo_lectura: 'MEDICION',
        distancia_m: parseInt(dist, 10),
        valor_ohm: parseFloat(val),
        observaciones: ''
    });
    document.getElementById('pat-lect-dist').value = '';
    document.getElementById('pat-lect-val').value = '';
    actualizarListaTemporalLecturas();
});

document.getElementById('btn-guardar-pat').addEventListener('click', () => {
    if (lecturasTemporales.length === 0) {
        alert('Debes agregar al menos una lectura para guardar el ensayo PAT.');
        return;
    }
    const ensayo = {
        id_ensayo: indiceEdicionPat === -1 ? generarIdLocal('PAT') : ensayosPat[indiceEdicionPat].id_ensayo,
        fecha_ensayo: new Date().toISOString(),
        metodo_pat: document.getElementById('pat-metodo').value,
        equipo_medicion: document.getElementById('pat-equipo').value,
        condicion_suelo: document.getElementById('pat-suelo').value,
        resultado: document.getElementById('pat-resultado').value,
        lecturas: [...lecturasTemporales]
    };

    if (indiceEdicionPat === -1) ensayosPat.push(ensayo);
    else ensayosPat[indiceEdicionPat] = ensayo;

    actualizarListaEnsayosPat();
    cerrarModal('modal-pat');
});

function editarEnsayoPat(index) {
    indiceEdicionPat = index;
    const ensayo = ensayosPat[index];
    document.getElementById('pat-metodo').value = ensayo.metodo_pat;
    document.getElementById('pat-equipo').value = ensayo.equipo_medicion;
    document.getElementById('pat-suelo').value = ensayo.condicion_suelo;
    document.getElementById('pat-resultado').value = ensayo.resultado;
    lecturasTemporales = [...ensayo.lecturas];
    actualizarListaTemporalLecturas();
    abrirModal('modal-pat');
}

function eliminarEnsayoPat(index) {
    if (confirm('¿Estás seguro de eliminar este ensayo PAT?')) {
        ensayosPat.splice(index, 1);
        actualizarListaEnsayosPat();
    }
}

const indice = (el) => Number(el.dataset.indice);
registrarAcciones({
    'editar-termografia': (el) => editarTermografia(indice(el)),
    'eliminar-termografia': (el) => eliminarTermografia(indice(el)),
    'eliminar-lectura': (el) => {
        lecturasTemporales.splice(indice(el), 1);
        actualizarListaTemporalLecturas();
    },
    'editar-ensayo-pat': (el) => editarEnsayoPat(indice(el)),
    'eliminar-ensayo-pat': (el) => eliminarEnsayoPat(indice(el)),
});
