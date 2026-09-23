"""Lectura incremental (streaming) del TXT de ancho fijo.

Prompt seccion 5 y 11: lectura por streaming, sin cargar el archivo completo
en memoria; conservar numero de linea y archivo origen; retirar unicamente el
terminador de linea (nunca strip() del contenido completo, los espacios
finales son parte del ancho fijo); politica explicita de BOM, lineas vacias,
CRLF/LF y errores de decodificacion.
"""

from __future__ import annotations

import io
from collections.abc import Iterator
from typing import BinaryIO

from etl_pmc.models import LineaCruda

_CHUNK_SIZE = 1 << 16


class DecodificacionError(Exception):
    def __init__(self, archivo_origen: str, numero_linea: int, encoding: str, causa: str) -> None:
        super().__init__(f"{archivo_origen}:{numero_linea}: error decodificando como {encoding}: {causa}")
        self.archivo_origen = archivo_origen
        self.numero_linea = numero_linea


def leer_lineas(
    binary_stream: BinaryIO,
    archivo_origen: str,
    encoding: str = "utf-8",
    *,
    permitir_bom: bool = True,
) -> Iterator[LineaCruda]:
    """Genera LineaCruda una por una a partir de un stream binario.

    - BOM UTF-8 inicial: se retira antes de la primera linea si permitir_bom es
      True; si es False, un BOM presente se reporta como DecodificacionError en
      la linea 1 (es un problema del archivo, no algo a adivinar).
    - CRLF y LF se aceptan indistintamente; se retira exactamente el
      terminador encontrado.
    - Una linea de longitud 0 (tras retirar terminador) se entrega igual, con
      su numero de linea -- la clasificacion de tipo (parsing.identify) la
      marcara invalida por no matchear ningun tipo/longitud declarado; no se
      descarta en silencio.
    - Un archivo que termina exactamente en un terminador de linea no genera
      una linea final vacia fantasma.
    """
    reader = io.TextIOWrapper(binary_stream, encoding=encoding, newline="", errors="strict")
    numero_linea = 0
    buffer = ""
    bom_verificado = False

    try:
        while True:
            chunk = reader.read(_CHUNK_SIZE)
            if not chunk:
                break
            if not bom_verificado:
                bom_verificado = True
                if chunk.startswith("﻿"):
                    if not permitir_bom:
                        raise DecodificacionError(
                            archivo_origen, 1, encoding, "BOM UTF-8 presente pero no permitido por configuracion"
                        )
                    chunk = chunk[1:]
            buffer += chunk
            while True:
                idx_lf = buffer.find("\n")
                if idx_lf == -1:
                    break
                if idx_lf > 0 and buffer[idx_lf - 1] == "\r":
                    contenido = buffer[: idx_lf - 1]
                else:
                    contenido = buffer[:idx_lf]
                buffer = buffer[idx_lf + 1 :]
                numero_linea += 1
                yield LineaCruda(archivo_origen=archivo_origen, numero_linea=numero_linea, contenido=contenido)
    except UnicodeDecodeError as exc:
        raise DecodificacionError(archivo_origen, numero_linea + 1, encoding, str(exc)) from exc

    if buffer:
        # Ultima linea sin terminador final. Puede o no ser una condicion de
        # error segun format.final_newline del manifiesto; esa decision se
        # toma en la capa de pipeline, no aca.
        numero_linea += 1
        yield LineaCruda(archivo_origen=archivo_origen, numero_linea=numero_linea, contenido=buffer)
