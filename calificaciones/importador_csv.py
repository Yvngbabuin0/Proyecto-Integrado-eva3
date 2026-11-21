import csv
import io
from datetime import date
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.core.validators import DecimalValidator
from django.db import transaction

from .models import CONCEPTOS, CalificacionBase, CalificacionLocal, DetalleLocal, Instrumento, Mercado

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
    pass


def _decimal(valor, columna, linea, max_digitos, decimales):
    if ',' in valor and '.' in valor:
        raise ErrorCSV(f'Fila {linea}: {columna} debe usar un solo separador decimal.')
    try:
        numero = Decimal(valor.replace(',', '.'))
        if not numero.is_finite():
            raise InvalidOperation
        DecimalValidator(max_digitos, decimales)(numero)
    except (InvalidOperation, ValidationError):
        raise ErrorCSV(
            f'Fila {linea}: {columna} debe ser un número con hasta '
            f'{decimales} decimales.'
        ) from None
    return numero


def _entero(valor, columna, linea, minimo, maximo):
    try:
        numero = int(valor)
    except ValueError:
        raise ErrorCSV(f'Fila {linea}: {columna} debe ser un número entero.') from None
    if not minimo <= numero <= maximo:
        raise ErrorCSV(f'Fila {linea}: {columna} está fuera del rango permitido.')
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
                raise ErrorCSV(f'El archivo supera el máximo de {MAX_FILAS_CSV} filas.')
            if not fila:
                raise ErrorCSV(f'Fila {linea}: la fila está vacía.')
            if len(fila) != len(encabezados):
                raise ErrorCSV(f'Fila {linea}: la cantidad de columnas no coincide con los encabezados.')

            vacias = [
                encabezados[indice]
                for indice, valor in enumerate(fila)
                if valor is None or not valor.strip() or valor.strip().lower() in {'null', 'none'}
            ]
            if vacias:
                raise ErrorCSV(f'Fila {linea}: hay campos vacíos o nulos: {", ".join(vacias)}.')

            valor = lambda columna: fila[posiciones[columna]].strip()
            mercado = valor('mercado').upper()
            if mercado not in Mercado.values:
                raise ErrorCSV(f'Fila {linea}: mercado debe ser ACC, CFI o FM.')

            codigo = valor('codigo_instrumento').upper()
            if len(codigo) > 30:
                raise ErrorCSV(f'Fila {linea}: codigo_instrumento no puede superar 30 caracteres.')

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
                raise ErrorCSV(f'Fila {linea}: fecha_pago debe tener formato AAAA-MM-DD.') from None

            descripcion = valor('descripcion')
            if len(descripcion) > 200:
                raise ErrorCSV(f'Fila {linea}: descripcion no puede superar 200 caracteres.')

            isfut_texto = valor('isfut').lower()
            valores_si = {'1', 'true', 'si', 'sí', 'yes'}
            valores_no = {'0', 'false', 'no'}
            if isfut_texto not in valores_si | valores_no:
                raise ErrorCSV(f'Fila {linea}: isfut debe ser Sí/No o 1/0.')

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
                    raise ErrorCSV(f'Fila {linea}: monto_{numero} no puede ser negativo.')
                if not 0 <= factor <= 1:
                    raise ErrorCSV(f'Fila {linea}: factor_{numero} debe estar entre 0 y 1.')
                detalles.append((numero, monto, factor))

            clave = (codigo, mercado, ejercicio, secuencia)
            if clave in claves_vistas:
                raise ErrorCSV(
                    f'Fila {linea}: registro duplicado dentro del CSV '
                    f'(también aparece en la fila {claves_vistas[clave]}).'
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


def _verificar_duplicados(registros, corredora, instrumentos):
    """Rechaza el archivo si alguna fila ya existe como calificación local de la corredora."""
    ids_existentes = [instrumento.pk for instrumento in instrumentos.values()]
    if not ids_existentes:
        return
    claves_existentes = set(
        CalificacionLocal.objects.filter(
            corredora=corredora,
            instrumento_id__in=ids_existentes,
        ).values_list('instrumento__codigo', 'instrumento__mercado', 'ejercicio', 'secuencia_evento')
    )
    duplicados = [
        registro['linea']
        for registro in registros
        if (registro['codigo'], registro['mercado'], registro['ejercicio'], registro['secuencia']) in claves_existentes
    ]
    if duplicados:
        filas = ', '.join(str(linea) for linea in duplicados[:10])
        sufijo = ' (y más)' if len(duplicados) > 10 else ''
        raise ErrorCSV(f'Hay registros existentes duplicados en las filas {filas}{sufijo}.')


def validar_csv(archivo, corredora):
    """Lee y valida el archivo completo sin guardar nada. Devuelve los registros y un resumen."""
    registros = _leer_csv(archivo)
    instrumentos = _instrumentos_existentes(registros)
    _verificar_duplicados(registros, corredora, instrumentos)
    pares = {(registro['codigo'], registro['mercado']) for registro in registros}
    resumen = {
        'filas': len(registros),
        'instrumentos_nuevos': len(pares - instrumentos.keys()),
    }
    return registros, resumen


def cargar_calificaciones_csv(archivo, corredora):
    return guardar_registros(_leer_csv(archivo), corredora)


def guardar_registros(registros, corredora):
    """Guarda los registros ya leídos en una sola transacción: todo o nada."""
    codigos = {registro['codigo'] for registro in registros}
    mercados = {registro['mercado'] for registro in registros}
    pares_instrumento = {(registro['codigo'], registro['mercado']) for registro in registros}

    with transaction.atomic():
        instrumentos = _instrumentos_existentes(registros)
        # Se vuelve a revisar dentro de la transacción: entre la previsualización y la
        # confirmación alguien pudo haber ingresado la misma calificación.
        _verificar_duplicados(registros, corredora, instrumentos)

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

        calificaciones = [
            CalificacionLocal(
                corredora=corredora,
                instrumento=instrumentos[(registro['codigo'], registro['mercado'])],
                base=bases.get((
                    instrumentos[(registro['codigo'], registro['mercado'])].pk,
                    registro['ejercicio'],
                    registro['secuencia'],
                )),
                ejercicio=registro['ejercicio'],
                fecha_pago=registro['fecha_pago'],
                secuencia_evento=registro['secuencia'],
                numero_dividendo=registro['numero_dividendo'],
                descripcion=registro['descripcion'],
                valor_historico=registro['valor_historico'],
                factor_actualizacion=registro['factor_actualizacion'],
                isfut=registro['isfut'],
                forma_ingreso=CalificacionLocal.FormaIngreso.ARCHIVO,
            )
            for registro in registros
        ]
        CalificacionLocal.objects.bulk_create(calificaciones, batch_size=1000)

        detalles_pendientes = []
        for calificacion, registro in zip(calificaciones, registros):
            if calificacion.pk is None:
                raise RuntimeError('La base de datos no devolvió el identificador de una calificación.')
            detalles_pendientes.extend(
                DetalleLocal(calificacion=calificacion, concepto_id=numero, monto=monto, factor=factor)
                for numero, monto, factor in registro['detalles']
            )
            if len(detalles_pendientes) >= 2000:
                DetalleLocal.objects.bulk_create(detalles_pendientes, batch_size=2000)
                detalles_pendientes.clear()
        if detalles_pendientes:
            DetalleLocal.objects.bulk_create(detalles_pendientes, batch_size=2000)

    return len(registros)
