/**
 * SIGVER - Sesión: login, datos del usuario en el menú y cierre de sesión.
 */
import { estado } from './estado.js?v=116';
import { iniciales } from './util.js?v=116';
import { registrarAcciones, showToast } from './ui.js?v=116';
import { obtenerPendientesPropios } from './sync.js?v=116';

const ROLES_GESTION = ['supervisor_zona', 'admin_eam'];
const NOMBRE_ROL = {
    tecnico_campo: 'Técnico de campo',
    supervisor_zona: 'Supervisor de zona',
    admin_eam: 'Administración EAM',
    consulta: 'Consulta',
};

export function esGestor(usuario = estado.usuario) {
    return !!usuario && (ROLES_GESTION.includes(usuario.rol) || usuario.is_superuser === true);
}

export function haySesion() {
    return !!localStorage.getItem('sigver_token');
}

// Recupera el usuario guardado al abrir la app (si había sesión)
export function restaurarSesion() {
    const userGuardado = localStorage.getItem('sigver_user');
    if (haySesion() && userGuardado) {
        estado.usuario = JSON.parse(userGuardado);
        ocultarLogin();
    }
}

// Completa el menú con el nombre, el rol y las opciones de gestión
function prepararMenuUsuario() {
    const usuario = estado.usuario;
    if (!usuario) return;
    const nombre = usuario.nombre || usuario.username || 'Usuario';
    document.getElementById('menu-user-name').textContent = nombre;
    document.getElementById('menu-user-avatar').textContent = iniciales(nombre);
    document.getElementById('btn-avatar').textContent = iniciales(nombre);
    document.getElementById('menu-user-role').textContent = NOMBRE_ROL[usuario.rol] || 'Personal de operaciones';

    const gestor = esGestor(usuario);
    document.getElementById('menu-gestion').style.display = gestor ? '' : 'none';
    document.getElementById('menu-gestion-titulo').style.display = gestor ? '' : 'none';
    const etiqueta = gestor ? 'Reclamos de la zona' : 'Mis reclamos';
    document.getElementById('menu-reclamos-label').textContent = etiqueta;
    document.getElementById('reclamos-titulo-texto').textContent = etiqueta;
}

export function ocultarLogin() {
    prepararMenuUsuario();
    const loginScreen = document.getElementById('login-screen');
    const appHeader = document.getElementById('app-header');
    if (loginScreen) loginScreen.style.display = 'none';
    if (appHeader) appHeader.style.display = 'flex';
}

// El service worker guarda respuestas de /api/ para usar sin señal, sin
// distinguir usuario: al salir se borran para que el próximo no las vea.
// (Los mapas descargados se conservan.)
async function borrarDatosApiDelCache() {
    if (!('caches' in window)) return;
    for (const nombre of await caches.keys()) {
        if (nombre.includes('tiles')) continue;
        const cache = await caches.open(nombre);
        for (const pedido of await cache.keys()) {
            if (new URL(pedido.url).pathname.startsWith('/api/')) await cache.delete(pedido);
        }
    }
}

// Revoca el refresh token en el servidor (si alguien lo copió, deja de servir).
// Sin señal no se puede: igual se cierra la sesión en el celular.
async function revocarToken() {
    const refresh = localStorage.getItem('sigver_refresh_token');
    if (!refresh || !navigator.onLine) return;
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 4000);
    try {
        await fetch('/api/token/logout/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ refresh }),
            signal: controller.signal,
        });
    } catch {
        // sin respuesta: el token vence solo a los 7 días
    } finally {
        clearTimeout(timeout);
    }
}

let cerrandoSesion = false;

// Cierra la sesión y vuelve al login.
// motivo 'vencida': el servidor ya no acepta el token (no hace falta revocarlo).
// Las verificaciones sin enviar NO se borran: quedan para cuando su dueño vuelva a ingresar.
export async function ejecutarCierreSesion({ motivo = 'usuario' } = {}) {
    if (cerrandoSesion) return;
    cerrandoSesion = true;

    if (motivo !== 'vencida') await revocarToken();
    try {
        await borrarDatosApiDelCache();
    } catch (err) {
        console.warn('No se pudo limpiar el caché de la API:', err);
    }

    ['sigver_token', 'sigver_refresh_token', 'sigver_user', 'sigver_reclamos_cache', 'sigver_reclamos_resueltos']
        .forEach((k) => localStorage.removeItem(k));
    if (motivo === 'vencida') {
        sessionStorage.setItem('sigver_aviso_login', 'Tu sesión venció. Ingresá de nuevo para seguir.');
    }
    window.location.reload();
}

// ==========================================
// Formulario de login
// ==========================================
const errorLogin = document.getElementById('login-error');

// Aviso que dejó el cierre anterior (p. ej. sesión vencida)
const avisoPendiente = sessionStorage.getItem('sigver_aviso_login');
if (avisoPendiente) {
    errorLogin.textContent = avisoPendiente;
    errorLogin.classList.add('info');
    sessionStorage.removeItem('sigver_aviso_login');
}

// Traduce la respuesta del servidor a un mensaje que el técnico entienda
async function mensajeDeError(res) {
    if (res.status === 400 || res.status === 401) return 'Usuario o contraseña incorrectos.';
    if (res.status === 429) {
        try {
            return (await res.json()).detail || 'Demasiados intentos. Esperá unos minutos.';
        } catch {
            return 'Demasiados intentos. Esperá unos minutos.';
        }
    }
    return 'El servidor no responde. Probá de nuevo en unos minutos.';
}

async function pedir(url, opciones) {
    try {
        return await fetch(url, opciones);
    } catch {
        throw new Error(navigator.onLine
            ? 'No se pudo conectar con el servidor. Revisá la señal y probá de nuevo.'
            : 'Sin conexión. El primer ingreso en este celular necesita internet.');
    }
}

document.getElementById('login-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const btn = document.getElementById('btn-login');

    btn.disabled = true;
    btn.textContent = 'Ingresando...';
    errorLogin.textContent = '';
    errorLogin.classList.remove('info');

    // Sin espacios accidentales (el teclado del celular a veces agrega uno al final)
    const username = document.getElementById('login-username').value.trim();
    const password = document.getElementById('login-password').value;

    try {
        // 1. Pedir el token a Django
        const res = await pedir('/api/token/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password })
        });
        if (!res.ok) throw new Error(await mensajeDeError(res));

        const data = await res.json();
        localStorage.setItem('sigver_token', data.access);
        localStorage.setItem('sigver_refresh_token', data.refresh);

        // 2. Pedir los datos del usuario
        const resUser = await pedir('/api/usuarios/me/', {
            headers: { 'Authorization': `Bearer ${data.access}` }
        });
        if (!resUser.ok) throw new Error('No se pudo obtener tu perfil. Probá de nuevo.');
        const userData = await resUser.json();
        if (!userData.personal_id) {
            showToast('Tu usuario no está vinculado a una ficha de Personal. No podrás registrar verificaciones.', 'warning');
        }
        localStorage.setItem('sigver_user', JSON.stringify(userData));
        estado.usuario = userData;

        ocultarLogin();
        // Recargar para que el mapa arranque con la sesión
        window.location.reload();
    } catch (err) {
        // Si falló a mitad de camino, no dejar un token suelto sin perfil
        localStorage.removeItem('sigver_token');
        localStorage.removeItem('sigver_refresh_token');
        errorLogin.textContent = err.message;
    } finally {
        btn.disabled = false;
        btn.textContent = 'Ingresar';
    }
});

// Mostrar / ocultar contraseña (botón real: se puede usar con teclado y lector de pantalla)
document.getElementById('toggle-password').addEventListener('click', (e) => {
    const boton = e.currentTarget;
    const passwordInput = document.getElementById('login-password');
    const mostrar = passwordInput.type === 'password';
    passwordInput.type = mostrar ? 'text' : 'password';
    boton.setAttribute('aria-pressed', String(mostrar));
    boton.setAttribute('aria-label', mostrar ? 'Ocultar contraseña' : 'Mostrar contraseña');
    const icono = boton.querySelector('i');
    icono.classList.toggle('fa-eye', !mostrar);
    icono.classList.toggle('fa-eye-slash', mostrar);
});

// ==========================================
// Modal de cierre de sesión
// ==========================================
async function abrirModalLogout() {
    const texto = document.getElementById('logout-texto');
    const confirmar = document.querySelector('[data-accion="confirmar-logout"]');
    let pendientes = 0;
    try {
        pendientes = (await obtenerPendientesPropios()).length;
    } catch {
        // si no se puede leer la cola, se muestra el aviso normal
    }
    if (pendientes > 0) {
        texto.innerHTML = `<strong>Tenés ${pendientes} verificación${pendientes === 1 ? '' : 'es'} sin enviar.</strong> `
            + 'No se pierden: se envían cuando vuelvas a ingresar con tu usuario y haya señal. '
            + 'Si otra persona usa este celular, no se enviarán a su nombre.';
        confirmar.textContent = 'Cerrar sesión igual';
    } else {
        texto.textContent = 'Vas a tener que ingresar tu usuario y contraseña de nuevo.';
        confirmar.textContent = 'Cerrar sesión';
    }
    document.getElementById('logout-modal').style.display = 'flex';
}

registrarAcciones({
    'abrir-logout': abrirModalLogout,
    'cancelar-logout': () => { document.getElementById('logout-modal').style.display = 'none'; },
    'confirmar-logout': (boton) => {
        boton.disabled = true;
        boton.textContent = 'Cerrando...';
        ejecutarCierreSesion();
    },
});
