"""Resultado de aplicacion (prompt seccion 13): estados propios, no codigos
de Azure. Exito tecnico del contenedor no debe ocultar un rechazo global del
lote -- por eso REJECTED/FAILED son estados de aplicacion explicitos, leidos
por ADF desde este JSON, no inferidos de un exit code."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum


class EstadoEjecucion(str, Enum):
    SUCCEEDED = "SUCCEEDED"
    SUCCEEDED_WITH_REJECTIONS = "SUCCEEDED_WITH_REJECTIONS"
    REJECTED = "REJECTED"
    FAILED = "FAILED"
    ALREADY_PROCESSED = "ALREADY_PROCESSED"


# Mapeo a codigo de salida del proceso (prompt seccion 13): fallos
# irrecuperables usan codigo no cero; un rechazo de negocio bien detectado y
# publicado como tal es exito tecnico del contenedor (codigo 0) aunque el
# lote no se haya publicado.
CODIGOS_SALIDA = {
    EstadoEjecucion.SUCCEEDED: 0,
    EstadoEjecucion.SUCCEEDED_WITH_REJECTIONS: 0,
    EstadoEjecucion.REJECTED: 0,
    EstadoEjecucion.ALREADY_PROCESSED: 0,
    EstadoEjecucion.FAILED: 1,
}


@dataclass
class ResultadoEjecucion:
    estado: EstadoEjecucion
    run_id: str
    pipeline_run_id: str
    lote_id: str
    version_codigo: str
    profile: str
    layout_version: int | None

    hash_entrada: str | None = None
    hash_enriquecimiento: str | None = None

    archivos_consumidos: list[str] = field(default_factory=list)
    archivos_producidos: list[str] = field(default_factory=list)

    cantidad_leida: int = 0
    cantidad_valida: int = 0
    # Solo se completan cuando enrichment.mode == "record_join" (simulacion
    # de cantidades, docs/matriz_equivalencia.md seccion 8.1); no afectan
    # cantidad_emitida.
    cantidad_enriquecimiento_coincidente: int = 0
    cantidad_enriquecimiento_sin_coincidencia: int = 0
    cantidad_rechazada: int = 0
    cantidad_excluida_negocio: int = 0
    cantidad_emitida: int = 0

    importe_total_declarado: Decimal | None = None
    importe_total_calculado: Decimal | None = None
    importe_total_salida: Decimal | None = None

    control_cabecera_valido: bool | None = None
    control_archivo_valido: bool | None = None

    duraciones_segundos: dict[str, float] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    ruta_errores: str | None = None
    motivos_rechazo_globales: tuple[str, ...] = field(default_factory=tuple)

    def codigo_salida(self) -> int:
        return CODIGOS_SALIDA[self.estado]

    def to_dict(self) -> dict:
        def _dec(v: Decimal | None) -> str | None:
            return None if v is None else str(v)

        return {
            "estado": self.estado.value,
            "run_id": self.run_id,
            "pipeline_run_id": self.pipeline_run_id,
            "lote_id": self.lote_id,
            "version_codigo": self.version_codigo,
            "profile": self.profile,
            "layout_version": self.layout_version,
            "hash_entrada": self.hash_entrada,
            "hash_enriquecimiento": self.hash_enriquecimiento,
            "archivos_consumidos": self.archivos_consumidos,
            "archivos_producidos": self.archivos_producidos,
            "cantidad_leida": self.cantidad_leida,
            "cantidad_valida": self.cantidad_valida,
            "cantidad_enriquecimiento_coincidente": self.cantidad_enriquecimiento_coincidente,
            "cantidad_enriquecimiento_sin_coincidencia": self.cantidad_enriquecimiento_sin_coincidencia,
            "cantidad_rechazada": self.cantidad_rechazada,
            "cantidad_excluida_negocio": self.cantidad_excluida_negocio,
            "cantidad_emitida": self.cantidad_emitida,
            "importe_total_declarado": _dec(self.importe_total_declarado),
            "importe_total_calculado": _dec(self.importe_total_calculado),
            "importe_total_salida": _dec(self.importe_total_salida),
            "control_cabecera_valido": self.control_cabecera_valido,
            "control_archivo_valido": self.control_archivo_valido,
            "duraciones_segundos": self.duraciones_segundos,
            "warnings": self.warnings,
            "ruta_errores": self.ruta_errores,
            "motivos_rechazo_globales": list(self.motivos_rechazo_globales),
        }

    def to_json(self) -> bytes:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False).encode("utf-8")
