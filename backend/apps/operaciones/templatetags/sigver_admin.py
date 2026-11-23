"""
Datos del inicio del admin: bandejas de trabajo del supervisor y lo último que llegó del campo.
No son indicadores (esos están en «Indicadores de reclamos»): son tareas pendientes, cada una con su enlace.
"""
from django import template
from django.urls import reverse

from apps.usuarios.permisos import filtrar_reclamos_por_rol, filtrar_verificaciones_por_rol

from .. import indicadores
from ..admin import filtrar_bandeja
from ..models import Reclamo, Verificacion, VerificacionETC

register = template.Library()

BANDEJAS = (
    ('validar', 'Pendientes de validación', 'Revisar la foto del técnico y cerrar o devolver',
     'fas fa-check-double', 'alerta'),
    ('vencidos', 'Vencidos', 'Superaron el plazo de su prioridad', 'fas fa-hourglass-end', 'peligro'),
    ('sin_agencia', 'Sin agencia', 'Asignar la agencia que corresponde', 'fas fa-building', 'aviso'),
    ('sin_tecnico', 'Sin técnico asignado', 'Asignar un responsable', 'fas fa-user-clock', 'aviso'),
    ('activos', 'Reclamos activos', 'Abiertos, asignados o en proceso', 'fas fa-tools', 'info'),
)


@register.simple_tag(takes_context=True)
def panel_supervisor(context):
    user = context['request'].user
    puede_reclamos = user.has_perm('operaciones.view_reclamo')
    datos = {'bandejas': [], 'verificaciones': []}

    if puede_reclamos:
        base = filtrar_reclamos_por_rol(user, Reclamo.objects.all())
        url = reverse('admin:operaciones_reclamo_changelist')
        for clave, titulo, ayuda, icono, tono in BANDEJAS:
            datos['bandejas'].append({
                'titulo': titulo, 'ayuda': ayuda, 'icono': icono, 'tono': tono,
                'cantidad': filtrar_bandeja(base, clave).count(),
                'url': f'{url}?bandeja={clave}',
            })

    recientes = []
    if user.has_perm('operaciones.view_verificacion'):
        regs = filtrar_verificaciones_por_rol(user, Verificacion.objects.select_related('sitio', 'responsable'))
        for v in regs.order_by('-fecha_verificacion')[:6]:
            recientes.append({
                'tipo': 'Regulador', 'codigo': v.sitio.id_sitio, 'fecha': v.fecha_verificacion,
                'responsable': v.responsable.nombre_completo,
                'estado': v.estado_sitio.lower() if v.estado_sitio else '',
                'estado_txt': v.get_estado_sitio_display() if v.estado_sitio else 'Sin dato',
                'url': reverse('admin:operaciones_verificacion_change', args=[v.pk]),
            })
    if user.has_perm('operaciones.view_verificacionetc'):
        etcs = filtrar_verificaciones_por_rol(user, VerificacionETC.objects.select_related('equipo_etc', 'responsable'))
        for v in etcs.order_by('-fecha_verificacion')[:6]:
            recientes.append({
                'tipo': 'ETC', 'codigo': v.equipo_etc.nro_equipo, 'fecha': v.fecha_verificacion,
                'responsable': v.responsable.nombre_completo,
                'estado': 'critico' if v.tiene_inconveniente else 'normal',
                'estado_txt': 'Con inconveniente' if v.tiene_inconveniente else 'Sin novedad',
                'url': reverse('admin:operaciones_verificacionetc_change', args=[v.pk]),
            })
    datos['verificaciones'] = sorted(recientes, key=lambda r: r['fecha'], reverse=True)[:6]
    return datos


@register.filter
def duracion(delta):
    """timedelta -> '3 d 4 h' (para los indicadores)."""
    return indicadores.texto_duracion(delta)
