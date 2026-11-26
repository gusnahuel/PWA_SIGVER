"""
SIGVER - Pruebas de inventario: importación del informe de ANDE.
"""
import tempfile
from io import StringIO
from pathlib import Path

from django.core.management import call_command
from django.test import TestCase
from openpyxl import Workbook

from .models import Alimentador, EquipoETC, SeccionRegional, SubEstacion


def informe_de_prueba(ruta):
    """Misma forma que la hoja TAVRIDA: departamento, estación, alimentadores, cerrado/abierto."""
    wb = Workbook()
    ws = wb.active
    filas = [
        ['DEPARTAMENTO DE ITAPUA'],
        [],
        ['SUBESTACION HOHENAU'],
        [None, 'ALIMENTADOR', 'NUMERO ETC', None, None, 'NUMERO ETC'],
        [None, None, 'CERRADO', None, None, 'ABIERTO'],
        [None, 'HOE_01', 42219, None, None, 42220],
        [None, 'TOTAL_HOE', 1, None, None, 1],
        ['DEPARTAMENTO DE ÑEEMBUCU'],
        ['ESTACION VILLALBIN'],
        [None, 'ALIMENTADOR', 'NUMERO ETC', None, None, 'NUMERO ETC'],
        [None, None, 'CERRADO', None, None, 'ABIERTO'],
        [None, 'VIN_01', 50001],
        ['ESTACION/SUBESTACION', 'NUMERO ETC'],
        ['DEPARTAMENTO DE ITAPUA'],
        ['ENCARNACION ', 35],
    ]
    for f in filas:
        ws.append(f)
    wb.save(ruta)


class ImportarInformeAndeTests(TestCase):
    def setUp(self):
        self.enc = SeccionRegional.objects.get_or_create(codigo='ENC', defaults={'nombre': 'Encarnación'})[0]
        self.pil = SeccionRegional.objects.get_or_create(codigo='PIL', defaults={'nombre': 'Pilar'})[0]
        vin = SubEstacion.objects.create(codigo='VIN')
        alim = Alimentador.objects.create(codigo='VIN_01', subestacion=vin)
        EquipoETC.objects.create(nro_equipo='50001', alimentador=alim, estado_seccionador='ABIERTO')
        self.dir = tempfile.TemporaryDirectory()
        self.ruta = Path(self.dir.name) / 'informe.xlsx'
        informe_de_prueba(self.ruta)

    def tearDown(self):
        self.dir.cleanup()

    def importar(self, *extra):
        salida = StringIO()
        call_command('importar_informe_ande', str(self.ruta), *extra, stdout=salida)
        return salida.getvalue()

    def test_carga_nombres_tipo_seccion_y_alimentadores(self):
        self.importar()
        vin = SubEstacion.objects.get(codigo='VIN')
        self.assertEqual((vin.nombre, vin.tipo, vin.seccion_regional), ('Villalbín', 'ESTACION', self.pil))
        self.assertEqual(str(vin), 'Villalbín (VIN)')
        hoe = SubEstacion.objects.get(codigo='HOE')
        self.assertEqual((hoe.nombre, hoe.tipo, hoe.seccion_regional), ('Hohenau', 'SUBESTACION', self.enc))
        self.assertTrue(Alimentador.objects.filter(codigo='HOE_01', subestacion=hoe).exists())

    def test_los_etc_solo_se_informan(self):
        salida = self.importar()
        self.assertIn('Faltan en el sistema: 2 (42219, 42220)', salida)
        self.assertIn('50001: sistema ABIERTO → informe CERRADO', salida)
        self.assertFalse(EquipoETC.objects.filter(nro_equipo='42219').exists())
        self.assertEqual(EquipoETC.objects.get(nro_equipo='50001').estado_seccionador, 'ABIERTO')

    def test_dry_run_no_guarda(self):
        self.importar('--dry-run')
        self.assertFalse(SubEstacion.objects.filter(codigo='HOE').exists())
        self.assertEqual(SubEstacion.objects.get(codigo='VIN').nombre, '')
