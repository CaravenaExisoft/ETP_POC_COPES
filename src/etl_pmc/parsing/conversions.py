"""Conversion tipada de texto crudo de ancho fijo.

Cada funcion es pura: recibe el texto ya extraido (ver FieldSpec.extract_raw)
y devuelve (valor_o_none, es_valido). Nunca lanza excepcion por un dato de
negocio invalido -- eso se resuelve en la capa de validacion, no aca. Los
importes usan exclusivamente Decimal (prompt seccion 6: nunca float).
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal, InvalidOperation

_DATE_RE = re.compile(r"^\d{8}$")
_INTEGER_RE = re.compile(r"^\d+$")


def convertir_fecha_yyyymmdd(raw: str) -> tuple[date | None, bool]:
    """yyyyMMdd estricto: 8 digitos y fecha de calendario real (rechaza p.ej.
    20260231). No admite separadores ni espacios."""
    if not _DATE_RE.match(raw):
        return None, False
    try:
        return date(int(raw[0:4]), int(raw[4:6]), int(raw[6:8])), True
    except ValueError:
        return None, False


def convertir_importe(raw: str, longitud_campo: int) -> tuple[Decimal | None, bool]:
    """Importe con coma decimal y 2 posiciones de centavos, sin separador de
    miles ni signo (patron observado empiricamente contra entrada_real_1000.txt,
    ver docs/matriz_equivalencia.md). El ancho de la parte entera se deriva de
    la longitud del campo (longitud - 3: coma + 2 decimales)."""
    digitos_enteros = longitud_campo - 3
    if digitos_enteros < 1:
        return None, False
    patron = re.compile(rf"^[0-9]{{{digitos_enteros}}},[0-9]{{2}}$")
    if not patron.match(raw):
        return None, False
    entero, decimales = raw.split(",")
    try:
        valor = Decimal(f"{entero}.{decimales}")
    except InvalidOperation:
        return None, False
    return valor, True


def convertir_entero(raw: str) -> tuple[int | None, bool]:
    if not _INTEGER_RE.match(raw):
        return None, False
    return int(raw), True


def convertir_texto(raw: str) -> tuple[str, bool]:
    return raw, True
