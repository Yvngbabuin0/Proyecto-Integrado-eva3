from unittest import mock

from django.contrib.auth.models import Group
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from .forms import MAX_INTENTOS
from .models import Corredora, Usuario


class LimiteIntentosTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        Usuario.objects.create_user('analista_a', password='clave-segura-123')

    def setUp(self):
        cache.clear()

    def login(self, password, username='analista_a'):
        return self.client.post(reverse('cuentas:login'), {'username': username, 'password': password})

    def assertEntra(self, respuesta):
        # Solo se revisa que el login redirija; el usuario de prueba no tiene rol.
        self.assertRedirects(respuesta, reverse('cuentas:inicio'), fetch_redirect_response=False)

    def fallar(self, veces, username='analista_a'):
        for _ in range(veces):
            self.login('incorrecta', username)

    def test_bloquea_despues_del_maximo_de_intentos(self):
        self.fallar(MAX_INTENTOS)
        # Ni siquiera la contraseña correcta entra mientras dura el bloqueo.
        respuesta = self.login('clave-segura-123')
        self.assertContains(respuesta, 'Demasiados intentos fallidos')
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_antes_del_maximo_todavia_puede_entrar(self):
        self.fallar(MAX_INTENTOS - 1)
        self.assertEntra(self.login('clave-segura-123'))

    def test_un_login_correcto_reinicia_el_contador(self):
        self.fallar(MAX_INTENTOS - 1)
        self.login('clave-segura-123')
        self.client.logout()
        self.fallar(MAX_INTENTOS - 1)
        self.assertEntra(self.login('clave-segura-123'))

    def test_el_bloqueo_no_distingue_mayusculas(self):
        self.fallar(MAX_INTENTOS, username='ANALISTA_A')
        self.assertContains(self.login('clave-segura-123'), 'Demasiados intentos fallidos')

    def test_el_bloqueo_es_por_usuario(self):
        Usuario.objects.create_user('corredor_a', password='otra-clave-456')
        self.fallar(MAX_INTENTOS)
        self.assertEntra(self.login('otra-clave-456', 'corredor_a'))

    def test_el_bloqueo_expira(self):
        self.fallar(MAX_INTENTOS)
        with mock.patch('cuentas.forms.cache.get', return_value=0):
            # Simula que pasaron los 15 minutos y la marca expiró.
            self.assertEntra(self.login('clave-segura-123'))


class InicioPorRolTests(TestCase):
    def entrar(self, rol=None, **campos):
        usuario = Usuario.objects.create_user('usuario', **campos)
        if rol:
            usuario.groups.add(Group.objects.get(name=rol))
        self.client.force_login(usuario)
        return self.client.get(reverse('cuentas:inicio'))

    def test_corredor_y_analista_van_al_mantenedor(self):
        corredora = Corredora.objects.create(rut='1-9', nombre='Corredora A')
        self.assertRedirects(
            self.entrar('Analista Tributario', corredora=corredora),
            reverse('calificaciones:mantenedor'),
        )

    def test_auditor_va_a_la_auditoria(self):
        self.assertRedirects(self.entrar('Auditor'), reverse('auditoria:listado'))

    def test_administrador_va_a_la_administracion(self):
        self.assertRedirects(self.entrar('Administrador', is_staff=True), reverse('admin:index'))

    def test_usuario_sin_rol_ve_acceso_denegado(self):
        self.assertEqual(self.entrar().status_code, 403)

    def test_respeta_la_pagina_que_se_queria_abrir(self):
        Usuario.objects.create_user('auditor', password='clave-segura-123').groups.add(Group.objects.get(name='Auditor'))
        url = reverse('auditoria:listado')
        respuesta = self.client.post(
            f"{reverse('cuentas:login')}?next={url}", {'username': 'auditor', 'password': 'clave-segura-123'},
        )
        self.assertRedirects(respuesta, url)
