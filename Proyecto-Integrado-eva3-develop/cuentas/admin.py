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
    list_filter = ['corredora', 'groups', 'is_staff', 'is_active']
    fieldsets = UserAdmin.fieldsets + (('Corredora', {'fields': ['corredora']}),)
    add_fieldsets = UserAdmin.add_fieldsets + (('Corredora', {'fields': ['corredora']}),)

    def get_readonly_fields(self, request, obj=None):
        # El rol Administrador gestiona usuarios, pero no puede darse ni dar permisos sueltos o de superusuario:
        # los permisos se asignan solo a través de los grupos (roles).
        if request.user.is_superuser:
            return super().get_readonly_fields(request, obj)
        return ['is_superuser', 'user_permissions']
