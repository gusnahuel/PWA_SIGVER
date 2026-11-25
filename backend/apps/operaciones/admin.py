"""
SIGVER - Admin de Operaciones
"""
from django import forms
from django.contrib import admin, messages
from django.contrib.gis.admin import GISModelAdmin
from django.db.models import Case, IntegerField, Q, Value, When
from django.utils.formats import date_format
from django.core.exceptions import PermissionDenied
from django.template.response import TemplateResponse
from django.urls import path
from django.utils.html import format_html, format_html_join
from django.urls import reverse
from django.utils import timezone

from apps.inventario.models import Agencia, Personal
from apps.usuarios.permisos import (
    InmutableSalvoAdminEAM, agencias_del_usuario, filtrar_reclamos_por_rol, filtrar_verificaciones_por_rol,
)

from . import geo, indicadores, reclamos
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


def insignia_distancia(metros, ubicacion, precision=None, sin_gps='Sin GPS'):
    """Distancia al equipo con color, precisión y enlace al mapa (verificaciones y reclamos)."""
    if ubicacion is None:
        return format_html('<span class="sg-muted">{}</span>', sin_gps)
    if metros is None:
        cuerpo = format_html('<span class="sg-badge sg-plazo-ok">{}</span>', 'El equipo no tiene coordenadas')
    else:
        clase = {'SI': 'sg-distancia-lugar', 'APROXIMADA': 'sg-distancia-cerca', 'NO': 'sg-distancia-lejos'}[geo.coincide(metros)]
        cuerpo = format_html('<span class="sg-badge {}">{}</span>', clase, geo.texto_distancia(metros))
    if precision is not None:
        cuerpo = format_html('{} <span class="sg-muted">GPS ±{} m</span>', cuerpo, precision)
    return format_html(
        '{0} · <a href="https://www.openstreetmap.org/?mlat={1}&amp;mlon={2}#map=18/{1}/{2}" '
        'target="_blank" rel="noopener">ver en el mapa</a>', cuerpo, f'{ubicacion.y:.6f}', f'{ubicacion.x:.6f}')


def enlace_pdf(tipo, obj, texto='PDF'):
    url = reverse('generar_pdf', args=[tipo, obj.pk])
    return format_html('<a class="sg-btn-pdf" href="{}" target="_blank" rel="noopener">'
                       '<i class="fas fa-file-pdf"></i> {}</a>', url, texto)


class AlcanceVerificacionesMixin:
    """El supervisor ve las verificaciones (y sus mediciones) de sus agencias."""
    prefijo_alcance = ''

    def get_queryset(self, request):
        return filtrar_verificaciones_por_rol(request.user, super().get_queryset(request), self.prefijo_alcance)


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
class VerificacionAdmin(AlcanceVerificacionesMixin, InmutableSalvoAdminEAM, GISModelAdmin):
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
    readonly_fields = ('synced_at', 'boton_pdf', 'fotos', 'distancia_gps', 'agencia_responsable')
    fieldsets = (
        ('Identificación', {'fields': ('id_verificacion', 'sitio', 'componente', 'fecha_verificacion',
                                       'responsable', 'agencia_responsable', 'boton_pdf')}),
        ('Estado del sitio', {'fields': ('estado_sitio', 'tipo_control_verificado', 'tipo_banco_verificado',
                                         'valla_perimetral', 'es_hibrido', 'configuracion_observada',
                                         'observaciones_control_unico', 'observaciones')}),
        ('Fotos', {'fields': ('fotos', 'foto_frontal', 'foto_entorno', 'foto_control_unico')}),
        ('Ubicación GPS', {'fields': ('distancia_gps', 'ubicacion_coincide', 'ubicacion_capturada'),
                           'description': 'Con GPS, «ubicación coincide» lo calcula el servidor según la distancia.'}),
        ('Reclamo', {'fields': ('requiere_reclamo', 'prioridad')}),
        ('Registro', {'fields': ('client_uuid', 'synced_at')}),
    )

    @admin.display(description='Estado', ordering='estado_sitio')
    def estado(self, obj):
        return etiqueta(obj.estado_sitio, obj.get_estado_sitio_display(), 'sitio')

    @admin.display(description='Informe')
    def informe(self, obj):
        return enlace_pdf('regulador', obj)

    @admin.display(description='Distancia al equipo')
    def distancia_gps(self, obj):
        return insignia_distancia(obj.distancia_equipo_m, obj.ubicacion_capturada, obj.precision_gps_m,
                                  'Sin GPS (ubicación declarada por el técnico)')

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
class VerificacionETCAdmin(AlcanceVerificacionesMixin, InmutableSalvoAdminEAM, GISModelAdmin):
    list_display = ('id_verificacion', 'equipo_etc', 'fecha_verificacion', 'responsable',
                    'resultado', 'informe')
    list_filter = ('tiene_inconveniente', 'requiere_reclamo', 'agencia_responsable', 'responsable')
    list_select_related = ('equipo_etc', 'responsable')
    search_fields = ('id_verificacion', 'equipo_etc__nro_equipo', 'responsable__nombre_completo')
    date_hierarchy = 'fecha_verificacion'
    list_per_page = 25
    readonly_fields = ('synced_at', 'boton_pdf', 'vista_foto', 'distancia_gps', 'agencia_responsable')
    fieldsets = (
        ('Identificación', {'fields': ('id_verificacion', 'equipo_etc', 'fecha_verificacion',
                                       'responsable', 'agencia_responsable', 'boton_pdf')}),
        ('Resultado', {'fields': ('tiene_inconveniente', 'fallas', 'observaciones',
                                  'requiere_reclamo', 'prioridad')}),
        ('Foto', {'fields': ('vista_foto', 'foto')}),
        ('Ubicación GPS', {'fields': ('distancia_gps', 'ubicacion_coincide', 'ubicacion_capturada'),
                           'description': 'Con GPS, «ubicación coincide» lo calcula el servidor según la distancia.'}),
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

    @admin.display(description='Distancia al equipo')
    def distancia_gps(self, obj):
        return insignia_distancia(obj.distancia_equipo_m, obj.ubicacion_capturada, obj.precision_gps_m,
                                  'Sin GPS (ubicación declarada por el técnico)')

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
class MedicionTermografiaAdmin(AlcanceVerificacionesMixin, InmutableSalvoAdminEAM, admin.ModelAdmin):
    prefijo_alcance = 'verificacion__'
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
class EnsayoPATAdmin(AlcanceVerificacionesMixin, InmutableSalvoAdminEAM, admin.ModelAdmin):
    prefijo_alcance = 'verificacion__'
    list_display = ('id_ensayo', 'componente', 'fecha_ensayo', 'metodo_pat', 'resultado', 'condicion_suelo')
    list_filter = ('resultado', 'condicion_suelo', 'metodo_pat')
    search_fields = ('id_ensayo', 'componente__id_componente')
    date_hierarchy = 'fecha_ensayo'
    inlines = [LecturaPATInline]


@admin.register(LecturaPAT)
class LecturaPATAdmin(AlcanceVerificacionesMixin, InmutableSalvoAdminEAM, admin.ModelAdmin):
    prefijo_alcance = 'ensayo__verificacion__'
    list_display = ('id_lectura', 'ensayo', 'tipo_lectura', 'distancia_m', 'valor_ohm')
    list_filter = ('tipo_lectura',)
    search_fields = ('id_lectura', 'ensayo__id_ensayo')


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

    # Lo que se pide al cargar un reclamo a mano (el resto lo completa el sistema)
    CAMPOS_ALTA = ('descripcion', 'prioridad', 'equipo_etc', 'componente',
                   'agencia_responsable', 'responsable_asignado')

    # Qué se puede hacer desde cada estado (ayuda bajo el campo Estado)
    AYUDA_ESTADO = {
        'ABIERTO': 'Para asignarlo elegí el técnico: el estado pasa solo a «Asignado». '
                   'Para descartarlo, «Rechazado» con un comentario.',
        'ASIGNADO': 'El técnico lo inicia desde la app. Podés reasignarlo o rechazarlo con un comentario.',
        'EN_PROCESO': 'El técnico está trabajando y lo envía a validación desde la app, con la foto.',
        'PENDIENTE_VALIDACION': 'Revisá las fotos y la ubicación. Para aprobar elegí «Cerrado»; '
                                'para pedir una corrección, «En proceso» con un comentario.',
        'CERRADO': 'Terminado. Solo admin EAM puede reabrirlo, con un comentario.',
        'RECHAZADO': 'Terminado. Solo admin EAM puede reabrirlo, con un comentario.',
    }

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
        # Los reclamos usan UUID: el id existe antes de guardar, por eso no sirve "instance.pk"
        self.es_nuevo = self.instance._state.adding
        if self.es_nuevo:
            ayudas = {
                'descripcion': 'Qué se observó y dónde. El número, el plazo y el estado los completa el sistema.',
                'equipo_etc': 'Elegí un ETC o un componente de regulador (uno solo).',
                'responsable_asignado': 'Opcional: si lo asignás ahora, el reclamo nace «Asignado».',
            }
            for campo, texto in ayudas.items():
                if campo in self.fields:
                    self.fields[campo].help_text = texto
            if 'componente' in self.fields:
                self.fields['componente'].label = 'Componente de regulador'
            return
        if 'estado' in self.fields:
            # Solo los estados a los que este usuario puede llevarlo desde el actual
            posibles = reclamos.estados_posibles(self.instance, self.usuario)
            self.fields['estado'].choices = [(v, t) for v, t in Reclamo.ESTADO if v in posibles]
            self.fields['estado'].help_text = self.AYUDA_ESTADO.get(self.instance.estado, '')
        # En la lista: no se reasigna lo terminado ni lo que espera validación
        if self.instance.estado in (*reclamos.ESTADOS_FINALES, 'PENDIENTE_VALIDACION'):
            for campo in ('agencia_responsable', 'responsable_asignado'):
                if campo in self.fields:
                    self.fields[campo].disabled = True

    def cambios(self):
        campos_modelo = {f.name for f in Reclamo._meta.fields}
        return {c: self.cleaned_data[c] for c in self.changed_data
                if c in campos_modelo and c in self.cleaned_data}

    def clean(self):
        datos = super().clean()
        try:
            if self.es_nuevo:
                if bool(datos.get('equipo_etc')) == bool(datos.get('componente')):
                    raise reclamos.ReglaReclamo('Elegí el equipo: un ETC o un componente de regulador (uno solo).',
                                                campo='equipo_etc')
                self.datos_nuevos = reclamos.preparar_nuevo(
                    self.usuario, {c: datos.get(c) for c in self.CAMPOS_ALTA})
            else:
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
                    'agencia_responsable', 'responsable_asignado')
    # Asignar agencia y técnico desde la lista, sin abrir cada reclamo
    list_editable = ('agencia_responsable', 'responsable_asignado')
    list_filter = (BandejaReclamosFilter, 'estado', 'prioridad', 'origen_reclamo',
                   'agencia_responsable', 'fecha_reclamo')
    list_select_related = ('componente__sitio', 'equipo_etc', 'agencia_responsable', 'responsable_asignado')
    search_fields = ('id_reclamo', 'descripcion', 'componente__id_componente', 'componente__sitio__id_sitio',
                     'equipo_etc__nro_equipo')
    autocomplete_fields = ('componente', 'equipo_etc')
    list_per_page = 25
    actions = ('validar_y_cerrar',)

    # Campos ocultos a propósito (siguen en la base): requiere_intervencion, resultado
    # y tipo_reclamo no los usa ninguna regla; la foto "antes" se ve en la galería; el
    # origen (verificación, equipo) se muestra resumido y no se edita.
    SECCION_EVIDENCIA = ('Evidencia del técnico', {
        'fields': ('vista_fotos', 'vista_ubicacion', 'observaciones_cierre'),
    })
    fieldsets = (
        ('Gestión', {
            'fields': ('estado', 'comentario', 'prioridad', 'agencia_responsable', 'responsable_asignado'),
        }),
        ('Reclamo', {
            'fields': ('id_reclamo', 'vista_origen', 'descripcion', 'fecha_limite'),
        }),
        ('Seguimiento', {
            'fields': ('vista_seguimiento',),
        }),
    )
    add_fieldsets = (
        ('Nuevo reclamo', {
            'fields': ('descripcion', 'prioridad', 'equipo_etc', 'componente',
                       'agencia_responsable', 'responsable_asignado'),
        }),
    )
    # Una vez creado: el número, el origen y lo que cargó el técnico solo se consultan
    readonly_fields = ('id_reclamo', 'vista_origen', 'descripcion', 'fecha_reclamo', 'fecha_limite',
                       'observaciones_cierre', 'vista_fotos', 'vista_ubicacion', 'vista_seguimiento')

    def get_inlines(self, request, obj):
        return self.inlines if obj is not None else ()   # un reclamo nuevo no tiene historial

    def change_view(self, request, object_id, form_url='', extra_context=None):
        extra_context = {**(extra_context or {}), 'show_save_and_add_another': False}
        return super().change_view(request, object_id, form_url, extra_context)

    def get_fieldsets(self, request, obj=None):
        if obj is None:
            return self.add_fieldsets
        if not (obj.foto_evidencia_antes or obj.foto_evidencia_despues):
            return self.fieldsets
        # Con algo que validar, la evidencia va primero; si no, al final
        if obj.estado == 'PENDIENTE_VALIDACION':
            return (self.SECCION_EVIDENCIA, *self.fieldsets)
        return (*self.fieldsets, self.SECCION_EVIDENCIA)

    def get_readonly_fields(self, request, obj=None):
        if obj is None:
            return ()
        campos = self.readonly_fields
        if obj.estado in reclamos.ESTADOS_FINALES:
            campos += ('prioridad', 'agencia_responsable', 'responsable_asignado')
        elif obj.estado == 'PENDIENTE_VALIDACION':
            # Hay que validarlo o devolverlo antes de reasignarlo
            campos += ('agencia_responsable', 'responsable_asignado')
        return campos

    def get_queryset(self, request):
        # Mismo alcance por rol que la API; primero lo que requiere acción.
        # Sin super(): el get_queryset de Django ordena antes de que exista la anotación.
        qs = self.model._default_manager.get_queryset().annotate(orden_bandeja=Case(
            When(estado='PENDIENTE_VALIDACION', then=Value(0)),
            When(estado__in=reclamos.ESTADOS_ACTIVOS, then=Value(1)),
            default=Value(2), output_field=IntegerField(),
        ))
        return filtrar_reclamos_por_rol(request.user, qs.order_by(*self.get_ordering(request)))

    def get_ordering(self, request):
        return ('orden_bandeja', 'fecha_limite', '-fecha_reclamo')

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
        # Alta: número, origen, estado y plazo los completa el servicio (preparar_nuevo)
        for campo, valor in form.datos_nuevos.items():
            setattr(obj, campo, valor)
        obj.fecha_limite = reclamos.calcular_fecha_limite(timezone.now(), obj.prioridad)
        super().save_model(request, obj, form, change)
        reclamos.registrar(obj, request.user, estado_nuevo=obj.estado, detalle='Cargado a mano desde el admin')

    def message_user(self, request, message, level=messages.INFO, *args, **kwargs):
        # Si el servicio rechazó el cambio, no mostrar además "se modificó con éxito"
        if getattr(request, '_reclamo_sin_guardar', False) and level == messages.SUCCESS:
            return
        super().message_user(request, message, level, *args, **kwargs)

    def has_delete_permission(self, request, obj=None):
        # Un reclamo no se borra: se rechaza con motivo. Solo admin EAM, para limpiar errores.
        return request.user.es_admin_eam and super().has_delete_permission(request, obj)

    # --- Columnas ---
    @admin.display(description='Equipo', ordering='componente__sitio__id_sitio')
    def equipo(self, obj):
        if obj.equipo_etc:
            return f'ETC {obj.equipo_etc.nro_equipo}'
        return f'Regulador {obj.componente.sitio.id_sitio}' if obj.componente else '—'

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
                               indicadores.texto_duracion(-restante))
        clase = 'sg-plazo-proximo' if restante.total_seconds() < 86400 else 'sg-plazo-ok'
        return format_html('<span class="sg-badge {}">Vence en {}</span>', clase, indicadores.texto_duracion(restante))

    @admin.display(description='Fotos del técnico')
    def vista_fotos(self, obj):
        return galeria(('Antes (al iniciar)', obj.foto_evidencia_antes),
                       ('Después (trabajo terminado)', obj.foto_evidencia_despues))

    @admin.display(description='Ubicación al enviar')
    def vista_ubicacion(self, obj):
        return insignia_distancia(
            obj.distancia_evidencia_m, obj.ubicacion_evidencia, obj.precision_evidencia_m,
            'Sin GPS' if obj.foto_evidencia_despues else 'Todavía no se envió la evidencia')

    @admin.display(description='Origen')
    def vista_origen(self, obj):
        def enlace(nombre_url, objeto, texto):
            return format_html('<a href="{}">{}</a>', reverse(nombre_url, args=[objeto.pk]), texto)
        partes = []
        if obj.verificacion_etc_id:
            partes.append(format_html('Verificación {}', enlace('admin:operaciones_verificacionetc_change',
                                                               obj.verificacion_etc, obj.verificacion_etc.id_verificacion)))
        elif obj.verificacion_id:
            partes.append(format_html('Verificación {}', enlace('admin:operaciones_verificacion_change',
                                                               obj.verificacion, obj.verificacion.id_verificacion)))
        else:
            partes.append(obj.get_origen_reclamo_display())
        if obj.equipo_etc_id:
            partes.append(enlace('admin:inventario_equipoetc_change', obj.equipo_etc, f'ETC {obj.equipo_etc.nro_equipo}'))
        if obj.componente_id:
            partes.append(enlace('admin:inventario_componente_change', obj.componente,
                                 f'Regulador {obj.componente.sitio.id_sitio} ({obj.componente.id_componente})'))
        return format_html_join(' · ', '{}', ((p,) for p in partes))

    @admin.display(description='Fechas')
    def vista_seguimiento(self, obj):
        """Las fechas del recorrido en una sola tabla (solo las que ocurrieron)."""
        validado = obj.fecha_validacion and format_html(
            '{} <span class="sg-muted">por {}</span>', date_format(timezone.localtime(obj.fecha_validacion),
                                                                    'DATETIME_FORMAT'),
            obj.validado_por.get_full_name() or obj.validado_por.username if obj.validado_por else '—')
        filas = [
            ('Recibido', obj.fecha_reclamo), ('Asignado', obj.fecha_asignacion), ('Iniciado', obj.fecha_inicio),
            ('Enviado a validación', obj.fecha_ejecucion), ('Validado', validado),
            ('Rechazado' if obj.estado == 'RECHAZADO' else 'Cerrado', obj.fecha_cierre),
        ]
        filas = [(t, v if not hasattr(v, 'tzinfo') else date_format(timezone.localtime(v), 'DATETIME_FORMAT'))
                 for t, v in filas if v]
        if obj.estado == 'RECHAZADO' and obj.motivo_rechazo:
            filas.append(('Motivo del rechazo', obj.motivo_rechazo))
        return format_html('<table class="sg-seguimiento">{}</table>',
                           format_html_join('', '<tr><th>{}</th><td>{}</td></tr>', filas))

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

