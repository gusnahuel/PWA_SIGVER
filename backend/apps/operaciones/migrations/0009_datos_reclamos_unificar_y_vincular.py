"""
Datos de los reclamos existentes:
1. "Resuelto" y "Cerrado" significaban lo mismo: todo pasa a "Cerrado".
2. Los reclamos de ETC solo nombraban el equipo en el texto: se vinculan con
   su verificación de ETC y su equipo.
3. Cada reclamo recibe la primera entrada de su historial.
"""
import re

from django.db import migrations

PATRON_EQUIPO = re.compile(r'verificación ETC (\S+?)\.')


def adelante(apps, schema_editor):
    Reclamo = apps.get_model('operaciones', 'Reclamo')
    VerificacionETC = apps.get_model('operaciones', 'VerificacionETC')
    EquipoETC = apps.get_model('inventario', 'EquipoETC')
    HistorialReclamo = apps.get_model('operaciones', 'HistorialReclamo')

    for reclamo in Reclamo.objects.all():
        notas = []
        if reclamo.estado == 'RESUELTO':
            reclamo.estado = 'CERRADO'
            notas.append('Estaba «Resuelto»; ese estado se unificó con «Cerrado».')

        if reclamo.id_reclamo.startswith('REC-ETC-') and reclamo.equipo_etc_id is None:
            verificacion = VerificacionETC.objects.filter(
                id_verificacion=reclamo.id_reclamo.removeprefix('REC-ETC-')).first()
            if verificacion is not None:
                reclamo.verificacion_etc = verificacion
                reclamo.equipo_etc_id = verificacion.equipo_etc_id
            else:
                encontrado = PATRON_EQUIPO.search(reclamo.descripcion or '')
                if encontrado:
                    reclamo.equipo_etc = EquipoETC.objects.filter(nro_equipo=encontrado.group(1)).first()
            if reclamo.equipo_etc_id:
                notas.append('Vinculado a su equipo ETC.')

        reclamo.save()
        HistorialReclamo.objects.create(
            reclamo=reclamo,
            fecha=reclamo.fecha_reclamo,
            usuario_nombre='Sistema',
            estado_nuevo=reclamo.estado,
            detalle='\n'.join(['Reclamo anterior al historial: se registra su estado al actualizar el sistema.']
                              + notas),
        )


class Migration(migrations.Migration):

    dependencies = [
        ('operaciones', '0008_reclamo_historial_y_vinculo_etc'),
        ('inventario', '__first__'),
    ]

    operations = [
        migrations.RunPython(adelante, migrations.RunPython.noop),
    ]
