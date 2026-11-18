from django import forms

from cuentas.models import Corredora

from .models import EventoAuditoria


class FiltroEventosForm(forms.Form):
    fecha = forms.DateField(label='Fecha', required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    accion = forms.ChoiceField(label='Acción', required=False, choices=[('', 'Todas'), *EventoAuditoria.Accion.choices])
    corredora = forms.ModelChoiceField(
        label='Corredora', required=False, queryset=Corredora.objects.all(), empty_label='Todas',
    )
