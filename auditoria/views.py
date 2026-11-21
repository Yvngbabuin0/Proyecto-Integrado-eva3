from django.contrib.auth.decorators import login_required, permission_required
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_GET

from calificaciones.models import CalificacionLocal
from cuentas.sesion import corredora_actual

from .cambios import cambios, formatear
from .forms import FiltroEventosForm
from .models import EventoAuditoria

EVENTOS_POR_PAGINA = 50


def eventos_visibles(request):
    """Eventos que puede ver el usuario: todos si tiene el permiso global (Auditor); si no, solo
    los de su corredora. Sin corredora asignada, ``corredora_actual`` responde 403: nunca se
    muestra todo por omisión."""
    eventos = EventoAuditoria.objects.select_related('corredora', 'lote')
    if request.user.has_perm('auditoria.ver_todas_las_corredoras'):
        return eventos
    return eventos.filter(corredora=corredora_actual(request))


def con_entidad(eventos):
    """Agrega a cada evento la calificación afectada ("JEAP · evento 100000809") y su origen."""
    ids = {evento.calificacion_id for evento in eventos if evento.calificacion_id is not None}
    calificaciones = {
        c.pk: f'{c.instrumento.codigo} · evento {c.secuencia_evento}'
        for c in CalificacionLocal.objects.filter(pk__in=ids).select_related('instrumento')
    }
    for evento in eventos:
        if evento.calificacion_id is None:
            # Evento de un lote completo (carga o rechazo de un CSV).
            evento.entidad = f'Lote {evento.lote_id} · {evento.lote.nombre_original}' if evento.lote_id else '—'
            evento.origen = 'Archivo'
            continue
        evento.entidad = calificaciones.get(evento.calificacion_id, f'Calificación {evento.calificacion_id}')
        estado = evento.estado_posterior or evento.estado_anterior or {}
        evento.origen = formatear('forma_ingreso', estado.get('forma_ingreso'))
    return eventos


@login_required
@permission_required('auditoria.view_eventoauditoria', raise_exception=True)
@require_GET
def listado(request):
    eventos = eventos_visibles(request)
    filtro = FiltroEventosForm(
        request.GET or None,
        ocultar_corredora=not request.user.has_perm('auditoria.ver_todas_las_corredoras'),
    )
    if filtro.is_valid():
        datos = filtro.cleaned_data
        if datos['fecha']:
            eventos = eventos.filter(fecha__date=datos['fecha'])
        if datos['accion']:
            eventos = eventos.filter(accion=datos['accion'])
        if datos['resultado'] == EventoAuditoria.Resultado.RECHAZADO:
            eventos = eventos.filter(accion__in=EventoAuditoria.ACCIONES_RECHAZADAS)
        elif datos['resultado'] == EventoAuditoria.Resultado.EXITOSO:
            eventos = eventos.exclude(accion__in=EventoAuditoria.ACCIONES_RECHAZADAS)
        if datos['corredora']:
            eventos = eventos.filter(corredora=datos['corredora'])

    pagina = Paginator(eventos, EVENTOS_POR_PAGINA).get_page(request.GET.get('pagina'))
    # Conserva los filtros al cambiar de página.
    parametros = request.GET.copy()
    parametros.pop('pagina', None)

    return render(request, 'auditoria/listado.html', {
        'filtro': filtro,
        'pagina': pagina,
        'eventos': con_entidad(list(pagina)),
        'parametros': parametros.urlencode(),
    })


@login_required
@permission_required('auditoria.view_eventoauditoria', raise_exception=True)
@require_GET
def detalle(request, pk):
    evento = get_object_or_404(eventos_visibles(request), pk=pk)
    con_entidad([evento])
    return render(request, 'auditoria/detalle.html', {
        'evento': evento,
        'cambios': cambios(evento.estado_anterior, evento.estado_posterior),
    })
