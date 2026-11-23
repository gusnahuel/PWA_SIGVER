"""
SIGVER - Indicadores de gestión de reclamos

Se calculan sobre los reclamos que el usuario puede ver (mismo alcance por rol
que la API y el admin) y recibidos dentro del período elegido.

    Tiempo de resolución   desde que se recibe el reclamo hasta que el
                           supervisor valida el trabajo (o se cierra).
    En plazo               el técnico envió el trabajo terminado antes de la
                           fecha límite de su prioridad.
    Devueltos              de los que llegaron a validación, cuántos el
                           supervisor tuvo que devolver al menos una vez.
    Vencidos ahora         sin asignar o en manos del técnico, fuera de plazo
                           (es una foto del momento: no depende del período).
"""
from datetime import timedelta

from django.db.models import Avg, DurationField, ExpressionWrapper, F, Q
from django.db.models.functions import Coalesce
from django.utils import timezone

from .models import HistorialReclamo, Reclamo
from .reclamos import ESTADOS_ACTIVOS, PLAZOS

PERIODOS = {
    '30': ('Últimos 30 días', timedelta(days=30)),
    '90': ('Últimos 90 días', timedelta(days=90)),
    '365': ('Último año', timedelta(days=365)),
    'todo': ('Desde el inicio', None),
}
PERIODO_POR_DEFECTO = '90'


def _porcentaje(parte, total):
    return round(100 * parte / total) if total else None


def resumen(qs, ahora):
    cerrados = qs.filter(estado='CERRADO')
    tiempo = cerrados.annotate(
        fin=Coalesce('fecha_validacion', 'fecha_cierre'),
    ).filter(fin__isnull=False).aggregate(
        t=Avg(ExpressionWrapper(F('fin') - F('fecha_reclamo'), output_field=DurationField())),
    )['t']

    con_plazo = cerrados.filter(fecha_ejecucion__isnull=False, fecha_limite__isnull=False)
    en_plazo = con_plazo.filter(fecha_ejecucion__lte=F('fecha_limite')).count()

    validados = set(HistorialReclamo.objects.filter(
        reclamo__in=qs, estado_nuevo='PENDIENTE_VALIDACION').values_list('reclamo_id', flat=True))
    devueltos = set(HistorialReclamo.objects.filter(
        reclamo__in=qs, estado_anterior='PENDIENTE_VALIDACION', estado_nuevo='EN_PROCESO',
    ).values_list('reclamo_id', flat=True))

    return {
        'recibidos': qs.count(),
        'cerrados': cerrados.count(),
        'rechazados': qs.filter(estado='RECHAZADO').count(),
        'activos': qs.filter(estado__in=(*ESTADOS_ACTIVOS, 'PENDIENTE_VALIDACION')).count(),
        'tiempo_medio': tiempo,
        'con_plazo': con_plazo.count(),
        'pct_en_plazo': _porcentaje(en_plazo, con_plazo.count()),
        'llegaron_a_validacion': len(validados),
        'pct_devueltos': _porcentaje(len(devueltos & validados), len(validados)),
    }


def calcular(base, periodo=PERIODO_POR_DEFECTO, ahora=None):
    """`base`: reclamos visibles para el usuario (ya filtrados por rol)."""
    ahora = ahora or timezone.now()
    nombre_periodo, duracion = PERIODOS.get(periodo, PERIODOS[PERIODO_POR_DEFECTO])
    qs = base.filter(fecha_reclamo__gte=ahora - duracion) if duracion else base

    vencidos = base.filter(estado__in=ESTADOS_ACTIVOS, fecha_limite__lt=ahora)

    por_prioridad = []
    for clave, nombre in Reclamo._meta.get_field('prioridad').choices[::-1]:   # de crítica a baja
        filtro = Q(prioridad=clave) | (Q(prioridad='') if clave == 'MEDIA' else Q(pk__in=[]))
        datos = resumen(qs.filter(filtro), ahora)
        plazo = PLAZOS[clave]
        datos.update(
            clave=clave, nombre=nombre, plazo=plazo,
            vencidos=vencidos.filter(filtro).count(),
            # Cuánto del plazo se usa en promedio (para la barra): 1.0 = justo en el límite
            uso_del_plazo=(datos['tiempo_medio'] / plazo) if datos['tiempo_medio'] is not None else None,
        )
        if datos['uso_del_plazo'] is not None:
            datos['ancho_barra'] = round(min(datos['uso_del_plazo'], 1) * 100)
            datos['excede_plazo'] = datos['uso_del_plazo'] > 1
        por_prioridad.append(datos)

    por_agencia = []
    agencias = (qs.values_list('agencia_responsable_id', 'agencia_responsable__nombre')
                .distinct().order_by('agencia_responsable__nombre'))
    for agencia_id, nombre in agencias:
        filtro = Q(agencia_responsable_id=agencia_id) if agencia_id else Q(agencia_responsable__isnull=True)
        datos = resumen(qs.filter(filtro), ahora)
        datos.update(nombre=nombre or 'Sin agencia', vencidos=vencidos.filter(filtro).count())
        por_agencia.append(datos)

    return {
        'periodo': periodo if periodo in PERIODOS else PERIODO_POR_DEFECTO,
        'nombre_periodo': nombre_periodo,
        'periodos': [(clave, nombre) for clave, (nombre, _) in PERIODOS.items()],
        'total': resumen(qs, ahora),
        'vencidos_ahora': vencidos.count(),
        'por_prioridad': por_prioridad,
        'por_agencia': por_agencia,
    }


def texto_duracion(delta):
    """Duración legible: '3 d 4 h', '5 h', '40 min'."""
    if delta is None:
        return '—'
    minutos = int(delta.total_seconds() // 60)
    dias, resto = divmod(minutos, 1440)
    horas, minutos = divmod(resto, 60)
    if dias:
        return f'{dias} d {horas} h' if horas else f'{dias} d'
    if horas:
        return f'{horas} h'
    return f'{max(minutos, 1)} min'
