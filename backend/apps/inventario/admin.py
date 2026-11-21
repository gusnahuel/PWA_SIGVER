"""
SIGVER - Admin de Inventario
"""
from django.contrib import admin
from django.contrib.gis.admin import GISModelAdmin

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


@admin.register(Personal)
class PersonalAdmin(admin.ModelAdmin):
    list_display = ('id_personal', 'nombre_completo', 'agencia', 'activo', 'tiene_acceso')
    list_filter = ('agencia', 'activo', 'tipo_participacion')
    search_fields = ('id_personal', 'nombre_completo', 'correo')

    @admin.display(boolean=True, description='¿Tiene acceso?')
    def tiene_acceso(self, obj):
        return obj.tiene_acceso


@admin.register(SubEstacion)
class SubEstacionAdmin(admin.ModelAdmin):
    list_display = ('codigo', 'nombre')
    search_fields = ('codigo', 'nombre')


@admin.register(Alimentador)
class AlimentadorAdmin(admin.ModelAdmin):
    list_display = ('codigo', 'subestacion')
    list_filter = ('subestacion',)
    search_fields = ('codigo',)


@admin.register(Sitio)
class SitioAdmin(GISModelAdmin):
    list_display = ('id_sitio', 'cod_sitio', 'alimentador', 'agencia', 'estado_general')
    list_filter = ('estado_general', 'agencia', 'alimentador__subestacion')
    search_fields = ('id_sitio', 'cod_sitio')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(Componente)
class ComponenteAdmin(admin.ModelAdmin):
    list_display = ('id_componente', 'sitio', 'tipo_componente', 'tipo_conexion', 'estado_componente')
    list_filter = ('tipo_componente', 'tipo_conexion', 'estado_componente')
    search_fields = ('id_componente',)


@admin.register(ElementoEquipo)
class ElementoEquipoAdmin(admin.ModelAdmin):
    list_display = ('marca', 'modelo', 'numero_serie', 'componente', 'estado_elemento')
    list_filter = ('marca', 'estado_elemento')
    search_fields = ('marca', 'modelo', 'numero_serie')


@admin.register(EquipoETC)
class EquipoETCAdmin(admin.ModelAdmin):
    list_display = ('nro_equipo', 'alimentador', 'estado_seccionador', 'tiene_problema_actual', 'fecha_ultima_verificacion')
    list_filter = ('estado_seccionador', 'tiene_problema_actual')
    search_fields = ('nro_equipo',)
    readonly_fields = ('created_at', 'updated_at')