"""
SIGVER - Modelos Operativos
Verificaciones, mediciones, ensayos y reclamos.
"""
import uuid

from django.conf import settings
from django.contrib.gis.db import models as gis_models
from django.db import models
from django.utils import timezone


# =====================================================
# CATÁLOGO DE FALLAS (ETC)
# =====================================================

class TipoFallaETC(models.Model):
    """Las 26 fallas predeterminadas del manual de ETC."""
    codigo = models.CharField(max_length=10, unique=True, help_text='Ej: F01')
    numero = models.PositiveSmallIntegerField(unique=True, help_text='1 a 26')
    descripcion = models.CharField(max_length=300)
    gravedad = models.CharField(
        max_length=10,
        choices=[
            ('BAJA', 'Baja'),
            ('MEDIA', 'Media'),
            ('ALTA', 'Alta'),
            ('CRITICA', 'Crítica'),
        ],
        default='MEDIA',
    )
    activo = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'Tipo de Falla ETC'
        verbose_name_plural = 'Tipos de Falla ETC'
        ordering = ['numero']

    def __str__(self):
        return f"F{self.numero:02d} - {self.descripcion[:60]}"


# =====================================================
# VERIFICACIÓN DE REGULADORES
# =====================================================

class Verificacion(models.Model):
    """Verificación completa de un regulador (formato Excel)."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    id_verificacion = models.CharField(max_length=50, unique=True)

    sitio = models.ForeignKey(
        'inventario.Sitio',
        on_delete=models.PROTECT,
        related_name='verificaciones',
    )
    componente = models.ForeignKey(
        'inventario.Componente',
        on_delete=models.PROTECT,
        related_name='verificaciones',
    )

    fecha_verificacion = models.DateTimeField()
    responsable = models.ForeignKey(
        'inventario.Personal',
        on_delete=models.PROTECT,
        related_name='verificaciones',
    )
    agencia_responsable = models.ForeignKey(
        'inventario.Agencia',
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='verificaciones_responsable',
    )

    # Ubicación capturada
    ubicacion_capturada = gis_models.PointField(geography=True, null=True, blank=True)
    precision_gps_m = models.PositiveIntegerField(
        null=True, blank=True, help_text='Precisión informada por el GPS del celular',
    )
    distancia_equipo_m = models.PositiveIntegerField(
        null=True, blank=True, help_text='Distancia al equipo, calculada por el servidor',
    )
    COINCIDE = [
        ('SI', 'Sí'),
        ('APROXIMADA', 'Aproximada'),
        ('NO', 'No'),
    ]
    ubicacion_coincide = models.CharField(max_length=15, choices=COINCIDE, blank=True)

    # Datos de la verificación
    TIPO_CONTROL = [
        ('CONTROL_UNICO', 'Control Único'),
        ('CONTROL_INDIVIDUAL', 'Control Individual'),
        ('NO_APLICA', 'No Aplica'),
    ]
    tipo_control_verificado = models.CharField(max_length=30, choices=TIPO_CONTROL, blank=True)

    TIPO_BANCO = [
        ('DELTA_CERRADO', 'Delta Cerrado'),
        ('DELTA_ABIERTO', 'Delta Abierto'),
        ('MONOFASICO', 'Monofásico'),
    ]
    tipo_banco_verificado = models.CharField(max_length=30, choices=TIPO_BANCO, blank=True)

    valla_perimetral = models.BooleanField(null=True, blank=True)
    es_hibrido = models.BooleanField(null=True, blank=True)
    configuracion_observada = models.CharField(max_length=200, blank=True)

    ESTADO_SITIO = [
        ('NORMAL', 'Normal'),
        ('OBSERVADO', 'Observado'),
        ('CRITICO', 'Crítico'),
        ('FUERA_SERVICIO', 'Fuera de Servicio'),
    ]
    estado_sitio = models.CharField(max_length=20, choices=ESTADO_SITIO, blank=True)

    observaciones_control_unico = models.TextField(blank=True)
    observaciones = models.TextField(blank=True)

    # Fotos
    foto_frontal = models.ImageField(upload_to='verificaciones/frontal/%Y/%m/', null=True, blank=True)
    foto_entorno = models.ImageField(upload_to='verificaciones/entorno/%Y/%m/', null=True, blank=True)
    foto_control_unico = models.ImageField(upload_to='verificaciones/control/%Y/%m/', null=True, blank=True)

    # Reclamo
    requiere_reclamo = models.BooleanField(default=False)
    prioridad = models.CharField(
        max_length=10,
        choices=[
            ('BAJA', 'Baja'),
            ('MEDIA', 'Media'),
            ('ALTA', 'Alta'),
            ('CRITICA', 'Crítica'),
        ],
        blank=True,
    )

    # Offline
    client_uuid = models.UUIDField(unique=True)
    synced_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Verificación de Regulador'
        verbose_name_plural = 'Verificaciones de Reguladores'
        ordering = ['-fecha_verificacion']
        indexes = [
            models.Index(fields=['componente', '-fecha_verificacion']),
            models.Index(fields=['responsable', '-fecha_verificacion']),
            models.Index(fields=['-fecha_verificacion']),
        ]

    def __str__(self):
        return f"Verificación {self.id_verificacion}"


# =====================================================
# VERIFICACIÓN DE ETC
# =====================================================

class VerificacionETC(models.Model):
    """Verificación simplificada de un ETC (1 foto + falla opcional)."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    id_verificacion = models.CharField(max_length=50, unique=True)

    equipo_etc = models.ForeignKey(
        'inventario.EquipoETC',
        on_delete=models.PROTECT,
        related_name='verificaciones',
    )

    fecha_verificacion = models.DateTimeField()
    responsable = models.ForeignKey(
        'inventario.Personal',
        on_delete=models.PROTECT,
        related_name='verificaciones_etc',
    )
    agencia_responsable = models.ForeignKey(
        'inventario.Agencia',
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='verificaciones_etc',
    )

    ubicacion_capturada = gis_models.PointField(geography=True, null=True, blank=True)
    precision_gps_m = models.PositiveIntegerField(
        null=True, blank=True, help_text='Precisión informada por el GPS del celular',
    )
    distancia_equipo_m = models.PositiveIntegerField(
        null=True, blank=True, help_text='Distancia al equipo, calculada por el servidor',
    )

    tiene_inconveniente = models.BooleanField(default=False)
    fallas = models.ManyToManyField(
        TipoFallaETC,
        blank=True,
        related_name='verificaciones',
        help_text='Seleccione una o más fallas'
    )
    observaciones = models.TextField(blank=True)
        
    COINCIDE = [
        ('SI', 'Sí'),
        ('APROXIMADA', 'Aproximada'),
        ('NO', 'No'),
    ]
    ubicacion_coincide = models.CharField(max_length=15, choices=COINCIDE, blank=True)
    
    requiere_reclamo = models.BooleanField(default=False)
    prioridad = models.CharField(
        max_length=10,
        choices=[
            ('BAJA', 'Baja'),
            ('MEDIA', 'Media'),
            ('ALTA', 'Alta'),
            ('CRITICA', 'Crítica'),
        ],
        blank=True
    )
    foto = models.ImageField(upload_to='verificaciones_etc/%Y/%m/', null=True, blank=True)

    client_uuid = models.UUIDField(unique=True)
    synced_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Verificación de ETC'
        verbose_name_plural = 'Verificaciones de ETC'
        ordering = ['-fecha_verificacion']
        indexes = [
            models.Index(fields=['equipo_etc', '-fecha_verificacion']),
        ]

    def __str__(self):
        return f"Verificación ETC {self.id_verificacion}"


# =====================================================
# MEDICIONES: TERMOGRAFÍA
# =====================================================

class PuntoInspeccionTermografia(models.Model):
    """Catálogo genérico de puntos de inspección termográfica."""
    id_punto = models.CharField(max_length=20, unique=True, help_text='Ej: P-001')

    FASE = [('R', 'R'), ('S', 'S'), ('T', 'T')]
    fase = models.CharField(max_length=1, choices=FASE)

    TIPO_ELEMENTO = [
        ('Seccionador_ByPass', 'Seccionador ByPass'),
        ('Seccionador_Equipo_LadoLinea', 'Seccionador Lado Línea'),
        ('Seccionador_Equipo_LadoEquipo', 'Seccionador Lado Equipo'),
        ('Bushing', 'Bushing'),
        ('Conector_Descargador_Linea', 'Conector Descargador Línea'),
        ('Conector_Descargador_Regulador', 'Conector Descargador Regulador'),
        ('Otros', 'Otros'),
    ]
    tipo_elemento = models.CharField(max_length=50, choices=TIPO_ELEMENTO)

    LADO = [
        ('Fuente', 'Fuente'),
        ('Carga', 'Carga'),
        ('Comun', 'Común'),
        ('N/A', 'N/A'),
    ]
    lado_conexion = models.CharField(max_length=20, choices=LADO)

    activo = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'Punto de Inspección Termográfica'
        verbose_name_plural = 'Puntos de Inspección Termográfica'
        ordering = ['id_punto']

    def __str__(self):
        return f"{self.id_punto} - {self.fase} - {self.get_tipo_elemento_display()}"


class MedicionTermografia(models.Model):
    """Medición termográfica realizada en un punto específico."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    id_medicion = models.CharField(max_length=50, unique=True)

    verificacion = models.ForeignKey(
        Verificacion,
        null=True, blank=True,
        on_delete=models.CASCADE,
        related_name='mediciones_termografia',
    )
    componente = models.ForeignKey(
        'inventario.Componente',
        on_delete=models.CASCADE,
        related_name='mediciones_termografia',
    )
    punto = models.ForeignKey(
        PuntoInspeccionTermografia,
        null=True, blank=True,
        on_delete=models.PROTECT,
    )

    fecha_hora = models.DateTimeField()
    corriente_a = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    fase_seleccion = models.CharField(max_length=10, blank=True)
    tipo_elemento_seleccion = models.CharField(max_length=50, blank=True)
    lado_conexion_seleccion = models.CharField(max_length=20, blank=True)
    temperatura_ambiente_c = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    temperatura_punto_c = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    delta_temperatura_c = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)

    NIVEL = [
        ('Nivel 1', 'Nivel 1'),
        ('Nivel 2', 'Nivel 2'),
        ('Nivel 3', 'Nivel 3'),
    ]
    nivel_termografico = models.CharField(max_length=20, choices=NIVEL, blank=True)
    observaciones = models.TextField(blank=True)

    class Meta:
        verbose_name = 'Medición de Termografía'
        verbose_name_plural = 'Mediciones de Termografía'
        ordering = ['-fecha_hora']

    def __str__(self):
        return f"Medición {self.id_medicion}"


# =====================================================
# MEDICIONES: PAT (Puesta a Tierra)
# =====================================================

class EnsayoPAT(models.Model):
    """Ensayo de Puesta a Tierra (PAT)."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    id_ensayo = models.CharField(max_length=50, unique=True)

    verificacion = models.ForeignKey(
        Verificacion,
        null=True, blank=True,
        on_delete=models.CASCADE,
        related_name='ensayos_pat',
    )
    componente = models.ForeignKey(
        'inventario.Componente',
        on_delete=models.CASCADE,
        related_name='ensayos_pat',
    )

    fecha_ensayo = models.DateTimeField()
    metodo_pat = models.CharField(max_length=50, blank=True, help_text='Ej: Metodo_62%')
    equipo_medicion = models.CharField(max_length=100, blank=True)
    temperatura_ambiente_c = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    condicion_suelo = models.CharField(max_length=30, blank=True, help_text='Ej: Húmedo / Seco')

    RESULTADO = [
        ('CONFORME', 'Conforme'),
        ('NO_CONFORME', 'No Conforme'),
        ('PENDIENTE', 'Pendiente Análisis'),
    ]
    resultado = models.CharField(max_length=20, choices=RESULTADO, blank=True)

    foto = models.ImageField(upload_to='ensayos_pat/%Y/%m/', null=True, blank=True)
    observaciones = models.TextField(blank=True)

    class Meta:
        verbose_name = 'Ensayo PAT'
        verbose_name_plural = 'Ensayos PAT'
        ordering = ['-fecha_ensayo']

    def __str__(self):
        return f"Ensayo PAT {self.id_ensayo}"


class LecturaPAT(models.Model):
    """Lectura individual de un ensayo PAT (distancia + valor en Ohm)."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    id_lectura = models.CharField(max_length=50, unique=True)

    ensayo = models.ForeignKey(
        EnsayoPAT,
        on_delete=models.CASCADE,
        related_name='lecturas',
    )

    TIPO = [
        ('MEDICION', 'Medición'),
        ('VALIDACION', 'Validación'),
    ]
    tipo_lectura = models.CharField(max_length=15, choices=TIPO)
    distancia_m = models.PositiveIntegerField(help_text='Distancia en metros')
    valor_ohm = models.DecimalField(max_digits=10, decimal_places=2)
    observaciones = models.TextField(blank=True)

    class Meta:
        verbose_name = 'Lectura PAT'
        verbose_name_plural = 'Lecturas PAT'
        ordering = ['ensayo', 'distancia_m']

    def __str__(self):
        return f"{self.get_tipo_lectura_display()} @ {self.distancia_m}m = {self.valor_ohm}Ω"


# =====================================================
# RECLAMOS
# =====================================================

class Reclamo(models.Model):
    """
    Reclamo de mantenimiento con workflow de estados.
    Las reglas de cada cambio (quién, desde qué estado, con qué requisitos)
    están en apps/operaciones/reclamos.py: no modificar el estado a mano.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    id_reclamo = models.CharField(max_length=50, unique=True)

    # Origen: un reclamo de regulador apunta a su verificación y componente;
    # uno de ETC, a su verificación de ETC y al equipo.
    verificacion = models.ForeignKey(
        Verificacion,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='reclamos',
        verbose_name='verificación de regulador',
    )
    componente = models.ForeignKey(
        'inventario.Componente',
        null=True, blank=True,
        on_delete=models.PROTECT,
        related_name='reclamos',
    )
    verificacion_etc = models.ForeignKey(
        VerificacionETC,
        null=True, blank=True,
        on_delete=models.PROTECT,
        related_name='reclamos',
        verbose_name='verificación de ETC',
    )
    equipo_etc = models.ForeignKey(
        'inventario.EquipoETC',
        null=True, blank=True,
        on_delete=models.PROTECT,
        related_name='reclamos',
        verbose_name='equipo ETC',
    )

    fecha_reclamo = models.DateTimeField(auto_now_add=True)

    ORIGEN = [
        ('VERIFICACION', 'Verificación'),
        ('MANUAL', 'Manual'),
        ('EXTERNO', 'Externo'),
    ]
    origen_reclamo = models.CharField(max_length=20, choices=ORIGEN, default='VERIFICACION')
    descripcion = models.TextField()
    tipo_reclamo = models.CharField(max_length=100, blank=True)
    prioridad = models.CharField(
        max_length=10,
        choices=[
            ('BAJA', 'Baja'),
            ('MEDIA', 'Media'),
            ('ALTA', 'Alta'),
            ('CRITICA', 'Crítica'),
        ],
        blank=True,
    )

    ESTADO = [
        ('ABIERTO', 'Abierto'),
        ('ASIGNADO', 'Asignado'),
        ('EN_PROCESO', 'En Proceso'),
        ('PENDIENTE_VALIDACION', 'Pendiente de validación'),
        # Cerrado = trabajo validado por el supervisor (antes existía también
        # "Resuelto", con el mismo significado; se unificaron)
        ('CERRADO', 'Cerrado'),
        ('RECHAZADO', 'Rechazado'),
    ]
    # 25: 'PENDIENTE_VALIDACION' tiene 20 caracteres
    estado = models.CharField(max_length=25, choices=ESTADO, default='ABIERTO')

    agencia_responsable = models.ForeignKey(
        'inventario.Agencia',
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='reclamos_responsable',
    )
    responsable_asignado = models.ForeignKey(
        'inventario.Personal',
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='reclamos_asignados',
    )

    requiere_intervencion = models.BooleanField(default=True)
    fecha_limite = models.DateTimeField(
        null=True, blank=True, db_index=True,
        help_text='Plazo para resolverlo, según la prioridad (ver PLAZOS en reclamos.py)',
    )
    fecha_asignacion = models.DateTimeField(null=True, blank=True)
    fecha_inicio = models.DateTimeField(
        null=True, blank=True, help_text='Cuándo el técnico empezó el trabajo (con la foto del estado inicial)',
    )
    fecha_ejecucion = models.DateTimeField(null=True, blank=True)
    fecha_cierre = models.DateTimeField(null=True, blank=True)
    validado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='reclamos_validados',
        help_text='Supervisor que aprobó el trabajo del técnico',
    )
    fecha_validacion = models.DateTimeField(null=True, blank=True)
    resultado = models.TextField(blank=True)
    motivo_rechazo = models.TextField(blank=True)
    foto_evidencia_antes = models.ImageField(upload_to='reclamos/antes/%Y/%m/', null=True, blank=True)
    foto_evidencia_despues = models.ImageField(upload_to='reclamos/despues/%Y/%m/', null=True, blank=True)
    observaciones_cierre = models.TextField(blank=True)

    # Dónde estaba el técnico al enviar la evidencia (prueba de que trabajó en el lugar)
    ubicacion_evidencia = gis_models.PointField(geography=True, null=True, blank=True)
    precision_evidencia_m = models.PositiveIntegerField(
        null=True, blank=True, help_text='Precisión informada por el GPS del celular',
    )
    distancia_evidencia_m = models.PositiveIntegerField(
        null=True, blank=True, help_text='Distancia al equipo, calculada por el servidor',
    )

    class Meta:
        verbose_name = 'Reclamo'
        verbose_name_plural = 'Reclamos'
        ordering = ['-fecha_reclamo']
        indexes = [
            models.Index(fields=['estado', 'prioridad']),
            models.Index(fields=['-fecha_reclamo']),
        ]

    def __str__(self):
        return f"Reclamo {self.id_reclamo} - {self.get_estado_display()}"


class HistorialReclamo(models.Model):
    """
    Bitácora de un reclamo: cada cambio de estado, asignación o dato, con
    quién lo hizo, cuándo y por qué. Solo se agrega; nunca se edita.
    """
    reclamo = models.ForeignKey(Reclamo, on_delete=models.CASCADE, related_name='historial')
    fecha = models.DateTimeField(default=timezone.now, db_index=True)
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='+',
    )
    # Copia del nombre: si el usuario se da de baja, el historial sigue diciendo quién fue
    usuario_nombre = models.CharField(max_length=150, blank=True)
    estado_anterior = models.CharField(max_length=25, choices=Reclamo.ESTADO, blank=True)
    estado_nuevo = models.CharField(max_length=25, choices=Reclamo.ESTADO, blank=True)
    detalle = models.TextField(blank=True, help_text='Qué cambió (asignación, prioridad, etc.)')
    comentario = models.TextField(blank=True, help_text='Motivo o nota de quien hizo el cambio')

    class Meta:
        verbose_name = 'Movimiento del reclamo'
        verbose_name_plural = 'Historial del reclamo'
        ordering = ['fecha', 'id']

    def __str__(self):
        return f"{self.reclamo.id_reclamo} · {self.fecha:%d/%m/%Y %H:%M} · {self.usuario_nombre}"
