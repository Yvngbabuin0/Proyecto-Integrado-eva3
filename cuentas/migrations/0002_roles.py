from django.contrib.auth.management import create_permissions
from django.db import migrations

# Roles del informe ES2 (sección 4.5.1) como grupos de Django, con el mínimo privilegio de cada uno.
CRUD_CALIFICACIONES = [
    'calificaciones.view_calificacionlocal',
    'calificaciones.add_calificacionlocal',
    'calificaciones.change_calificacionlocal',  # incluye la baja lógica
    'calificaciones.view_calificacionbase',
]

ROLES = {
    'Corredor': CRUD_CALIFICACIONES,
    'Analista Tributario': CRUD_CALIFICACIONES + ['calificaciones.carga_masiva'],
    # Gestiona usuarios y corredoras; no opera calificaciones.
    'Administrador': [
        'cuentas.view_usuario', 'cuentas.add_usuario', 'cuentas.change_usuario',
        'cuentas.view_corredora', 'cuentas.add_corredora', 'cuentas.change_corredora',
        'auth.view_group',
    ],
    # Sus permisos de consulta del registro de operaciones llegan con el módulo de auditoría.
    'Auditor': [],
}


def crear_roles(apps, schema_editor):
    # Los permisos normalmente se crean al terminar migrate; aquí se necesitan antes.
    for app_config in apps.get_app_configs():
        app_config.models_module = True
        create_permissions(app_config, apps=apps, verbosity=0)
        app_config.models_module = None

    Group = apps.get_model('auth', 'Group')
    Permission = apps.get_model('auth', 'Permission')
    for nombre, permisos in ROLES.items():
        grupo, _ = Group.objects.get_or_create(name=nombre)
        for permiso in permisos:
            app_label, codename = permiso.split('.')
            grupo.permissions.add(Permission.objects.get(content_type__app_label=app_label, codename=codename))


def borrar_roles(apps, schema_editor):
    apps.get_model('auth', 'Group').objects.filter(name__in=ROLES).delete()


class Migration(migrations.Migration):
    dependencies = [
        ('cuentas', '0001_initial'),
        ('calificaciones', '0003_permiso_carga_masiva'),
        ('auth', '0012_alter_user_first_name_max_length'),
    ]

    operations = [
        migrations.RunPython(crear_roles, borrar_roles),
    ]
