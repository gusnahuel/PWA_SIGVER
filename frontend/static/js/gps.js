/**
 * SIGVER - GPS de las verificaciones.
 *
 * Muestra en la tarjeta del formulario a qué distancia está el técnico del
 * equipo (orientativo) y guarda la posición para enviarla. La distancia que
 * vale es la que calcula el servidor con esas coordenadas.
 */
import { calcularDistanciaMetros } from './util.js?v=128';

export const UMBRAL_EN_EL_LUGAR_M = 50;
export const UMBRAL_CERCA_M = 300;

export function sugerirCoincidencia(metros) {
    if (metros <= UMBRAL_EN_EL_LUGAR_M) return 'SI';
    return metros <= UMBRAL_CERCA_M ? 'APROXIMADA' : 'NO';
}

/**
 * Pide la posición y la muestra en la tarjeta `prefijo`-gps-card.
 * `destino`: feature GeoJSON del equipo (o null si no tiene coordenadas).
 * `alObtener(posicion, metros)`: se llama con {lat, lng, precision} y la distancia (o null).
 * Devuelve una función que devuelve la última posición obtenida (o null).
 */
export function seguirUbicacion(prefijo, destino, alObtener = () => {}) {
    const card = document.getElementById(`${prefijo}-gps-card`);
    const titulo = document.getElementById(`${prefijo}-gps-titulo`);
    const sub = document.getElementById(`${prefijo}-gps-sub`);
    let posicion = null;

    card.classList.remove('ok', 'lejos');
    titulo.textContent = 'Buscando tu ubicación...';
    sub.textContent = 'Activá el GPS: la ubicación se guarda con la verificación';

    if (!navigator.geolocation) {
        titulo.textContent = 'Ubicación no disponible';
        sub.textContent = 'Este dispositivo no informa GPS';
        return () => null;
    }

    navigator.geolocation.getCurrentPosition((pos) => {
        posicion = { lat: pos.coords.latitude, lng: pos.coords.longitude, precision: pos.coords.accuracy };
        const precision = `GPS ±${Math.round(pos.coords.accuracy)} m`;
        if (!destino?.geometry) {
            titulo.textContent = 'Ubicación registrada';
            sub.textContent = `${precision} · el equipo no tiene coordenadas para comparar`;
            card.classList.add('ok');
            alObtener(posicion, null);
            return;
        }
        const [lngEquipo, latEquipo] = destino.geometry.coordinates;
        const metros = calcularDistanciaMetros(posicion.lat, posicion.lng, latEquipo, lngEquipo);
        const sugerido = sugerirCoincidencia(metros);
        const texto = { SI: 'coincide', APROXIMADA: 'aproximada', NO: 'no coincide' }[sugerido];
        titulo.textContent = metros < 1000
            ? `Estás a ${Math.round(metros)} m del equipo`
            : `Estás a ${(metros / 1000).toFixed(1).replace('.', ',')} km del equipo`;
        sub.textContent = `${precision} · ubicación ${texto}`;
        card.classList.add(sugerido === 'NO' ? 'lejos' : 'ok');
        alObtener(posicion, metros);
    }, () => {
        titulo.textContent = 'No se pudo obtener el GPS';
        sub.textContent = 'Revisá los permisos. Se puede guardar igual, sin ubicación';
    }, { enableHighAccuracy: true, timeout: 15000, maximumAge: 30000 });

    return () => posicion;
}

// Campos que espera el servidor (vacío si no hubo GPS)
export function datosGps(posicion) {
    if (!posicion) return {};
    return {
        gps_latitud: posicion.lat,
        gps_longitud: posicion.lng,
        gps_precision_m: Math.round(posicion.precision),
    };
}
