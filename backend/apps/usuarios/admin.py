"""
SIGVER - Admin de Usuarios (solo admin_eam: los supervisores no tienen permisos sobre usuarios)
"""
from django.contrib import admin
from django.contrib.admin.forms import AdminAuthenticationForm
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from apps.inventario.models import Personal

from .models import Usuario
from .seguridad import MENSAJE_BLOQUEO, esta_bloqueado


class LoginAdminForm(AdminAuthenticationForm):
    """Muestra el motivo cuando el usuario está bloqueado por intentos fallidos
    (sin esto el admin diría solo "usuario o contraseña incorrectos")."""

    def clean(self):
        if self.request is not None and esta_bloqueado(self.request, self.cleaned_data.get('username')):
            raise ValidationError(MENSAJE_BLOQUEO, code='bloqueado')
        return super().clean()


admin.site.login_form = LoginAdminForm


class PersonalInline(admin.StackedInline):
    """Ficha de Personal del usuario (legajo, agencia, cargo) en la misma pantalla."""
    model = Personal
    fk_name = 'usuario'
    extra = 0
    max_num = 1
    can_delete = False
    verbose_name = 'Ficha de Personal'
    verbose_name_plural = 'Ficha de Personal'
    fields = ('id_personal', 'nombre_completo', 'agencia', 'cargo', 'telefono', 'activo')


@admin.register(Usuario)
class UsuarioAdmin(BaseUserAdmin):
    list_display = ('username', 'get_full_name', 'rol', 'ficha_personal', 'is_active', 'is_staff')
    list_filter = ('rol', 'is_active', 'is_staff', 'is_superuser')
    list_select_related = ('personal',)
    search_fields = ('username', 'first_name', 'last_name', 'email', 'legajo')
    ordering = ('username',)
    inlines = [PersonalInline]
    # Se calcula a partir del rol (ver Usuario.save)
    readonly_fields = ('is_staff',)

    filter_horizontal = BaseUserAdmin.filter_horizontal + ('agencias_asignadas',)

    fieldsets = BaseUserAdmin.fieldsets + (
        (_('Información SIGVER'), {
            'fields': ('rol', 'legajo', 'telefono', 'agencias_asignadas'),
            'description': 'El acceso al admin y el grupo «Supervisores de zona» se asignan '
                           'automáticamente según el rol.',
        }),
    )

    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        (_('Información SIGVER'), {
            'fields': ('rol', 'legajo', 'telefono', 'agencias_asignadas'),
        }),
    )

    @admin.display(boolean=True, description='Ficha de Personal')
    def ficha_personal(self, obj):
        return hasattr(obj, 'personal')

    def save_related(self, request, form, formsets, change):
        # El formulario reescribe los grupos con lo que tenía marcado;
        # volvemos a aplicar la regla del rol después.
        super().save_related(request, form, formsets, change)
        form.instance.sincronizar_grupos()
