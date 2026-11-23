"""
Antes, el reclamo generado por una verificación quedaba "Abierto" pero ya
asignado al técnico que la hizo. Con las reglas nuevas, un reclamo con técnico
está "Asignado": se corrigen esos casos y se deja constancia en el historial.
"""
from django.db import migrations
from django.utils import timezone


def adelante(apps, schema_editor):
    Reclamo = apps.get_model('operaciones', 'Reclamo')
    HistorialReclamo = apps.get_model('operaciones', 'HistorialReclamo')

    for reclamo in Reclamo.objects.filter(estado='ABIERTO', responsable_asignado__isnull=False):
        reclamo.estado = 'ASIGNADO'
        reclamo.fecha_asignacion = reclamo.fecha_asignacion or reclamo.fecha_reclamo
        reclamo.save(update_fields=['estado', 'fecha_asignacion'])
        HistorialReclamo.objects.create(
            reclamo=reclamo,
            fecha=timezone.now(),
            usuario_nombre='Sistema',
            estado_anterior='ABIERTO',
            estado_nuevo='ASIGNADO',
            detalle='Corrección de datos: el reclamo ya tenía técnico asignado (regla anterior, '
                    'que asignaba al técnico que lo reportó).',
        )


class Migration(migrations.Migration):

    dependencies = [
        ('operaciones', '0011_datos_plazos_y_estado_etc'),
    ]

    operations = [
        migrations.RunPython(adelante, migrations.RunPython.noop),
    ]
