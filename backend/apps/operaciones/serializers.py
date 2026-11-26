"""
SIGVER - Serializers de Operaciones
"""
import json
from datetime import timedelta

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers
from rest_framework_gis.serializers import GeometryField

from apps.inventario.models import ElementoEquipo, EquipoETC, Personal, Sitio
from . import estado_red, geo, reclamos
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
    La agencia es siempre la del responsable (no la elige el celular).
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
        attrs['agencia_responsable'] = attrs['responsable'].agencia
        return attrs


class DatosDeCampoMixin(serializers.Serializer):
    """
    Lo que el servidor controla de toda verificación que llega del celular:
    - la fecha (el reloj del celular puede estar mal),
    - el GPS: arma el punto y, al guardar, mide la distancia al equipo; con
      GPS, «ubicación coincide» lo decide esa distancia y no el técnico,
    - la coherencia reclamo/prioridad.
    """
    # Una verificación puede esperar varios días en la cola sin señal, pero no meses
    ANTIGUEDAD_MAXIMA = timedelta(days=60)
    TOLERANCIA_RELOJ = timedelta(minutes=10)

    gps_latitud = serializers.FloatField(write_only=True, required=False, min_value=-90, max_value=90)
    gps_longitud = serializers.FloatField(write_only=True, required=False, min_value=-180, max_value=180)
    gps_precision_m = serializers.FloatField(write_only=True, required=False, min_value=0)

    def _validar_fecha(self, attrs):
        fecha = attrs.get('fecha_verificacion')
        ahora = timezone.now()
        if fecha and fecha > ahora + self.TOLERANCIA_RELOJ:
            raise serializers.ValidationError({
                'fecha_verificacion': 'La fecha es posterior a la actual: revisá la fecha y hora del celular.'})
        if fecha and fecha < ahora - self.ANTIGUEDAD_MAXIMA:
            raise serializers.ValidationError({
                'fecha_verificacion': 'La verificación tiene más de 60 días: revisá la fecha y hora del celular.'})

    def _resolver_gps(self, attrs):
        lat, lng = attrs.pop('gps_latitud', None), attrs.pop('gps_longitud', None)
        precision = attrs.pop('gps_precision_m', None)
        if (lat is None) != (lng is None):
            raise serializers.ValidationError({'gps_latitud': 'Enviá latitud y longitud juntas.'})
        if lat is not None:
            attrs['ubicacion_capturada'] = geo.punto_gps(lat, lng)
            attrs['precision_gps_m'] = round(precision) if precision is not None else None

    @staticmethod
    def _exigir_reclamo(attrs, motivo):
        """Falla grave: el reclamo es obligatorio, con prioridad alta como mínimo."""
        attrs['requiere_reclamo'] = True
        if reclamos.ORDEN_PRIORIDAD.get(attrs.get('prioridad') or 'BAJA', 1) < reclamos.ORDEN_PRIORIDAD['ALTA']:
            attrs['prioridad'] = 'ALTA'
        attrs['_reclamo_obligatorio'] = motivo

    @staticmethod
    def _normalizar_reclamo(attrs):
        if not attrs.get('requiere_reclamo'):
            attrs['prioridad'] = ''

    def _guardar_distancia(self, verificacion, queryset, campo):
        metros = geo.distancia_m(queryset, campo, verificacion.ubicacion_capturada)
        if metros is not None:
            verificacion.distancia_equipo_m = metros
            verificacion.ubicacion_coincide = geo.coincide(metros)
            verificacion.save(update_fields=['distancia_equipo_m', 'ubicacion_coincide'])


class VerificacionETCSerializer(ResponsableDesdeUsuarioMixin, DatosDeCampoMixin, serializers.ModelSerializer):
    ubicacion_capturada = GeometryField(read_only=True)
    responsable = ResponsableField()

    class Meta:
        model = VerificacionETC
        fields = '__all__'
        read_only_fields = ('synced_at', 'agencia_responsable', 'precision_gps_m', 'distancia_equipo_m')

    def validate(self, attrs):
        self._validar_fecha(attrs)
        self._resolver_gps(attrs)
        fallas = attrs.get('fallas') or []
        if fallas:
            attrs['tiene_inconveniente'] = True   # con fallas marcadas hay inconveniente
        criticas = [f for f in fallas if f.gravedad == 'CRITICA']
        if criticas:
            self._exigir_reclamo(attrs, 'falla de gravedad crítica: '
                                 + ', '.join(f'F{f.numero:02d}' for f in criticas))
        self._normalizar_reclamo(attrs)
        return self._resolver_responsable(attrs)

    @transaction.atomic
    def create(self, validated_data):
        obligatorio = validated_data.pop('_reclamo_obligatorio', None)
        verificacion = super().create(validated_data)
        verificacion._reclamo_obligatorio = obligatorio
        self._guardar_distancia(verificacion, EquipoETC.objects.filter(pk=verificacion.equipo_etc_id), 'ubicacion')

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
        # Los calcula el servidor con las temperaturas (MedicionTermografia.save)
        read_only_fields = ('delta_temperatura_c', 'nivel_termografico')


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
            attrs['ubicacion_evidencia'] = geo.punto_gps(lat, lng)
            attrs['precision_evidencia_m'] = round(precision) if precision is not None else None
        return attrs


def imagen_subida(archivo, descripcion):
    """Valida que el archivo subido sea una imagen (las fotos que viajan fuera del JSON)."""
    try:
        return serializers.ImageField().to_internal_value(archivo)
    except (serializers.ValidationError, DjangoValidationError):
        raise serializers.ValidationError({'fotos': f'La foto {descripcion} no es una imagen válida.'})


class ElementoEnVerificacionSerializer(serializers.Serializer):
    """
    Datos de placa de una unidad del banco, cargados durante la verificación.
    `id`: lo genera el celular; si la unidad ya existe se corrige, si no se crea
    con ese id (así un reenvío desde la cola no la duplica).
    `clave`: identifica sus fotos, que llegan aparte como foto_elemento_<clave>_<equipo|placa|control>.
    """
    id = serializers.UUIDField()
    clave = serializers.RegexField(r'^[A-Za-z0-9_-]{1,60}$')
    identificador_elemento = serializers.CharField(max_length=100, required=False, allow_blank=True)
    marca = serializers.CharField(max_length=100, required=False, allow_blank=True)
    modelo = serializers.CharField(max_length=100, required=False, allow_blank=True)
    numero_serie = serializers.CharField(max_length=100, required=False, allow_blank=True)
    estado_elemento = serializers.CharField(max_length=30, required=False, allow_blank=True)
    observaciones = serializers.CharField(required=False, allow_blank=True)


class VerificacionSerializer(ResponsableDesdeUsuarioMixin, DatosDeCampoMixin, serializers.ModelSerializer):
    sitio = serializers.PrimaryKeyRelatedField(queryset=Sitio.objects.all(), required=False)
    responsable = ResponsableField()
    mediciones_termografia = MedicionTermografiaSerializer(many=True, required=False)
    ensayos_pat = EnsayoPATSerializer(many=True, required=False)
    elementos = ElementoEnVerificacionSerializer(many=True, required=False, write_only=True)

    CAMPOS_ANIDADOS = ('mediciones_termografia', 'ensayos_pat', 'elementos')
    FOTOS_ELEMENTO = ('equipo', 'placa', 'control')

    class Meta:
        model = Verificacion
        fields = '__all__'
        read_only_fields = ('synced_at', 'agencia_responsable', 'precision_gps_m', 'distancia_equipo_m')

    ubicacion_capturada = GeometryField(read_only=True)
    ESTADOS_CON_RECLAMO = {'CRITICO': 'sitio en estado crítico', 'FUERA_SERVICIO': 'sitio fuera de servicio'}

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
        self._validar_fecha(attrs)
        self._resolver_gps(attrs)
        self._validar_elementos(attrs)
        if attrs.get('estado_sitio') in self.ESTADOS_CON_RECLAMO:
            self._exigir_reclamo(attrs, self.ESTADOS_CON_RECLAMO[attrs['estado_sitio']])
        self._normalizar_reclamo(attrs)
        return self._resolver_responsable(attrs)

    def _validar_elementos(self, attrs):
        """Solo se cargan unidades del regulador que se está verificando."""
        ids = {e['id'] for e in attrs.get('elementos') or []}
        if not ids:
            return
        componente = attrs.get('componente')
        if componente is None:
            raise serializers.ValidationError({'elementos': 'Los equipos del banco necesitan el regulador.'})
        if ElementoEquipo.objects.filter(id__in=ids).exclude(componente=componente).exists():
            raise serializers.ValidationError({'elementos': 'Hay una unidad que no pertenece a este regulador.'})

    def _guardar_elementos(self, componente, elementos_data):
        archivos = self.context['request'].FILES
        for numero, datos in enumerate(elementos_data, start=1):
            datos = dict(datos)
            pk, clave = datos.pop('id'), datos.pop('clave')
            for que in self.FOTOS_ELEMENTO:
                archivo = archivos.get(f'foto_elemento_{clave}_{que}')
                if archivo:
                    datos[f'foto_{que}'] = imagen_subida(archivo, f'de la unidad {numero} ({que})')
            elemento = componente.elementos.filter(pk=pk).first() or ElementoEquipo(pk=pk, componente=componente)
            for campo, valor in datos.items():
                setattr(elemento, campo, valor)
            elemento.save()

    @transaction.atomic
    def create(self, validated_data):
        mediciones_data = validated_data.pop('mediciones_termografia', [])
        ensayos_data = validated_data.pop('ensayos_pat', [])
        elementos_data = validated_data.pop('elementos', [])
        obligatorio = validated_data.pop('_reclamo_obligatorio', None)

        verificacion = super().create(validated_data)
        verificacion._reclamo_obligatorio = obligatorio
        self._guardar_distancia(verificacion, Sitio.objects.filter(pk=verificacion.sitio_id), 'ubicacion_base')

        for med_data in mediciones_data:
            MedicionTermografia.objects.create(
                verificacion=verificacion,
                componente=verificacion.componente,
                **med_data,
            )

        archivos = self.context['request'].FILES
        for ensayo_data in ensayos_data:
            lecturas_data = ensayo_data.pop('lecturas', [])
            # La foto de cada ensayo llega aparte (el ensayo viaja como JSON): foto_pat_<id_ensayo>
            foto = archivos.get(f"foto_pat_{ensayo_data['id_ensayo']}")
            if foto:
                ensayo_data['foto'] = imagen_subida(foto, 'del ensayo PAT')
            ensayo = EnsayoPAT.objects.create(
                verificacion=verificacion,
                componente=verificacion.componente,
                **ensayo_data,
            )
            LecturaPAT.objects.bulk_create(
                LecturaPAT(ensayo=ensayo, **lectura) for lectura in lecturas_data
            )

        if elementos_data and verificacion.componente_id:
            self._guardar_elementos(verificacion.componente, elementos_data)

        if verificacion.requiere_reclamo:
            reclamos.registrar_falla(self.context['request'].user, verificacion)
        estado_red.por_verificacion_regulador(verificacion)
        return verificacion
