from datetime import date
from decimal import Decimal

from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

from cuentas.models import Corredora, Usuario

from .models import CONCEPTOS, CalificacionBase, CalificacionLocal, DetalleLocal, Instrumento, Mercado


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


class LoginTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        corredora = Corredora.objects.create(rut='1-9', nombre='Corredora A')
        crear_usuario('analista_a', 'Analista Tributario', password='clave-segura-123', corredora=corredora)

    def test_login_correcto_entra_al_mantenedor(self):
        respuesta = self.client.post(reverse('cuentas:login'), {'username': 'analista_a', 'password': 'clave-segura-123'})
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
