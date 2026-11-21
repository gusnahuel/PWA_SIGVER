"""
SIGVER - URLs de Inventario
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import EquipoETCViewSet, SitioViewSet


app_name = 'inventario'

router = DefaultRouter()
router.register(r'equipos', EquipoETCViewSet, basename='equipo')
router.register(r'sitios', SitioViewSet, basename='sitio')

urlpatterns = [
    path('', include(router.urls)),
]