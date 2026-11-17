from decimal import Decimal

from django import forms

from .models import CONCEPTOS, CONCEPTOS_SUMA, CalificacionBase, CalificacionLocal, ConceptoTributario, Instrumento, Mercado


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


class CalificacionForm(forms.ModelForm):
    """Datos iniciales de una calificación local. La corredora nunca viene del formulario."""

    mercado = forms.ChoiceField(label='Mercado', choices=Mercado.choices)
    codigo_instrumento = forms.CharField(
        label='Instrumento',
        max_length=30,
        widget=forms.TextInput(attrs={'placeholder': 'Ej. JEAP o NO-INSCRITO-01'}),
    )

    class Meta:
        model = CalificacionLocal
        fields = [
            'mercado', 'ejercicio', 'codigo_instrumento', 'secuencia_evento', 'fecha_pago',
            'numero_dividendo', 'descripcion', 'valor_historico', 'factor_actualizacion', 'isfut',
        ]
        labels = {
            'ejercicio': 'Ejercicio comercial',
            'secuencia_evento': 'Secuencia del evento',
            'fecha_pago': 'Fecha de pago',
            'numero_dividendo': 'Número de dividendo',
            'descripcion': 'Descripción',
            'valor_historico': 'Valor histórico',
            'factor_actualizacion': 'Factor de actualización',
            'isfut': 'Indicador ISFUT',
        }
        widgets = {
            'fecha_pago': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
            'descripcion': forms.TextInput(attrs={'placeholder': 'Describe el evento tributario'}),
        }
        localized_fields = ['valor_historico', 'factor_actualizacion']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.initial['mercado'] = self.instance.instrumento.mercado
            self.initial['codigo_instrumento'] = self.instance.instrumento.codigo

    def clean_codigo_instrumento(self):
        return self.cleaned_data['codigo_instrumento'].strip().upper()

    def save(self, commit=True):
        calificacion = super().save(commit=False)
        # Si el instrumento no existe, se crea como no inscrito (no viene de Bolsa).
        calificacion.instrumento, _ = Instrumento.objects.get_or_create(
            codigo=self.cleaned_data['codigo_instrumento'],
            mercado=self.cleaned_data['mercado'],
            defaults={'inscrito': False},
        )
        # Si Bolsa informó el mismo evento, la calificación local la reemplaza en el listado.
        calificacion.base = CalificacionBase.objects.filter(
            instrumento=calificacion.instrumento,
            ejercicio=calificacion.ejercicio,
            secuencia_evento=calificacion.secuencia_evento,
        ).first()
        if commit:
            calificacion.save()
        return calificacion


class DetallesForm(forms.Form):
    """Monto y factor de cada concepto 8–37."""

    def __init__(self, *args, calificacion=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.conceptos = list(ConceptoTributario.objects.filter(numero__in=CONCEPTOS))
        actuales = {d.concepto_id: d for d in calificacion.detalles.all()} if calificacion else {}

        for concepto in self.conceptos:
            n = concepto.numero
            detalle = actuales.get(n)
            self.fields[f'monto_{n}'] = forms.DecimalField(
                label=f'Monto {n}', required=False, min_value=0, max_digits=15, decimal_places=2,
                localize=True, initial=detalle.monto if detalle else None,
            )
            self.fields[f'factor_{n}'] = forms.DecimalField(
                label=f'Factor {n}', required=False, min_value=0, max_value=1, max_digits=9, decimal_places=8,
                localize=True, initial=detalle.factor if detalle else None,
            )

    def filas(self):
        """(concepto, campo de monto, campo de factor, participa en la suma) para la plantilla."""
        for concepto in self.conceptos:
            n = concepto.numero
            yield concepto, self[f'monto_{n}'], self[f'factor_{n}'], n in CONCEPTOS_SUMA

    def save(self, calificacion):
        calificacion.detalles.all().delete()
        calificacion.detalles.bulk_create(
            calificacion.detalles.model(
                calificacion=calificacion,
                concepto=concepto,
                monto=self.cleaned_data[f'monto_{concepto.numero}'] or Decimal(0),
                factor=self.cleaned_data[f'factor_{concepto.numero}'] or Decimal(0),
            )
            for concepto in self.conceptos
        )
