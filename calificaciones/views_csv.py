"""Carga masiva por CSV en dos pasos: subir y validar, previsualizar y confirmar."""

import io
import uuid
from decimal import Decimal

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from cuentas.sesion import corredora_actual

from .forms import CargaCSVForm
from .importador_csv import ErrorCSV, guardar_registros, validar_csv
from .models import CONCEPTOS_SUMA, Mercado

CLAVE_SESION = 'csv_pendiente'
FILAS_PREVISUALIZADAS = 100


def _ruta(archivo_id):
    # El nombre lo genera el sistema (UUID); nunca se usa el nombre que envió el usuario.
    return settings.CSV_PENDIENTES_DIR / f'{uuid.UUID(archivo_id)}.csv'


def _pendiente(request):
    """Archivo pendiente de la sesión, o None. Solo se puede confirmar el archivo propio."""
    pendiente = request.session.get(CLAVE_SESION)
    if pendiente and _ruta(pendiente['id']).exists():
        return pendiente
    return None


def _descartar(request):
    pendiente = request.session.pop(CLAVE_SESION, None)
    if pendiente:
        _ruta(pendiente['id']).unlink(missing_ok=True)


@login_required
@permission_required('calificaciones.carga_masiva', raise_exception=True)
def cargar_csv(request):
    """Paso 1: subir el archivo. Se valida completo; si tiene errores no se guarda nada."""
    form = CargaCSVForm(request.POST or None, request.FILES or None)
    if request.method == 'POST' and form.is_valid():
        contenido = form.cleaned_data['archivo'].read()
        try:
            validar_csv(io.BytesIO(contenido), corredora_actual(request))
        except ErrorCSV as error:
            messages.error(request, str(error))
        else:
            _descartar(request)  # si había otro archivo pendiente, se reemplaza
            archivo_id = str(uuid.uuid4())
            settings.CSV_PENDIENTES_DIR.mkdir(parents=True, exist_ok=True)
            _ruta(archivo_id).write_bytes(contenido)
            request.session[CLAVE_SESION] = {'id': archivo_id, 'nombre': form.cleaned_data['archivo'].name}
            return redirect('calificaciones:previsualizar_csv')

    return render(request, 'calificaciones/cargar_csv.html', {'form': form})


@login_required
@permission_required('calificaciones.carga_masiva', raise_exception=True)
def previsualizar_csv(request):
    """Paso 2: mostrar lo que se va a cargar antes de confirmar."""
    pendiente = _pendiente(request)
    if pendiente is None:
        return redirect('calificaciones:cargar_csv')
    try:
        # Se valida otra vez: los datos de la base pudieron cambiar desde que se subió.
        registros, resumen = validar_csv(io.BytesIO(_ruta(pendiente['id']).read_bytes()), corredora_actual(request))
    except ErrorCSV as error:
        _descartar(request)
        messages.error(request, str(error))
        return redirect('calificaciones:cargar_csv')

    mercados = dict(Mercado.choices)
    filas = [
        {
            'linea': registro['linea'],
            'ejercicio': registro['ejercicio'],
            'mercado': mercados[registro['mercado']],
            'codigo': registro['codigo'],
            'fecha_pago': registro['fecha_pago'],
            'secuencia': registro['secuencia'],
            'descripcion': registro['descripcion'],
            'existente': registro['existente'],
            'suma': sum((f for n, _, f in registro['detalles'] if n in CONCEPTOS_SUMA), Decimal(0)),
        }
        for registro in registros[:FILAS_PREVISUALIZADAS]
    ]
    return render(request, 'calificaciones/previsualizar_csv.html', {
        'nombre': pendiente['nombre'],
        'resumen': resumen,
        'filas': filas,
        'ocultas': resumen['filas'] - len(filas),
    })


@login_required
@permission_required('calificaciones.carga_masiva', raise_exception=True)
@require_POST
def confirmar_csv(request):
    """Paso 3: guardar todo en una sola transacción."""
    pendiente = _pendiente(request)
    if pendiente is None:
        messages.error(request, 'No hay un archivo pendiente de confirmar. Vuelve a subirlo.')
        return redirect('calificaciones:cargar_csv')
    try:
        registros, _ = validar_csv(io.BytesIO(_ruta(pendiente['id']).read_bytes()), corredora_actual(request))
        resultado = guardar_registros(registros, corredora_actual(request), request.user)
    except ErrorCSV as error:
        messages.error(request, str(error))
        return redirect('calificaciones:cargar_csv')
    finally:
        _descartar(request)

    messages.success(
        request,
        f"Carga confirmada: {resultado['nuevas']} calificaciones nuevas y "
        f"{resultado['actualizadas']} actualizadas.",
    )
    return redirect('calificaciones:mantenedor')


@login_required
@permission_required('calificaciones.carga_masiva', raise_exception=True)
@require_POST
def cancelar_csv(request):
    _descartar(request)
    messages.info(request, 'Carga cancelada. No se guardó ninguna calificación.')
    return redirect('calificaciones:cargar_csv')
