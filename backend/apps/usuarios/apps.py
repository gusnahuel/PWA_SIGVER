from django.apps import AppConfig
from django.db.models.signals import post_migrate


class UsuariosConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.usuarios'
    verbose_name = 'Usuarios y accesos'

    def ready(self):
        from .permisos import configurar_grupo_supervisores
        # Sin filtrar por app: los permisos de cada app se crean en su propio
        # post_migrate, y la última llamada ya los encuentra todos.
        post_migrate.connect(configurar_grupo_supervisores, dispatch_uid='sigver_grupo_supervisores')
