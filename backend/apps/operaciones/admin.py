"""
SIGVER - Admin de Operaciones
"""
from django import forms
from django.contrib import admin, messages
from django.contrib.gis.admin import GISModelAdmin
from django.db.models import Q
from django.core.exceptions import PermissionDenied
from django.template.response import TemplateResponse
from django.urls import path
from django.utils.html import format_html, format_html_join
from django.urls import reverse
from django.utils import timezone

from apps.inventario.models import Agencia, Personal
from apps.usuarios.permisos import InmutableSalvoAdminEAM, agencias_del_usuario, filtrar_reclamos_por_rol

from . import indicadores, reclamos
from .models import (
    TipoFallaETC, Verificacion, VerificacionETC,
    PuntoInspeccionTermografia, MedicionTermografia,
    EnsayoPAT, LecturaPAT, Reclamo, HistorialReclamo,
)


# =====================================================
# PIEZAS VISUALES (estilos en static/sigver_admin/admin.css)
# =====================================================

def etiqueta(valor, texto, grupo):
    """Etiqueta de color: grupo 'estado', 'prioridad' o 'sitio' + el valor del campo."""
    if not valor:
        return '—'
    return format_html('<span class="sg-badge sg-{}-{}">{}</span>', grupo, valor.lower(), texto)


def galeria(*fotos):
    """Miniaturas clicables de las fotos cargadas (las vacías se omiten)."""
    items = [(titulo, f) for titulo, f in fotos if f]
    if not items:
        return format_html('<span class="sg-muted">{}</span>', 'Sin fotos')
    miniaturas = format_html_join(
        '', '<a class="sg-foto" href="{0}" target="_blank" rel="noopener">'
            '<img src="{0}" alt="{1}" loading="lazy"><span>{1}</span></a>',
        ((f.url, titulo) for titulo, f in items),
    )
    return format_html('<div class="sg-galeria">{}</div>', miniaturas)


def enlace_pdf(tipo, obj, texto='PDF'):
    url = reverse('generar_pdf', args=[tipo, obj.pk])
    return format_html('<a class="sg-btn-pdf" href="{}" target="_blank" rel="noopener">'
                       '<i class="fas fa-file-pdf"></i> {}</a>', url, texto)


@admin.register(TipoFallaETC)
class TipoFallaETCAdmin(admin.ModelAdmin):
    list_display = ('codigo', 'numero', 'descripcion', 'gravedad', 'activo')
    list_filter = ('gravedad', 'activo')
    search_fields = ('codigo', 'descripcion')
    ordering = ('numero',)


class MedicionTermografiaInline(InmutableSalvoAdminEAM, admin.TabularInline):
    model = MedicionTermografia
    extra = 0
    fields = ('id_medicion', 'punto', 'fecha_hora', 'temperatura_punto_c', 'nivel_termografico')
    readonly_fields = ('id_medicion',)
    can_delete = False


class EnsayoPATInline(InmutableSalvoAdminEAM, admin.TabularInline):
    model = EnsayoPAT
    extra = 0
    fields = ('id_ensayo', 'fecha_ensayo', 'metodo_pat', 'resultado')
    readonly_fields = ('id_ensayo',)
    can_delete = False
    show_change_link = True  # las lecturas se ven dentro del ensayo


@admin.register(Verificacion)
class VerificacionAdmin(InmutableSalvoAdminEAM, GISModelAdmin):
    list_display = ('id_verificacion', 'sitio', 'fecha_verificacion', 'responsable',
                    'estado', 'requiere_reclamo', 'informe')
    list_filter = ('estado_sitio', 'requiere_reclamo', 'agencia_responsable', 'responsable',
                   'tipo_banco_verificado', 'tipo_control_verificado')
    list_select_related = ('sitio', 'componente', 'responsable')
    search_fields = ('id_verificacion', 'sitio__id_sitio', 'componente__id_componente',
                     'responsable__nombre_completo')
    date_hierarchy = 'fecha_verificacion'
    list_per_page = 25
    inlines = [MedicionTermografiaInline, EnsayoPATInline]
    readonly_fields = ('synced_at', 'boton_pdf', 'fotos')
    fieldsets = (
        ('Identificación', {'fields': ('id_verificacion', 'sitio', 'componente', 'fecha_verificacion',
                                       'responsable', 'agencia_responsable', 'boton_pdf')}),
        ('Estado del sitio', {'fields': ('estado_sitio', 'tipo_control_verificado', 'tipo_banco_verificado',
                                         'valla_perimetral', 'es_hibrido', 'configuracion_observada',
                                         'observaciones_control_unico', 'observaciones')}),
        ('Fotos', {'fields': ('fotos', 'foto_frontal', 'foto_entorno', 'foto_control_unico')}),
        ('Ubicación GPS', {'fields': ('ubicacion_coincide', 'ubicacion_capturada')}),
        ('Reclamo', {'fields': ('requiere_reclamo', 'prioridad')}),
        ('Registro', {'fields': ('client_uuid', 'synced_at')}),
    )

    @admin.display(description='Estado', ordering='estado_sitio')
    def estado(self, obj):
        return etiqueta(obj.estado_sitio, obj.get_estado_sitio_display(), 'sitio')

    @admin.display(description='Informe')
    def informe(self, obj):
        return enlace_pdf('regulador', obj)

    @admin.display(description='Fotos de campo')
    def fotos(self, obj):
        return galeria(('Frontal', obj.foto_frontal), ('Entorno', obj.foto_entorno),
                       ('Control', obj.foto_control_unico))

    @admin.display(description='Informe')
    def boton_pdf(self, obj):
        if obj.pk:
            return enlace_pdf('regulador', obj, 'Descargar informe PDF')
        return 'Se genera al guardar la verificación.'


@admin.register(VerificacionETC)
class VerificacionETCAdmin(InmutableSalvoAdminEAM, GISModelAdmin):
    list_display = ('id_verificacion', 'equipo_etc', 'fecha_verificacion', 'responsable',
                    'resultado', 'informe')
    list_filter = ('tiene_inconveniente', 'requiere_reclamo', 'agencia_responsable', 'responsable')
    list_select_related = ('equipo_etc', 'responsable')
    search_fields = ('id_verificacion', 'equipo_etc__nro_equipo', 'responsable__nombre_completo')
    date_hierarchy = 'fecha_verificacion'
    list_per_page = 25
    readonly_fields = ('synced_at', 'boton_pdf', 'vista_foto')
    fieldsets = (
        ('Identificación', {'fields': ('id_verificacion', 'equipo_etc', 'fecha_verificacion',
                                       'responsable', 'agencia_responsable', 'boton_pdf')}),
        ('Resultado', {'fields': ('tiene_inconveniente', 'fallas', 'observaciones',
                                  'requiere_reclamo', 'prioridad')}),
        ('Foto', {'fields': ('vista_foto', 'foto')}),
        ('Ubicación GPS', {'fields': ('ubicacion_coincide', 'ubicacion_capturada')}),
        ('Registro', {'fields': ('client_uuid', 'synced_at')}),
    )

    @admin.display(description='Resultado', ordering='tiene_inconveniente')
    def resultado(self, obj):
        if obj.tiene_inconveniente:
            return etiqueta('critico', 'Con inconveniente', 'sitio')
        return etiqueta('normal', 'Sin novedad', 'sitio')

    @admin.display(description='Informe')
    def informe(self, obj):
        return enlace_pdf('etc', obj)

    @admin.display(description='Foto de campo')
    def vista_foto(self, obj):
        return galeria(('Equipo', obj.foto))

    @admin.display(description='Informe')
    def boton_pdf(self, obj):
        if obj.pk:
            return enlace_pdf('etc', obj, 'Descargar informe PDF')
        return 'Se genera al guardar la verificación.'


@admin.register(PuntoInspeccionTermografia)
class PuntoInspeccionTermografiaAdmin(admin.ModelAdmin):
    list_display = ('id_punto', 'fase', 'tipo_elemento', 'lado_conexion', 'activo')
    list_filter = ('fase', 'tipo_elemento', 'lado_conexion', 'activo')
    search_fields = ('id_punto',)


@admin.register(MedicionTermografia)
class MedicionTermografiaAdmin(InmutableSalvoAdminEAM, admin.ModelAdmin):
    list_display = ('id_medicion', 'componente', 'punto', 'fecha_hora', 'temperatura_punto_c', 'nivel_termografico')
    list_filter = ('nivel_termografico', 'fecha_hora')
    search_fields = ('id_medicion', 'componente__id_componente')
    date_hierarchy = 'fecha_hora'


class LecturaPATInline(InmutableSalvoAdminEAM, admin.TabularInline):
    model = LecturaPAT
    extra = 0
    fields = ('id_lectura', 'tipo_lectura', 'distancia_m', 'valor_ohm')
    readonly_fields = ('id_lectura',)


@admin.register(EnsayoPAT)
class EnsayoPATAdmin(InmutableSalvoAdminEAM, admin.ModelAdmin):
    list_display = ('id_ensayo', 'componente', 'fecha_ensayo', 'metodo_pat', 'resultado', 'condicion_suelo')
    list_filter = ('resultado', 'condicion_suelo', 'metodo_pat')
    search_fields = ('id_ensayo', 'componente__id_componente')
    date_hierarchy = 'fecha_ensayo'
    inlines = [LecturaPATInline]


@admin.register(LecturaPAT)
class LecturaPATAdmin(InmutableSalvoAdminEAM, admin.ModelAdmin):
    list_display = ('id_lectura', 'ensayo', 'tipo_lectura', 'distancia_m', 'valor_ohm')
    list_filter = ('tipo_lectura',)
    search_fields = ('id_lectura', 'ensayo__id_ensayo')


def texto_duracion(delta):
    """'3 d', '5 h' o '20 min': lo justo para leer de un vistazo."""
    segundos = int(delta.total_seconds())
    if segundos >= 86400:
        return f'{segundos // 86400} d'
    if segundos >= 3600:
        return f'{segundos // 3600} h'
    return f'{max(segundos // 60, 1)} min'


class BandejaReclamosFilter(admin.SimpleListFilter):
    """Colas de trabajo del supervisor (las mismas que muestra el inicio del admin)."""
    title = 'bandeja de trabajo'
    parameter_name = 'bandeja'
    ESTADOS_ACTIVOS = ('ABIERTO', 'ASIGNADO', 'EN_PROCESO')

    def lookups(self, request, model_admin):
        return (
            ('validar', 'Pendientes de validación'),
            ('vencidos', 'Vencidos (fuera de plazo)'),
            ('sin_agencia', 'Sin agencia'),
            ('sin_tecnico', 'Sin técnico asignado'),
            ('activos', 'Activos (abiertos y en proceso)'),
        )

    def queryset(self, request, queryset):
        return filtrar_bandeja(queryset, self.value())


def filtrar_bandeja(qs, bandeja):
    activos = BandejaReclamosFilter.ESTADOS_ACTIVOS
    if bandeja == 'validar':
        return qs.filter(estado='PENDIENTE_VALIDACION')
    if bandeja == 'vencidos':
        return qs.filter(estado__in=activos, fecha_limite__lt=timezone.now())
    if bandeja == 'sin_agencia':
        return qs.filter(agencia_responsable__isnull=True, estado__in=activos)
    if bandeja == 'sin_tecnico':
        return qs.filter(responsable_asignado__isnull=True, estado__in=activos)
    if bandeja == 'activos':
        return qs.filter(estado__in=activos)
    return qs


class ReclamoAdminForm(forms.ModelForm):
    """
    Valida con las mismas reglas que la API (apps/operaciones/reclamos.py), así
    el error aparece en el formulario en lugar de guardarse algo incoherente.
    """
    usuario = None   # lo fija ReclamoAdmin con el usuario del pedido

    comentario = forms.CharField(
        label='Comentario o motivo', required=False,
        widget=forms.Textarea(attrs={'rows': 2}),
        help_text='Queda en el historial. Obligatorio para devolver al técnico, rechazar o reabrir.',
    )

    class Meta:
        model = Reclamo
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if 'estado' in self.fields:
            # Solo los estados a los que este usuario puede llevarlo desde el actual
            if self.instance.pk:
                posibles = reclamos.estados_posibles(self.instance, self.usuario)
            else:
                posibles = ['ABIERTO']
            self.fields['estado'].choices = [(v, t) for v, t in Reclamo.ESTADO if v in posibles]

    def cambios(self):
        campos_modelo = {f.name for f in Reclamo._meta.fields}
        return {c: self.cleaned_data[c] for c in self.changed_data
                if c in campos_modelo and c in self.cleaned_data}

    def clean(self):
        datos = super().clean()
        if self.instance.pk:
            try:
                reclamos.planificar(self.instance, self.usuario, self.cambios(), datos.get('comentario', ''))
            except reclamos.ReglaReclamo as e:
                self.add_error(e.campo if e.campo in self.fields else None, e.mensaje)
        return datos


class HistorialReclamoInline(admin.TabularInline):
    """Línea de tiempo del reclamo. Solo lectura: el historial no se edita."""
    model = HistorialReclamo
    extra = 0
    can_delete = False
    ordering = ('fecha', 'id')
    fields = readonly_fields = ('fecha', 'quien', 'cambio', 'detalle_y_comentario')
    verbose_name = 'movimiento'
    verbose_name_plural = 'Historial (quién hizo qué y cuándo)'

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    @admin.display(description='Usuario')
    def quien(self, obj):
        return obj.usuario_nombre or '—'

    @admin.display(description='Cambio de estado')
    def cambio(self, obj):
        if not obj.estado_nuevo:
            return '—'
        if not obj.estado_anterior:
            return etiqueta(obj.estado_nuevo, obj.get_estado_nuevo_display(), 'estado')
        return format_html('{} <span class="sg-muted">→</span> {}',
                           etiqueta(obj.estado_anterior, obj.get_estado_anterior_display(), 'estado'),
                           etiqueta(obj.estado_nuevo, obj.get_estado_nuevo_display(), 'estado'))

    @admin.display(description='Detalle')
    def detalle_y_comentario(self, obj):
        # <span> y no <div>: el admin envuelve los campos de solo lectura en un <p>
        partes = format_html_join('', '<span class="sg-historial-linea">{}</span>',
                                  ((linea,) for linea in obj.detalle.splitlines() if linea))
        if obj.comentario:
            partes = format_html('{}<span class="sg-historial-linea sg-historial-comentario">«{}»</span>',
                                 partes, obj.comentario)
        return partes or '—'


@admin.register(Reclamo)
class ReclamoAdmin(admin.ModelAdmin):
    form = ReclamoAdminForm
    inlines = (HistorialReclamoInline,)
    list_display = ('id_reclamo', 'equipo', 'estado_badge', 'prioridad_badge', 'plazo',
                    'agencia_responsable', 'responsable_asignado', 'tiene_evidencia')
    # Asignar agencia y técnico desde la lista, sin abrir cada reclamo
    list_editable = ('agencia_responsable', 'responsable_asignado')
    list_filter = (BandejaReclamosFilter, 'estado', 'prioridad', 'origen_reclamo',
                   'agencia_responsable', 'fecha_reclamo')
    list_select_related = ('componente', 'equipo_etc', 'agencia_responsable', 'responsable_asignado')
    search_fields = ('id_reclamo', 'descripcion', 'componente__id_componente', 'equipo_etc__nro_equipo')
    autocomplete_fields = ('componente', 'verificacion', 'equipo_etc', 'verificacion_etc')
    list_per_page = 25
    # La evidencia la carga el técnico desde la PWA y las fechas las pone el sistema:
    # el supervisor las ve, no las edita
    readonly_fields = ('fecha_reclamo', 'observaciones_cierre', 'foto_evidencia_despues',
                       'vista_fotos', 'vista_ubicacion', 'fecha_inicio', 'fecha_asignacion', 'fecha_ejecucion', 'fecha_cierre',
                       'validado_por', 'fecha_validacion', 'motivo_rechazo', 'fecha_limite')
    actions = ('validar_y_cerrar',)
    fieldsets = (
        ('Evidencia del técnico (para validar)', {
            'fields': ('vista_fotos', 'vista_ubicacion', 'observaciones_cierre'),
            'description': 'Revisá las fotos, la ubicación y la observación. Para aprobar, pasá el estado a '
                           '«Cerrado»; para pedir una corrección, a «En proceso» con un comentario.',
        }),
        ('Gestión', {
            'fields': ('estado', 'comentario', 'prioridad', 'agencia_responsable', 'responsable_asignado',
                       'requiere_intervencion'),
            'description': 'Al asignar un técnico el reclamo pasa solo a «Asignado».',
        }),
        ('Reclamo', {
            'fields': ('id_reclamo', 'descripcion', 'tipo_reclamo', 'origen_reclamo', 'fecha_reclamo',
                       'equipo_etc', 'verificacion_etc', 'componente', 'verificacion')
        }),
        ('Fechas y validación', {
            'fields': ('fecha_limite', 'fecha_asignacion', 'fecha_inicio', 'fecha_ejecucion', 'fecha_validacion',
                       'validado_por', 'fecha_cierre'),
            'description': 'El plazo depende de la prioridad: crítica 24 h, alta 72 h, media 7 días, baja 30 días.',
        }),
        ('Resolución', {
            'fields': ('resultado', 'motivo_rechazo', 'foto_evidencia_antes')
        }),
    )

    def get_fieldsets(self, request, obj=None):
        # La evidencia va primero solo cuando hay algo que validar
        fieldsets = super().get_fieldsets(request, obj)
        if obj is None or not (obj.foto_evidencia_despues or obj.observaciones_cierre):
            fieldsets = fieldsets[1:] + fieldsets[:1]
        return fieldsets

    # --- Indicadores ---
    def get_urls(self):
        propias = [path('indicadores/', self.admin_site.admin_view(self.vista_indicadores),
                        name='operaciones_reclamo_indicadores')]
        return propias + super().get_urls()

    def vista_indicadores(self, request):
        if not self.has_view_permission(request):
            raise PermissionDenied
        base = filtrar_reclamos_por_rol(request.user, Reclamo.objects.all())
        contexto = {
            **self.admin_site.each_context(request),
            'title': 'Indicadores de reclamos',
            'opts': self.model._meta,
            'ind': indicadores.calcular(base, request.GET.get('periodo', indicadores.PERIODO_POR_DEFECTO)),
            'lista_url': 'admin:operaciones_reclamo_changelist',
        }
        return TemplateResponse(request, 'admin/operaciones/reclamo/indicadores.html', contexto)

    # --- Formularios con las reglas del servicio ---
    def _form_del_usuario(self, request):
        return type('ReclamoAdminFormUsuario', (ReclamoAdminForm,), {'usuario': request.user})

    def get_form(self, request, obj=None, **kwargs):
        kwargs['form'] = self._form_del_usuario(request)
        return super().get_form(request, obj, **kwargs)

    def get_changelist_form(self, request, **kwargs):
        kwargs['form'] = self._form_del_usuario(request)
        return super().get_changelist_form(request, **kwargs)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        # El supervisor solo ofrece agencias y técnicos de su zona (más los ya cargados,
        # para que la fila no quede inválida si admin EAM asignó a alguien de afuera)
        if not request.user.es_admin_eam and db_field.name in ('agencia_responsable', 'responsable_asignado'):
            mias = agencias_del_usuario(request.user)
            visibles = filtrar_reclamos_por_rol(request.user, Reclamo.objects.all())
            if db_field.name == 'agencia_responsable':
                kwargs['queryset'] = Agencia.objects.filter(
                    Q(id__in=mias) | Q(reclamos_responsable__in=visibles)).distinct()
            else:
                kwargs['queryset'] = Personal.objects.filter(
                    Q(activo=True, agencia_id__in=mias) | Q(reclamos_asignados__in=visibles)).distinct()
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def save_model(self, request, obj, form, change):
        comentario = form.cleaned_data.get('comentario', '')
        if change:
            # No se guarda el objeto del formulario: el cambio lo aplica el servicio
            # (vuelve a validar sobre el estado actual de la base y registra el historial)
            try:
                reclamos.actualizar(obj, request.user, form.cambios(), comentario)
            except reclamos.ReglaReclamo as e:
                # Solo si otro usuario lo cambió entre que se abrió y se guardó el formulario
                request._reclamo_sin_guardar = True
                self.message_user(request, f'No se guardó {obj.id_reclamo}: {e.mensaje}', messages.ERROR)
            return
        obj.estado = 'ASIGNADO' if obj.responsable_asignado else 'ABIERTO'
        if obj.responsable_asignado:
            obj.fecha_asignacion = timezone.now()
        obj.fecha_limite = reclamos.calcular_fecha_limite(timezone.now(), obj.prioridad)
        super().save_model(request, obj, form, change)
        reclamos.registrar(obj, request.user, estado_nuevo=obj.estado,
                           detalle='Cargado a mano desde el admin', comentario=comentario)

    def message_user(self, request, message, level=messages.INFO, *args, **kwargs):
        # Si el servicio rechazó el cambio, no mostrar además "se modificó con éxito"
        if getattr(request, '_reclamo_sin_guardar', False) and level == messages.SUCCESS:
            return
        super().message_user(request, message, level, *args, **kwargs)

    def has_delete_permission(self, request, obj=None):
        # Un reclamo no se borra: se rechaza con motivo. Solo admin EAM, para limpiar errores.
        return request.user.es_admin_eam and super().has_delete_permission(request, obj)

    # --- Columnas ---
    @admin.display(description='Equipo', ordering='componente__id_componente')
    def equipo(self, obj):
        if obj.equipo_etc:
            return f'ETC {obj.equipo_etc.nro_equipo}'
        return obj.componente.id_componente if obj.componente else '—'

    @admin.display(description='Estado', ordering='estado')
    def estado_badge(self, obj):
        return etiqueta(obj.estado, obj.get_estado_display(), 'estado')

    @admin.display(description='Prioridad', ordering='prioridad')
    def prioridad_badge(self, obj):
        return etiqueta(obj.prioridad, obj.get_prioridad_display(), 'prioridad')

    @admin.display(description='Plazo', ordering='fecha_limite')
    def plazo(self, obj):
        if obj.estado not in reclamos.ESTADOS_ACTIVOS or obj.fecha_limite is None:
            return '—'
        restante = obj.fecha_limite - timezone.now()
        if restante.total_seconds() < 0:
            return format_html('<span class="sg-badge sg-plazo-vencido">Vencido hace {}</span>',
                               texto_duracion(-restante))
        clase = 'sg-plazo-proximo' if restante.total_seconds() < 86400 else 'sg-plazo-ok'
        return format_html('<span class="sg-badge {}">Vence en {}</span>', clase, texto_duracion(restante))

    @admin.display(boolean=True, description='Evidencia')
    def tiene_evidencia(self, obj):
        return bool(obj.foto_evidencia_despues)

    @admin.display(description='Fotos del técnico')
    def vista_fotos(self, obj):
        return galeria(('Antes (al iniciar)', obj.foto_evidencia_antes),
                       ('Después (trabajo terminado)', obj.foto_evidencia_despues))

    @admin.display(description='Ubicación al enviar')
    def vista_ubicacion(self, obj):
        if obj.ubicacion_evidencia is None:
            return format_html('<span class="sg-muted">{}</span>',
                               'Sin GPS' if obj.foto_evidencia_despues else 'Todavía no se envió la evidencia')
        metros = obj.distancia_evidencia_m
        if metros is None:
            etiqueta_html = format_html('<span class="sg-badge sg-plazo-ok">{}</span>',
                                        'El equipo no tiene coordenadas')
        else:
            clase = ('sg-distancia-lugar' if metros <= reclamos.DISTANCIA_EN_EL_LUGAR_M
                     else 'sg-distancia-cerca' if metros <= reclamos.DISTANCIA_CERCA_M
                     else 'sg-distancia-lejos')
            etiqueta_html = format_html('<span class="sg-badge {}">{}</span>', clase,
                                        reclamos.texto_distancia(metros))
        precision = (format_html(' <span class="sg-muted">GPS ±{} m</span>', obj.precision_evidencia_m)
                     if obj.precision_evidencia_m is not None else '')
        lat, lng = obj.ubicacion_evidencia.y, obj.ubicacion_evidencia.x
        mapa = format_html(
            ' · <a href="https://www.openstreetmap.org/?mlat={0}&amp;mlon={1}#map=18/{0}/{1}" '
            'target="_blank" rel="noopener">ver en el mapa</a>', f'{lat:.6f}', f'{lng:.6f}')
        return format_html('{}{}{}', etiqueta_html, precision, mapa)

    # Lo que viene de la verificación de campo: el supervisor no lo reescribe
    CAMPOS_DE_ORIGEN = ('id_reclamo', 'verificacion', 'componente', 'verificacion_etc', 'equipo_etc',
                        'origen_reclamo', 'foto_evidencia_antes')

    def get_readonly_fields(self, request, obj=None):
        campos = super().get_readonly_fields(request, obj)
        if obj is not None and not request.user.es_admin_eam:
            campos = tuple(campos) + self.CAMPOS_DE_ORIGEN
        if obj is not None and obj.estado in reclamos.ESTADOS_FINALES:
            # Terminado: solo se consulta (admin EAM puede reabrirlo cambiando el estado)
            campos = tuple(dict.fromkeys(tuple(campos) + self.CAMPOS_DE_ORIGEN + (
                'prioridad', 'agencia_responsable', 'responsable_asignado',
                'requiere_intervencion', 'descripcion', 'tipo_reclamo', 'resultado')))
        return campos

    @admin.action(description='Validar y cerrar los reclamos seleccionados')
    def validar_y_cerrar(self, request, queryset):
        cerrados, errores = 0, []
        for reclamo in queryset.filter(estado='PENDIENTE_VALIDACION'):
            try:
                reclamos.actualizar(reclamo, request.user, {'estado': 'CERRADO'})
                cerrados += 1
            except reclamos.ReglaReclamo as e:
                errores.append(f'{reclamo.id_reclamo}: {e.mensaje}')
        omitidos = queryset.exclude(estado='PENDIENTE_VALIDACION').count()
        self.message_user(request, f'{cerrados} reclamo(s) validados y cerrados.', messages.SUCCESS)
        if omitidos:
            self.message_user(
                request, f'{omitidos} reclamo(s) omitidos: solo se cierran los pendientes de validación.',
                messages.WARNING,
            )
        for error in errores:
            self.message_user(request, error, messages.ERROR)

    def get_queryset(self, request):
        # Mismo alcance por rol que la API (admin_eam/superusuario ven todo,
        # supervisores ven sus agencias asignadas).
        return filtrar_reclamos_por_rol(request.user, super().get_queryset(request))
