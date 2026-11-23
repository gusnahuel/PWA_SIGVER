/**
 * SIGVER - Estado compartido entre módulos.
 * Un solo objeto: cualquier módulo lo importa y lee/escribe sus campos.
 */
export const estado = {
    usuario: null,   // perfil de /api/usuarios/me/ (null = sin sesión)
    equipos: [],     // features GeoJSON de ETCs
    sitios: [],      // features GeoJSON de sitios con regulador
    mapa: null,      // instancia de Leaflet
};
