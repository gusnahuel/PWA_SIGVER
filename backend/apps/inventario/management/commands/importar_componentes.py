"""
SIGVER - Importador de Componentes (Reguladores) desde Excel

Lee:
  - Hoja 'Componentes': reguladores individuales con datos de la verificación.
  - Hoja 'Copia de Componentes': elementos (marca/modelo/serie) asociados.

Además, genera 1 componente por cada Sitio que no tenga uno.

Uso:
    python manage.py importar_componentes /app/data/sitios_reguladores.xlsx --dry-run
    python manage.py importar_componentes /app/data/sitios_reguladores.xlsx
"""
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from openpyxl import load_workbook

from apps.inventario.models import Sitio, Componente, ElementoEquipo
from apps.operaciones.models import Verificacion


def safe_get(row, idx):
    try:
        return row[idx]
    except (IndexError, TypeError):
        return None


def clean_str(value):
    if value is None:
        return ''
    return str(value).strip()


class Command(BaseCommand):
    help = 'Importa componentes (reguladores) desde Excel'

    def add_arguments(self, parser):
        parser.add_argument('archivo', type=str)
        parser.add_argument('--dry-run', action='store_true')
        parser.add_argument(
            '--sin-generar-faltantes',
            action='store_true',
            help='No generar componentes faltantes para los sitios huérfanos',
        )

    def handle(self, *args, **options):
        archivo = Path(options['archivo'])
        if not archivo.exists():
            raise CommandError(f'No existe el archivo: {archivo}')

        dry_run = options['dry_run']
        sin_generar = options['sin_generar_faltantes']

        self.stdout.write(f"📂 Leyendo: {archivo.name}")
        if dry_run:
            self.stdout.write(self.style.WARNING("⚠️  Modo DRY-RUN: no se guardará nada"))

        wb = load_workbook(archivo, data_only=True)

        # ============================================================
        # 1. Componentes desde hoja 'Componentes'
        # ============================================================
        creados_comp = 0
        actualizados_comp = 0
        errores_comp = []

        if 'Componentes' in wb.sheetnames:
            ws = wb['Componentes']
            # Encabezados en fila 1, datos desde fila 2
            for row_idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
                if not row or not any(c is not None for c in row):
                    continue

                id_componente = clean_str(safe_get(row, 0))
                id_verificacion = clean_str(safe_get(row, 1))
                # tipo_component = row[2]
                # tipo_conexion = row[3]
                # tipo_control_asociado = row[4]
                # fases_conexion = row[5]
                # estado_componente = row[6]
                # estado_control = row[7]
                # obs_comp = row[8]
                # obs_control = row[9]

                if not id_componente:
                    continue

                # Buscar el sitio a través de la verificación
                sitio = None
                if id_verificacion:
                    verif = Verificacion.objects.filter(
                        id_verificacion=id_verificacion
                    ).first()
                    if verif:
                        sitio = verif.sitio

                if not sitio:
                    errores_comp.append(
                        f"Fila {row_idx} ({id_componente}): no se encontró sitio "
                        f"(verificación {id_verificacion})"
                    )
                    continue

                if dry_run:
                    self.stdout.write(
                        f"  [DRY-COMP] {id_componente} → {sitio.id_sitio}"
                    )
                    creados_comp += 1
                    continue

                try:
                    obj, created = Componente.objects.update_or_create(
                        id_componente=id_componente,
                        defaults={
                            'sitio': sitio,
                            'tipo_componente': 'REGULADOR',
                            'tipo_conexion': clean_str(safe_get(row, 3)),
                            'tipo_control_asociado': clean_str(safe_get(row, 4)),
                            'fases_conexion': clean_str(safe_get(row, 5)),
                            'estado_componente': clean_str(safe_get(row, 6)),
                            'estado_control': clean_str(safe_get(row, 7)),
                            'observaciones_componente': clean_str(safe_get(row, 8)),
                            'observaciones_control': clean_str(safe_get(row, 9)),
                        }
                    )
                    if created:
                        creados_comp += 1
                    else:
                        actualizados_comp += 1
                except Exception as e:
                    errores_comp.append(f"Fila {row_idx} ({id_componente}): {e}")
        else:
            self.stdout.write(
                self.style.WARNING("⚠️  No existe la hoja 'Componentes'")
            )

        # ============================================================
        # 2. Elementos desde hoja 'Copia de Componentes'
        # ============================================================
        creados_elem = 0
        actualizados_elem = 0
        errores_elem = []

        if 'Copia de Componentes' in wb.sheetnames:
            ws = wb['Copia de Componentes']
            for row_idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
                if not row or not any(c is not None for c in row):
                    continue

                id_elemento = clean_str(safe_get(row, 0))
                id_componente = clean_str(safe_get(row, 1))
                # id_verificacion = row[2]
                # identificador_elemento = row[3]
                # marca = row[4]
                # modelo = row[5]
                # numero_serie = row[6]
                # foto_equipo = row[7]
                # foto_placa = row[8]
                # foto_control = row[9]
                # estado_elemento = row[10]
                # observaciones = row[11]

                if not id_componente:
                    continue

                componente = Componente.objects.filter(
                    id_componente=id_componente
                ).first()
                if not componente:
                    errores_elem.append(
                        f"Fila {row_idx}: componente '{id_componente}' no existe"
                    )
                    continue

                if dry_run:
                    self.stdout.write(
                        f"  [DRY-ELEM] {id_componente} | "
                        f"{clean_str(safe_get(row, 4))} {clean_str(safe_get(row, 5))} "
                        f"({clean_str(safe_get(row, 6))})"
                    )
                    creados_elem += 1
                    continue

                try:
                    obj, created = ElementoEquipo.objects.update_or_create(
                        id_elemento=id_elemento or f"ELEM-{id_componente}",
                        defaults={
                            'componente': componente,
                            'identificador_elemento': clean_str(safe_get(row, 3)),
                            'marca': clean_str(safe_get(row, 4)),
                            'modelo': clean_str(safe_get(row, 5)),
                            'numero_serie': clean_str(safe_get(row, 6)),
                            'estado_elemento': clean_str(safe_get(row, 10)),
                            'observaciones': clean_str(safe_get(row, 11)),
                        }
                    )
                    if created:
                        creados_elem += 1
                    else:
                        actualizados_elem += 1
                except Exception as e:
                    errores_elem.append(f"Fila {row_idx}: {e}")

        # ============================================================
        # 3. Generar componentes faltantes para sitios huérfanos
        # ============================================================
        creados_gen = 0
        if not sin_generar and not dry_run:
            sitios_sin_comp = Sitio.objects.filter(componentes__isnull=True)
            for sitio in sitios_sin_comp:
                Componente.objects.create(
                    id_componente=f"COMP-{sitio.id_sitio}",
                    sitio=sitio,
                    tipo_componente='REGULADOR',
                )
                creados_gen += 1
        elif not sin_generar and dry_run:
            sitios_sin_comp = Sitio.objects.filter(componentes__isnull=True)
            for sitio in sitios_sin_comp:
                self.stdout.write(
                    f"  [DRY-GEN] Generar componente para {sitio.id_sitio}"
                )
            creados_gen = sitios_sin_comp.count()

        # ============================================================
        # Resumen
        # ============================================================
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS("📊 Resumen:"))
        self.stdout.write(self.style.SUCCESS(
            f"   • Componentes creados (Excel): {creados_comp}"
        ))
        self.stdout.write(self.style.SUCCESS(
            f"   • Componentes actualizados:    {actualizados_comp}"
        ))
        self.stdout.write(self.style.SUCCESS(
            f"   • Elementos creados:           {creados_elem}"
        ))
        self.stdout.write(self.style.SUCCESS(
            f"   • Elementos actualizados:      {actualizados_elem}"
        ))
        self.stdout.write(self.style.SUCCESS(
            f"   • Componentes generados:       {creados_gen}"
        ))
        self.stdout.write(self.style.WARNING(
            f"   • Errores componentes:         {len(errores_comp)}"
        ))
        self.stdout.write(self.style.WARNING(
            f"   • Errores elementos:           {len(errores_elem)}"
        ))

        for e in (errores_comp + errores_elem)[:20]:
            self.stdout.write(f"   {e}")