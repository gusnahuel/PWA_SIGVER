/**
 * SIGVER - Piezas de interfaz compartidas: notificaciones, paneles, menú,
 * contadores, botones segmentados y el registro de acciones de los botones.
 */
import { escapeHtml } from './util.js?v=116';

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
        if (id !== excepto) document.getElementById(id)?.classList.remove('active');
    });
}

export function abrirPanel(id) {
    cerrarPaneles(id);
    document.getElementById(id).classList.add('active');
}

export function cerrarPanel(id) {
    document.getElementById(id).classList.remove('active');
}

// Cualquier .btn-close cierra el panel que lo contiene
document.addEventListener('click', (e) => {
    const btn = e.target.closest('.btn-close');
    btn?.closest('.bottom-sheet')?.classList.remove('active');
});

// ==========================================
// Menú lateral y barra de navegación
// ==========================================
export function abrirMenu() {
    document.getElementById('sidebar-menu').classList.add('active');
    document.getElementById('sidebar-overlay').classList.add('active');
}

export function cerrarMenu() {
    document.getElementById('sidebar-menu').classList.remove('active');
    document.getElementById('sidebar-overlay').classList.remove('active');
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
function pintarSegmentado(contenedor) {
    const select = document.getElementById(contenedor.dataset.for);
    contenedor.querySelectorAll('button').forEach((b) => {
        b.setAttribute('aria-pressed', String(b.dataset.valor === select.value));
    });
}

export function iniciarSegmentados() {
    document.querySelectorAll('.segmented[data-for]').forEach((contenedor) => {
        const select = document.getElementById(contenedor.dataset.for);
        contenedor.setAttribute('role', 'radiogroup');
        contenedor.innerHTML = [...select.options].map((o) => `
            <button type="button" data-valor="${escapeHtml(o.value)}">
                ${o.dataset.color ? `<span class="punto" style="background: ${o.dataset.color};"></span>` : ''}${escapeHtml(o.textContent)}
            </button>`).join('');
        contenedor.addEventListener('click', (e) => {
            const btn = e.target.closest('button');
            if (!btn) return;
            select.value = btn.dataset.valor;
            select.dataset.tocado = '1';
            select.dispatchEvent(new Event('change', { bubbles: true }));
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
