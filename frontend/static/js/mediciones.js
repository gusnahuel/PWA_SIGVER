/**
 * SIGVER - Mediciones del formulario de reguladores (paso 3):
 * termografías y ensayos de puesta a tierra (PAT), con alta, edición y borrado.
 */
import { fetchConToken } from './api.js?v=127';
import { comprimirImagen, escapeHtml, generarIdLocal, nivelTermografico } from './util.js?v=127';
import { abrirModal, cerrarModal, registrarAcciones } from './ui.js?v=127';

let termografias = [];
let indiceEdicionTermografia = -1; // -1 = agregando una nueva
let ensayosPat = [];
let lecturasTemporales = [];       // lecturas del ensayo que se está editando en el modal
let fotoPatTemporal = null;        // foto (ya comprimida) del ensayo que se está editando
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

const coma = (n) => String(n).replace('.', ',');
const CLASE_NIVEL = { 'Nivel 1': 'n1', 'Nivel 2': 'n2', 'Nivel 3': 'n3', 'Nivel 4': 'n4' };
const COLOR_NIVEL = { 'Nivel 1': 'var(--success)', 'Nivel 2': 'var(--warning)', 'Nivel 3': '#b91c1c', 'Nivel 4': '#b91c1c' };

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

const NOMBRE_ELEMENTO = {
    Seccionador_ByPass: 'Seccionador bypass',
    Seccionador_Equipo_LadoLinea: 'Seccionador lado línea',
    Seccionador_Equipo_LadoEquipo: 'Seccionador lado equipo',
    Bushing: 'Bushing',
    Conector_Descargador_Linea: 'Conector descargador línea',
    Conector_Descargador_Regulador: 'Conector descargador regulador',
    Otros: 'Otros',
};
const NOMBRE_LADO = { Fuente: 'fuente', Carga: 'carga', Comun: 'común' };

// Puntos agrupados por fase; los que ya se midieron en esta verificación quedan marcados
function llenarSelectPuntos(actual = '') {
    const select = document.getElementById('term-punto');
    const guardados = localStorage.getItem('sigver_puntos_ter');
    if (!guardados) {
        select.innerHTML = '<option value="">No se pudieron cargar los puntos (abrí la app con señal)</option>';
        return;
    }
    const medidos = new Set(termografias.map((t) => t.punto).filter((p) => p !== actual));
    const porFase = {};
    JSON.parse(guardados).filter((p) => p.activo !== false).forEach((p) => {
        (porFase[p.fase] ||= []).push(p);
    });
    select.innerHTML = '<option value="">Elegí un punto...</option>' + Object.keys(porFase).sort().map((fase) => `
        <optgroup label="Fase ${escapeHtml(fase)}">${porFase[fase].map((p) => {
            const lado = NOMBRE_LADO[p.lado_conexion] ? ` (${NOMBRE_LADO[p.lado_conexion]})` : '';
            const texto = `${p.id_punto} · ${NOMBRE_ELEMENTO[p.tipo_elemento] || p.tipo_elemento}${lado}${medidos.has(p.id_punto) ? ' ✓ medido' : ''}`;
            return `<option value="${escapeHtml(p.id_punto)}">${escapeHtml(texto)}</option>`;
        }).join('')}</optgroup>`).join('');
    select.value = actual;
}

function deltaDelModal() {
    const punto = document.getElementById('term-temp-punto').value;
    const ambiente = document.getElementById('term-temp-amb').value;
    if (punto === '' || ambiente === '') return null;
    return Math.round((parseFloat(punto) - parseFloat(ambiente)) * 10) / 10;
}

// Muestra en el modal el ΔT y el nivel mientras se cargan las temperaturas
function mostrarNivelEnModal() {
    const caja = document.getElementById('term-nivel');
    const delta = deltaDelModal();
    const nivel = nivelTermografico(delta);
    caja.className = `nivel-termo ${CLASE_NIVEL[nivel] || ''}`;
    caja.textContent = nivel ? `ΔT ${coma(delta)} °C · ${nivel}` : 'Cargá las dos temperaturas para ver el nivel';
}
['term-temp-punto', 'term-temp-amb'].forEach((id) => document.getElementById(id).addEventListener('input', mostrarNivelEnModal));

function actualizarListaTermografias() {
    const n = termografias.length;
    document.getElementById('reg-term-cuenta').textContent = n === 1 ? '1 punto' : `${n} puntos`;

    document.getElementById('lista-termografias').innerHTML = termografias.map((t, index) => {
        const delta = t.delta_temperatura_c;
        const nivel = nivelTermografico(delta);
        const detalle = [
            `${coma(t.temperatura_punto_c)} °C`,
            t.temperatura_ambiente_c !== null ? `amb. ${coma(t.temperatura_ambiente_c)} °C` : null,
            t.corriente_a !== null ? `${t.corriente_a} A` : null,
            t.observaciones || null,
        ].filter(Boolean).join(' · ');
        return `
            <div class="medicion-item">
                <div class="med-texto">
                    <div class="med-titulo">${escapeHtml(t.punto)}</div>
                    <div class="med-sub">${escapeHtml(detalle)}</div>
                </div>
                <div class="med-delta" style="color: ${COLOR_NIVEL[nivel] || 'var(--text-muted)'};">${nivel
                    ? `Δ ${escapeHtml(coma(delta))}°<br><small>${escapeHtml(nivel)}</small>` : ''}</div>
                <button type="button" class="icon-action" data-accion="editar-termografia" data-indice="${index}" aria-label="Editar"><i class="fa-solid fa-pen" aria-hidden="true"></i></button>
                <button type="button" class="icon-action danger" data-accion="eliminar-termografia" data-indice="${index}" aria-label="Eliminar"><i class="fa-solid fa-trash" aria-hidden="true"></i></button>
            </div>`;
    }).join('');
}

document.getElementById('btn-add-termografia').addEventListener('click', () => {
    indiceEdicionTermografia = -1;
    ['term-temp-punto', 'term-temp-amb', 'term-corriente', 'term-observaciones'].forEach((id) => {
        document.getElementById(id).value = '';
    });
    llenarSelectPuntos();
    mostrarNivelEnModal();
    abrirModal('modal-termografia');
});

document.getElementById('btn-cancelar-term').addEventListener('click', () => cerrarModal('modal-termografia'));

document.getElementById('btn-guardar-term').addEventListener('click', () => {
    const punto = document.getElementById('term-punto').value;
    const tempPunto = document.getElementById('term-temp-punto').value;
    const tempAmb = document.getElementById('term-temp-amb').value;
    const corriente = document.getElementById('term-corriente').value;

    if (!punto || !tempPunto) {
        alert('Elegí un punto y cargá su temperatura.');
        return;
    }

    // ΔT y nivel se muestran acá; el servidor los vuelve a calcular al guardar
    const medicion = {
        id_medicion: indiceEdicionTermografia === -1 ? generarIdLocal('TERM') : termografias[indiceEdicionTermografia].id_medicion,
        punto,
        fecha_hora: new Date().toISOString(),
        corriente_a: corriente ? parseFloat(corriente) : null,
        temperatura_ambiente_c: tempAmb ? parseFloat(tempAmb) : null,
        temperatura_punto_c: parseFloat(tempPunto),
        delta_temperatura_c: deltaDelModal(),
        observaciones: document.getElementById('term-observaciones').value.trim(),
    };

    if (indiceEdicionTermografia === -1) termografias.push(medicion);
    else termografias[indiceEdicionTermografia] = medicion;

    actualizarListaTermografias();
    cerrarModal('modal-termografia');
});

function editarTermografia(index) {
    indiceEdicionTermografia = index;
    const term = termografias[index];
    llenarSelectPuntos(term.punto);
    document.getElementById('term-temp-punto').value = term.temperatura_punto_c;
    document.getElementById('term-temp-amb').value = term.temperatura_ambiente_c ?? '';
    document.getElementById('term-corriente').value = term.corriente_a ?? '';
    document.getElementById('term-observaciones').value = term.observaciones || '';
    mostrarNivelEnModal();
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
const NOMBRE_LECTURA = { MEDICION: 'Medición', VALIDACION: 'Validación' };

function actualizarListaTemporalLecturas() {
    const div = document.getElementById('lista-lecturas-modal');
    if (lecturasTemporales.length === 0) {
        div.innerHTML = '<span style="color: var(--text-muted);">Todavía no hay lecturas.</span>';
        return;
    }
    div.innerHTML = lecturasTemporales.map((l, idx) => `
        <div class="item-row" style="background: var(--surface);"><span>${escapeHtml(NOMBRE_LECTURA[l.tipo_lectura] || l.tipo_lectura)} · ${escapeHtml(l.distancia_m)} m: <b>${escapeHtml(coma(l.valor_ohm))} Ω</b></span>
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
            `${e.lecturas.length} lectura(s)`, e.foto ? 'con foto' : null].filter(Boolean).join(' · ');
        return `
            <div class="medicion-item">
                <div class="med-texto">
                    <div class="med-titulo">Ensayo ${index + 1}</div>
                    <div class="med-sub">${escapeHtml(detalle)}</div>
                </div>
                <div class="med-delta" style="color: var(--ande-blue);">${minimo !== null ? escapeHtml(coma(minimo)) + ' Ω' : ''}</div>
                <button type="button" class="icon-action" data-accion="editar-ensayo-pat" data-indice="${index}" aria-label="Editar"><i class="fa-solid fa-pen" aria-hidden="true"></i></button>
                <button type="button" class="icon-action danger" data-accion="eliminar-ensayo-pat" data-indice="${index}" aria-label="Eliminar"><i class="fa-solid fa-trash" aria-hidden="true"></i></button>
            </div>`;
    }).join('');
}

function elegirTipoLectura(valor) {
    const select = document.getElementById('pat-lect-tipo');
    select.value = valor;
    select.dispatchEvent(new Event('change'));   // repinta los botones
}

function mostrarFotoPat(foto) {
    const preview = document.getElementById('pat-foto-preview');
    if (preview.src.startsWith('blob:')) URL.revokeObjectURL(preview.src);
    if (foto) {
        preview.src = URL.createObjectURL(foto);
        preview.style.display = 'block';
    } else {
        preview.removeAttribute('src');
        preview.style.display = 'none';
    }
}

document.getElementById('pat-foto').addEventListener('change', async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    try {
        fotoPatTemporal = await comprimirImagen(file);
    } catch (err) {
        console.error('Error comprimiendo la foto del ensayo:', err);
        fotoPatTemporal = file;
    }
    mostrarFotoPat(fotoPatTemporal);
    e.target.value = '';   // permite volver a elegir la misma foto
});

document.getElementById('btn-add-pat').addEventListener('click', () => {
    indiceEdicionPat = -1;
    lecturasTemporales = [];
    fotoPatTemporal = null;
    ['pat-metodo', 'pat-equipo', 'pat-temp-amb', 'pat-observaciones', 'pat-lect-dist', 'pat-lect-val'].forEach((id) => {
        document.getElementById(id).value = '';
    });
    elegirTipoLectura('MEDICION');
    mostrarFotoPat(null);
    document.getElementById('lista-lecturas-modal').innerHTML = '';
    abrirModal('modal-pat');
});

document.getElementById('btn-cancelar-pat').addEventListener('click', () => cerrarModal('modal-pat'));

document.getElementById('btn-add-lectura').addEventListener('click', () => {
    const dist = document.getElementById('pat-lect-dist').value;
    const val = document.getElementById('pat-lect-val').value;
    if (!dist || !val) {
        alert('Completá la distancia y el valor de la lectura.');
        return;
    }
    lecturasTemporales.push({
        id_lectura: generarIdLocal('LECT'),
        tipo_lectura: document.getElementById('pat-lect-tipo').value,
        distancia_m: parseInt(dist, 10),
        valor_ohm: parseFloat(val),
        observaciones: '',
    });
    document.getElementById('pat-lect-dist').value = '';
    document.getElementById('pat-lect-val').value = '';
    actualizarListaTemporalLecturas();
});

document.getElementById('btn-guardar-pat').addEventListener('click', () => {
    if (lecturasTemporales.length === 0) {
        alert('Agregá al menos una lectura para guardar el ensayo.');
        return;
    }
    const temperatura = document.getElementById('pat-temp-amb').value;
    const ensayo = {
        id_ensayo: indiceEdicionPat === -1 ? generarIdLocal('PAT') : ensayosPat[indiceEdicionPat].id_ensayo,
        fecha_ensayo: new Date().toISOString(),
        metodo_pat: document.getElementById('pat-metodo').value,
        equipo_medicion: document.getElementById('pat-equipo').value,
        temperatura_ambiente_c: temperatura ? parseFloat(temperatura) : null,
        condicion_suelo: document.getElementById('pat-suelo').value,
        resultado: document.getElementById('pat-resultado').value,
        observaciones: document.getElementById('pat-observaciones').value.trim(),
        lecturas: [...lecturasTemporales],
        foto: fotoPatTemporal,   // se envía aparte (ver agregarEnsayosPat en util.js)
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
    document.getElementById('pat-temp-amb').value = ensayo.temperatura_ambiente_c ?? '';
    document.getElementById('pat-suelo').value = ensayo.condicion_suelo;
    document.getElementById('pat-resultado').value = ensayo.resultado;
    document.getElementById('pat-observaciones').value = ensayo.observaciones || '';
    elegirTipoLectura('MEDICION');
    fotoPatTemporal = ensayo.foto || null;
    mostrarFotoPat(fotoPatTemporal);
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
