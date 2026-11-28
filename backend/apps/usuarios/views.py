from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import transaction
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
from rest_framework_simplejwt.tokens import RefreshToken
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


class CambiarClaveView(APIView):
    """
    Cambio de contraseña desde la PWA. Pide la actual (pasa por el bloqueo por
    intentos fallidos, igual que el login), revoca las sesiones abiertas en otros
    celulares y devuelve tokens nuevos para que este siga con la sesión.
    """
    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'login'

    def post(self, request):
        user = request.user
        actual = request.data.get('actual') or ''
        nueva = request.data.get('nueva') or ''

        if esta_bloqueado(request, user.username):
            return Response({'detail': MENSAJE_BLOQUEO}, status=status.HTTP_429_TOO_MANY_REQUESTS)
        if authenticate(request, username=user.username, password=actual) is None:
            return Response({'actual': ['La contraseña actual no es correcta.']}, status=status.HTTP_400_BAD_REQUEST)
        if nueva == actual:
            return Response({'nueva': ['La nueva tiene que ser distinta de la actual.']},
                            status=status.HTTP_400_BAD_REQUEST)
        try:
            validate_password(nueva, user)
        except ValidationError as e:
            return Response({'nueva': list(e.messages)}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            user.set_password(nueva)
            user.save(update_fields=['password'])
            # Cualquier otra sesión (otro celular, alguien que copió el token) deja de renovarse
            for token in OutstandingToken.objects.filter(user=user):
                BlacklistedToken.objects.get_or_create(token=token)
        refresh = RefreshToken.for_user(user)
        return Response({'access': str(refresh.access_token), 'refresh': str(refresh)})
