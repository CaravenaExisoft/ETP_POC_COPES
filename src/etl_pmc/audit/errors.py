"""Registro de errores en CSV con esquema explicito (prompt seccion 14):
run_id, archivo, numero_linea, categoria, codigo, campo, motivo. Nunca se
concatenan filas a mano; se usa el modulo csv estandar para escapado
correcto. Categorias: entrada, control_archivo, control_cabecera,
enriquecimiento, negocio, formato_salida.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass

CATEGORIA_ENTRADA = "entrada"
CATEGORIA_CONTROL_ARCHIVO = "control_archivo"
CATEGORIA_CONTROL_CABECERA = "control_cabecera"
CATEGORIA_ENRIQUECIMIENTO = "enriquecimiento"
CATEGORIA_NEGOCIO = "negocio"
CATEGORIA_FORMATO_SALIDA = "formato_salida"
CATEGORIA_FORMATO_SCHEMA_SINTETICO = "formato_schema_sintetico"

_COLUMNAS = ("run_id", "archivo", "numero_linea", "categoria", "codigo", "campo", "motivo")


@dataclass(frozen=True)
class FilaError:
    run_id: str
    archivo: str
    numero_linea: int | None
    categoria: str
    codigo: str
    campo: str
    motivo: str


def escribir_csv_errores(filas: list[FilaError]) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(_COLUMNAS)
    for f in filas:
        writer.writerow(
            [f.run_id, f.archivo, f.numero_linea if f.numero_linea is not None else "", f.categoria, f.codigo, f.campo, f.motivo]
        )
    return buffer.getvalue().encode("utf-8")
