from __future__ import annotations

from datetime import date

from etl_pmc.control.cabecera import (
    MOTIVO_CABECERA_AUSENTE,
    MOTIVO_CABECERA_DUPLICADA,
    MOTIVO_FECHA_CABECERA_INVALIDA,
    validar_cabeceras,
)
from etl_pmc.models import CabeceraConvertida, LineaCruda


def _cabecera(numero_linea: int, fecha: date | None, valida: bool) -> CabeceraConvertida:
    return CabeceraConvertida(
        linea=LineaCruda(archivo_origen="f.txt", numero_linea=numero_linea, contenido="1" + "0" * 87),
        fecha_cabecera_raw="20260921" if valida else "bad",
        fecha_cabecera=fecha,
        fecha_cabecera_valida=valida,
    )


def test_cabecera_unica_y_valida():
    resultado = validar_cabeceras([_cabecera(1, date(2026, 9, 21), True)])
    assert resultado.valida is True
    assert resultado.motivos == ()


def test_cabecera_ausente():
    resultado = validar_cabeceras([])
    assert resultado.valida is False
    assert MOTIVO_CABECERA_AUSENTE in resultado.motivos


def test_cabecera_duplicada():
    resultado = validar_cabeceras(
        [_cabecera(1, date(2026, 9, 21), True), _cabecera(50, date(2026, 9, 21), True)]
    )
    assert resultado.valida is False
    assert MOTIVO_CABECERA_DUPLICADA in resultado.motivos


def test_fecha_cabecera_invalida():
    resultado = validar_cabeceras([_cabecera(1, None, False)])
    assert resultado.valida is False
    assert MOTIVO_FECHA_CABECERA_INVALIDA in resultado.motivos
