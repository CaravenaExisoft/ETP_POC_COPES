from __future__ import annotations

from decimal import Decimal

from etl_pmc.parsing.conversions import (
    convertir_entero,
    convertir_fecha_yyyymmdd,
    convertir_importe,
    convertir_texto,
)


def test_fecha_valida():
    valor, valido = convertir_fecha_yyyymmdd("20260921")
    assert valido is True
    assert valor.isoformat() == "2026-09-21"


def test_fecha_invalida_calendario():
    # 31 de febrero no existe
    valor, valido = convertir_fecha_yyyymmdd("20260231")
    assert valido is False
    assert valor is None


def test_fecha_invalida_formato():
    valor, valido = convertir_fecha_yyyymmdd("2026-09-21")
    assert valido is False


def test_fecha_invalida_longitud():
    valor, valido = convertir_fecha_yyyymmdd("2026921")
    assert valido is False


def test_importe_valido_13_chars():
    valor, valido = convertir_importe("0000594310,07", 13)
    assert valido is True
    assert valor == Decimal("594310.07")


def test_importe_valido_15_chars():
    valor, valido = convertir_importe("000509483812,32", 15)
    assert valido is True
    assert valor == Decimal("509483812.32")


def test_importe_rechaza_punto_decimal():
    valor, valido = convertir_importe("0000594310.07", 13)
    assert valido is False


def test_importe_rechaza_separador_de_miles():
    valor, valido = convertir_importe("0.000.594,07", 13)
    assert valido is False


def test_importe_rechaza_signo():
    valor, valido = convertir_importe("-000594310,07", 13)
    assert valido is False


def test_entero_valido():
    valor, valido = convertir_entero("00001000")
    assert valido is True
    assert valor == 1000


def test_entero_rechaza_no_digitos():
    valor, valido = convertir_entero("0000a000")
    assert valido is False


def test_texto_no_transforma_espacios():
    valor, valido = convertir_texto("  abc  ")
    assert valido is True
    assert valor == "  abc  "
