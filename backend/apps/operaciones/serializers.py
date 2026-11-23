"""
SIGVER - Serializers de Operaciones
"""
import json

from django.contrib.gis.geos import Point
from django.db import transaction
from rest_framework import serializers
from rest_framework_gis.serializers import GeometryField

from apps.inventario.models import Personal, Sitio
from . import estado_red, reclamos
from .models import (
    EnsayoPAT, HistorialReclamo, LecturaPAT, MedicionTermografia, PuntoInspeccionTermografia,
    Reclamo, TipoFallaETC, Verificacion, VerificacionETC,
)

VALORES_NULOS = ('', 'null', 'undefined', 'None')


class ResponsableField(serializers.PrimaryKeyRelatedField):
    """Acepta 'null'/'undefined' (lo que envía FormData cuando falta el valor) como vacío."""

    def __init__(self, **kwargs):
        kwargs.setdefault('queryset', Personal.objects.all())
        kwargs.setdefault('required', False)
        kwargs.setdefault('allow_null', True)
        super().__init__(**kwargs)

    def validate_empty_values(self, data):
        if data in VALORES_NULOS:
            return (True, None)
        return super().validate_empty_values(data)


class TipoFallaETCSerializer(serializers.ModelSerializer):
    class Meta:
        model = TipoFallaETC
        fields = '__all__'


class PersonalSerializer(serializers.ModelSerializer):
    class Meta:
        model = Personal
        fields = ('id', 'id_personal', 'nombre_completo', 'cargo')


class ResponsableDesdeUsuarioMixin:
    """
    Asigna el responsable a partir del usuario autenticado, para que nadie
    pueda registrar verificaciones a nombre de otra persona.
    Los supervisores/administradores pueden indicarlo explícitamente.
    """

    def _resolver_responsable(self, attrs):
        request = self.context.get('request')
        user = getattr(request, 'user', None)
        personal = getattr(user, 'personal', None) if user else None

        puede_elegir = bool(user and user.is_authenticated and user.es_supervisor)
        if personal is not None and not (puede_elegir and attrs.get('responsable')):
            attrs['responsable'] = personal

        if not attrs.get('responsable'):
            raise serializers.ValidationError({
                'responsable': 'Tu usuario no tiene una ficha de Personal asociada. '
                               'Pedí al administrador que la vincule.'
            })
        if not attrs.get('agencia_responsable'):
            attrs['agencia_responsable'] = attrs['responsable'].agencia
        return attrs


class VerificacionETCSerializer(ResponsableDesdeUsuarioMixin, serializers.ModelSerializer):
    ubicacion_capturada = GeometryField(required=False, allow_null=True)
    responsable = ResponsableField()

    class Meta:
        model = VerificacionETC
        fields = '__all__'
        read_only_fields = ('synced_at',)

    def validate(self, attrs):
        return self._resolver_responsable(attrs)

    @transaction.atomic
    def create(self, validated_data):
        verificacion = super().create(validated_data)

        # Primero el reclamo (nuevo o el que ya estaba abierto) y después el
        # estado del equipo en el mapa, que tiene en cuenta los reclamos abiertos
        if verificacion.requiere_reclamo:
            reclamos.registrar_falla(self.context['request'].user, verificacion)
        estado_red.por_verificacion_etc(verificacion)
        return verificacion


class MedicionTermografiaSerializer(serializers.ModelSerializer):
    # El frontend envía el código del punto ("P-001") en lugar del ID numérico
    punto = serializers.SlugRelatedField(
        slug_field='id_punto',
        queryset=PuntoInspeccionTermografia.objects.all(),
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
    lecturas = LecturaPATSerializer(many=True, required=False)

    class Meta:
        model = EnsayoPAT
        fields = ('id_ensayo', 'fecha_ensayo', 'metodo_pat', 'equipo_medicion',
                  'temperatura_ambiente_c', 'condicion_suelo', 'resultado', 'observaciones', 'lecturas')


class HistorialReclamoSerializer(serializers.ModelSerializer):
    class Meta:
        model = HistorialReclamo
        fields = ('fecha', 'usuario_nombre', 'estado_anterior', 'estado_nuevo', 'detalle', 'comentario')


class ReclamoSerializer(serializers.ModelSerializer):
    """
    Lectura completa del reclamo con su historial. Las escrituras las valida
    apps/operaciones/reclamos.py (la vista no llama a serializer.save()).
    """
    historial = HistorialReclamoSerializer(many=True, read_only=True)
    equipo_nro = serializers.CharField(source='equipo_etc.nro_equipo', read_only=True, default=None)
    # Motivo del cambio (devolver, rechazar, reabrir). No es un campo del modelo: va al historial.
    comentario = serializers.CharField(write_only=True, required=False, allow_blank=True)
    # GPS del celular al enviar la evidencia; el servidor arma el punto y mide la distancia
    gps_latitud = serializers.FloatField(write_only=True, required=False, min_value=-90, max_value=90)
    gps_longitud = serializers.FloatField(write_only=True, required=False, min_value=-180, max_value=180)
    gps_precision_m = serializers.FloatField(write_only=True, required=False, min_value=0)
    ubicacion_evidencia = GeometryField(read_only=True)

    class Meta:
        model = Reclamo
        fields = '__all__'
        # Los completa el sistema según el cambio de estado
        read_only_fields = ('fecha_reclamo', 'fecha_limite', 'fecha_asignacion', 'fecha_inicio',
                            'fecha_ejecucion', 'fecha_cierre', 'validado_por', 'fecha_validacion',
                            'motivo_rechazo', 'precision_evidencia_m', 'distancia_evidencia_m')
        extra_kwargs = {'id_reclamo': {'required': False}}

    def validate(self, attrs):
        lat, lng = attrs.pop('gps_latitud', None), attrs.pop('gps_longitud', None)
        precision = attrs.pop('gps_precision_m', None)
        if (lat is None) != (lng is None):
            raise serializers.ValidationError({'gps_latitud': 'Enviá latitud y longitud juntas.'})
        if lat is not None:
            attrs['ubicacion_evidencia'] = Point(lng, lat, srid=4326)
            attrs['precision_evidencia_m'] = round(precision) if precision is not None else None
        return attrs


class VerificacionSerializer(ResponsableDesdeUsuarioMixin, serializers.ModelSerializer):
    sitio = serializers.PrimaryKeyRelatedField(queryset=Sitio.objects.all(), required=False)
    responsable = ResponsableField()
    mediciones_termografia = MedicionTermografiaSerializer(many=True, required=False)
    ensayos_pat = EnsayoPATSerializer(many=True, required=False)

    CAMPOS_ANIDADOS = ('mediciones_termografia', 'ensayos_pat')

    class Meta:
        model = Verificacion
        fields = '__all__'
        read_only_fields = ('synced_at',)

    def to_internal_value(self, data):
        """
        La PWA envía multipart/form-data (por las fotos) y los datos anidados
        como texto JSON. DRF ignora en silencio las listas anidadas en un
        QueryDict, así que las convertimos a un dict normal y decodificamos.
        """
        if hasattr(data, 'getlist'):
            data = {key: data.get(key) for key in data.keys()}
        else:
            data = dict(data)

        for campo in self.CAMPOS_ANIDADOS:
            valor = data.get(campo)
            if isinstance(valor, str):
                try:
                    data[campo] = json.loads(valor) if valor.strip() else []
                except json.JSONDecodeError:
                    raise serializers.ValidationError({campo: 'JSON inválido.'})
        return super().to_internal_value(data)

    def validate(self, attrs):
        if not attrs.get('sitio'):
            componente = attrs.get('componente')
            if not componente:
                raise serializers.ValidationError({'sitio': 'Debe enviar sitio o componente.'})
            attrs['sitio'] = componente.sitio
        return self._resolver_responsable(attrs)

    @transaction.atomic
    def create(self, validated_data):
        mediciones_data = validated_data.pop('mediciones_termografia', [])
        ensayos_data = validated_data.pop('ensayos_pat', [])

        verificacion = super().create(validated_data)

        for med_data in mediciones_data:
            MedicionTermografia.objects.create(
                verificacion=verificacion,
                componente=verificacion.componente,
                **med_data,
            )

        for ensayo_data in ensayos_data:
            lecturas_data = ensayo_data.pop('lecturas', [])
            ensayo = EnsayoPAT.objects.create(
                verificacion=verificacion,
                componente=verificacion.componente,
                **ensayo_data,
            )
            LecturaPAT.objects.bulk_create(
                LecturaPAT(ensayo=ensayo, **lectura) for lectura in lecturas_data
            )

        if verificacion.requiere_reclamo:
            reclamos.registrar_falla(self.context['request'].user, verificacion)
        estado_red.por_verificacion_regulador(verificacion)
        return verificacion
