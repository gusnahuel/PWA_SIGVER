"""
SIGVER - Configuración de desarrollo
"""
from .base import *

DEBUG = True

ALLOWED_HOSTS = ['*']

# CORS permisivo en desarrollo
CORS_ALLOW_ALL_ORIGINS = True