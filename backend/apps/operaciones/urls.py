"""
SIGVER - URLs de Operaciones
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import VerificacionETCViewSet, TipoFallaETCViewSet, PersonalViewSet
from .views import VerificacionViewSet, PuntoInspeccionTermografiaViewSet, ReclamoViewSet


app_name = 'operaciones'

router = DefaultRouter()
router.register(r'verificaciones-etc', VerificacionETCViewSet, basename='verificacion-etc')
router.register(r'fallas-etc', TipoFallaETCViewSet, basename='falla-etc')
router.register(r'personal', PersonalViewSet, basename='personal')
router.register(r'verificaciones', VerificacionViewSet, basename='verificacion')
router.register(r'puntos-termografia', PuntoInspeccionTermografiaViewSet, basename='puntos-termografia')
router.register(r'reclamos', ReclamoViewSet, basename='reclamos')
urlpatterns = [
    path('', include(router.urls)),
]
