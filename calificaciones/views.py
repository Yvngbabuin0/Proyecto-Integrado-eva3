from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render

from auditoria.models import EventoAuditoria, estado_calificacion
from cuentas.sesion import corredora_actual

from .forms import CalificacionForm, DetallesForm, FiltroForm
from .models import CONCEPTOS, CalificacionBase, CalificacionLocal


def con_factores(calificaciones):
    """Agrega a cada calificación la lista de sus 30 factores, en orden de concepto."""
    for calificacion in calificaciones:
        por_concepto = {detalle.concepto_id: detalle.factor for detalle in calificacion.detalles.all()}
        calificacion.factores = [por_concepto.get(numero, 0) for numero in CONCEPTOS]
        calificacion.es_local = isinstance(calificacion, CalificacionLocal)
    return list(calificaciones)


@login_required
@permission_required('calificaciones.view_calificacionlocal', raise_exception=True)
def mantenedor(request):
    corredora = corredora_actual(request)
    locales = CalificacionLocal.objects.filter(corredora=corredora, activa=True)
    # Una calificación de Bolsa no se muestra si la corredora ya tiene una local activa que la reemplaza.
    bases = CalificacionBase.objects.exclude(pk__in=locales.filter(base__isnull=False).values('base'))

    ejercicios = sorted(
        set(locales.values_list('ejercicio', flat=True)) | set(bases.values_list('ejercicio', flat=True)),
        reverse=True,
    )
    filtro = FiltroForm(request.GET or None, ejercicios=ejercicios)
    origen = ''
    if filtro.is_valid():
        datos = filtro.cleaned_data
        origen = datos['origen']
        if datos['ejercicio']:
            locales = locales.filter(ejercicio=datos['ejercicio'])
            bases = bases.filter(ejercicio=datos['ejercicio'])
        if datos['mercado']:
            locales = locales.filter(instrumento__mercado=datos['mercado'])
            bases = bases.filter(instrumento__mercado=datos['mercado'])
        if datos['instrumento']:
            locales = locales.filter(instrumento__codigo__icontains=datos['instrumento'])
            bases = bases.filter(instrumento__codigo__icontains=datos['instrumento'])

    filas = []
    if origen != 'bolsa':
        filas += con_factores(locales.select_related('instrumento').prefetch_related('detalles'))
    if origen != 'corredora':
        filas += con_factores(bases.select_related('instrumento').prefetch_related('detalles'))

    return render(request, 'calificaciones/mantenedor.html', {
        'corredora': corredora,
        'filtro': filtro,
        'filas': filas,
        'conceptos': CONCEPTOS,
    })


@login_required
def formulario(request, pk=None):
    """Ingresar (sin pk) o modificar (con pk) una calificación local de la corredora de la sesión."""
    permiso = 'calificaciones.add_calificacionlocal' if pk is None else 'calificaciones.change_calificacionlocal'
    if not request.user.has_perm(permiso):
        raise PermissionDenied
    corredora = corredora_actual(request)
    if pk is None:
        calificacion = CalificacionLocal(corredora=corredora, forma_ingreso=CalificacionLocal.FormaIngreso.MANUAL)
        accion = EventoAuditoria.Accion.CREAR
        estado_anterior = None
    else:
        # Filtrar por corredora hace que la de otra corredora responda 404, sin revelar que existe.
        calificacion = get_object_or_404(CalificacionLocal, pk=pk, corredora=corredora, activa=True)
        accion = EventoAuditoria.Accion.MODIFICAR
        estado_anterior = estado_calificacion(calificacion)

    datos = request.POST if request.method == 'POST' else None
    form = CalificacionForm(datos, instance=calificacion)
    detalles = DetallesForm(datos, calificacion=calificacion if pk else None)

    if datos is not None and form.is_valid() and detalles.is_valid():
        with transaction.atomic():
            calificacion = form.save()
            detalles.save(calificacion)
            EventoAuditoria.objects.create(
                accion=accion,
                usuario=request.user,
                usuario_nombre=request.user.get_username(),
                corredora=corredora,
                calificacion_id=calificacion.pk,
                estado_anterior=estado_anterior,
                estado_posterior=estado_calificacion(calificacion),
            )
        messages.success(request, 'Calificación actualizada correctamente.' if pk else 'Calificación ingresada correctamente.')
        return redirect('calificaciones:mantenedor')

    return render(request, 'calificaciones/formulario.html', {
        'corredora': corredora,
        'calificacion': calificacion if pk else None,
        'form': form,
        'detalles': detalles,
    })


@login_required
@permission_required('calificaciones.change_calificacionlocal', raise_exception=True)
def baja(request, pk):
    """Baja lógica: la calificación sale del listado, pero se conserva con su histórico."""
    corredora = corredora_actual(request)
    calificacion = get_object_or_404(CalificacionLocal, pk=pk, corredora=corredora, activa=True)

    if request.method == 'POST':
        with transaction.atomic():
            calificacion = get_object_or_404(
                CalificacionLocal.objects.select_for_update(),
                pk=pk,
                corredora=corredora,
                activa=True,
            )
            estado_anterior = estado_calificacion(calificacion)
            calificacion.activa = False
            calificacion.save(update_fields=['activa', 'modificada'])
            EventoAuditoria.objects.create(
                accion=EventoAuditoria.Accion.BAJA,
                usuario=request.user,
                usuario_nombre=request.user.get_username(),
                corredora=corredora,
                calificacion_id=calificacion.pk,
                estado_anterior=estado_anterior,
                estado_posterior=estado_calificacion(calificacion),
            )
        messages.success(request, 'Registro retirado del listado activo. El histórico se conservó.')
        return redirect('calificaciones:mantenedor')

    return render(request, 'calificaciones/confirmar_baja.html', {
        'corredora': corredora,
        'calificacion': calificacion,
    })
