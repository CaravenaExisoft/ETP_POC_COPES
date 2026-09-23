"""Adaptador de Azure Blob Storage. Identidad administrada en el Job,
DefaultAzureCredential para desarrollo local (prompt seccion 12: sin secretos
en codigo/imagen/manifiesto/logs). La lectura es streaming real (no
descarga el blob completo a memoria antes de procesarlo, prompt seccion 11).
"""

from __future__ import annotations

import io
import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import BinaryIO

from azure.core.exceptions import ResourceNotFoundError
from azure.storage.blob import BlobServiceClient

from etl_pmc.storage.base import StorageAdapter

_CHUNK_SIZE = 4 * 1024 * 1024  # 4 MiB, acotado independientemente del tamaño del blob
_COPY_POLL_INTERVAL_SECONDS = 1.0
_COPY_TIMEOUT_SECONDS = 300.0


class _BlobReadStream(io.RawIOBase):
    """Envuelve el downloader de azure-storage-blob como BinaryIO estandar,
    consumiendo el blob en chunks acotados en vez de con .readall()."""

    def __init__(self, downloader) -> None:
        self._chunks: Iterator[bytes] = downloader.chunks()
        self._buffer = b""
        self._agotado = False

    def readable(self) -> bool:
        return True

    def readinto(self, b) -> int:  # type: ignore[override]
        while len(self._buffer) < len(b) and not self._agotado:
            try:
                self._buffer += next(self._chunks)
            except StopIteration:
                self._agotado = True
                break
        n = min(len(b), len(self._buffer))
        b[:n] = self._buffer[:n]
        self._buffer = self._buffer[n:]
        return n


class AzureBlobStorageAdapter(StorageAdapter):
    def __init__(self, service_client: BlobServiceClient) -> None:
        self._client = service_client

    @classmethod
    def desde_url_con_identidad_administrada(cls, storage_account_url: str) -> "AzureBlobStorageAdapter":
        from azure.identity import DefaultAzureCredential

        credential = DefaultAzureCredential()
        return cls(BlobServiceClient(account_url=storage_account_url, credential=credential))

    def _blob_client(self, container: str, blob: str):
        return self._client.get_container_client(container).get_blob_client(blob)

    def existe(self, container: str, blob: str) -> bool:
        return self._blob_client(container, blob).exists()

    @contextmanager
    def abrir_lectura(self, container: str, blob: str) -> Iterator[BinaryIO]:
        cliente = self._blob_client(container, blob)
        try:
            downloader = cliente.download_blob(max_concurrency=1)
        except ResourceNotFoundError as exc:
            raise FileNotFoundError(f"blob '{container}/{blob}' no existe") from exc
        stream = io.BufferedReader(_BlobReadStream(downloader), buffer_size=_CHUNK_SIZE)
        try:
            yield stream
        finally:
            stream.close()

    def escribir_bytes(self, container: str, blob: str, contenido: bytes) -> None:
        """Escribe a un blob temporal y publica via copia server-side,
        esperando su exito antes de considerar el commit hecho (prompt
        seccion 13: no asumir que copy+delete es un rename atomico)."""
        contenedor = self._client.get_container_client(container)
        blob_temporal = f"{blob}.tmp-{int(time.time() * 1000)}"

        cliente_temporal = contenedor.get_blob_client(blob_temporal)
        cliente_temporal.upload_blob(contenido, overwrite=True)

        cliente_final = contenedor.get_blob_client(blob)
        copia = cliente_final.start_copy_from_url(cliente_temporal.url)

        deadline = time.monotonic() + _COPY_TIMEOUT_SECONDS
        estado = copia.get("copy_status")
        while estado == "pending":
            if time.monotonic() > deadline:
                cliente_temporal.delete_blob()
                raise TimeoutError(f"la copia de '{blob_temporal}' a '{blob}' no termino en {_COPY_TIMEOUT_SECONDS}s")
            time.sleep(_COPY_POLL_INTERVAL_SECONDS)
            propiedades = cliente_final.get_blob_properties()
            estado = propiedades.copy.status

        cliente_temporal.delete_blob()

        if estado != "success":
            raise RuntimeError(f"la copia de '{blob_temporal}' a '{blob}' termino con estado '{estado}', no 'success'")
