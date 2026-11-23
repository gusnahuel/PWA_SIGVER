"""
SIGVER - Configuración base compartida
"""
import sys
from pathlib import Path
from decouple import config, Csv
from datetime import timedelta
# ==========================================
# RUTAS
# ==========================================
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# ==========================================
# SEGURIDAD
# ==========================================
SECRET_KEY = config('DJANGO_SECRET_KEY')
DEBUG = config('DJANGO_DEBUG', default=False, cast=bool)
ALLOWED_HOSTS = config('DJANGO_ALLOWED_HOSTS', default='localhost', cast=Csv())

CSRF_TRUSTED_ORIGINS = config(
    'DJANGO_CSRF_TRUSTED_ORIGINS',
    default='http://localhost:8000,http://localhost,http://127.0.0.1:8000',
    cast=Csv(),
)

# ==========================================
# APLICACIONES
# ==========================================
DJANGO_APPS = [
    'jazzmin',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.gis',   # GeoDjango
]

THIRD_PARTY_APPS = [
    'rest_framework',
    'rest_framework_gis',
    'rest_framework_simplejwt.token_blacklist',  # revocar refresh tokens (logout y rotación)
    'corsheaders',
    'django_filters',
]

LOCAL_APPS = [
    'apps.usuarios',
    'apps.inventario',
    'apps.operaciones',
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

# ==========================================
# MIDDLEWARE
# ==========================================
MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

# ==========================================
# TEMPLATES
# ==========================================
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        # templates/: personalización del admin (inicio con bandejas de trabajo)
        'DIRS': [BASE_DIR / 'templates', BASE_DIR.parent / 'frontend'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

# ==========================================
# WSGI / ASGI
# ==========================================
WSGI_APPLICATION = 'config.wsgi.application'
ASGI_APPLICATION = 'config.asgi.application'

# ==========================================
# BASE DE DATOS (PostgreSQL + PostGIS)
# ==========================================
DATABASES = {
    'default': {
        'ENGINE': 'django.contrib.gis.db.backends.postgis',
        'NAME': config('DB_NAME', default='sigver_db'),
        'USER': config('DB_USER', default='sigver_admin'),
        'PASSWORD': config('DB_PASSWORD', default=''),
        'HOST': config('DB_HOST', default='localhost'),
        'PORT': config('DB_PORT', default='5432'),
    }
}

# ==========================================
# AUTENTICACIÓN
# ==========================================
AUTH_USER_MODEL = 'usuarios.Usuario'

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# ==========================================
# INTERNACIONALIZACIÓN
# ==========================================
LANGUAGE_CODE = 'es-py'
TIME_ZONE = 'America/Asuncion'
USE_I18N = True
USE_TZ = True
FORMAT_MODULE_PATH = ['config.formats']

# ==========================================
# ARCHIVOS ESTÁTICOS Y MEDIA
# ==========================================
STATIC_URL = '/static/'
_frontend_static = BASE_DIR.parent / 'frontend' / 'static'
STATICFILES_DIRS = [BASE_DIR / 'static']  # estilos del admin
if _frontend_static.exists():
    STATICFILES_DIRS.append(_frontend_static)
STATIC_ROOT = BASE_DIR / 'staticfiles'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# ==========================================
# DJANGO REST FRAMEWORK
# ==========================================
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_FILTER_BACKENDS': [
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 100,
    'PAGE_SIZE_QUERY_PARAM': 'page_size',
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
    ],
    # nginx está delante: la IP real del cliente es la última de X-Forwarded-For
    'NUM_PROXIES': 1,
    # Límite de pedidos por IP en el login (además del bloqueo por usuario en
    # apps/usuarios/seguridad.py)
    'DEFAULT_THROTTLE_RATES': {
        'login': '10/min',
        'token_refresh': '60/min',
    },
}

# Bloqueo por intentos fallidos (admin y API)
AUTHENTICATION_BACKENDS = ['apps.usuarios.seguridad.BackendConBloqueo']

# Caché en archivos: la comparten los procesos de gunicorn del mismo contenedor
# (con la de memoria, cada proceso llevaría su propia cuenta de intentos)
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.filebased.FileBasedCache',
        'LOCATION': config('DJANGO_CACHE_DIR', default='/tmp/sigver_cache'),
    }
}
if 'test' in sys.argv:
    # Los tests limpian el caché: que no borren los bloqueos del servidor en uso
    CACHES = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}}

# ==========================================
# CSRF (para permitir a la PWA leer el token)
# ==========================================
CSRF_COOKIE_HTTPONLY = False

# nginx termina el HTTPS y avisa con X-Forwarded-Proto (lo fija nginx, el
# cliente no lo puede falsear). Sin esto Django cree que la conexión es HTTP
# y rechaza el login del admin por CSRF (origen https:// distinto de http://).
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
# SAMEORIGIN: el admin (Jazzmin) abre ventanas internas del mismo sitio;
# con DENY (el valor por defecto de Django) quedan en blanco.
X_FRAME_OPTIONS = 'SAMEORIGIN'
CSRF_COOKIE_SAMESITE = 'Lax'
SESSION_COOKIE_SAMESITE = 'Lax'

# ==========================================
# DEFAULT AUTO FIELD
# ==========================================
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
# ==========================================
# LOGGING (los errores de validación se registran en consola / docker logs)
# ==========================================
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {'console': {'class': 'logging.StreamHandler'}},
    'loggers': {
        'apps': {'handlers': ['console'], 'level': 'INFO'},
    },
}

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=60),
    # 7 días desde la última renovación: con la rotación, un técnico que usa la
    # app no tiene que volver a ingresar; uno que la deja una semana, sí.
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS': True,       # cada renovación entrega un refresh nuevo...
    'BLACKLIST_AFTER_ROTATION': True,    # ...y revoca el anterior
    'UPDATE_LAST_LOGIN': True,           # "último ingreso" visible en el admin
    'AUTH_HEADER_TYPES': ('Bearer',),
}
# ==========================================
# CONFIGURACIÓN DE JAZZMIN (Django Admin Premium)
# ==========================================
JAZZMIN_SETTINGS = {
    "site_title": "SIGVER Admin",
    "site_header": "SIGVER",
    "site_brand": "SIGVER",
    "site_logo": "icons/icon-maskable.svg",  # mismo dibujo que el ícono de la app
    "site_logo_classes": "",            # el logo es cuadrado: sin recorte circular
    "login_logo": "icons/icon-maskable.svg",  # mismo dibujo que el ícono de la app
    "site_icon": "icons/icon-maskable.svg",  # mismo dibujo que el ícono de la app
    "welcome_sign": "Gestión de reclamos, verificaciones e inventario",
    "copyright": "ANDE · Departamento de Operación",
    "search_model": ["operaciones.Reclamo", "inventario.Sitio"],
    "user_avatar": None,

    # Menú: primero el trabajo diario, después los datos de la red, al final la configuración
    "navigation_expanded": True,
    "hide_apps": ["auth"],  # Grupos se muestra dentro de "Usuarios y accesos"
    "hide_models": [
        # Se ven dentro de su ficha (verificación, ensayo o componente)
        "operaciones.MedicionTermografia",
        "operaciones.EnsayoPAT",
        "operaciones.LecturaPAT",
        "inventario.ElementoEquipo",
    ],
    "order_with_respect_to": [
        "operaciones",
        "operaciones.Reclamo",
        "operaciones.Verificacion",
        "operaciones.VerificacionETC",
        "operaciones.TipoFallaETC",
        "operaciones.PuntoInspeccionTermografia",
        "inventario",
        "inventario.Sitio",
        "inventario.EquipoETC",
        "inventario.Componente",
        "inventario.Personal",
        "inventario.Agencia",
        "inventario.SeccionRegional",
        "inventario.SubEstacion",
        "inventario.Alimentador",
        "usuarios",
    ],
    "custom_links": {
        "operaciones": [{
            "name": "Indicadores de reclamos",
            "url": "admin:operaciones_reclamo_indicadores",
            "icon": "fas fa-chart-line",
            "permissions": ["operaciones.view_reclamo"],
        }],
        "usuarios": [{
            "name": "Grupos y permisos",
            "url": "admin:auth_group_changelist",
            "icon": "fas fa-user-shield",
            "permissions": ["auth.view_group"],
        }],
    },
    "topmenu_links": [
        {"name": "Abrir la app", "url": "/", "new_window": True},
    ],
    "icons": {
        "operaciones": "fas fa-hard-hat",
        "inventario": "fas fa-network-wired",
        "usuarios": "fas fa-users-cog",
        "usuarios.Usuario": "fas fa-user",
        "auth.Group": "fas fa-user-shield",
        "inventario.Agencia": "fas fa-building",
        "inventario.SeccionRegional": "fas fa-map",
        "inventario.SubEstacion": "fas fa-industry",
        "inventario.Alimentador": "fas fa-project-diagram",
        "inventario.Sitio": "fas fa-map-marker-alt",
        "inventario.EquipoETC": "fas fa-broadcast-tower",
        "inventario.Componente": "fas fa-microchip",
        "inventario.Personal": "fas fa-id-badge",
        "operaciones.Reclamo": "fas fa-exclamation-triangle",
        "operaciones.Verificacion": "fas fa-clipboard-check",
        "operaciones.VerificacionETC": "fas fa-clipboard-list",
        "operaciones.TipoFallaETC": "fas fa-tags",
        "operaciones.PuntoInspeccionTermografia": "fas fa-temperature-high",
    },
    "default_icon_children": "fas fa-angle-right",

    # Fichas: pestañas en general; el reclamo en una sola página para validar de un vistazo
    "changeform_format": "horizontal_tabs",
    "changeform_format_overrides": {
        "operaciones.reclamo": "single",
        "usuarios.usuario": "collapsible",
    },
    "related_modal_active": True,
    "custom_css": "sigver_admin/admin.css",
    "use_google_fonts_cdn": False,  # usamos Inter (como la PWA), cargada en admin.css
    "show_ui_builder": False,
    "show_theme_chooser": False,  # colores institucionales fijos; claro/oscuro según el sistema
}

JAZZMIN_UI_TWEAKS = {
    "navbar_small_text": False,
    "footer_small_text": True,
    "body_small_text": False,
    "brand_small_text": False,
    "brand_colour": False,
    "accent": "accent-primary",
    "navbar": "navbar-white navbar-light",
    "no_navbar_border": True,
    "navbar_fixed": True,
    "layout_boxed": False,
    "footer_fixed": False,
    "sidebar_fixed": True,
    "sidebar": "sidebar-dark-primary", # Barra lateral oscura
    "sidebar_nav_small_text": False,
    "sidebar_disable_expand": False,
    "sidebar_nav_child_indent": True,
    "sidebar_nav_compact_style": False,
    "sidebar_nav_legacy_style": False,
    "sidebar_nav_flat_style": False,
    "theme": "default", 
    "default_theme_mode": "auto", 
    "button_classes": {
        "primary": "btn-primary",
        "secondary": "btn-outline-secondary",
        "info": "btn-outline-primary",
        "warning": "btn-warning",
        "danger": "btn-outline-danger",
        "success": "btn-primary",   # Guardar / Añadir con el azul institucional
    }
}