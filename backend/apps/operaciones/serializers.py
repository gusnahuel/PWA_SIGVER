"""
SIGVER - Serializers de Operaciones
"""
from rest_framework import serializers
from rest_framework_gis.serializers import GeometryField

from .models import VerificacionETC, TipoFallaETC, Verificacion, MedicionTermografia, PuntoInspeccionTermografia
from apps.inventario.models import Personal, Sitio
from .models import EnsayoPAT, LecturaPAT, Reclamo


class TipoFallaETCSerializer(serializers.ModelSerializer):
    class Meta:
        model = TipoFallaETC
        fields = '__all__'


class PersonalSerializer(serializers.ModelSerializer):
    class Meta:
        model = Personal
        fields = ('id', 'id_personal', 'nombre_completo', 'cargo')


class VerificacionETCSerializer(serializers.ModelSerializer):
    ubicacion_capturada = GeometryField(required=False, allow_null=True)

    class Meta:
        model = VerificacionETC
        fields = '__all__'
        read_only_fields = ('synced_at',)

    def create(self, validated_data):
        # 1. Guardamos la verificación normalmente (Django hace su magia con las fallas aquí)
        verificacion = super().create(validated_data)
        
        # 2. Lógica extra: Si el técnico tildó "Requiere Reclamo", lo creamos
        if verificacion.requiere_reclamo:
            Reclamo.objects.create(
                id_reclamo=f"REC-ETC-{verificacion.id_verificacion}",
                descripcion=f"Reclamo generado desde verificación ETC {verificacion.equipo_etc.nro_equipo}. Obs: {verificacion.observaciones}",
                prioridad=verificacion.prioridad or 'MEDIA',
                estado='ABIERTO',
                origen_reclamo='VERIFICACION',
                agencia_responsable=verificacion.agencia_responsable,
                responsable_asignado=verificacion.responsable
            )
            
        return verificacion


class MedicionTermografiaSerializer(serializers.ModelSerializer):
    # 👇 Esto permite que el frontend envíe "P-001" (el código) en lugar del ID numérico
    punto = serializers.SlugRelatedField(
        slug_field='id_punto',
        queryset=PuntoInspeccionTermografia.objects.all()
    )

    class Meta:
        model = MedicionTermografia
        fields = ('id_medicion', 'punto', 'fecha_hora', 'corriente_a', 
                  'temperatura_ambiente_c', 'temperatura_punto_c', 
                  'delta_temperatura_c', 'nivel_termografico', 'observaciones')

class PuntoInspeccionTermografiaSerializer(serializers.ModelSerializer):
    class Meta:
        model = PuntoInspeccionTermografia
        fields = '__all__'

class LecturaPATSerializer(serializers.ModelSerializer):
    class Meta:
        model = LecturaPAT
        fields = ('id_lectura', 'tipo_lectura', 'distancia_m', 'valor_ohm', 'observaciones')

class EnsayoPATSerializer(serializers.ModelSerializer):
    # 👇 Esto permite que el ensayo reciba su lista de lecturas
    lecturas = LecturaPATSerializer(many=True, required=False)
    class Meta:
        model = EnsayoPAT
        fields = ('id_ensayo', 'fecha_ensayo', 'metodo_pat', 'equipo_medicion', 
                  'temperatura_ambiente_c', 'condicion_suelo', 'resultado', 'observaciones', 'lecturas')

class ReclamoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Reclamo
        fields = '__all__'        

class VerificacionSerializer(serializers.ModelSerializer):
    sitio = serializers.PrimaryKeyRelatedField(queryset=Sitio.objects.all(), required=False)
    mediciones_termografia = MedicionTermografiaSerializer(many=True, required=False)
    ensayos_pat = EnsayoPATSerializer(many=True, required=False)

    class Meta:
        model = Verificacion
        fields = '__all__'
        read_only_fields = ('synced_at',)

    def create(self, validated_data):
        mediciones_data = validated_data.pop('mediciones_termografia', [])
        ensayos_data = validated_data.pop('ensayos_pat', [])
        
        if 'sitio' not in validated_data or not validated_data.get('sitio'):
            componente = validated_data.get('componente')
            if componente:
                validated_data['sitio'] = componente.sitio
            else:
                raise serializers.ValidationError({"sitio": "Debe enviar sitio o componente."})
                
        verificacion = super().create(validated_data)
        
        # Guardar termografías
        for med_data in mediciones_data:
            MedicionTermografia.objects.create(
                verificacion=verificacion,
                componente=verificacion.componente,
                **med_data
            )
            
        # Guardar Ensayos PAT y sus Lecturas
        for ensayo_data in ensayos_data:
            lecturas_data = ensayo_data.pop('lecturas', [])
            ensayo = EnsayoPAT.objects.create(
                verificacion=verificacion,
                componente=verificacion.componente,
                **ensayo_data
            )
            for lectura_data in lecturas_data:
                LecturaPAT.objects.create(ensayo=ensayo, **lectura_data)

        #  LÓGICA DE RECLAMO AUTOMÁTICO (Va acá, justo antes del return) 
        if verificacion.requiere_reclamo:
            Reclamo.objects.create(
                id_reclamo=f"REC-REG-{verificacion.id_verificacion}",
                verificacion=verificacion,
                componente=verificacion.componente,
                descripcion=f"Reclamo generado desde verificación de Regulador {verificacion.componente.id_componente}. Obs: {verificacion.observaciones}",
                prioridad=verificacion.prioridad or 'MEDIA',
                estado='ABIERTO',
                origen_reclamo='VERIFICACION',
                agencia_responsable=verificacion.agencia_responsable,
                responsable_asignado=verificacion.responsable
            )
        
                
        return verificacion