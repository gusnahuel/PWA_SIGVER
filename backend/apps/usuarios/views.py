from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenBlacklistView, TokenObtainPairView, TokenRefreshView

from .seguridad import MENSAJE_BLOQUEO, esta_bloqueado


class PerfilUsuarioView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        personal_id = None

        # Verificamos si el usuario tiene un perfil de Personal asociado
        if hasattr(user, 'personal'):
            personal_id = user.personal.id

        return Response({
            'id': str(user.id),
            'username': user.username,
            'nombre': user.get_full_name() or user.username,
            'rol': user.rol,
            'personal_id': str(personal_id) if personal_id else None
        })


class LoginView(TokenObtainPairView):
    """Login de la PWA: límite de pedidos por IP y bloqueo por intentos fallidos."""
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'login'

    def post(self, request, *args, **kwargs):
        # El backend ya rechaza al usuario bloqueado; acá se avisa con un 429
        # para que la app muestre el motivo en lugar de "contraseña incorrecta".
        if esta_bloqueado(request, request.data.get('username')):
            return Response({'detail': MENSAJE_BLOQUEO}, status=status.HTTP_429_TOO_MANY_REQUESTS)
        return super().post(request, *args, **kwargs)


class RenovarTokenView(TokenRefreshView):
    """Renueva el access token. Con rotación: devuelve también un refresh nuevo
    y el anterior queda revocado."""
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'token_refresh'


class LogoutView(TokenBlacklistView):
    """Revoca el refresh token al cerrar sesión (si alguien lo copió, deja de servir)."""
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'token_refresh'
