from django.urls import path

from . import views

app_name = 'calificaciones'

urlpatterns = [
    path('', views.mantenedor, name='mantenedor'),
    path('cargar-csv/', views.cargar_csv, name='cargar_csv'),
    path('ingresar/', views.formulario, name='ingresar'),
    path('<int:pk>/modificar/', views.formulario, name='modificar'),
    path('<int:pk>/eliminar/', views.baja, name='eliminar'),
]
