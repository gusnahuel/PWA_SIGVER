"""
SIGVER - Tests de acceso al admin: grupo de supervisores, inmutabilidad
de las verificaciones y ficha de Personal en el usuario.
"""
import uuid

from django.contrib.admin.sites import site as admin_site
from django.contrib.auth.models import Group
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone

from django.contrib.gis.geos import Point

from apps.inventario.models import Alimentador, Componente, Personal, Sitio, SubEstacion
from apps.operaciones.models import Reclamo, Verificacion

from .models import Usuario
from .permisos import GRUPO_SUPERVISORES


class GrupoSupervisoresTests(TestCase):
    def test_grupo_existe_con_permisos_justos(self):
        grupo = Group.objects.get(name=GRUPO_SUPERVISORES)
        codenames = set(grupo.permissions.values_list('codename', flat=True))
        self.assertIn('change_reclamo', codenames)
        self.assertIn('view_verificacion', codenames)
        self.assertIn('change_sitio', codenames)
        self.assertNotIn('change_verificacion', codenames)
        self.assertNotIn('delete_reclamo', codenames)
        self.assertFalse(any(c.endswith('_usuario') for c in codenames))

    def test_supervisor_recibe_admin_y_grupo_automaticamente(self):
        u = Usuario.objects.create_user('sup', password='x', rol='supervisor_zona')
        self.assertTrue(u.is_staff)
        self.assertTrue(u.groups.filter(name=GRUPO_SUPERVISORES).exists())
        self.assertTrue(u.has_perm('operaciones.change_reclamo'))

    def test_cambiar_rol_quita_admin_y_grupo(self):
        u = Usuario.objects.create_user('sup', password='x', rol='supervisor_zona')
        u.rol = 'tecnico_campo'
        u.save()
        u.refresh_from_db()
        self.assertFalse(u.is_staff)
        self.assertFalse(u.groups.filter(name=GRUPO_SUPERVISORES).exists())

    def test_tecnico_no_entra_al_admin_aunque_marquen_staff(self):
        u = Usuario.objects.create_user('tec', password='x', rol='tecnico_campo', is_staff=True)
        self.assertFalse(u.is_staff)

    def test_superusuario_conserva_admin(self):
        u = Usuario.objects.create_superuser('root', password='x')
        self.assertTrue(u.is_staff)

    def test_formulario_del_admin_no_borra_el_grupo(self):
        u = Usuario.objects.create_user('sup', password='x', rol='supervisor_zona')

        class FormularioFalso:
            instance = u

            def save_m2m(self):  # como hace el admin con la casilla de grupos vacía
                u.groups.clear()

        request = RequestFactory().post('/')
        admin_site._registry[Usuario].save_related(request, FormularioFalso(), [], True)
        self.assertTrue(u.groups.filter(name=GRUPO_SUPERVISORES).exists())


class AdminSupervisorTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.supervisor = Usuario.objects.create_user('sup', password='x', rol='supervisor_zona')
        cls.admin_eam = Usuario.objects.create_superuser('eam', password='x', rol='admin_eam')
        alim = Alimentador.objects.create(codigo='A_01', subestacion=SubEstacion.objects.create(codigo='SE'))
        cls.sitio = Sitio.objects.create(id_sitio='S-1', alimentador=alim, ubicacion_base=Point(-56.2, -27.1))
        componente = Componente.objects.create(id_componente='COMP-1', sitio=cls.sitio)
        tecnico = Personal.objects.create(id_personal='PER-9', nombre_completo='Técnico')
        cls.verificacion = Verificacion.objects.create(
            id_verificacion='VER-1', sitio=cls.sitio, fecha_verificacion=timezone.now(), componente=componente, responsable=tecnico, client_uuid=uuid.uuid4(),
        )
        cls.reclamo = Reclamo.objects.create(id_reclamo='REC-1', descripcion='x')

    def _request(self, user):
        request = RequestFactory().get('/')
        request.user = user
        return request

    def test_supervisor_ve_pero_no_edita_ni_borra_verificaciones(self):
        ma = admin_site._registry[Verificacion]
        req = self._request(self.supervisor)
        self.assertTrue(ma.has_view_permission(req, self.verificacion))
        self.assertFalse(ma.has_change_permission(req, self.verificacion))
        self.assertFalse(ma.has_delete_permission(req, self.verificacion))
        self.assertFalse(ma.has_add_permission(req))

    def test_post_del_supervisor_a_una_verificacion_es_rechazado(self):
        self.client.force_login(self.supervisor)
        url = reverse('admin:operaciones_verificacion_change', args=[self.verificacion.pk])
        self.assertEqual(self.client.get(url).status_code, 200)  # la ve en solo lectura
        self.assertEqual(self.client.post(url, {'estado_sitio': 'otro'}).status_code, 403)
        url_borrar = reverse('admin:operaciones_verificacion_delete', args=[self.verificacion.pk])
        self.assertEqual(self.client.post(url_borrar, {'post': 'yes'}).status_code, 403)
        self.assertTrue(Verificacion.objects.filter(pk=self.verificacion.pk).exists())

    def test_admin_eam_puede_corregir_verificaciones(self):
        ma = admin_site._registry[Verificacion]
        self.assertTrue(ma.has_change_permission(self._request(self.admin_eam), self.verificacion))

    def test_supervisor_no_reescribe_los_datos_de_origen_del_reclamo(self):
        ma = admin_site._registry[Reclamo]
        req = self._request(self.supervisor)
        self.assertTrue(ma.has_change_permission(req, self.reclamo))
        campos = ma.get_readonly_fields(req, self.reclamo)
        for campo in ('id_reclamo', 'descripcion', 'observaciones_cierre', 'vista_origen'):
            self.assertIn(campo, campos)
        self.assertNotIn('agencia_responsable', campos)
        self.assertNotIn('estado', campos)
        # El origen y la evidencia del técnico ni siquiera son campos del formulario
        editables = {c for _, opciones in ma.get_fieldsets(req, self.reclamo) for c in opciones['fields']} - set(campos)
        for campo in ('verificacion', 'componente', 'foto_evidencia_antes', 'foto_evidencia_despues'):
            self.assertNotIn(campo, editables)

    def test_supervisor_no_ve_usuarios(self):
        self.client.force_login(self.supervisor)
        self.assertEqual(self.client.get(reverse('admin:usuarios_usuario_changelist')).status_code, 403)

    def test_paginas_principales_del_supervisor_cargan(self):
        self.client.force_login(self.supervisor)
        for nombre in ('operaciones_reclamo', 'operaciones_verificacion', 'inventario_personal',
                       'inventario_sitio'):
            self.assertEqual(self.client.get(reverse(f'admin:{nombre}_changelist')).status_code, 200, nombre)
        res = self.client.get(reverse('admin:operaciones_reclamo_change', args=[self.reclamo.pk]))
        self.assertEqual(res.status_code, 200)


    def test_inicio_muestra_bandejas_del_supervisor(self):
        self.client.force_login(self.supervisor)
        res = self.client.get(reverse('admin:index'))
        self.assertContains(res, 'Bandejas de trabajo')
        self.assertContains(res, '?bandeja=sin_agencia')
        self.assertContains(res, self.sitio.id_sitio)  # aparece en «Últimas verificaciones»

    def test_filtro_bandeja_sin_agencia(self):
        self.client.force_login(self.supervisor)
        url = reverse('admin:operaciones_reclamo_changelist')
        self.assertContains(self.client.get(url + '?bandeja=sin_agencia'), 'REC-1')
        self.assertNotContains(self.client.get(url + '?bandeja=validar'), 'REC-1')


class PersonalEnUsuarioTests(TestCase):
    def setUp(self):
        self.admin_eam = Usuario.objects.create_superuser('root', password='x')
        self.client.force_login(self.admin_eam)
        self.tecnico = Usuario.objects.create_user('tec', password='x', rol='tecnico_campo')
        Personal.objects.create(id_personal='PER-1', nombre_completo='Con usuario', usuario=self.tecnico)
        Personal.objects.create(id_personal='PER-2', nombre_completo='Sin usuario')

    def test_ficha_de_usuario_muestra_su_personal(self):
        res = self.client.get(reverse('admin:usuarios_usuario_change', args=[self.tecnico.pk]))
        self.assertContains(res, 'PER-1')
        self.assertContains(res, 'Ficha de Personal')

    def test_filtro_personal_sin_usuario(self):
        res = self.client.get(reverse('admin:inventario_personal_changelist') + '?acceso=no')
        self.assertContains(res, 'PER-2')
        self.assertNotContains(res, 'PER-1')


class SeguridadLoginTests(TestCase):
    """Bloqueo por intentos fallidos, límite por IP, rotación y revocación de tokens."""

    def setUp(self):
        from django.core.cache import cache
        cache.clear()  # el bloqueo y el throttling viven en el caché
        self.user = Usuario.objects.create_user('tec', password='Clave-segura-1', rol='tecnico_campo')
        self.url = reverse('token_obtain_pair')

    def _login(self, password, ip='10.0.0.1', username='tec'):
        return self.client.post(self.url, {'username': username, 'password': password},
                                content_type='application/json', REMOTE_ADDR=ip)

    def test_cinco_fallos_bloquean_aunque_despues_acierte(self):
        for _ in range(5):
            self.assertEqual(self._login('mala').status_code, 401)
        res = self._login('Clave-segura-1')
        self.assertEqual(res.status_code, 429)
        self.assertIn('15 minutos', res.json()['detail'])

    def test_el_bloqueo_es_por_ip(self):
        for _ in range(5):
            self._login('mala', ip='10.0.0.1')
        # El técnico legítimo, desde su celular (otra IP), sigue pudiendo entrar
        self.assertEqual(self._login('Clave-segura-1', ip='10.0.0.2').status_code, 200)

    def test_acertar_reinicia_la_cuenta(self):
        for _ in range(4):
            self._login('mala')
        self.assertEqual(self._login('Clave-segura-1').status_code, 200)
        for _ in range(4):
            self._login('mala')
        self.assertEqual(self._login('Clave-segura-1').status_code, 200)

    def test_detras_de_nginx_usa_la_ip_real(self):
        # El cliente puede inventar X-Forwarded-For; nginx agrega la real al final
        for _ in range(5):
            self.client.post(self.url, {'username': 'tec', 'password': 'mala'}, content_type='application/json',
                             REMOTE_ADDR='172.18.0.5', HTTP_X_FORWARDED_FOR='1.1.1.1, 200.1.1.1')
        res = self.client.post(self.url, {'username': 'tec', 'password': 'Clave-segura-1'},
                               content_type='application/json',
                               REMOTE_ADDR='172.18.0.5', HTTP_X_FORWARDED_FOR='9.9.9.9, 200.1.1.1')
        self.assertEqual(res.status_code, 429)

    def test_limite_de_pedidos_por_ip(self):
        # Probando muchos usuarios distintos desde la misma IP
        codigos = [self._login('mala', username=f'u{i}').status_code for i in range(11)]
        self.assertEqual(codigos[-1], 429)

    def test_admin_bloqueado_muestra_el_motivo(self):
        Usuario.objects.create_user('sup', password='Clave-segura-1', rol='supervisor_zona')
        url = reverse('admin:login')
        for _ in range(5):
            self.client.post(url, {'username': 'sup', 'password': 'mala'})
        res = self.client.post(url, {'username': 'sup', 'password': 'Clave-segura-1'})
        self.assertContains(res, 'Demasiados intentos fallidos')
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_rotacion_revoca_el_refresh_anterior(self):
        refresh = self._login('Clave-segura-1').json()['refresh']
        url = reverse('token_refresh')
        res = self.client.post(url, {'refresh': refresh}, content_type='application/json')
        self.assertEqual(res.status_code, 200)
        self.assertIn('refresh', res.json())
        self.assertNotEqual(res.json()['refresh'], refresh)
        # El refresh viejo ya no sirve
        self.assertEqual(self.client.post(url, {'refresh': refresh}, content_type='application/json').status_code, 401)

    def test_logout_revoca_el_refresh(self):
        refresh = self._login('Clave-segura-1').json()['refresh']
        res = self.client.post(reverse('token_logout'), {'refresh': refresh}, content_type='application/json')
        self.assertEqual(res.status_code, 200)
        res = self.client.post(reverse('token_refresh'), {'refresh': refresh}, content_type='application/json')
        self.assertEqual(res.status_code, 401)
