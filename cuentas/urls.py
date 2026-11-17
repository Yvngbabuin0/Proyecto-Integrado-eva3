from django.contrib.auth import views as auth_views
from django.urls import path

from . import views
from .forms import LoginForm

app_name = 'cuentas'

urlpatterns = [
    path(
        'login/',
        auth_views.LoginView.as_view(authentication_form=LoginForm, redirect_authenticated_user=True),
        name='login',
    ),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('inicio/', views.inicio, name='inicio'),
]
