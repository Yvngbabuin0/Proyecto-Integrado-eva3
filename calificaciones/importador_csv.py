import csv
import io
from datetime import date
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.core.validators import DecimalValidator
from django.db import transaction
from django.utils import timezone

from auditoria.models import EventoAuditoria, estado_calificacion

from .models import CONCEPTOS, CONCEPTOS_SUMA, CalificacionBase, CalificacionLocal, DetalleLocal, Instrumento, Mercado

MAX_FILAS_CSV = 5000

COLUMNAS_BASE = (
    'mercado',
    'ejercicio',
    'codigo_instrumento',
    'secuencia_evento',
    'fecha_pago',
    'numero_dividendo',
    'descripcion',
    'valor_historico',
    'factor_actualizacion',
    'isfut',
)
COLUMNAS_CSV = COLUMNAS_BASE + tuple(
    columna
    for numero in CONCEPTOS
    for columna in (f'monto_{numero}', f'factor_{numero}')
)


class ErrorCSV(ValueError):
    """Error bloqueante del archivo. ``fila`` y ``col`` indican dónde está, si se sabe."""

    def __init__(self, mensaje, fila=None, col=None):
        super().__init__(mensaje)
        self.fila = fila
        self.col = col

    def detalle(self):
        """Forma que se guarda en ``LoteCarga.errores``: {"fila": 12, "col": "factor_8", "error": "..."}."""
        return {'fila': self.fila, 'col': self.col, 'error': str(self)}


def _decimal(valor, columna, linea, max_digitos, decimales):
    if ',' in valor and '.' in valor:
        raise ErrorCSV(f'Fila {linea}: {columna} debe usar un solo separador decimal.', fila=linea, col=columna)
    try:
        numero = Decimal(valor.replace(',', '.'))
        if not numero.is_finite():
            raise InvalidOperation
        DecimalValidator(max_digitos, decimales)(numero)
    except (InvalidOperation, ValidationError):
        raise ErrorCSV(
            f'Fila {linea}: {columna} debe ser un número con hasta '
            f'{decimales} decimales.',
            fila=linea,
            col=columna,
        ) from None
    return numero


def _entero(valor, columna, linea, minimo, maximo):
    try:
        numero = int(valor)
    except ValueError:
        raise ErrorCSV(f'Fila {linea}: {columna} debe ser un número entero.', fila=linea, col=columna) from None
    if not minimo <= numero <= maximo:
        raise ErrorCSV(f'Fila {linea}: {columna} está fuera del rango permitido.', fila=linea, col=columna)
    return numero


def _leer_csv(archivo):
    contenido = archivo.read()
    try:
        texto = contenido.decode('utf-8-sig')
    except UnicodeDecodeError:
        raise ErrorCSV('El archivo debe estar codificado en UTF-8.') from None

    try:
        muestra = texto[:4096]
        try:
            delimitador = csv.Sniffer().sniff(muestra, delimiters=',;').delimiter
        except csv.Error:
            delimitador = ','

        lector = csv.reader(io.StringIO(texto, newline=''), delimiter=delimitador, strict=True)
        encabezados = next(lector, None)
        if not encabezados:
            raise ErrorCSV('El CSV está vacío o no contiene encabezados.')

        encabezados = [encabezado.strip().lower() for encabezado in encabezados]
        if len(encabezados) != len(set(encabezados)):
            raise ErrorCSV('El CSV contiene encabezados duplicados.')
        faltantes = [columna for columna in COLUMNAS_CSV if columna not in encabezados]
        sobrantes = [columna for columna in encabezados if columna not in COLUMNAS_CSV]
        if faltantes or sobrantes:
            detalles = []
            if faltantes:
                detalles.append('faltan columnas: ' + ', '.join(faltantes))
            if sobrantes:
                detalles.append('columnas no reconocidas: ' + ', '.join(sobrantes))
            raise ErrorCSV('Encabezados inválidos (' + '; '.join(detalles) + ').')

        posiciones = {columna: encabezados.index(columna) for columna in COLUMNAS_CSV}
        registros = []
        claves_vistas = {}
        for fila in lector:
            linea = lector.line_num
            if len(registros) >= MAX_FILAS_CSV:
                raise ErrorCSV(f'El archivo supera el máximo de {MAX_FILAS_CSV} filas.', fila=linea)
            if not fila:
                raise ErrorCSV(f'Fila {linea}: la fila está vacía.', fila=linea, col=None)
            if len(fila) != len(encabezados):
                raise ErrorCSV(f'Fila {linea}: la cantidad de columnas no coincide con los encabezados.', fila=linea, col=None)

            vacias = [
                encabezados[indice]
                for indice, valor in enumerate(fila)
                if valor is None or not valor.strip() or valor.strip().lower() in {'null', 'none'}
            ]
            if vacias:
                raise ErrorCSV(f'Fila {linea}: hay campos vacíos o nulos: {", ".join(vacias)}.', fila=linea, col=', '.join(vacias))

            valor = lambda columna: fila[posiciones[columna]].strip()
            mercado = valor('mercado').upper()
            if mercado not in Mercado.values:
                raise ErrorCSV(f'Fila {linea}: mercado debe ser ACC, CFI o FM.', fila=linea, col='mercado')

            codigo = valor('codigo_instrumento').upper()
            if len(codigo) > 30:
                raise ErrorCSV(f'Fila {linea}: codigo_instrumento no puede superar 30 caracteres.', fila=linea, col='codigo_instrumento')

            ejercicio = _entero(valor('ejercicio'), 'ejercicio', linea, 0, 32767)
            secuencia = _entero(
                valor('secuencia_evento'), 'secuencia_evento', linea, 0, 9223372036854775807
            )
            numero_dividendo = _entero(
                valor('numero_dividendo'), 'numero_dividendo', linea, 0, 2147483647
            )

            try:
                fecha_pago = date.fromisoformat(valor('fecha_pago'))
            except ValueError:
                raise ErrorCSV(f'Fila {linea}: fecha_pago debe tener formato AAAA-MM-DD.', fila=linea, col='fecha_pago') from None

            descripcion = valor('descripcion')
            if len(descripcion) > 200:
                raise ErrorCSV(f'Fila {linea}: descripcion no puede superar 200 caracteres.', fila=linea, col='descripcion')

            isfut_texto = valor('isfut').lower()
            valores_si = {'1', 'true', 'si', 'sí', 'yes'}
            valores_no = {'0', 'false', 'no'}
            if isfut_texto not in valores_si | valores_no:
                raise ErrorCSV(f'Fila {linea}: isfut debe ser Sí/No o 1/0.', fila=linea, col='isfut')

            valor_historico = _decimal(
                valor('valor_historico'), 'valor_historico', linea, 18, 8
            )
            factor_actualizacion = _decimal(
                valor('factor_actualizacion'), 'factor_actualizacion', linea, 12, 8
            )
            detalles = []
            for numero in CONCEPTOS:
                monto = _decimal(valor(f'monto_{numero}'), f'monto_{numero}', linea, 15, 2)
                factor = _decimal(valor(f'factor_{numero}'), f'factor_{numero}', linea, 9, 8)
                if monto < 0:
                    raise ErrorCSV(f'Fila {linea}: monto_{numero} no puede ser negativo.', fila=linea, col=f'monto_{numero}')
                if not 0 <= factor <= 1:
                    raise ErrorCSV(f'Fila {linea}: factor_{numero} debe estar entre 0 y 1.', fila=linea, col=f'factor_{numero}')
                detalles.append((numero, monto, factor))
            suma = sum((factor for numero, _, factor in detalles if numero in CONCEPTOS_SUMA), Decimal(0))
            if suma > 1:
                raise ErrorCSV(
                    f'Fila {linea}: la suma de los factores 8 a 19 es {suma:.8f}'.replace('.', ',')
                    + ' y no puede superar 1.',
                    fila=linea,
                    col='factor_8 a factor_19',
                )

            clave = (codigo, mercado, ejercicio, secuencia)
            if clave in claves_vistas:
                raise ErrorCSV(
                    f'Fila {linea}: registro duplicado dentro del CSV '
                    f'(también aparece en la fila {claves_vistas[clave]}).',
                    fila=linea,
                )
            claves_vistas[clave] = linea
            registros.append({
                'linea': linea,
                'codigo': codigo,
                'mercado': mercado,
                'ejercicio': ejercicio,
                'secuencia': secuencia,
                'fecha_pago': fecha_pago,
                'numero_dividendo': numero_dividendo,
                'descripcion': descripcion,
                'valor_historico': valor_historico,
                'factor_actualizacion': factor_actualizacion,
                'isfut': isfut_texto in valores_si,
                'detalles': detalles,
            })
    except csv.Error:
        raise ErrorCSV('El archivo CSV tiene una estructura inválida.') from None

    if not registros:
        raise ErrorCSV('El CSV no contiene filas para cargar.')
    return registros


def _instrumentos_existentes(registros):
    codigos = {registro['codigo'] for registro in registros}
    mercados = {registro['mercado'] for registro in registros}
    existentes = Instrumento.objects.filter(codigo__in=codigos, mercado__in=mercados)
    return {(instrumento.codigo, instrumento.mercado): instrumento for instrumento in existentes}


def _clave(registro):
    return (registro['codigo'], registro['mercado'], registro['ejercicio'], registro['secuencia'])


def _calificaciones_existentes(registros, corredora, instrumentos, bloquear=False):
    """Calificaciones locales activas de la corredora que ya tienen la llave funcional de alguna fila.

    La llave es corredora + ejercicio + mercado + instrumento + secuencia del evento. Las dadas de
    baja no cuentan: se conservan como histórico y la fila del archivo crea una nueva.
    """
    ids_instrumentos = [instrumento.pk for instrumento in instrumentos.values()]
    if not ids_instrumentos:
        return {}
    consulta = CalificacionLocal.objects.filter(
        corredora=corredora,
        activa=True,
        instrumento_id__in=ids_instrumentos,
        ejercicio__in={registro['ejercicio'] for registro in registros},
        secuencia_evento__in={registro['secuencia'] for registro in registros},
    ).select_related('instrumento')
    if bloquear:
        consulta = consulta.select_for_update()
    claves = {_clave(registro) for registro in registros}
    existentes = {}
    for calificacion in consulta:
        clave = (
            calificacion.instrumento.codigo,
            calificacion.instrumento.mercado,
            calificacion.ejercicio,
            calificacion.secuencia_evento,
        )
        if clave in claves:
            existentes[clave] = calificacion
    return existentes


def validar_csv(archivo, corredora):
    """Lee y valida el archivo completo sin guardar nada. Devuelve los registros y un resumen.

    Cada registro queda marcado con ``existente``: True si va a actualizar una calificación
    activa de la corredora, False si va a crear una nueva.
    """
    registros = _leer_csv(archivo)
    instrumentos = _instrumentos_existentes(registros)
    existentes = _calificaciones_existentes(registros, corredora, instrumentos)
    for registro in registros:
        registro['existente'] = _clave(registro) in existentes
    pares = {(registro['codigo'], registro['mercado']) for registro in registros}
    actualizadas = sum(registro['existente'] for registro in registros)
    resumen = {
        'filas': len(registros),
        'nuevas': len(registros) - actualizadas,
        'actualizadas': actualizadas,
        'instrumentos_nuevos': len(pares - instrumentos.keys()),
    }
    return registros, resumen


def cargar_calificaciones_csv(archivo, corredora):
    return guardar_registros(_leer_csv(archivo), corredora)


CAMPOS_ACTUALIZABLES = (
    'fecha_pago', 'numero_dividendo', 'descripcion', 'valor_historico',
    'factor_actualizacion', 'isfut', 'forma_ingreso', 'modificada',
)


def guardar_registros(registros, corredora, usuario=None):
    """Guarda los registros ya leídos en una sola transacción: todo o nada.

    Las filas cuya llave funcional ya existe como calificación activa de la corredora la
    actualizan (datos y los 30 detalles); las demás crean una calificación nueva.
    Si se indica ``usuario``, cada fila deja un evento de auditoría (creación o modificación)
    dentro de la misma transacción. Devuelve ``{'nuevas': n, 'actualizadas': m}``.
    """
    codigos = {registro['codigo'] for registro in registros}
    mercados = {registro['mercado'] for registro in registros}
    pares_instrumento = {(registro['codigo'], registro['mercado']) for registro in registros}

    with transaction.atomic():
        instrumentos = _instrumentos_existentes(registros)
        # Se vuelve a buscar dentro de la transacción: entre la previsualización y la
        # confirmación alguien pudo haber ingresado o dado de baja una calificación.
        existentes = _calificaciones_existentes(registros, corredora, instrumentos, bloquear=True)

        faltantes = pares_instrumento - instrumentos.keys()
        if faltantes:
            Instrumento.objects.bulk_create(
                [
                    Instrumento(codigo=codigo, mercado=mercado, inscrito=False)
                    for codigo, mercado in faltantes
                ],
                batch_size=1000,
            )
            instrumentos.update({
                (instrumento.codigo, instrumento.mercado): instrumento
                for instrumento in Instrumento.objects.filter(codigo__in=codigos, mercado__in=mercados)
            })

        codigos_ids = {instrumento.pk for instrumento in instrumentos.values()}
        bases = {
            (instrumento_id, ejercicio, secuencia): pk
            for pk, instrumento_id, ejercicio, secuencia in CalificacionBase.objects.filter(
                instrumento_id__in=codigos_ids,
                ejercicio__in={registro['ejercicio'] for registro in registros},
                secuencia_evento__in={registro['secuencia'] for registro in registros},
            ).values_list('pk', 'instrumento_id', 'ejercicio', 'secuencia_evento')
        }

        anteriores = {}
        if usuario is not None and existentes:
            detalles_anteriores = {}
            for detalle in DetalleLocal.objects.filter(calificacion__in=list(existentes.values())):
                detalles_anteriores.setdefault(detalle.calificacion_id, []).append(detalle)
            anteriores = {
                calificacion.pk: estado_calificacion(calificacion, detalles_anteriores.get(calificacion.pk, []))
                for calificacion in existentes.values()
            }

        ahora = timezone.now()
        nuevas, actualizadas = [], []
        for registro in registros:
            calificacion = existentes.get(_clave(registro))
            if calificacion is None:
                instrumento = instrumentos[(registro['codigo'], registro['mercado'])]
                calificacion = CalificacionLocal(
                    corredora=corredora,
                    instrumento=instrumento,
                    base_id=bases.get((instrumento.pk, registro['ejercicio'], registro['secuencia'])),
                    ejercicio=registro['ejercicio'],
                    secuencia_evento=registro['secuencia'],
                )
                nuevas.append((calificacion, registro))
            else:
                calificacion.modificada = ahora
                actualizadas.append((calificacion, registro))
            calificacion.fecha_pago = registro['fecha_pago']
            calificacion.numero_dividendo = registro['numero_dividendo']
            calificacion.descripcion = registro['descripcion']
            calificacion.valor_historico = registro['valor_historico']
            calificacion.factor_actualizacion = registro['factor_actualizacion']
            calificacion.isfut = registro['isfut']
            calificacion.forma_ingreso = CalificacionLocal.FormaIngreso.ARCHIVO

        CalificacionLocal.objects.bulk_create([c for c, _ in nuevas], batch_size=1000)
        if actualizadas:
            CalificacionLocal.objects.bulk_update(
                [c for c, _ in actualizadas], CAMPOS_ACTUALIZABLES, batch_size=1000,
            )
            # Los detalles de las actualizadas se reemplazan completos por los del archivo.
            DetalleLocal.objects.filter(calificacion__in=[c for c, _ in actualizadas]).delete()

        detalles_pendientes = []
        eventos = []
        for calificacion, registro in nuevas + actualizadas:
            if calificacion.pk is None:
                raise RuntimeError('La base de datos no devolvió el identificador de una calificación.')
            detalles = [
                DetalleLocal(calificacion=calificacion, concepto_id=numero, monto=monto, factor=factor)
                for numero, monto, factor in registro['detalles']
            ]
            detalles_pendientes.extend(detalles)
            if usuario is not None:
                eventos.append(EventoAuditoria(
                    accion=(
                        EventoAuditoria.Accion.MODIFICAR if calificacion.pk in anteriores
                        else EventoAuditoria.Accion.CREAR
                    ),
                    usuario=usuario,
                    usuario_nombre=usuario.get_username(),
                    corredora=corredora,
                    calificacion_id=calificacion.pk,
                    estado_anterior=anteriores.get(calificacion.pk),
                    estado_posterior=estado_calificacion(calificacion, detalles),
                ))
            if len(detalles_pendientes) >= 2000:
                DetalleLocal.objects.bulk_create(detalles_pendientes, batch_size=2000)
                detalles_pendientes.clear()
        if detalles_pendientes:
            DetalleLocal.objects.bulk_create(detalles_pendientes, batch_size=2000)
        EventoAuditoria.objects.bulk_create(eventos, batch_size=1000)

    return {'nuevas': len(nuevas), 'actualizadas': len(actualizadas)}
