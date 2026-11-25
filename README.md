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

# 2. Generar el certificado HTTPS (una sola vez; nginx no arranca sin él)
scripts/certificado-local.sh

# 3. Levantar contenedores (las migraciones se aplican solas al arrancar)
docker compose up -d --build

# 4. Crear superusuario
docker compose exec web python manage.py createsuperuser

# 5. Acceder desde esta PC (HTTP, sin advertencias de certificado)
# PWA:      http://localhost/
# Admin:    http://localhost/admin/
# API:      http://localhost/api/
# Desde celulares u otras PCs de la red: https://<IP-de-la-PC>/ (ver abajo)
```

### HTTPS y celulares de prueba

Fuera de `localhost`, los navegadores solo permiten service worker, GPS y cámara
con HTTPS de confianza. `scripts/certificado-local.sh` crea una autoridad
certificadora (CA) propia de SIGVER y firma con ella el certificado del servidor
(válido para `localhost` y la IP de la PC en la red).

1. **En cada celular, una sola vez:** abrir `http://<IP-de-la-PC>/sigver-ca.crt` e
   instalarla como certificado de CA (Android: Ajustes › Seguridad › Cifrado y
   credenciales › Instalar un certificado › Certificado de CA. iPhone: instalar el
   perfil y activarlo en Ajustes › General › Información › Ajustes de confianza).
2. Entrar a `https://<IP-de-la-PC>/`.

En la propia PC se usa `http://localhost/`: el navegador ya lo considera seguro,
así que no hace falta instalar la CA (solo si se quiere probar `https://` en la PC).

> nginx monta sus archivos de configuración uno por uno: después de editarlos,
> `docker compose restart nginx` (un `nginx -s reload` puede seguir leyendo la versión anterior).

Si cambia la IP de la PC, volver a correr el script (la CA se conserva, no hay que
reinstalarla) y `docker compose restart nginx`.

**Producción:** no se usa la CA local. Se copia el certificado real (de ANDE o de
Let's Encrypt) como `nginx/certs/servidor.crt` y `nginx/certs/servidor.key`, y se
usa `DJANGO_SETTINGS_MODULE=config.settings.prod` (cookies seguras y HSTS).
La carpeta `nginx/certs/` está en `.gitignore`: las claves privadas nunca van al repositorio.

### Pruebas por internet (supervisores, con wifi o datos móviles)

`scripts/ngrok.sh` publica SIGVER con ngrok: HTTPS válido, sin instalar la CA en
los celulares. Mientras corre, Django usa la configuración de producción (sin DEBUG),
solo acepta la dirección de ngrok y no se publican los puertos 8000 ni 5432
(`docker-compose.ngrok.yml`). Ctrl+C lo corta y vuelve al modo desarrollo.

1. **Una sola vez:** crear una cuenta gratis en ngrok, correr
   `ngrok config add-authtoken <TOKEN>` y poner el dominio fijo gratis de la cuenta
   en el `.env` (`NGROK_DOMAIN=algo.ngrok-free.app`). El dominio fijo importa:
   si cambiara, la app instalada en los celulares y su cola sin señal quedarían en la dirección vieja.
2. `scripts/ngrok.sh` y pasar a los supervisores `https://<NGROK_DOMAIN>/`.

Mientras está activo, en esta PC también se entra por la dirección de ngrok
(`http://localhost` redirige a HTTPS). La PC tiene que estar prendida y con internet.

### Publicar una versión nueva de la PWA

```bash
scripts/version.sh   # sube el ?v= en todos los archivos y corre collectstatic
```

Documentación y decisiones arquitectónicas

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