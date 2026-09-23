"""Test de regresion del layout completo contra el unico archivo real
disponible (docs/matriz_equivalencia.md seccion 1): sin export ADF, la mejor
evidencia de que las posiciones inferidas del layout son correctas es que el
control de totales independiente (suma de importe_principal de los 1000
detalles vs. el total declarado en el pie) cierra exactamente.

Si este test empieza a fallar tras tocar el layout o los conversores, es una
señal fuerte de que se rompio algo real, no solo un detalle de test.
"""

from __future__ import annotations

from decimal import Decimal

from etl_pmc.models import TipoRegistro
from etl_pmc.parsing.detalle import parsear_detalle
from etl_pmc.parsing.identify import identificar_tipo
from etl_pmc.parsing.pie import parsear_pie
from etl_pmc.parsing.reader import leer_lineas


def test_control_de_totales_cierra_contra_archivo_real(poc_pmc_layout, real_sample_path):
    detalles_validos = 0
    detalles_importe_invalido = 0
    suma_importe_principal = Decimal("0")
    pies_encontrados = 0
    pie_convertido = None

    with real_sample_path.open("rb") as fh:
        for linea in leer_lineas(fh, real_sample_path.name):
            tipo = identificar_tipo(linea, poc_pmc_layout)
            if tipo == TipoRegistro.DETALLE:
                detalle = parsear_detalle(linea, poc_pmc_layout)
                if detalle.importe_principal_valido:
                    detalles_validos += 1
                    suma_importe_principal += detalle.importe_principal
                else:
                    detalles_importe_invalido += 1
            elif tipo == TipoRegistro.PIE:
                pies_encontrados += 1
                pie_convertido = parsear_pie(linea, poc_pmc_layout)

    assert pies_encontrados == 1
    assert detalles_importe_invalido == 0
    assert detalles_validos == 1000
    assert pie_convertido is not None
    assert pie_convertido.cantidad_declarada_valida is True
    assert pie_convertido.cantidad_declarada == 1000
    assert pie_convertido.importe_total_declarado_valido is True
    assert suma_importe_principal == pie_convertido.importe_total_declarado


def test_archivo_real_tiene_una_cabecera_un_pie_y_1000_detalles(poc_pmc_layout, real_sample_path):
    conteo = {t: 0 for t in TipoRegistro}
    with real_sample_path.open("rb") as fh:
        for linea in leer_lineas(fh, real_sample_path.name):
            conteo[identificar_tipo(linea, poc_pmc_layout)] += 1

    assert conteo[TipoRegistro.CABECERA] == 1
    assert conteo[TipoRegistro.DETALLE] == 1000
    assert conteo[TipoRegistro.PIE] == 1
    assert conteo[TipoRegistro.INVALIDO] == 0
