from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models

from cuentas.models import Corredora


class EventoAuditoria(models.Model):
    class Accion(models.TextChoices):
        CREAR = 'CREAR', 'Creación'
        MODIFICAR = 'MODIFICAR', 'Modificación'
        BAJA = 'BAJA', 'Baja lógica'

    accion = models.CharField(max_length=10, choices=Accion.choices)
    fecha = models.DateTimeField(auto_now_add=True, db_index=True)
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='eventos_auditoria',
    )
    usuario_nombre = models.CharField(max_length=150)
    corredora = models.ForeignKey(
        Corredora,
        on_delete=models.PROTECT,
        related_name='eventos_auditoria',
    )
    calificacion_id = models.PositiveBigIntegerField(db_index=True)
    estado_anterior = models.JSONField(null=True, blank=True, encoder=DjangoJSONEncoder)
    estado_posterior = models.JSONField(null=True, blank=True, encoder=DjangoJSONEncoder)

    class Meta:
        ordering = ['-fecha', '-pk']
        default_permissions = ('view',)
        verbose_name = 'evento de auditoría'
        verbose_name_plural = 'eventos de auditoría'

    def __str__(self):
        return f'{self.get_accion_display()} · calificación {self.calificacion_id}'


def estado_calificacion(calificacion, detalles=None):
    """Representación estable de una calificación local y sus detalles.

    ``detalles`` permite pasar los detalles ya cargados (por ejemplo en la carga CSV, para
    no hacer una consulta por fila); si se omite, se leen de la base de datos.
    """
    if detalles is None:
        detalles = calificacion.detalles.order_by('concepto_id')
    else:
        detalles = sorted(detalles, key=lambda detalle: detalle.concepto_id)
    return {
        'instrumento_id': calificacion.instrumento_id,
        'ejercicio': calificacion.ejercicio,
        'fecha_pago': calificacion.fecha_pago,
        'secuencia_evento': calificacion.secuencia_evento,
        'numero_dividendo': calificacion.numero_dividendo,
        'descripcion': calificacion.descripcion,
        'valor_historico': calificacion.valor_historico,
        'factor_actualizacion': calificacion.factor_actualizacion,
        'isfut': calificacion.isfut,
        'corredora_id': calificacion.corredora_id,
        'base_id': calificacion.base_id,
        'forma_ingreso': calificacion.forma_ingreso,
        'activa': calificacion.activa,
        'creada': calificacion.creada,
        'modificada': calificacion.modificada,
        'detalles': [
            {
                'concepto_id': detalle.concepto_id,
                'monto': detalle.monto,
                'factor': detalle.factor,
            }
            for detalle in detalles
        ],
    }

