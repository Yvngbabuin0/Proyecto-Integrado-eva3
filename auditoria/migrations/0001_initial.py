# Generated manually for the ES3 audit module.

import django.core.serializers.json
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='EventoAuditoria',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('accion', models.CharField(choices=[('CREAR', 'Creación'), ('MODIFICAR', 'Modificación'), ('BAJA', 'Baja lógica')], max_length=10)),
                ('fecha', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('usuario_nombre', models.CharField(max_length=150)),
                ('calificacion_id', models.PositiveBigIntegerField(db_index=True)),
                ('estado_anterior', models.JSONField(blank=True, encoder=django.core.serializers.json.DjangoJSONEncoder, null=True)),
                ('estado_posterior', models.JSONField(blank=True, encoder=django.core.serializers.json.DjangoJSONEncoder, null=True)),
                ('corredora', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='eventos_auditoria', to='cuentas.corredora')),
                ('usuario', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='eventos_auditoria', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'evento de auditoría',
                'verbose_name_plural': 'eventos de auditoría',
                'ordering': ['-fecha', '-pk'],
                'default_permissions': ('view',),
            },
        ),
    ]

