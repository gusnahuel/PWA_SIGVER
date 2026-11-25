/**
 * SIGVER - Verificación de regulador: formulario en 4 pasos (datos y GPS,
 * fotos, mediciones, reclamo/resumen). Sin señal se guarda en la cola offline.
 */
import { guardarVerificacionOffline } from './db.js?v=122';
import { datosGps, seguirUbicacion, sugerirCoincidencia } from './gps.js?v=122';
import { estado } from './estado.js?v=122';
import { fetchConTimeout, esErrorDeRed, describirErrorServidor } from './api.js?v=122';
import {
    agregarEnsayosPat, comprimirImagen, escapeHtml, generarIdLocal, generarUUID, nivelTermografico,
} from './util.js?v=122';
import {
    abrirPanel, avisarSoloCelular, cerrarPanel, cerrarPopupsMapa, esEscritorio,
    repintarSegmentados, showToast,
} from './ui.js?v=122';
import { actualizarContadorPendientes } from './sync.js?v=122';
import { obtenerEnsayosPat, obtenerTermografias, reiniciarMediciones } from './mediciones.js?v=122';

const TOTAL_PASOS = 4;
const FOTOS_REGULADOR = ['reg-foto-frontal', 'reg-foto-entorno', 'reg-foto-control'];

let componenteSeleccionadoId = null;
let pasoActual = 0;

export function abrirFormularioRegulador(componenteId, codSitio) {
    if (esEscritorio()) { avisarSoloCelular(); return; }
    componenteSeleccionadoId = componenteId;

    const sitio = estado.sitios.find((s) => s.properties.componente_id === componenteId);
    document.getElementById('reg-codigo').textContent = [codSitio, sitio?.properties.cod_sitio].filter(Boolean).join(' · ');
    const form = document.getElementById('form-regulador');
    form.reset();
    repintarSegmentados(form);
    limpiarFotosRegulador();
    reiniciarMediciones();
    document.getElementById('reg-status').textContent = '';
    document.getElementById('reg-req-reclamo').checked = false;
    document.getElementById('grupo-prioridad-reg').style.display = 'none';
    irAPaso(0);
    medirDistanciaAlSitio(sitio);

    abrirPanel('sheet-regulador');
    cerrarPopupsMapa();
}

const cerrarFormulario = () => cerrarPanel('sheet-regulador');
document.getElementById('btn-cerrar-sheet-reg').addEventListener('click', cerrarFormulario);

// ==========================================
// Navegación entre pasos
// ==========================================
function irAPaso(n) {
    pasoActual = Math.max(0, Math.min(TOTAL_PASOS - 1, n));
    document.querySelectorAll('#form-regulador .paso').forEach((el) => {
        el.classList.toggle('activo', Number(el.dataset.paso) === pasoActual);
    });
    document.querySelectorAll('#sheet-regulador .paso-tab').forEach((t) => {
        const i = Number(t.dataset.irPaso);
        t.classList.toggle('actual', i === pasoActual);
        t.classList.toggle('hecho', i < pasoActual);
        t.setAttribute('aria-selected', String(i === pasoActual));
    });
    const ultimo = pasoActual === TOTAL_PASOS - 1;
    document.getElementById('btn-paso-anterior').textContent = pasoActual === 0 ? 'Cancelar' : 'Anterior';
    document.getElementById('btn-paso-siguiente').style.display = ultimo ? 'none' : '';
    document.getElementById('btn-guardar-reg').style.display = ultimo ? '' : 'none';
    if (ultimo) actualizarResumenRegulador();
    document.getElementById('form-regulador').scrollTop = 0;
}

document.querySelectorAll('#sheet-regulador .paso-tab').forEach((t) => {
    t.addEventListener('click', () => irAPaso(Number(t.dataset.irPaso)));
});
document.getElementById('btn-paso-siguiente').addEventListener('click', () => irAPaso(pasoActual + 1));
document.getElementById('btn-paso-anterior').addEventListener('click', () => {
    if (pasoActual === 0) cerrarFormulario();
    else irAPaso(pasoActual - 1);
});
// Enter en un campo de texto no debe guardar el formulario antes del último paso
document.getElementById('form-regulador').addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && e.target.tagName === 'INPUT') e.preventDefault();
});

document.getElementById('reg-req-reclamo').addEventListener('change', (e) => {
    document.getElementById('grupo-prioridad-reg').style.display = e.target.checked ? 'block' : 'none';
});

// ==========================================
// GPS: distancia al sitio y sugerencia de "ubicación coincide"
// (con GPS, el servidor recalcula y decide; ver gps.js)
// ==========================================
let posicionActual = () => null;

function medirDistanciaAlSitio(sitio) {
    posicionActual = seguirUbicacion('reg', sitio, (posicion, metros) => {
        if (metros === null) return;
        const select = document.getElementById('reg-ubicacion-coincide');
        if (!select.dataset.tocado) { // no pisar lo que eligió el técnico
            select.value = sugerirCoincidencia(metros);
            select.dispatchEvent(new Event('change'));
            delete select.dataset.tocado;
        }
    });
}

// ==========================================
// Fotos con vista previa
// ==========================================
function contarFotosRegulador() {
    return FOTOS_REGULADOR.filter((id) => document.getElementById(id).files.length > 0).length;
}

function actualizarCuentaFotos() {
    document.getElementById('reg-fotos-cuenta').textContent = `${contarFotosRegulador()} de 3`;
}

function limpiarFotosRegulador() {
    FOTOS_REGULADOR.forEach((id) => {
        const tile = document.querySelector(`[data-preview-de="${id}"]`);
        tile.classList.remove('con-foto');
        tile.style.backgroundImage = '';
    });
    actualizarCuentaFotos();
    document.getElementById('reg-obs-cuenta').textContent = '0 / 500';
}

FOTOS_REGULADOR.forEach((id) => {
    document.getElementById(id).addEventListener('change', (e) => {
        const tile = document.querySelector(`[data-preview-de="${id}"]`);
        const file = e.target.files[0];
        if (file) {
            tile.style.backgroundImage = `url("${URL.createObjectURL(file)}")`;
            tile.classList.add('con-foto');
        } else {
            tile.style.backgroundImage = '';
            tile.classList.remove('con-foto');
        }
        actualizarCuentaFotos();
    });
});

document.getElementById('reg-observaciones').addEventListener('input', (e) => {
    document.getElementById('reg-obs-cuenta').textContent = `${e.target.value.length} / 500`;
});

// ==========================================
// Resumen del último paso
// ==========================================
function actualizarResumenRegulador() {
    const textoSelect = (id) => {
        const s = document.getElementById(id);
        return s.options[s.selectedIndex]?.textContent || '-';
    };
    const termografias = obtenerTermografias();
    const ensayos = obtenerEnsayosPat();
    const deltas = termografias.map((t) => t.delta_temperatura_c).filter((d) => d !== null && d !== undefined);
    const maxDelta = deltas.length ? Math.max(...deltas) : null;
    const nivelMax = nivelTermografico(maxDelta);
    const fotos = contarFotosRegulador();
    const filas = [
        ['Estado del sitio', textoSelect('reg-estado-sitio')],
        ['Ubicación coincide', textoSelect('reg-ubicacion-coincide')],
        ['Fotos', `${fotos} de 3`],
        ['Termografía', termografias.length
            ? `${termografias.length} punto(s)${maxDelta !== null ? ` · máx. Δ ${String(maxDelta).replace('.', ',')}° (${nivelMax})` : ''}`
            : 'Sin mediciones'],
        ['Ensayo PAT', ensayos.length
            ? ensayos.map((e) => e.resultado.replace('_', ' ').toLowerCase()).join(', ')
            : 'Sin ensayo'],
    ];
    let html = filas.map(([a, b]) => `<div class="resumen-fila"><span>${a}</span><span style="text-transform: none;">${escapeHtml(b)}</span></div>`).join('');
    if (fotos < 3) {
        html += `<div class="resumen-aviso">Faltan ${3 - fotos} foto(s). Podés guardar igual.</div>`;
    }
    document.getElementById('reg-resumen').innerHTML = html;
}

// ==========================================
// Guardar: en línea al servidor, sin señal a la cola offline
// ==========================================
document.getElementById('form-regulador').addEventListener('submit', async (e) => {
    e.preventDefault();
    const btnGuardar = document.getElementById('btn-guardar-reg');

    if (!componenteSeleccionadoId) {
        showToast('Este sitio no tiene un componente (regulador) cargado.', 'error');
        return;
    }
    const valor = (id) => document.getElementById(id).value;
    const requiereReclamo = document.getElementById('reg-req-reclamo').checked;

    // Fotos comprimidas
    const comprimir = async (id) => {
        const file = document.getElementById(id).files[0];
        return file ? comprimirImagen(file) : undefined;
    };
    const fotoFrontal = await comprimir('reg-foto-frontal');
    const fotoEntorno = await comprimir('reg-foto-entorno');
    const fotoControl = await comprimir('reg-foto-control');

    const payloadBase = {
        id_verificacion: generarIdLocal('VERIF-REG'),
        client_uuid: generarUUID(),
        componente: componenteSeleccionadoId,
        fecha_verificacion: new Date().toISOString(),
        tipo_control_verificado: valor('reg-tipo-control'),
        tipo_banco_verificado: valor('reg-tipo-banco'),
        valla_perimetral: valor('reg-valla') === 'true',
        es_hibrido: valor('reg-hibrido') === 'true',
        configuracion_observada: valor('reg-config-obs'),
        estado_sitio: valor('reg-estado-sitio'),
        observaciones: valor('reg-observaciones'),
        ubicacion_coincide: valor('reg-ubicacion-coincide'),
        requiere_reclamo: requiereReclamo,
        prioridad: requiereReclamo ? valor('reg-prioridad') : '',
        ...datosGps(posicionActual()),
    };
    const termografias = obtenerTermografias();
    const ensayos = obtenerEnsayosPat();

    const formData = new FormData();
    Object.entries(payloadBase).forEach(([k, v]) => formData.append(k, v));
    if (fotoFrontal) formData.append('foto_frontal', fotoFrontal);
    if (fotoEntorno) formData.append('foto_entorno', fotoEntorno);
    if (fotoControl) formData.append('foto_control_unico', fotoControl);
    if (termografias.length > 0) formData.append('mediciones_termografia', JSON.stringify(termografias));
    agregarEnsayosPat(formData, ensayos);

    let guardadoExitoso = false;
    try {
        btnGuardar.disabled = true;
        btnGuardar.innerHTML = '<span class="spinner"></span> Guardando...';

        if (!navigator.onLine) throw new TypeError('offline');

        const res = await fetchConTimeout('/api/operaciones/verificaciones/', {
            method: 'POST',
            body: formData
        }, 30000);

        if (res.ok) {
            showToast('Regulador guardado correctamente', 'success');
            guardadoExitoso = true;
        } else {
            showToast('No se pudo guardar: ' + await describirErrorServidor(res), 'error');
        }
    } catch (err) {
        console.warn('Error al guardar regulador:', err);
        if (esErrorDeRed(err)) {
            try {
                const payloadOffline = { ...payloadBase, tipo: 'regulador', propietario: estado.usuario?.id };
                if (fotoFrontal) payloadOffline.foto_frontal = fotoFrontal;
                if (fotoEntorno) payloadOffline.foto_entorno = fotoEntorno;
                if (fotoControl) payloadOffline.foto_control_unico = fotoControl;
                if (termografias.length > 0) payloadOffline.mediciones_termografia = termografias;
                if (ensayos.length > 0) payloadOffline.ensayos_pat = ensayos;

                await guardarVerificacionOffline(payloadOffline);
                showToast('Guardado localmente. Se enviará al recuperar señal.', 'warning');
                actualizarContadorPendientes();
                guardadoExitoso = true;
            } catch {
                showToast('Error al guardar localmente.', 'error');
            }
        } else {
            showToast('Error del servidor: ' + err.message, 'error');
        }
    } finally {
        btnGuardar.disabled = false;
        btnGuardar.textContent = 'Guardar verificación';
        if (guardadoExitoso) {
            reiniciarMediciones();
            setTimeout(cerrarFormulario, 2000);
        }
    }
});
