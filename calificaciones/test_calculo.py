from decimal import Decimal

from django.test import SimpleTestCase

from .calculo import (
    CONCEPTOS_FACTORES,
    FACTORES_SIN_FORMULA_DEFAULT,
    SumaCeroError,
    factores_desde_montos,
    factores_validos,
    suma_factores_8_a_19,
)


class FactoresDesdeMontosTests(SimpleTestCase):
    """El ejemplo del HDU: suma de montos 8 a 19 = 368.745.318."""

    def test_ejemplo_del_hdu(self):
        montos = {
            8: Decimal('192770580'),
            9: Decimal('64161878'),
            10: Decimal('0'),
            11: Decimal('111812860'),
            25: Decimal('71298705'),
            30: Decimal('15837333'),
        }
        factores = factores_desde_montos(montos)
        self.assertEqual(factores[8], Decimal('0.52277431'))
        self.assertEqual(factores[9], Decimal('0.17400052'))
        self.assertEqual(factores[10], Decimal('0.00000000'))
        self.assertEqual(factores[11], Decimal('0.30322517'))
        self.assertEqual(factores[25], Decimal('0.19335488'))
        self.assertEqual(factores[30], Decimal('0.04294924'))

    def test_conceptos_34_a_37_no_se_calculan(self):
        # Los factores 34 a 37 son de ingreso directo: no deben devolverlos
        # factores_desde_montos, que solo calcula 8 a 33.
        factores = factores_desde_montos({8: Decimal('100')})
        for numero in range(34, 38):
            self.assertNotIn(numero, factores)

    def test_conceptos_20_a_33_tienen_formula(self):
        # Un monto en el concepto 20 debe dar el mismo factor que si estuviera en
        # el rango de la suma: monto / suma(8 a 19).
        factores = factores_desde_montos({8: Decimal('100'), 20: Decimal('50')})
        self.assertEqual(factores[20], Decimal('0.50000000'))

    def test_conceptos_ausentes_tratados_como_cero(self):
        factores = factores_desde_montos({8: Decimal('100')})
        self.assertEqual(factores[9], Decimal('0.00000000'))


class SumaCeroTests(SimpleTestCase):
    def test_total_en_cero_lanza_error(self):
        with self.assertRaises(SumaCeroError):
            factores_desde_montos({})

    def test_todos_los_conceptos_en_cero(self):
        with self.assertRaises(SumaCeroError):
            factores_desde_montos({n: Decimal('0') for n in range(8, 20)})


class ValidacionSumaTests(SimpleTestCase):
    def test_suma_exacta_uno_aceptada(self):
        factores = {8: Decimal('1.00000000')}
        self.assertTrue(factores_validos(factores))

    def test_suma_mayor_a_uno_rechazada(self):
        factores = {8: Decimal('0.50000000'), 9: Decimal('0.80000000')}
        self.assertFalse(factores_validos(factores))

    def test_suma_1_00000001_con_tolerancia_cero_rechazada(self):
        # Dos factores que suman 1,00000001: 0.50000000 + 0.50000001.
        factores = {8: Decimal('0.50000000'), 9: Decimal('0.50000001')}
        self.assertFalse(factores_validos(factores, estricto=True))

    def test_seis_montos_iguales_aceptados_con_tolerancia_por_defecto(self):
        # Cada factor es 0,16666667 y suman 1,00000002, dentro de la tolerancia.
        factores = {n: Decimal('0.16666667') for n in range(8, 14)}
        self.assertTrue(factores_validos(factores))

    def test_seis_montos_iguales_rechazados_con_tolerancia_cero(self):
        factores = {n: Decimal('0.16666667') for n in range(8, 14)}
        self.assertFalse(factores_validos(factores, estricto=True))

    def test_factor_mayor_a_uno_rechazado(self):
        factores = {8: Decimal('1.50000000')}
        self.assertFalse(factores_validos(factores))

    def test_factor_mayor_a_uno_rechazado_incluso_con_suma_pequena(self):
        factores = {8: Decimal('1.50000000'), 9: Decimal('0.00000000')}
        self.assertFalse(factores_validos(factores))

    def test_factor_34_mayor_a_uno_rechazado(self):
        # Los factores 34 a 37 son de ingreso directo pero siguen la regla 0 <= factor <= 1.
        factores = {8: Decimal('1.00000000'), 34: Decimal('1.50000000')}
        self.assertFalse(factores_validos(factores))

    def test_factor_34_en_rango_aceptado(self):
        factores = {8: Decimal('1.00000000'), 34: Decimal('0.50000000')}
        self.assertTrue(factores_validos(factores))


class SumaFactoresTests(SimpleTestCase):
    def test_suma_factores_8_a_19(self):
        factores = {8: Decimal('0.50000000'), 9: Decimal('0.50000000'), 19: Decimal('0.00000000')}
        self.assertEqual(suma_factores_8_a_19(factores), Decimal('1.00000000'))

    def test_suma_con_factores_ausentes(self):
        self.assertEqual(suma_factores_8_a_19({}), Decimal('0'))