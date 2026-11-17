from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path('admin/', admin.site.urls),
    path('cuentas/', include('cuentas.urls')),
    path('auditoria/', include('auditoria.urls')),
    path('', include('calificaciones.urls')),
]
