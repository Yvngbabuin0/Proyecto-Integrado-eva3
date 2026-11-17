"""Convierte los estados guardados en un evento en una lista legible de cambios."""

from datetime import date
from decimal import Decimal, InvalidOperation

from django.utils.formats import date_format, number_format

from calificaciones.models import CalificacionLocal, Instrumento

# Campos de la calificación que se muestran, en este orden. Los que no están aquí
# (como 'creada' o 'modificada') no se muestran porque cambian solos.
CAMPOS = {
    'instrumento_id': 'Instrumento',
    'ejercicio': 'Ejercicio',
    'fecha_pago': 'Fecha de pago',
    'secuencia_evento': 'Secuencia del evento',
    'numero_dividendo': 'Número de dividendo',
    'descripcion': 'Descripción',
    'valor_historico': 'Valor histórico',
    'factor_actualizacion': 'Factor de actualización',
    'isfut': 'ISFUT',
    'forma_ingreso': 'Forma de ingreso',
    'activa': 'Activa',
}
DECIMALES = {'valor_historico': 8, 'factor_actualizacion': 8, 'monto': 2, 'factor': 8}


def _decimal(valor, decimales):
    try:
        return number_format(Decimal(valor), decimales)
    except (InvalidOperation, TypeError, ValueError):
        return str(valor)


def formatear(campo, valor, instrumentos=None):
    if valor is None:
        return '—'
    if isinstance(valor, bool):
        return 'Sí' if valor else 'No'
    if campo in DECIMALES:
        return _decimal(valor, DECIMALES[campo])
    if campo == 'fecha_pago':
        try:
            return date_format(date.fromisoformat(valor), 'd-m-Y')
        except (TypeError, ValueError):
            return str(valor)
    if campo == 'instrumento_id' and instrumentos:
        return instrumentos.get(valor, str(valor))
    if campo == 'forma_ingreso':
        return CalificacionLocal.FormaIngreso(valor).label if valor in CalificacionLocal.FormaIngreso.values else valor
    return str(valor)


def _detalles_por_concepto(estado):
    return {d['concepto_id']: d for d in (estado or {}).get('detalles', [])}


def cambios(anterior, posterior):
    """Lista de (campo, antes, después) con solo lo que cambió.

    En una creación no hay estado anterior: se listan los valores con contenido.
    """
    anterior = anterior or {}
    posterior = posterior or {}
    ids = {e.get('instrumento_id') for e in (anterior, posterior)} - {None}
    instrumentos = dict(Instrumento.objects.filter(pk__in=ids).values_list('pk', 'codigo'))

    filas = []
    for campo, etiqueta in CAMPOS.items():
        antes, despues = anterior.get(campo), posterior.get(campo)
        # Los decimales se comparan como números: '0E-8' y '0.00000000' son el mismo valor.
        if antes == despues or (campo in DECIMALES and _iguales(antes, despues)):
            continue
        if not anterior and despues in (None, '', 0, '0', False):
            continue  # en una creación, se omiten los valores vacíos
        filas.append((etiqueta, formatear(campo, antes, instrumentos), formatear(campo, despues, instrumentos)))

    detalles_antes = _detalles_por_concepto(anterior)
    detalles_despues = _detalles_por_concepto(posterior)
    for numero in sorted(detalles_antes.keys() | detalles_despues.keys()):
        for campo, etiqueta in (('monto', 'Monto'), ('factor', 'Factor')):
            antes = detalles_antes.get(numero, {}).get(campo)
            despues = detalles_despues.get(numero, {}).get(campo)
            if _iguales(antes, despues):
                continue
            if not anterior and _iguales(despues, 0):
                continue
            filas.append((f'{etiqueta} {numero}', formatear(campo, antes), formatear(campo, despues)))
    return filas


def _iguales(a, b):
    try:
        return Decimal(a or 0) == Decimal(b or 0)
    except (InvalidOperation, TypeError, ValueError):
        return a == b
