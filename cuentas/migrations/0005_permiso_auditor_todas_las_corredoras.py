from django.contrib.auth.management import create_permissions
from django.db import migrations


def asignar_permiso(apps, schema_editor):
    # Los permisos se crean normalmente al terminar migrate. Se fuerza su creación aquí
    # para que esta migración no dependa del orden de post_migrate.
    app_config = apps.get_app_config('auditoria')
    app_config.models_module = True
    create_permissions(app_config, apps=apps, verbosity=0)
    app_config.models_module = None

    Group = apps.get_model('auth', 'Group')
    Permission = apps.get_model('auth', 'Permission')
    permiso = Permission.objects.get(
        content_type__app_label='auditoria',
        codename='ver_todas_las_corredoras',
    )
    Group.objects.get(name='Auditor').permissions.add(permiso)


def quitar_permiso(apps, schema_editor):
    Group = apps.get_model('auth', 'Group')
    Permission = apps.get_model('auth', 'Permission')
    permiso = Permission.objects.filter(
        content_type__app_label='auditoria',
        codename='ver_todas_las_corredoras',
    ).first()
    grupo = Group.objects.filter(name='Auditor').first()
    if permiso and grupo:
        grupo.permissions.remove(permiso)


class Migration(migrations.Migration):
    dependencies = [
        ('auditoria', '0002_permiso_ver_todas_las_corredoras'),
        ('cuentas', '0004_permiso_auditoria_corredora'),
    ]

    operations = [
        migrations.RunPython(asignar_permiso, quitar_permiso),
    ]
