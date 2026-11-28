/**
 * SIGVER - Equipos del banco (paso 4 del regulador): datos de placa de cada
 * unidad (marca, modelo, serie, estado y fotos). Muestra lo ya cargado en el
 * servidor y envía con la verificación solo lo nuevo o corregido.
 */
import { comprimirImagen, escapeHtml, generarUUID } from './util.js?v=128';
import { abrirModal, cerrarModal, registrarAcciones } from './ui.js?v=128';

const FOTOS = ['equipo', 'placa', 'control'];
const CAMPOS = {
    identificador_elemento: 'elem-identificador',
    marca: 'elem-marca',
    modelo: 'elem-modelo',
    numero_serie: 'elem-serie',
    estado_elemento: 'elem-estado',
    observaciones: 'elem-observaciones',
};

// { id, clave, guardado, ...CAMPOS, fotos_guardadas (n), fotos: {equipo: File, ...}, cambiado }
// El id de una unidad nueva lo genera el celular: el servidor la crea con ese id,
// así una corrección posterior o un reenvío desde la cola no la duplica.
let elementos = [];
let indiceEdicion = -1;
let fotosTemporales = {};

// Al abrir el formulario: las unidades que ya tiene el regulador (vienen con los sitios)
export function cargarElementos(sitio) {
    elementos = (sitio?.properties.elementos || []).map((e) => ({
        ...e, clave: e.id, guardado: true, fotos_guardadas: e.fotos || 0, fotos: {}, cambiado: false,
    }));
    actualizarLista();
}

// Solo lo nuevo o corregido viaja con la verificación
export function obtenerElementosParaEnviar() {
    return elementos.filter((e) => e.cambiado).map((e) => {
        const datos = { id: e.id, clave: e.clave, fotos: { ...e.fotos } };
        Object.keys(CAMPOS).forEach((c) => { datos[c] = e[c] || ''; });
        return datos;
    });
}

// Después de guardar: lo enviado pasa a ser "lo que ya está cargado" (para el resumen del sitio)
export function elementosComoGuardados() {
    return elementos.map(({ fotos, cambiado, clave, guardado, fotos_guardadas, ...datos }) => ({
        ...datos, fotos: Math.max(fotos_guardadas, Object.keys(fotos).length),
    }));
}

function resumen(e) {
    const nFotos = Math.max(e.fotos_guardadas, Object.keys(e.fotos).length);
    return [e.marca, e.modelo, e.numero_serie ? `serie ${e.numero_serie}` : null,
        nFotos ? `${nFotos} foto(s)` : 'sin fotos'].filter(Boolean).join(' · ');
}

function actualizarLista() {
    const cuenta = document.getElementById('reg-elem-cuenta');
    cuenta.textContent = elementos.length ? `${elementos.length} unidad(es)` : 'Sin datos';
    document.getElementById('lista-elementos').innerHTML = elementos.map((e, i) => `
        <div class="medicion-item">
            <div class="med-texto">
                <div class="med-titulo">${escapeHtml(e.identificador_elemento || `Unidad ${i + 1}`)}${e.cambiado ? ' <span class="chip chip-media">a enviar</span>' : ''}</div>
                <div class="med-sub">${escapeHtml(resumen(e))}</div>
            </div>
            <button type="button" class="icon-action" data-accion="editar-elemento" data-indice="${i}" aria-label="Editar"><i class="fa-solid fa-pen" aria-hidden="true"></i></button>
            ${e.guardado ? '' : `<button type="button" class="icon-action danger" data-accion="eliminar-elemento" data-indice="${i}" aria-label="Quitar"><i class="fa-solid fa-trash" aria-hidden="true"></i></button>`}
        </div>`).join('');
}

function pintarFotos(guardadas) {
    FOTOS.forEach((que) => {
        const tile = document.querySelector(`[data-foto-elemento="${que}"]`);
        const foto = fotosTemporales[que];
        tile.style.backgroundImage = foto ? `url("${URL.createObjectURL(foto)}")` : '';
        tile.classList.toggle('con-foto', Boolean(foto));
    });
    document.getElementById('elem-fotos-ayuda').textContent = guardadas
        ? `Ya tiene ${guardadas} foto(s) guardada(s). Sacá una nueva solo si querés reemplazarla.`
        : '';
}

function abrirEditor(indice) {
    indiceEdicion = indice;
    const e = indice === -1 ? null : elementos[indice];
    Object.entries(CAMPOS).forEach(([campo, id]) => {
        document.getElementById(id).value = e ? (e[campo] || '') : '';
    });
    const estado = document.getElementById('elem-estado');
    if (!estado.value) estado.value = 'Operativo';
    estado.dispatchEvent(new Event('change'));   // repinta los botones
    if (!e) document.getElementById('elem-identificador').value = `Unidad ${elementos.length + 1}`;
    fotosTemporales = e ? { ...e.fotos } : {};
    pintarFotos(e?.fotos_guardadas || 0);
    document.getElementById('titulo-elemento').textContent = e ? 'Editar unidad' : 'Agregar unidad';
    abrirModal('modal-elemento');
}

FOTOS.forEach((que) => {
    document.getElementById(`elem-foto-${que}`).addEventListener('change', async (ev) => {
        const file = ev.target.files[0];
        if (!file) return;
        try {
            fotosTemporales[que] = await comprimirImagen(file);
        } catch {
            fotosTemporales[que] = file;
        }
        ev.target.value = '';   // permite repetir la foto
        pintarFotos(indiceEdicion === -1 ? 0 : elementos[indiceEdicion].fotos_guardadas);
    });
});

document.getElementById('btn-add-elemento').addEventListener('click', () => abrirEditor(-1));
document.getElementById('btn-cancelar-elemento').addEventListener('click', () => cerrarModal('modal-elemento'));

document.getElementById('btn-guardar-elemento').addEventListener('click', () => {
    const valores = Object.fromEntries(Object.entries(CAMPOS).map(([c, id]) => [c, document.getElementById(id).value.trim()]));
    if (!valores.marca && !valores.modelo && !valores.numero_serie && !Object.keys(fotosTemporales).length) {
        alert('Cargá al menos la marca, el modelo, la serie o una foto.');
        return;
    }
    if (indiceEdicion === -1) {
        const id = generarUUID();
        elementos.push({ id, clave: id, guardado: false, fotos_guardadas: 0, ...valores,
            fotos: fotosTemporales, cambiado: true });
    } else {
        const e = elementos[indiceEdicion];
        const cambio = Object.keys(CAMPOS).some((c) => (e[c] || '') !== valores[c])
            || Object.keys(fotosTemporales).length !== Object.keys(e.fotos).length
            || Object.keys(fotosTemporales).some((k) => fotosTemporales[k] !== e.fotos[k]);
        Object.assign(e, valores, { fotos: fotosTemporales, cambiado: e.cambiado || cambio });
    }
    actualizarLista();
    cerrarModal('modal-elemento');
});

registrarAcciones({
    'editar-elemento': (el) => abrirEditor(Number(el.dataset.indice)),
    'eliminar-elemento': (el) => {
        // Solo se quitan unidades agregadas ahora; las guardadas se corrigen desde el admin
        if (confirm('¿Quitar esta unidad?')) {
            elementos.splice(Number(el.dataset.indice), 1);
            actualizarLista();
        }
    },
});
