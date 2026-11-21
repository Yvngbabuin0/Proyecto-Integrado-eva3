"""Registro de cada carga CSV como un LoteCarga, con su archivo original y su evento de auditoría."""

import hashlib
import io
import uuid

from django.conf import settings
from django.db import transaction

from auditoria.models import EventoAuditoria

from .importador_csv import guardar_registros, validar_csv
from .models import LoteCarga


def ruta_archivo(archivo_id):
    return settings.CSV_LOTES_DIR / f'{uuid.UUID(str(archivo_id))}.csv'


def _nuevo_lote(contenido, nombre, corredora, usuario, estado):
    """Guarda el archivo original con un nombre generado y crea su LoteCarga."""
    archivo_id = uuid.uuid4()
    settings.CSV_LOTES_DIR.mkdir(parents=True, exist_ok=True)
    ruta_archivo(archivo_id).write_bytes(contenido)
    return LoteCarga.objects.create(
        corredora=corredora,
        usuario=usuario,
        estado=estado,
        archivo_id=archivo_id,
        nombre_original=nombre[:255],
        tamano=len(contenido),
        huella=hashlib.sha256(contenido).hexdigest(),
    )


def _evento_lote(lote, accion):
    EventoAuditoria.objects.create(
        accion=accion,
        usuario=lote.usuario,
        usuario_nombre=lote.usuario.get_username(),
        corredora=lote.corredora,
        lote=lote,
    )


def confirmar_carga(contenido, nombre, corredora, usuario):
    """Valida y guarda el archivo completo en una sola transacción. Lanza ErrorCSV si no es válido.

    Quedan en la misma transacción las calificaciones, el lote, su archivo y los eventos (uno por
    calificación y uno de la carga): si algo falla, no queda nada.
    """
    registros, _ = validar_csv(io.BytesIO(contenido), corredora)
    with transaction.atomic():
        lote = _nuevo_lote(contenido, nombre, corredora, usuario, LoteCarga.Estado.CARGADO)
        try:
            resultado = guardar_registros(registros, corredora, usuario, lote=lote)
        except Exception:
            ruta_archivo(lote.archivo_id).unlink(missing_ok=True)
            raise
        lote.filas = len(registros)
        lote.nuevas = resultado['nuevas']
        lote.actualizadas = resultado['actualizadas']
        lote.save(update_fields=['filas', 'nuevas', 'actualizadas'])
        _evento_lote(lote, EventoAuditoria.Accion.CARGA)
    return lote


def registrar_rechazo(contenido, nombre, corredora, usuario, error):
    """Deja constancia de un archivo rechazado. Se llama después de revertir la carga."""
    with transaction.atomic():
        lote = _nuevo_lote(contenido, nombre, corredora, usuario, LoteCarga.Estado.RECHAZADO)
        lote.errores = [error.detalle()]
        lote.save(update_fields=['errores'])
        _evento_lote(lote, EventoAuditoria.Accion.RECHAZO)
    return lote
