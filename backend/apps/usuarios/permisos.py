"""
SIGVER - Permisos y alcance por rol (RBAC)
"""
from django.db.models import Q
from rest_framework.permissions import SAFE_METHODS, BasePermission


class SoloLecturaParaConsulta(BasePermission):
    """El rol 'consulta' solo puede leer; el resto de los roles puede escribir."""
    message = 'Tu rol solo permite consultar información.'

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        if request.method in SAFE_METHODS:
            return True
        return user.is_superuser or user.rol != 'consulta'


def agencias_del_usuario(user):
    """
    IDs de agencias que el usuario puede ver (asignadas + la de su ficha de Personal),
    o None si no tiene ninguna: opera todo el departamento. Es el caso de los jefes
    del Departamento de Operación de Distribución, que atienden las tres regionales.
    """
    ids = set(user.agencias_asignadas.values_list('id', flat=True))
    personal = getattr(user, 'personal', None)
    if personal is not None and personal.agencia_id:
        ids.add(personal.agencia_id)
    return ids or None


def filtrar_reclamos_por_rol(user, qs):
    """
    - admin_eam / superusuario / consulta: todos los reclamos.
    - supervisor_zona: los de sus agencias y los que todavía no tienen agencia
      (bandeja de entrada: el supervisor les asigna la que corresponda).
      Sin agencias asignadas: todos (opera todo el departamento).
    - tecnico_campo: solo los asignados a él.
    """
    if user.es_admin_eam or user.rol == 'consulta':
        return qs
    if user.es_supervisor:
        mias = agencias_del_usuario(user)
        if mias is None:
            return qs
        return qs.filter(Q(agencia_responsable_id__in=mias) | Q(agencia_responsable__isnull=True))

    filtro = Q(pk__in=[])
    personal = getattr(user, 'personal', None)
    if personal is not None:
        filtro = Q(responsable_asignado=personal)
    return qs.filter(filtro)


def filtrar_verificaciones_por_rol(user, qs, prefijo=''):
    """
    - admin_eam / superusuario / consulta: todas.
    - supervisor_zona: las de sus agencias (y las que no tienen agencia).
    - tecnico_campo: solo las propias.
    `prefijo` permite filtrar modelos hijos (p. ej. 'verificacion__' para mediciones).
    """
    if user.es_admin_eam or user.rol == 'consulta':
        return qs
    if user.es_supervisor:
        mias = agencias_del_usuario(user)
        if mias is None:
            return qs
        return qs.filter(
            Q(**{f'{prefijo}agencia_responsable_id__in': mias})
            | Q(**{f'{prefijo}agencia_responsable__isnull': True})
        )
    personal = getattr(user, 'personal', None)
    if personal is None:
        return qs.none()
    return qs.filter(**{f'{prefijo}responsable': personal})


def filtrar_personal_por_rol(user, qs):
    """Personal visible: todo para admin/consulta, el de sus agencias para el supervisor, uno mismo para el técnico."""
    if user.es_admin_eam or user.rol == 'consulta':
        return qs
    if user.es_supervisor:
        mias = agencias_del_usuario(user)
        if mias is None:
            return qs
        return qs.filter(Q(agencia_id__in=mias) | Q(agencia__isnull=True))
    personal = getattr(user, 'personal', None)
    return qs.filter(pk=personal.pk) if personal is not None else qs.none()


# =====================================================
# ADMIN DE DJANGO: grupo de supervisores e inmutabilidad
# =====================================================

GRUPO_SUPERVISORES = 'Supervisores de zona'

# Roles que entran al admin (se les activa is_staff automáticamente)
ROLES_CON_ADMIN = ('supervisor_zona', 'admin_eam')

# Permisos del grupo: (app, modelo) -> acciones.
# Lo que no figura acá (usuarios, grupos, catálogos de configuración como subestaciones,
# alimentadores o tipos de falla) no aparece en su menú.
PERMISOS_SUPERVISOR = {
    # Operación: gestiona reclamos; las verificaciones son evidencia y solo se consultan
    # (mediciones, ensayos y lecturas se muestran dentro de la verificación)
    ('operaciones', 'reclamo'): ('view', 'change'),
    ('operaciones', 'historialreclamo'): ('view',),   # se ve dentro del reclamo
    ('operaciones', 'verificacion'): ('view',),
    ('operaciones', 'verificacionetc'): ('view',),
    ('operaciones', 'mediciontermografia'): ('view',),
    ('operaciones', 'ensayopat'): ('view',),
    ('operaciones', 'lecturapat'): ('view',),
    # Inventario: corrige datos maestros de la red y del personal
    ('inventario', 'sitio'): ('view', 'change'),
    ('inventario', 'equipoetc'): ('view', 'change'),
    ('inventario', 'componente'): ('view', 'change'),
    ('inventario', 'elementoequipo'): ('view', 'change'),
    ('inventario', 'personal'): ('view', 'change'),
    ('inventario', 'agencia'): ('view',),
}


def configurar_grupo_supervisores(**kwargs):
    """
    Crea o actualiza el grupo de supervisores con exactamente los permisos de
    PERMISOS_SUPERVISOR. Se ejecuta en cada `migrate` (señal post_migrate), así
    cualquier instalación nueva queda igual y un cambio en la tabla se aplica solo.
    """
    from django.contrib.auth.models import Group, Permission

    grupo, _ = Group.objects.get_or_create(name=GRUPO_SUPERVISORES)
    permisos = []
    for (app, modelo), acciones in PERMISOS_SUPERVISOR.items():
        codenames = [f'{accion}_{modelo}' for accion in acciones]
        permisos += Permission.objects.filter(content_type__app_label=app, codename__in=codenames)
    grupo.permissions.set(permisos)
    return grupo


class InmutableSalvoAdminEAM:
    """
    Mixin para ModelAdmin e inlines de registros de campo (verificaciones y sus
    mediciones). Son la evidencia de lo que se hizo en el sitio: nadie los
    modifica ni borra desde el admin, salvo admin_eam para corregir errores
    (y esos cambios quedan en el historial del admin).
    En la API ya no se pueden editar: solo se crean desde la PWA.
    """

    def has_add_permission(self, request, *args):
        return request.user.es_admin_eam and super().has_add_permission(request, *args)

    def has_change_permission(self, request, obj=None):
        return request.user.es_admin_eam and super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        return request.user.es_admin_eam and super().has_delete_permission(request, obj)
