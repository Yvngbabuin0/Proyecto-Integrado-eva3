from datetime import date
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from calificaciones.models import (
    CONCEPTOS,
    CalificacionBase,
    CalificacionLocal,
    DetalleBase,
    DetalleLocal,
    Instrumento,
    Mercado,
)
from cuentas.models import Corredora

# Datos ficticios basados en el prototipo de Figma. Nada de esto corresponde a datos reales.
CORREDORAS = [
    ('76.000.001-1', 'Corredora A'),
    ('76.000.002-2', 'Corredora B'),
]

# (código, ejercicio, fecha de pago, secuencia, descripción, factores 8, 9, 10...)
BOLSA = [
    ('ADP', 2025, date(2025, 4, 1), 133947, 'Dividendo USD 1,54', []),
    ('AGG', 2025, date(2025, 3, 6), 135010, 'Dividendo USD 0,304188', []),
    ('AAPL', 2025, date(2025, 2, 13), 135902, 'Dividendo USD 0,25', ['0.4', '0.6']),
]

# (corredora, código, ejercicio, fecha, secuencia, descripción, forma de ingreso, ISFUT, factor act., montos 8, 9, 10...)
LOCALES = [
    ('Corredora A', 'JEAP', 2025, date(2025, 1, 2), 100000809, 'JEAP ACC 1X1', 'MANUAL', False, '0',
     ['5000000', '3000000', '2000000']),
    ('Corredora A', 'AMGN', 2025, date(2025, 3, 7), 132575, 'Dividendo USD 2,38', 'ARCHIVO', False, '0',
     ['6000000', '4000000']),
    ('Corredora A', 'APO', 2024, date(2024, 5, 9), 136075, 'Dividendo USD 0,82', 'MANUAL', True, '1.024',
     ['7000000', '2000000', '1000000']),
    ('Corredora B', 'JEAP', 2025, date(2025, 1, 2), 100000809, 'JEAP ACC 1X1 (Corredora B)', 'MANUAL', False, '0',
     ['1000000', '1000000']),
]


def factores_desde_montos(montos):
    total = sum(montos, Decimal(0))
    return [(monto / total).quantize(Decimal('0.00000001')) for monto in montos]


class Command(BaseCommand):
    help = 'Carga corredoras, instrumentos y calificaciones ficticias para desarrollo. Se puede ejecutar varias veces.'

    @transaction.atomic
    def handle(self, *args, **options):
        corredoras = {
            nombre: Corredora.objects.get_or_create(rut=rut, defaults={'nombre': nombre})[0]
            for rut, nombre in CORREDORAS
        }

        for codigo, ejercicio, fecha, secuencia, descripcion, factores in BOLSA:
            calificacion, creada = CalificacionBase.objects.get_or_create(
                instrumento=self.instrumento(codigo),
                ejercicio=ejercicio,
                secuencia_evento=secuencia,
                defaults={'fecha_pago': fecha, 'descripcion': descripcion},
            )
            if creada:
                factores = [Decimal(f) for f in factores]
                DetalleBase.objects.bulk_create(
                    DetalleBase(calificacion=calificacion, concepto_id=numero, factor=valor)
                    for numero, valor in zip(CONCEPTOS, factores + [Decimal(0)] * 30)
                )

        for (nombre, codigo, ejercicio, fecha, secuencia, descripcion, forma, isfut, factor_act,
             montos) in LOCALES:
            calificacion, creada = CalificacionLocal.objects.get_or_create(
                corredora=corredoras[nombre],
                instrumento=self.instrumento(codigo),
                ejercicio=ejercicio,
                secuencia_evento=secuencia,
                defaults={
                    'fecha_pago': fecha,
                    'descripcion': descripcion,
                    'forma_ingreso': forma,
                    'isfut': isfut,
                    'factor_actualizacion': Decimal(factor_act),
                },
            )
            if creada:
                montos = [Decimal(m) for m in montos]
                factores = factores_desde_montos(montos)
                relleno = [Decimal(0)] * 30
                DetalleLocal.objects.bulk_create(
                    DetalleLocal(calificacion=calificacion, concepto_id=numero, monto=monto, factor=factor)
                    for numero, monto, factor in zip(CONCEPTOS, montos + relleno, factores + relleno)
                )

        self.stdout.write(self.style.SUCCESS(
            f'Datos de demostración listos: {Corredora.objects.count()} corredoras, '
            f'{CalificacionBase.objects.count()} calificaciones de Bolsa y '
            f'{CalificacionLocal.objects.count()} locales.'
        ))

    def instrumento(self, codigo):
        return Instrumento.objects.get_or_create(codigo=codigo, mercado=Mercado.ACCIONES)[0]
