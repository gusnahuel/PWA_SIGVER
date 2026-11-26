"""
SIGVER - Admin de Inventario
"""
from django.contrib import admin
from django.contrib.gis.admin import GISModelAdmin
from django.utils.html import format_html

from apps.usuarios.permisos import filtrar_personal_por_rol

from .models import (
    SeccionRegional, Agencia, Personal,
    SubEstacion, Alimentador, Sitio,
    Componente, ElementoEquipo, EquipoETC,
)


@admin.register(SeccionRegional)
class SeccionRegionalAdmin(admin.ModelAdmin):
    list_display = ('codigo', 'nombre')
    search_fields = ('codigo', 'nombre')


@admin.register(Agencia)
class AgenciaAdmin(admin.ModelAdmin):
    list_display = ('id_seccion', 'nombre', 'seccion_regional')
    list_filter = ('seccion_regional',)
    search_fields = ('id_seccion', 'nombre')


class AccesoPWAFilter(admin.SimpleListFilter):
    title = 'acceso a la app'
    parameter_name = 'acceso'

    def lookups(self, request, model_admin):
        return (('si', 'Puede ingresar'), ('no', 'Sin usuario'))

    def queryset(self, request, queryset):
        if self.value() == 'si':
            return queryset.filter(usuario__isnull=False)
        if self.value() == 'no':
            return queryset.filter(usuario__isnull=True)
        return queryset


@admin.register(Personal)
class PersonalAdmin(admin.ModelAdmin):
    list_display = ('id_personal', 'nombre_completo', 'agencia', 'activo', 'puede_ingresar', 'usuario')
    list_filter = (AccesoPWAFilter, 'agencia', 'activo', 'tipo_participacion')
    list_select_related = ('agencia', 'usuario')
    search_fields = ('id_personal', 'nombre_completo', 'correo')
    autocomplete_fields = ('usuario',)

    @admin.display(boolean=True, description='Puede ingresar')
    def puede_ingresar(self, obj):
        return obj.tiene_acceso

    def get_queryset(self, request):
        # El supervisor administra el personal de sus agencias
        return filtrar_personal_por_rol(request.user, super().get_queryset(request))

    def get_readonly_fields(self, request, obj=None):
        # Vincular una ficha con un usuario da acceso al sistema: solo admin_eam
        if not request.user.es_admin_eam:
            return ('usuario',)
        return ()


@admin.register(SubEstacion)
class SubEstacionAdmin(admin.ModelAdmin):
    list_display = ('codigo', 'nombre', 'tipo', 'seccion_regional')
    list_filter = ('tipo', 'seccion_regional')
    list_select_related = ('seccion_regional',)
    search_fields = ('codigo', 'nombre')


@admin.register(Alimentador)
class AlimentadorAdmin(admin.ModelAdmin):
    list_display = ('codigo', 'subestacion')
    list_filter = ('subestacion',)
    list_select_related = ('subestacion',)
    search_fields = ('codigo', 'subestacion__nombre')


@admin.register(Sitio)
class SitioAdmin(GISModelAdmin):
    list_display = ('id_sitio', 'cod_sitio', 'alimentador', 'agencia', 'estado')
    list_filter = ('estado_general', 'agencia', 'alimentador__subestacion')
    list_select_related = ('alimentador', 'agencia')
    search_fields = ('id_sitio', 'cod_sitio')
    readonly_fields = ('created_at', 'updated_at')
    list_per_page = 25

    @admin.display(description='Estado', ordering='estado_general')
    def estado(self, obj):
        if not obj.estado_general:
            return '—'
        return format_html('<span class="sg-badge sg-sitio-{}">{}</span>',
                           obj.estado_general.lower(), obj.get_estado_general_display())


class ElementoEquipoInline(admin.StackedInline):
    """Marca, modelo y serie del componente: se cargan dentro de su ficha."""
    model = ElementoEquipo
    extra = 0


@admin.register(Componente)
class ComponenteAdmin(admin.ModelAdmin):
    list_display = ('id_componente', 'sitio', 'tipo_componente', 'tipo_conexion', 'estado_componente')
    list_filter = ('tipo_componente', 'tipo_conexion', 'estado_componente')
    list_select_related = ('sitio',)
    search_fields = ('id_componente', 'sitio__id_sitio')
    inlines = [ElementoEquipoInline]


@admin.register(ElementoEquipo)
class ElementoEquipoAdmin(admin.ModelAdmin):
    list_display = ('marca', 'modelo', 'numero_serie', 'componente', 'estado_elemento')
    list_filter = ('marca', 'estado_elemento')
    list_select_related = ('componente',)
    search_fields = ('marca', 'modelo', 'numero_serie')


@admin.register(EquipoETC)
class EquipoETCAdmin(admin.ModelAdmin):
    list_display = ('nro_equipo', 'alimentador', 'estado_seccionador', 'tiene_problema_actual', 'fecha_ultima_verificacion')
    list_filter = ('estado_seccionador', 'tiene_problema_actual', 'alimentador__subestacion')
    list_select_related = ('alimentador',)
    search_fields = ('nro_equipo',)
    readonly_fields = ('created_at', 'updated_at')
    list_per_page = 25
