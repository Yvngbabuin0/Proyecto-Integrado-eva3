"""Cálculo de factores tributarios.

Todas las funciones son puras: no acceden a la base de datos ni a Django, y
trabajan con :class:`decimal.Decimal` en nunca con ``float``. El redondeo es
siempre explícito con ``ROUND_HALF_UP``.

La regla general del HDU es::

    factor = monto / suma(montos de los conceptos 8 a 19)

y se aplica a los conceptos 8 a 33. Los conceptos 34 a 37 no tienen fórmula
(veáse :data:`FACTORES_SIN_FORMULA_DEFAULT`).
"""

from decimal import Decimal, ROUND_HALF_UP

# Conceptos cuyos factores se calculan con la fórmula del HDU (8 a 33).
CONCEPTOS_CON_FORMULA = range(8, 34)
# Conceptos cuyos montos se suman para el denominador (8 a 19).
CONCEPTOS_SUMA = range(8, 20)
# Rango completo de factores del certificado (8 a 37): incluye los 4 de ingreso
# directo que no tienen fórmula pero sí validación de rango individual.
CONCEPTOS_FACTORES = range(8, 38)
# Cada factor debe ser <= 1.
FACTOR_MAXIMO = Decimal(1)
# Decimales a los que se redondea cada factor.
DECIMALES_FACTOR = Decimal('0.00000001')
# Suma máxima permitida de los factores 8 a 19.
SUMA_FACTORES_MAXIMA = Decimal(1)
# Máximo error acumulado al redondear los 12 factores de la suma (8 a 19).
# Cada factor se redondea a 8 decimales con ROUND_HALF_UP, así que su error
# es como máximo 0,000000005 (media unidad del último decimal). Como la suma
# lleva 12 factores, el error total puede llegar a 12 x 0,000000005 = 0,00000006.
# Por ejemplo, seis montos iguales dan factor 0,16666667 y suman 1,00000002.
TOLERANCIA_SUMA_POR_DEFECTO = Decimal('0.00000006')

# Los conceptos 34 a 37 no tienen fórmula en el HDU. Por defecto se les asigna
# factor 0; cambiar esta constante (por ejemplo a ``Decimal('0.5')``) modifica
# el valor con el que los devuelven :func:`factores_desde_montos` sin tocar la
# lógica del resto del módulo.
FACTORES_SIN_FORMULA_DEFAULT = Decimal(0)


class SumaCeroError(ValueError):
    """La suma de los montos 8 a 19 es 0, por lo que no se puede dividir."""


def _redondear(value: Decimal) -> Decimal:
    """Redondea ``value`` a 8 decimales con el criterio ``ROUND_HALF_UP``."""
    return value.quantize(DECIMALES_FACTOR, rounding=ROUND_HALF_UP)


def _suma_montos(montos: dict) -> Decimal:
    """Suma los montos de los conceptos 8 a 19. Devuelve ``Decimal(0)`` si no hay."""
    return sum((montos.get(n, Decimal(0)) for n in CONCEPTOS_SUMA), Decimal(0))


def factores_desde_montos(montos: dict) -> dict:
    """Calcula los factores 8 a 33 a partir de un monto por concepto.

    ``montos`` es un mapeo ``numero_de_concepto -> Decimal`` (o lo que se
    pueda convertir a él); los conceptos ausentes se tratan como monto 0.

    Los factores 8 a 33 se calculan como ``monto / suma(8 a 19)``. Los
    conceptos 34 a 37 no tienen fórmula (ingreso directo) y no se devuelven
    aquí; véase :data:`FACTORES_SIN_FORMULA_DEFAULT`.

    Lanza :class:`SumaCeroError` si la suma de los montos 8 a 19 es 0.
    """
    suma = _suma_montos(montos)
    if suma == 0:
        raise SumaCeroError(
            'La suma de los montos de los conceptos 8 a 19 es 0; no se puede calcular el factor.'
        )

    factores = {}
    for numero in CONCEPTOS_CON_FORMULA:
        monto = montos.get(numero, Decimal(0))
        factores[numero] = _redondear(monto / suma)
    return factores


def suma_factores_8_a_19(factores: dict) -> Decimal:
    """Suma los factores del rango 8 a 19 (los que participan en la suma)."""
    return sum((factores.get(n, Decimal(0)) for n in CONCEPTOS_SUMA), Decimal(0))


def factores_validos(factores: dict, *, estricto=False) -> bool:
    """Valida las reglas de los factores calculados.

    Cada factor 8 a 33 debe ser <= 1 y la suma de los factores 8 a 19 debe ser
    <= 1 (más la tolerancia que corresponda).

    **Sobre la suma y el redondeo.** La suma de los factores *exactos*
    (monto / Σmontos, sin redondear) es exactamente 1, porque cada monto es una
    fracción de la misma suma. Pero cuando redondeamos cada factor a 8
    decimales con ``ROUND_HALF_UP``, ese redondeo puede sumar o restar una
    unidades del último decimal por factor. Con seis montos iguales, cada
    factor exacto es 0,16666666666… y al redondear queda 0,16666667: seis veces
    0,16666667 suman 1,00000002, que supera 1. Validar la suma contra los
    factores redondeados sin tolerancia daría un falso negativo.

    Por eso la validación de la suma permite una tolerancia por defecto de
    :data:`TOLERANCIA_SUMA_POR_DEFECTO` (12 factores x 0,000000005 = 0,00000006),
    que cubre el peor caso de acumulación de errores de redondeo. Cuando los
    factores se ingresan a mano (el usuario los escribe) no hay redondeo, así
    que se usa ``estricto=True``: la suma debe ser <= 1 sin tolerancia.
    """
    tolerancia = 0 if estricto else TOLERANCIA_SUMA_POR_DEFECTO
    # Rango individual aplica a todos los factores 8 a 37, incluidos los de
    # ingreso directo (34 a 37) que no tienen fórmula pero sí validación de rango.
    for numero in CONCEPTOS_FACTORES:
        if factores.get(numero, Decimal(0)) > FACTOR_MAXIMO:
            return False
    if suma_factores_8_a_19(factores) > SUMA_FACTORES_MAXIMA + tolerancia:
        return False
    return True