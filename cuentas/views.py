from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect


@login_required
def inicio(request):
    """Después del login, lleva a cada usuario a la sección de su rol."""
    usuario = request.user
    if usuario.has_perm('calificaciones.view_calificacionlocal'):
        return redirect('calificaciones:mantenedor')
    if usuario.has_perm('auditoria.view_eventoauditoria'):
        return redirect('auditoria:listado')
    if usuario.is_staff:
        return redirect('admin:index')
    raise PermissionDenied
