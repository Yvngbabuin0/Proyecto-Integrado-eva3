from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import Corredora, Usuario


@admin.register(Corredora)
class CorredoraAdmin(admin.ModelAdmin):
    list_display = ['nombre', 'rut']
    search_fields = ['nombre', 'rut']


@admin.register(Usuario)
class UsuarioAdmin(UserAdmin):
    list_display = ['username', 'email', 'corredora', 'is_staff']
    list_filter = ['corredora', 'is_staff', 'is_active']
    fieldsets = UserAdmin.fieldsets + (('Corredora', {'fields': ['corredora']}),)
    add_fieldsets = UserAdmin.add_fieldsets + (('Corredora', {'fields': ['corredora']}),)
