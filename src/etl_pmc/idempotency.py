"""Idempotencia basada en identidad/hash de entrada, hash del snapshot de
enriquecimiento, perfil, version de layout/config y parametros relevantes
(prompt seccion 13) -- nunca solo el nombre del TXT ni solo el run_id.

La marca de 'ya procesado' se guarda como un blob JSON en el destino de
audit; una segunda ejecucion con la misma clave de idempotencia no debe
sobrescribir una salida ya publicada ni anunciar exito mientras la primera
sigue en curso. Este modulo resuelve la clave y el chequeo; el bloqueo de
escrituras concurrentes (lease/condicional) es responsabilidad del adaptador
de storage al publicar.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass


def hash_bytes(contenido: bytes) -> str:
    return hashlib.sha256(contenido).hexdigest()


@dataclass(frozen=True)
class ClaveIdempotencia:
    hash_entrada: str
    hash_enriquecimiento: str
    profile: str
    layout_version: int
    parametros_relevantes: dict[str, object]

    def clave(self) -> str:
        payload = {
            "hash_entrada": self.hash_entrada,
            "hash_enriquecimiento": self.hash_enriquecimiento,
            "profile": self.profile,
            "layout_version": self.layout_version,
            "parametros_relevantes": self.parametros_relevantes,
        }
        canonico = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonico.encode("utf-8")).hexdigest()


def marca_ya_procesado(marca_existente: bytes | None, clave_actual: ClaveIdempotencia) -> bool:
    """True si el blob de marca existente corresponde exactamente a esta
    misma clave de idempotencia (misma entrada+snapshot+perfil+parametros)."""
    if marca_existente is None:
        return False
    try:
        data = json.loads(marca_existente)
    except json.JSONDecodeError:
        return False
    return data.get("clave_idempotencia") == clave_actual.clave()


def construir_marca(clave: ClaveIdempotencia, *, run_id: str) -> bytes:
    return json.dumps({"clave_idempotencia": clave.clave(), "run_id": run_id}, indent=2).encode("utf-8")
