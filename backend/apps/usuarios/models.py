"""
SIGVER - Modelo de Usuario personalizado
"""
import uuid

from django.contrib.auth.models import AbstractUser
from django.db import models


class Usuario(AbstractUser):
    """
    Usuario del sistema con rol y agencias asignadas.

    Reemplaza al User por defecto de Django para incorporar el control
    de acceso basado en roles (RBAC) y la asignación territorial.
    """

    ROL_CHOICES = [
        ('tecnico_campo', 'Técnico de Campo'),
        ('supervisor_zona', 'Supervisor de Zona'),
        ('admin_eam', 'Administrador EAM'),
        ('consulta', 'Consulta'),
    ]

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    rol = models.CharField(
        max_length=20,
        choices=ROL_CHOICES,
        default='consulta',
        help_text="Rol del usuario en el sistema",
    )
    legajo = models.CharField(
        max_length=20,
        blank=True,
        help_text="Número de legajo interno de ANDE",
    )
    telefono = models.CharField(
        max_length=30,
        blank=True,
    )
    agencias_asignadas = models.ManyToManyField(
        'inventario.Agencia',
        blank=True,
        related_name='usuarios_asignados',
        help_text='Agencias que este usuario puede ver (técnicos y supervisores)',
    )

    class Meta:
        verbose_name = 'Usuario'
        verbose_name_plural = 'Usuarios'
        ordering = ['username']

    def __str__(self):
        return f"{self.get_full_name() or self.username} ({self.get_rol_display()})"

    def save(self, *args, **kwargs):
        # El acceso al admin lo da el rol, no una casilla suelta: supervisores
        # y admin_eam entran; técnicos y consulta usan solo la PWA.
        from .permisos import ROLES_CON_ADMIN
        self.is_staff = self.is_superuser or self.rol in ROLES_CON_ADMIN
        super().save(*args, **kwargs)
        self.sincronizar_grupos()

    def sincronizar_grupos(self):
        """Pone o quita al usuario del grupo de supervisores según su rol."""
        from django.contrib.auth.models import Group
        from .permisos import GRUPO_SUPERVISORES
        grupo = Group.objects.filter(name=GRUPO_SUPERVISORES).first()
        if grupo is None:  # todavía no se corrió migrate
            return
        if self.rol == 'supervisor_zona':
            self.groups.add(grupo)
        else:
            self.groups.remove(grupo)

    @property
    def es_admin_eam(self):
        """Retorna True si el usuario es administrador EAM o superusuario."""
        return self.rol == 'admin_eam' or self.is_superuser

    @property
    def es_supervisor(self):
        return self.rol in ('supervisor_zona', 'admin_eam') or self.is_superuser

    @property
    def es_tecnico(self):
        return self.rol == 'tecnico_campo'