"""
SIGVER - Importador de Sitios desde Excel
Lee la hoja 'Sitio' del Excel de reguladores.
Normaliza los códigos de alimentador al formato XXX_NN (consistente con ETCs).

Uso:
    python manage.py importar_sitios /app/data/sitios_reguladores.xlsx --dry-run
    python manage.py importar_sitios /app/data/sitios_reguladores.xlsx
"""
import re
from pathlib import Path

from django.contrib.gis.geos import Point
from django.core.management.base import BaseCommand, CommandError
from openpyxl import load_workbook

from apps.inventario.models import SubEstacion, Alimentador, Sitio


# Índices de columnas (0-based) en la hoja Sitio
COL_ID_SITIO = 0
COL_COD_SITIO = 1
COL_DEPARTAMENTO = 2
COL_DISTRITO = 3
COL_LOCALIDAD = 4
COL_SUBESTACION = 5
COL_ALIMENTADOR = 6
COL_UBICACION = 7
COL_UTM_E = 8
COL_UTM_N = 9
COL_CONFIG_BANCO = 10
COL_CAPACIDAD = 11
COL_USUARIO = 12
COL_TIPO_BASE = 13
COL_RESPONSABLE = 14
COL_ESTADO_GENERAL = 15
COL_FECHA_ULTIMO = 16
COL_OBSERVACIONES = 17


def safe_get(row, idx):
    try:
        return row[idx]
    except (IndexError, TypeError):
        return None


def clean_str(value):
    if value is None:
        return ''
    return str(value).strip()


def normalize_subestacion(raw):
    """Normaliza el código de subestación: 'ES CBO' -> 'CBO', 'SE-ENC' -> 'ENC'."""
    if not raw:
        return ''
    s = str(raw).strip().upper().replace('_', '-')
    # Quitar prefijos comunes
    if s.startswith('ES '):
        s = s[3:]
    if s.startswith('SE-'):
        s = s[3:]
    return s.strip()


def normalize_alimentador(sub_code, al_raw):
    """
    Normaliza el alimentador al formato XXX_NN usando el código de subestación.
    'SPP1'  + 'SPP' -> 'SPP_01'
    'CBO 6' + 'CBO' -> 'CBO_06'
    'NTA2'  + 'NAT' -> 'NAT_02'  (corrige typo del Excel)
    """
    if not al_raw:
        return ''
    al_str = str(al_raw).strip().upper()
    # Extraer el número (todos los dígitos)
    m = re.search(r'(\d+)', al_str)
    if not m:
        # Sin número, devolver tal cual
        return al_str
    num = int(m.group(1))
    return f"{sub_code}_{num:02d}"


def parse_latlong(texto):
    """Parsea '-27.123, -56.456' a (lat, lng)."""
    if not texto:
        return None, None
    texto = str(texto).strip()
    m = re.match(r'^\s*(-?\d+\.?\d*)\s*,\s*(-?\d+\.?\d*)\s*$', texto)
    if not m:
        return None, None
    lat = float(m.group(1))
    lng = float(m.group(2))
    if not (-90 <= lat <= 90) or not (-180 <= lng <= 180):
        return None, None
    return lat, lng


class Command(BaseCommand):
    help = 'Importa sitios (reguladores) desde Excel'

    def add_arguments(self, parser):
        parser.add_argument('archivo', type=str)
        parser.add_argument('--sheet', type=str, default='Sitio')
        parser.add_argument('--dry-run', action='store_true')

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

        for row_idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
            if not row or not any(c is not None for c in row):
                saltados += 1
                continue

            id_sitio = clean_str(safe_get(row, COL_ID_SITIO))
            cod_sitio = clean_str(safe_get(row, COL_COD_SITIO))
            alimentador_raw = clean_str(safe_get(row, COL_ALIMENTADOR))
            subestacion_raw = clean_str(safe_get(row, COL_SUBESTACION))
            ubicacion_raw = safe_get(row, COL_UBICACION)

            # Ignorar IDs que no siguen el formato SIT-XXX
            if not id_sitio.startswith('SIT-'):
                if id_sitio:
                    errores.append(f"Fila {row_idx}: id_sitio inválido '{id_sitio}'")
                else:
                    saltados += 1
                continue

            if not alimentador_raw:
                saltados += 1
                continue

            lat, lng = parse_latlong(ubicacion_raw)
            if lat is None:
                errores.append(
                    f"Fila {row_idx} ({id_sitio}): ubicación inválida '{ubicacion_raw}'"
                )
                continue

            # Normalizar subestación y alimentador
            sub_code = normalize_subestacion(subestacion_raw)
            if not sub_code:
                errores.append(f"Fila {row_idx} ({id_sitio}): subestación vacía")
                continue

            al_code = normalize_alimentador(sub_code, alimentador_raw)
            if not al_code:
                errores.append(f"Fila {row_idx} ({id_sitio}): alimentador vacío")
                continue

            # Configuración del banco
            config_raw = clean_str(safe_get(row, COL_CONFIG_BANCO)).upper()
            config_norm = ''
            if 'CERRADO' in config_raw:
                config_norm = 'DELTA_CERRADO'
            elif 'ABIERTO' in config_raw:
                config_norm = 'DELTA_ABIERTO'
            elif 'MONOF' in config_raw:
                config_norm = 'MONOFASICO'

            capacidad_raw = safe_get(row, COL_CAPACIDAD)
            try:
                capacidad = int(float(capacidad_raw)) if capacidad_raw else None
            except (TypeError, ValueError):
                capacidad = None

            estado_raw = clean_str(safe_get(row, COL_ESTADO_GENERAL)).upper()
            estado_norm = ''
            if estado_raw in ('NORMAL', 'OBSERVADO', 'CRITICO', 'CRÍTICO', 'FUERA DE SERVICIO'):
                estado_norm = (
                    estado_raw.replace('Í', 'I')
                    .replace(' ', '_')
                    .replace('FUERA_DE_SERVICIO', 'FUERA_SERVICIO')
                )

            if dry_run:
                self.stdout.write(
                    f"  [DRY] {id_sitio} | {cod_sitio} | "
                    f"sub={sub_code} alim={al_code} @ ({lat:.5f}, {lng:.5f})"
                )
                creados += 1
                continue

            try:
                sub, _ = SubEstacion.objects.get_or_create(codigo=sub_code)
                alimentador, _ = Alimentador.objects.get_or_create(
                    codigo=al_code,
                    defaults={'subestacion': sub},
                )

                obj, created = Sitio.objects.update_or_create(
                    id_sitio=id_sitio,
                    defaults={
                        'cod_sitio': cod_sitio,
                        'alimentador': alimentador,
                        'ubicacion_base': Point(lng, lat, srid=4326),
                        'utm_este': safe_get(row, COL_UTM_E),
                        'utm_norte': safe_get(row, COL_UTM_N),
                        'configuracion_banco': config_norm,
                        'capacidad_a': capacidad,
                        'usuario': clean_str(safe_get(row, COL_USUARIO)),
                        'tipo_base': clean_str(safe_get(row, COL_TIPO_BASE)),
                        'estado_general': estado_norm,
                        'observaciones_generales': clean_str(safe_get(row, COL_OBSERVACIONES)),
                    }
                )
                if created:
                    creados += 1
                else:
                    actualizados += 1
            except Exception as e:
                errores.append(f"Fila {row_idx} ({id_sitio}): {e}")

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS("📊 Resumen:"))
        self.stdout.write(self.style.SUCCESS(f"   • Creados:      {creados}"))
        self.stdout.write(self.style.SUCCESS(f"   • Actualizados: {actualizados}"))
        self.stdout.write(self.style.WARNING(f"   • Saltados:     {saltados}"))
        self.stdout.write(self.style.WARNING(f"   • Con errores:  {len(errores)}"))

        if errores:
            self.stdout.write('')
            self.stdout.write(self.style.WARNING("⚠️  Errores (primeros 20):"))
            for e in errores[:20]:
                self.stdout.write(f"   {e}")