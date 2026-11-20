from django.db import migrations

# Los conceptos 28 y 33 se llaman igual ("Crédito por IPE") en el certificado, pero pertenecen a
# grupos distintos según la hoja "3.2 Homologación columnas" del HDU del cliente.
NOMBRES = {
    28: 'Acumulados a contar del 01.01.2017 · Crédito por IPE',
    33: 'Acumulados hasta el 31.12.2016 · Crédito por IPE',
}
NOMBRE_ANTERIOR = 'Crédito por IPE'


def actualizar(apps, schema_editor):
    ConceptoTributario = apps.get_model('calificaciones', 'ConceptoTributario')
    for numero, nombre in NOMBRES.items():
        ConceptoTributario.objects.filter(numero=numero).update(nombre=nombre)


def revertir(apps, schema_editor):
    ConceptoTributario = apps.get_model('calificaciones', 'ConceptoTributario')
    ConceptoTributario.objects.filter(numero__in=NOMBRES).update(nombre=NOMBRE_ANTERIOR)


class Migration(migrations.Migration):
    dependencies = [
        ('calificaciones', '0003_permiso_carga_masiva'),
    ]

    operations = [
        migrations.RunPython(actualizar, revertir),
    ]
