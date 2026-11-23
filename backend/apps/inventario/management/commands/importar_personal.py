"""
SIGVER - Importador de Personal desde Excel
Lee la hoja 'Responsable' del Excel de sitios/reguladores.

Uso:
    python manage.py importar_personal /app/data/sitios_reguladores.xlsx --dry-run
    python manage.py importar_personal /app/data/sitios_reguladores.xlsx
"""
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from openpyxl import load_workbook

from apps.inventario.models import Personal, Agencia


# Índices de columnas (0-based) en la hoja Responsable
COL_ID_PERSONAL = 0
COL_NOMBRE = 1
COL_UNIDAD = 2
COL_TIPO_PARTICIPACION = 3
COL_CARGO = 4
COL_TELEFONO = 5
COL_CORREO = 6
COL_ACTIVO = 7
COL_ORIGEN = 8
COL_OBSERVACIONES = 9


def safe_get(row, idx):
    """Devuelve row[idx] o None si el índice está fuera de rango."""
    try:
        return row[idx]
    except (IndexError, TypeError):
        return None


def clean_str(value):
    """Devuelve un string limpio o cadena vacía."""
    if value is None:
        return ''
    return str(value).strip()


class Command(BaseCommand):
    help = 'Importa el personal desde la hoja "Responsable" del Excel'

    def add_arguments(self, parser):
        parser.add_argument('archivo', type=str, help='Ruta del archivo Excel')
        parser.add_argument(
            '--sheet',
            type=str,
            default='Responsable',
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

        # Datos empiezan en fila 2 (fila 1 son encabezados)
        for row_idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
            if not row or not any(c is not None for c in row):
                saltados += 1
                continue

            id_personal = clean_str(safe_get(row, COL_ID_PERSONAL))
            nombre = clean_str(safe_get(row, COL_NOMBRE))

            if not id_personal or not nombre:
                saltados += 1
                continue

            # Si el ID no empieza con PER- es probable que sea fila de encabezado o error
            if not id_personal.startswith('PER-'):
                saltados += 1
                continue

            unidad_raw = clean_str(safe_get(row, COL_UNIDAD))
            tipo_participacion = clean_str(safe_get(row, COL_TIPO_PARTICIPACION))
            cargo = clean_str(safe_get(row, COL_CARGO))
            telefono = clean_str(safe_get(row, COL_TELEFONO))
            correo = clean_str(safe_get(row, COL_CORREO))
            activo_raw = clean_str(safe_get(row, COL_ACTIVO)).upper()
            origen = clean_str(safe_get(row, COL_ORIGEN))
            observaciones = clean_str(safe_get(row, COL_OBSERVACIONES))

            activo = activo_raw in ('SI', 'SÍ', 'TRUE', '1', 'YES')

            # Intentar matchear la agencia por nombre
            agencia = None
            if unidad_raw:
                agencia = Agencia.objects.filter(nombre__iexact=unidad_raw).first()
                if not agencia:
                    # Guardar en observaciones para no perder el dato
                    if observaciones:
                        observaciones = f"[Unidad original: {unidad_raw}] {observaciones}"
                    else:
                        observaciones = f"[Unidad original: {unidad_raw}]"

            if dry_run:
                self.stdout.write(
                    f"  [DRY] {id_personal} | {nombre} | "
                    f"unidad={unidad_raw or '-'} | activo={activo}"
                )
                creados += 1
                continue

            try:
                obj, created = Personal.objects.update_or_create(
                    id_personal=id_personal,
                    defaults={
                        'nombre_completo': nombre,
                        'agencia': agencia,
                        'tipo_participacion': tipo_participacion,
                        'cargo': cargo,
                        'telefono': telefono,
                        'correo': correo,
                        'activo': activo,
                        'origen_registro': origen,
                        'observaciones': observaciones,
                    }
                )

                if created:
                    creados += 1
                else:
                    actualizados += 1

            except Exception as e:
                errores.append(f"Fila {row_idx} ({id_personal}): {e}")

        # Resumen final
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS("📊 Resumen:"))
        self.stdout.write(self.style.SUCCESS(f"   • Creados:      {creados}"))
        self.stdout.write(self.style.SUCCESS(f"   • Actualizados: {actualizados}"))
        self.stdout.write(self.style.WARNING(f"   • Saltados:     {saltados}"))
        self.stdout.write(self.style.WARNING(f"   • Con errores:  {len(errores)}"))

        if errores:
            self.stdout.write('')
            self.stdout.write(self.style.WARNING("⚠️  Errores:"))
            for e in errores[:20]:
                self.stdout.write(f"   {e}")