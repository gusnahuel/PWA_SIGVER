/**
 * SIGVER - Piezas de interfaz compartidas: notificaciones, paneles, menú,
 * contadores, botones segmentados y el registro de acciones de los botones.
 */
import { escapeHtml } from './util.js?v=127';

// ==========================================
// Acciones: data-accion="nombre" en el HTML en lugar de onclick="..."
// Cada módulo registra las suyas; un único listener las despacha.
// ==========================================
const acciones = {};

export function registrarAcciones(mapa) {
    for (const [nombre, fn] of Object.entries(mapa)) {
        if (acciones[nombre]) console.warn(`[UI] Acción duplicada: ${nombre}`);
        acciones[nombre] = fn;
    }
}

document.addEventListener('click', (e) => {
    const el = e.target.closest('[data-accion]');
    if (!el) return;
    const fn = acciones[el.dataset.accion];
    if (!fn) {
        console.warn(`[UI] Acción sin registrar: ${el.dataset.accion}`);
        return;
    }
    fn(el, e);
});

// ==========================================
// Notificaciones (toast)
// ==========================================
export function showToast(mensaje, tipo = 'success') {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    toast.className = `toast ${tipo}`;

    const icono = tipo === 'success' ? 'fa-circle-check' : (tipo === 'error' ? 'fa-circle-exclamation' : 'fa-triangle-exclamation');
    const i = document.createElement('i');
    i.className = `fa-solid ${icono}`;
    i.setAttribute('aria-hidden', 'true');
    const texto = document.createElement('span');
    texto.textContent = String(mensaje).trim();
    toast.append(i, texto);

    container.appendChild(toast);

    setTimeout(() => {
        toast.style.animation = 'fadeOut 0.3s ease forwards';
        setTimeout(() => toast.remove(), 300);
    }, 4000);
}

// ==========================================
// Modo escritorio: pantalla ancha con mouse = solo consulta
// (las verificaciones se cargan desde el celular: GPS y cámara)
// ==========================================
const MQ_ESCRITORIO = window.matchMedia('(min-width: 1024px) and (hover: hover)');
export function esEscritorio() {
    return MQ_ESCRITORIO.matches;
}

export function avisarSoloCelular() {
    showToast('Las verificaciones se cargan desde el celular. En la computadora podés consultar.', 'warning');
}

// ==========================================
// Paneles (bottom sheets en el celular, laterales en escritorio)
// ==========================================
const PANELES = ['sheet-verificacion', 'sheet-regulador', 'search-sheet', 'sheet-reclamos'];

export function cerrarPaneles(excepto = null) {
    PANELES.forEach((id) => {
        if (id !== excepto && document.getElementById(id)?.classList.contains('active')) cerrarPanel(id);
    });
}

// `foco`: elemento que recibe el foco al abrir (por defecto, el título del panel)
export function abrirPanel(id, { foco } = {}) {
    cerrarPaneles(id);
    const el = document.getElementById(id);
    if (el.classList.contains('active')) return;
    el.classList.add('active');
    registrarDialogo(el, { modal: false, foco, alCerrar: () => cerrarPanel(id) });
}

export function cerrarPanel(id) {
    const el = document.getElementById(id);
    el.classList.remove('active');
    olvidarDialogo(el);
}

// Cualquier .btn-close cierra el panel que lo contiene
document.addEventListener('click', (e) => {
    const panel = e.target.closest('.btn-close')?.closest('.bottom-sheet');
    if (panel) cerrarPanel(panel.id);
});

// ==========================================
// Diálogos accesibles por teclado y lector de pantalla
// Paneles (no modales: el mapa sigue usable) y modales (bloquean lo de atrás).
// Al abrir: el foco va al título, que anuncia el nombre del diálogo.
// Escape cierra el de arriba; en los modales el Tab no se escapa;
// al cerrar, el foco vuelve a donde estaba.
// ==========================================
const ENFOCABLES = 'a[href], button:not([disabled]), input:not([disabled]):not([type="hidden"]), '
    + 'select:not([disabled]):not([hidden]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';
const pilaDialogos = [];   // { el, origen, modal, alCerrar }

function registrarDialogo(el, { modal, alCerrar, foco }) {
    olvidarDialogo(el);
    el.setAttribute('aria-modal', String(modal));
    pilaDialogos.push({ el, origen: document.activeElement, modal, alCerrar });
    requestAnimationFrame(() => {
        if (foco) {
            foco.focus({ preventScroll: true });
            return;
        }
        const titulo = document.getElementById(el.getAttribute('aria-labelledby'));
        if (titulo) {
            titulo.setAttribute('tabindex', '-1');
            titulo.focus({ preventScroll: true });
        } else {
            el.querySelector(ENFOCABLES)?.focus({ preventScroll: true });
        }
    });
}

function olvidarDialogo(el) {
    const i = pilaDialogos.findIndex((d) => d.el === el);
    if (i === -1) return;
    const [dialogo] = pilaDialogos.splice(i, 1);
    // Devolver el foco solo si sigue dentro del diálogo que se cerró (o en ninguna parte)
    const foco = document.activeElement;
    if ((foco === document.body || el.contains(foco)) && dialogo.origen?.isConnected) {
        dialogo.origen.focus({ preventScroll: true });
    }
}

export function abrirModal(id, { alCerrar } = {}) {
    const el = document.getElementById(id);
    el.style.display = 'flex';
    // Siempre desde arriba: si no, reabre a la altura en que quedó la vez anterior
    el.querySelectorAll('.modal-card').forEach((card) => { card.scrollTop = 0; });
    registrarDialogo(el, { modal: true, alCerrar: alCerrar || (() => cerrarModal(id)) });
}

export function cerrarModal(id) {
    const el = document.getElementById(id);
    el.style.display = 'none';
    olvidarDialogo(el);
}

document.addEventListener('keydown', (e) => {
    const arriba = pilaDialogos[pilaDialogos.length - 1];
    if (!arriba) return;
    if (e.key === 'Escape') {
        e.preventDefault();
        arriba.alCerrar();
        return;
    }
    if (e.key !== 'Tab' || !arriba.modal) return;
    const enfocables = [...arriba.el.querySelectorAll(ENFOCABLES)].filter((x) => x.offsetParent !== null);
    if (!enfocables.length) return;
    const primero = enfocables[0];
    const ultimo = enfocables[enfocables.length - 1];
    const dentro = arriba.el.contains(document.activeElement);
    if (e.shiftKey && (document.activeElement === primero || !dentro)) {
        e.preventDefault();
        ultimo.focus();
    } else if (!e.shiftKey && (document.activeElement === ultimo || !dentro)) {
        e.preventDefault();
        primero.focus();
    }
});

// ==========================================
// Menú lateral y barra de navegación
// ==========================================
export function abrirMenu() {
    const menu = document.getElementById('sidebar-menu');
    menu.classList.add('active');
    document.getElementById('sidebar-overlay').classList.add('active');
    // En el celular el menú se superpone: Escape lo cierra y el foco vuelve al botón
    registrarDialogo(menu, { modal: false, alCerrar: cerrarMenu });
}

export function cerrarMenu() {
    const menu = document.getElementById('sidebar-menu');
    menu.classList.remove('active');
    document.getElementById('sidebar-overlay').classList.remove('active');
    olvidarDialogo(menu);
}

export function menuAbierto() {
    return document.getElementById('sidebar-menu').classList.contains('active');
}

export function marcarNav(nombre) {
    document.querySelectorAll('.nav-item').forEach((n) => n.classList.toggle('activo', n.dataset.nav === nombre));
}

registrarAcciones({
    'abrir-menu': abrirMenu,
    'cerrar-menu': cerrarMenu,
});

// ==========================================
// Contadores e insignia de estado
// ==========================================
export function ponerBadge(id, n) {
    const el = document.getElementById(id);
    if (!el) return;
    el.textContent = n;
    el.style.display = n > 0 ? '' : 'none';
}

export function setStatus(texto, esError = false) {
    const badge = document.getElementById('status-badge');
    if (!badge) return;
    badge.textContent = texto;
    badge.style.display = 'inline-flex';
    badge.classList.remove('offline');
    badge.classList.toggle('error', esError);
}

// ==========================================
// Botones segmentados
// Cada .segmented[data-for] dibuja un botón por <option> del <select> oculto;
// los formularios siguen leyendo el valor del select.
// ==========================================
// Controles segmentados: un grupo de opciones (radio) que reemplaza a un <select>
// oculto. Accesible como radiogroup: nombre del grupo = la etiqueta visible de
// arriba, flechas para cambiar de opción y un solo punto de Tab por grupo.
function pintarSegmentado(contenedor) {
    const select = document.getElementById(contenedor.dataset.for);
    const botones = [...contenedor.querySelectorAll('[role="radio"]')];
    const hayElegido = botones.some((b) => b.dataset.valor === select.value);
    botones.forEach((b, i) => {
        const elegido = b.dataset.valor === select.value;
        b.setAttribute('aria-checked', String(elegido));
        // Sin opción elegida, el Tab entra por la primera
        b.tabIndex = elegido || (!hayElegido && i === 0) ? 0 : -1;
    });
}

function elegirSegmento(contenedor, boton, { enfocar = false } = {}) {
    const select = document.getElementById(contenedor.dataset.for);
    select.value = boton.dataset.valor;
    select.dataset.tocado = '1';
    select.dispatchEvent(new Event('change', { bubbles: true }));
    if (enfocar) boton.focus();
}

export function iniciarSegmentados() {
    document.querySelectorAll('.segmented[data-for]').forEach((contenedor) => {
        const select = document.getElementById(contenedor.dataset.for);
        contenedor.setAttribute('role', 'radiogroup');
        const etiqueta = contenedor.previousElementSibling;
        if (etiqueta?.classList.contains('field-label')) {
            etiqueta.id ||= `${select.id}-etiqueta`;
            contenedor.setAttribute('aria-labelledby', etiqueta.id);
        }
        contenedor.innerHTML = [...select.options].map((o) => `
            <button type="button" role="radio" aria-checked="false" data-valor="${escapeHtml(o.value)}">
                ${o.dataset.color ? `<span class="punto" style="background: ${o.dataset.color};" aria-hidden="true"></span>` : ''}${escapeHtml(o.textContent)}
            </button>`).join('');
        contenedor.addEventListener('click', (e) => {
            const btn = e.target.closest('[role="radio"]');
            if (btn) elegirSegmento(contenedor, btn);
        });
        contenedor.addEventListener('keydown', (e) => {
            const botones = [...contenedor.querySelectorAll('[role="radio"]')];
            const actual = botones.indexOf(document.activeElement);
            if (actual === -1) return;
            const paso = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 }[e.key];
            let destino = null;
            if (paso) destino = botones[(actual + paso + botones.length) % botones.length];
            else if (e.key === 'Home') destino = botones[0];
            else if (e.key === 'End') destino = botones[botones.length - 1];
            if (!destino) return;
            e.preventDefault();
            elegirSegmento(contenedor, destino, { enfocar: true });
        });
        select.addEventListener('change', () => pintarSegmentado(contenedor));
        pintarSegmentado(contenedor);
    });
}

export function repintarSegmentados(form) {
    // form.reset() no dispara 'change': se repinta a mano después del reset
    setTimeout(() => {
        form.querySelectorAll('select').forEach((s) => delete s.dataset.tocado);
        form.querySelectorAll('.segmented[data-for]').forEach(pintarSegmentado);
    }, 0);
}

// Cierra el popup de Leaflet que haya abierto (al abrir un formulario)
export function cerrarPopupsMapa() {
    document.querySelectorAll('.leaflet-popup-close-button').forEach((btn) => btn.click());
}
