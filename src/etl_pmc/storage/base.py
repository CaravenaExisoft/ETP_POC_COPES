"""Interfaz comun de almacenamiento. El pipeline programa contra esta
abstraccion, nunca contra 'Path' o 'BlobClient' directamente, para poder
correr el mismo nucleo de negocio en modo local y en modo Azure (prompt
seccion 11: 'el nucleo debe poder probarse sin Azure')."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator
from contextlib import contextmanager
from typing import BinaryIO


class StorageAdapter(ABC):
    @abstractmethod
    def existe(self, container: str, blob: str) -> bool: ...

    @contextmanager
    @abstractmethod
    def abrir_lectura(self, container: str, blob: str) -> Iterator[BinaryIO]: ...

    @abstractmethod
    def escribir_bytes(self, container: str, blob: str, contenido: bytes) -> None:
        """Escribe contenido completo de forma atomica desde el punto de
        vista de un lector: nunca debe ser visible un archivo a medio
        escribir (prompt seccion 13)."""
