from django.contrib.auth.models import AbstractUser
from django.db import models


class Corredora(models.Model):
    rut = models.CharField(max_length=12, unique=True)
    nombre = models.CharField(max_length=150)

    class Meta:
        ordering = ['nombre']

    def __str__(self):
        return self.nombre


class Usuario(AbstractUser):
    # Vacía para Administrador y Auditor, que no pertenecen a una corredora.
    corredora = models.ForeignKey(
        Corredora,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='usuarios',
    )
