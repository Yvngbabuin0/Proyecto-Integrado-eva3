from django.contrib import admin

from .models import CalificacionBase, CalificacionLocal, ConceptoTributario, DetalleBase, DetalleLocal, Instrumento


@admin.register(Instrumento)
class InstrumentoAdmin(admin.ModelAdmin):
    list_display = ['codigo', 'mercado', 'inscrito']
    list_filter = ['mercado', 'inscrito']
    search_fields = ['codigo']


@admin.register(ConceptoTributario)
class ConceptoTributarioAdmin(admin.ModelAdmin):
    list_display = ['numero', 'nombre']


class DetalleBaseInline(admin.TabularInline):
    model = DetalleBase
    extra = 0


class DetalleLocalInline(admin.TabularInline):
    model = DetalleLocal
    extra = 0


@admin.register(CalificacionBase)
class CalificacionBaseAdmin(admin.ModelAdmin):
    list_display = ['instrumento', 'ejercicio', 'fecha_pago', 'secuencia_evento', 'descripcion']
    list_filter = ['ejercicio', 'instrumento__mercado']
    inlines = [DetalleBaseInline]


@admin.register(CalificacionLocal)
class CalificacionLocalAdmin(admin.ModelAdmin):
    list_display = ['instrumento', 'corredora', 'ejercicio', 'fecha_pago', 'secuencia_evento', 'activa']
    list_filter = ['corredora', 'ejercicio', 'activa', 'instrumento__mercado']
    inlines = [DetalleLocalInline]
