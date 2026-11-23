"""
Datos existentes:
1. Plazo de cada reclamo según su prioridad (desde la fecha del reclamo).
2. ETC con reclamos: se aplica la regla nueva del mapa. Con un reclamo sin
   terminar figura con problema; si no le queda ninguno y el último cierre es
   posterior a su última verificación, deja de figurar con problema.
"""
from datetime import timedelta

from django.db import migrations
from django.db.models import Max

PLAZOS = {
    'CRITICA': timedelta(hours=24),
    'ALTA': timedelta(hours=72),
    'MEDIA': timedelta(days=7),
    'BAJA': timedelta(days=30),
}
TERMINADOS = ('CERRADO', 'RECHAZADO')


def adelante(apps, schema_editor):
    Reclamo = apps.get_model('operaciones', 'Reclamo')
    EquipoETC = apps.get_model('inventario', 'EquipoETC')

    for reclamo in Reclamo.objects.filter(fecha_limite__isnull=True):
        reclamo.fecha_limite = reclamo.fecha_reclamo + PLAZOS.get(reclamo.prioridad or 'MEDIA', PLAZOS['MEDIA'])
        reclamo.save(update_fields=['fecha_limite'])

    for equipo in EquipoETC.objects.filter(reclamos__isnull=False).distinct():
        if equipo.reclamos.exclude(estado__in=TERMINADOS).exists():
            # Reclamo sin terminar: figura con problema hasta que se cierre
            if not equipo.tiene_problema_actual:
                equipo.tiene_problema_actual = True
                equipo.save(update_fields=['tiene_problema_actual'])
            continue
        if not equipo.tiene_problema_actual:
            continue
        cierres = equipo.reclamos.aggregate(c=Max('fecha_cierre'), r=Max('fecha_reclamo'))
        ultimo_cierre = cierres['c'] or cierres['r']
        if equipo.fecha_ultima_verificacion is None or ultimo_cierre >= equipo.fecha_ultima_verificacion:
            equipo.tiene_problema_actual = False
            equipo.save(update_fields=['tiene_problema_actual'])


class Migration(migrations.Migration):

    dependencies = [
        ('operaciones', '0010_reclamo_fecha_limite'),
        ('inventario', '__first__'),
    ]

    operations = [
        migrations.RunPython(adelante, migrations.RunPython.noop),
    ]
