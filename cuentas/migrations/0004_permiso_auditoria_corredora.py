from django.contrib.auth.management import create_permissions
from django.db import migrations


def asignar_permiso_auditoria_corredora(apps, schema_editor):
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
    for nombre in ('Corredor', 'Analista Tributario'):
        Group.objects.get(name=nombre).permissions.add(permiso)


def quitar_permiso_auditoria_corredora(apps, schema_editor):
    Group = apps.get_model('auth', 'Group')
    Permission = apps.get_model('auth', 'Permission')
    permiso = Permission.objects.filter(
        content_type__app_label='auditoria',
        codename='view_eventoauditoria',
    ).first()
    for nombre in ('Corredor', 'Analista Tributario'):
        grupo = Group.objects.filter(name=nombre).first()
        if permiso and grupo:
            grupo.permissions.remove(permiso)


class Migration(migrations.Migration):
    dependencies = [
        ('cuentas', '0003_permiso_auditoria'),
    ]

    operations = [
        migrations.RunPython(asignar_permiso_auditoria_corredora, quitar_permiso_auditoria_corredora),
    ]