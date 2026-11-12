from django import forms

from .models import Mercado


class FiltroForm(forms.Form):
    ORIGENES = [('', 'Todos'), ('corredora', 'Corredora'), ('bolsa', 'Bolsa / Sistema')]

    ejercicio = forms.TypedChoiceField(label='Ejercicio comercial', coerce=int, required=False, empty_value=None)
    mercado = forms.ChoiceField(label='Mercado', choices=[('', 'Todos'), *Mercado.choices], required=False)
    origen = forms.ChoiceField(label='Origen del dato', choices=ORIGENES, required=False)
    instrumento = forms.CharField(
        label='Instrumento',
        max_length=30,
        required=False,
        widget=forms.TextInput(attrs={'placeholder': 'Buscar por código'}),
    )

    def __init__(self, *args, ejercicios=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['ejercicio'].choices = [('', 'Todos'), *((e, e) for e in ejercicios)]
