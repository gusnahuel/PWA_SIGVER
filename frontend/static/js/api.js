/**
 * SIGVER - Llamadas al servidor: token JWT (con renovación), timeout y errores.
 */
import { ejecutarCierreSesion } from './sesion.js?v=122';

// Renovación compartida: con la rotación de tokens, cada refresh se puede usar
// una sola vez. Si varios pedidos vencen juntos (p. ej. los 4 del arranque),
// todos esperan la misma renovación en lugar de pisarse y cerrar la sesión.
let renovacionEnCurso = null;

async function renovarToken() {
    const refresh = localStorage.getItem('sigver_refresh_token');
    if (!refresh) return { ok: false, vencida: true };

    const res = await fetch('/api/token/refresh/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh })
    });
    if (!res.ok) {
        // 401: el refresh venció o fue revocado -> hay que volver a ingresar.
        // Otro error (429, 5xx): problema pasajero, no se cierra la sesión.
        return { ok: false, vencida: res.status === 401 };
    }
    const data = await res.json();
    localStorage.setItem('sigver_token', data.access);
    if (data.refresh) localStorage.setItem('sigver_refresh_token', data.refresh);
    return { ok: true };
}

function renovarUnaVez() {
    if (!renovacionEnCurso) {
        renovacionEnCurso = renovarToken().finally(() => { renovacionEnCurso = null; });
    }
    return renovacionEnCurso;
}

export async function fetchConToken(url, options = {}) {
    const conToken = () => ({
        ...options,
        headers: { ...options.headers, 'Authorization': `Bearer ${localStorage.getItem('sigver_token')}` },
    });

    const res = await fetch(url, conToken());
    if (res.status !== 401) return res;

    // El access token venció (dura 60 min): renovarlo y repetir el pedido
    try {
        const renovacion = await renovarUnaVez();
        if (renovacion.ok) return await fetch(url, conToken());
        if (renovacion.vencida) ejecutarCierreSesion({ motivo: 'vencida' });
    } catch (error) {
        // Sin red: no se cierra la sesión, el pedido falla como cualquier otro
        console.error('Error renovando token:', error);
    }
    return res;
}

// fetch con timeout (en mala señal un POST con fotos puede colgarse)
export async function fetchConTimeout(url, options = {}, ms = 15000) {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), ms);
    try {
        return await fetchConToken(url, { ...options, signal: controller.signal });
    } finally {
        clearTimeout(timeoutId);
    }
}

// true si el fallo fue de red/timeout (y por lo tanto conviene guardar offline)
export function esErrorDeRed(err) {
    return !navigator.onLine || err?.name === 'AbortError' || err instanceof TypeError;
}

// Lee la respuesta de error de DRF y la convierte en un texto corto
export async function describirErrorServidor(res) {
    try {
        const data = await res.json();
        if (data.detail) return data.detail;
        return Object.entries(data)
            .map(([campo, msg]) => `${campo}: ${Array.isArray(msg) ? msg.join(' ') : JSON.stringify(msg)}`)
            .join(' | ');
    } catch {
        return `HTTP ${res.status}`;
    }
}
