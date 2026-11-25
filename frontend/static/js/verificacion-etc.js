/**
 * SIGVER - Verificación de ETC (equipo telecomandado): formulario simple con
 * foto, fallas y reclamo opcional. Si no hay señal se guarda en la cola offline.
 */
import { guardarVerificacionOffline } from './db.js?v=122';
import { datosGps, seguirUbicacion, sugerirCoincidencia } from './gps.js?v=122';
import { estado } from './estado.js?v=122';
import { fetchConToken, fetchConTimeout, esErrorDeRed, describirErrorServidor } from './api.js?v=122';
import { comprimirImagen, generarIdLocal, generarUUID } from './util.js?v=122';
import {
    abrirPanel, avisarSoloCelular, cerrarPanel, cerrarPopupsMapa, esEscritorio,
    repintarSegmentados, showToast,
} from './ui.js?v=122';
import { actualizarContadorPendientes } from './sync.js?v=122';

let equipoSeleccionadoId = null;
let posicionActual = () => null;   // GPS del formulario abierto (ver gps.js)

export function abrirFormularioVerificacion(equipoId, nroEquipo) {
    if (esEscritorio()) { avisarSoloCelular(); return; }
    equipoSeleccionadoId = equipoId;
    const form = document.getElementById('form-verificacion');
    document.getElementById('verif-nro-equipo').textContent = nroEquipo;
    form.reset();
    repintarSegmentados(form);
    document.getElementById('grupo-prioridad-etc').style.display = 'none';
    document.getElementById('grupo-falla').style.display = 'none';
    document.getElementById('verif-status').textContent = '';
    abrirPanel('sheet-verificacion');
    cerrarPopupsMapa();
    document.querySelectorAll('.checkbox-falla').forEach((cb) => { cb.checked = false; });
    document.getElementById('preview-foto').style.display = 'none';
    const equipo = estado.equipos.find((e) => String(e.properties.id ?? e.id) === String(equipoId));
    // Con GPS se sugiere la respuesta (el servidor recalcula y decide); sin GPS vale lo que elija el técnico
    posicionActual = seguirUbicacion('verif', equipo, (posicion, metros) => {
        const select = document.getElementById('verif-ubicacion-coincide');
        if (metros === null || select.dataset.tocado) return;
        select.value = sugerirCoincidencia(metros);
        select.dispatchEvent(new Event('change'));
        delete select.dataset.tocado;
    });
}

// ==========================================
// Catálogo de fallas (se guarda para usarlo sin señal)
// ==========================================
function llenarListaFallas(fallas) {
    const contenedor = document.getElementById('lista-fallas');
    if (contenedor.children.length > 0) return; // ya está cargada

    fallas.forEach((falla) => {
        const label = document.createElement('label');
        label.className = 'falla-item';

        const checkbox = document.createElement('input');
        checkbox.type = 'checkbox';
        checkbox.value = falla.id;
        checkbox.className = 'checkbox-falla';

        const texto = document.createElement('span');
        texto.textContent = `F${falla.numero} - ${falla.descripcion}`;

        label.append(checkbox, texto);
        contenedor.appendChild(label);
    });
}

export async function cargarFallas() {
    // 1. Lo guardado en el celular (sirve sin señal)
    const fallasLocales = localStorage.getItem('sigver_fallas');
    if (fallasLocales && fallasLocales !== 'undefined') {
        try {
            llenarListaFallas(JSON.parse(fallasLocales));
        } catch {
            console.warn('Error leyendo fallas locales');
        }
    }

    // 2. Con internet, actualizar
    if (!navigator.onLine) return;
    try {
        const res = await fetchConToken('/api/operaciones/fallas-etc/');
        if (res.ok) {
            const data = await res.json();
            if (data.results) {
                localStorage.setItem('sigver_fallas', JSON.stringify(data.results));
                llenarListaFallas(data.results);
            }
        }
    } catch (err) {
        console.error('Error cargando fallas:', err);
    }
}

// ==========================================
// Interacción del formulario
// ==========================================
document.getElementById('verif-foto').addEventListener('change', (e) => {
    const file = e.target.files[0];
    const preview = document.getElementById('preview-foto');
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
});

document.getElementById('btn-cerrar-sheet').addEventListener('click', () => cerrarPanel('sheet-verificacion'));

document.getElementById('verif-tiene-inconveniente').addEventListener('change', (e) => {
    const conFalla = e.target.value === 'si';
    document.getElementById('grupo-falla').style.display = conFalla ? 'block' : 'none';
    if (conFalla) cargarFallas();
});

document.getElementById('verif-req-reclamo').addEventListener('change', (e) => {
    document.getElementById('grupo-prioridad-etc').style.display = e.target.checked ? 'block' : 'none';
});

// ==========================================
// Guardar: en línea al servidor, sin señal a la cola offline
// ==========================================
document.getElementById('form-verificacion').addEventListener('submit', async (e) => {
    e.preventDefault();

    const btnGuardar = document.getElementById('btn-guardar-verif');
    const tieneInconveniente = document.getElementById('verif-tiene-inconveniente').value === 'si';
    const observaciones = document.getElementById('verif-observaciones').value;
    const requiereReclamo = document.getElementById('verif-req-reclamo').checked;
    const prioridad = document.getElementById('verif-prioridad').value;

    let fotoArchivo = document.getElementById('verif-foto').files[0];
    if (fotoArchivo) {
        try {
            fotoArchivo = await comprimirImagen(fotoArchivo);
        } catch (err) {
            console.error('Error comprimiendo imagen:', err);
        }
    }

    const fallasSeleccionadas = Array.from(document.querySelectorAll('.checkbox-falla:checked'))
        .map((cb) => parseInt(cb.value, 10));
    // El servidor asigna el responsable según el usuario autenticado
    const datos = {
        id_verificacion: generarIdLocal('VERIF'),
        client_uuid: generarUUID(),
        equipo_etc: equipoSeleccionadoId,
        fecha_verificacion: new Date().toISOString(),
        tiene_inconveniente: tieneInconveniente,
        observaciones,
        requiere_reclamo: requiereReclamo,
        prioridad: requiereReclamo ? prioridad : '',
        ubicacion_coincide: document.getElementById('verif-ubicacion-coincide').value,
        ...datosGps(posicionActual()),
    };

    const formData = new FormData();
    Object.entries(datos).forEach(([k, v]) => formData.append(k, v));
    fallasSeleccionadas.forEach((idFalla) => formData.append('fallas', idFalla));
    if (fotoArchivo) formData.append('foto', fotoArchivo);

    let guardadoExitoso = false;
    try {
        btnGuardar.disabled = true;
        btnGuardar.innerHTML = '<span class="spinner"></span> Guardando...';

        if (!navigator.onLine) throw new TypeError('offline');

        const res = await fetchConTimeout('/api/operaciones/verificaciones-etc/', {
            method: 'POST',
            body: formData,
        });

        if (res.ok) {
            showToast('Verificación ETC guardada correctamente', 'success');
            guardadoExitoso = true;
        } else {
            // Error de datos/permisos: guardarlo offline solo haría que se pierda al sincronizar
            showToast('No se pudo guardar: ' + await describirErrorServidor(res), 'error');
        }
    } catch (err) {
        if (!esErrorDeRed(err)) {
            console.error('Error inesperado al guardar ETC:', err);
            showToast('Error inesperado: ' + err.message, 'error');
            return;
        }
        console.warn('Fallo de red o timeout, guardando offline:', err);
        try {
            await guardarVerificacionOffline({
                ...datos, fallas: fallasSeleccionadas, foto: fotoArchivo, propietario: estado.usuario?.id,
            });
            showToast('Guardado en el celular. Se enviará al recuperar señal.', 'warning');
            actualizarContadorPendientes();
            guardadoExitoso = true;
        } catch (dbErr) {
            console.error('Error DB:', dbErr);
            showToast('Error crítico al guardar localmente.', 'error');
        }
    } finally {
        btnGuardar.disabled = false;
        btnGuardar.textContent = 'Guardar verificación';
        if (guardadoExitoso) setTimeout(() => cerrarPanel('sheet-verificacion'), 2000);
    }
});
