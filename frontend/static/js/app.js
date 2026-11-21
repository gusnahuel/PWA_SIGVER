/**
 * SIGVER - App principal
 * Muestra los equipos (ETC + Reguladores) en un mapa Leaflet
 * con clustering para rendimiento en móviles.
 */
import { guardarVerificacionOffline, obtenerPendientes, eliminarDeOutbox } from './db.js';
// ==========================================
// 1. Configuración
// ==========================================
const API_BASE = '/api/inventario';
const CENTRO_PARAGUAY = [-27.16, -56.24];
const ZOOM_INICIAL = 10;
let isSyncing = false; // 
// ==========================================
// NOTIFICACIONES MODERNAS (TOAST)
// ==========================================
window.showToast = function(mensaje, tipo = 'success') {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    toast.className = `toast ${tipo}`;
    
    const icono = tipo === 'success' ? '✅' : (tipo === 'error' ? '❌' : '⚠️');
    toast.innerHTML = `<span>${icono}</span> <span>${mensaje}</span>`;
    
    container.appendChild(toast);
    
    // Desaparece a los 3 segundos
    setTimeout(() => {
        toast.style.animation = 'fadeOut 0.3s ease forwards';
        setTimeout(() => toast.remove(), 300);
    }, 4000);
};
let todosLosEquipos = []; // Guarda los ETCs
let todosLosSitios = [];  // Guarda los Reguladores
let mapGlobal = null;     // Referencia global al mapa para poder volar a un equipo

function generarUUID() {
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
        var r = Math.random() * 16 | 0, v = c == 'x' ? r : (r & 0x3 | 0x8);
        return v.toString(16);
    });
}

function comprimirImagen(file, maxWidth = 1024, quality = 0.6) {
    return new Promise((resolve) => {
        const reader = new FileReader();
        reader.readAsDataURL(file);
        reader.onload = (event) => {
            const img = new Image();
            img.src = event.target.result;
            img.onload = () => {
                const canvas = document.createElement('canvas');
                let width = img.width;
                let height = img.height;
                if (width > maxWidth) {
                    height = Math.round((height * maxWidth) / width);
                    width = maxWidth;
                }
                canvas.width = width;
                canvas.height = height;
                const ctx = canvas.getContext('2d');
                ctx.drawImage(img, 0, 0, width, height);
                canvas.toBlob((blob) => {
                    resolve(new File([blob], file.name, { type: 'image/jpeg', lastModified: Date.now() }));
                }, 'image/jpeg', quality);
            };
        };
    });
}
async function fetchConToken(url, options = {}) {
    // 1. Preparamos los headers con el token actual
    let token = localStorage.getItem('sigver_token');
    options.headers = {
        ...options.headers,
        'Authorization': `Bearer ${token}`
    };

    // 2. Hacemos la petición
    let res = await fetch(url, options);

    // 3. Si el token venció (Error 401), intentamos renovarlo
    if (res.status === 401) {
        console.log("Token vencido, intentando renovar automáticamente...");
        const refresh = localStorage.getItem('sigver_refresh_token');
        
        if (refresh) {
            try {
                const refreshRes = await fetch('/api/token/refresh/', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ refresh: refresh })
                });

                if (refreshRes.ok) {
                    const refreshData = await refreshRes.json();
                    localStorage.setItem('sigver_token', refreshData.access);
                    
                    // Volvemos a hacer la petición original con el token nuevo
                    options.headers['Authorization'] = `Bearer ${refreshData.access}`;
                    return await fetch(url, options);
                } else {
                    // Si el refresh token también venció (pasaron 7 días)
                    cerrarSesion();
                }
            } catch (error) {
                console.error("Error renovando token:", error);
            }
        } else {
            cerrarSesion();
        }
    }
    return res;
}

// Abrir el modal
window.abrirModalLogout = function() {
    document.getElementById('logout-modal').style.display = 'flex';
};

// Cerrar el modal sin hacer nada
window.cerrarModalLogout = function() {
    document.getElementById('logout-modal').style.display = 'none';
};

// Ejecutar la acción real de cerrar sesión
window.ejecutarCierreSesion = function() {
    // Borramos todas las credenciales y cachés
    localStorage.removeItem('sigver_token');
    localStorage.removeItem('sigver_refresh_token');
    localStorage.removeItem('sigver_user');
    localStorage.removeItem('sigver_reclamos_cache'); 
    localStorage.removeItem('sigver_reclamos_resueltos'); 
    
    // Recargamos para volver al Login
    window.location.reload();
};

// ==========================================
// AUTENTICACIÓN Y SESIÓN
// ==========================================
let usuarioLogueado = null;

// Verificar si ya hay un token guardado al abrir la app
const tokenGuardado = localStorage.getItem('sigver_token');
const userGuardado = localStorage.getItem('sigver_user');

if (tokenGuardado && userGuardado) {
    usuarioLogueado = JSON.parse(userGuardado);
    ocultarLogin();
}

// Evento de inicio de sesión
document.getElementById('login-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const btn = document.getElementById('btn-login');
    const errorDiv = document.getElementById('login-error');
    
    btn.disabled = true;
    btn.textContent = 'Ingresando...';
    errorDiv.textContent = '';

    const username = document.getElementById('login-username').value;
    const password = document.getElementById('login-password').value;

    try {
        // 1. Pedir el Token a Django
        const res = await fetch('/api/token/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password })
        });

        if (!res.ok) throw new Error('Usuario o contraseña incorrectos');
        
        const data = await res.json();
        localStorage.setItem('sigver_token', data.access);
        localStorage.setItem('sigver_refresh_token', data.refresh);

        // 2. Pedir los datos del usuario
        const resUser = await fetch('/api/usuarios/me/', {
            headers: { 'Authorization': `Bearer ${data.access}` }
        });
        
        const userData = await resUser.json();
        localStorage.setItem('sigver_user', JSON.stringify(userData));
        usuarioLogueado = userData;

        ocultarLogin();
        
        // Recargar la página para que el mapa arranque con la sesión
        window.location.reload(); 

    } catch (err) {
        errorDiv.textContent = err.message;
    } finally {
        btn.disabled = false;
        btn.textContent = 'Ingresar';
    }
});

function ocultarLogin() {
    const loginScreen = document.getElementById('login-screen');
    const appHeader = document.getElementById('app-header');
    
    if (loginScreen) {
        loginScreen.style.display = 'none';
    }
    
    if (appHeader) {
        appHeader.style.display = 'flex';
    }
}
// ==========================================
// 2. Íconos personalizados
// ==========================================
function createEtcIcon(estado) {
    const color = estado === 'ABIERTO' ? '#f5b000' : '#1e88e5';
    const letra = estado === 'ABIERTO' ? 'A' : 'C';

    return L.divIcon({
        html: `
            <div style="
                background-color: ${color};
                color: white;
                font-weight: bold;
                font-size: 11px;
                width: 24px;
                height: 24px;
                border-radius: 50%;
                display: flex;
                align-items: center;
                justify-content: center;
                border: 2px solid white;
                box-shadow: 0 2px 6px rgba(0,0,0,0.4);
            ">${letra}</div>
        `,
        className: '',
        iconSize: [24, 24],
        iconAnchor: [12, 12],
        popupAnchor: [0, -12],
    });
}

function createReguladorIcon() {
    return L.divIcon({
        html: `
            <div style="
                background-color: #dc3545;
                color: white;
                font-weight: bold;
                font-size: 11px;
                width: 24px;
                height: 24px;
                border-radius: 50%;
                display: flex;
                align-items: center;
                justify-content: center;
                border: 2px solid white;
                box-shadow: 0 2px 6px rgba(0,0,0,0.4);
            ">R</div>
        `,
        className: '',
        iconSize: [24, 24],
        iconAnchor: [12, 12],
        popupAnchor: [0, -12],
    });
}

// ==========================================
// 3. Ícono custom para los clusters
// ==========================================
function clusterIcon(cluster) {
    const count = cluster.getChildCount();

    let bg = '#28a745';        // verde (pocos)
    let dim = 36;

    if (count >= 10) {
        bg = '#ffc107';        // amarillo (medio)
        dim = 42;
    }
    if (count >= 50) {
        bg = '#dc3545';        // rojo (muchos)
        dim = 50;
    }

    const fontSize = count < 10 ? 13 : count < 50 ? 14 : 16;

    return L.divIcon({
        html: `
            <div style="
                background: ${bg};
                color: white;
                width: ${dim}px;
                height: ${dim}px;
                border-radius: 50%;
                display: flex;
                align-items: center;
                justify-content: center;
                font-weight: bold;
                font-size: ${fontSize}px;
                border: 3px solid white;
                box-shadow: 0 3px 8px rgba(0,0,0,0.4);
            ">${count}</div>
        `,
        className: '',
        iconSize: [dim, dim],
    });
}

// ==========================================
// 4. Inicialización del mapa
// ==========================================
function initMap() {
    const map = L.map('map', {
        center: CENTRO_PARAGUAY,
        zoom: ZOOM_INICIAL,
        zoomControl: false // Quitamos el zoom por defecto para ponerlo abajo a la derecha
    });

    // 1. Capa Satelital (Esri)
    const mapaSatelital = L.tileLayer(
        'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
        {
            maxZoom: 19,
            attribution: '&copy; Esri &mdash; SIGVER ANDE',
        }
    ).addTo(map);

    // 2. Capa de Etiquetas (Ciudades, Rutas, Límites) - ¡ACTIVADA!
    const etiquetas = L.tileLayer(
        'https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}',
        { maxZoom: 19 }
    ).addTo(map); // 👈 .addTo(map) hace que se muestre por defecto

    // 3. Capa de Calles (Alternativa por si quieren ver el mapa político)
    const calles = L.tileLayer(
        'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
        { maxZoom: 19 }
    );

    // 4. Control de Capas (Para que el usuario prenda/apague lo que quiera)
    const baseMaps = {
        "Satelital (Esri)": mapaSatelital,
        "Calles (OSM)": calles
    };

    window.layerControl = L.control.layers(baseMaps, {
        "Nombres de Ciudades": etiquetas
    }, { position: 'topright', collapsed: true }).addTo(map);

    // Agregamos los botones de Zoom abajo a la derecha
    L.control.zoom({ position: 'bottomleft' }).addTo(map);

    return map;
}
// ==========================================
// 26. Geolocalización (Mi Ubicación)
// ==========================================
let marcadorUsuario = null; // Variable para guardar el punto y no duplicarlo

window.centrarEnMiUbicacion = function() {
    cerrarMenu();

    if (!navigator.geolocation) {
        showToast('Tu navegador no soporta geolocalización.', 'error');
        return;
    }

    showToast('Obteniendo tu ubicación GPS...', 'warning');

    navigator.geolocation.getCurrentPosition(
        (position) => {
            const lat = position.coords.latitude;
            const lng = position.coords.longitude;
            const precision = position.coords.accuracy;

            if (marcadorUsuario) {
                mapGlobal.removeLayer(marcadorUsuario);
            }

            // El punto azul
            marcadorUsuario = L.circleMarker([lat, lng], {
                radius: 8,
                fillColor: "#0ea5e9", 
                color: "#ffffff",     
                weight: 3,
                opacity: 1,
                fillOpacity: 1
            }).addTo(mapGlobal);

            // 👇 REDISEÑO DEL POPUP 👇
            marcadorUsuario.bindPopup(`
                <div style="font-family: 'Inter', sans-serif; padding: 4px 8px; text-align: center;">
                    <div style="color: #0ea5e9; font-weight: 800; font-size: 13px; margin-bottom: 2px;">Mi Ubicación</div>
                    <div style="color: #64748b; font-size: 11px;">Precisión: <b>±${Math.round(precision)} m</b></div>
                </div>
            `);

            // Volamos a la ubicación
            mapGlobal.flyTo([lat, lng], 18, { duration: 1.5 });
            
            // 👇 ELIMINAMOS EL setTimeout QUE ABRÍA EL POPUP AUTOMÁTICAMENTE 👇

            showToast('Ubicación encontrada.', 'success');
        },
        (error) => {
            console.error("Error GPS:", error);
            showToast('No se pudo obtener la ubicación. Revisá los permisos.', 'error');
        },
        { enableHighAccuracy: true, timeout: 10000, maximumAge: 0 }
    );
};

// ==========================================
// 5. Cargar ETCs
// ==========================================
async function cargarETCs(capaCluster) {
    const res = await fetchConToken(`${API_BASE}/equipos/`);
    if (!res.ok) throw new Error(`Error HTTP ${res.status}`);

    const data = await res.json();
    const features = data.features || [];
    todosLosEquipos = features;

    const markers = [];
    features.forEach((f) => {
        const [lng, lat] = f.geometry.coordinates;
        const p = f.properties;

        const marker = L.marker([lat, lng], {
            icon: createEtcIcon(p.estado_seccionador),
        });

        // 👇 NUEVO DISEÑO MODERNO PARA ETC 👇
        const claseEstado = p.estado_seccionador === 'ABIERTO' ? 'status-abierto' : 'status-cerrado';

        marker.bindPopup(`
            <div class="modern-popup">
                <div class="popup-header header-etc">
                    <i class="fa-solid fa-bolt"></i> ETC ${p.nro_equipo}
                </div>
                <div class="popup-body">
                    <div class="popup-row">
                        <span class="popup-label"><i class="fa-solid fa-tower-broadcast"></i> Alimentador</span>
                        <span class="popup-value">${p.alimentador_codigo}</span>
                    </div>
                    <div class="popup-row">
                        <span class="popup-label"><i class="fa-solid fa-circle-info"></i> Estado</span>
                        <span class="popup-value ${claseEstado}">${p.estado_seccionador}</span>
                    </div>
                </div>
                <div class="popup-footer">
                    <button class="btn-popup-modern" onclick="abrirFormularioVerificacion('${f.id}', '${p.nro_equipo}')">
                        <i class="fa-solid fa-clipboard-check"></i> Verificar Equipo
                    </button>
                </div>
            </div>
        `);

        markers.push(marker);
    });

    capaCluster.addLayers(markers);
    return features.length;
}

// ==========================================
// 6. Cargar Reguladores (Sitios)
// ==========================================
async function cargarSitios(capaCluster) {
    const res = await fetchConToken(`${API_BASE}/sitios/`);
    if (!res.ok) throw new Error(`Error HTTP ${res.status}`);

    const data = await res.json();
    const features = data.features || [];
    const markers = [];

    features.forEach((f) => {
        const [lng, lat] = f.geometry.coordinates;
        const p = f.properties;

        const marker = L.marker([lat, lng], { icon: createReguladorIcon() });

        marker.on('popupopen', function() {
            window.sitioSeleccionadoTemp = {
                componenteId: p.componente_id,
                codSitio: p.id_sitio
            };
        });

        // 👇 NUEVO DISEÑO MODERNO PARA REGULADOR 👇
        marker.bindPopup(`
            <div class="modern-popup">
                <div class="popup-header header-regulador">
                    <i class="fa-solid fa-plug"></i> Regulador ${p.id_sitio}
                </div>
                <div class="popup-body">
                    <div class="popup-row">
                        <span class="popup-label"><i class="fa-solid fa-barcode"></i> Código</span>
                        <span class="popup-value">${p.cod_sitio}</span>
                    </div>
                    <div class="popup-row">
                        <span class="popup-label"><i class="fa-solid fa-tower-broadcast"></i> Alimentador</span>
                        <span class="popup-value">${p.alimentador_codigo}</span>
                    </div>
                </div>
                <div class="popup-footer">
                    <button class="btn-popup-modern btn-regulador" onclick="abrirFormularioRegulador('${p.componente_id}', '${p.id_sitio}')">
                        <i class="fa-solid fa-clipboard-check"></i> Verificar Regulador
                    </button>
                </div>
            </div>
        `);

        markers.push(marker);
    });

    capaCluster.addLayers(markers);
    return features.length;
}
// ==========================================
// 7. Actualizar insignia de estado
// ==========================================
function setStatus(texto, esError = false) {
    const badge = document.getElementById('status-badge');
    if (!badge) return;
    badge.textContent = texto;
    badge.classList.toggle('error', esError);
}

// ==========================================
// 8. Bootstrap de la app
// ==========================================
async function iniciarApp() {
    document.getElementById('loading-screen').style.display = 'flex';
     document.getElementById('map').style.display = 'block'; 
    try {
        console.log("🚀 Iniciando mapa...");
        mapGlobal = initMap();
        const map = mapGlobal;

        // Crear los grupos con clustering
        const capaETCs = L.markerClusterGroup({
            maxClusterRadius: 120,
            showCoverageOnHover: false,
            zoomToBoundsOnClick: true,
            spiderfyOnMaxZoom: true,
            disableClusteringAtZoom: 14,
            chunkedLoading: true,
            chunkInterval: 100,
            chunkDelay: 50,
            iconCreateFunction: clusterIcon,
        }).addTo(map);

        const capaSitios = L.markerClusterGroup({
            maxClusterRadius: 120,
            showCoverageOnHover: false,
            zoomToBoundsOnClick: true,
            spiderfyOnMaxZoom: true,
            disableClusteringAtZoom: 14,
            chunkedLoading: true,
            iconCreateFunction: clusterIcon,
        }).addTo(map);

        setStatus('Cargando...');

        const [nETCs, nSitios] = await Promise.all([
            cargarETCs(capaETCs),
            cargarSitios(capaSitios),
            cargarFallas(), // precarga de fallas para el formulario
            cargarPuntosTermografia(),
        ]);

        

        setStatus(`✓ ${nETCs + nSitios} equipos`);

        window.layerControl.addOverlay(capaETCs, 'ETCs (Telecomandados)');
        window.layerControl.addOverlay(capaSitios, 'Reguladores');
        
        const loader = document.getElementById('loading-screen');
        if (loader) {
            loader.style.opacity = '0';
            setTimeout(() => loader.style.display = 'none', 500);
        }

    } catch (err) {
        console.error('Error:', err);
        setStatus('Error de conexión', true);

        document.getElementById('loading-screen').style.display = 'none';
    }
}

// ==========================================
// CONTROL DE ARRANQUE (Solo si hay sesión)
// ==========================================
const tokenInicial = localStorage.getItem('sigver_token');
if (tokenInicial) {
    // Ya está logueado: ocultamos login y arrancamos el mapa
    ocultarLogin();
    iniciarApp();
} else {
    // No está logueado: nos aseguramos de que el mapa NO arranque
    console.log("Esperando inicio de sesión...");

    document.getElementById('loading-screen').style.display = 'none';
}

// ==========================================
// 11. Lógica del Formulario de Verificación
// ==========================================
let equipoSeleccionadoId = null;

window.abrirFormularioVerificacion = function(equipoId, nroEquipo) {
    equipoSeleccionadoId = equipoId;
    document.getElementById('verif-nro-equipo').textContent = nroEquipo;
    document.getElementById('form-verificacion').reset();
    document.getElementById('grupo-falla').style.display = 'none';
    document.getElementById('verif-status').textContent = '';
    document.getElementById('sheet-verificacion').classList.add('active');
    document.querySelectorAll('.leaflet-popup-close-button').forEach(btn => btn.click());
    document.querySelectorAll('.checkbox-falla').forEach(cb => cb.checked = false);
    document.getElementById('preview-foto').style.display = 'none';
};
// Mostrar preview de la foto
document.getElementById('verif-foto').addEventListener('change', (e) => {
    const file = e.target.files[0];
    const preview = document.getElementById('preview-foto');
    if (file) {
        const reader = new FileReader();
        reader.onload = (e) => {
            preview.src = e.target.result;
            preview.style.display = 'block';
        };
        reader.readAsDataURL(file);
    } else {
        preview.style.display = 'none';
    }
});

document.getElementById('btn-cerrar-sheet').addEventListener('click', () => {
    document.getElementById('sheet-verificacion').classList.remove('active');
});

document.getElementById('verif-tiene-inconveniente').addEventListener('change', (e) => {
    const grupoFalla = document.getElementById('grupo-falla');
    if (e.target.value === 'si') {
        grupoFalla.style.display = 'block';
        cargarFallas();
    } else {
        grupoFalla.style.display = 'none';
    }
});

async function cargarFallas() {
    
    // 1. Intentar leer del localStorage (offline)
    const fallasLocales = localStorage.getItem('sigver_fallas');
    if (fallasLocales && fallasLocales !== 'undefined') {
        try {
            llenarSelectFallas(JSON.parse(fallasLocales));
        } catch(e) { console.warn("Error leyendo fallas locales"); }
    }

    // 2. Si hay internet, actualizar
    if (navigator.onLine) {
        try {
            const res = await fetchConToken('/api/operaciones/fallas-etc/');
            if (res.ok) {
                const data = await res.json();
                if (data.results) {
                    localStorage.setItem('sigver_fallas', JSON.stringify(data.results));
                    llenarSelectFallas(data.results);
                }
            }
        } catch (err) {
            console.error('Error cargando fallas:', err);
        }
    }
}
async function cargarPuntosTermografia() {
    // Si hay internet, los descargamos
    if (navigator.onLine) {
        try {
            const res = await fetchConToken('/api/operaciones/puntos-termografia/');
            if (res.ok) {
                const data = await res.json();
                if (data.results) {
                    localStorage.setItem('sigver_puntos_ter', JSON.stringify(data.results));
                    console.log("Puntos termográficos cargados y guardados en el celular.");
                }
            }
        } catch (err) {
            console.error('Error cargando puntos de termografía:', err);
        }
    }
}

function llenarSelectFallas(fallas) {
    const contenedor = document.getElementById('lista-fallas');
    if (contenedor.children.length > 0) return; // Si ya tiene, no hacer nada
    
    contenedor.innerHTML = '';
    fallas.forEach(falla => {
        const label = document.createElement('label');
        label.className = 'falla-item';
        
        const checkbox = document.createElement('input');
        checkbox.type = 'checkbox';
        checkbox.value = falla.id;
        checkbox.className = 'checkbox-falla'; // Clase para identificarlos
        
        const texto = document.createElement('span');
        texto.textContent = `F${falla.numero} - ${falla.descripcion}`;
        
        label.appendChild(checkbox);
        label.appendChild(texto);
        contenedor.appendChild(label);
    });
}
// Enviar el formulario ETC
document.getElementById('form-verificacion').addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const btnGuardar = document.getElementById('btn-guardar-verif');
    const tieneInconveniente = document.getElementById('verif-tiene-inconveniente').value === 'si';
    const observaciones = document.getElementById('verif-observaciones').value;
    const fotoInput = document.getElementById('verif-foto');
    
    // 1. RECOLECTAR DATOS DEL RECLAMO
    const requiereReclamo = document.getElementById('verif-req-reclamo').checked;
    const prioridad = document.getElementById('verif-prioridad').value;

    let fotoArchivo = fotoInput.files[0];

    // Si hay foto, la comprimimos
    if (fotoArchivo) {
        try {
            fotoArchivo = await comprimirImagen(fotoArchivo);
        } catch (err) {
            console.error('Error comprimiendo imagen:', err);
        }
    }
    
    const checkboxesSeleccionados = document.querySelectorAll('.checkbox-falla:checked');
    const fallasSeleccionadas = Array.from(checkboxesSeleccionados).map(cb => parseInt(cb.value));
    const clientUuid = generarUUID();
    const idVerificacion = `VERIF-${Date.now()}`;
    const responsableId = usuarioLogueado.personal_id;
    
    // 2. CONSTRUIMOS EL FORMDATA
    const formData = new FormData();
    formData.append('id_verificacion', idVerificacion);
    formData.append('client_uuid', clientUuid);
    formData.append('equipo_etc', equipoSeleccionadoId);
    formData.append('fecha_verificacion', new Date().toISOString());
    formData.append('responsable', responsableId);
    formData.append('tiene_inconveniente', tieneInconveniente);
    formData.append('observaciones', observaciones);
    
    formData.append('requiere_reclamo', requiereReclamo);
    formData.append('prioridad', requiereReclamo ? prioridad : '');
    
    fallasSeleccionadas.forEach(idFalla => {
        formData.append('fallas', idFalla);
    });

    if (fotoArchivo) {
        formData.append('foto', fotoArchivo);
    }
    
    // 👇 3. VARIABLE PARA CONTROLAR EL CIERRE DEL PANEL 👇
    let guardadoExitoso = false;
     try {
        btnGuardar.disabled = true;
        btnGuardar.innerHTML = '<span class="spinner"></span> Guardando...';
        
        // 1. Cortamos la petición a los 5 segundos si no hay respuesta
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 5000); 

        const res = await fetchConToken('/api/operaciones/verificaciones-etc/', {
            method: 'POST',
            body: formData,
            signal: controller.signal 
        });
        
        clearTimeout(timeoutId);
        
        // 2. Verificamos que realmente el servidor haya guardado
        if (res.ok) {
            showToast('Verificación ETC guardada correctamente', 'success');
            guardadoExitoso = true;
        } else {
            throw new Error('Error de servidor');
        }
    } catch (err) {
        console.warn('Fallo de red o timeout, guardando offline:', err);
        try {
            const payloadOffline = {
                id_verificacion: idVerificacion,
                client_uuid: clientUuid,
                equipo_etc: equipoSeleccionadoId,
                fecha_verificacion: new Date().toISOString(),
                responsable: responsableId,
                tiene_inconveniente: tieneInconveniente,
                observaciones: observaciones,
                fallas: fallasSeleccionadas,
                foto: fotoArchivo,
                requiere_reclamo: requiereReclamo,
                prioridad: requiereReclamo ? prioridad : ''
            };
            await guardarVerificacionOffline(payloadOffline);
            
            showToast('📴 Guardado localmente. Se enviará al recuperar señal.', 'warning');
            actualizarContadorPendientes();
            guardadoExitoso = true; 

        } catch (dbErr) {
            console.error('Error DB:', dbErr);
            showToast('Error crítico al guardar localmente.', 'error');
        }
    } finally {
        btnGuardar.disabled = false;
        btnGuardar.innerHTML = 'Guardar Verificación';
        
        if (guardadoExitoso) {
            setTimeout(() => {
                document.getElementById('sheet-verificacion').classList.remove('active');
            }, 2000);
        }
    }

});
// ==========================================
// 12. Sincronización de datos Offline
// ==========================================

// Función para actualizar el numerito amarillo
async function actualizarContadorPendientes() {
    try {
        const pendientes = await obtenerPendientes();
        const badge = document.getElementById('badge-pendientes');
        if (pendientes.length > 0) {
            badge.textContent = pendientes.length;
            badge.style.display = 'inline-block';
        } else {
            badge.style.display = 'none';
        }
    } catch (err) {
        console.error('Error contando pendientes:', err);
    }
}



async function sincronizarPendientes(esManual = false) {
    if (isSyncing) return; 
    
    if (!navigator.onLine) {
        if (esManual) showToast('No hay conexión a internet.', 'error');
        return;
    }

    console.log(" [Sync] Iniciando sincronización. ¿Es manual?:", esManual);
    isSyncing = true; 
    let datosSincronizados = false; 

    try {
        // 1. Sincronizar reclamos
        const resueltosOffline = JSON.parse(localStorage.getItem('sigver_reclamos_resueltos') || '[]');
        if (resueltosOffline.length > 0) {
            console.log(" [Sync] Reclamos pendientes:", resueltosOffline.length);
            if (esManual) showToast(`Sincronizando ${resueltosOffline.length} reclamos...`, 'warning');
            
            for (const reclamoId of resueltosOffline) {
                try {
                    const res = await fetchConToken(`/api/operaciones/reclamos/${reclamoId}/`, {
                        method: 'PATCH',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ estado: 'RESUELTO', fecha_ejecucion: new Date().toISOString() })
                    });
                    if (res.ok || res.status === 404) {
                        const index = resueltosOffline.indexOf(reclamoId);
                        resueltosOffline.splice(index, 1);
                        localStorage.setItem('sigver_reclamos_resueltos', JSON.stringify(resueltosOffline));
                        datosSincronizados = true; 
                    }
                } catch (e) { console.error('Error sync reclamo:', e); }
            }
        }

        // 2. Sincronizar verificaciones
        const pendientes = await obtenerPendientes();
        console.log(" [Sync] Verificaciones pendientes:", pendientes.length);
        
        if (pendientes.length > 0) {
            if (esManual) showToast(`Sincronizando ${pendientes.length} verificaciones...`, 'warning');
            datosSincronizados = true; 
        }

        for (const payload of pendientes) {
            let endpoint = '';
            const formData = new FormData();

            if (payload.tipo === 'regulador') {
                endpoint = '/api/operaciones/verificaciones/';
                for (const key in payload) {
                    if (key !== 'tipo' && key !== 'foto_frontal' && key !== 'foto_entorno' && key !== 'foto_control_unico' && key !== 'mediciones_termografia' && key !== 'ensayos_pat' && key !== 'estado_sync' && key !== 'timestamp_local') {
                        formData.append(key, payload[key]);
                    }
                }
                if (payload.foto_frontal) formData.append('foto_frontal', payload.foto_frontal);
                if (payload.foto_entorno) formData.append('foto_entorno', payload.foto_entorno);
                if (payload.foto_control_unico) formData.append('foto_control_unico', payload.foto_control_unico);
                if (payload.mediciones_termografia) formData.append('mediciones_termografia', JSON.stringify(payload.mediciones_termografia));
                if (payload.ensayos_pat) formData.append('ensayos_pat', JSON.stringify(payload.ensayos_pat));
            } else {
                endpoint = '/api/operaciones/verificaciones-etc/';
                formData.append('id_verificacion', payload.id_verificacion);
                formData.append('client_uuid', payload.client_uuid);
                formData.append('equipo_etc', payload.equipo_etc);
                formData.append('fecha_verificacion', payload.fecha_verificacion);
                formData.append('responsable', payload.responsable);
                formData.append('tiene_inconveniente', payload.tiene_inconveniente);
                formData.append('observaciones', payload.observaciones || '');
                formData.append('requiere_reclamo', payload.requiere_reclamo || false);
                formData.append('prioridad', payload.prioridad || '');
                if (payload.fallas) payload.fallas.forEach(id => formData.append('fallas', id));
                if (payload.foto) formData.append('foto', payload.foto);
            }

            const res = await fetchConToken(endpoint, { method: 'POST', body: formData });
            if (res.ok || res.status === 400 || res.status === 409) {
                await eliminarDeOutbox(payload.client_uuid);
            }
        }
        
        console.log(" [Sync] Terminó el bucle. ¿Datos sincronizados?:", datosSincronizados);

        if (datosSincronizados) {
            console.log("[Sync] Lanzando Toast automático...");
            if (esManual) {
                showToast(' Sincronización manual completada.', 'success');
            } else {
                showToast('Datos actualizados en el servidor (Automático).', 'success');
            }
        } else if (esManual) {
            showToast('No hay datos pendientes para enviar.', 'warning');
        }

    } catch (err) {
        console.error('[Sync] Error:', err);
        if (esManual) showToast(' Red inestable.', 'error');
    } finally {
        isSyncing = false; 
        actualizarContadorPendientes(); 
    }
}

window.sincronizarPendientes = sincronizarPendientes;

// ==========================================
// 13. Detección de conexión
// ==========================================
function actualizarEstadoConexion() {
    const badge = document.getElementById('status-badge');
    if (!badge) return;

    if (navigator.onLine) {
        badge.style.backgroundColor = '#28a745'; 
        badge.textContent = 'En línea'; 
        // Si vuelve la red, esperamos 2 segundos para que la antena estabilice
        setTimeout(() => sincronizarPendientes(false), 2000); 
    } else {
        badge.textContent = '📴 Sin conexión';
        badge.style.backgroundColor = '#6c757d'; 
    }
}

window.addEventListener('online', actualizarEstadoConexion);
window.addEventListener('offline', actualizarEstadoConexion);
actualizarEstadoConexion();

// Al iniciar la app, comprobar si hay datos pendientes
setTimeout(actualizarContadorPendientes, 3000);

// ==========================================
// 14. Registro del Service Worker
// ==========================================
if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => {
        navigator.serviceWorker.register('/sw.js', { updateViaCache: 'none' })
            .then((reg) => {
                reg.update();
            })
            .catch((err) => console.warn('[PWA] SW no registrado:', err));
    });
}
// ==========================================
// 15. Lógica del Formulario de Reguladores
// ==========================================
let componenteSeleccionadoId = null;

window.abrirFormularioRegulador = function(componenteId, codSitio) {
    componenteSeleccionadoId = componenteId;
    
    document.getElementById('reg-codigo').textContent = codSitio;
    document.getElementById('form-regulador').reset();
    document.getElementById('reg-status').textContent = '';

    // Limpiar termografías y PAT
    ensayosPatAgregados = [];
    actualizarListaEnsayosPat();
    
    // Limpiar reclamos
    document.getElementById('reg-req-reclamo').checked = false;
    document.getElementById('grupo-prioridad-reg').style.display = 'none';

    // Abrir panel
    document.getElementById('sheet-regulador').classList.add('active');
    document.querySelectorAll('.leaflet-popup-close-button').forEach(btn => btn.click());
};
document.getElementById('btn-cerrar-sheet-reg').addEventListener('click', () => {
    document.getElementById('sheet-regulador').classList.remove('active');
});

document.getElementById('form-regulador').addEventListener('submit', async (e) => {
    e.preventDefault();
    const btnGuardar = document.getElementById('btn-guardar-reg');
    
    // Recolectar datos
    const clientUuid = generarUUID();
    const idVerificacion = `VERIF-REG-${Date.now()}`;
    const responsableId = usuarioLogueado.personal_id;

    const requiereReclamo = document.getElementById('reg-req-reclamo').checked;
    const prioridad = document.getElementById('reg-prioridad').value;

    // Obtener fotos comprimidas
    const fotoFrontalFile = document.getElementById('reg-foto-frontal').files[0];
    const fotoEntornoFile = document.getElementById('reg-foto-entorno').files[0];
    const fotoControlFile = document.getElementById('reg-foto-control').files[0];

    let fotoFrontal, fotoEntorno, fotoControl;
    if (fotoFrontalFile) fotoFrontal = await comprimirImagen(fotoFrontalFile);
    if (fotoEntornoFile) fotoEntorno = await comprimirImagen(fotoEntornoFile);
    if (fotoControlFile) fotoControl = await comprimirImagen(fotoControlFile);

    const payloadBase = {
        id_verificacion: idVerificacion,
        client_uuid: clientUuid,
        componente: componenteSeleccionadoId,
        fecha_verificacion: new Date().toISOString(),
        responsable: responsableId,
        tipo_control_verificado: document.getElementById('reg-tipo-control').value,
        tipo_banco_verificado: document.getElementById('reg-tipo-banco').value,
        valla_perimetral: document.getElementById('reg-valla').value === 'true',
        es_hibrido: document.getElementById('reg-hibrido').value === 'true',
        configuracion_observada: document.getElementById('reg-config-obs').value,
        estado_sitio: document.getElementById('reg-estado-sitio').value,
        observaciones: document.getElementById('reg-observaciones').value,
        
        // 👇 2. AGREGADO EL CAMPO DE COINCIDENCIA 👇
        ubicacion_coincide: document.getElementById('reg-ubicacion-coincide').value,
        
        requiere_reclamo: requiereReclamo,
        prioridad: requiereReclamo ? prioridad : ''
    };

    const formData = new FormData();
    for (const key in payloadBase) {
        formData.append(key, payloadBase[key]);
    }
    
    if (fotoFrontal) formData.append('foto_frontal', fotoFrontal);
    if (fotoEntorno) formData.append('foto_entorno', fotoEntorno);
    if (fotoControl) formData.append('foto_control_unico', fotoControl);

    if (termografiasAgregadas.length > 0) {
        formData.append('mediciones_termografia', JSON.stringify(termografiasAgregadas));
    }
    if (ensayosPatAgregados.length > 0) {
        formData.append('ensayos_pat', JSON.stringify(ensayosPatAgregados));
    }

    let guardadoExitoso = false;

    try {
        btnGuardar.disabled = true;
        btnGuardar.innerHTML = '<span class="spinner"></span> Guardando...';
        
        if (!navigator.onLine) {
            throw new Error('NetworkError'); 
        }

        const res = await fetchConToken('/api/operaciones/verificaciones/', {
            method: 'POST',
            body: formData
        });
        
        if (res.ok) {
            showToast('Regulador guardado correctamente', 'success');
            termografiasAgregadas = []; 
            ensayosPatAgregados = []; 
            guardadoExitoso = true;
        } else {
            throw new Error('Error de servidor');
        }
    } catch (err) {
        console.warn('Error al guardar regulador:', err);
        
        if (err.message.includes('NetworkError') || err.message.includes('Failed to fetch')) {
            try {
                const payloadOffline = { ...payloadBase, tipo: 'regulador' };
                if (fotoFrontal) payloadOffline.foto_frontal = fotoFrontal;
                if (fotoEntorno) payloadOffline.foto_entorno = fotoEntorno;
                if (fotoControl) payloadOffline.foto_control_unico = fotoControl;
                
                if (termografiasAgregadas.length > 0) {
                    payloadOffline.mediciones_termografia = termografiasAgregadas;
                }
                if (ensayosPatAgregados.length > 0) {
                    payloadOffline.ensayos_pat = ensayosPatAgregados;
                }

                await guardarVerificacionOffline(payloadOffline);
                showToast('Guardado localmente. Se enviará al recuperar señal.', 'warning');
                actualizarContadorPendientes();
                
                termografiasAgregadas = [];
                ensayosPatAgregados = [];
                guardadoExitoso = true; 

            } catch (dbErr) {
                showToast('Error al guardar localmente.', 'error');
            }
        } else {
            showToast('Error del servidor: ' + err.message, 'error');
        }
    } finally {
        btnGuardar.disabled = false;
        btnGuardar.innerHTML = 'Guardar Verificación';
        
        if (guardadoExitoso) {
            setTimeout(() => {
                document.getElementById('sheet-regulador').classList.remove('active');
            }, 2000);
        }
    }
});

// ==========================================
// 16. Mediciones Termográficas (Editar / Eliminar)
// ==========================================
let termografiasAgregadas = [];
let indiceEdicionTermografia = -1; // -1 significa que estamos agregando una nueva

// Abrir modal (Nueva Medición)
document.getElementById('btn-add-termografia').addEventListener('click', () => {
    indiceEdicionTermografia = -1; // Reiniciar a "modo creación"
    
    // Limpiar campos del modal
    document.getElementById('term-temp-punto').value = '';
    document.getElementById('term-temp-amb').value = '';
    document.getElementById('term-corriente').value = '';
    document.getElementById('term-punto').value = '';

    llenarSelectPuntos();
    document.getElementById('modal-termografia').style.display = 'flex';
});

// Cerrar modal
document.getElementById('btn-cancelar-term').addEventListener('click', () => {
    document.getElementById('modal-termografia').style.display = 'none';
});

// Guardar medición (Nueva o Editada)
document.getElementById('btn-guardar-term').addEventListener('click', () => {
    const punto = document.getElementById('term-punto').value;
    const tempPunto = document.getElementById('term-temp-punto').value;
    const tempAmb = document.getElementById('term-temp-amb').value;
    const corriente = document.getElementById('term-corriente').value;

    if (!punto || !tempPunto) {
        alert("Por favor, selecciona un punto y la temperatura.");
        return;
    }

    const delta = tempPunto && tempAmb ? (parseFloat(tempPunto) - parseFloat(tempAmb)).toFixed(1) : null;

    const termografiaData = {
        id_medicion: indiceEdicionTermografia === -1 ? `TERM-${Date.now()}` : termografiasAgregadas[indiceEdicionTermografia].id_medicion,
        punto: punto,
        fecha_hora: new Date().toISOString(),
        corriente_a: corriente ? parseFloat(corriente) : null,
        temperatura_ambiente_c: tempAmb ? parseFloat(tempAmb) : null,
        temperatura_punto_c: parseFloat(tempPunto),
        delta_temperatura_c: delta ? parseFloat(delta) : null,
        nivel_termografico: "Nivel 1",
        observaciones: ""
    };

    if (indiceEdicionTermografia === -1) {
        // Es nueva, la agregamos a la lista
        termografiasAgregadas.push(termografiaData);
    } else {
        // Es una edición, reemplazamos los datos en el índice
        termografiasAgregadas[indiceEdicionTermografia] = termografiaData;
    }
    
    actualizarListaTermografias();
    document.getElementById('modal-termografia').style.display = 'none';
});

// Función para pintar la lista con botones de Editar y Eliminar
function actualizarListaTermografias() {
    const listaDiv = document.getElementById('lista-termografias');
    if (termografiasAgregadas.length === 0) {
        listaDiv.innerHTML = '';
        return;
    }
    
    let html = '<b>Termografías agregadas:</b><ul style="margin-top: 5px; padding-left: 0; list-style: none;">';
    
    termografiasAgregadas.forEach((t, index) => {
        html += `
            <li style="display: flex; justify-content: space-between; align-items: center; background: #f1f5f9; padding: 8px; border-radius: 6px; margin-bottom: 5px; border: 1px solid #e2e8f0;">
                <span style="font-size: 12px;">${t.punto}: <b>${t.temperatura_punto_c}°C</b> (Δ ${t.delta_temperatura_c}°C)</span>
                <div>
                    <button type="button" onclick="editarTermografia(${index})" style="background: none; border: none; cursor: pointer; font-size: 16px; margin-right: 5px;">✏️</button>
                    <button type="button" onclick="eliminarTermografia(${index})" style="background: none; border: none; cursor: pointer; font-size: 16px;">🗑️</button>
                </div>
            </li>
        `;
    });
    html += '</ul>';
    listaDiv.innerHTML = html;
}

// Función global para Editar
window.editarTermografia = function(index) {
    indiceEdicionTermografia = index;
    const term = termografiasAgregadas[index];
    
    // Llenar el modal con los datos actuales
    llenarSelectPuntos(); // Asegurarnos de que el select tenga las opciones
    document.getElementById('term-punto').value = term.punto;
    document.getElementById('term-temp-punto').value = term.temperatura_punto_c;
    document.getElementById('term-temp-amb').value = term.temperatura_ambiente_c || '';
    document.getElementById('term-corriente').value = term.corriente_a || '';
    
    document.getElementById('modal-termografia').style.display = 'flex';
};

// Función global para Eliminar
window.eliminarTermografia = function(index) {
    if (confirm('¿Estás seguro de eliminar esta termografía?')) {
        termografiasAgregadas.splice(index, 1);
        actualizarListaTermografias();
    }
};

// Función auxiliar para llenar el Select
function llenarSelectPuntos() {
    const select = document.getElementById('term-punto');
    if (select.options.length === 0) {
        const puntos = localStorage.getItem('sigver_puntos_ter');
        if (puntos) {
            const data = JSON.parse(puntos);
            select.innerHTML = '<option value="">Seleccione un punto...</option>';
            data.forEach(p => {
                select.innerHTML += `<option value="${p.id_punto}">${p.id_punto} - Fase ${p.fase} (${p.tipo_elemento})</option>`;
            });
        } else {
            select.innerHTML = '<option value="">Error al cargar puntos</option>';
        }
    }
}

// Limpiar al abrir un nuevo regulador
const originalAbrirRegulador = window.abrirFormularioRegulador;
window.abrirFormularioRegulador = function(componenteId, codSitio) {
    termografiasAgregadas = []; // Reiniciar lista
    actualizarListaTermografias();
    originalAbrirRegulador(componenteId, codSitio);
};
// ==========================================
// 17. Ensayos PAT (Puesta a Tierra)
// ==========================================
let ensayosPatAgregados = [];
let lecturasTemporales = []; // Para ir guardando las lecturas dentro del modal
let indiceEdicionPat = -1;

// Abrir modal PAT
document.getElementById('btn-add-pat').addEventListener('click', () => {
    indiceEdicionPat = -1;
    lecturasTemporales = [];
    
    // Limpiar campos
    document.getElementById('pat-metodo').value = '';
    document.getElementById('pat-equipo').value = '';
    document.getElementById('pat-lect-dist').value = '';
    document.getElementById('pat-lect-val').value = '';
    document.getElementById('lista-lecturas-modal').innerHTML = '';

    document.getElementById('modal-pat').style.display = 'flex';
});

document.getElementById('btn-cancelar-pat').addEventListener('click', () => {
    document.getElementById('modal-pat').style.display = 'none';
});

// Agregar una lectura temporal al modal
document.getElementById('btn-add-lectura').addEventListener('click', () => {
    const dist = document.getElementById('pat-lect-dist').value;
    const val = document.getElementById('pat-lect-val').value;

    if (!dist || !val) {
        alert("Por favor, completa distancia y valor de la lectura.");
        return;
    }

    lecturasTemporales.push({
        id_lectura: `LECT-${Date.now()}-${lecturasTemporales.length}`,
        tipo_lectura: 'MEDICION',
        distancia_m: parseInt(dist),
        valor_ohm: parseFloat(val),
        observaciones: ''
    });

    // Limpiar inputs y actualizar lista visual
    document.getElementById('pat-lect-dist').value = '';
    document.getElementById('pat-lect-val').value = '';
    actualizarListaTemporalLecturas();
});

function actualizarListaTemporalLecturas() {
    const div = document.getElementById('lista-lecturas-modal');
    if (lecturasTemporales.length === 0) {
        div.innerHTML = '<span style="color: #999;">No hay lecturas agregadas.</span>';
        return;
    }
    
    let html = '<ul style="margin: 0; padding-left: 15px;">';
    lecturasTemporales.forEach((l, idx) => {
        html += `<li>${l.distancia_m}m: <b>${l.valor_ohm} Ω</b> <span style="color: red; cursor: pointer;" onclick="eliminarLecturaTemporal(${idx})">🗑️</span></li>`;
    });
    html += '</ul>';
    div.innerHTML = html;
}

window.eliminarLecturaTemporal = function(index) {
    lecturasTemporales.splice(index, 1);
    actualizarListaTemporalLecturas();
};

// Guardar Ensayo (del modal a la lista principal)
document.getElementById('btn-guardar-pat').addEventListener('click', () => {
    if (lecturasTemporales.length === 0) {
        alert("Debes agregar al menos una lectura para guardar el ensayo PAT.");
        return;
    }

    const ensayoData = {
        id_ensayo: indiceEdicionPat === -1 ? `PAT-${Date.now()}` : ensayosPatAgregados[indiceEdicionPat].id_ensayo,
        fecha_ensayo: new Date().toISOString(),
        metodo_pat: document.getElementById('pat-metodo').value,
        equipo_medicion: document.getElementById('pat-equipo').value,
        condicion_suelo: document.getElementById('pat-suelo').value,
        resultado: document.getElementById('pat-resultado').value,
        lecturas: [...lecturasTemporales] // Copiamos el arreglo
    };

    if (indiceEdicionPat === -1) {
        ensayosPatAgregados.push(ensayoData);
    } else {
        ensayosPatAgregados[indiceEdicionPat] = ensayoData;
    }

    actualizarListaEnsayosPat();
    document.getElementById('modal-pat').style.display = 'none';
});

function actualizarListaEnsayosPat() {
    const listaDiv = document.getElementById('lista-ensayos-pat');
    if (ensayosPatAgregados.length === 0) {
        listaDiv.innerHTML = '';
        return;
    }
    
    let html = '<b>Ensayos PAT agregados:</b><ul style="margin-top: 5px; padding-left: 0; list-style: none;">';
    ensayosPatAgregados.forEach((e, index) => {
        html += `
            <li style="display: flex; justify-content: space-between; align-items: center; background: #f1f5f9; padding: 8px; border-radius: 6px; margin-bottom: 5px; border: 1px solid #e2e8f0;">
                <span style="font-size: 12px;">Ensayo: <b>${e.lecturas.length} lecturas</b> (${e.resultado})</span>
                <div>
                    <button type="button" onclick="editarEnsayosPat(${index})" style="background: none; border: none; cursor: pointer; font-size: 16px; margin-right: 5px;">✏️</button>
                    <button type="button" onclick="eliminarEnsayosPat(${index})" style="background: none; border: none; cursor: pointer; font-size: 16px;">🗑️</button>
                </div>
            </li>
        `;
    });
    html += '</ul>';
    listaDiv.innerHTML = html;
}

window.editarEnsayosPat = function(index) {
    indiceEdicionPat = index;
    const ensayo = ensayosPatAgregados[index];
    
    document.getElementById('pat-metodo').value = ensayo.metodo_pat;
    document.getElementById('pat-equipo').value = ensayo.equipo_medicion;
    document.getElementById('pat-suelo').value = ensayo.condicion_suelo;
    document.getElementById('pat-resultado').value = ensayo.resultado;
    
    lecturasTemporales = [...ensayo.lecturas];
    actualizarListaTemporalLecturas();
    
    document.getElementById('modal-pat').style.display = 'flex';
};

window.eliminarEnsayosPat = function(index) {
    if (confirm('¿Estás seguro de eliminar este ensayo PAT?')) {
        ensayosPatAgregados.splice(index, 1);
        actualizarListaEnsayosPat();
    }
};

// Limpiar al abrir un nuevo regulador
const originalAbrirReguladorPat = window.abrirFormularioRegulador;
window.abrirFormularioRegulador = function(componenteId, codSitio) {
    // Limpiamos termografías y PAT
    ensayosPatAgregados = [];
    actualizarListaEnsayosPat();
    // 👇 ACÁ VA LA LIMPIEZA DEL RECLAMO 👇
    document.getElementById('reg-req-reclamo').checked = false;
    document.getElementById('grupo-prioridad-reg').style.display = 'none';
    // Llamamos a la función original que abre el panel
    originalAbrirReguladorPat(componenteId, codSitio);
};

// Escuchar cuando el usuario escribe o cambia el desplegable
document.getElementById('search-input').addEventListener('input', ejecutarBusqueda);
document.getElementById('search-filter').addEventListener('change', ejecutarBusqueda);

function ejecutarBusqueda() {
    const query = document.getElementById('search-input').value.toLowerCase().trim();
    const filtro = document.getElementById('search-filter').value;
    const divResultados = document.getElementById('search-results');

    // 👇 Exigimos 2 letras para no dibujar 313 equipos de golpe
    if (query.length < 2) {
        divResultados.innerHTML = '<p style="text-align: center; color: #999; margin-top: 20px;">Escribe al menos 2 letras para buscar...</p>';
        return;
    }

    let resultados = [];

    // Buscar en ETCs
    if (filtro === 'todos' || filtro === 'etc') {
        todosLosEquipos.forEach(f => {
            const p = f.properties;
            if (p.nro_equipo.toLowerCase().includes(query) || 
                p.alimentador_codigo.toLowerCase().includes(query) || 
                p.subestacion_codigo.toLowerCase().includes(query)) {
                
                resultados.push({
                    tipo: 'ETC',
                    id: f.id,
                    titulo: `⚡ ETC ${p.nro_equipo}`,
                    subtitulo: `Subestación ${p.subestacion_codigo} | Alimentador ${p.alimentador_codigo}`,
                    coords: f.geometry.coordinates
                });
            }
        });
    }

    // Buscar en Sitios (Reguladores)
    if (filtro === 'todos' || filtro === 'regulador') {
        todosLosSitios.forEach(f => {
            const p = f.properties;
            if (p.id_sitio.toLowerCase().includes(query) || 
                p.cod_sitio.toLowerCase().includes(query) ||
                p.alimentador_codigo.toLowerCase().includes(query) || 
                p.subestacion_codigo.toLowerCase().includes(query)) {
                
                resultados.push({
                    tipo: 'Regulador',
                    id: f.id,
                    titulo: `🔌 Regulador ${p.id_sitio}`,
                    subtitulo: `${p.cod_sitio} | Subestación ${p.subestacion_codigo}`,
                    coords: f.geometry.coordinates
                });
            }
        });
    }

    // Mostrar resultados
    if (resultados.length === 0) {
        divResultados.innerHTML = '<p style="text-align: center; color: #999; margin-top: 20px;">No se encontraron equipos.</p>';
        return;
    }

    // 👇 Límite de 50 resultados para que el celular no explote
    const resultadosMostrados = resultados.slice(0, 50);

    let html = '';
    resultadosMostrados.forEach(r => {
        html += `
            <div onclick="volarAEquipo(${r.coords[1]}, ${r.coords[0]}, '${r.tipo}')" 
                 style="padding: 12px; border-bottom: 1px solid #eee; cursor: pointer; transition: background 0.2s;"
                 onmouseover="this.style.background='#f0f0f0'" 
                 onmouseout="this.style.background='white'">
                <div style="font-weight: bold; color: #002f6c; font-size: 14px;">${r.titulo}</div>
                <div style="font-size: 12px; color: #666;">${r.subtitulo}</div>
            </div>
        `;
    });

    if (resultados.length > 50) {
        html += `<p style="text-align: center; color: #999; font-size: 12px; margin-top: 10px;">Mostrando los primeros 50 resultados de ${resultados.length}. Escribe más para filtrar.</p>`;
    }
    
    divResultados.innerHTML = html;
}

// Función global para volar al equipo
window.volarAEquipo = function(lat, lng, tipo) {
    document.getElementById('search-sheet').classList.remove('active');
    mapGlobal.flyTo([lat, lng], 18, { duration: 1.5 });
};
//Selector de prioridad y otros campos según el checkbox
document.getElementById('verif-req-reclamo').addEventListener('change', (e) => {
    document.getElementById('grupo-prioridad-etc').style.display = e.target.checked ? 'block' : 'none';
});

document.getElementById('reg-req-reclamo').addEventListener('change', (e) => {
    document.getElementById('grupo-prioridad-reg').style.display = e.target.checked ? 'block' : 'none';
});

// ==========================================
// 23. Gestión de Reclamos (Offline-First)
// ==========================================

async function cargarMisReclamos() {
    const contenedor = document.getElementById('lista-reclamos');
    contenedor.innerHTML = '<p style="text-align: center; color: #999;">Buscando reclamos...</p>';

    // 1. Si no hay internet, leemos del localStorage
    if (!navigator.onLine) {
        const guardados = localStorage.getItem('sigver_reclamos_cache');
        if (guardados) {
            renderizarListaReclamos(JSON.parse(guardados));
        } else {
            contenedor.innerHTML = '<p style="text-align: center; color: #ef4444; padding: 20px;">📴 Sin conexión. No hay reclamos guardados en el celular.</p>';
        }
        return;
    }
    
    // 2. Si hay internet, pedimos al servidor
    try {
        const personalId = usuarioLogueado.personal_id;
        const res = await fetchConToken(`/api/operaciones/reclamos/?responsable_asignado=${personalId}`);
        
        if (!res.ok) throw new Error("Error HTTP: " + res.status);
        
        const data = await res.json();
        const reclamos = data.results || data;

        // Guardamos en caché local para modo offline
        localStorage.setItem('sigver_reclamos_cache', JSON.stringify(reclamos));
        renderizarListaReclamos(reclamos);

    } catch (err) {
        console.error("Error en reclamos:", err);
        contenedor.innerHTML = `<p style="text-align: center; color: red; padding: 20px;">Error de red: Intentá de nuevo.</p>`;
    }
}

// Función para dibujar la lista en pantalla
function renderizarListaReclamos(reclamos) {
    const contenedor = document.getElementById('lista-reclamos');
    
    // Leemos los reclamos que se resolvieron offline y están esperando sincronizar
    const resueltosOffline = JSON.parse(localStorage.getItem('sigver_reclamos_resueltos') || '[]');

    if (reclamos.length === 0) {
        contenedor.innerHTML = '<p style="text-align: center; color: #28a745; margin-top: 20px;">✅ No tenés reclamos pendientes.</p>';
        return;
    }

    let html = '';
    reclamos.forEach(r => {
        // Si no está cerrado y no está en la lista de resueltos offline, lo mostramos
        if (r.estado !== 'CERRADO' && r.estado !== 'RESUELTO' && !resueltosOffline.includes(r.id)) {
            html += `
                <div style="background: #fff3cd; border: 1px solid #ffeeba; border-radius: 8px; padding: 12px; margin-bottom: 10px;">
                    <div style="font-weight: bold; color: #856404; font-size: 14px;">${r.id_reclamo} (${r.prioridad})</div>
                    <div style="font-size: 12px; color: #555; margin: 5px 0;">${r.descripcion}</div>
                    <button onclick="resolverReclamo('${r.id}')" style="width: 100%; margin-top: 8px; padding: 8px; background: #28a745; color: white; border: none; border-radius: 4px; font-weight: bold; cursor: pointer;">
                        ✅ Marcar como Resuelto
                    </button>
                </div>
            `;
        }
    });
    
    contenedor.innerHTML = html || '<p style="text-align: center; color: #28a745; margin-top: 20px;">✅ No tenés reclamos pendientes.</p>';
}

// Función para resolver un reclamo
window.resolverReclamo = async function(reclamoId) {
    if (!confirm('¿Seguro que querés marcar este reclamo como resuelto?')) return;
    
    try {
        // Intentamos resolverlo en el servidor (con timeout de 5 segundos)
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 5000);

        const res = await fetchConToken(`/api/operaciones/reclamos/${reclamoId}/`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                estado: 'RESUELTO',
                fecha_ejecucion: new Date().toISOString()
            }),
            signal: controller.signal
        });
        
        clearTimeout(timeoutId);

        if (res.ok) {
            showToast('✅ Reclamo resuelto con éxito.', 'success');
            cargarMisReclamos(); 
        } else {
            throw new Error('Error del servidor');
        }
    } catch (err) {
        console.warn('Guardando resolución offline:', err);
        
        // Si falla la red, lo guardamos en la cola local
        let resueltosOffline = JSON.parse(localStorage.getItem('sigver_reclamos_resueltos') || '[]');
        if (!resueltosOffline.includes(reclamoId)) {
            resueltosOffline.push(reclamoId);
            localStorage.setItem('sigver_reclamos_resueltos', JSON.stringify(resueltosOffline));
        }
        
        showToast('📴 Sin conexión. Se resolverá al recuperar señal.', 'warning');
        cargarMisReclamos(); // Recargamos para que desaparezca de la vista
    }
};
// ==========================================
// 21. Control del Menú Lateral
// ==========================================
window.abrirMenu = function() {
    document.getElementById('sidebar-menu').classList.add('active');
    document.getElementById('sidebar-overlay').classList.add('active');
    
    // Mostrar el nombre del usuario logueado en el menú
    if (usuarioLogueado) {
        document.getElementById('menu-user-name').textContent = usuarioLogueado.nombre;
    }
};

window.cerrarMenu = function() {
    document.getElementById('sidebar-menu').classList.remove('active');
    document.getElementById('sidebar-overlay').classList.remove('active');
};

// Funciones para abrir las ventanas desde el menú
window.abrirBusqueda = function() {
    cerrarMenu();
    // Pequeño delay para que se cierre el menú antes de abrir el buscador
    setTimeout(() => {
        document.getElementById('search-sheet').classList.add('active');
        document.getElementById('search-input').focus();
    }, 300);
};

window.abrirReclamos = function() {
    cerrarMenu();
    setTimeout(() => {
        document.getElementById('sheet-reclamos').classList.add('active');
        cargarMisReclamos();
    }, 300);
};

// ==========================================
// 22. Cierre Global de Paneles (A prueba de fallos)
// ==========================================
document.addEventListener('click', (e) => {
    // Si el clic fue en un botón que tenga la clase 'btn-close'
    if (e.target.classList.contains('btn-close') || e.target.closest('.btn-close')) {
        const btn = e.target.closest('.btn-close');
        const sheet = btn.closest('.bottom-sheet');
        if (sheet) {
            sheet.classList.remove('active'); // Cierra el panel que lo contiene
        }
    }
});

// Lo mismo para cerrar el menú lateral si tocan el fondo oscuro
const overlay = document.getElementById('sidebar-overlay');
if (overlay) {
    overlay.addEventListener('click', () => {
        document.getElementById('sidebar-menu').classList.remove('active');
        overlay.classList.remove('active');
    });
}
// ==========================================
// 24. Auto-Sincronización Inteligente
// ==========================================

// 1. Escuchar cuando el usuario vuelve a la app (ej: desbloquea el celular o cambia de pestaña)
document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible' && navigator.onLine) {
        console.log('[Auto-Sync] La app volvió a primer plano, verificando pendientes...');
        sincronizarPendientes(false); // false significa que es silencioso
    }
});

// 2. El "Vigilante" silencioso (cada 20 segundos)
setInterval(async () => {
    // Solo intentar si hay internet y no está sincronizando ya
    if (navigator.onLine && !isSyncing) {
        // Verificamos si hay algo pendiente en IndexedDB o LocalStorage
        const pendientesOutbox = await obtenerPendientes();
        const reclamosPendientes = JSON.parse(localStorage.getItem('sigver_reclamos_resueltos') || '[]');

        if (pendientesOutbox.length > 0 || reclamosPendientes.length > 0) {
            console.log('[Auto-Sync] Encontré datos pendientes. Sincronizando en segundo plano...');
            sincronizarPendientes(false);
        }
    }
}, 20000); 
// ==========================================
// MOSTRAR / OCULTAR CONTRASEÑA
// ==========================================
document.getElementById('toggle-password').addEventListener('click', function (e) {
    const passwordInput = document.getElementById('login-password');
    
    // Cambiamos el tipo de input
    if (passwordInput.type === 'password') {
        passwordInput.type = 'text';
        this.classList.remove('fa-eye');
        this.classList.add('fa-eye-slash');
    } else {
        passwordInput.type = 'password';
        this.classList.remove('fa-eye-slash');
        this.classList.add('fa-eye');
    }
});
// ==========================================
// 27. Cálculo de Distancia (Haversine)
// ==========================================
function calcularDistanciaMetros(lat1, lon1, lat2, lon2) {
    const R = 6371e3; // Radio de la Tierra en metros
    const p1 = lat1 * Math.PI / 180;
    const p2 = lat2 * Math.PI / 180;
    const dp = (lat2 - lat1) * Math.PI / 180;
    const dl = (lon2 - lon1) * Math.PI / 180;

    const a = Math.sin(dp / 2) * Math.sin(dp / 2) +
              Math.cos(p1) * Math.cos(p2) *
              Math.sin(dl / 2) * Math.sin(dl / 2);
    const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));

    return R * c; // Retorna la distancia en metros
}

