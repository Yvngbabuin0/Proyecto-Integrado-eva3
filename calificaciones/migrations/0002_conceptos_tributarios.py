from django.db import migrations

# Catálogo de los 30 conceptos (8–37), tomado del prototipo alineado con el Excel del cliente.
# Ojo: 28 y 33 tienen el mismo nombre ("Crédito por IPE"); falta confirmarlo con el cliente.
CONCEPTOS = {
    8: 'Con crédito por IDPC generados a contar del 01.01.2017',
    9: 'Con crédito por IDPC acumulados hasta el 31.12.2016',
    10: 'Con derecho a crédito por pago de IDPC voluntario',
    11: 'Sin derecho a crédito',
    12: 'Rentas provenientes del registro RAP y Diferencia Inicial de sociedad acogida al ex Art. 14 ter A) LIR',
    13: 'Otras rentas percibidas sin prioridad en su orden de imputación',
    14: 'Exceso de distribuciones desproporcionadas (N° 9 Art. 14 A) LIR',
    15: 'Utilidades afectadas con impuesto sustitutivo al FUT (ISFUT) Ley N° 20.780',
    16: 'Rentas generadas hasta el 31.12.1983 y/o utilidades afectadas con impuesto sustitutivo al FUT (ISFUT) Ley N° 21.210',
    17: 'Rentas exentas de Impuesto Global Complementario (IGC) (Artículo 11, Ley 18.401), afectas a Impuesto Adicional',
    18: 'Rentas exentas de Impuesto Global Complementario (IGC) y/o Impuesto Adicional (IA)',
    19: 'Ingresos No Constitutivos de Renta',
    20: 'Asociados a rentas afectas · No sujetos a restitución generados hasta el 31.12.2019 · Sin derecho a devolución',
    21: 'Asociados a rentas afectas · No sujetos a restitución generados hasta el 31.12.2019 · Con derecho a devolución',
    22: 'Asociados a rentas afectas · No sujetos a restitución generados a contar del 01.01.2020 · Sin derecho a devolución',
    23: 'Asociados a rentas afectas · No sujetos a restitución generados a contar del 01.01.2020 · Con derecho a devolución',
    24: 'Acumulados a contar del 01.01.2017 · Asociados a rentas afectas · Sujetos a restitución · Sin derecho a devolución',
    25: 'Acumulados a contar del 01.01.2017 · Asociados a rentas afectas · Sujetos a restitución · Con derecho a devolución',
    26: 'Acumulados a contar del 01.01.2017 · Asociados a rentas exentas · Sujetos a restitución · Sin derecho a devolución',
    27: 'Acumulados a contar del 01.01.2017 · Asociados a rentas exentas · Sujetos a restitución · Con derecho a devolución',
    28: 'Crédito por IPE',
    29: 'Acumulados hasta el 31.12.2016 · Asociados a rentas afectas · Sin derecho a devolución',
    30: 'Acumulados hasta el 31.12.2016 · Asociados a rentas afectas · Con derecho a devolución',
    31: 'Acumulados hasta el 31.12.2016 · Asociados a rentas exentas · Sin derecho a devolución',
    32: 'Acumulados hasta el 31.12.2016 · Asociados a rentas exentas · Con derecho a devolución',
    33: 'Crédito por IPE',
    34: 'Crédito por impuesto tasa adicional, ex Art. 21 LIR',
    35: 'Tasa efectiva del crédito del FUT (TEF)',
    36: 'Tasa efectiva del crédito del FUNT (TEX)',
    37: 'Devolución de capital Art. 17 N° 7 LIR',
}


def crear_conceptos(apps, schema_editor):
    ConceptoTributario = apps.get_model('calificaciones', 'ConceptoTributario')
    ConceptoTributario.objects.bulk_create(
        ConceptoTributario(numero=numero, nombre=nombre) for numero, nombre in CONCEPTOS.items()
    )


def borrar_conceptos(apps, schema_editor):
    apps.get_model('calificaciones', 'ConceptoTributario').objects.filter(numero__in=CONCEPTOS).delete()


class Migration(migrations.Migration):
    dependencies = [
        ('calificaciones', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(crear_conceptos, borrar_conceptos),
    ]
