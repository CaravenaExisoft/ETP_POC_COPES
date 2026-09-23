"""Adaptador de almacenamiento local (filesystem). Un 'container' es una
subcarpeta de la raiz configurada; un 'blob' es una ruta relativa dentro de
ese container. Usado para modo local y para toda la suite de tests sin
Azure (prompt seccion 11).
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import BinaryIO

from etl_pmc.storage.base import StorageAdapter

_SEGMENTO_INVALIDO_RE = re.compile(r"^\.\.?$")


def _validar_blob_relativo(blob: str) -> None:
    if os.path.isabs(blob):
        raise ValueError(f"blob '{blob}' no puede ser una ruta absoluta")
    partes = re.split(r"[\\/]", blob)
    if any(_SEGMENTO_INVALIDO_RE.match(p) for p in partes):
        raise ValueError(f"blob '{blob}' contiene un segmento de ruta invalido ('.' o '..')")


class LocalStorageAdapter(StorageAdapter):
    def __init__(self, root: Path) -> None:
        self._root = root

    def _path(self, container: str, blob: str) -> Path:
        _validar_blob_relativo(blob)
        return self._root / container / blob

    def existe(self, container: str, blob: str) -> bool:
        return self._path(container, blob).is_file()

    @contextmanager
    def abrir_lectura(self, container: str, blob: str) -> Iterator[BinaryIO]:
        path = self._path(container, blob)
        with path.open("rb") as fh:
            yield fh

    def escribir_bytes(self, container: str, blob: str, contenido: bytes) -> None:
        path = self._path(container, blob)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.parent / f".{path.name}.tmp-{os.getpid()}"
        tmp_path.write_bytes(contenido)
        os.replace(tmp_path, path)  # rename atomico dentro del mismo volumen
