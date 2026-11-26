"""
SIGVER - Estado de los equipos en el mapa

Regla: un equipo figura "con problema" mientras la última verificación lo
reportó con falla o tenga un reclamo sin terminar. Cerrar el reclamo (el
supervisor validó la reparación) lo apaga, aunque la verificación que
originó la falla sea anterior.

    ETC        -> EquipoETC.tiene_problema_actual (True / False)
    Regulador  -> Sitio.estado_general (NORMAL / OBSERVADO / CRITICO / FUERA_SERVICIO)

Cada función devuelve un texto para el historial del reclamo cuando cambia
algo (o '' si no hubo cambio).
"""
from django.db.models import Q

from apps.inventario.models import Componente, EquipoETC, Sitio
from .models import Reclamo, Verificacion

ESTADOS_TERMINADOS = ('CERRADO', 'RECHAZADO')
ESTADOS_SITIO_CON_PROBLEMA = ('OBSERVADO', 'CRITICO')


def _reclamos_activos(**filtro):
    return Reclamo.objects.filter(**filtro).exclude(estado__in=ESTADOS_TERMINADOS)


# =====================================================
# Al guardar una verificación
# =====================================================

def por_verificacion_etc(verificacion):
    """Actualiza el ETC solo si esta es su verificación más reciente (pueden llegar fuera de orden)."""
    con_reclamo = _reclamos_activos(equipo_etc_id=verificacion.equipo_etc_id).exists()
    EquipoETC.objects.filter(pk=verificacion.equipo_etc_id).filter(
        Q(fecha_ultima_verificacion__isnull=True)
        | Q(fecha_ultima_verificacion__lte=verificacion.fecha_verificacion)
    ).update(
        fecha_ultima_verificacion=verificacion.fecha_verificacion,
        # Sin falla en esta visita, pero con un reclamo abierto: sigue en rojo hasta cerrarlo
        tiene_problema_actual=verificacion.tiene_inconveniente or con_reclamo,
    )


def por_verificacion_regulador(verificacion):
    """Pasa al sitio el estado observado en la verificación, si es la más reciente."""
    _componente_por_verificacion(verificacion)
    nuevo = verificacion.estado_sitio
    if not nuevo:
        return
    hay_posterior = Verificacion.objects.filter(
        sitio_id=verificacion.sitio_id, fecha_verificacion__gt=verificacion.fecha_verificacion,
    ).exclude(pk=verificacion.pk).exists()
    if hay_posterior:
        return
    if nuevo == 'NORMAL' and _reclamos_activos(componente__sitio_id=verificacion.sitio_id).exists():
        return   # igual que en ETC: el reclamo abierto manda hasta que se cierre
    Sitio.objects.filter(pk=verificacion.sitio_id).update(estado_general=nuevo)


def _componente_por_verificacion(verificacion):
    """El estado del regulador y de su control que vio la última visita queda en el Componente."""
    if not (verificacion.componente_id and (verificacion.estado_componente or verificacion.estado_control)):
        return   # versiones anteriores de la app no envían estos datos
    hay_posterior = Verificacion.objects.filter(
        componente_id=verificacion.componente_id, fecha_verificacion__gt=verificacion.fecha_verificacion,
    ).exclude(pk=verificacion.pk).exists()
    if hay_posterior:
        return
    Componente.objects.filter(pk=verificacion.componente_id).update(
        estado_componente=verificacion.get_estado_componente_display() if verificacion.estado_componente else '',
        observaciones_componente=verificacion.observaciones_componente,
        estado_control=verificacion.estado_control,
        observaciones_control=verificacion.observaciones_control,
    )


# =====================================================
# Al terminar o reabrir un reclamo
# =====================================================

def por_reclamo(reclamo):
    """Recalcula el equipo del reclamo después de un cambio de estado."""
    terminado = reclamo.estado in ESTADOS_TERMINADOS
    if reclamo.equipo_etc_id:
        return _etc_por_reclamo(reclamo, terminado)
    if reclamo.componente_id:
        return _sitio_por_reclamo(reclamo, terminado)
    return ''


def _etc_por_reclamo(reclamo, terminado):
    equipo = EquipoETC.objects.get(pk=reclamo.equipo_etc_id)
    problema = not terminado or _reclamos_activos(equipo_etc_id=equipo.pk).exists()
    if problema == equipo.tiene_problema_actual:
        return ''
    EquipoETC.objects.filter(pk=equipo.pk).update(tiene_problema_actual=problema)
    return (f'Mapa: el ETC {equipo.nro_equipo} ' + ('vuelve a figurar con problema.' if problema
                                                    else 'deja de figurar con problema.'))


def _sitio_por_reclamo(reclamo, terminado):
    sitio = Sitio.objects.get(componentes__id=reclamo.componente_id)
    if terminado:
        # FUERA_SERVICIO no se toca: eso lo determina una verificación en el lugar
        if sitio.estado_general not in ESTADOS_SITIO_CON_PROBLEMA:
            return ''
        if _reclamos_activos(componente__sitio_id=sitio.pk).exists():
            return ''
        nuevo = 'NORMAL'
    else:
        if sitio.estado_general not in ('', 'NORMAL'):
            return ''
        nuevo = 'OBSERVADO'
    Sitio.objects.filter(pk=sitio.pk).update(estado_general=nuevo)
    return f'Mapa: el sitio {sitio.id_sitio} pasa a «{dict(Sitio.ESTADO_SITIO)[nuevo]}».'
