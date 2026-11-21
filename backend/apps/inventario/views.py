"""
SIGVER - Vistas de Inventario
Solo lectura por ahora (prototipo visual).
"""
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from .models import EquipoETC, Sitio
from .serializers import EquipoETCSerializer, SitioSerializer


class EquipoETCViewSet(viewsets.ReadOnlyModelViewSet):
    """Endpoint de solo lectura para ETCs. Sin paginación (prototipo)."""
    queryset = EquipoETC.objects.select_related('alimentador__subestacion').all()
    serializer_class = EquipoETCSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None   # 👈 Deshabilitar paginación


class SitioViewSet(viewsets.ReadOnlyModelViewSet):
    """Endpoint de solo lectura para Sitios (reguladores). Sin paginación."""
    queryset = Sitio.objects.select_related('alimentador__subestacion').all()
    serializer_class = SitioSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None   # 👈 Deshabilitar paginación