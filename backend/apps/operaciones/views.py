"""
SIGVER - Vistas de Operaciones
"""
import base64
import logging
from io import BytesIO

from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.staticfiles import finders
from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string
from django.utils import timezone
from PIL import Image
from rest_framework import status, viewsets
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.inventario.models import Personal
from apps.usuarios.permisos import (
    SoloLecturaParaConsulta, filtrar_personal_por_rol, filtrar_reclamos_por_rol, filtrar_verificaciones_por_rol,
)
from . import geo, reclamos
from .models import (
    PuntoInspeccionTermografia, Reclamo, TipoFallaETC, Verificacion, VerificacionETC,
)
from .serializers import (
    PersonalSerializer, PuntoInspeccionTermografiaSerializer, ReclamoSerializer,
    TipoFallaETCSerializer, VerificacionETCSerializer, VerificacionSerializer,
)

logger = logging.getLogger(__name__)


class SincronizacionIdempotenteMixin:
    """
    Creación idempotente por `client_uuid`.

    Si la PWA reenvía una verificación que ya llegó (p. ej. el primer envío
    se guardó pero la respuesta se perdió por mala señal), devolvemos 200 con
    el registro existente en lugar de un 400, para que el cliente la pueda
    quitar de su cola sin perder datos.
    """
    http_method_names = ['get', 'post', 'head', 'options']

    def get_queryset(self):
        # Mínimo privilegio: el técnico ve las suyas, el supervisor las de sus agencias
        return filtrar_verificaciones_por_rol(self.request.user, super().get_queryset())

    def create(self, request, *args, **kwargs):
        client_uuid = request.data.get('client_uuid')
        if client_uuid:
            try:
                existente = self.get_queryset().filter(client_uuid=client_uuid).first()
            except (ValueError, DjangoValidationError):
                existente = None
            if existente is not None:
                return Response(self.get_serializer(existente).data, status=status.HTTP_200_OK)

        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            logger.warning('Verificación rechazada (%s): %s', self.__class__.__name__, serializer.errors)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)


class VerificacionETCViewSet(SincronizacionIdempotenteMixin, viewsets.ModelViewSet):
    """Crear y listar verificaciones de ETC (los registros no se editan ni borran por API)."""
    queryset = VerificacionETC.objects.select_related('equipo_etc', 'responsable').order_by('-fecha_verificacion')
    serializer_class = VerificacionETCSerializer
    permission_classes = [IsAuthenticated, SoloLecturaParaConsulta]
    parser_classes = (MultiPartParser, FormParser, JSONParser)


class VerificacionViewSet(SincronizacionIdempotenteMixin, viewsets.ModelViewSet):
    """Crear y listar verificaciones de Reguladores (los registros no se editan ni borran por API)."""
    queryset = Verificacion.objects.select_related('sitio', 'componente', 'responsable').order_by('-fecha_verificacion')
    serializer_class = VerificacionSerializer
    permission_classes = [IsAuthenticated, SoloLecturaParaConsulta]
    parser_classes = (MultiPartParser, FormParser, JSONParser)


class TipoFallaETCViewSet(viewsets.ReadOnlyModelViewSet):
    """Las 26 fallas del manual."""
    queryset = TipoFallaETC.objects.filter(activo=True)
    serializer_class = TipoFallaETCSerializer
    permission_classes = [IsAuthenticated]


class PersonalViewSet(viewsets.ReadOnlyModelViewSet):
    """Personal de campo activo."""
    queryset = Personal.objects.filter(activo=True)
    serializer_class = PersonalSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return filtrar_personal_por_rol(self.request.user, super().get_queryset())


class PuntoInspeccionTermografiaViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = PuntoInspeccionTermografia.objects.filter(activo=True)
    serializer_class = PuntoInspeccionTermografiaSerializer
    permission_classes = [IsAuthenticated]


class ReclamoViewSet(viewsets.ModelViewSet):
    """
    Reclamos filtrados por rol. Las reglas de cada cambio (quién, desde qué
    estado, con qué requisitos) están en apps/operaciones/reclamos.py, las
    mismas que usa el admin.
    Sin DELETE: un reclamo no se borra, se rechaza con motivo (queda en el historial).
    """
    queryset = Reclamo.objects.select_related('equipo_etc').prefetch_related('historial').order_by('-fecha_reclamo')
    serializer_class = ReclamoSerializer
    permission_classes = [IsAuthenticated, SoloLecturaParaConsulta]
    http_method_names = ['get', 'post', 'patch', 'head', 'options']

    def get_queryset(self):
        qs = filtrar_reclamos_por_rol(self.request.user, super().get_queryset())
        personal_id = self.request.query_params.get('responsable_asignado')
        if personal_id:
            try:
                qs = qs.filter(responsable_asignado_id=personal_id)
            except (ValueError, DjangoValidationError):
                return qs.none()
        return qs

    @staticmethod
    def _aplicar(funcion, *args, **kwargs):
        try:
            return funcion(*args, **kwargs)
        except reclamos.ReglaReclamo as e:
            if e.permiso:
                raise PermissionDenied(e.mensaje)
            raise ValidationError({e.campo or 'detail': [e.mensaje]})

    def perform_create(self, serializer):
        datos = dict(serializer.validated_data)
        comentario = datos.pop('comentario', '')
        datos = self._aplicar(reclamos.preparar_nuevo, self.request.user, datos)
        serializer.instance = reclamos.crear(self.request.user, detalle='Cargado a mano',
                                             comentario=comentario, **datos)

    def perform_update(self, serializer):
        cambios = dict(serializer.validated_data)
        comentario = cambios.pop('comentario', '')
        serializer.instance = self._aplicar(
            reclamos.actualizar, serializer.instance, self.request.user, cambios, comentario,
        )
        # El historial se precargó antes del cambio: que la respuesta traiga el nuevo
        serializer.instance = self.get_queryset().get(pk=serializer.instance.pk)


# =====================================================
# INFORMES PDF
# =====================================================

def imagen_a_base64(imagen, max_size=(800, 800)):
    """Reduce la imagen y la devuelve como data-URI JPEG para incrustarla en el PDF."""
    if not imagen:
        return None
    try:
        if not imagen.storage.exists(imagen.name):
            return None
        with imagen.open('rb') as f:
            img = Image.open(f)
            if img.mode != 'RGB':
                img = img.convert('RGB')
            img.thumbnail(max_size, Image.Resampling.LANCZOS)
            output = BytesIO()
            img.save(output, format='JPEG', quality=80)
        return 'data:image/jpeg;base64,' + base64.b64encode(output.getvalue()).decode('ascii')
    except Exception:
        logger.exception('Error al codificar imagen %s', imagen.name)
        return None


# Tono del veredicto del acta (mismo criterio de colores que el admin y el mapa)
TONO_ESTADO_SITIO = {'NORMAL': 'ok', 'OBSERVADO': 'aviso', 'CRITICO': 'peligro', 'FUERA_SERVICIO': 'peligro'}


def _ubicacion_del_acta(verificacion):
    """Qué dice el acta sobre dónde estaba el técnico (la distancia la midió el servidor)."""
    punto = verificacion.ubicacion_capturada
    if punto is None:
        declarada = verificacion.get_ubicacion_coincide_display() or 'sin dato'
        return {'texto': 'Sin GPS', 'detalle': f'Coincidencia declarada por el técnico: {declarada.lower()}',
                'tono': 'neutro'}
    metros = verificacion.distancia_equipo_m
    tono = {'SI': 'ok', 'APROXIMADA': 'aviso', 'NO': 'peligro'}[geo.coincide(metros)] if metros is not None else 'neutro'
    return {
        'texto': geo.texto_distancia(metros) if metros is not None else 'Registrada',
        'detalle': f'{punto.y:.6f}, {punto.x:.6f}'
                   + (f' · GPS ±{verificacion.precision_gps_m} m' if verificacion.precision_gps_m is not None else ''),
        'tono': tono,
    }


@staff_member_required
def generar_informe_pdf(request, tipo, id):
    """Acta PDF de una verificación. Solo accesible desde el admin (usuarios staff)."""
    from weasyprint import HTML  # import diferido: carga pesada

    # Mismo alcance por rol que el admin: un supervisor no descarga informes de otras zonas
    if tipo == 'etc':
        verificacion = get_object_or_404(
            filtrar_verificaciones_por_rol(request.user, VerificacionETC.objects.select_related(
                'equipo_etc__alimentador__subestacion', 'equipo_etc__sitio', 'responsable', 'agencia_responsable',
            )), id=id)
        fotos = [('Equipo', imagen_a_base64(verificacion.foto))]
        if verificacion.tiene_inconveniente:
            veredicto = {'texto': 'Con falla', 'tono': 'peligro'}
        else:
            veredicto = {'texto': 'Operativo', 'tono': 'ok'}
        contexto = {'tipo': 'ETC', 'nombre_tipo': 'Equipo telecomandado (ETC)',
                    'fallas': verificacion.fallas.order_by('numero')}
    elif tipo == 'regulador':
        verificacion = get_object_or_404(
            filtrar_verificaciones_por_rol(request.user, Verificacion.objects.select_related(
                'sitio__alimentador__subestacion', 'sitio__agencia', 'componente', 'responsable',
                'agencia_responsable',
            )), id=id)
        fotos = [('Frontal', imagen_a_base64(verificacion.foto_frontal)),
                 ('Entorno', imagen_a_base64(verificacion.foto_entorno)),
                 ('Control único', imagen_a_base64(verificacion.foto_control_unico))]
        veredicto = {'texto': verificacion.get_estado_sitio_display() or 'Sin dato',
                     'tono': TONO_ESTADO_SITIO.get(verificacion.estado_sitio, 'neutro')}
        contexto = {'tipo': 'REGULADOR', 'nombre_tipo': 'Regulador de tensión',
                    'mediciones': verificacion.mediciones_termografia.select_related('punto').order_by('fecha_hora'),
                    'ensayos': verificacion.ensayos_pat.prefetch_related('lecturas')}
    else:
        raise Http404('Tipo de informe desconocido.')

    if verificacion.requiere_reclamo:
        veredicto['detalle'] = f'Requiere intervención · prioridad {verificacion.get_prioridad_display().lower() or "media"}'
    else:
        veredicto['detalle'] = 'Sin reclamo de mantenimiento'

    contexto.update(
        verificacion=verificacion,
        veredicto=veredicto,
        ubicacion=_ubicacion_del_acta(verificacion),
        fotos=[(titulo, b64) for titulo, b64 in fotos if b64],
        reclamos=verificacion.reclamos.order_by('fecha_reclamo'),
        fecha_actual=timezone.now(),
        emitido_por=request.user.get_full_name() or request.user.username,
        # Archivos locales: el PDF se arma sin pedir nada a internet
        fuente_inter=finders.find('vendor/inter-5.2.5/inter-latin-wght-normal.woff2'),
        fuente_inter_ext=finders.find('vendor/inter-5.2.5/inter-latin-ext-wght-normal.woff2'),
        logo=finders.find('icons/icon-maskable.svg'),
    )
    html_string = render_to_string('reportes/informe_verificacion.html', contexto, request=request)
    pdf = HTML(string=html_string).write_pdf()

    response = HttpResponse(pdf, content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="acta_{verificacion.id_verificacion}.pdf"'
    response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return response
