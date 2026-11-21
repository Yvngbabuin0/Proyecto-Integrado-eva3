from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models

from cuentas.models import Corredora


class EventoInmutableError(Exception):
    """Intento de modificar o eliminar un evento de auditoría: el log es de solo inserción."""


class EventoAuditoriaQuerySet(models.QuerySet):
    """QuerySet que prohíbe UPDATE y DELETE masivos."""

    def update(self, **kwargs):
        raise EventoInmutableError('No se pueden modificar eventos de auditoría (INSERT-only)')

    def delete(self):
        raise EventoInmutableError('No se pueden eliminar eventos de auditoría (INSERT-only)')


class EventoAuditoria(models.Model):
    class Accion(models.TextChoices):
        CREAR = 'CREAR', 'Creación'
        MODIFICAR = 'MODIFICAR', 'Modificación'
        BAJA = 'BAJA', 'Baja lógica'
        CARGA = 'CARGA', 'Carga CSV'
        RECHAZO = 'RECHAZO', 'Carga rechazada'

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
    # Vacío en los eventos de un lote completo (carga o rechazo), que no afectan a una sola calificación.
    calificacion_id = models.PositiveBigIntegerField(db_index=True, null=True, blank=True)
    lote = models.ForeignKey(
        'calificaciones.LoteCarga',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='eventos',
    )
    estado_anterior = models.JSONField(null=True, blank=True, encoder=DjangoJSONEncoder)
    estado_posterior = models.JSONField(null=True, blank=True, encoder=DjangoJSONEncoder)

    objects = EventoAuditoriaQuerySet.as_manager()

    class Meta:
        ordering = ['-fecha', '-pk']
        # Django usa el manager base en operaciones internas; sin esto, _base_manager.update()
        # se saltaría el bloqueo.
        base_manager_name = 'objects'
        default_permissions = ('view',)
        permissions = [
            ('ver_todas_las_corredoras', 'Puede ver los eventos de todas las corredoras'),
        ]
        verbose_name = 'evento de auditoría'
        verbose_name_plural = 'eventos de auditoría'

    def __str__(self):
        if self.calificacion_id is None:
            return f'{self.get_accion_display()} · lote {self.lote_id}'
        return f'{self.get_accion_display()} · calificación {self.calificacion_id}'

    def save(self, *args, **kwargs):
        """Prohíbe UPDATE: solo permite INSERT inicial (force_insert=True o _state.adding)."""
        if not self._state.adding and not kwargs.get('force_insert', False):
            raise EventoInmutableError('No se pueden modificar eventos de auditoría (INSERT-only)')
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        """Prohíbe DELETE de instancias individuales."""
        raise EventoInmutableError('No se pueden eliminar eventos de auditoría (INSERT-only)')


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

