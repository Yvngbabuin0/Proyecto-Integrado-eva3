from django.shortcuts import render

from cuentas.sesion import corredora_actual

from .forms import FiltroForm
from .models import CONCEPTOS, CalificacionBase, CalificacionLocal


def con_factores(calificaciones):
    """Agrega a cada calificación la lista de sus 30 factores, en orden de concepto."""
    for calificacion in calificaciones:
        por_concepto = {detalle.concepto_id: detalle.factor for detalle in calificacion.detalles.all()}
        calificacion.factores = [por_concepto.get(numero, 0) for numero in CONCEPTOS]
        calificacion.es_local = isinstance(calificacion, CalificacionLocal)
    return list(calificaciones)


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
