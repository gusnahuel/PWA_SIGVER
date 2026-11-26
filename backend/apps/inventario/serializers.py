"""
SIGVER - Serializers de Inventario
Devuelven GeoJSON listo para Leaflet.
"""
from rest_framework import serializers
from rest_framework_gis.serializers import GeoFeatureModelSerializer

from .models import ElementoEquipo, EquipoETC, Sitio


class EquipoETCSerializer(GeoFeatureModelSerializer):
    """Serializer GeoJSON para ETCs."""
    tipo = serializers.SerializerMethodField()
    alimentador_codigo = serializers.CharField(source='alimentador.codigo', read_only=True)
    subestacion_codigo = serializers.CharField(
        source='alimentador.subestacion.codigo', read_only=True
    )
    subestacion_nombre = serializers.CharField(
        source='alimentador.subestacion.nombre', read_only=True, default=''
    )

    class Meta:
        model = EquipoETC
        geo_field = 'ubicacion'
        fields = (
            'id', 'nro_equipo', 'tipo',
            'alimentador_codigo', 'subestacion_codigo', 'subestacion_nombre',
            'estado_seccionador', 'cuchillas_laterales',
            'tiene_problema_actual', 'fecha_ultima_verificacion',
        )

    def get_tipo(self, obj):
        return 'ETC'


class ElementoEquipoSerializer(serializers.ModelSerializer):
    """Datos de placa de cada unidad del banco (los ve el técnico al verificar)."""
    fotos = serializers.SerializerMethodField()

    class Meta:
        model = ElementoEquipo
        fields = ('id', 'identificador_elemento', 'marca', 'modelo', 'numero_serie',
                  'estado_elemento', 'observaciones', 'fotos')

    def get_fotos(self, obj):
        return sum(bool(f) for f in (obj.foto_equipo, obj.foto_placa, obj.foto_control))


class SitioSerializer(GeoFeatureModelSerializer):
    """Serializer GeoJSON para Sitios (reguladores)."""
    tipo = serializers.SerializerMethodField()
    alimentador_codigo = serializers.CharField(source='alimentador.codigo', read_only=True)
    subestacion_codigo = serializers.CharField(
        source='alimentador.subestacion.codigo', read_only=True
    )
    subestacion_nombre = serializers.CharField(
        source='alimentador.subestacion.nombre', read_only=True, default=''
    )
    componente_id = serializers.SerializerMethodField()
    elementos = serializers.SerializerMethodField()

    class Meta:
        model = Sitio
        geo_field = 'ubicacion_base'
        fields = (
            'id', 'id_sitio', 'cod_sitio', 'tipo',
            'alimentador_codigo', 'subestacion_codigo', 'subestacion_nombre',
            'configuracion_banco', 'capacidad_a', 'estado_general',
            'componente_id', 'elementos',
        )

    def get_tipo(self, obj):
        return 'REGULADOR'

    def get_componente_id(self, obj):
        # Usa el prefetch de la vista (evita una consulta por sitio)
        componentes = list(obj.componentes.all())
        return str(componentes[0].id) if componentes else None

    def get_elementos(self, obj):
        componentes = list(obj.componentes.all())
        if not componentes:
            return []
        return ElementoEquipoSerializer(componentes[0].elementos.all(), many=True).data
