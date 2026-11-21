"""
SIGVER - Admin de Operaciones
"""
from django.contrib import admin
from django.contrib.gis.admin import GISModelAdmin
from django.utils.html import format_html
from django.urls import reverse

from .models import (
    TipoFallaETC, Verificacion, VerificacionETC,
    PuntoInspeccionTermografia, MedicionTermografia,
    EnsayoPAT, LecturaPAT, Reclamo,
)


@admin.register(TipoFallaETC)
class TipoFallaETCAdmin(admin.ModelAdmin):
    list_display = ('codigo', 'numero', 'descripcion', 'gravedad', 'activo')
    list_filter = ('gravedad', 'activo')
    search_fields = ('codigo', 'descripcion')
    ordering = ('numero',)


class MedicionTermografiaInline(admin.TabularInline):
    model = MedicionTermografia
    extra = 0
    fields = ('id_medicion', 'punto', 'fecha_hora', 'temperatura_punto_c', 'nivel_termografico')
    readonly_fields = ('id_medicion',)
    can_delete = False


class EnsayoPATInline(admin.TabularInline):
    model = EnsayoPAT
    extra = 0
    fields = ('id_ensayo', 'fecha_ensayo', 'metodo_pat', 'resultado')
    readonly_fields = ('id_ensayo',)
    can_delete = False


@admin.register(Verificacion)
class VerificacionAdmin(GISModelAdmin):
    list_display = ('id_verificacion', 'sitio', 'componente', 'fecha_verificacion', 'responsable', 'estado_sitio', 'requiere_reclamo')
    list_filter = ('estado_sitio', 'requiere_reclamo', 'tipo_banco_verificado', 'tipo_control_verificado')
    search_fields = ('id_verificacion', 'sitio__id_sitio', 'componente__id_componente')
    readonly_fields = ('synced_at',)
    date_hierarchy = 'fecha_verificacion'
    inlines = [MedicionTermografiaInline, EnsayoPATInline]
    readonly_fields = ('synced_at', 'boton_pdf')
    
    def boton_pdf(self, obj):
        if obj.pk:
            url = reverse('generar_pdf', args=['regulador', obj.pk])
            return format_html('<a class="button" href="{}" target="_blank">📄 Descargar Informe PDF</a>', url)
        return "Guarda la verificación primero."
    boton_pdf.short_description = "Informe"


@admin.register(VerificacionETC)
class VerificacionETCAdmin(GISModelAdmin):
    list_display = ('id_verificacion', 'equipo_etc', 'fecha_verificacion', 'responsable', 'tiene_inconveniente')
    list_filter = ('tiene_inconveniente',)
    search_fields = ('id_verificacion', 'equipo_etc__nro_equipo')
    readonly_fields = ('synced_at',)
    date_hierarchy = 'fecha_verificacion'
    readonly_fields = ('synced_at', 'boton_pdf')
    def boton_pdf(self, obj):
        if obj.pk:
            url = reverse('generar_pdf', args=['etc', obj.pk])
            return format_html('<a class="button" href="{}" target="_blank">📄 Descargar Informe PDF</a>', url)
        return "Guarda la verificación primero."
    boton_pdf.short_description = "Informe"


@admin.register(PuntoInspeccionTermografia)
class PuntoInspeccionTermografiaAdmin(admin.ModelAdmin):
    list_display = ('id_punto', 'fase', 'tipo_elemento', 'lado_conexion', 'activo')
    list_filter = ('fase', 'tipo_elemento', 'lado_conexion', 'activo')
    search_fields = ('id_punto',)


@admin.register(MedicionTermografia)
class MedicionTermografiaAdmin(admin.ModelAdmin):
    list_display = ('id_medicion', 'componente', 'punto', 'fecha_hora', 'temperatura_punto_c', 'nivel_termografico')
    list_filter = ('nivel_termografico', 'fecha_hora')
    search_fields = ('id_medicion', 'componente__id_componente')
    date_hierarchy = 'fecha_hora'


class LecturaPATInline(admin.TabularInline):
    model = LecturaPAT
    extra = 0
    fields = ('id_lectura', 'tipo_lectura', 'distancia_m', 'valor_ohm')
    readonly_fields = ('id_lectura',)


@admin.register(EnsayoPAT)
class EnsayoPATAdmin(admin.ModelAdmin):
    list_display = ('id_ensayo', 'componente', 'fecha_ensayo', 'metodo_pat', 'resultado', 'condicion_suelo')
    list_filter = ('resultado', 'condicion_suelo', 'metodo_pat')
    search_fields = ('id_ensayo', 'componente__id_componente')
    date_hierarchy = 'fecha_ensayo'
    inlines = [LecturaPATInline]


@admin.register(LecturaPAT)
class LecturaPATAdmin(admin.ModelAdmin):
    list_display = ('id_lectura', 'ensayo', 'tipo_lectura', 'distancia_m', 'valor_ohm')
    list_filter = ('tipo_lectura',)
    search_fields = ('id_lectura', 'ensayo__id_ensayo')


@admin.register(Reclamo)
class ReclamoAdmin(admin.ModelAdmin):
    list_display = ('id_reclamo', 'componente', 'estado', 'prioridad', 'fecha_reclamo', 'agencia_responsable', 'responsable_asignado')
    list_filter = ('estado', 'prioridad', 'origen_reclamo', 'agencia_responsable')
    search_fields = ('id_reclamo', 'descripcion', 'componente__id_componente')
    readonly_fields = ('fecha_reclamo',)
    date_hierarchy = 'fecha_reclamo'
    fieldsets = (
        ('Identificación', {
            'fields': ('id_reclamo', 'verificacion', 'componente', 'fecha_reclamo', 'origen_reclamo')
        }),
        ('Descripción', {
            'fields': ('descripcion', 'tipo_reclamo', 'prioridad')
        }),
        ('Workflow', {
            'fields': ('estado', 'agencia_responsable', 'responsable_asignado', 'requiere_intervencion')
        }),
        ('Fechas de gestión', {
            'fields': ('fecha_asignacion', 'fecha_ejecucion', 'fecha_cierre')
        }),
        ('Resolución', {
            'fields': ('resultado', 'motivo_rechazo', 'observaciones_cierre',
                       'foto_evidencia_antes', 'foto_evidencia_despues')
        }),
    )
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        
        # 1. Si es superusuario (tu usuario admin), ve TODO.
        if request.user.is_superuser:
            return qs
            
        # 2. Si es un usuario normal (supervisor), verificamos si tiene agencia
        if hasattr(request.user, 'personal') and request.user.personal.agencia:
            # Solo le mostramos los reclamos de SU agencia
            return qs.filter(agencia_responsable=request.user.personal.agencia)
            
        # 3. Si no tiene agencia (o no tiene perfil Personal), no ve nada
        return qs.none()