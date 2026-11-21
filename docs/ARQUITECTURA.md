# 🏗️ Arquitectura del Sistema SIGVER

Documento de decisiones arquitectónicas para la tesis.

---

## 1. Contexto

ANDE requiere digitalizar la verificación en campo de:
- **344 Equipos Telecomandados (ETC)**
- **55 Reguladores de Tensión**

Distribuidos en los departamentos de Itapúa, Misiones y Ñeembucú.

Los técnicos operan en zonas con conectividad limitada, por lo que la aplicación debe funcionar offline y sincronizar cuando haya red disponible.

---

## 2. Decisiones arquitectónicas (ADRs)

### ADR-001: Uso de PWA en lugar de aplicación nativa
**Decisión:** Progressive Web App.

**Razones:** multiplataforma, actualización automática, soporte offline con Service Workers, menor costo.

### ADR-002: Django + DRF como backend
**Decisión:** Django 5 + Django REST Framework.

**Razones:** ORM maduro, admin autogenerado, GeoDjango nativo, estándar en la industria.

### ADR-003: PostgreSQL + PostGIS
**Decisión:** PostgreSQL 15 con PostGIS 3.3.

**Razones:** índices GIST, tipo `geography`, estándar OGC, integración con GeoDjango.

### ADR-004: JavaScript vanilla (sin framework SPA)
**Decisión:** JS ES6 modules, sin React/Vue/Svelte.

**Razones:** menor complejidad, mejor rendimiento en gama baja, adecuado al alcance (KISS de Pressman).

### ADR-005: Offline-first con IndexedDB
**Decisión:** IndexedDB como cola de salida (outbox) + Service Worker para cacheo.

**Razones:** soporta Blobs (fotos), permite Background Sync, estrategias de cacheo diferenciadas.

### ADR-006: JWT para autenticación
**Decisión:** JWT con `djangorestframework-simplejwt`.

**Razones:** stateless, ideal para PWA, roles en el token, renovación con refresh token.

### ADR-007: 4 roles con permisos por agencia
**Roles:** técnico_campo, supervisor_zona, admin_eam, consulta.

### ADR-008: Docker para despliegue reproducible
**Decisión:** Docker Compose con 3 servicios: `db`, `web`, `nginx`.

### ADR-009: Verificaciones diferenciadas
**Decisión:** modelos separados (`Verificacion` para reguladores, `VerificacionETC` para ETC).

### ADR-010: Mediciones como tablas relacionales (no JSON)
**Modelos:** PuntoInspeccionTermografia, MedicionTermografia, EnsayoPAT, LecturaPAT.

---

## 3. Modelo de datos (resumen)
SeccionRegional
└── Agencia
├── Personal (1:1 opcional con Usuario)
└── Alimentador
└── Sitio
├── Componente (reguladores)
│ ├── ElementoEquipo (1:N)
│ ├── Verificacion
│ │ ├── MedicionTermografia (1:N)
│ │ ├── EnsayoPAT (1:N)
│ │ │ └── LecturaPAT (1:N)
│ │ └── Reclamo (1:N)
└── EquipoETC
└── VerificacionETC

Usuario (auth)
├── rol
└── agencias_asignadas (M:N con Agencia)

text

---

## 4. Estado del documento

- **Última actualización:** 13/10/2026
- **Estado:** Diseño cerrado, listo para implementación.
