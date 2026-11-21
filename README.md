# SIGVER

**Sistema Integrado de Gestión y Verificación de Equipos de Distribución**

Trabajo Final de Grado — ANDE (Administración Nacional de Electricidad)

---

## 📋 Descripción

PWA offline-first para la verificación en campo de equipos telecomandados (ETC) y reguladores de tensión, con gestión de reclamos, control de acceso basado en roles y sincronización diferida.

## 🧱 Stack

- **Backend:** Django 5 + Django REST Framework + JWT
- **Base de datos:** PostgreSQL 15 + PostGIS 3.3
- **Frontend:** JavaScript ES6 modules + Leaflet + Tailwind CSS v4
- **Offline:** IndexedDB + Service Worker (Workbox)
- **Contenedores:** Docker + Docker Compose + Nginx

## 📁 Estructura
sigver/
├── backend/ # API Django
├── frontend/ # PWA
├── nginx/ # Configuración del proxy inverso
└── docs/ # Documentación y decisiones arquitectónicas

text

## 🚀 Arranque (desarrollo)

```bash
# 1. Copiar variables de entorno
cp .env.example .env

# 2. Levantar contenedores
docker compose up -d --build

# 3. Aplicar migraciones
docker compose exec web python manage.py migrate

# 4. Crear superusuario
docker compose exec web python manage.py createsuperuser

# 5. Acceder
# API:      http://localhost:8000/api/
# Admin:    http://localhost:8000/admin/
# PWA:      http://localhost/

Documentación
docs/ARQUITECTURA.md — decisiones arquitectónicas

docs/PROGRESO.md — checklist de avance

🔐 Roles del sistema

tecnico_campo	Verifica equipos, registra problemas
supervisor_zona	Supervisa su zona, cierra reclamos
admin_eam	Administrador total
consulta	Solo lectura