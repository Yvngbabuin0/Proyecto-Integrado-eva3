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

    def test_seis_montos_iguales_suman_exactamente_uno(self):
        # Redondeados uno por uno darían 0,16666667 x 6 = 1,00000002.
        factores = factores_desde_montos({n: Decimal('1') for n in range(8, 14)})
        self.assertEqual(suma_factores_8_a_19(factores), Decimal('1.00000000'))
        self.assertEqual(
            [factores[n] for n in range(8, 14)],
            [Decimal('0.16666667')] * 4 + [Decimal('0.16666666')] * 2,
        )

    def test_doce_montos_distintos_suman_exactamente_uno(self):
        factores = factores_desde_montos({n: Decimal(n * 7919) for n in range(8, 20)})
        self.assertEqual(suma_factores_8_a_19(factores), Decimal('1.00000000'))
        self.assertTrue(factores_validos(factores))

    def test_el_ajuste_va_al_factor_con_mayor_resto(self):
        # 2/3 = 0,666666666… y 1/3 = 0,333333333…: la unidad que falta va al 8, que tiene mayor resto.
        factores = factores_desde_montos({8: Decimal('2'), 9: Decimal('1')})
        self.assertEqual(factores[8], Decimal('0.66666667'))
        self.assertEqual(factores[9], Decimal('0.33333333'))


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

    def test_suma_1_00000001_rechazada(self):
        # Dos factores que suman 1,00000001: 0.50000000 + 0.50000001.
        factores = {8: Decimal('0.50000000'), 9: Decimal('0.50000001')}
        self.assertFalse(factores_validos(factores))

    def test_seis_factores_redondeados_hacia_arriba_rechazados(self):
        # Seis veces 0,16666667 suma 1,00000002: supera 1 y se bloquea.
        factores = {n: Decimal('0.16666667') for n in range(8, 14)}
        self.assertFalse(factores_validos(factores))

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