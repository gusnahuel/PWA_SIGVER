"""
SIGVER - URLs raíz
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from apps.operaciones.views import generar_informe_pdf
from apps.usuarios.views import LoginView, LogoutView, RenovarTokenView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/token/', LoginView.as_view(), name='token_obtain_pair'),
    path('api/token/refresh/', RenovarTokenView.as_view(), name='token_refresh'),
    path('api/token/logout/', LogoutView.as_view(), name='token_logout'),
    path('api/usuarios/', include('apps.usuarios.urls')),
    path('api/inventario/', include('apps.inventario.urls')),
    path('api/operaciones/', include('apps.operaciones.urls')),
    path('reportes/<str:tipo>/<uuid:id>/', generar_informe_pdf, name='generar_pdf'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)