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
        cls.corredor = crear_usuario('corredor', 'Corredor', corredora=cls.corredora)
        cls.analista = crear_usuario('analista', 'Analista Tributario', corredora=cls.corredora)
        cls.administrador = crear_usuario('administrador', 'Administrador', is_staff=True)

    def test_auditor_puede_consultar(self):
        self.client.force_login(self.auditor)

        respuesta = self.client.get(reverse('auditoria:listado'))

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, 'Eventos de auditoría')
        self.assertEqual(self.client.post(reverse('auditoria:listado')).status_code, 405)

    def test_corredor_y_analista_pueden_consultar_su_corredora(self):
        for usuario, rol in [(self.corredor, 'Corredor'), (self.analista, 'Analista Tributario')]:
            with self.subTest(rol=rol):
                self.client.force_login(usuario)
                respuesta = self.client.get(reverse('auditoria:listado'))
                self.assertEqual(respuesta.status_code, 200)
                self.assertContains(respuesta, 'Eventos de auditoría')

    def test_administrador_sin_corredora_recibe_403(self):
        self.client.force_login(self.administrador)
        respuesta = self.client.get(reverse('auditoria:listado'))
        self.assertEqual(respuesta.status_code, 403)



class ConsultaLegibleTests(TestCase):
    """El listado y el detalle muestran la información de forma legible."""

    @classmethod
    def setUpTestData(cls):
        cls.corredora_a = Corredora.objects.create(rut='1-9', nombre='Corredora A')
        cls.corredora_b = Corredora.objects.create(rut='2-7', nombre='Corredora B')
        cls.analista_a = crear_usuario('analista_a', 'Analista Tributario', corredora=cls.corredora_a)
        cls.analista_b = crear_usuario('analista_b', 'Analista Tributario', corredora=cls.corredora_b)
        cls.auditor = crear_usuario('auditor', 'Auditor')

    def operar(self, usuario, **cambios):
        self.client.force_login(usuario)
        self.client.post(reverse('calificaciones:ingresar'), datos_formulario(**cambios))
        return CalificacionLocal.objects.latest('pk')

    def test_listado_muestra_la_calificacion_y_no_el_estado_completo(self):
        self.operar(self.analista_a)
        self.client.force_login(self.auditor)
        respuesta = self.client.get(reverse('auditoria:listado'))
        self.assertContains(respuesta, 'NUEVO · evento 100000900')
        self.assertContains(respuesta, 'Creación')
        self.assertNotContains(respuesta, 'concepto_id')

    def test_filtros_por_accion_y_corredora(self):
        calificacion = self.operar(self.analista_a)
        self.client.post(reverse('calificaciones:eliminar', args=[calificacion.pk]))
        self.operar(self.analista_b, codigo_instrumento='OTRO')
        self.client.force_login(self.auditor)

        por_accion = self.client.get(reverse('auditoria:listado'), {'accion': 'BAJA'})
        self.assertEqual(por_accion.context['pagina'].paginator.count, 1)

        por_corredora = self.client.get(reverse('auditoria:listado'), {'corredora': self.corredora_b.pk})
        self.assertEqual(por_corredora.context['pagina'].paginator.count, 1)
        self.assertContains(por_corredora, 'OTRO · evento 100000900')

    def test_detalle_de_modificacion_muestra_solo_lo_que_cambio(self):
        calificacion = self.operar(self.analista_a)
        self.client.post(
            reverse('calificaciones:modificar', args=[calificacion.pk]),
            datos_formulario(descripcion='Descripción nueva', factor_8='0,5'),
        )
        evento = EventoAuditoria.objects.get(accion=EventoAuditoria.Accion.MODIFICAR)
        self.client.force_login(self.auditor)
        respuesta = self.client.get(reverse('auditoria:detalle', args=[evento.pk]))

        self.assertEqual(
            [campo for campo, _, _ in respuesta.context['cambios']],
            ['Descripción', 'Factor 8'],
        )
        self.assertContains(respuesta, 'Calificación auditada')
        self.assertContains(respuesta, 'Descripción nueva')
        self.assertContains(respuesta, '0,50000000')

    def test_detalle_de_baja_muestra_el_cambio_de_estado(self):
        calificacion = self.operar(self.analista_a)
        self.client.post(reverse('calificaciones:eliminar', args=[calificacion.pk]))
        evento = EventoAuditoria.objects.get(accion=EventoAuditoria.Accion.BAJA)
        self.client.force_login(self.auditor)
        respuesta = self.client.get(reverse('auditoria:detalle', args=[evento.pk]))
        self.assertEqual(respuesta.context['cambios'], [('Activa', 'Sí', 'No')])

    def test_detalle_solo_para_quien_puede_ver_la_auditoria(self):
        self.operar(self.analista_a)
        evento = EventoAuditoria.objects.get()
        # Analista Tributario can now access their own corredora's events
        self.client.force_login(self.analista_a)
        respuesta = self.client.get(reverse('auditoria:detalle', args=[evento.pk]))
        self.assertEqual(respuesta.status_code, 200)

        # But Auditor should also be able to see it
        self.client.force_login(self.auditor)
        respuesta = self.client.get(reverse('auditoria:detalle', args=[evento.pk]))
        self.assertEqual(respuesta.status_code, 200)

        # Other users without the permission get 403
        sin_permiso = Usuario.objects.create_user('sin_permiso', corredora=self.corredora_a)
        # Don't add any group
        self.client.force_login(sin_permiso)
        respuesta = self.client.get(reverse('auditoria:detalle', args=[evento.pk]))
        self.assertEqual(respuesta.status_code, 403)


class FiltradoPorCorredoraTests(TestCase):
    """Corredor y Analista solo ven eventos de su propia corredora."""

    @classmethod
    def setUpTestData(cls):
        cls.corredora_a = Corredora.objects.create(rut='1-9', nombre='Corredora A')
        cls.corredora_b = Corredora.objects.create(rut='2-7', nombre='Corredora B')
        cls.analista_a = crear_usuario('analista_a', 'Analista Tributario', corredora=cls.corredora_a)
        cls.analista_b = crear_usuario('analista_b', 'Analista Tributario', corredora=cls.corredora_b)
        cls.corredor_a = crear_usuario('corredor_a', 'Corredor', corredora=cls.corredora_a)
        cls.auditor = crear_usuario('auditor', 'Auditor')
        cls.instrumento = Instrumento.objects.create(codigo='JEAP', mercado=Mercado.ACCIONES)

    def _crear_evento(self, usuario, corredora, descripcion):
        self.client.force_login(usuario)
        respuesta = self.client.post(reverse('calificaciones:ingresar'), datos_formulario(
            codigo_instrumento='JEAP',
            secuencia_evento='100000900',
            descripcion=descripcion,
        ))
        calificacion = CalificacionLocal.objects.get(descripcion=descripcion)
        return EventoAuditoria.objects.get(calificacion_id=calificacion.pk, accion=EventoAuditoria.Accion.CREAR)

    def test_corredor_y_analista_ven_solo_sus_eventos_en_listado(self):
        evento_a = self._crear_evento(self.analista_a, self.corredora_a, 'Evento A')
        evento_b = self._crear_evento(self.analista_b, self.corredora_b, 'Evento B')

        for usuario, rol in [(self.analista_a, 'Analista Tributario'), (self.corredor_a, 'Corredor')]:
            with self.subTest(rol=rol):
                self.client.force_login(usuario)
                respuesta = self.client.get(reverse('auditoria:listado'))
                self.assertEqual(respuesta.status_code, 200)
                # The entity shown is "JEAP · evento 100000900" (instrumento + sequence)
                self.assertContains(respuesta, 'JEAP · evento 100000900')
                self.assertEqual(respuesta.context['pagina'].paginator.count, 1)
                # Even if they try to filter by corredora B, they should only see their own
                respuesta_filtro = self.client.get(reverse('auditoria:listado'), {'corredora': self.corredora_b.pk})
                self.assertEqual(respuesta_filtro.context['pagina'].paginator.count, 0)

    def test_corredor_y_analista_reciben_404_en_detalle_de_otra_corredora(self):
        evento_a = self._crear_evento(self.analista_a, self.corredora_a, 'Evento A')
        evento_b = self._crear_evento(self.analista_b, self.corredora_b, 'Evento B')

        for usuario, rol in [(self.analista_a, 'Analista Tributario'), (self.corredor_a, 'Corredor')]:
            with self.subTest(rol=rol):
                self.client.force_login(usuario)
                respuesta = self.client.get(reverse('auditoria:detalle', args=[evento_b.pk]))
                self.assertEqual(respuesta.status_code, 404)

    def test_auditor_ve_todas_las_corredoras(self):
        evento_a = self._crear_evento(self.analista_a, self.corredora_a, 'Evento A')
        evento_b = self._crear_evento(self.analista_b, self.corredora_b, 'Evento B')

        self.client.force_login(self.auditor)
        respuesta = self.client.get(reverse('auditoria:listado'))
        self.assertEqual(respuesta.status_code, 200)
        # Entities are shown as "JEAP · evento 100000900"
        self.assertContains(respuesta, 'JEAP · evento 100000900')
        self.assertEqual(respuesta.context['pagina'].paginator.count, 2)

        # Auditor can filter by corredora
        por_corredora = self.client.get(reverse('auditoria:listado'), {'corredora': self.corredora_b.pk})
        self.assertEqual(por_corredora.context['pagina'].paginator.count, 1)
        self.assertContains(por_corredora, 'JEAP · evento 100000900')

        # Auditor can access any detail
        self.assertEqual(self.client.get(reverse('auditoria:detalle', args=[evento_a.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse('auditoria:detalle', args=[evento_b.pk])).status_code, 200)

    def test_filtro_corredora_oculto_para_usuarios_con_corredora(self):
        self.client.force_login(self.analista_a)
        respuesta = self.client.get(reverse('auditoria:listado'))
        # The form should have corredora as hidden input
        self.assertIn('corredora', respuesta.context['filtro'].fields)
        field = respuesta.context['filtro'].fields['corredora']
        from django import forms
        self.assertIsInstance(field.widget, forms.HiddenInput)

    def test_corredor_o_analista_sin_corredora_asignada_reciben_403(self):
        evento = self._crear_evento(self.analista_a, self.corredora_a, 'Evento A')
        for rol in ('Corredor', 'Analista Tributario'):
            with self.subTest(rol=rol):
                self.client.force_login(crear_usuario(f'sin_corredora_{rol}', rol))
                self.assertEqual(self.client.get(reverse('auditoria:listado')).status_code, 403)
                self.assertEqual(self.client.get(reverse('auditoria:detalle', args=[evento.pk])).status_code, 403)

    def test_solo_el_auditor_tiene_el_permiso_global(self):
        self.assertTrue(self.auditor.has_perm('auditoria.ver_todas_las_corredoras'))
        for usuario in (self.analista_a, self.corredor_a):
            with self.subTest(usuario=usuario.username):
                self.assertFalse(usuario.has_perm('auditoria.ver_todas_las_corredoras'))

    def test_auditor_ve_el_filtro_de_corredora(self):
        self.client.force_login(self.auditor)
        respuesta = self.client.get(reverse('auditoria:listado'))
        self.assertFalse(respuesta.context['filtro'].fields['corredora'].widget.is_hidden)
