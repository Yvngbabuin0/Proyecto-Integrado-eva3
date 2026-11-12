from django.urls import path

from . import views

app_name = 'calificaciones'

urlpatterns = [
    path('', views.mantenedor, name='mantenedor'),
    path('ingresar/', views.formulario, name='ingresar'),
    path('<int:pk>/modificar/', views.formulario, name='modificar'),
]
