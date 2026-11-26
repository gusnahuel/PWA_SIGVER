"""
SIGVER - Importa el "Listado de equipos telecomandados en producción" de ANDE
(informe_Ande.xlsx, hoja TAVRIDA).

Carga lo que el informe dice de la red, sin tocar los ETC:
  - nombre, tipo (estación/subestación) y sección regional de cada subestación
  - las subestaciones y alimentadores que todavía no existen

Las diferencias de los ETC (faltantes, otro alimentador, abierto/cerrado) solo
se informan: se revisan antes de decidir cuál fuente vale.

Uso:
    python manage.py importar_informe_ande /app/data/informe_Ande.xlsx --dry-run
    python manage.py importar_informe_ande /app/data/informe_Ande.xlsx
"""
import re
import unicodedata
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from openpyxl import load_workbook

from apps.inventario.models import Alimentador, EquipoETC, SeccionRegional, SubEstacion

# El informe viene en mayúsculas y sin tildes: nombre oficial con su ortografía
NOMBRES = {
    'CBO': 'Coronel Bogado', 'SPP': 'San Pedro del Paraná', 'FRA': 'Fram',
    'NAT': 'Natalio', 'CAL': 'Carlos Antonio López', 'TRI': 'Trinidad',
    'PPO': 'Pirapó', 'ENC': 'Encarnación', 'CAM': 'Cambyretá',
    'NAR': 'Naranjal', 'HOE': 'Hohenau', 'AYO': 'Ayolas',
    'SPA': 'San Patricio', 'SIG': 'San Ignacio', 'SJB': 'San Juan Bautista',
    'VIN': 'Villalbín', 'PIL': 'Pilar', 'BRO': 'Buey Rodeo',
}
# Departamento del informe -> código de la sección regional
SECCION_POR_DEPARTAMENTO = {'ITAPUA': 'ENC', 'MISIONES': 'MIS', 'NEEMBUCU': 'PIL'}

RE_ALIMENTADOR = re.compile(r'^([A-Z]{2,4})_\d+$')
RE_ESTACION = re.compile(r'^(SUB)?ESTACION\s+(.+)$')


def sin_tildes(texto):
    texto = unicodedata.normalize('NFD', str(texto).upper())
    return ''.join(c for c in texto if unicodedata.category(c) != 'Mn').strip()


def leer_informe(ruta):
    """Devuelve {codigo: {nombre_informe, tipo, departamento}} y {nro_etc: (alimentador, estado)}."""
    hoja = load_workbook(ruta, data_only=True, read_only=True).active
    estaciones, equipos = {}, {}
    departamento = estacion = None
    col_abierto = 5
    for fila in hoja.iter_rows(values_only=True):
        celdas = [(i, c) for i, c in enumerate(fila) if c not in (None, '')]
        if not celdas:
            continue
        texto = sin_tildes(celdas[0][1]) if isinstance(celdas[0][1], str) else ''
        if texto.startswith('ESTACION/SUBESTACION'):
            break   # empieza el cuadro resumen del final
        if texto.startswith('DEPARTAMENTO DE '):
            departamento = texto.removeprefix('DEPARTAMENTO DE ').strip()
            continue
        if m := RE_ESTACION.match(texto):
            estacion = {'nombre_informe': m.group(2).strip(), 'departamento': departamento,
                        'tipo': 'SUBESTACION' if m.group(1) else 'ESTACION'}
            continue
        if estacion is None:
            continue
        for i, c in celdas:
            if isinstance(c, str) and sin_tildes(c) == 'ABIERTO':
                col_abierto = i
        if not (m := RE_ALIMENTADOR.match(texto)):
            continue
        codigo_alim = texto
        estaciones.setdefault(m.group(1), estacion)
        for i, c in celdas[1:]:
            nro = str(int(c)) if isinstance(c, (int, float)) else str(c).strip()
            if nro.isdigit():
                equipos[nro] = (codigo_alim, 'ABIERTO' if i >= col_abierto else 'CERRADO')
    return estaciones, equipos


class Command(BaseCommand):
    help = 'Carga nombres, tipo y sección de las subestaciones, y los alimentadores faltantes, desde el informe de ANDE.'

    def add_arguments(self, parser):
        parser.add_argument('archivo', type=str)
        parser.add_argument('--dry-run', action='store_true', help='Muestra los cambios sin guardarlos')

    def handle(self, *args, **opts):
        ruta = Path(opts['archivo'])
        if not ruta.exists():
            raise CommandError(f'No existe el archivo: {ruta}')
        estaciones, equipos = leer_informe(ruta)
        if not estaciones:
            raise CommandError('No se encontraron estaciones en el informe (¿es el archivo correcto?)')

        secciones = {s.codigo: s for s in SeccionRegional.objects.all()}
        with transaction.atomic():
            self._subestaciones(estaciones, secciones)
            self._alimentadores(equipos)
            self._diferencias_etc(equipos)
            if opts['dry_run']:
                transaction.set_rollback(True)
                self.stdout.write(self.style.WARNING('\nDRY-RUN: no se guardó nada.'))
            else:
                self.stdout.write(self.style.SUCCESS('\nListo.'))

    def _subestaciones(self, estaciones, secciones):
        self.stdout.write('Subestaciones:')
        for codigo, datos in sorted(estaciones.items()):
            sub, creada = SubEstacion.objects.get_or_create(codigo=codigo)
            seccion = secciones.get(SECCION_POR_DEPARTAMENTO.get(datos['departamento'], ''))
            nuevos = {
                'nombre': NOMBRES.get(codigo) or datos['nombre_informe'].title(),
                'tipo': datos['tipo'],
                'seccion_regional': seccion,
            }
            cambios = [k for k, v in nuevos.items() if getattr(sub, k) != v]
            for k in cambios:
                setattr(sub, k, nuevos[k])
            if cambios:
                sub.save()
            estado = 'NUEVA' if creada else ('actualizada' if cambios else 'sin cambios')
            self.stdout.write(f'  {codigo:4} {nuevos["nombre"]:22} {sub.get_tipo_display():12} '
                              f'{seccion or "¿sección?"!s:12} {estado}')
        otras = SubEstacion.objects.exclude(codigo__in=estaciones).values_list('codigo', flat=True)
        if otras:
            self.stdout.write(f'  No figuran en el informe (se dejan como están): {", ".join(otras)}')

    def _alimentadores(self, equipos):
        existentes = set(Alimentador.objects.values_list('codigo', flat=True))
        nuevos = sorted({alim for alim, _ in equipos.values()} - existentes)
        for codigo in nuevos:
            Alimentador.objects.create(
                codigo=codigo, subestacion=SubEstacion.objects.get(codigo=codigo.split('_')[0]))
        self.stdout.write(f'\nAlimentadores nuevos: {len(nuevos)}' + (f' ({", ".join(nuevos)})' if nuevos else ''))

    def _diferencias_etc(self, equipos):
        """Solo informa: los ETC no se modifican desde este comando."""
        sistema = {e.nro_equipo: e for e in EquipoETC.objects.select_related('alimentador')}
        faltan = sorted(set(equipos) - set(sistema))
        sobran = sorted(set(sistema) - set(equipos))
        otro_alim = [(n, sistema[n].alimentador.codigo if sistema[n].alimentador else '—', a)
                     for n, (a, _) in sorted(equipos.items())
                     if n in sistema and (sistema[n].alimentador is None or sistema[n].alimentador.codigo != a)]
        otro_estado = [(n, sistema[n].estado_seccionador or '—', e) for n, (_, e) in sorted(equipos.items())
                       if n in sistema and sistema[n].estado_seccionador != e]

        self.stdout.write(f'\nETC en el informe: {len(equipos)} · en el sistema: {len(sistema)} (no se modifican)')
        self.stdout.write(f'  Faltan en el sistema: {len(faltan)}' + (f' ({", ".join(faltan)})' if faltan else ''))
        if sobran:
            self.stdout.write(f'  No figuran en el informe: {len(sobran)} ({", ".join(sobran)})')
        self.stdout.write(f'  Con otro alimentador: {len(otro_alim)}')
        for n, antes, despues in otro_alim:
            self.stdout.write(f'    {n}: sistema {antes} → informe {despues}')
        self.stdout.write(f'  Con otro estado (abierto/cerrado): {len(otro_estado)}')
        for n, antes, despues in otro_estado:
            self.stdout.write(f'    {n}: sistema {antes} → informe {despues}')
