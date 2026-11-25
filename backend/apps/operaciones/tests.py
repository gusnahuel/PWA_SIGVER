"""
SIGVER - Tests de Operaciones (verificaciones, sincronización offline y reclamos)
"""
import io
import json
import shutil
import tempfile
import uuid

from django.contrib.admin.sites import site as admin_site
from django.contrib.gis.geos import Point
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image
from rest_framework.test import APIClient

from apps.inventario.models import (
    Agencia, Alimentador, Componente, EquipoETC, Personal, SeccionRegional, SubEstacion, Sitio,
)
from apps.usuarios.models import Usuario
from . import reclamos
from .models import (
    EnsayoPAT, HistorialReclamo, LecturaPAT, MedicionTermografia, PuntoInspeccionTermografia,
    Reclamo, Verificacion, VerificacionETC,
)


class BaseSigverTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        seccion = SeccionRegional.objects.create(nombre='Test Sección', codigo='TST')
        cls.agencia = Agencia.objects.create(id_seccion='TST/01', nombre='Agencia Test', seccion_regional=seccion)
        cls.otra_agencia = Agencia.objects.create(id_seccion='TST/02', nombre='Otra', seccion_regional=seccion)
        sub = SubEstacion.objects.create(codigo='TSTSE')
        alim = Alimentador.objects.create(codigo='TSTSE_01', subestacion=sub)
        cls.sitio = Sitio.objects.create(
            id_sitio='SIT-TST-1', alimentador=alim, agencia=cls.agencia,
            ubicacion_base=Point(-56.2, -27.1),
        )
        cls.componente = Componente.objects.create(id_componente='COMP-TST-1', sitio=cls.sitio)
        cls.equipo = EquipoETC.objects.create(nro_equipo='TST-99', alimentador=alim, ubicacion=Point(-56.2, -27.1))
        cls.punto, _ = PuntoInspeccionTermografia.objects.get_or_create(
            id_punto='P-TST', defaults={'fase': 'R', 'tipo_elemento': 'Bushing', 'lado_conexion': 'Fuente'},
        )

        cls.tecnico = Usuario.objects.create_user('tecnico', password='x', rol='tecnico_campo')
        cls.personal_tecnico = Personal.objects.create(
            id_personal='PER-T1', nombre_completo='Técnico Uno', agencia=cls.agencia, usuario=cls.tecnico,
        )
        cls.otro_tecnico = Usuario.objects.create_user('tecnico2', password='x', rol='tecnico_campo')
        cls.personal_otro = Personal.objects.create(
            id_personal='PER-T2', nombre_completo='Técnico Dos', agencia=cls.otra_agencia, usuario=cls.otro_tecnico,
        )
        cls.supervisor = Usuario.objects.create_user('super', password='x', rol='supervisor_zona')
        cls.supervisor.agencias_asignadas.add(cls.agencia)
        cls.consulta = Usuario.objects.create_user('consulta', password='x', rol='consulta')
        cls.sin_personal = Usuario.objects.create_user('huerfano', password='x', rol='tecnico_campo')

    def cliente(self, user):
        c = APIClient()
        c.force_authenticate(user)
        return c

    def datos_regulador(self, **extra):
        datos = {
            'id_verificacion': f'VERIF-REG-{uuid.uuid4().hex[:8]}',
            'client_uuid': str(uuid.uuid4()),
            'componente': str(self.componente.id),
            'fecha_verificacion': timezone.now().isoformat(),
            'estado_sitio': 'NORMAL',
            'requiere_reclamo': 'false',
            'prioridad': '',
        }
        datos.update(extra)
        return datos


class VerificacionReguladorTests(BaseSigverTest):
    url = '/api/operaciones/verificaciones/'

    def test_multipart_guarda_termografias_y_pat(self):
        """Antes, las listas anidadas enviadas como JSON en FormData se descartaban en silencio."""
        termos = [{
            'id_medicion': 'TERM-TST-1', 'punto': 'P-TST', 'fecha_hora': timezone.now().isoformat(),
            'temperatura_punto_c': 45.5, 'temperatura_ambiente_c': 30, 'delta_temperatura_c': 15.5,
            'nivel_termografico': 'Nivel 1',
        }]
        ensayos = [{
            'id_ensayo': 'PAT-TST-1', 'fecha_ensayo': timezone.now().isoformat(), 'resultado': 'CONFORME',
            'condicion_suelo': 'Seco',
            'lecturas': [
                {'id_lectura': 'LECT-TST-1', 'tipo_lectura': 'MEDICION', 'distancia_m': 10, 'valor_ohm': 4.2},
                {'id_lectura': 'LECT-TST-2', 'tipo_lectura': 'MEDICION', 'distancia_m': 20, 'valor_ohm': 5.1},
            ],
        }]
        datos = self.datos_regulador(
            mediciones_termografia=json.dumps(termos), ensayos_pat=json.dumps(ensayos),
        )
        res = self.cliente(self.tecnico).post(self.url, datos, format='multipart')
        self.assertEqual(res.status_code, 201, res.data)

        verif = Verificacion.objects.get(client_uuid=datos['client_uuid'])
        self.assertEqual(verif.sitio, self.sitio)
        self.assertEqual(MedicionTermografia.objects.filter(verificacion=verif).count(), 1)
        ensayo = EnsayoPAT.objects.get(verificacion=verif)
        self.assertEqual(LecturaPAT.objects.filter(ensayo=ensayo).count(), 2)

    def test_reenvio_con_mismo_client_uuid_es_idempotente(self):
        datos = self.datos_regulador()
        c = self.cliente(self.tecnico)
        self.assertEqual(c.post(self.url, datos, format='multipart').status_code, 201)
        res = c.post(self.url, datos, format='multipart')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(Verificacion.objects.filter(client_uuid=datos['client_uuid']).count(), 1)

    def test_error_anidado_no_deja_registros_a_medias(self):
        termos = [{'id_medicion': 'TERM-X', 'punto': 'NO-EXISTE', 'fecha_hora': timezone.now().isoformat()}]
        datos = self.datos_regulador(mediciones_termografia=json.dumps(termos))
        res = self.cliente(self.tecnico).post(self.url, datos, format='multipart')
        self.assertEqual(res.status_code, 400)
        self.assertFalse(Verificacion.objects.filter(client_uuid=datos['client_uuid']).exists())

    def test_responsable_se_toma_del_usuario_autenticado(self):
        datos = self.datos_regulador(responsable=str(self.personal_otro.id))
        res = self.cliente(self.tecnico).post(self.url, datos, format='multipart')
        self.assertEqual(res.status_code, 201, res.data)
        verif = Verificacion.objects.get(client_uuid=datos['client_uuid'])
        self.assertEqual(verif.responsable, self.personal_tecnico)
        self.assertEqual(verif.agencia_responsable, self.agencia)

    def test_responsable_null_en_formdata(self):
        datos = self.datos_regulador(responsable='null')
        res = self.cliente(self.tecnico).post(self.url, datos, format='multipart')
        self.assertEqual(res.status_code, 201, res.data)

    def test_usuario_sin_personal_recibe_error_claro(self):
        res = self.cliente(self.sin_personal).post(self.url, self.datos_regulador(), format='multipart')
        self.assertEqual(res.status_code, 400)
        self.assertIn('responsable', res.data)

    def test_rol_consulta_no_puede_crear(self):
        res = self.cliente(self.consulta).post(self.url, self.datos_regulador(), format='multipart')
        self.assertEqual(res.status_code, 403)

    def test_verificaciones_no_se_pueden_borrar_por_api(self):
        datos = self.datos_regulador()
        c = self.cliente(self.tecnico)
        c.post(self.url, datos, format='multipart')
        verif = Verificacion.objects.get(client_uuid=datos['client_uuid'])
        self.assertEqual(c.delete(f'{self.url}{verif.id}/').status_code, 405)

    def test_reclamo_automatico(self):
        datos = self.datos_regulador(requiere_reclamo='true', prioridad='ALTA')
        res = self.cliente(self.tecnico).post(self.url, datos, format='multipart')
        self.assertEqual(res.status_code, 201, res.data)
        reclamo = Reclamo.objects.get(id_reclamo=f"REC-REG-{datos['id_verificacion']}")
        self.assertEqual(reclamo.prioridad, 'ALTA')
        self.assertEqual(reclamo.agencia_responsable, self.sitio.agencia)
        # Nace sin técnico: lo asigna el supervisor (quien verifica no siempre repara)
        self.assertIsNone(reclamo.responsable_asignado)
        self.assertEqual(reclamo.estado, 'ABIERTO')
        self.assertEqual(reclamo.verificacion.id_verificacion, datos['id_verificacion'])
        self.assertEqual(reclamo.historial.get().usuario, self.tecnico)


class VerificacionETCTests(BaseSigverTest):
    url = '/api/operaciones/verificaciones-etc/'

    def test_crear_actualiza_estado_del_equipo(self):
        datos = {
            'id_verificacion': 'VERIF-ETC-TST', 'client_uuid': str(uuid.uuid4()),
            'equipo_etc': str(self.equipo.id), 'fecha_verificacion': timezone.now().isoformat(),
            'tiene_inconveniente': 'true', 'observaciones': 'x', 'requiere_reclamo': 'false', 'prioridad': '',
        }
        res = self.cliente(self.tecnico).post(self.url, datos, format='multipart')
        self.assertEqual(res.status_code, 201, res.data)
        self.equipo.refresh_from_db()
        self.assertTrue(self.equipo.tiene_problema_actual)
        self.assertIsNotNone(self.equipo.fecha_ultima_verificacion)
        self.assertEqual(VerificacionETC.objects.get(client_uuid=datos['client_uuid']).responsable,
                         self.personal_tecnico)

    def test_reclamo_de_etc_queda_vinculado_al_equipo(self):
        datos = {
            'id_verificacion': 'VERIF-ETC-REC', 'client_uuid': str(uuid.uuid4()),
            'equipo_etc': str(self.equipo.id), 'fecha_verificacion': timezone.now().isoformat(),
            'tiene_inconveniente': 'true', 'observaciones': 'x', 'requiere_reclamo': 'true', 'prioridad': 'ALTA',
        }
        res = self.cliente(self.tecnico).post(self.url, datos, format='multipart')
        self.assertEqual(res.status_code, 201, res.data)
        reclamo = Reclamo.objects.get(id_reclamo='REC-ETC-VERIF-ETC-REC')
        self.assertEqual(reclamo.equipo_etc, self.equipo)
        self.assertEqual(reclamo.verificacion_etc.client_uuid, uuid.UUID(datos['client_uuid']))
        self.assertEqual(self.equipo.reclamos.count(), 1)
        entrada = reclamo.historial.get()
        self.assertEqual((entrada.estado_nuevo, entrada.usuario), ('ABIERTO', self.tecnico))


class ReclamoPermisosTests(BaseSigverTest):
    url = '/api/operaciones/reclamos/'

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.reclamo_propio = Reclamo.objects.create(
            id_reclamo='REC-1', descripcion='a', agencia_responsable=cls.agencia,
            responsable_asignado=cls.personal_tecnico,
        )
        cls.reclamo_ajeno = Reclamo.objects.create(
            id_reclamo='REC-2', descripcion='b', agencia_responsable=cls.otra_agencia,
            responsable_asignado=cls.personal_otro,
        )

    def ids(self, res):
        return {r['id_reclamo'] for r in res.data['results']}

    def test_tecnico_solo_ve_sus_reclamos(self):
        res = self.cliente(self.tecnico).get(self.url)
        self.assertEqual(self.ids(res), {'REC-1'})

    def test_supervisor_ve_los_de_su_agencia(self):
        res = self.cliente(self.supervisor).get(self.url)
        self.assertEqual(self.ids(res), {'REC-1'})

    def test_supervisor_ve_los_que_no_tienen_agencia(self):
        Reclamo.objects.create(id_reclamo='REC-SIN', descripcion='c')
        res = self.cliente(self.supervisor).get(self.url)
        self.assertEqual(self.ids(res), {'REC-1', 'REC-SIN'})
        # un técnico no los ve si no están asignados a él
        self.assertEqual(self.ids(self.cliente(self.tecnico).get(self.url)), {'REC-1'})

    def test_tecnico_no_puede_resolver_directamente(self):
        # Segregación de funciones: resolver o cerrar es tarea del supervisor
        res = self.cliente(self.tecnico).patch(
            f'{self.url}{self.reclamo_propio.id}/',
            {'estado': 'CERRADO', 'fecha_ejecucion': timezone.now().isoformat()}, format='json',
        )
        self.assertEqual(res.status_code, 403)

    def test_tecnico_no_puede_tocar_reclamo_ajeno(self):
        res = self.cliente(self.tecnico).patch(
            f'{self.url}{self.reclamo_ajeno.id}/', {'estado': 'EN_PROCESO'}, format='json',
        )
        self.assertEqual(res.status_code, 404)

    def test_tecnico_no_puede_cerrar_ni_reasignar(self):
        c = self.cliente(self.tecnico)
        url = f'{self.url}{self.reclamo_propio.id}/'
        self.assertEqual(c.patch(url, {'estado': 'CERRADO'}, format='json').status_code, 403)
        self.assertEqual(
            c.patch(url, {'responsable_asignado': str(self.personal_otro.id)}, format='json').status_code, 403,
        )
        self.assertEqual(c.delete(url).status_code, 405)

    def test_filtro_con_uuid_invalido_no_rompe(self):
        res = self.cliente(self.tecnico).get(self.url + '?responsable_asignado=null')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(self.ids(res), set())


def imagen_de_prueba(nombre='evidencia.jpg'):
    buffer = io.BytesIO()
    Image.new('RGB', (10, 10), 'blue').save(buffer, format='JPEG')
    return SimpleUploadedFile(nombre, buffer.getvalue(), content_type='image/jpeg')


class ReclamoValidacionTests(BaseSigverTest):
    """Flujo: el técnico envía el trabajo a validación con foto; el supervisor cierra en el admin."""
    url = '/api/operaciones/reclamos/'

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._media = tempfile.mkdtemp()
        cls._override = override_settings(MEDIA_ROOT=cls._media)
        cls._override.enable()

    @classmethod
    def tearDownClass(cls):
        cls._override.disable()
        shutil.rmtree(cls._media, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        self.reclamo = Reclamo.objects.create(
            id_reclamo='REC-VAL', descripcion='x', agencia_responsable=self.agencia,
            responsable_asignado=self.personal_tecnico, estado='EN_PROCESO',
        )
        self.detalle = f'{self.url}{self.reclamo.id}/'

    def enviar_a_validacion(self, user=None, **extra):
        datos = {
            'estado': 'PENDIENTE_VALIDACION',
            'observaciones_cierre': 'Se ajustó la conexión',
            'fecha_ejecucion': timezone.now().isoformat(),
            'foto_evidencia_despues': imagen_de_prueba(),
        }
        datos.update(extra)
        datos = {k: v for k, v in datos.items() if v is not None}
        return self.cliente(user or self.tecnico).patch(self.detalle, datos, format='multipart')

    def test_tecnico_envia_a_validacion_con_foto(self):
        res = self.enviar_a_validacion()
        self.assertEqual(res.status_code, 200, res.data)
        self.reclamo.refresh_from_db()
        self.assertEqual(self.reclamo.estado, 'PENDIENTE_VALIDACION')
        self.assertEqual(self.reclamo.observaciones_cierre, 'Se ajustó la conexión')
        self.assertTrue(self.reclamo.foto_evidencia_despues)
        self.assertIsNotNone(self.reclamo.fecha_ejecucion)

    def test_sin_foto_se_rechaza(self):
        res = self.enviar_a_validacion(foto_evidencia_despues=None)
        self.assertEqual(res.status_code, 400)
        self.assertIn('foto_evidencia_despues', res.data)
        self.reclamo.refresh_from_db()
        self.assertEqual(self.reclamo.estado, 'EN_PROCESO')

    def test_tecnico_no_modifica_reclamo_cerrado(self):
        self.reclamo.estado = 'CERRADO'
        self.reclamo.save()
        res = self.enviar_a_validacion()
        self.assertEqual(res.status_code, 403)

    def test_admin_valida_y_cierra(self):
        self.enviar_a_validacion()
        otro = Reclamo.objects.create(id_reclamo='REC-ABIERTO', descripcion='y', agencia_responsable=self.agencia)
        admin_user = Usuario.objects.create_superuser('jefe_admin', password='x')
        request = RequestFactory().post('/admin/')
        request.user = admin_user
        request._messages = type('M', (), {'add': lambda *a, **k: None})()
        modelo_admin = admin_site._registry[Reclamo]

        modelo_admin.validar_y_cerrar(request, Reclamo.objects.filter(id__in=[self.reclamo.id, otro.id]))

        self.reclamo.refresh_from_db()
        otro.refresh_from_db()
        self.assertEqual(self.reclamo.estado, 'CERRADO')
        self.assertIsNotNone(self.reclamo.fecha_cierre)
        self.assertEqual(self.reclamo.validado_por, admin_user)
        self.assertEqual(otro.estado, 'ABIERTO')  # solo se cierran los pendientes de validación
        ultimo = self.reclamo.historial.last()
        self.assertEqual((ultimo.estado_anterior, ultimo.estado_nuevo, ultimo.usuario),
                         ('PENDIENTE_VALIDACION', 'CERRADO', admin_user))


class ReclamoReglasTests(BaseSigverTest):
    """Máquina de estados de apps/operaciones/reclamos.py, por API y por admin."""
    url = '/api/operaciones/reclamos/'

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._media = tempfile.mkdtemp()
        cls._override = override_settings(MEDIA_ROOT=cls._media)
        cls._override.enable()

    @classmethod
    def tearDownClass(cls):
        cls._override.disable()
        shutil.rmtree(cls._media, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        self.reclamo = reclamos.crear(None, id_reclamo='REC-R', descripcion='x', agencia_responsable=self.agencia)
        self.detalle = f'{self.url}{self.reclamo.id}/'
        # otro técnico de la misma agencia, para reasignar
        self.personal_tres = Personal.objects.create(
            id_personal='PER-T3', nombre_completo='Técnico Tres', agencia=self.agencia,
        )

    def patch(self, user, datos, formato='json'):
        return self.cliente(user).patch(self.detalle, datos, format=formato)

    def recargar(self):
        self.reclamo.refresh_from_db()
        return self.reclamo

    def llevar_a_validacion(self):
        self.patch(self.supervisor, {'responsable_asignado': str(self.personal_tecnico.id)})
        self.iniciar()
        res = self.patch(self.tecnico, {'estado': 'PENDIENTE_VALIDACION',
                                        'foto_evidencia_despues': imagen_de_prueba()}, 'multipart')
        self.assertEqual(res.status_code, 200, res.data)

    def iniciar(self):
        res = self.patch(self.tecnico, {'estado': 'EN_PROCESO', 'foto_evidencia_antes': imagen_de_prueba('antes.jpg')},
                         'multipart')
        self.assertEqual(res.status_code, 200, res.data)
        return res

    # --- Asignación ---
    def test_asignar_tecnico_pasa_a_asignado_y_registra(self):
        res = self.patch(self.supervisor, {'responsable_asignado': str(self.personal_tecnico.id)})
        self.assertEqual(res.status_code, 200, res.data)
        r = self.recargar()
        self.assertEqual(r.estado, 'ASIGNADO')
        self.assertIsNotNone(r.fecha_asignacion)
        entrada = r.historial.last()
        self.assertEqual((entrada.estado_anterior, entrada.estado_nuevo, entrada.usuario),
                         ('ABIERTO', 'ASIGNADO', self.supervisor))
        self.assertIn('Técnico Uno', entrada.detalle)
        # la respuesta ya trae el historial actualizado
        self.assertEqual(res.data['historial'][-1]['estado_nuevo'], 'ASIGNADO')

    def test_supervisor_no_asigna_tecnico_de_otra_agencia(self):
        res = self.patch(self.supervisor, {'responsable_asignado': str(self.personal_otro.id)})
        self.assertEqual(res.status_code, 400)
        self.assertIn('responsable_asignado', res.data)
        self.assertEqual(self.recargar().estado, 'ABIERTO')

    def test_supervisor_no_manda_reclamo_a_agencia_ajena(self):
        res = self.patch(self.supervisor, {'agencia_responsable': str(self.otra_agencia.id)})
        self.assertEqual(res.status_code, 400)
        self.assertIn('agencia_responsable', res.data)

    def test_sin_agencia_toma_la_del_tecnico(self):
        sin_agencia = Reclamo.objects.create(id_reclamo='REC-SA', descripcion='x')
        res = self.cliente(self.supervisor).patch(
            f'{self.url}{sin_agencia.id}/', {'responsable_asignado': str(self.personal_tecnico.id)}, format='json')
        self.assertEqual(res.status_code, 200, res.data)
        sin_agencia.refresh_from_db()
        self.assertEqual(sin_agencia.agencia_responsable, self.agencia)

    def test_reasignar_en_proceso_vuelve_a_asignado(self):
        self.patch(self.supervisor, {'responsable_asignado': str(self.personal_tecnico.id)})
        self.iniciar()
        self.assertEqual(self.recargar().estado, 'EN_PROCESO')
        self.patch(self.supervisor, {'responsable_asignado': str(self.personal_tres.id)})
        r = self.recargar()
        self.assertEqual((r.estado, r.responsable_asignado), ('ASIGNADO', self.personal_tres))
        # el técnico anterior ya no lo ve
        self.assertEqual(self.patch(self.tecnico, {'estado': 'EN_PROCESO'}).status_code, 404)

    # --- Validación ---
    def test_supervisor_no_cierra_sin_pasar_por_validacion(self):
        self.patch(self.supervisor, {'responsable_asignado': str(self.personal_tecnico.id)})
        res = self.patch(self.supervisor, {'estado': 'CERRADO'})
        self.assertEqual(res.status_code, 400)
        self.assertEqual(self.recargar().estado, 'ASIGNADO')

    def test_supervisor_no_envia_a_validacion_por_el_tecnico(self):
        self.patch(self.supervisor, {'responsable_asignado': str(self.personal_tecnico.id)})
        res = self.patch(self.supervisor, {'estado': 'PENDIENTE_VALIDACION',
                                           'foto_evidencia_despues': imagen_de_prueba()}, 'multipart')
        self.assertIn(res.status_code, (400, 403))   # ni siquiera el supervisor salta el «iniciar»
        self.assertEqual(self.recargar().estado, 'ASIGNADO')

    def test_validar_registra_quien_y_cuando(self):
        self.llevar_a_validacion()
        r = self.recargar()
        self.assertIsNotNone(r.fecha_ejecucion)
        res = self.patch(self.supervisor, {'estado': 'CERRADO', 'comentario': 'Conforme'})
        self.assertEqual(res.status_code, 200, res.data)
        r = self.recargar()
        self.assertEqual((r.estado, r.validado_por), ('CERRADO', self.supervisor))
        self.assertIsNotNone(r.fecha_validacion)
        self.assertEqual(r.historial.last().comentario, 'Conforme')
        estados = list(r.historial.values_list('estado_nuevo', flat=True))
        self.assertEqual(estados, ['ABIERTO', 'ASIGNADO', 'EN_PROCESO', 'PENDIENTE_VALIDACION', 'CERRADO'])

    def test_devolver_exige_motivo_y_pide_foto_nueva(self):
        self.llevar_a_validacion()
        res = self.patch(self.supervisor, {'estado': 'EN_PROCESO'})
        self.assertEqual(res.status_code, 400)
        self.assertIn('comentario', res.data)
        res = self.patch(self.supervisor, {'estado': 'EN_PROCESO', 'comentario': 'Falta foto del seccionador'})
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(self.recargar().historial.last().comentario, 'Falta foto del seccionador')
        # reenviar sin foto nueva no alcanza, aunque ya haya una anterior
        res = self.patch(self.tecnico, {'estado': 'PENDIENTE_VALIDACION'})
        self.assertEqual(res.status_code, 400)
        self.assertIn('foto_evidencia_despues', res.data)

    def test_tecnico_no_toca_lo_que_espera_validacion(self):
        self.llevar_a_validacion()
        res = self.patch(self.tecnico, {'observaciones_cierre': 'cambio'})
        self.assertEqual(res.status_code, 403)

    def test_supervisor_no_reescribe_la_evidencia_ni_el_origen(self):
        self.assertEqual(self.patch(self.supervisor, {'observaciones_cierre': 'otra'}).status_code, 403)
        self.assertEqual(self.patch(self.supervisor, {'origen_reclamo': 'EXTERNO'}).status_code, 403)
        self.assertEqual(self.patch(self.supervisor, {'fecha_cierre': timezone.now().isoformat()}).status_code, 200)
        self.assertIsNone(self.recargar().fecha_cierre)   # campo del sistema: se ignora

    # --- Rechazo, reapertura y borrado ---
    def test_rechazar_exige_motivo(self):
        self.assertEqual(self.patch(self.supervisor, {'estado': 'RECHAZADO'}).status_code, 400)
        res = self.patch(self.supervisor, {'estado': 'RECHAZADO', 'comentario': 'Duplicado de REC-1'})
        self.assertEqual(res.status_code, 200, res.data)
        r = self.recargar()
        self.assertEqual((r.estado, r.motivo_rechazo), ('RECHAZADO', 'Duplicado de REC-1'))
        self.assertIsNotNone(r.fecha_cierre)
        # terminado: el supervisor ya no lo modifica
        self.assertEqual(self.patch(self.supervisor, {'prioridad': 'ALTA'}).status_code, 403)

    def test_solo_admin_eam_reabre(self):
        self.patch(self.supervisor, {'estado': 'RECHAZADO', 'comentario': 'No corresponde'})
        self.assertEqual(self.patch(self.supervisor, {'estado': 'ABIERTO', 'comentario': 'x'}).status_code, 403)
        admin_eam = Usuario.objects.create_user('eam', password='x', rol='admin_eam')
        self.assertEqual(self.patch(admin_eam, {'estado': 'ABIERTO'}).status_code, 400)  # sin motivo
        res = self.patch(admin_eam, {'estado': 'ABIERTO', 'comentario': 'Se rechazó por error'})
        self.assertEqual(res.status_code, 200, res.data)
        r = self.recargar()
        self.assertEqual(r.estado, 'ABIERTO')
        self.assertIsNone(r.fecha_cierre)

    def test_nadie_borra_por_api(self):
        self.assertEqual(self.cliente(self.supervisor).delete(self.detalle).status_code, 405)
        self.assertTrue(Reclamo.objects.filter(pk=self.reclamo.pk).exists())

    # --- Creación manual ---
    def test_supervisor_crea_en_su_zona(self):
        c = self.cliente(self.supervisor)
        res = c.post(self.url, {'descripcion': 'Poste inclinado', 'responsable_asignado': str(self.personal_tecnico.id),
                                'estado': 'CERRADO'}, format='json')
        self.assertEqual(res.status_code, 201, res.data)
        nuevo = Reclamo.objects.get(pk=res.data['id'])
        self.assertEqual((nuevo.estado, nuevo.origen_reclamo, nuevo.agencia_responsable),
                         ('ASIGNADO', 'MANUAL', self.agencia))   # el estado pedido se ignora
        self.assertTrue(nuevo.id_reclamo.startswith('REC-MAN-'))
        self.assertEqual(nuevo.historial.get().usuario, self.supervisor)
        res = c.post(self.url, {'descripcion': 'x', 'agencia_responsable': str(self.otra_agencia.id)}, format='json')
        self.assertEqual(res.status_code, 400)

    def test_tecnico_no_crea(self):
        res = self.cliente(self.tecnico).post(self.url, {'descripcion': 'x'}, format='json')
        self.assertEqual(res.status_code, 403)

    # --- Iniciar trabajo (Fase 3) ---
    def test_iniciar_exige_foto_inicial_y_registra_la_hora(self):
        self.patch(self.supervisor, {'responsable_asignado': str(self.personal_tecnico.id)})
        res = self.patch(self.tecnico, {'estado': 'EN_PROCESO'})
        self.assertEqual(res.status_code, 400)
        self.assertIn('foto_evidencia_antes', res.data)
        self.iniciar()
        r = self.recargar()
        self.assertEqual(r.estado, 'EN_PROCESO')
        self.assertIsNotNone(r.fecha_inicio)
        self.assertTrue(r.foto_evidencia_antes)

    def test_no_se_finaliza_sin_iniciar(self):
        self.patch(self.supervisor, {'responsable_asignado': str(self.personal_tecnico.id)})
        res = self.patch(self.tecnico, {'estado': 'PENDIENTE_VALIDACION',
                                        'foto_evidencia_despues': imagen_de_prueba()}, 'multipart')
        self.assertEqual(res.status_code, 400)
        self.assertIn('iniciá el trabajo', str(res.data))

    def test_supervisor_no_inicia_por_el_tecnico(self):
        self.patch(self.supervisor, {'responsable_asignado': str(self.personal_tecnico.id)})
        self.assertEqual(self.patch(self.supervisor, {'estado': 'EN_PROCESO'}).status_code, 403)

    def test_devuelto_conserva_la_hora_de_inicio(self):
        self.llevar_a_validacion()
        inicio = self.recargar().fecha_inicio
        self.patch(self.supervisor, {'estado': 'EN_PROCESO', 'comentario': 'Repetir'})
        self.assertEqual(self.recargar().fecha_inicio, inicio)

    # --- Supervisor que trabaja en el campo ---
    def test_supervisor_asignado_ejecuta_pero_no_se_valida_a_si_mismo(self):
        ficha = Personal.objects.create(id_personal='PER-S1', nombre_completo='Supervisor Uno',
                                        agencia=self.agencia, usuario=self.supervisor)
        self.patch(self.supervisor, {'responsable_asignado': str(ficha.id)})
        # Inicia y finaliza como cualquier asignado (con las mismas fotos)
        res = self.patch(self.supervisor, {'estado': 'EN_PROCESO',
                                           'foto_evidencia_antes': imagen_de_prueba('antes.jpg')}, 'multipart')
        self.assertEqual(res.status_code, 200, res.data)
        res = self.patch(self.supervisor, {'estado': 'PENDIENTE_VALIDACION',
                                           'foto_evidencia_despues': imagen_de_prueba()}, 'multipart')
        self.assertEqual(res.status_code, 200, res.data)
        # Pero no aprueba su propio trabajo
        res = self.patch(self.supervisor, {'estado': 'CERRADO'})
        self.assertEqual(res.status_code, 403)
        self.assertIn('otro supervisor', str(res.data))
        otro = Usuario.objects.create_user('super2', password='x', rol='supervisor_zona')
        otro.agencias_asignadas.add(self.agencia)
        self.assertEqual(self.patch(otro, {'estado': 'CERRADO'}).status_code, 200)
        self.assertEqual(self.recargar().validado_por, otro)

    def test_quien_no_esta_asignado_recibe_un_mensaje_claro(self):
        self.patch(self.supervisor, {'responsable_asignado': str(self.personal_tecnico.id)})
        res = self.patch(self.supervisor, {'estado': 'EN_PROCESO',
                                           'foto_evidencia_antes': imagen_de_prueba('antes.jpg')}, 'multipart')
        self.assertEqual(res.status_code, 403)
        self.assertIn('asignado a otra persona', str(res.data))

    # --- GPS de la evidencia (Fase 3) ---
    def finalizar(self, **gps):
        self.patch(self.supervisor, {'responsable_asignado': str(self.personal_tecnico.id)})
        self.iniciar()
        datos = {'estado': 'PENDIENTE_VALIDACION', 'foto_evidencia_despues': imagen_de_prueba(), **gps}
        res = self.patch(self.tecnico, datos, 'multipart')
        self.assertEqual(res.status_code, 200, res.data)
        return self.recargar()

    def test_gps_en_el_lugar(self):
        self.reclamo.equipo_etc = self.equipo     # equipo en (-27.1, -56.2)
        self.reclamo.save()
        r = self.finalizar(gps_latitud=-27.1001, gps_longitud=-56.2, gps_precision_m=8.4)
        self.assertLessEqual(r.distancia_evidencia_m, 15)
        self.assertEqual(r.precision_evidencia_m, 8)
        self.assertIn('En el lugar', r.historial.last().detalle)

    def test_gps_lejos_del_equipo(self):
        self.reclamo.componente = self.componente   # sitio en (-27.1, -56.2)
        self.reclamo.save()
        r = self.finalizar(gps_latitud=-27.12, gps_longitud=-56.2)
        self.assertAlmostEqual(r.distancia_evidencia_m, 2215, delta=30)
        self.assertIn('Lejos (2,2 km)', r.historial.last().detalle)

    def test_sin_gps_se_envia_igual_y_queda_anotado(self):
        self.reclamo.equipo_etc = self.equipo
        self.reclamo.save()
        r = self.finalizar()
        self.assertIsNone(r.ubicacion_evidencia)
        self.assertIn('no informó GPS', r.historial.last().detalle)

    def test_gps_suelto_o_incompleto_se_rechaza(self):
        self.patch(self.supervisor, {'responsable_asignado': str(self.personal_tecnico.id)})
        self.iniciar()
        self.assertEqual(self.patch(self.tecnico, {'gps_latitud': -27.1, 'gps_longitud': -56.2}).status_code, 400)
        res = self.patch(self.tecnico, {'estado': 'PENDIENTE_VALIDACION', 'gps_latitud': -27.1,
                                        'foto_evidencia_despues': imagen_de_prueba()}, 'multipart')
        self.assertEqual(res.status_code, 400)

    # --- Admin: formulario ---
    def admin_eam_request(self):
        request = RequestFactory().post('/admin/')
        request.user = Usuario.objects.create_superuser('eam_form', password='x')
        return request

    def test_alta_manual_genera_numero_y_origen(self):
        ma = admin_site._registry[Reclamo]
        request = self.admin_eam_request()
        Formulario = ma.get_form(request, None)
        form = Formulario(data={'descripcion': 'Poste inclinado', 'prioridad': 'ALTA',
                                'equipo_etc': self.equipo.id, 'agencia_responsable': self.agencia.id})
        self.assertTrue(form.is_valid(), form.errors)
        self.assertNotIn('estado', form.fields)            # lo fija el sistema
        obj = form.save(commit=False)
        request._messages = type('M', (), {'add': lambda *a, **k: None})()
        ma.save_model(request, obj, form, change=False)
        nuevo = Reclamo.objects.get(descripcion='Poste inclinado')
        self.assertTrue(nuevo.id_reclamo.startswith('REC-MAN-'))
        self.assertEqual((nuevo.origen_reclamo, nuevo.estado), ('MANUAL', 'ABIERTO'))
        self.assertIsNotNone(nuevo.fecha_limite)
        self.assertEqual(nuevo.historial.get().estado_nuevo, 'ABIERTO')

    def test_alta_manual_exige_un_solo_equipo(self):
        ma = admin_site._registry[Reclamo]
        Formulario = ma.get_form(self.admin_eam_request(), None)
        sin_equipo = Formulario(data={'descripcion': 'x', 'prioridad': 'ALTA'})
        self.assertFalse(sin_equipo.is_valid())
        dos = Formulario(data={'descripcion': 'x', 'prioridad': 'ALTA', 'equipo_etc': self.equipo.id,
                               'componente': self.componente.id})
        self.assertFalse(dos.is_valid())
        self.assertIn('equipo_etc', dos.errors)

    def test_numero_de_reclamo_y_reasignacion_en_lista(self):
        ma = admin_site._registry[Reclamo]
        request = self.admin_eam_request()
        self.assertIn('id_reclamo', ma.get_readonly_fields(request, self.reclamo))   # ni siquiera admin EAM
        self.patch(self.supervisor, {'estado': 'RECHAZADO', 'comentario': 'Duplicado'})
        self.recargar()
        fila = ma.get_changelist_form(request)(instance=self.reclamo)
        self.assertTrue(fila.fields['responsable_asignado'].disabled)
        self.assertTrue(fila.fields['agencia_responsable'].disabled)

    # --- Admin ---
    def test_admin_usa_las_mismas_reglas(self):
        request = RequestFactory().get('/admin/')
        request.user = self.supervisor
        formulario = admin_site._registry[Reclamo].get_form(request, self.reclamo)
        datos = {f: getattr(self.reclamo, f) for f in ('id_reclamo', 'descripcion', 'origen_reclamo')}
        datos.update(estado='ABIERTO', agencia_responsable=self.agencia.id,
                     responsable_asignado=self.personal_otro.id, requiere_intervencion=True)
        form = formulario(data=datos, instance=self.reclamo)
        self.assertFalse(form.is_valid())
        self.assertIn('responsable_asignado', form.errors)
        # el desplegable de estados solo ofrece lo posible desde «Abierto»
        estados = {v for v, _ in form.fields['estado'].choices}
        self.assertNotIn('CERRADO', estados)
        self.assertNotIn('PENDIENTE_VALIDACION', estados)


class ReclamosDesdeVerificacionTests(BaseSigverTest):
    """Fase 2: sin duplicados, agencia del equipo, plazos y estado del mapa."""
    url_etc = '/api/operaciones/verificaciones-etc/'
    url_reg = '/api/operaciones/verificaciones/'

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._media = tempfile.mkdtemp()
        cls._override = override_settings(MEDIA_ROOT=cls._media)
        cls._override.enable()

    @classmethod
    def tearDownClass(cls):
        cls._override.disable()
        shutil.rmtree(cls._media, ignore_errors=True)
        super().tearDownClass()

    def verificar_etc(self, falla=True, reclamo=True, prioridad='ALTA', obs='x'):
        datos = {
            'id_verificacion': f'VERIF-{uuid.uuid4().hex[:8]}', 'client_uuid': str(uuid.uuid4()),
            'equipo_etc': str(self.equipo.id), 'fecha_verificacion': timezone.now().isoformat(),
            'tiene_inconveniente': str(falla).lower(), 'observaciones': obs,
            'requiere_reclamo': str(reclamo).lower(), 'prioridad': prioridad if reclamo else '',
        }
        res = self.cliente(self.tecnico).post(self.url_etc, datos, format='multipart')
        self.assertEqual(res.status_code, 201, res.data)
        self.equipo.refresh_from_db()
        return datos

    def cerrar(self, reclamo):
        """Recorrido completo: asignar, el técnico envía la foto, el supervisor valida."""
        reclamos.actualizar(reclamo, self.supervisor, {'responsable_asignado': self.personal_tecnico})
        reclamos.actualizar(reclamo, self.tecnico, {'estado': 'EN_PROCESO',
                                                    'foto_evidencia_antes': imagen_de_prueba('antes.jpg')})
        reclamos.actualizar(reclamo, self.tecnico, {'estado': 'PENDIENTE_VALIDACION',
                                                    'foto_evidencia_despues': imagen_de_prueba()})
        reclamos.actualizar(reclamo, self.supervisor, {'estado': 'CERRADO'})
        reclamo.refresh_from_db()
        return reclamo

    # --- Sin duplicados ---
    def test_segunda_verificacion_suma_al_reclamo_abierto(self):
        self.verificar_etc(prioridad='MEDIA')
        reclamo = self.equipo.reclamos.get()
        limite_original = reclamo.fecha_limite
        segunda = self.verificar_etc(prioridad='CRITICA', obs='sigue chispeando')
        self.assertEqual(self.equipo.reclamos.count(), 1)
        reclamo.refresh_from_db()
        self.assertEqual(reclamo.prioridad, 'CRITICA')
        self.assertLess(reclamo.fecha_limite, limite_original)   # plazo más corto
        entrada = reclamo.historial.last()
        self.assertIn(segunda['id_verificacion'], entrada.detalle)
        self.assertIn('Prioridad: Media → Crítica', entrada.detalle)
        self.assertEqual(entrada.comentario, 'Obs. de campo: sigue chispeando')

    def test_prioridad_menor_no_baja_la_del_reclamo(self):
        self.verificar_etc(prioridad='ALTA')
        self.verificar_etc(prioridad='BAJA')
        self.assertEqual(self.equipo.reclamos.get().prioridad, 'ALTA')

    def test_con_el_reclamo_cerrado_se_crea_uno_nuevo(self):
        self.verificar_etc()
        self.cerrar(self.equipo.reclamos.get())
        self.verificar_etc()
        self.assertEqual(self.equipo.reclamos.count(), 2)
        self.assertEqual(self.equipo.reclamos.filter(estado='ABIERTO').count(), 1)

    # --- Asignación inicial ---
    def test_nace_sin_tecnico_y_el_que_reporto_no_lo_ve(self):
        self.verificar_etc()
        reclamo = self.equipo.reclamos.get()
        self.assertIsNone(reclamo.responsable_asignado)
        res = self.cliente(self.tecnico).get('/api/operaciones/reclamos/')
        self.assertEqual(res.data['results'], [])
        # el supervisor sí, en su bandeja
        res = self.cliente(self.supervisor).get('/api/operaciones/reclamos/')
        self.assertEqual([r['id'] for r in res.data['results']], [str(reclamo.id)])

    def test_equipo_sin_agencia_toma_la_del_tecnico_y_lo_anota(self):
        self.verificar_etc()
        reclamo = self.equipo.reclamos.get()
        self.assertEqual(reclamo.agencia_responsable, self.agencia)
        self.assertIn('no tiene agencia cargada', reclamo.historial.get().detalle)

    def test_equipo_con_agencia_usa_la_suya(self):
        self.sitio.agencia = self.otra_agencia
        self.sitio.save()
        self.equipo.sitio = self.sitio
        self.equipo.save()
        self.verificar_etc()
        reclamo = self.equipo.reclamos.get()
        self.assertEqual(reclamo.agencia_responsable, self.otra_agencia)
        self.assertNotIn('no tiene agencia', reclamo.historial.get().detalle)

    # --- Plazos ---
    def test_plazo_segun_prioridad_y_recalculo(self):
        self.verificar_etc(prioridad='CRITICA')
        reclamo = self.equipo.reclamos.get()
        horas = (reclamo.fecha_limite - reclamo.fecha_reclamo).total_seconds() / 3600
        self.assertAlmostEqual(horas, 24, delta=0.1)
        reclamos.actualizar(reclamo, self.supervisor, {'prioridad': 'BAJA'})
        reclamo.refresh_from_db()
        self.assertEqual((reclamo.fecha_limite - reclamo.fecha_reclamo).days, 30)

    def test_bandeja_de_vencidos(self):
        from .admin import filtrar_bandeja
        self.verificar_etc()
        reclamo = self.equipo.reclamos.get()
        self.assertFalse(filtrar_bandeja(Reclamo.objects.all(), 'vencidos').exists())
        Reclamo.objects.filter(pk=reclamo.pk).update(fecha_limite=timezone.now() - timezone.timedelta(hours=1))
        self.assertTrue(filtrar_bandeja(Reclamo.objects.all(), 'vencidos').exists())

    # --- Mapa ---
    def test_etc_sigue_en_rojo_hasta_cerrar_el_reclamo(self):
        self.verificar_etc()
        self.assertTrue(self.equipo.tiene_problema_actual)
        # visita sin falla, pero el reclamo sigue abierto: no se apaga
        self.verificar_etc(falla=False, reclamo=False)
        self.assertTrue(self.equipo.tiene_problema_actual)
        reclamo = self.cerrar(self.equipo.reclamos.get())
        self.equipo.refresh_from_db()
        self.assertFalse(self.equipo.tiene_problema_actual)
        self.assertIn('deja de figurar con problema', reclamo.historial.last().detalle)

    def test_reabrir_vuelve_a_marcar_el_etc(self):
        self.verificar_etc()
        reclamo = self.cerrar(self.equipo.reclamos.get())
        admin_eam = Usuario.objects.create_user('eam2', password='x', rol='admin_eam')
        reclamos.actualizar(reclamo, admin_eam, {'estado': 'ABIERTO'}, 'Se validó por error')
        self.equipo.refresh_from_db()
        self.assertTrue(self.equipo.tiene_problema_actual)

    def test_regulador_actualiza_el_sitio_y_cerrar_lo_normaliza(self):
        datos = self.datos_regulador(estado_sitio='CRITICO', requiere_reclamo='true', prioridad='CRITICA')
        res = self.cliente(self.tecnico).post(self.url_reg, datos, format='multipart')
        self.assertEqual(res.status_code, 201, res.data)
        self.sitio.refresh_from_db()
        self.assertEqual(self.sitio.estado_general, 'CRITICO')
        reclamo = self.cerrar(Reclamo.objects.get(componente=self.componente))
        self.sitio.refresh_from_db()
        self.assertEqual(self.sitio.estado_general, 'NORMAL')
        self.assertIn('pasa a «Normal»', reclamo.historial.last().detalle)

    def test_verificacion_vieja_no_pisa_el_estado_del_sitio(self):
        c = self.cliente(self.tecnico)
        c.post(self.url_reg, self.datos_regulador(estado_sitio='OBSERVADO'), format='multipart')
        vieja = self.datos_regulador(estado_sitio='CRITICO',
                                     fecha_verificacion=(timezone.now() - timezone.timedelta(days=3)).isoformat())
        self.assertEqual(c.post(self.url_reg, vieja, format='multipart').status_code, 201)
        self.sitio.refresh_from_db()
        self.assertEqual(self.sitio.estado_general, 'OBSERVADO')


class IndicadoresTests(BaseSigverTest):
    """Fase 3: indicadores de gestión (apps/operaciones/indicadores.py)."""

    def nuevo(self, **campos):
        datos = dict(id_reclamo=f'REC-{uuid.uuid4().hex[:6]}', descripcion='x',
                     agencia_responsable=self.agencia, prioridad='ALTA')
        datos.update(campos)
        return reclamos.crear(None, **datos)

    def test_tiempos_plazo_devueltos_y_vencidos(self):
        from datetime import timedelta
        from . import indicadores
        ahora = timezone.now()
        # Cerrado en 10 h, ejecutado dentro del plazo (72 h), sin devoluciones
        a = self.nuevo()
        Reclamo.objects.filter(pk=a.pk).update(
            estado='CERRADO', fecha_reclamo=ahora - timedelta(hours=10), fecha_ejecucion=ahora - timedelta(hours=2),
            fecha_limite=ahora + timedelta(hours=62), fecha_validacion=ahora)
        reclamos.registrar(a, None, estado_anterior='EN_PROCESO', estado_nuevo='PENDIENTE_VALIDACION')
        # Cerrado en 30 h, ejecutado fuera de plazo, devuelto una vez
        b = self.nuevo()
        Reclamo.objects.filter(pk=b.pk).update(
            estado='CERRADO', fecha_reclamo=ahora - timedelta(hours=30), fecha_ejecucion=ahora - timedelta(hours=1),
            fecha_limite=ahora - timedelta(hours=5), fecha_validacion=ahora)
        reclamos.registrar(b, None, estado_anterior='EN_PROCESO', estado_nuevo='PENDIENTE_VALIDACION')
        reclamos.registrar(b, None, estado_anterior='PENDIENTE_VALIDACION', estado_nuevo='EN_PROCESO')
        # Vencido sin terminar, en otra agencia
        c = self.nuevo(agencia_responsable=self.otra_agencia)
        Reclamo.objects.filter(pk=c.pk).update(estado='ASIGNADO', fecha_limite=ahora - timedelta(hours=1))
        # Fuera del período de 30 días
        d = self.nuevo()
        Reclamo.objects.filter(pk=d.pk).update(fecha_reclamo=ahora - timedelta(days=60))

        ind = indicadores.calcular(Reclamo.objects.all(), '30', ahora=ahora)
        total = ind['total']
        self.assertEqual((total['recibidos'], total['cerrados']), (3, 2))
        self.assertEqual(total['tiempo_medio'], timedelta(hours=20))
        self.assertEqual(total['pct_en_plazo'], 50)
        self.assertEqual(total['pct_devueltos'], 50)
        self.assertEqual(ind['vencidos_ahora'], 1)
        alta = next(p for p in ind['por_prioridad'] if p['clave'] == 'ALTA')
        self.assertAlmostEqual(alta['uso_del_plazo'], 20 / 72)
        self.assertFalse(alta['excede_plazo'])
        agencias = {a['nombre']: a for a in ind['por_agencia']}
        self.assertEqual(agencias['Otra']['vencidos'], 1)
        self.assertEqual(agencias['Agencia Test']['cerrados'], 2)
        self.assertEqual(indicadores.calcular(Reclamo.objects.all(), 'todo', ahora=ahora)['total']['recibidos'], 4)

    def test_pagina_respeta_el_alcance_del_supervisor(self):
        self.nuevo()
        self.nuevo(agencia_responsable=self.otra_agencia)
        self.client.force_login(self.supervisor)
        res = self.client.get(reverse('admin:operaciones_reclamo_indicadores') + '?periodo=todo')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.context['ind']['total']['recibidos'], 1)
        self.client.force_login(self.tecnico)   # sin acceso al admin
        self.assertEqual(self.client.get(reverse('admin:operaciones_reclamo_indicadores')).status_code, 302)

    def test_texto_duracion(self):
        from datetime import timedelta
        from .indicadores import texto_duracion
        self.assertEqual(texto_duracion(timedelta(days=3, hours=4)), '3 d 4 h')
        self.assertEqual(texto_duracion(timedelta(hours=5, minutes=20)), '5 h')
        self.assertEqual(texto_duracion(timedelta(seconds=10)), '1 min')
        self.assertEqual(texto_duracion(None), '—')


class VerificacionDatosDeCampoTests(BaseSigverTest):
    """Auditoría: alcance por rol, datos que decide el servidor y coherencia."""
    url_etc = '/api/operaciones/verificaciones-etc/'
    url_reg = '/api/operaciones/verificaciones/'

    def etc(self, user=None, **extra):
        datos = {
            'id_verificacion': f'VERIF-{uuid.uuid4().hex[:8]}', 'client_uuid': str(uuid.uuid4()),
            'equipo_etc': str(self.equipo.id), 'fecha_verificacion': timezone.now().isoformat(),
            'tiene_inconveniente': 'false', 'observaciones': '', 'requiere_reclamo': 'false', 'prioridad': '',
        }
        datos.update(extra)
        return self.cliente(user or self.tecnico).post(self.url_etc, datos, format='multipart')

    def ids(self, res):
        return {v['id_verificacion'] for v in res.data['results']}

    # --- Alcance por rol ---
    def test_cada_rol_ve_solo_lo_suyo(self):
        propia = self.etc().data['id_verificacion']
        ajena = self.etc(self.otro_tecnico).data['id_verificacion']   # técnico de otra agencia
        self.assertEqual(self.ids(self.cliente(self.tecnico).get(self.url_etc)), {propia})
        self.assertEqual(self.ids(self.cliente(self.supervisor).get(self.url_etc)), {propia})
        self.assertEqual(self.ids(self.cliente(self.consulta).get(self.url_etc)), {propia, ajena})
        self.assertEqual(self.cliente(self.sin_personal).get(self.url_etc).data['results'], [])

    def test_personal_solo_el_propio_para_el_tecnico(self):
        res = self.cliente(self.tecnico).get('/api/operaciones/personal/')
        self.assertEqual([p['id_personal'] for p in res.data['results']], ['PER-T1'])
        res = self.cliente(self.supervisor).get('/api/operaciones/personal/')
        self.assertNotIn('PER-T2', [p['id_personal'] for p in res.data['results']])

    def test_pdf_de_otra_zona_no_se_descarga(self):
        ajena = VerificacionETC.objects.get(client_uuid=self.etc(self.otro_tecnico).data['client_uuid'])
        self.client.force_login(self.supervisor)
        self.assertEqual(self.client.get(reverse('generar_pdf', args=['etc', ajena.id])).status_code, 404)

    # --- Lo decide el servidor ---
    def test_la_agencia_es_la_del_tecnico(self):
        res = self.etc(agencia_responsable=str(self.otra_agencia.id))
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(VerificacionETC.objects.get(client_uuid=res.data['client_uuid']).agencia_responsable,
                         self.agencia)

    def test_fecha_del_celular_adelantada_o_muy_vieja(self):
        futura = (timezone.now() + timezone.timedelta(hours=2)).isoformat()
        res = self.etc(fecha_verificacion=futura)
        self.assertEqual(res.status_code, 400)
        self.assertIn('fecha_verificacion', res.data)
        vieja = (timezone.now() - timezone.timedelta(days=90)).isoformat()
        self.assertEqual(self.etc(fecha_verificacion=vieja).status_code, 400)
        # unos días en la cola sin señal es normal
        self.assertEqual(self.etc(fecha_verificacion=(timezone.now() - timezone.timedelta(days=5)).isoformat())
                         .status_code, 201)

    def test_gps_cerca_decide_que_coincide(self):
        res = self.etc(gps_latitud='-27.1002', gps_longitud='-56.2', gps_precision_m='6.7', ubicacion_coincide='NO')
        self.assertEqual(res.status_code, 201, res.data)
        v = VerificacionETC.objects.get(client_uuid=res.data['client_uuid'])
        self.assertLessEqual(v.distancia_equipo_m, 30)
        self.assertEqual((v.ubicacion_coincide, v.precision_gps_m), ('SI', 7))
        self.assertIsNotNone(v.ubicacion_capturada)

    def test_gps_lejos_no_coincide_aunque_diga_que_si(self):
        datos = self.datos_regulador(gps_latitud='-27.2', gps_longitud='-56.2', ubicacion_coincide='SI')
        res = self.cliente(self.tecnico).post(self.url_reg, datos, format='multipart')
        self.assertEqual(res.status_code, 201, res.data)
        v = Verificacion.objects.get(client_uuid=datos['client_uuid'])
        self.assertEqual(v.ubicacion_coincide, 'NO')
        self.assertAlmostEqual(v.distancia_equipo_m, 11077, delta=50)

    def test_sin_gps_queda_lo_declarado(self):
        res = self.etc(ubicacion_coincide='APROXIMADA')
        v = VerificacionETC.objects.get(client_uuid=res.data['client_uuid'])
        self.assertEqual((v.ubicacion_coincide, v.distancia_equipo_m), ('APROXIMADA', None))

    # --- Coherencia ---
    def test_fallas_implican_inconveniente_y_prioridad_sin_reclamo_se_limpia(self):
        from .models import TipoFallaETC
        leve = TipoFallaETC.objects.create(codigo='FT1', numero=91, descripcion='leve', gravedad='BAJA')
        res = self.etc(fallas=[leve.id], prioridad='ALTA')
        v = VerificacionETC.objects.get(client_uuid=res.data['client_uuid'])
        self.assertTrue(v.tiene_inconveniente)
        self.assertEqual((v.requiere_reclamo, v.prioridad), (False, ''))

    def test_falla_critica_obliga_a_reclamar(self):
        from .models import TipoFallaETC
        grave = TipoFallaETC.objects.create(codigo='FT2', numero=92, descripcion='grave', gravedad='CRITICA')
        res = self.etc(fallas=[grave.id], tiene_inconveniente='true', requiere_reclamo='false')
        self.assertEqual(res.status_code, 201, res.data)
        reclamo = self.equipo.reclamos.get()
        self.assertEqual(reclamo.prioridad, 'ALTA')
        self.assertIn('falla de gravedad crítica: F92', reclamo.historial.get().detalle)

    def test_sitio_fuera_de_servicio_obliga_a_reclamar(self):
        datos = self.datos_regulador(estado_sitio='FUERA_SERVICIO', requiere_reclamo='false')
        self.assertEqual(self.cliente(self.tecnico).post(self.url_reg, datos, format='multipart').status_code, 201)
        reclamo = Reclamo.objects.get(componente=self.componente)
        self.assertEqual(reclamo.prioridad, 'ALTA')
        self.assertIn('sitio fuera de servicio', reclamo.historial.get().detalle)


class InformePDFTests(BaseSigverTest):
    def test_pdf_requiere_usuario_staff(self):
        url = reverse('generar_pdf', args=['etc', uuid.uuid4()])
        res = self.client.get(url)
        self.assertEqual(res.status_code, 302)  # redirige al login del admin

    def test_pdf_inexistente_da_404(self):
        staff = Usuario.objects.create_user('staff', password='x', rol='supervisor_zona')
        self.client.force_login(staff)
        self.assertEqual(self.client.get(reverse('generar_pdf', args=['etc', uuid.uuid4()])).status_code, 404)
        self.assertEqual(self.client.get(reverse('generar_pdf', args=['otro', uuid.uuid4()])).status_code, 404)
