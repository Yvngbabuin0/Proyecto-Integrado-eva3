"""Cálculo de factores tributarios.

Todas las funciones son puras: no acceden a la base de datos ni a Django, y
trabajan con :class:`decimal.Decimal` en nunca con ``float``. El redondeo es
siempre explícito con ``ROUND_HALF_UP``.

La regla general del HDU es::

    factor = monto / suma(montos de los conceptos 8 a 19)

y se aplica a los conceptos 8 a 33. Los conceptos 34 a 37 no tienen fórmula
(veáse :data:`FACTORES_SIN_FORMULA_DEFAULT`).
"""

from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP

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
# Tolerancia para la suma de factores 8-19 cuando vienen de cálculo (redondeo acumulado).
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
    factores.update(_repartir_suma(montos, suma))
    return factores


def _repartir_suma(montos: dict, suma: Decimal) -> dict:
    """Factores 8 a 19 redondeados a 8 decimales de modo que sumen exactamente 1.

    Redondear cada factor por separado puede hacer que la suma pase de 1: con
    seis montos iguales, cada factor queda en 0,16666667 y suman 1,00000002.
    Para evitarlo se usa el método del mayor resto: cada factor se trunca a 8
    decimales y las unidades del último decimal que faltan para llegar a 1 se
    entregan a los factores con mayor parte truncada (si empatan, al concepto
    de número menor). Cuando el redondeo normal ya suma 1, como en el ejemplo
    del HDU, el resultado es el mismo que con ``ROUND_HALF_UP``.
    """
    exactos = {n: montos.get(n, Decimal(0)) / suma for n in CONCEPTOS_SUMA}
    truncados = {n: valor.quantize(DECIMALES_FACTOR, rounding=ROUND_DOWN) for n, valor in exactos.items()}
    faltantes = int((SUMA_FACTORES_MAXIMA - sum(truncados.values())) / DECIMALES_FACTOR)
    por_resto = sorted(CONCEPTOS_SUMA, key=lambda n: (-(exactos[n] - truncados[n]), n))
    for numero in por_resto[:faltantes]:
        truncados[numero] += DECIMALES_FACTOR
    return truncados


def suma_factores_8_a_19(factores: dict) -> Decimal:
    """Suma los factores del rango 8 a 19 (los que participan en la suma)."""
    return sum((factores.get(n, Decimal(0)) for n in CONCEPTOS_SUMA), Decimal(0))


def factores_validos(factores: dict, *, estricto: bool = True) -> bool:
    """Valida las reglas de los factores.

    Cada factor 8 a 37 debe ser <= 1 y la suma de los factores 8 a 19 debe ser
    <= 1. Si ``estricto=True`` (por defecto), la suma debe ser <= 1 sin tolerancia.
    Si ``estricto=False``, se permite una tolerancia de ``TOLERANCIA_SUMA_POR_DEFECTO``
    para cubrir el redondeo acumulado de factores calculados desde montos.

    Los factores que entrega :func:`factores_desde_montos` ya suman exactamente 1
    (véase :func:`_repartir_suma`), así que pasan esta validación sin excepciones.
    """
    # Rango individual aplica a todos los factores 8 a 37, incluidos los de
    # ingreso directo (34 a 37) que no tienen fórmula pero sí validación de rango.
    for numero in CONCEPTOS_FACTORES:
        if factores.get(numero, Decimal(0)) > FACTOR_MAXIMO:
            return False
    suma = suma_factores_8_a_19(factores)
    if estricto:
        return suma <= SUMA_FACTORES_MAXIMA
    return suma <= SUMA_FACTORES_MAXIMA + TOLERANCIA_SUMA_POR_DEFECTO
