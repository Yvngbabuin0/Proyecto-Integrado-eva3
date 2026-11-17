from django.contrib.auth.management import create_permissions
from django.db import migrations


def asignar_permiso_auditoria(apps, schema_editor):
    # Los permisos automáticos se crean normalmente al terminar migrate. Se fuerza
    # su creación aquí para que esta migración no dependa del orden de post_migrate.
    app_config = apps.get_app_config('auditoria')
    app_config.models_module = True
    create_permissions(app_config, apps=apps, verbosity=0)
    app_config.models_module = None

    Group = apps.get_model('auth', 'Group')
    Permission = apps.get_model('auth', 'Permission')
    permiso = Permission.objects.get(
        content_type__app_label='auditoria',
        codename='view_eventoauditoria',
    )
    Group.objects.get(name='Auditor').permissions.add(permiso)


def quitar_permiso_auditoria(apps, schema_editor):
    Group = apps.get_model('auth', 'Group')
    Permission = apps.get_model('auth', 'Permission')
    permiso = Permission.objects.filter(
        content_type__app_label='auditoria',
        codename='view_eventoauditoria',
    ).first()
    grupo = Group.objects.filter(name='Auditor').first()
    if permiso and grupo:
        grupo.permissions.remove(permiso)


class Migration(migrations.Migration):
    dependencies = [
        ('auditoria', '0001_initial'),
        ('cuentas', '0002_roles'),
    ]

    operations = [
        migrations.RunPython(asignar_permiso_auditoria, quitar_permiso_auditoria),
    ]

