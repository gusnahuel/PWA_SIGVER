/**
 * SIGVER - Base de datos local (IndexedDB)
 * Se usa como "Outbox" para guardar verificaciones cuando no hay red.
 */

const DB_NAME = 'sigver-db';
const DB_VERSION = 1;
const STORE_NAME = 'outbox_verificaciones';

// Abrir/crear la base de datos
function abrirDB() {
    return new Promise((resolve, reject) => {
        const request = indexedDB.open(DB_NAME, DB_VERSION);

        request.onerror = (e) => reject(e.target.error);

        request.onupgradeneeded = (e) => {
            const db = e.target.result;
            if (!db.objectStoreNames.contains(STORE_NAME)) {
                // Creamos el almacén usando el client_uuid como clave primaria
                db.createObjectStore(STORE_NAME, { keyPath: 'client_uuid' });
            }
        };

        request.onsuccess = (e) => resolve(e.target.result);
    });
}

// Guardar una verificación en la cola
export async function guardarVerificacionOffline(payload) {
    const db = await abrirDB();
    return new Promise((resolve, reject) => {
        const tx = db.transaction(STORE_NAME, 'readwrite');
        const store = tx.objectStore(STORE_NAME);
        
        // Agregar metadata extra
        // (se respeta 'error' cuando el servidor rechazó el envío)
        payload.estado_sync = payload.estado_sync || 'pendiente';
        payload.timestamp_local = payload.timestamp_local || Date.now();

        const request = store.put(payload); // put guarda o actualiza

        request.onsuccess = () => resolve(true);
        request.onerror = (e) => reject(e.target.error);
    });
}

// Obtener todas las verificaciones pendientes
export async function obtenerPendientes() {
    const db = await abrirDB();
    return new Promise((resolve, reject) => {
        const tx = db.transaction(STORE_NAME, 'readonly');
        const store = tx.objectStore(STORE_NAME);
        const request = store.getAll();

        request.onsuccess = (e) => resolve(e.target.result);
        request.onerror = (e) => reject(e.target.error);
    });
}

// Eliminar una verificación de la cola (cuando ya se sincronizó)
export async function eliminarDeOutbox(client_uuid) {
    const db = await abrirDB();
    return new Promise((resolve, reject) => {
        const tx = db.transaction(STORE_NAME, 'readwrite');
        const store = tx.objectStore(STORE_NAME);
        const request = store.delete(client_uuid);

        request.onsuccess = () => resolve(true);
        request.onerror = (e) => reject(e.target.error);
    });
}