"""
SIGVER - Configuración de producción
"""
from .base import *  # noqa: F401,F403
from decouple import Csv, config

DEBUG = False

# CORS restrictivo
CORS_ALLOW_ALL_ORIGINS = False
CORS_ALLOWED_ORIGINS = config('DJANGO_CORS_ALLOWED_ORIGINS', default='', cast=Csv())

# Seguridad
# (SECURE_PROXY_SSL_HEADER está en base.py: nginx termina el HTTPS. Sin él,
# SECURE_SSL_REDIRECT entraría en un bucle infinito de redirecciones.)
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
# 0 en el modo de pruebas con ngrok (docker-compose.ngrok.yml)
SECURE_HSTS_SECONDS = config('DJANGO_HSTS_SECONDS', default=31536000, cast=int)
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
# X_FRAME_OPTIONS = 'SAMEORIGIN' viene de base.py (el admin usa ventanas internas)