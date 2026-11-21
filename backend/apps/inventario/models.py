"""
SIGVER - Modelos de Inventario
"""
import uuid

from django.contrib.gis.db import models as gis_models
from django.db import models


# =====================================================
# ORGANIZACIONAL
# =====================================================

class SeccionRegional(models.Model):
    """Sección regional de distribución (Encarnación, Misiones, Pilar)."""
    nombre = models.CharField(max_length=100, unique=True)
    codigo = models.CharField(max_length=20, unique=True)

    class Meta:
        verbose_name = 'Sección Regional'
        verbose_name_plural = 'Secciones Regionales'
        ordering = ['nombre']

    def __str__(self):
        return self.nombre


class Agencia(models.Model):
    """Agencia de ANDE (unidad organizacional y geográfica)."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    id_seccion = models.CharField(max_length=20, unique=True, help_text='Ej: DR/ARI2')
    nombre = models.CharField(max_length=100, help_text='Ej: Encarnación')
    seccion_regional = models.ForeignKey(
        SeccionRegional,
        on_delete=models.PROTECT,
        related_name='agencias',
    )

    class Meta:
        verbose_name = 'Agencia'
        verbose_name_plural = 'Agencias'
        ordering = ['nombre']

    def __str__(self):
        return f"{self.nombre} ({self.id_seccion})"


class Personal(models.Model):
    """Directorio de funcionarios del Departamento de Operación."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    id_personal = models.CharField(max_length=20, unique=True, help_text='Ej: PER-009')
    nombre_completo = models.CharField(max_length=150)
    agencia = models.ForeignKey(
        Agencia,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='personal',
    )
    tipo_participacion = models.CharField(max_length=50, blank=True)
    cargo = models.CharField(max_length=100, blank=True)
    telefono = models.CharField(max_length=30, blank=True)
    correo = models.EmailField(blank=True)
    activo = models.BooleanField(default=True)
    origen_registro = models.CharField(max_length=50, blank=True)
    observaciones = models.TextField(blank=True)

    usuario = models.OneToOneField(
        'usuarios.Usuario',
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='personal',
        help_text='Usuario de Django. Solo quienes acceden a la PWA.',
    )

    class Meta:
        verbose_name = 'Personal'
        verbose_name_plural = 'Personal'
        ordering = ['id_personal']

    def __str__(self):
        return f"{self.id_personal} - {self.nombre_completo}"

    @property
    def tiene_acceso(self):
        return self.usuario is not None


# =====================================================
# INVENTARIO: RED ELÉCTRICA
# =====================================================

class SubEstacion(models.Model):
    """Subestación eléctrica (BRO, ENC, NAT, etc.)."""
    codigo = models.CharField(max_length=20, unique=True)
    nombre = models.CharField(max_length=100, blank=True)

    class Meta:
        verbose_name = 'Subestación'
        verbose_name_plural = 'Subestaciones'
        ordering = ['codigo']

    def __str__(self):
        return self.codigo


class Alimentador(models.Model):
    """Alimentador eléctrico (BRO1, SJB_01, etc.)."""
    codigo = models.CharField(max_length=30, unique=True)
    subestacion = models.ForeignKey(
        SubEstacion,
        on_delete=models.PROTECT,
        related_name='alimentadores',
    )

    class Meta:
        verbose_name = 'Alimentador'
        verbose_name_plural = 'Alimentadores'
        ordering = ['codigo']

    def __str__(self):
        return self.codigo


class Sitio(models.Model):
    """Ubicación física con uno o más componentes."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    id_sitio = models.CharField(max_length=50, unique=True, help_text='Ej: SIT-001')
    cod_sitio = models.CharField(max_length=50, blank=True, help_text='Ej: RT-BRO-01-01')

    alimentador = models.ForeignKey(
        Alimentador,
        on_delete=models.PROTECT,
        related_name='sitios',
    )
    agencia = models.ForeignKey(
        Agencia,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='sitios',
    )

    # Ubicación
    ubicacion_base = gis_models.PointField(geography=True, null=True, blank=True)
    utm_este = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    utm_norte = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    # Configuración del banco
    CONFIG_BANCO = [
        ('DELTA_CERRADO', 'Delta Cerrado'),
        ('DELTA_ABIERTO', 'Delta Abierto'),
        ('MONOFASICO', 'Monofásico'),
    ]
    configuracion_banco = models.CharField(max_length=20, choices=CONFIG_BANCO, blank=True)
    capacidad_a = models.PositiveIntegerField(null=True, blank=True, help_text='Amperaje')
    usuario = models.CharField(max_length=30, blank=True, help_text='ANDE / EXCLUSIVO')
    tipo_base = models.CharField(max_length=50, blank=True, help_text='Ej: Directo_Suelo')

    # Estado general
    ESTADO_SITIO = [
        ('NORMAL', 'Normal'),
        ('OBSERVADO', 'Observado'),
        ('CRITICO', 'Crítico'),
        ('FUERA_SERVICIO', 'Fuera de Servicio'),
    ]
    estado_general = models.CharField(max_length=20, choices=ESTADO_SITIO, blank=True)
    fecha_ultimo_levantamiento = models.DateTimeField(null=True, blank=True)
    observaciones_generales = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Sitio'
        verbose_name_plural = 'Sitios'
        ordering = ['id_sitio']
        indexes = [
            models.Index(fields=['estado_general']),
            models.Index(fields=['agencia']),
        ]

    def __str__(self):
        return f"{self.id_sitio} - {self.cod_sitio}"


class Componente(models.Model):
    """Regulador de tensión individual dentro de un sitio."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    id_componente = models.CharField(max_length=50, unique=True)
    sitio = models.ForeignKey(
        Sitio,
        on_delete=models.CASCADE,
        related_name='componentes',
    )

    TIPO_COMPONENTE = [('REGULADOR', 'Regulador')]
    tipo_componente = models.CharField(
        max_length=20,
        choices=TIPO_COMPONENTE,
        default='REGULADOR',
    )

    tipo_conexion = models.CharField(max_length=30, blank=True)
    tipo_control_asociado = models.CharField(max_length=30, blank=True)
    fases_conexion = models.CharField(max_length=10, blank=True)
    estado_componente = models.CharField(max_length=30, blank=True)
    estado_control = models.CharField(max_length=30, blank=True)
    observaciones_componente = models.TextField(blank=True)
    observaciones_control = models.TextField(blank=True)

    class Meta:
        verbose_name = 'Componente'
        verbose_name_plural = 'Componentes'
        ordering = ['id_componente']

    def __str__(self):
        return f"{self.id_componente} @ {self.sitio.id_sitio}"


class ElementoEquipo(models.Model):
    """Elemento físico del componente (marca/modelo/serie). Relación 1:N."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    id_elemento = models.CharField(max_length=50, blank=True)
    componente = models.ForeignKey(
        Componente,
        on_delete=models.CASCADE,
        related_name='elementos',
    )

    identificador_elemento = models.CharField(max_length=100, blank=True)
    marca = models.CharField(max_length=100, blank=True)
    modelo = models.CharField(max_length=100, blank=True)
    numero_serie = models.CharField(max_length=100, blank=True)

    foto_equipo = models.ImageField(upload_to='elementos/equipo/%Y/%m/', null=True, blank=True)
    foto_placa = models.ImageField(upload_to='elementos/placa/%Y/%m/', null=True, blank=True)
    foto_control = models.ImageField(upload_to='elementos/control/%Y/%m/', null=True, blank=True)

    estado_elemento = models.CharField(max_length=30, blank=True)
    observaciones = models.TextField(blank=True)

    class Meta:
        verbose_name = 'Elemento de Equipo'
        verbose_name_plural = 'Elementos de Equipo'

    def __str__(self):
        return f"{self.marca} {self.modelo} ({self.numero_serie})"


# =====================================================
# EQUIPOS TELECOMANDADOS (ETC)
# =====================================================

class EquipoETC(models.Model):
    """Inventario maestro de ETC. Se carga a medida que se verifican."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    nro_equipo = models.CharField(max_length=50, unique=True, help_text='Ej: 37008')

    alimentador = models.ForeignKey(
        Alimentador,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='equipos_etc',
    )
    sitio = models.ForeignKey(
        Sitio,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='equipos_etc',
    )

    ubicacion = gis_models.PointField(geography=True, null=True, blank=True)

    ESTADO_SECCIONADOR = [('ABIERTO', 'Abierto'), ('CERRADO', 'Cerrado')]
    estado_seccionador = models.CharField(
        max_length=10,
        choices=ESTADO_SECCIONADOR,
        default='CERRADO',
        help_text='Solo modificable desde el admin de Django',
    )
    CUCHILLAS = [
        ('SI', 'Sí tiene'),
        ('NO', 'No tiene'),
        ('FALTA_FOTO', 'Falta foto'),
    ]
    cuchillas_laterales = models.CharField(
        max_length=15,
        choices=CUCHILLAS,
        blank=True,
        help_text='Presencia de cuchillas laterales',
    )


    fecha_ultima_verificacion = models.DateTimeField(null=True, blank=True)
    tiene_problema_actual = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Equipo Telecomandado'
        verbose_name_plural = 'Equipos Telecomandados'
        ordering = ['nro_equipo']

    def __str__(self):
        return f"ETC-{self.nro_equipo}"