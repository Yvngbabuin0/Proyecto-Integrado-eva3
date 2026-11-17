from django.contrib.auth.decorators import login_required, permission_required
from django.shortcuts import render
from django.views.decorators.http import require_GET

from .models import EventoAuditoria


@login_required
@permission_required('auditoria.view_eventoauditoria', raise_exception=True)
@require_GET
def listado(request):
    eventos = EventoAuditoria.objects.select_related('usuario', 'corredora')
    return render(request, 'auditoria/listado.html', {'eventos': eventos})

