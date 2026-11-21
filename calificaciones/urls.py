from django.urls import path

from . import views, views_csv

app_name = 'calificaciones'

urlpatterns = [
    path('', views.mantenedor, name='mantenedor'),
    path('cargar-csv/', views_csv.cargar_csv, name='cargar_csv'),
    path('cargar-csv/previsualizar/', views_csv.previsualizar_csv, name='previsualizar_csv'),
    path('cargar-csv/confirmar/', views_csv.confirmar_csv, name='confirmar_csv'),
    path('cargar-csv/cancelar/', views_csv.cancelar_csv, name='cancelar_csv'),
    path('ingresar/', views.formulario, name='ingresar'),
    path('<int:pk>/modificar/', views.formulario, name='modificar'),
    path('<int:pk>/eliminar/', views.baja, name='eliminar'),
]
