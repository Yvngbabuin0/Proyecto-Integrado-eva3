from django import forms

from cuentas.models import Corredora

from .models import EventoAuditoria


class FiltroEventosForm(forms.Form):
    fecha = forms.DateField(label='Fecha', required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    accion = forms.ChoiceField(label='Acción', required=False, choices=[('', 'Todas'), *EventoAuditoria.Accion.choices])
    resultado = forms.ChoiceField(
        label='Resultado', required=False, choices=[('', 'Todos'), *EventoAuditoria.Resultado.choices],
    )
    corredora = forms.ModelChoiceField(
        label='Corredora', required=False, queryset=Corredora.objects.all(), empty_label='Todas',
    )

    def __init__(self, *args, **kwargs):
        ocultar_corredora = kwargs.pop('ocultar_corredora', False)
        super().__init__(*args, **kwargs)
        if ocultar_corredora:
            self.fields['corredora'].widget = forms.HiddenInput()
