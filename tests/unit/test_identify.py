from __future__ import annotations

from etl_pmc.models import LineaCruda, TipoRegistro
from etl_pmc.parsing.identify import identificar_tipo


def _linea(contenido: str) -> LineaCruda:
    return LineaCruda(archivo_origen="test.txt", numero_linea=1, contenido=contenido)


def test_identifica_cabecera(poc_pmc_layout):
    contenido = "1" + "0" * 87
    assert identificar_tipo(_linea(contenido), poc_pmc_layout) == TipoRegistro.CABECERA


def test_identifica_detalle(poc_pmc_layout):
    contenido = "2" + "0" * 712
    assert identificar_tipo(_linea(contenido), poc_pmc_layout) == TipoRegistro.DETALLE


def test_identifica_pie(poc_pmc_layout):
    contenido = "3" + "0" * 23
    assert identificar_tipo(_linea(contenido), poc_pmc_layout) == TipoRegistro.PIE


def test_tipo_correcto_pero_longitud_incorrecta_es_invalido(poc_pmc_layout):
    # tipo '1' (cabecera) con 87 en vez de 88 caracteres
    contenido = "1" + "0" * 86
    assert identificar_tipo(_linea(contenido), poc_pmc_layout) == TipoRegistro.INVALIDO


def test_tipo_desconocido_es_invalido(poc_pmc_layout):
    contenido = "9" + "0" * 87
    assert identificar_tipo(_linea(contenido), poc_pmc_layout) == TipoRegistro.INVALIDO


def test_linea_vacia_es_invalida(poc_pmc_layout):
    assert identificar_tipo(_linea(""), poc_pmc_layout) == TipoRegistro.INVALIDO


def test_longitud_limite_exacta_713_vs_712_vs_714(poc_pmc_layout):
    assert identificar_tipo(_linea("2" + "0" * 711), poc_pmc_layout) == TipoRegistro.INVALIDO
    assert identificar_tipo(_linea("2" + "0" * 712), poc_pmc_layout) == TipoRegistro.DETALLE
    assert identificar_tipo(_linea("2" + "0" * 713), poc_pmc_layout) == TipoRegistro.INVALIDO
