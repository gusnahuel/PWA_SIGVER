"""
SIGVER - Reglas de los reclamos (única fuente de verdad)

Toda modificación de un reclamo pasa por acá, venga de la API de la PWA o del
admin de Django. Así no hay "otra puerta" para saltearse las reglas, y cada
cambio queda en el historial con quién, cuándo y por qué.

Recorrido normal:

    ABIERTO ──supervisor asigna técnico──> ASIGNADO
        ──técnico inicia (foto del estado inicial)──> EN_PROCESO
        ──técnico envía la foto del trabajo terminado y su ubicación──> PENDIENTE_VALIDACION
        ──supervisor valida──> CERRADO
                  └──supervisor devuelve (con motivo)──> EN_PROCESO

    Cualquier estado activo ──supervisor, con motivo──> RECHAZADO
    CERRADO / RECHAZADO ──admin EAM, con motivo──> se reabre
"""
import uuid
from dataclasses import dataclass, field
from datetime import timedelta

from django.db import transaction
from django.db.models.fields.files import FieldFile
from django.utils import timezone

from apps.inventario.models import Componente, EquipoETC, Sitio
from apps.usuarios.permisos import agencias_del_usuario
from . import estado_red, geo
from .models import HistorialReclamo, Reclamo

ESTADOS_ACTIVOS = ('ABIERTO', 'ASIGNADO', 'EN_PROCESO')
# Sin terminar: incluye el que espera validación (el trabajo puede ser devuelto)
ESTADOS_ABIERTOS = (*ESTADOS_ACTIVOS, 'PENDIENTE_VALIDACION')
ESTADOS_FINALES = ('CERRADO', 'RECHAZADO')
NOMBRE_ESTADO = dict(Reclamo.ESTADO)

SUPERVISION = frozenset({'supervisor', 'admin_eam'})
TODOS = frozenset({'tecnico', 'supervisor', 'admin_eam'})
# No es un rol: la persona cuya ficha de Personal tiene asignado el reclamo
EJECUTOR = frozenset({'asignado'})
MENSAJE_OTRA_PERSONA = 'Este reclamo está asignado a otra persona: lo inicia y lo termina quien lo tiene asignado.'

# (desde, hacia) -> roles que pueden hacerlo.
# El técnico ejecuta y envía a validación; el supervisor asigna, valida,
# devuelve o rechaza (segregación de funciones: nadie valida su propio trabajo).
TRANSICIONES = {
    ('ABIERTO', 'ASIGNADO'): SUPERVISION,
    ('ASIGNADO', 'ABIERTO'): SUPERVISION,
    # Iniciar y terminar el trabajo lo hace la persona asignada, sea cual sea su
    # rol (un supervisor también puede salir al campo). Así hay foto del antes
    # y del después; finalizar exige haber iniciado.
    ('ABIERTO', 'EN_PROCESO'): EJECUTOR,
    ('ASIGNADO', 'EN_PROCESO'): EJECUTOR,
    ('EN_PROCESO', 'PENDIENTE_VALIDACION'): EJECUTOR,
    ('PENDIENTE_VALIDACION', 'CERRADO'): SUPERVISION,
    ('PENDIENTE_VALIDACION', 'EN_PROCESO'): SUPERVISION,   # devolver al técnico
    **{(desde, 'RECHAZADO'): SUPERVISION for desde in (*ESTADOS_ACTIVOS, 'PENDIENTE_VALIDACION')},
    # Reabrir un reclamo terminado es una corrección excepcional
    **{(desde, hacia): frozenset({'admin_eam'})
       for desde in ESTADOS_FINALES for hacia in ('ABIERTO', 'EN_PROCESO')},
}

# Cambios que exigen dejar escrito el porqué
REQUIEREN_MOTIVO = {
    ('PENDIENTE_VALIDACION', 'EN_PROCESO'): 'Indicá qué tiene que corregir el técnico.',
    **{(desde, 'RECHAZADO'): 'Indicá el motivo del rechazo.'
       for desde in (*ESTADOS_ACTIVOS, 'PENDIENTE_VALIDACION')},
    **{(desde, hacia): 'Indicá por qué se reabre el reclamo.'
       for desde in ESTADOS_FINALES for hacia in ('ABIERTO', 'EN_PROCESO')},
}

# Qué campos puede escribir cada rol (lo demás lo completa el sistema)
CAMPOS_TECNICO = frozenset({
    'estado', 'resultado', 'observaciones_cierre', 'foto_evidencia_antes', 'foto_evidencia_despues',
    'ubicacion_evidencia', 'precision_evidencia_m',
})
# La descripción viene del campo (verificación o carga manual): el supervisor
# agrega información con un comentario, que queda en el historial
CAMPOS_SUPERVISOR = frozenset({
    'estado', 'prioridad', 'agencia_responsable', 'responsable_asignado', 'requiere_intervencion',
    'tipo_reclamo', 'resultado',
})
# El origen (qué verificación lo generó) y la evidencia del técnico solo los
# corrige admin EAM; el supervisor no reescribe lo que viene del campo.
CAMPOS_ADMIN_EAM = CAMPOS_SUPERVISOR | {
    'descripcion', 'id_reclamo', 'verificacion', 'componente', 'verificacion_etc', 'equipo_etc', 'origen_reclamo',
    'foto_evidencia_antes', 'foto_evidencia_despues', 'observaciones_cierre',
}
# Plazo para resolver según la prioridad, contado desde que se crea el reclamo.
# Valores propuestos: ajustarlos con lo que defina ANDE.
PLAZOS = {
    'CRITICA': timedelta(hours=24),
    'ALTA': timedelta(hours=72),
    'MEDIA': timedelta(days=7),
    'BAJA': timedelta(days=30),
}
ORDEN_PRIORIDAD = {'BAJA': 1, 'MEDIA': 2, 'ALTA': 3, 'CRITICA': 4}


def calcular_fecha_limite(desde, prioridad):
    return desde + PLAZOS.get(prioridad or 'MEDIA', PLAZOS['MEDIA'])


# Los completa el sistema según la transición (no se muestran como "dato cambiado")
CAMPOS_DEL_SISTEMA = frozenset({
    'fecha_limite', 'fecha_asignacion', 'fecha_inicio', 'fecha_ejecucion', 'fecha_cierre',
    'fecha_validacion', 'validado_por', 'motivo_rechazo',
    'ubicacion_evidencia', 'precision_evidencia_m', 'distancia_evidencia_m',
})
CAMPOS_POR_ROL = {'tecnico': CAMPOS_TECNICO, 'supervisor': CAMPOS_SUPERVISOR, 'admin_eam': CAMPOS_ADMIN_EAM}


class ReglaReclamo(Exception):
    """Un cambio que las reglas no permiten. `permiso=True` -> 403; si no, 400."""

    def __init__(self, mensaje, campo=None, permiso=False):
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.campo = campo
        self.permiso = permiso


@dataclass
class Plan:
    """Lo que va a cambiar, ya validado."""
    valores: dict = field(default_factory=dict)
    estado_anterior: str = ''
    estado_nuevo: str = ''
    detalle: list = field(default_factory=list)
    comentario: str = ''

    @property
    def vacio(self):
        return not self.valores and self.estado_anterior == self.estado_nuevo and not self.comentario


def rol_de(usuario):
    if usuario is None or not usuario.is_authenticated:
        return None
    if usuario.es_admin_eam:
        return 'admin_eam'
    if usuario.es_supervisor:
        return 'supervisor'
    if usuario.es_tecnico:
        return 'tecnico'
    return None


def nombre_de(usuario):
    if usuario is None:
        return 'Sistema'
    return usuario.get_full_name() or usuario.username


def estados_posibles(reclamo, usuario):
    """Estados a los que este usuario puede llevar el reclamo (incluye el actual)."""
    rol = rol_de(usuario)
    return [reclamo.estado] + [
        hacia for (desde, hacia), roles in TRANSICIONES.items()
        if desde == reclamo.estado and rol in roles
    ]


def _nombre_campo(campo):
    return str(Reclamo._meta.get_field(campo).verbose_name)


def _texto(valor):
    if valor in (None, '', False) or (isinstance(valor, FieldFile) and not valor):
        return '—'
    if valor is True:
        return 'Sí'
    return str(valor)


def _distinto(actual, nuevo):
    if isinstance(actual, FieldFile):
        # Un archivo nuevo siempre es un cambio; None/False = quitarlo
        return bool(nuevo) or bool(actual)
    return actual != nuevo


def planificar(reclamo, usuario, cambios, comentario=''):
    """
    Valida un cambio sin guardarlo. `reclamo` es el estado actual (tal como
    está en la base) y `cambios` un dict campo -> valor nuevo.
    Devuelve un Plan o lanza ReglaReclamo.
    """
    rol = rol_de(usuario)
    if rol is None:
        raise ReglaReclamo('Tu rol solo permite consultar reclamos.', permiso=True)

    comentario = (comentario or '').strip()
    cambios = {c: v for c, v in cambios.items() if _distinto(getattr(reclamo, c), v)}
    asignado = es_la_persona_asignada(reclamo, usuario)
    # Quien tiene asignado el reclamo carga su evidencia, aunque sea supervisor
    no_permitidos = set(cambios) - (CAMPOS_POR_ROL[rol] | (CAMPOS_TECNICO if asignado else frozenset()))
    if no_permitidos and no_permitidos <= CAMPOS_TECNICO:
        # Evidencia del trabajo cargada por alguien que no lo tiene asignado
        raise ReglaReclamo(MENSAJE_OTRA_PERSONA, permiso=True)
    if no_permitidos:
        nombres = ', '.join(sorted(_nombre_campo(c) for c in no_permitidos))
        raise ReglaReclamo(f'No podés modificar: {nombres}.', permiso=True)

    actual = reclamo.estado
    plan = Plan(valores=dict(cambios), estado_anterior=actual, estado_nuevo=actual, comentario=comentario)
    destino = plan.valores.pop('estado', None)
    if 'ubicacion_evidencia' in plan.valores and destino != 'PENDIENTE_VALIDACION':
        raise ReglaReclamo('La ubicación se envía junto con la evidencia del trabajo terminado.',
                           campo='ubicacion_evidencia')

    if actual in ESTADOS_FINALES and plan.valores:
        raise ReglaReclamo('El reclamo ya está terminado y no se modifica. '
                           'Si hace falta, admin EAM puede reabrirlo.', permiso=True)
    if rol == 'tecnico' and actual == 'PENDIENTE_VALIDACION':
        raise ReglaReclamo('Ya lo enviaste a validación: esperá la respuesta del supervisor.', permiso=True)

    ahora = timezone.now()
    estado = actual

    # --- Asignación (agencia y técnico) ---
    if 'agencia_responsable' in plan.valores or 'responsable_asignado' in plan.valores:
        if actual == 'PENDIENTE_VALIDACION':
            raise ReglaReclamo('Está esperando validación: validalo o devolvelo antes de reasignarlo.',
                               campo='responsable_asignado')
        estado = _validar_asignacion(reclamo, usuario, rol, plan, estado, ahora)

    # --- Cambio de estado pedido explícitamente ---
    if destino is not None and destino != estado:
        _validar_transicion(reclamo, usuario, rol, asignado, plan, estado, destino, comentario, ahora)
        estado = destino

    if 'prioridad' in plan.valores:
        # El plazo se recalcula desde la creación del reclamo
        plan.valores['fecha_limite'] = calcular_fecha_limite(reclamo.fecha_reclamo, plan.valores['prioridad'])

    plan.estado_nuevo = estado
    plan.detalle = [
        f'{_nombre_campo(c)}: se cargó una foto' if isinstance(getattr(reclamo, c), FieldFile)
        else f'{_nombre_campo(c)}: {_texto(getattr(reclamo, c))} → {_texto(v)}'
        for c, v in plan.valores.items() if c not in CAMPOS_DEL_SISTEMA
    ]
    if estado == 'PENDIENTE_VALIDACION' and actual != estado:
        if plan.valores.get('ubicacion_evidencia') is None:
            plan.detalle.append('Ubicación: el celular no informó GPS.')
        elif plan.valores.get('distancia_evidencia_m') is None:
            plan.detalle.append('Ubicación registrada (el equipo no tiene coordenadas para comparar).')
        else:
            precision = plan.valores.get('precision_evidencia_m')
            plan.detalle.append(f'Ubicación: {geo.texto_distancia(plan.valores["distancia_evidencia_m"])} del equipo'
                                + (f', GPS ±{precision} m.' if precision is not None else '.'))
    return plan


def _validar_asignacion(reclamo, usuario, rol, plan, estado, ahora):
    valores = plan.valores
    agencia = valores.get('agencia_responsable', reclamo.agencia_responsable)
    responsable = valores.get('responsable_asignado', reclamo.responsable_asignado)

    if responsable is not None and 'responsable_asignado' in valores:
        if not responsable.activo:
            raise ReglaReclamo(f'{responsable.nombre_completo} está dado de baja.', campo='responsable_asignado')
        if agencia is None and responsable.agencia is not None:
            # Sin agencia todavía: toma la del técnico asignado
            agencia = valores['agencia_responsable'] = responsable.agencia
        elif agencia is not None and responsable.agencia_id != agencia.id and rol != 'admin_eam':
            otra = responsable.agencia or 'sin agencia'
            raise ReglaReclamo(f'{responsable.nombre_completo} es de otra agencia ({otra}).',
                               campo='responsable_asignado')

    if rol == 'supervisor':
        mias = agencias_del_usuario(usuario)
        if 'agencia_responsable' in valores:
            if agencia is None:
                raise ReglaReclamo('Elegí la agencia responsable.', campo='agencia_responsable')
            if agencia.id not in mias:
                raise ReglaReclamo(f'No tenés asignada la agencia {agencia}.', campo='agencia_responsable')
        if responsable is not None and 'responsable_asignado' in valores and responsable.agencia_id not in mias:
            raise ReglaReclamo(f'{responsable.nombre_completo} no pertenece a tus agencias.',
                               campo='responsable_asignado')

    # El estado acompaña a la asignación
    if 'responsable_asignado' in valores:
        if responsable is None:
            if estado in ('ASIGNADO', 'EN_PROCESO'):
                estado = 'ABIERTO'
        else:
            valores['fecha_asignacion'] = ahora
            if estado in ('ABIERTO', 'EN_PROCESO'):
                # Técnico nuevo: arranca desde "asignado"
                estado = 'ASIGNADO'
    return estado


def distancia_al_equipo(reclamo, punto):
    """Metros entre el punto y el equipo del reclamo (None si el equipo no tiene ubicación)."""
    if reclamo.equipo_etc_id:
        return geo.distancia_m(EquipoETC.objects.filter(pk=reclamo.equipo_etc_id), 'ubicacion', punto)
    if reclamo.componente_id:
        return geo.distancia_m(Sitio.objects.filter(componentes__id=reclamo.componente_id), 'ubicacion_base', punto)
    return None


def es_la_persona_asignada(reclamo, usuario):
    personal = getattr(usuario, 'personal', None)
    return personal is not None and reclamo.responsable_asignado_id == personal.pk


def _validar_transicion(reclamo, usuario, rol, asignado, plan, desde, hacia, comentario, ahora):
    clave = (desde, hacia)
    roles = TRANSICIONES.get(clave)
    permitido = roles is not None and (rol in roles or ('asignado' in roles and asignado))
    if not permitido:
        if roles == EJECUTOR:
            raise ReglaReclamo(MENSAJE_OTRA_PERSONA, campo='estado', permiso=True)
        if hacia == 'PENDIENTE_VALIDACION' and desde in ('ABIERTO', 'ASIGNADO') and asignado:
            raise ReglaReclamo('Primero iniciá el trabajo, con la foto del estado inicial.', campo='estado')
        if rol == 'tecnico':
            raise ReglaReclamo('Un técnico solo puede iniciar el trabajo o enviarlo a validación.',
                               permiso=True)
        if roles is None:
            raise ReglaReclamo(f'No se puede pasar de «{NOMBRE_ESTADO[desde]}» a «{NOMBRE_ESTADO[hacia]}».',
                               campo='estado')
        raise ReglaReclamo('Solo admin EAM puede reabrir un reclamo terminado.', campo='estado', permiso=True)

    if clave in REQUIEREN_MOTIVO and not comentario:
        raise ReglaReclamo(REQUIEREN_MOTIVO[clave], campo='comentario')

    valores = plan.valores
    responsable = valores.get('responsable_asignado', reclamo.responsable_asignado)
    if hacia in ('ASIGNADO', 'EN_PROCESO', 'PENDIENTE_VALIDACION') and responsable is None:
        raise ReglaReclamo('Primero asigná un técnico.', campo='responsable_asignado')

    if hacia == 'CERRADO' and asignado:
        # Segregación de funciones: quien hizo el trabajo no lo aprueba
        raise ReglaReclamo('No podés validar un trabajo que hiciste vos: tiene que validarlo otro supervisor.',
                           campo='estado', permiso=True)

    if hacia == 'EN_PROCESO' and desde in ('ABIERTO', 'ASIGNADO'):
        # Iniciar: foto del estado en que encontró el equipo
        if not (valores.get('foto_evidencia_antes') or reclamo.foto_evidencia_antes):
            raise ReglaReclamo('Sacá una foto del estado inicial para iniciar el trabajo.',
                               campo='foto_evidencia_antes')
        if reclamo.fecha_inicio is None:
            valores['fecha_inicio'] = ahora
    elif hacia == 'PENDIENTE_VALIDACION':
        # Cada envío trae su foto (si fue devuelto, la anterior no alcanza)
        if not valores.get('foto_evidencia_despues'):
            raise ReglaReclamo('Adjuntá la foto del trabajo terminado para enviarlo a validación.',
                               campo='foto_evidencia_despues')
        valores['fecha_ejecucion'] = ahora   # hora del servidor, no la del celular
        # Ubicación de este envío (si el GPS no respondió, queda vacía: no se
        # arrastra la de un envío anterior)
        punto = valores.get('ubicacion_evidencia')
        valores['ubicacion_evidencia'] = punto
        valores.setdefault('precision_evidencia_m', None)
        valores['distancia_evidencia_m'] = distancia_al_equipo(reclamo, punto) if punto else None
    elif hacia == 'CERRADO':
        valores.update(validado_por=usuario, fecha_validacion=ahora, fecha_cierre=ahora)
    elif hacia == 'RECHAZADO':
        valores.update(motivo_rechazo=comentario, fecha_cierre=ahora)
    elif desde in ESTADOS_FINALES:
        valores.update(fecha_cierre=None, validado_por=None, fecha_validacion=None)


@transaction.atomic
def actualizar(reclamo, usuario, cambios, comentario=''):
    """Aplica un cambio validado y lo registra en el historial. Devuelve el reclamo actualizado."""
    # Bloqueo de fila: si dos supervisores validan a la vez, el segundo ve el estado nuevo
    actual = Reclamo.objects.select_for_update().get(pk=reclamo.pk)
    plan = planificar(actual, usuario, cambios, comentario)
    if plan.vacio:
        return actual

    for campo, valor in plan.valores.items():
        setattr(actual, campo, None if valor is False and isinstance(getattr(actual, campo), FieldFile) else valor)
    actual.estado = plan.estado_nuevo
    actual.save()

    cambio_estado = plan.estado_anterior != plan.estado_nuevo
    detalle = list(plan.detalle)
    if cambio_estado and (plan.estado_nuevo in ESTADOS_FINALES or plan.estado_anterior in ESTADOS_FINALES):
        # Terminar o reabrir el reclamo cambia cómo se ve el equipo en el mapa
        detalle.append(estado_red.por_reclamo(actual))
    registrar(
        actual, usuario,
        estado_anterior=plan.estado_anterior if cambio_estado else '',
        estado_nuevo=plan.estado_nuevo if cambio_estado else '',
        detalle='\n'.join(linea for linea in detalle if linea),
        comentario=plan.comentario,
    )
    return actual


def registrar(reclamo, usuario, estado_anterior='', estado_nuevo='', detalle='', comentario=''):
    return HistorialReclamo.objects.create(
        reclamo=reclamo,
        usuario=usuario if usuario is not None and usuario.is_authenticated else None,
        usuario_nombre=nombre_de(usuario),
        estado_anterior=estado_anterior,
        estado_nuevo=estado_nuevo,
        detalle=detalle,
        comentario=comentario,
    )


# =====================================================
# CREACIÓN
# =====================================================

def nuevo_numero_manual():
    return f"REC-MAN-{timezone.localdate():%Y%m%d}-{uuid.uuid4().hex[:6].upper()}"


def preparar_nuevo(usuario, datos):
    """Valida y completa los datos de un reclamo cargado a mano (API o admin)."""
    rol = rol_de(usuario)
    if rol not in SUPERVISION:
        raise ReglaReclamo('Solo supervisores o administradores pueden crear reclamos.', permiso=True)

    datos = {c: v for c, v in datos.items() if c in CAMPOS_ADMIN_EAM or c == 'id_reclamo'}
    datos.pop('estado', None)
    agencia = datos.get('agencia_responsable')
    responsable = datos.get('responsable_asignado')

    if responsable is not None:
        if not responsable.activo:
            raise ReglaReclamo(f'{responsable.nombre_completo} está dado de baja.', campo='responsable_asignado')
        if agencia is None:
            agencia = datos['agencia_responsable'] = responsable.agencia
    if rol == 'supervisor':
        mias = agencias_del_usuario(usuario)
        if agencia is not None and agencia.id not in mias:
            raise ReglaReclamo(f'No tenés asignada la agencia {agencia}.', campo='agencia_responsable')
        if responsable is not None and responsable.agencia_id not in mias:
            raise ReglaReclamo(f'{responsable.nombre_completo} no pertenece a tus agencias.',
                               campo='responsable_asignado')

    datos['estado'] = 'ASIGNADO' if responsable else 'ABIERTO'
    if responsable:
        datos['fecha_asignacion'] = timezone.now()
    datos.setdefault('origen_reclamo', 'MANUAL')
    if not datos.get('id_reclamo'):
        datos['id_reclamo'] = nuevo_numero_manual()
    return datos


def crear(usuario, detalle='', comentario='', **campos):
    """Crea el reclamo y deja la primera entrada del historial."""
    campos.setdefault('fecha_limite', calcular_fecha_limite(timezone.now(), campos.get('prioridad')))
    reclamo = Reclamo.objects.create(**campos)
    registrar(reclamo, usuario, estado_nuevo=reclamo.estado, detalle=detalle, comentario=comentario)
    return reclamo


# =====================================================
# RECLAMOS QUE GENERAN LAS VERIFICACIONES
# =====================================================

def registrar_falla(usuario, verificacion):
    """
    Reclamo para la falla que reportó una verificación (de ETC o de regulador).

    - Si el equipo ya tiene un reclamo sin terminar, no se crea otro: la nueva
      verificación se anota en su historial y, si trae una prioridad mayor, se la sube.
    - El reclamo nuevo nace sin técnico, en la bandeja del supervisor (quien
      verifica no suele ser la cuadrilla que repara), con la agencia del equipo
      o, si el equipo no tiene una cargada, la del técnico que lo verificó.

    Se llama dentro de la transacción que guarda la verificación.
    Devuelve (reclamo, creado).
    """
    es_etc = hasattr(verificacion, 'equipo_etc_id')
    if es_etc:
        # Bloquear el equipo: dos verificaciones simultáneas no crean dos reclamos
        equipo = EquipoETC.objects.select_for_update().get(pk=verificacion.equipo_etc_id)
        filtro = {'equipo_etc': equipo}
        agencia_equipo = equipo.sitio.agencia if equipo.sitio_id else None
        nombre_equipo = f'ETC {equipo.nro_equipo}'
        origen = {'verificacion_etc': verificacion, 'equipo_etc': equipo}
        id_reclamo = f'REC-ETC-{verificacion.id_verificacion}'
        tipo = 'ETC'
    else:
        componente = Componente.objects.select_for_update().get(pk=verificacion.componente_id)
        filtro = {'componente': componente}
        agencia_equipo = verificacion.sitio.agencia
        nombre_equipo = f'regulador {componente.id_componente}'
        origen = {'verificacion': verificacion, 'componente': componente}
        id_reclamo = f'REC-REG-{verificacion.id_verificacion}'
        tipo = 'regulador'

    prioridad = verificacion.prioridad or 'MEDIA'
    nombres_prioridad = dict(Reclamo._meta.get_field('prioridad').choices)
    existente = (Reclamo.objects.select_for_update().filter(**filtro)
                 .filter(estado__in=ESTADOS_ABIERTOS).order_by('fecha_reclamo').first())

    if existente is not None:
        lineas = [f'La verificación {verificacion.id_verificacion} volvió a reportar la falla '
                  f'(no se creó un reclamo duplicado).']
        if ORDEN_PRIORIDAD[prioridad] > ORDEN_PRIORIDAD.get(existente.prioridad or 'MEDIA', 2):
            lineas.append(f'Prioridad: {existente.get_prioridad_display() or "—"} → {nombres_prioridad[prioridad]}')
            existente.prioridad = prioridad
            existente.fecha_limite = calcular_fecha_limite(existente.fecha_reclamo, prioridad)
            existente.save(update_fields=['prioridad', 'fecha_limite'])
        if existente.estado == 'PENDIENTE_VALIDACION':
            lineas.append('Atención: el trabajo espera validación y la falla sigue presente.')
        registrar(existente, usuario, detalle='\n'.join(lineas),
                  comentario=f'Obs. de campo: {verificacion.observaciones}' if verificacion.observaciones else '')
        return existente, False

    agencia = agencia_equipo or verificacion.agencia_responsable
    lineas = [f'Generado por la verificación de {tipo} {verificacion.id_verificacion}.']
    obligatorio = getattr(verificacion, '_reclamo_obligatorio', None)
    if obligatorio:
        lineas.append(f'Reclamo obligatorio por {obligatorio} (prioridad alta como mínimo).')
    if agencia_equipo is None and agencia is not None:
        lineas.append(f'El equipo no tiene agencia cargada: se tomó la del técnico ({agencia}).')
    reclamo = crear(
        usuario,
        detalle='\n'.join(lineas),
        id_reclamo=id_reclamo,
        descripcion=f'Falla reportada en {nombre_equipo}. Obs: {verificacion.observaciones}',
        prioridad=prioridad,
        estado='ABIERTO',
        origen_reclamo='VERIFICACION',
        agencia_responsable=agencia,
        **origen,
    )
    return reclamo, True
