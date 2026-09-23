from __future__ import annotations

from dataclasses import replace

from etl_pmc.models import LineaCruda
from etl_pmc.parsing.detalle import parsear_detalle
from etl_pmc.validation.detalle import (
    MOTIVO_FECHA_INVALIDA,
    MOTIVO_IDENTIFICACION_INVALIDA,
    MOTIVO_IMPORTE_INVALIDO,
    MOTIVO_MONEDA_INVALIDA,
    validar_detalle,
)


def _detalle_base() -> str:
    campos = {
        58: ("10855959", 8),
        103: ("843289651", 9),
        144: ("20260710", 8),
        168: ("ARS", 3),
        173: ("0000594310,07", 13),
        666: ("20261030", 8),
        674: ("0000594310,07", 13),
        687: ("20261113", 8),
        695: ("0000594310,07", 13),
    }
    linea = ["0"] * 713
    linea[0] = "2"
    for start, (valor, length) in campos.items():
        for i, ch in enumerate(valor):
            linea[start - 1 + i] = ch
    return "".join(linea)


def _validar(contenido: str, layout):
    linea = LineaCruda(archivo_origen="f.txt", numero_linea=2, contenido=contenido)
    return validar_detalle(parsear_detalle(linea, layout))


def test_detalle_realista_es_valido(poc_pmc_layout):
    resultado = _validar(_detalle_base(), poc_pmc_layout)
    assert resultado.detalle_valido is True
    assert resultado.motivos_rechazo == ()


def test_moneda_distinta_de_ars_es_invalida(poc_pmc_layout):
    contenido = list(_detalle_base())
    contenido[168 - 1 : 168 - 1 + 3] = list("USD")
    resultado = _validar("".join(contenido), poc_pmc_layout)
    assert resultado.moneda_valida is False
    assert resultado.detalle_valido is False
    assert MOTIVO_MONEDA_INVALIDA in resultado.motivos_rechazo


def test_id_deuda_con_letra_es_invalido(poc_pmc_layout):
    contenido = list(_detalle_base())
    contenido[103 - 1] = "A"
    resultado = _validar("".join(contenido), poc_pmc_layout)
    assert resultado.identificacion_valida is False
    assert MOTIVO_IDENTIFICACION_INVALIDA in resultado.motivos_rechazo


def test_importe_con_punto_decimal_es_invalido(poc_pmc_layout):
    contenido = list(_detalle_base())
    contenido[173 - 1 : 173 - 1 + 13] = list("0000594310.07")
    resultado = _validar("".join(contenido), poc_pmc_layout)
    assert resultado.importes_validos is False
    assert MOTIVO_IMPORTE_INVALIDO in resultado.motivos_rechazo


def test_fecha_invalida_de_calendario(poc_pmc_layout):
    contenido = list(_detalle_base())
    contenido[144 - 1 : 144 - 1 + 8] = list("20260231")  # 31 de febrero
    resultado = _validar("".join(contenido), poc_pmc_layout)
    assert resultado.fechas_validas is False
    assert MOTIVO_FECHA_INVALIDA in resultado.motivos_rechazo


def test_vencimientos_desordenados_no_rechazan_por_diseno(poc_pmc_layout):
    # Decision de POC (docs/matriz_equivalencia.md seccion 4): el prompt no
    # exige orden cronologico entre vencimientos, a diferencia del borrador
    # de ADF retirado. No se agrega una restriccion no pedida.
    contenido = list(_detalle_base())
    # tercer_vencimiento (687) antes que primer_vencimiento (144)
    contenido[687 - 1 : 687 - 1 + 8] = list("20200101")
    resultado = _validar("".join(contenido), poc_pmc_layout)
    assert resultado.fechas_validas is True
    assert resultado.detalle_valido is True


def test_referencia_cliente_con_menos_de_8_digitos_por_espacio_es_invalida(poc_pmc_layout):
    contenido = list(_detalle_base())
    contenido[58 - 1 : 58 - 1 + 8] = list(" 1234567")
    resultado = _validar("".join(contenido), poc_pmc_layout)
    assert resultado.identificacion_valida is False
