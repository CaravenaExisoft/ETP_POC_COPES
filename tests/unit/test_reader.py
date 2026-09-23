from __future__ import annotations

import io

import pytest

from etl_pmc.parsing.reader import DecodificacionError, leer_lineas


def test_lee_lineas_crlf():
    data = b"AAA\r\nBBB\r\nCCC\r\n"
    lineas = list(leer_lineas(io.BytesIO(data), "f.txt"))
    assert [l.contenido for l in lineas] == ["AAA", "BBB", "CCC"]
    assert [l.numero_linea for l in lineas] == [1, 2, 3]


def test_lee_lineas_lf():
    data = b"AAA\nBBB\nCCC\n"
    lineas = list(leer_lineas(io.BytesIO(data), "f.txt"))
    assert [l.contenido for l in lineas] == ["AAA", "BBB", "CCC"]


def test_no_genera_linea_fantasma_al_final():
    data = b"AAA\r\nBBB\r\n"
    lineas = list(leer_lineas(io.BytesIO(data), "f.txt"))
    assert len(lineas) == 2


def test_ultima_linea_sin_terminador_se_conserva():
    data = b"AAA\r\nBBB"
    lineas = list(leer_lineas(io.BytesIO(data), "f.txt"))
    assert [l.contenido for l in lineas] == ["AAA", "BBB"]


def test_linea_vacia_intermedia_se_conserva_con_su_numero():
    data = b"AAA\r\n\r\nCCC\r\n"
    lineas = list(leer_lineas(io.BytesIO(data), "f.txt"))
    assert [(l.numero_linea, l.contenido) for l in lineas] == [(1, "AAA"), (2, ""), (3, "CCC")]


def test_bom_utf8_se_retira_por_defecto():
    data = "﻿AAA\r\nBBB\r\n".encode("utf-8")
    lineas = list(leer_lineas(io.BytesIO(data), "f.txt", encoding="utf-8"))
    assert lineas[0].contenido == "AAA"


def test_bom_rechazado_si_no_se_permite():
    data = "﻿AAA\r\n".encode("utf-8")
    with pytest.raises(DecodificacionError):
        list(leer_lineas(io.BytesIO(data), "f.txt", encoding="utf-8", permitir_bom=False))


def test_no_aplica_strip_al_contenido():
    data = b"AAA   \r\n   BBB\r\n"
    lineas = list(leer_lineas(io.BytesIO(data), "f.txt"))
    assert lineas[0].contenido == "AAA   "
    assert lineas[1].contenido == "   BBB"


def test_error_de_decodificacion_reporta_archivo_y_linea():
    data = b"AAA\r\n\xff\xfe\r\n"
    with pytest.raises(DecodificacionError) as exc_info:
        list(leer_lineas(io.BytesIO(data), "f.txt", encoding="utf-8"))
    assert exc_info.value.archivo_origen == "f.txt"
