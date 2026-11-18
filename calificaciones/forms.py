from decimal import Decimal

from django import forms

from .calculo import CONCEPTOS_CON_FORMULA, CONCEPTOS_FACTORES, SumaCeroError, factores_desde_montos
from .models import CONCEPTOS, CONCEPTOS_SUMA, CalificacionBase, CalificacionLocal, ConceptoTributario, Instrumento, Mercado


class CargaCSVForm(forms.Form):
    archivo = forms.FileField(label='Archivo CSV')

    def clean_archivo(self):
        archivo = self.cleaned_data['archivo']
        if not archivo.name.lower().endswith('.csv'):
            raise forms.ValidationError('Selecciona un archivo con extensión .csv.')
        return archivo


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
        # request.POST is immutable; make a mutable copy so rellenar_factores can modify it.
        self.data = self.data.copy()
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

    def factores(self):
        """Factores 8 a 37 del formulario, ya limpios, como Decimals.

        Incluye los 4 factores de ingreso directo (34 a 37) para que la
        validación de rango individual los cubra también.
        """
        return {n: self.cleaned_data.get(f'factor_{n}') or Decimal(0) for n in CONCEPTOS_FACTORES}

    def montos(self):
        """Montos 8 a 19 del formulario, ya limpios, como Decimals."""
        return {n: self.cleaned_data.get(f'monto_{n}') or Decimal(0) for n in CONCEPTOS_SUMA}

    def factores_calculados(self):
        """Factores 8 a 33 que se obtendrían de recalcular desde los montos."""
        return factores_desde_montos(self.montos())

    def factores_8_a_19(self):
        """Factores 8 a 19 del formulario, ya limpios, como Decimals."""
        return {n: self.cleaned_data.get(f'factor_{n}') or Decimal(0) for n in CONCEPTOS_SUMA}

    def factores_iguales_a_calculados(self):
        """True si los factores 8 a 33 del formulario son exactamente los calculados.

        Los factores 34 a 37 son de ingreso directo y no se calculan, así que no
        entran en la comparación. ``factores_calculados`` lanza
        :class:`SumaCeroError` cuando no hay montos, así que aquí se captura y se
        devuelve ``False`` (no hay factores calculados con los que comparar).
        """
        try:
            calculados = self.factores_calculados()
        except SumaCeroError:
            return False
        return {n: self.cleaned_data.get(f'factor_{n}') or Decimal(0) for n in CONCEPTOS_CON_FORMULA} == calculados

    def rellenar_factores(self, factores):
        """Rellena los factores 8 a 33 en el POST para que el formulario los muestre.

        Usa ``f'{valor:.8f}'`` porque ``str(Decimal('0E-8'))`` da ``'0E-8'``
        (notación científica) en lugar de ``'0.00000000'``.
        """
        for numero, valor in factores.items():
            self.data[f'factor_{numero}'] = f'{valor:.8f}'.replace('.', ',')

    def limpiar_factores(self):
        """Borra los factores 8 a 33 del POST, dejando solo los montos."""
        for numero in CONCEPTOS_CON_FORMULA:
            self.data.pop(f'factor_{numero}', None)

    def factores_mostrados(self):
        """Factores 8 a 33 que se están mostrando en pantalla (limpios o calculados)."""
        return {n: self.cleaned_data.get(f'factor_{n}') or Decimal(0) for n in CONCEPTOS_CON_FORMULA}

    def suma_mostrada(self):
        """Suma de los factores 8 a 19 que se están mostrando en pantalla."""
        return sum((self.factores_mostrados()[n] for n in CONCEPTOS_SUMA), Decimal(0))
