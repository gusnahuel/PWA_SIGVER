"""
SIGVER - Vistas de Operaciones
"""
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from django.http import HttpResponse
from django.template.loader import render_to_string
from weasyprint import HTML
from django.utils import timezone
from django.conf import settings
import base64
import mimetypes
from io import BytesIO
from PIL import Image


from .models import VerificacionETC, TipoFallaETC, Verificacion, PuntoInspeccionTermografia, Reclamo
from .serializers import VerificacionETCSerializer, TipoFallaETCSerializer, PersonalSerializer, VerificacionSerializer
from apps.inventario.models import Personal
from .serializers import PuntoInspeccionTermografiaSerializer, ReclamoSerializer



class VerificacionETCViewSet(viewsets.ModelViewSet):
    """Endpoint para crear y listar verificaciones de ETC."""
    queryset = VerificacionETC.objects.all().order_by('-fecha_verificacion')
    serializer_class = VerificacionETCSerializer
    permission_classes = [IsAuthenticated]
    parser_classes = (MultiPartParser, FormParser, JSONParser)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            # ESTO IMPRIMIRÁ EL ERROR EXACTO EN LA TERMINAL
            print("❌ ERROR DE VALIDACIÓN:", serializer.errors)
            return Response(serializer.errors, status=400)
        
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=201, headers=headers)


class TipoFallaETCViewSet(viewsets.ReadOnlyModelViewSet):
    """Endpoint para listar las 26 fallas del manual."""
    queryset = TipoFallaETC.objects.filter(activo=True)
    serializer_class = TipoFallaETCSerializer
    permission_classes = [IsAuthenticated]


class PersonalViewSet(viewsets.ReadOnlyModelViewSet):
    """Endpoint para listar el personal de campo."""
    queryset = Personal.objects.filter(activo=True)
    serializer_class = PersonalSerializer
    permission_classes = [IsAuthenticated]

class ReclamoViewSet(viewsets.ModelViewSet):
    queryset = Reclamo.objects.all().order_by('-fecha_reclamo')
    serializer_class = ReclamoSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = super().get_queryset()
        # Si el frontend pide los reclamos de un técnico específico
        personal_id = self.request.query_params.get('responsable_asignado', None)
        if personal_id:
            return qs.filter(responsable_asignado_id=personal_id)
        return qs    

class VerificacionViewSet(viewsets.ModelViewSet):
    """Endpoint para crear y listar verificaciones de Reguladores."""
    queryset = Verificacion.objects.all().order_by('-fecha_verificacion')
    serializer_class = VerificacionSerializer
    permission_classes = [IsAuthenticated]
    parser_classes = (MultiPartParser, FormParser, JSONParser)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            # ESTO IMPRIMIRÁ EL ERROR EXACTO EN LA TERMINAL
            print("❌ ERROR DE VALIDACIÓN:", serializer.errors)
            return Response(serializer.errors, status=400)
        
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=201, headers=headers)
    
class PuntoInspeccionTermografiaViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = PuntoInspeccionTermografia.objects.filter(activo=True)
    serializer_class = PuntoInspeccionTermografiaSerializer
    permission_classes = [IsAuthenticated]

def imagen_a_base64(imagen):
    if not imagen:
        return None
    try:
        with imagen.open('rb') as f:
            return "data:image/jpeg;base64," + base64.b64encode(f.read()).decode('utf-8')
    except Exception as e:
        print(f"Error al codificar imagen: {e}")
        return None

def imagen_a_base64(imagen):
    if not imagen:
        return None
    try:
        if not imagen.storage.exists(imagen.name):
            return None
            
        with imagen.open('rb') as f:
            img = Image.open(f)
            
            # Convertir a RGB si es necesario (por si es PNG con transparencia)
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            
            # 👇 REDIMENSIONAR: Máximo 800px de ancho para que no pese tanto
            max_size = (800, 800)
            img.thumbnail(max_size, Image.Resampling.LANCZOS)
            
            # Guardar en memoria
            output = BytesIO()
            img.save(output, format='JPEG', quality=80) # Calidad 80% es buen balance
            encoded = base64.b64encode(output.getvalue()).decode('utf-8')
            
            return f"data:image/jpeg;base64,{encoded}"
    except Exception as e:
        print(f"❌ Error al codificar imagen {imagen.name}: {e}")
        return None

def generar_informe_pdf(request, tipo, id):
    if tipo == 'etc':
        verificacion = VerificacionETC.objects.get(id=id)
        template = 'reportes/informe_verificacion.html'
        contexto = {
            'verificacion': verificacion, 
            'tipo': 'ETC',
            'foto_b64': imagen_a_base64(verificacion.foto)
        }
    else:
        verificacion = Verificacion.objects.get(id=id)
        template = 'reportes/informe_verificacion.html'
        contexto = {
            'verificacion': verificacion, 
            'tipo': 'REGULADOR',
            'foto_frontal_b64': imagen_a_base64(verificacion.foto_frontal),
            'foto_entorno_b64': imagen_a_base64(verificacion.foto_entorno),
            'foto_control_b64': imagen_a_base64(verificacion.foto_control_unico)
        }

    contexto['fecha_actual'] = timezone.now()
    html_string = render_to_string(template, contexto)
    html = HTML(string=html_string)
    pdf = html.write_pdf()

    response = HttpResponse(pdf, content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="informe_{tipo}_{id}.pdf"'
    response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response['Pragma'] = 'no-cache'
    response['Expires'] = '0'
    return response