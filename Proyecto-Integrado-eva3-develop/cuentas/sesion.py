from django.core.exceptions import PermissionDenied


def corredora_actual(request):
    """Corredora con la que opera la sesión. Nunca se toma de un formulario ni de la URL."""
    if not request.user.is_authenticated or request.user.corredora is None:
        # Administrador y Auditor no pertenecen a una corredora y no operan calificaciones.
        raise PermissionDenied
    return request.user.corredora
