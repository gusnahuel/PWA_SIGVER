from django.urls import path
from .views import CambiarClaveView, PerfilUsuarioView
app_name = 'usuarios'

urlpatterns = [
    path('me/', PerfilUsuarioView.as_view(), name='perfil'),
    path('cambiar-clave/', CambiarClaveView.as_view(), name='cambiar_clave'),
]
