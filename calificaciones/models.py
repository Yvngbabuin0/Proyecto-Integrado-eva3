from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from cuentas.models import Corredora

# Conceptos cuyos factores participan en la suma (supuesto 8–19 del informe ES2).
CONCEPTOS_SUMA = range(8, 20)
# Todos los conceptos del catálogo: 8 a 37.
CONCEPTOS = range(8, 38)


class Mercado(models.TextChoices):
    ACCIONES = 'ACC', 'Acciones'
    CFI = 'CFI', 'CFI'
    FONDOS_MUTUOS = 'FM', 'Fondos Mutuos'


class Instrumento(models.Model):
    codigo = models.CharField(max_length=30)
    mercado = models.CharField(max_length=3, choices=Mercado.choices)
    inscrito = models.BooleanField(default=True)

    class Meta:
        ordering = ['codigo']
        constraints = [
            models.UniqueConstraint(fields=['codigo', 'mercado'], name='instrumento_unico_por_mercado'),
        ]

    def __str__(self):
        return self.codigo


class ConceptoTributario(models.Model):
    numero = models.PositiveSmallIntegerField(primary_key=True)
    nombre = models.TextField()

    class Meta:
        ordering = ['numero']

    def __str__(self):
        return f'{self.numero} · {self.nombre}'


class DatosCalificacion(models.Model):
    """Campos comunes a la calificación de Bolsa y a la local de cada corredora."""

    instrumento = models.ForeignKey(Instrumento, on_delete=models.PROTECT)
    ejercicio = models.PositiveSmallIntegerField()
    fecha_pago = models.DateField()
    secuencia_evento = models.PositiveBigIntegerField()
    numero_dividendo = models.PositiveIntegerField(default=0)
    descripcion = models.CharField(max_length=200)
    valor_historico = models.DecimalField(max_digits=18, decimal_places=8, default=0)
    factor_actualizacion = models.DecimalField(max_digits=12, decimal_places=8, default=0)
    isfut = models.BooleanField('ISFUT', default=False)

    class Meta:
        abstract = True
        ordering = ['-ejercicio', 'instrumento__codigo', 'secuencia_evento']

    def __str__(self):
        return f'{self.instrumento} · {self.ejercicio} · evento {self.secuencia_evento}'


class CalificacionBase(DatosCalificacion):
    """Calificación informada por Bolsa. El mantenedor nunca escribe en esta tabla."""

    class Meta(DatosCalificacion.Meta):
        verbose_name = 'calificación de Bolsa'
        verbose_name_plural = 'calificaciones de Bolsa'


class CalificacionLocal(DatosCalificacion):
    """Calificación propia de una corredora. Solo la ve y la modifica esa corredora."""

    class FormaIngreso(models.TextChoices):
        MANUAL = 'MANUAL', 'Manual'
        ARCHIVO = 'ARCHIVO', 'Archivo'

    corredora = models.ForeignKey(Corredora, on_delete=models.PROTECT, related_name='calificaciones')
    base = models.ForeignKey(
        CalificacionBase,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='locales',
        help_text='Calificación de Bolsa que reemplaza, si existe.',
    )
    forma_ingreso = models.CharField(max_length=7, choices=FormaIngreso.choices, default=FormaIngreso.MANUAL)
    # Baja lógica: el registro sale del listado pero se conserva el histórico.
    activa = models.BooleanField(default=True)
    creada = models.DateTimeField(auto_now_add=True)
    modificada = models.DateTimeField(auto_now=True)

    class Meta(DatosCalificacion.Meta):
        verbose_name = 'calificación local'
        verbose_name_plural = 'calificaciones locales'


class Detalle(models.Model):
    """Monto y factor de un concepto (8–37). Una fila por concepto en vez de 30 columnas."""

    concepto = models.ForeignKey(ConceptoTributario, on_delete=models.PROTECT)
    monto = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    factor = models.DecimalField(
        max_digits=9,
        decimal_places=8,
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(1)],
    )

    class Meta:
        abstract = True
        ordering = ['concepto']


class DetalleBase(Detalle):
    calificacion = models.ForeignKey(CalificacionBase, on_delete=models.CASCADE, related_name='detalles')

    class Meta(Detalle.Meta):
        constraints = [
            models.UniqueConstraint(fields=['calificacion', 'concepto'], name='detalle_base_unico'),
        ]


class DetalleLocal(Detalle):
    calificacion = models.ForeignKey(CalificacionLocal, on_delete=models.CASCADE, related_name='detalles')

    class Meta(Detalle.Meta):
        constraints = [
            models.UniqueConstraint(fields=['calificacion', 'concepto'], name='detalle_local_unico'),
        ]
