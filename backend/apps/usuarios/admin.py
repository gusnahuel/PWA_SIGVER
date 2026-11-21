"""
SIGVER - Admin de Usuarios
"""
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.translation import gettext_lazy as _

from .models import Usuario


@admin.register(Usuario)
class UsuarioAdmin(BaseUserAdmin):
    list_display = ('username', 'get_full_name', 'rol', 'legajo', 'is_active', 'is_staff')
    list_filter = ('rol', 'is_active', 'is_staff', 'is_superuser')
    search_fields = ('username', 'first_name', 'last_name', 'email', 'legajo')
    ordering = ('username',)

    fieldsets = BaseUserAdmin.fieldsets + (
        (_('Información SIGVER'), {
            'fields': ('rol', 'legajo', 'telefono'),
        }),
    )

    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        (_('Información SIGVER'), {
            'fields': ('rol', 'legajo', 'telefono'),
        }),
    )