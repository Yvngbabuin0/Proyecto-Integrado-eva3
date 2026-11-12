from django.conf import settings
from django.core.exceptions import PermissionDenied

from .models import Corredora


def corredora_actual(request):
    """Corredora con la que opera la sesión. Nunca se toma de un formulario ni de la URL."""
    if request.user.is_authenticated:
        if request.user.corredora is None:
            # Administrador y Auditor no operan calificaciones.
            raise PermissionDenied
        return request.user.corredora

    # shortcut: mientras no exista el login, en desarrollo se opera como la primera corredora.
    # Se elimina cuando se agregue la autenticación.
    if settings.DEBUG:
        corredora = Corredora.objects.first()
        if corredora:
            return corredora
    raise PermissionDenied
