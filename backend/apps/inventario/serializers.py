"""
SIGVER - Serializers de Inventario
Devuelven GeoJSON listo para Leaflet.
"""
from rest_framework import serializers
from rest_framework_gis.serializers import GeoFeatureModelSerializer

from .models import EquipoETC, Sitio


class EquipoETCSerializer(GeoFeatureModelSerializer):
    """Serializer GeoJSON para ETCs."""
    tipo = serializers.SerializerMethodField()
    alimentador_codigo = serializers.CharField(source='alimentador.codigo', read_only=True)
    subestacion_codigo = serializers.CharField(
        source='alimentador.subestacion.codigo', read_only=True
    )

    class Meta:
        model = EquipoETC
        geo_field = 'ubicacion'
        fields = (
            'id', 'nro_equipo', 'tipo',
            'alimentador_codigo', 'subestacion_codigo',
            'estado_seccionador', 'cuchillas_laterales',
            'tiene_problema_actual',
        )

    def get_tipo(self, obj):
        return 'ETC'


class SitioSerializer(GeoFeatureModelSerializer):
    """Serializer GeoJSON para Sitios (reguladores)."""
    tipo = serializers.SerializerMethodField()
    alimentador_codigo = serializers.CharField(source='alimentador.codigo', read_only=True)
    subestacion_codigo = serializers.CharField(
        source='alimentador.subestacion.codigo', read_only=True
    )
    componente_id = serializers.SerializerMethodField()

    class Meta:
        model = Sitio
        geo_field = 'ubicacion_base'
        fields = (
            'id', 'id_sitio', 'cod_sitio', 'tipo',
            'alimentador_codigo', 'subestacion_codigo',
            'configuracion_banco', 'capacidad_a', 'estado_general',
            'componente_id'
        )

    def get_tipo(self, obj):
        return 'REGULADOR'

    def get_componente_id(self, obj):
        comp = obj.componentes.first()
        return str(comp.id) if comp else None