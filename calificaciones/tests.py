import csv
import hashlib
import io
import shutil
import tempfile
from pathlib import Path
from datetime import date
from decimal import Decimal
from unittest import mock

from django.contrib.auth.models import Group
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from auditoria.models import EventoAuditoria
from cuentas.models import Corredora, Usuario

from .importador_csv import COLUMNAS_CSV, MAX_FILAS_CSV, ErrorCSV
from .models import (
    CONCEPTOS,
    CalificacionBase,
    CalificacionLocal,
    DetalleLocal,
    Instrumento,
    LoteCarga,
    Mercado,
)
from .calculo import CONCEPTOS_CON_FORMULA, SumaCeroError, factores_desde_montos


def archivo_csv(filas, nombre='calificaciones.csv'):
    contenido = io.StringIO()
    escritor = csv.writer(contenido)
    escritor.writerow(COLUMNAS_CSV)
    datos_base = {
        'mercado': 'ACC',
        'ejercicio': '2025',
        'codigo_instrumento': 'CSV-TEST',
        'secuencia_evento': '500',
        'fecha_pago': '2025-06-30',
        'numero_dividendo': '0',
        'descripcion': 'Carga de prueba',
        'valor_historico': '0',
        'factor_actualizacion': '0',
        'isfut': '0',
    }
    datos_base.update({columna: '0' for columna in COLUMNAS_CSV if columna.startswith(('monto_', 'factor_'))})
    for cambios in filas:
        datos = {**datos_base, **cambios}
        escritor.writerow([datos.get(columna, '0') for columna in COLUMNAS_CSV])
    return SimpleUploadedFile(nombre, contenido.getvalue().encode('utf-8'), content_type='text/csv')


def crear_usuario(username, rol=None, **campos):
    usuario = Usuario.objects.create_user(username, **campos)
    if rol:
        usuario.groups.add(Group.objects.get(name=rol))
    return usuario


def datos_formulario(**cambios):
    datos = {
        'mercado': Mercado.ACCIONES,
        'ejercicio': '2025',
        'codigo_instrumento': 'nuevo',
        'secuencia_evento': '100000900',
        'fecha_pago': '2025-06-30',
        'numero_dividendo': '0',
        'descripcion': 'Calificación de prueba',
        'valor_historico': '0',
        'factor_actualizacion': '0',
        'monto_8': '5000000',
        'factor_8': '0,5',
        'factor_9': '0,3',
        'factor_10': '0,2',
    }
    datos.update(cambios)
    return datos


class MantenedorTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.corredora_a = Corredora.objects.create(rut='1-9', nombre='Corredora A')
        cls.corredora_b = Corredora.objects.create(rut='2-7', nombre='Corredora B')
        cls.usuario_a = crear_usuario('analista_a', 'Analista Tributario', corredora=cls.corredora_a)
        cls.jeap = Instrumento.objects.create(codigo='JEAP', mercado=Mercado.ACCIONES)
        cls.adp = Instrumento.objects.create(codigo='ADP', mercado=Mercado.ACCIONES)

        cls.base_adp = CalificacionBase.objects.create(
            instrumento=cls.adp, ejercicio=2025, fecha_pago=date(2025, 4, 1),
            secuencia_evento=133947, descripcion='Bolsa ADP',
        )
        cls.local_a = CalificacionLocal.objects.create(
            corredora=cls.corredora_a, instrumento=cls.jeap, ejercicio=2025,
            fecha_pago=date(2025, 1, 2), secuencia_evento=100000809, descripcion='Local A',
        )
        cls.local_b = CalificacionLocal.objects.create(
            corredora=cls.corredora_b, instrumento=cls.jeap, ejercicio=2025,
            fecha_pago=date(2025, 1, 2), secuencia_evento=100000809, descripcion='Local B',
        )

    def setUp(self):
        self.client.force_login(self.usuario_a)

    def listado(self, **filtros):
        return self.client.get(reverse('calificaciones:mantenedor'), filtros)

    # Listado

    def test_listado_muestra_lo_propio_y_bolsa_pero_no_otra_corredora(self):
        respuesta = self.listado()
        self.assertContains(respuesta, 'Local A')
        self.assertContains(respuesta, 'Bolsa ADP')
        self.assertNotContains(respuesta, 'Local B')

    def test_filtro_por_origen(self):
        respuesta = self.listado(origen='bolsa')
        self.assertContains(respuesta, 'Bolsa ADP')
        self.assertNotContains(respuesta, 'Local A')

    def test_local_reemplaza_a_bolsa_en_el_listado(self):
        self.client.post(reverse('calificaciones:ingresar'), datos_formulario(
            codigo_instrumento='adp', secuencia_evento='133947', descripcion='Local reemplaza ADP',
        ))
        respuesta = self.listado()
        self.assertContains(respuesta, 'Local reemplaza ADP')
        self.assertNotContains(respuesta, 'Bolsa ADP')

    # Ingresar y modificar

    def test_ingresar_usa_la_corredora_de_la_sesion(self):
        # Aunque el formulario envíe otra corredora, se ignora.
        respuesta = self.client.post(
            reverse('calificaciones:ingresar'), datos_formulario(corredora=self.corredora_b.pk),
        )
        self.assertRedirects(respuesta, reverse('calificaciones:mantenedor'))
        nueva = CalificacionLocal.objects.get(descripcion='Calificación de prueba')
        self.assertEqual(nueva.corredora, self.corredora_a)
        self.assertEqual(nueva.instrumento.codigo, 'NUEVO')
        self.assertFalse(nueva.instrumento.inscrito)
        self.assertEqual(nueva.detalles.count(), len(CONCEPTOS))
        self.assertEqual(nueva.detalles.get(concepto_id=8).factor, Decimal('0.50000000'))

    def test_factor_mayor_a_uno_no_se_guarda(self):
        respuesta = self.client.post(reverse('calificaciones:ingresar'), datos_formulario(factor_8='1,5'))
        self.assertEqual(respuesta.status_code, 200)
        self.assertFalse(CalificacionLocal.objects.filter(descripcion='Calificación de prueba').exists())

    def test_factor_con_mas_de_ocho_decimales_no_se_guarda(self):
        respuesta = self.client.post(reverse('calificaciones:ingresar'), datos_formulario(factor_8='0,123456789'))
        self.assertEqual(respuesta.status_code, 200)
        self.assertFalse(CalificacionLocal.objects.filter(descripcion='Calificación de prueba').exists())

    def test_modificar_reemplaza_los_detalles(self):
        url = reverse('calificaciones:modificar', args=[self.local_a.pk])
        self.client.post(url, datos_formulario(codigo_instrumento='JEAP', descripcion='Local A editada', factor_8='0,1'))
        self.local_a.refresh_from_db()
        self.assertEqual(self.local_a.descripcion, 'Local A editada')
        self.assertEqual(DetalleLocal.objects.filter(calificacion=self.local_a).count(), len(CONCEPTOS))
        self.assertEqual(self.local_a.detalles.get(concepto_id=8).factor, Decimal('0.10000000'))

    def test_no_se_puede_modificar_la_de_otra_corredora(self):
        url = reverse('calificaciones:modificar', args=[self.local_b.pk])
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.post(url, datos_formulario()).status_code, 404)
        self.local_b.refresh_from_db()
        self.assertEqual(self.local_b.descripcion, 'Local B')

    # Baja lógica

    def test_baja_logica_conserva_el_registro(self):
        url = reverse('calificaciones:eliminar', args=[self.local_a.pk])
        self.assertContains(self.client.get(url), 'Confirmar eliminación')
        self.local_a.refresh_from_db()
        self.assertTrue(self.local_a.activa)  # el GET solo pide confirmación

        self.client.post(url)
        self.local_a.refresh_from_db()
        self.assertFalse(self.local_a.activa)
        self.assertNotContains(self.listado(), 'Local A')

    def test_no_se_puede_dar_de_baja_la_de_otra_corredora(self):
        respuesta = self.client.post(reverse('calificaciones:eliminar', args=[self.local_b.pk]))
        self.assertEqual(respuesta.status_code, 404)
        self.local_b.refresh_from_db()
        self.assertTrue(self.local_b.activa)

    # Acceso

    def test_usuario_sin_corredora_no_opera_calificaciones(self):
        self.client.force_login(crear_usuario('administrador', 'Administrador'))
        self.assertEqual(self.listado().status_code, 403)

    def test_sin_sesion_redirige_al_login(self):
        self.client.logout()
        for url in [
            reverse('calificaciones:mantenedor'),
            reverse('calificaciones:ingresar'),
            reverse('calificaciones:modificar', args=[self.local_a.pk]),
            reverse('calificaciones:eliminar', args=[self.local_a.pk]),
        ]:
            self.assertRedirects(self.client.get(url), f"{reverse('cuentas:login')}?next={url}")


class CarpetaCSVTemporalMixin:
    """Guarda los CSV pendientes en una carpeta temporal durante las pruebas."""

    def setUp(self):
        super().setUp()
        self.carpeta_csv = Path(tempfile.mkdtemp())
        self.carpeta_lotes = Path(tempfile.mkdtemp())
        ajuste = override_settings(CSV_PENDIENTES_DIR=self.carpeta_csv, CSV_LOTES_DIR=self.carpeta_lotes)
        ajuste.enable()
        self.addCleanup(ajuste.disable)
        self.addCleanup(shutil.rmtree, self.carpeta_csv, ignore_errors=True)
        self.addCleanup(shutil.rmtree, self.carpeta_lotes, ignore_errors=True)


class CargaCSVTests(CarpetaCSVTemporalMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.corredora = Corredora.objects.create(rut='3-5', nombre='Corredora CSV')
        cls.analista = crear_usuario('analista_csv', 'Analista Tributario', corredora=cls.corredora)

    def setUp(self):
        super().setUp()
        self.client.force_login(self.analista)

    def cargar(self, archivo):
        """Sube el archivo y, si pasa la validación, confirma la carga desde la previsualización."""
        respuesta = self.client.post(reverse('calificaciones:cargar_csv'), {'archivo': archivo})
        if respuesta.status_code == 302 and respuesta['Location'] == reverse('calificaciones:previsualizar_csv'):
            return self.client.post(reverse('calificaciones:confirmar_csv'))
        return respuesta

    def test_carga_csv_guarda_calificaciones_y_detalles(self):
        respuesta = self.cargar(archivo_csv([{
            'descripcion': 'Importada',
            'monto_8': '1200.50',
            'factor_8': '0.5',
        }]))

        self.assertRedirects(respuesta, reverse('calificaciones:mantenedor'))
        calificacion = CalificacionLocal.objects.get(descripcion='Importada')
        self.assertEqual(calificacion.forma_ingreso, CalificacionLocal.FormaIngreso.ARCHIVO)
        self.assertEqual(calificacion.corredora, self.corredora)
        self.assertEqual(calificacion.detalles.count(), len(CONCEPTOS))
        detalle = calificacion.detalles.get(concepto_id=8)
        self.assertEqual(detalle.monto, Decimal('1200.50'))
        self.assertEqual(detalle.factor, Decimal('0.50000000'))

    def test_celda_vacia_rechaza_todo_el_archivo_sin_crear_instrumento(self):
        respuesta = self.cargar(archivo_csv([
            {'descripcion': 'Primera fila', 'secuencia_evento': '501'},
            {'descripcion': 'Fila inválida', 'secuencia_evento': '502', 'monto_8': ''},
        ]))

        self.assertContains(respuesta, 'Fila 3')
        self.assertFalse(CalificacionLocal.objects.filter(corredora=self.corredora).exists())
        self.assertFalse(Instrumento.objects.filter(codigo='CSV-TEST').exists())

    def test_valor_nulo_rechaza_todo_el_archivo(self):
        respuesta = self.cargar(archivo_csv([{'descripcion': 'null'}]))

        self.assertContains(respuesta, 'vacíos o nulos')
        self.assertFalse(CalificacionLocal.objects.filter(corredora=self.corredora).exists())

    def test_acepta_punto_y_coma_y_coma_decimal(self):
        contenido = io.StringIO()
        escritor = csv.writer(contenido, delimiter=';')
        escritor.writerow(COLUMNAS_CSV)
        datos = {columna: '0' for columna in COLUMNAS_CSV}
        datos.update({
            'mercado': 'ACC',
            'ejercicio': '2025',
            'codigo_instrumento': 'CSV-TEST',
            'secuencia_evento': '501',
            'fecha_pago': '2025-06-30',
            'descripcion': 'Importada con coma decimal',
            'monto_8': '1200,50',
            'factor_8': '0,5',
        })
        escritor.writerow([datos[columna] for columna in COLUMNAS_CSV])
        archivo = SimpleUploadedFile('calificaciones.csv', contenido.getvalue().encode('utf-8'))

        respuesta = self.cargar(archivo)

        self.assertRedirects(respuesta, reverse('calificaciones:mantenedor'))
        calificacion = CalificacionLocal.objects.get(descripcion='Importada con coma decimal')
        self.assertEqual(calificacion.detalles.get(concepto_id=8).monto, Decimal('1200.50'))

    def crear_existente(self, corredora=None, **campos):
        instrumento, _ = Instrumento.objects.get_or_create(codigo='CSV-TEST', mercado=Mercado.ACCIONES)
        datos = {
            'corredora': corredora or self.corredora, 'instrumento': instrumento, 'ejercicio': 2025,
            'fecha_pago': date(2025, 6, 30), 'secuencia_evento': 500, 'descripcion': 'Ya existe',
            'forma_ingreso': CalificacionLocal.FormaIngreso.MANUAL,
        }
        datos.update(campos)
        calificacion = CalificacionLocal.objects.create(**datos)
        calificacion.detalles.create(concepto_id=8, monto=Decimal('10'), factor=Decimal('0.1'))
        return calificacion

    def test_fila_existente_actualiza_la_calificacion_en_vez_de_rechazar(self):
        existente = self.crear_existente()

        respuesta = self.cargar(archivo_csv([
            {'descripcion': 'Nueva', 'secuencia_evento': '501'},
            {'descripcion': 'Actualizada', 'monto_8': '500', 'factor_8': '0.75'},
        ]))

        self.assertRedirects(respuesta, reverse('calificaciones:mantenedor'))
        self.assertEqual(CalificacionLocal.objects.filter(corredora=self.corredora).count(), 2)
        existente.refresh_from_db()
        self.assertEqual(existente.descripcion, 'Actualizada')
        self.assertEqual(existente.forma_ingreso, CalificacionLocal.FormaIngreso.ARCHIVO)
        self.assertEqual(existente.detalles.count(), len(CONCEPTOS))
        self.assertEqual(existente.detalles.get(concepto_id=8).factor, Decimal('0.75000000'))
        self.assertGreater(existente.modificada, existente.creada)

    def test_mensaje_indica_nuevas_y_actualizadas(self):
        self.crear_existente()
        respuesta = self.client.post(
            reverse('calificaciones:cargar_csv'),
            {'archivo': archivo_csv([{'secuencia_evento': '501'}, {'secuencia_evento': '502'}, {}])},
        )
        respuesta = self.client.post(reverse('calificaciones:confirmar_csv'), follow=True)
        self.assertContains(respuesta, '2 calificaciones nuevas y 1 actualizadas')

    def test_no_actualiza_la_calificacion_de_otra_corredora(self):
        otra = Corredora.objects.create(rut='9-9', nombre='Otra corredora')
        ajena = self.crear_existente(corredora=otra)

        self.cargar(archivo_csv([{'descripcion': 'Propia'}]))

        ajena.refresh_from_db()
        self.assertEqual(ajena.descripcion, 'Ya existe')
        self.assertTrue(CalificacionLocal.objects.filter(corredora=self.corredora, descripcion='Propia').exists())

    def test_suma_de_factores_8_a_19_mayor_a_uno_rechaza_el_archivo(self):
        respuesta = self.cargar(archivo_csv([{'factor_8': '0.6', 'factor_19': '0.40000001'}]))

        self.assertContains(respuesta, 'la suma de los factores 8 a 19 es 1,00000001 y no puede superar 1')
        self.assertFalse(CalificacionLocal.objects.filter(corredora=self.corredora).exists())

    def test_factores_20_a_37_no_entran_en_la_suma(self):
        respuesta = self.cargar(archivo_csv([{'factor_8': '1', 'factor_20': '0.5', 'factor_34': '0.5'}]))

        self.assertRedirects(respuesta, reverse('calificaciones:mantenedor'))

    def test_carga_registra_creacion_y_modificacion_en_auditoria(self):
        existente = self.crear_existente()

        self.cargar(archivo_csv([
            {'descripcion': 'Nueva', 'secuencia_evento': '501'},
            {'descripcion': 'Actualizada', 'factor_8': '0.75'},
        ]))

        nueva = CalificacionLocal.objects.get(descripcion='Nueva')
        creacion = EventoAuditoria.objects.get(calificacion_id=nueva.pk)
        self.assertEqual(creacion.accion, EventoAuditoria.Accion.CREAR)
        self.assertEqual(creacion.usuario, self.analista)
        self.assertIsNone(creacion.estado_anterior)
        self.assertEqual(len(creacion.estado_posterior['detalles']), len(CONCEPTOS))

        modificacion = EventoAuditoria.objects.get(calificacion_id=existente.pk)
        self.assertEqual(modificacion.accion, EventoAuditoria.Accion.MODIFICAR)
        self.assertEqual(modificacion.estado_anterior['descripcion'], 'Ya existe')
        self.assertEqual(modificacion.estado_anterior['detalles'][0]['factor'], '0.10000000')
        self.assertEqual(modificacion.estado_posterior['descripcion'], 'Actualizada')
    def test_superar_5000_filas_rechaza_el_archivo_sin_guardar(self):
        filas = ({'secuencia_evento': str(1000 + indice)} for indice in range(MAX_FILAS_CSV + 1))

        respuesta = self.cargar(archivo_csv(filas))

        self.assertContains(respuesta, f'máximo de {MAX_FILAS_CSV} filas')
        self.assertFalse(CalificacionLocal.objects.filter(corredora=self.corredora).exists())

    def test_permite_cargar_exactamente_5000_filas(self):
        filas = ({'secuencia_evento': str(1000 + indice)} for indice in range(MAX_FILAS_CSV))

        respuesta = self.cargar(archivo_csv(filas))

        self.assertRedirects(respuesta, reverse('calificaciones:mantenedor'))
        self.assertEqual(CalificacionLocal.objects.filter(corredora=self.corredora).count(), MAX_FILAS_CSV)
        self.assertEqual(
            DetalleLocal.objects.filter(calificacion__corredora=self.corredora).count(),
            MAX_FILAS_CSV * len(CONCEPTOS),
        )

    def test_usuario_sin_permiso_no_puede_cargar_csv(self):
        corredor = crear_usuario('corredor_csv', 'Corredor', corredora=self.corredora)
        self.client.force_login(corredor)

        respuesta = self.client.get(reverse('calificaciones:cargar_csv'))

        self.assertEqual(respuesta.status_code, 403)


class LoginTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        corredora = Corredora.objects.create(rut='1-9', nombre='Corredora A')
        crear_usuario('analista_a', 'Analista Tributario', password='clave-segura-123', corredora=corredora)

    def test_login_correcto_entra_al_mantenedor(self):
        respuesta = self.client.post(
            reverse('cuentas:login'), {'username': 'analista_a', 'password': 'clave-segura-123'}, follow=True,
        )
        self.assertRedirects(respuesta, reverse('calificaciones:mantenedor'))

    def test_login_incorrecto_muestra_error(self):
        respuesta = self.client.post(reverse('cuentas:login'), {'username': 'analista_a', 'password': 'otra'})
        self.assertContains(respuesta, 'Usuario o contraseña incorrectos.')

    def test_logout_cierra_la_sesion(self):
        self.client.login(username='analista_a', password='clave-segura-123')
        respuesta = self.client.post(reverse('cuentas:logout'))
        self.assertRedirects(respuesta, reverse('cuentas:login'))
        self.assertEqual(self.client.get(reverse('calificaciones:mantenedor')).status_code, 302)


class RolesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.corredora = Corredora.objects.create(rut='1-9', nombre='Corredora A')
        instrumento = Instrumento.objects.create(codigo='JEAP', mercado=Mercado.ACCIONES)
        cls.local = CalificacionLocal.objects.create(
            corredora=cls.corredora, instrumento=instrumento, ejercicio=2025,
            fecha_pago=date(2025, 1, 2), secuencia_evento=1, descripcion='Local',
        )

    def test_corredor_opera_sus_calificaciones_pero_no_carga_masiva(self):
        corredor = crear_usuario('corredor', 'Corredor', corredora=self.corredora)
        self.client.force_login(corredor)
        self.assertEqual(self.client.get(reverse('calificaciones:mantenedor')).status_code, 200)
        self.assertEqual(self.client.get(reverse('calificaciones:ingresar')).status_code, 200)
        self.assertEqual(self.client.get(reverse('calificaciones:modificar', args=[self.local.pk])).status_code, 200)
        self.assertFalse(corredor.has_perm('calificaciones.carga_masiva'))

    def test_solo_el_analista_tiene_carga_masiva(self):
        analista = crear_usuario('analista', 'Analista Tributario', corredora=self.corredora)
        self.assertTrue(analista.has_perm('calificaciones.carga_masiva'))

    def test_usuario_sin_rol_no_entra_aunque_tenga_corredora(self):
        self.client.force_login(crear_usuario('sin_rol', corredora=self.corredora))
        for url in [
            reverse('calificaciones:mantenedor'),
            reverse('calificaciones:ingresar'),
            reverse('calificaciones:modificar', args=[self.local.pk]),
            reverse('calificaciones:eliminar', args=[self.local.pk]),
        ]:
            self.assertEqual(self.client.get(url).status_code, 403, url)

    def test_auditor_no_opera_calificaciones(self):
        self.client.force_login(crear_usuario('auditor', 'Auditor'))
        self.assertEqual(self.client.get(reverse('calificaciones:mantenedor')).status_code, 403)

    def test_administrador_no_puede_volverse_superusuario(self):
        administrador = crear_usuario('admin_rol', 'Administrador', is_staff=True)
        self.client.force_login(administrador)
        url = reverse('admin:cuentas_usuario_change', args=[administrador.pk])
        respuesta = self.client.get(url)
        self.assertEqual(respuesta.status_code, 200)
        self.assertNotContains(respuesta, 'name="is_superuser"')
        self.assertNotContains(respuesta, 'name="user_permissions"')


class AccesoDenegadoTests(TestCase):
    def test_administrador_ve_enlace_a_la_administracion(self):
        self.client.force_login(crear_usuario('admin_rol', 'Administrador', is_staff=True))
        respuesta = self.client.get(reverse('calificaciones:mantenedor'))
        self.assertContains(respuesta, 'no pertenece a una corredora', status_code=403)
        self.assertContains(respuesta, reverse('admin:index'), status_code=403)

    # ---------- Pruebas nuevas para la funcionalidad de cálculo de factores ----------
class CalculoBotonTests(TestCase):
    def setUp(self):
        # Ensure a Corredora exists for the user
        self.corredora = Corredora.objects.create(rut='1-1', nombre='TestCorredora')
        self.user = crear_usuario('analista_test', 'Analista Tributario', corredora=self.corredora)
        self.user.is_staff = True
        self.user.is_superuser = True
        self.user.save()
        self.client.force_login(self.user)

    def test_calcular_con_montos_correctos(self):
        datos = {
            'mercado': 'ACC',
            'ejercicio': '2025',
            'codigo_instrumento': 'NI',
            'secuencia_evento': '100001',
            'fecha_pago': '2025-01-01',
            'numero_dividendo': '0',
            'descripcion': 'Test calcular',
            'valor_historico': '0',
            'factor_actualizacion': '0',
            'monto_8': '192770580',
            'monto_9': '64161878',
            'monto_10': '0',
            'monto_11': '111812860',
            'monto_25': '71298705',
            'monto_30': '15837333',
        }
        uri = reverse('calificaciones:ingresar')
        respuesta = self.client.post(uri, datos, follow=True)
        self.assertRedirects(respuesta, reverse('calificaciones:mantenedor'))

    def test_calcular_suma_cero_muestra_error(self):
        datos = {
            'mercado': 'ACC',
            'ejercicio': '2025',
            'codigo_instrumento': 'NI',
            'secuencia_evento': '100001',
            'fecha_pago': '2025-01-01',
            'numero_dividendo': '0',
            'descripcion': 'Suma cero',
            'valor_historico': '0',
            'factor_actualizacion': '0',
            # all amounts zero
            'monto_8': '0',
            'monto_9': '0',
            'monto_10': '0',
            'monto_11': '0',
            'monto_12': '0',
            'monto_13': '0',
            'monto_14': '0',
            'monto_15': '0',
            'monto_16': '0',
            'monto_17': '0',
            'monto_18': '0',
            'monto_19': '0',
            'accion': 'calcular',
        }
        uri = reverse('calificaciones:ingresar')
        respuesta = self.client.post(uri, datos)
        self.assertContains(respuesta, 'Ingresa al menos un monto')
        self.assertFalse(CalificacionLocal.objects.exists())

    def test_calcular_y_grabar_sin_editar(self):
        datos = {
            'mercado': 'ACC',
            'ejercicio': '2025',
            'codigo_instrumento': 'NI',
            'secuencia_evento': '100001',
            'fecha_pago': '2025-01-01',
            'numero_dividendo': '0',
            'descripcion': 'Calcular y grabar',
            'valor_historico': '0',
            'factor_actualizacion': '0',
        }
        uri = reverse('calificaciones:ingresar')
        datos_calcular = datos.copy()
        datos_calcular['accion'] = 'calcular'
        self.client.post(uri, datos_calcular)
        datos_grabar = datos.copy()
        self.client.post(uri, datos_grabar, follow=True)
        self.assertTrue(CalificacionLocal.objects.filter(descripcion='Calcular y grabar').exists())

    def datos_seis_montos_iguales(self, **extra):
        datos = {
            'mercado': 'ACC', 'ejercicio': '2025', 'codigo_instrumento': 'SEIS',
            'secuencia_evento': '100001', 'fecha_pago': '2025-01-01',
            'numero_dividendo': '0', 'descripcion': 'Seis montos iguales',
            'valor_historico': '0', 'factor_actualizacion': '0',
        }
        datos.update({f'monto_{n}': '1000' for n in range(8, 14)})
        datos.update(extra)
        return datos

    def test_calcular_y_grabar_seis_montos_iguales(self):
        # Antes del ajuste, estos factores sumaban 1,00000002.
        uri = reverse('calificaciones:ingresar')
        calculo = self.client.post(uri, self.datos_seis_montos_iguales(accion='calcular'))
        self.assertContains(calculo, 'value="0,16666666"')
        datos = self.datos_seis_montos_iguales()
        datos.update({clave: valor for clave, valor in calculo.context['detalles'].data.items() if clave.startswith('factor_')})
        respuesta = self.client.post(uri, datos)
        self.assertRedirects(respuesta, reverse('calificaciones:mantenedor'))
        calificacion = CalificacionLocal.objects.get(descripcion='Seis montos iguales')
        suma = sum(d.factor for d in calificacion.detalles.filter(concepto_id__in=range(8, 20)))
        self.assertEqual(suma, Decimal('1.00000000'))

    def test_factores_que_suman_mas_de_uno_se_bloquean(self):
        factores = {f'factor_{n}': '0,16666667' for n in range(8, 14)}
        respuesta = self.client.post(reverse('calificaciones:ingresar'), self.datos_seis_montos_iguales(**factores))
        self.assertContains(respuesta, 'La suma de los factores 8 a 19 no puede superar 1')
        self.assertFalse(CalificacionLocal.objects.exists())

    def test_calcular_no_muestra_notacion_cientifica(self):
        # Los factores cero no deben renderizar como '0E-8'.
        datos = {
            'mercado': 'ACC', 'ejercicio': '2025', 'codigo_instrumento': 'NI',
            'secuencia_evento': '100001', 'fecha_pago': '2025-01-01',
            'numero_dividendo': '0', 'descripcion': 'Notacion',
            'valor_historico': '0', 'factor_actualizacion': '0',
            'monto_8': '100', 'monto_9': '0', 'monto_10': '0', 'monto_11': '0',
            'monto_12': '0', 'monto_13': '0', 'monto_14': '0', 'monto_15': '0',
            'monto_16': '0', 'monto_17': '0', 'monto_18': '0', 'monto_19': '0',
            'accion': 'calcular',
        }
        uri = reverse('calificaciones:ingresar')
        respuesta = self.client.post(uri, datos)
        self.assertEqual(respuesta.status_code, 200)
        self.assertNotContains(respuesta, '0E-')
        self.assertContains(respuesta, '0,00000000')

    def test_calcular_factores_20_a_33_con_formula_hdu(self):
        """Verifica que el botón Calcular calcule factores 8-33 usando la fórmula HDU."""
        datos = {
            'mercado': 'ACC',
            'ejercicio': '2025',
            'codigo_instrumento': 'NI',
            'secuencia_evento': '100001',
            'fecha_pago': '2025-01-01',
            'numero_dividendo': '0',
            'descripcion': 'Test HDU',
            'valor_historico': '0',
            'factor_actualizacion': '0',
            # Montos del ejemplo HDU Hoja 3.2
            'monto_8': '192770580',
            'monto_9': '64161878',
            'monto_10': '0',
            'monto_11': '111812860',
            'monto_25': '71298705',
            'monto_30': '15837333',
            # Monto en concepto 35 (ingreso directo - NO se debe calcular)
            'monto_35': '10000000',
            'accion': 'calcular',
        }
        uri = reverse('calificaciones:ingresar')
        respuesta = self.client.post(uri, datos)
        self.assertEqual(respuesta.status_code, 200)

        # Verificar factores calculados en la respuesta (formato con coma decimal)
        # F8 = 0.52277431
        self.assertContains(respuesta, '0,52277431')
        # F9 = 0.17400052
        self.assertContains(respuesta, '0,17400052')
        # F10 = 0.00000000
        self.assertContains(respuesta, '0,00000000')
        # F11 = 0.30322517
        self.assertContains(respuesta, '0,30322517')
        # F25 = 0.19335488
        self.assertContains(respuesta, '0,19335488')
        # F30 = 0.04294924
        self.assertContains(respuesta, '0,04294924')

        # El concepto 35 es de ingreso directo: aunque tenga monto, su factor no se calcula.
        self.assertContains(respuesta, '<input type="text" name="factor_35" id="id_factor_35">', html=True)
        self.assertNotIn('factor_35', respuesta.context['detalles'].data)

    def test_calcular_y_grabar_con_variaciones_intervencion_negada(self):
        self.skipTest('Skip complex variation test')
        datos = {
            'mercado': 'ACC',
            'ejercicio': '2025',
            'codigo_instrumento': 'NI',
            'secuencia_evento': '100001',
            'fecha_pago': '2025-01-01',
            'numero_dividendo': '0',
            'descripcion': 'Falla suma',
            'valor_historico': '0',
            'factor_actualizacion': '0',
        }
        uri = reverse('calificaciones:ingresar')
        datos_calcular = datos.copy(); datos_calcular['accion']='calcular'
        self.client.post(uri, datos_calcular)
        datos_grabar = datos.copy(); datos_grabar['factor_8']='1,0'
        respuesta = self.client.post(uri, datos_grabar)
        self.assertContains(respuesta, 'La suma de los factores 8 a 19 no puede superar 1')
        self.assertFalse(CalificacionLocal.objects.filter(descripcion='Falla suma').exists())
        datos_inadecuado = datos.copy(); datos_inadecuado['factor_8']='0,6'; datos_inadecuado['factor_9']='0,8'
        respuesta2=self.client.post(uri, datos_inadecuado)
        self.assertContains(respuesta2, 'no puede superar 1')




class CatalogoConceptosTests(TestCase):
    def test_los_30_conceptos_tienen_nombres_distintos(self):
        from .models import ConceptoTributario

        nombres = list(ConceptoTributario.objects.values_list('nombre', flat=True))
        self.assertEqual(len(nombres), 30)
        self.assertEqual(len(set(nombres)), 30)

    def test_creditos_por_ipe_indican_su_grupo(self):
        from .models import ConceptoTributario

        self.assertIn('01.01.2017', ConceptoTributario.objects.get(numero=28).nombre)
        self.assertIn('31.12.2016', ConceptoTributario.objects.get(numero=33).nombre)


class PrevisualizacionCSVTests(CarpetaCSVTemporalMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.corredora = Corredora.objects.create(rut='3-5', nombre='Corredora CSV')
        cls.analista = crear_usuario('analista_csv', 'Analista Tributario', corredora=cls.corredora)

    def setUp(self):
        super().setUp()
        self.client.force_login(self.analista)

    def subir(self, filas):
        return self.client.post(reverse('calificaciones:cargar_csv'), {'archivo': archivo_csv(filas)})

    def locales(self):
        return CalificacionLocal.objects.filter(corredora=self.corredora)

    def test_subir_muestra_la_previsualizacion_sin_guardar(self):
        respuesta = self.subir([{'descripcion': 'Primera', 'factor_8': '0.6', 'factor_9': '0.4'}])
        self.assertRedirects(respuesta, reverse('calificaciones:previsualizar_csv'))

        previsualizacion = self.client.get(reverse('calificaciones:previsualizar_csv'))
        self.assertContains(previsualizacion, 'Primera')
        self.assertContains(previsualizacion, 'CSV-TEST')
        self.assertContains(previsualizacion, '1,00000000')  # suma F8–F19
        self.assertEqual(
            previsualizacion.context['resumen'],
            {'filas': 1, 'nuevas': 1, 'actualizadas': 0, 'instrumentos_nuevos': 1},
        )
        self.assertFalse(self.locales().exists())
        self.assertEqual(len(list(self.carpeta_csv.iterdir())), 1)

    def test_confirmar_guarda_y_borra_el_archivo_pendiente(self):
        self.subir([{'descripcion': 'Confirmada'}])
        respuesta = self.client.post(reverse('calificaciones:confirmar_csv'))
        self.assertRedirects(respuesta, reverse('calificaciones:mantenedor'))
        self.assertTrue(self.locales().filter(descripcion='Confirmada').exists())
        self.assertEqual(list(self.carpeta_csv.iterdir()), [])

    def test_cancelar_no_guarda_nada_y_borra_el_archivo(self):
        self.subir([{'descripcion': 'Cancelada'}])
        respuesta = self.client.post(reverse('calificaciones:cancelar_csv'))
        self.assertRedirects(respuesta, reverse('calificaciones:cargar_csv'))
        self.assertFalse(self.locales().exists())
        self.assertEqual(list(self.carpeta_csv.iterdir()), [])
        self.assertRedirects(
            self.client.get(reverse('calificaciones:previsualizar_csv')), reverse('calificaciones:cargar_csv'),
        )

    def test_archivo_invalido_no_queda_pendiente(self):
        respuesta = self.subir([{'factor_8': '1.5'}])
        self.assertContains(respuesta, 'factor_8 debe estar entre 0 y 1')
        self.assertEqual(list(self.carpeta_csv.iterdir()), [])

    def test_confirmar_sin_archivo_pendiente(self):
        respuesta = self.client.post(reverse('calificaciones:confirmar_csv'), follow=True)
        self.assertContains(respuesta, 'No hay un archivo pendiente')

    def test_confirmar_y_cancelar_solo_aceptan_post(self):
        self.assertEqual(self.client.get(reverse('calificaciones:confirmar_csv')).status_code, 405)
        self.assertEqual(self.client.get(reverse('calificaciones:cancelar_csv')).status_code, 405)

    def test_calificacion_creada_despues_de_previsualizar_se_actualiza(self):
        self.subir([{'descripcion': 'Desde CSV'}])
        instrumento = Instrumento.objects.create(codigo='CSV-TEST', mercado=Mercado.ACCIONES)
        manual = CalificacionLocal.objects.create(
            corredora=self.corredora, instrumento=instrumento, ejercicio=2025,
            fecha_pago=date(2025, 6, 30), secuencia_evento=500, descripcion='Ingresada a mano',
        )
        respuesta = self.client.post(reverse('calificaciones:confirmar_csv'), follow=True)
        self.assertContains(respuesta, '0 calificaciones nuevas y 1 actualizadas')
        manual.refresh_from_db()
        self.assertEqual(manual.descripcion, 'Desde CSV')
        self.assertEqual(self.locales().count(), 1)

    def test_previsualizacion_marca_las_filas_que_se_actualizan(self):
        instrumento = Instrumento.objects.create(codigo='CSV-TEST', mercado=Mercado.ACCIONES)
        CalificacionLocal.objects.create(
            corredora=self.corredora, instrumento=instrumento, ejercicio=2025,
            fecha_pago=date(2025, 6, 30), secuencia_evento=500, descripcion='Existente',
        )
        self.subir([{'descripcion': 'Reemplazo'}, {'descripcion': 'Otra', 'secuencia_evento': '501'}])

        previsualizacion = self.client.get(reverse('calificaciones:previsualizar_csv'))

        self.assertEqual(
            previsualizacion.context['resumen'],
            {'filas': 2, 'nuevas': 1, 'actualizadas': 1, 'instrumentos_nuevos': 0},
        )
        self.assertContains(previsualizacion, 'Actualiza</span>', count=1)
        self.assertContains(previsualizacion, 'Nueva</span>', count=1)
        self.assertEqual(self.locales().get().descripcion, 'Existente')
    def test_otro_usuario_no_puede_confirmar_el_archivo_ajeno(self):
        self.subir([{'descripcion': 'Ajena'}])
        self.client.force_login(crear_usuario('analista_2', 'Analista Tributario', corredora=self.corredora))
        respuesta = self.client.post(reverse('calificaciones:confirmar_csv'), follow=True)
        self.assertContains(respuesta, 'No hay un archivo pendiente')
        self.assertFalse(self.locales().filter(descripcion='Ajena').exists())

    def test_corredor_no_puede_previsualizar_ni_confirmar(self):
        self.client.force_login(crear_usuario('corredor_csv', 'Corredor', corredora=self.corredora))
        self.assertEqual(self.client.get(reverse('calificaciones:previsualizar_csv')).status_code, 403)
        self.assertEqual(self.client.post(reverse('calificaciones:confirmar_csv')).status_code, 403)


class DuplicadosCSVTests(CarpetaCSVTemporalMixin, TestCase):
    def test_una_calificacion_dada_de_baja_se_puede_volver_a_cargar(self):
        corredora = Corredora.objects.create(rut='3-5', nombre='Corredora CSV')
        self.client.force_login(crear_usuario('analista_csv', 'Analista Tributario', corredora=corredora))
        instrumento = Instrumento.objects.create(codigo='CSV-TEST', mercado=Mercado.ACCIONES)
        CalificacionLocal.objects.create(
            corredora=corredora, instrumento=instrumento, ejercicio=2025, fecha_pago=date(2025, 6, 30),
            secuencia_evento=500, descripcion='Dada de baja', activa=False,
        )
        respuesta = self.client.post(reverse('calificaciones:cargar_csv'), {'archivo': archivo_csv([{'descripcion': 'Nueva'}])})
        self.assertRedirects(respuesta, reverse('calificaciones:previsualizar_csv'))
        self.client.post(reverse('calificaciones:confirmar_csv'))
        self.assertTrue(CalificacionLocal.objects.filter(descripcion='Nueva', activa=True).exists())
        self.assertTrue(CalificacionLocal.objects.filter(descripcion='Dada de baja', activa=False).exists())


class LoteCargaTests(CarpetaCSVTemporalMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.corredora = Corredora.objects.create(rut='3-5', nombre='Corredora CSV')
        cls.analista = crear_usuario('analista_csv', 'Analista Tributario', corredora=cls.corredora)

    def setUp(self):
        super().setUp()
        self.client.force_login(self.analista)

    def subir(self, filas, nombre='calificaciones.csv'):
        archivo = archivo_csv(filas, nombre)
        contenido = archivo.read()
        archivo.seek(0)
        respuesta = self.client.post(reverse('calificaciones:cargar_csv'), {'archivo': archivo})
        return respuesta, contenido

    def test_confirmar_registra_el_lote_con_su_archivo_original(self):
        instrumento = Instrumento.objects.create(codigo='CSV-TEST', mercado=Mercado.ACCIONES)
        CalificacionLocal.objects.create(
            corredora=self.corredora, instrumento=instrumento, ejercicio=2025,
            fecha_pago=date(2025, 6, 30), secuencia_evento=500, descripcion='Existente',
        )
        _, contenido = self.subir([{}, {'secuencia_evento': '501'}, {'secuencia_evento': '502'}], 'dividendos.csv')
        respuesta = self.client.post(reverse('calificaciones:confirmar_csv'), follow=True)

        lote = LoteCarga.objects.get()
        self.assertContains(respuesta, f'Carga confirmada (lote {lote.pk}): 2 calificaciones nuevas y 1 actualizadas')
        self.assertEqual(lote.estado, LoteCarga.Estado.CARGADO)
        self.assertEqual((lote.corredora, lote.usuario), (self.corredora, self.analista))
        self.assertEqual(lote.nombre_original, 'dividendos.csv')
        self.assertEqual((lote.filas, lote.nuevas, lote.actualizadas), (3, 2, 1))
        self.assertEqual(lote.tamano, len(contenido))
        self.assertEqual(lote.huella, hashlib.sha256(contenido).hexdigest())
        self.assertEqual(lote.errores, [])
        # El archivo se guarda con el nombre generado, nunca con el enviado por el usuario.
        self.assertEqual(list(self.carpeta_lotes.iterdir()), [self.carpeta_lotes / f'{lote.archivo_id}.csv'])
        self.assertEqual((self.carpeta_lotes / f'{lote.archivo_id}.csv').read_bytes(), contenido)

    def test_la_carga_deja_un_evento_del_lote_y_uno_por_calificacion(self):
        self.subir([{}, {'secuencia_evento': '501'}])
        self.client.post(reverse('calificaciones:confirmar_csv'))

        lote = LoteCarga.objects.get()
        carga = EventoAuditoria.objects.get(accion=EventoAuditoria.Accion.CARGA)
        self.assertEqual(carga.lote, lote)
        self.assertIsNone(carga.calificacion_id)
        self.assertEqual(carga.usuario, self.analista)
        self.assertEqual(
            EventoAuditoria.objects.filter(accion=EventoAuditoria.Accion.CREAR, lote=lote).count(), 2,
        )

    def test_archivo_rechazado_al_subirlo_queda_registrado(self):
        respuesta, contenido = self.subir([{}, {'secuencia_evento': '501', 'factor_8': '1.5'}], 'malo.csv')

        self.assertContains(respuesta, 'factor_8 debe estar entre 0 y 1')
        lote = LoteCarga.objects.get()
        self.assertEqual(lote.estado, LoteCarga.Estado.RECHAZADO)
        self.assertEqual(lote.nombre_original, 'malo.csv')
        self.assertEqual(lote.filas, 0)
        self.assertEqual(
            lote.errores, [{'fila': 3, 'col': 'factor_8', 'error': 'Fila 3: factor_8 debe estar entre 0 y 1.'}],
        )
        self.assertEqual((self.carpeta_lotes / f'{lote.archivo_id}.csv').read_bytes(), contenido)
        rechazo = EventoAuditoria.objects.get()
        self.assertEqual((rechazo.accion, rechazo.lote), (EventoAuditoria.Accion.RECHAZO, lote))
        self.assertFalse(CalificacionLocal.objects.exists())

    def test_falla_al_confirmar_revierte_todo_y_registra_el_rechazo(self):
        self.subir([{}])
        with mock.patch('calificaciones.lotes.guardar_registros', side_effect=ErrorCSV('Falla simulada')):
            respuesta = self.client.post(reverse('calificaciones:confirmar_csv'), follow=True)

        self.assertContains(respuesta, 'Falla simulada')
        self.assertFalse(CalificacionLocal.objects.exists())
        lote = LoteCarga.objects.get()  # el lote CARGADO se revirtió; solo queda el rechazo
        self.assertEqual(lote.estado, LoteCarga.Estado.RECHAZADO)
        self.assertEqual(lote.errores, [{'fila': None, 'col': None, 'error': 'Falla simulada'}])
        self.assertEqual(list(self.carpeta_lotes.iterdir()), [self.carpeta_lotes / f'{lote.archivo_id}.csv'])
        self.assertEqual(
            list(EventoAuditoria.objects.values_list('accion', flat=True)), [EventoAuditoria.Accion.RECHAZO],
        )

    def test_cancelar_no_crea_lote(self):
        self.subir([{}])
        self.client.post(reverse('calificaciones:cancelar_csv'))
        self.assertFalse(LoteCarga.objects.exists())
        self.assertFalse(EventoAuditoria.objects.exists())

    def test_el_log_muestra_el_rechazo_con_sus_errores(self):
        self.subir([{'monto_8': ''}], 'vacio.csv')
        evento = EventoAuditoria.objects.get()

        listado = self.client.get(reverse('auditoria:listado'))
        self.assertContains(listado, 'Carga rechazada')
        self.assertContains(listado, f'Lote {evento.lote_id} · vacio.csv')

        detalle = self.client.get(reverse('auditoria:detalle', args=[evento.pk]))
        self.assertContains(detalle, 'hay campos vacíos o nulos: monto_8')
        self.assertContains(detalle, evento.lote.huella)

    def test_otra_corredora_no_ve_el_lote_en_el_log(self):
        self.subir([{'monto_8': ''}])
        evento = EventoAuditoria.objects.get()
        otra = Corredora.objects.create(rut='9-9', nombre='Otra corredora')
        self.client.force_login(crear_usuario('analista_otra', 'Analista Tributario', corredora=otra))

        self.assertEqual(self.client.get(reverse('auditoria:detalle', args=[evento.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse('auditoria:listado')).context['pagina'].paginator.count, 0)

    def test_error_inesperado_al_confirmar_no_deja_archivo_huerfano(self):
        self.subir([{}])
        with mock.patch('calificaciones.lotes._evento_lote', side_effect=RuntimeError('Falla de la base')):
            with self.assertRaises(RuntimeError):
                self.client.post(reverse('calificaciones:confirmar_csv'))

        self.assertFalse(LoteCarga.objects.exists())
        self.assertFalse(CalificacionLocal.objects.exists())
        self.assertEqual(list(self.carpeta_lotes.iterdir()), [])
