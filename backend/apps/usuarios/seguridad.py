"""
SIGVER - Protección del inicio de sesión contra la prueba de contraseñas.

Tanto el login del admin como el de la API (/api/token/) pasan por
django.contrib.auth.authenticate(), así que un solo backend cubre las dos
entradas: después de MAX_FALLOS intentos fallidos con el mismo usuario desde
la misma IP, ese usuario queda bloqueado en esa IP durante BLOQUEO_SEGUNDOS.

Se cuenta por usuario + IP (y no solo por usuario) para que alguien de afuera
no pueda dejar bloqueado a un técnico legítimo con solo equivocarse a propósito.
"""
from django.contrib.auth.backends import ModelBackend
from django.core.cache import cache

MAX_FALLOS = 5
BLOQUEO_SEGUNDOS = 15 * 60
MENSAJE_BLOQUEO = (
    'Demasiados intentos fallidos. Por seguridad, esperá 15 minutos antes de volver a intentar.'
)


def ip_cliente(request):
    """IP real del cliente detrás de nginx.

    nginx agrega la IP que ve al final de X-Forwarded-For; se toma la última
    porque las anteriores las puede inventar el propio cliente.
    """
    xff = request.META.get('HTTP_X_FORWARDED_FOR', '')
    if xff:
        return xff.split(',')[-1].strip()
    return request.META.get('REMOTE_ADDR', '')


def _clave(request, username):
    return f'sigver:login_fallos:{ip_cliente(request)}:{(username or "").strip().lower()}'


def esta_bloqueado(request, username):
    return bool(username) and cache.get(_clave(request, username), 0) >= MAX_FALLOS


def registrar_fallo(request, username):
    clave = _clave(request, username)
    # add() solo crea la clave si no existe: el plazo corre desde el primer fallo
    cache.add(clave, 0, BLOQUEO_SEGUNDOS)
    try:
        cache.incr(clave)
    except ValueError:  # venció justo entre add() e incr()
        cache.set(clave, 1, BLOQUEO_SEGUNDOS)


def limpiar_fallos(request, username):
    cache.delete(_clave(request, username))


class BackendConBloqueo(ModelBackend):
    """ModelBackend que rechaza a los usuarios bloqueados y cuenta los fallos."""

    def authenticate(self, request, username=None, password=None, **kwargs):
        if request is None or not username:
            return super().authenticate(request, username=username, password=password, **kwargs)

        if esta_bloqueado(request, username):
            return None

        user = super().authenticate(request, username=username, password=password, **kwargs)
        if user is None:
            registrar_fallo(request, username)
        else:
            limpiar_fallos(request, username)
        return user
