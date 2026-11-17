from datetime import date
from unittest import mock

from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

from calificaciones.models import CONCEPTOS, CalificacionLocal, Instrumento, Mercado
from cuentas.models import Corredora, Usuario

from .models import EventoAuditoria


def crear_usuario(username, rol, corredora=None, **campos):
    usuario = Usuario.objects.create_user(username, corredora=corredora, **campos)
    usuario.groups.add(Group.objects.get(name=rol))
    return usuario


def datos_formulario(**cambios):
    datos = {
        'mercado': Mercado.ACCIONES,
        'ejercicio': '2025',
        'codigo_instrumento': 'NUEVO',
        'secuencia_evento': '100000900',
        'fecha_pago': '2025-06-30',
        'numero_dividendo': '0',
        'descripcion': 'Calificación auditada',
        'valor_historico': '0',
        'factor_actualizacion': '0',
        'monto_8': '1000',
        'factor_8': '1',
    }
    datos.update(cambios)
    return datos


class RegistroAuditoriaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.corredora_a = Corredora.objects.create(rut='1-9', nombre='Corredora A')
        cls.corredora_b = Corredora.objects.create(rut='2-7', nombre='Corredora B')
        cls.analista_a = crear_usuario(
            'analista_a', 'Analista Tributario', corredora=cls.corredora_a,
        )
        cls.instrumento = Instrumento.objects.create(codigo='JEAP', mercado=Mercado.ACCIONES)

    def setUp(self):
        self.client.force_login(self.analista_a)

    def crear_local(self, corredora=None, descripcion='Original'):
        return CalificacionLocal.objects.create(
            corredora=corredora or self.corredora_a,
            instrumento=self.instrumento,
            ejercicio=2025,
            fecha_pago=date(2025, 1, 2),
            secuencia_evento=100000809,
            descripcion=descripcion,
        )

    def test_creacion_registra_evento(self):
        respuesta = self.client.post(reverse('calificaciones:ingresar'), datos_formulario())

        self.assertRedirects(respuesta, reverse('calificaciones:mantenedor'))
        calificacion = CalificacionLocal.objects.get(descripcion='Calificación auditada')
        evento = EventoAuditoria.objects.get()
        self.assertEqual(evento.accion, EventoAuditoria.Accion.CREAR)
        self.assertEqual(evento.usuario, self.analista_a)
        self.assertEqual(evento.usuario_nombre, 'analista_a')
        self.assertEqual(evento.corredora, self.corredora_a)
        self.assertEqual(evento.calificacion_id, calificacion.pk)
        self.assertIsNone(evento.estado_anterior)
        self.assertEqual(evento.estado_posterior['descripcion'], 'Calificación auditada')
        self.assertEqual(len(evento.estado_posterior['detalles']), len(CONCEPTOS))
        Usuario.objects.filter(pk=self.analista_a.pk).update(username='nombre_nuevo')
        evento.refresh_from_db()
        self.assertEqual(evento.usuario_nombre, 'analista_a')

    def test_modificacion_registra_estados_anterior_y_posterior(self):
        calificacion = self.crear_local()

        respuesta = self.client.post(
            reverse('calificaciones:modificar', args=[calificacion.pk]),
            datos_formulario(
                codigo_instrumento='JEAP',
                secuencia_evento=str(calificacion.secuencia_evento),
                descripcion='Modificada',
            ),
        )

        self.assertRedirects(respuesta, reverse('calificaciones:mantenedor'))
        evento = EventoAuditoria.objects.get()
        self.assertEqual(evento.accion, EventoAuditoria.Accion.MODIFICAR)
        self.assertEqual(evento.calificacion_id, calificacion.pk)
        self.assertEqual(evento.estado_anterior['descripcion'], 'Original')
        self.assertEqual(evento.estado_posterior['descripcion'], 'Modificada')

    def test_baja_registra_cambio_de_estado(self):
        calificacion = self.crear_local()

        respuesta = self.client.post(reverse('calificaciones:eliminar', args=[calificacion.pk]))

        self.assertRedirects(respuesta, reverse('calificaciones:mantenedor'))
        evento = EventoAuditoria.objects.get()
        self.assertEqual(evento.accion, EventoAuditoria.Accion.BAJA)
        self.assertTrue(evento.estado_anterior['activa'])
        self.assertFalse(evento.estado_posterior['activa'])
        calificacion.refresh_from_db()
        self.assertFalse(calificacion.activa)

    def test_objeto_de_otra_corredora_no_genera_evento(self):
        ajena = self.crear_local(corredora=self.corredora_b, descripcion='Ajena')

        respuesta_modificar = self.client.post(
            reverse('calificaciones:modificar', args=[ajena.pk]),
            datos_formulario(),
        )
        respuesta_baja = self.client.post(reverse('calificaciones:eliminar', args=[ajena.pk]))

        self.assertEqual(respuesta_modificar.status_code, 404)
        self.assertEqual(respuesta_baja.status_code, 404)
        self.assertFalse(EventoAuditoria.objects.exists())
        ajena.refresh_from_db()
        self.assertTrue(ajena.activa)
        self.assertEqual(ajena.descripcion, 'Ajena')

    def test_fallo_de_auditoria_revierte_creacion(self):
        with mock.patch(
            'calificaciones.views.EventoAuditoria.objects.create',
            side_effect=RuntimeError('fallo simulado'),
        ):
            with self.assertRaises(RuntimeError):
                self.client.post(reverse('calificaciones:ingresar'), datos_formulario())

        self.assertFalse(CalificacionLocal.objects.filter(descripcion='Calificación auditada').exists())
        self.assertFalse(EventoAuditoria.objects.exists())

    def test_fallo_de_auditoria_revierte_baja(self):
        calificacion = self.crear_local()
        with mock.patch(
            'calificaciones.views.EventoAuditoria.objects.create',
            side_effect=RuntimeError('fallo simulado'),
        ):
            with self.assertRaises(RuntimeError):
                self.client.post(reverse('calificaciones:eliminar', args=[calificacion.pk]))

        calificacion.refresh_from_db()
        self.assertTrue(calificacion.activa)
        self.assertFalse(EventoAuditoria.objects.exists())


class AccesoAuditoriaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.corredora = Corredora.objects.create(rut='1-9', nombre='Corredora A')
        cls.auditor = crear_usuario('auditor', 'Auditor')
        cls.usuarios_sin_acceso = [
            crear_usuario('corredor', 'Corredor', corredora=cls.corredora),
            crear_usuario('analista', 'Analista Tributario', corredora=cls.corredora),
            crear_usuario('administrador', 'Administrador', is_staff=True),
        ]

    def test_auditor_puede_consultar(self):
        self.client.force_login(self.auditor)

        respuesta = self.client.get(reverse('auditoria:listado'))

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, 'Eventos de auditoría')
        self.assertEqual(self.client.post(reverse('auditoria:listado')).status_code, 405)

    def test_otros_roles_reciben_403(self):
        for usuario in self.usuarios_sin_acceso:
            with self.subTest(rol=usuario.groups.get().name):
                self.client.force_login(usuario)
                respuesta = self.client.get(reverse('auditoria:listado'))
                self.assertEqual(respuesta.status_code, 403)

