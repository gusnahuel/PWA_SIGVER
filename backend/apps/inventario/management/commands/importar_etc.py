"""
SIGVER - Importador de ETCs desde Excel
Lee el archivo 'etc_cuchillas.xlsx' y crea/actualiza equipos con coordenadas.

Uso:
    python manage.py importar_etc /app/data/etc_cuchillas.xlsx --dry-run
    python manage.py importar_etc /app/data/etc_cuchillas.xlsx
"""
import re
from pathlib import Path

from django.contrib.gis.geos import Point
from django.core.management.base import BaseCommand, CommandError
from openpyxl import load_workbook

from apps.inventario.models import SubEstacion, Alimentador, EquipoETC


# Índices de columnas (0-based) en la hoja INVENTARIO_EQUIPOS
COL_ESTACION = 0
COL_ALIMENTADOR = 1
COL_EQUIPO = 2
COL_CUCHILLAS = 3
COL_ESTADO = 4
COL_LAT = 7
COL_LNG = 8


def safe_get(row, idx):
    """Devuelve row[idx] o None si el índice está fuera de rango."""
    try:
        return row[idx]
    except (IndexError, TypeError):
        return None


class Command(BaseCommand):
    help = 'Importa ETCs con coordenadas desde Excel'

    def add_arguments(self, parser):
        parser.add_argument('archivo', type=str, help='Ruta del archivo Excel')
        parser.add_argument(
            '--sheet',
            type=str,
            default='INVENTARIO_EQUIPOS',
            help='Nombre de la hoja a procesar',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Simular sin guardar en la BD',
        )

    def handle(self, *args, **options):
        archivo = Path(options['archivo'])
        if not archivo.exists():
            raise CommandError(f'No existe el archivo: {archivo}')

        sheet_name = options['sheet']
        dry_run = options['dry_run']

        self.stdout.write(f"📂 Leyendo: {archivo.name} (hoja: {sheet_name})")
        if dry_run:
            self.stdout.write(self.style.WARNING("⚠️  Modo DRY-RUN: no se guardará nada"))

        wb = load_workbook(archivo, data_only=True)
        if sheet_name not in wb.sheetnames:
            raise CommandError(
                f'La hoja "{sheet_name}" no existe. '
                f'Hojas disponibles: {wb.sheetnames}'
            )

        ws = wb[sheet_name]

        creados = 0
        actualizados = 0
        saltados = 0
        errores = []
        total_filas = 0

        # Datos empiezan en fila 3 (filas 1 y 2 son encabezados)
        for row_idx, row in enumerate(ws.iter_rows(min_row=3, values_only=True), start=3):
            total_filas += 1

            # Fila completamente vacía
            if not row or not any(c is not None for c in row):
                saltados += 1
                continue

            estacion_raw = safe_get(row, COL_ESTACION)
            alimentador_raw = safe_get(row, COL_ALIMENTADOR)
            equipo_raw = safe_get(row, COL_EQUIPO)
            cuchillas_raw = safe_get(row, COL_CUCHILLAS)
            estado_raw = safe_get(row, COL_ESTADO)
            lat_raw = safe_get(row, COL_LAT)
            lng_raw = safe_get(row, COL_LNG)

            # Filas de separación o encabezados secundarios
            if not estacion_raw or not equipo_raw:
                saltados += 1
                continue

            # Filas que empiezan con algo que no es estación
            est_str = str(estacion_raw).strip().upper()
            if est_str in ('SI', 'NO', 'ESTACION', 'N/A', '-'):
                errores.append(f"Fila {row_idx}: estación inválida '{estacion_raw}'")
                continue

            # Normalizar estación: SE-ENC / SE_ENC -> ENC
            est_code = est_str.replace('_', '-')
            if est_code.startswith('SE-'):
                est_code = est_code[3:]
            if not est_code:
                errores.append(f"Fila {row_idx}: estación vacía")
                continue

            # Normalizar alimentador: E_AL01 / E_AL1 / EAL1 -> ENC_01
            if not alimentador_raw:
                errores.append(f"Fila {row_idx}: alimentador vacío")
                continue

            al_raw = str(alimentador_raw).strip().upper()
            m = re.match(r'E[_-]?AL(\d+)', al_raw)
            if not m:
                errores.append(f"Fila {row_idx}: alimentador inválido '{al_raw}'")
                continue
            al_num = int(m.group(1))
            al_code = f"{est_code}_{al_num:02d}"

            # Validar coordenadas
            try:
                lat = float(lat_raw)
                lng = float(lng_raw)
                if not (-90 <= lat <= 90) or not (-180 <= lng <= 180):
                    raise ValueError('fuera de rango')
                if abs(lat) < 0.01 and abs(lng) < 0.01:
                    raise ValueError('coordenada nula')
            except (TypeError, ValueError) as e:
                errores.append(
                    f"Fila {row_idx} (ETC {equipo_raw}): coords inválidas ({e})"
                )
                continue

            # Normalizar cuchillas
            cuch_norm = ''
            if cuchillas_raw:
                c = str(cuchillas_raw).strip().upper()
                if c == 'SI':
                    cuch_norm = 'SI'
                elif c == 'NO':
                    cuch_norm = 'NO'
                elif 'FALTA' in c:
                    cuch_norm = 'FALTA_FOTO'

            # Normalizar estado seccionador
            est_secc = 'CERRADO'
            if estado_raw and str(estado_raw).strip().upper() == 'ABIERTO':
                est_secc = 'ABIERTO'

            # Guardar
            if dry_run:
                self.stdout.write(
                    f"  [DRY] ETC {equipo_raw}: {al_code} @ "
                    f"({lat:.5f}, {lng:.5f}) cuchillas={cuch_norm} estado={est_secc}"
                )
                continue

            try:
                sub, _ = SubEstacion.objects.get_or_create(codigo=est_code)

                alimentador, _ = Alimentador.objects.get_or_create(
                    codigo=al_code,
                    defaults={'subestacion': sub},
                )

                obj, created = EquipoETC.objects.update_or_create(
                    nro_equipo=str(equipo_raw).strip(),
                    defaults={
                        'alimentador': alimentador,
                        'ubicacion': Point(lng, lat, srid=4326),
                        'estado_seccionador': est_secc,
                        'cuchillas_laterales': cuch_norm,
                    }
                )

                if created:
                    creados += 1
                else:
                    actualizados += 1

            except Exception as e:
                errores.append(f"Fila {row_idx} (ETC {equipo_raw}): {e}")

        # Resumen final
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(f"📊 Total filas leídas: {total_filas}"))
        self.stdout.write(self.style.SUCCESS(f"   • Creados:       {creados}"))
        self.stdout.write(self.style.SUCCESS(f"   • Actualizados:  {actualizados}"))
        self.stdout.write(self.style.WARNING(f"   • Saltados:      {saltados}"))
        self.stdout.write(self.style.WARNING(f"   • Con errores:   {len(errores)}"))

        if errores:
            self.stdout.write('')
            self.stdout.write(self.style.WARNING("⚠️  Errores (primeros 20):"))
            for e in errores[:20]:
                self.stdout.write(f"   {e}")
            if len(errores) > 20:
                self.stdout.write(f"   ... y {len(errores) - 20} más")