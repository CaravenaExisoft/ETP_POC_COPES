"""Modelos tipados. Separan explicitamente tres etapas (prompt seccion 5/11):
dato bruto (linea completa) -> extraccion de campo (texto crudo por campo) ->
conversion tipada (Decimal/date/int) -> validacion de negocio (flags + motivos).

Los identificadores (id_deuda, referencia_cliente) se conservan como texto en
todas las etapas para no perder ceros a la izquierda.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import Enum


class TipoRegistro(str, Enum):
    CABECERA = "cabecera"
    DETALLE = "detalle"
    PIE = "pie"
    INVALIDO = "invalido"


@dataclass(frozen=True)
class LineaCruda:
    """Una linea leida del archivo, antes de cualquier interpretacion."""

    archivo_origen: str
    numero_linea: int  # 1-based
    contenido: str  # terminador de linea ya retirado; strip() NO aplicado


# --- Cabecera -----------------------------------------------------------


@dataclass(frozen=True)
class CabeceraCruda:
    linea: LineaCruda
    fecha_cabecera_raw: str


@dataclass(frozen=True)
class CabeceraConvertida:
    linea: LineaCruda
    fecha_cabecera_raw: str
    fecha_cabecera: date | None
    fecha_cabecera_valida: bool


# --- Detalle --------------------------------------------------------------


@dataclass(frozen=True)
class DetalleCrudo:
    linea: LineaCruda
    referencia_cliente_raw: str
    id_deuda_raw: str
    primer_vencimiento_raw: str
    moneda_raw: str
    importe_principal_raw: str
    nombre_entidad_raw: str
    concepto_raw: str
    segundo_vencimiento_raw: str
    importe_segundo_vencimiento_raw: str
    tercer_vencimiento_raw: str
    importe_tercer_vencimiento_raw: str
    # INVENTADO a pedido del usuario (sin base documental ni empirica, ver
    # docs/matriz_equivalencia.md seccion 9.1): default "" para no romper
    # construcciones existentes que no lo pasan.
    fecha_emision_deuda_sintetica_raw: str = ""


@dataclass(frozen=True)
class DetalleConvertido:
    crudo: DetalleCrudo

    referencia_cliente: str  # texto, conserva ceros a la izquierda
    id_deuda: str

    primer_vencimiento: date | None
    primer_vencimiento_valido: bool

    moneda: str

    importe_principal: Decimal | None
    importe_principal_valido: bool

    nombre_entidad: str
    concepto: str

    segundo_vencimiento: date | None
    segundo_vencimiento_valido: bool
    importe_segundo_vencimiento: Decimal | None
    importe_segundo_vencimiento_valido: bool

    tercer_vencimiento: date | None
    tercer_vencimiento_valido: bool
    importe_tercer_vencimiento: Decimal | None
    importe_tercer_vencimiento_valido: bool

    # INVENTADO (ver DetalleCrudo.fecha_emision_deuda_sintetica_raw). Solo se
    # usa si AplicarFiltroAntiguedad esta activo en el manifiesto.
    fecha_emision_deuda_sintetica: date | None = None
    fecha_emision_deuda_sintetica_valida: bool = False

    @property
    def linea(self) -> LineaCruda:
        return self.crudo.linea


@dataclass(frozen=True)
class DetalleValidado:
    convertido: DetalleConvertido

    identificacion_valida: bool
    moneda_valida: bool
    importes_validos: bool
    fechas_validas: bool

    motivos_rechazo: tuple[str, ...] = field(default_factory=tuple)

    @property
    def detalle_valido(self) -> bool:
        return (
            self.identificacion_valida
            and self.moneda_valida
            and self.importes_validos
            and self.fechas_validas
        )

    @property
    def linea(self) -> LineaCruda:
        return self.convertido.linea


# --- Pie --------------------------------------------------------------------


@dataclass(frozen=True)
class PieCrudo:
    linea: LineaCruda
    cantidad_declarada_raw: str
    importe_total_declarado_raw: str


@dataclass(frozen=True)
class PieConvertido:
    linea: LineaCruda
    cantidad_declarada: int | None
    cantidad_declarada_valida: bool
    importe_total_declarado: Decimal | None
    importe_total_declarado_valido: bool


# --- Control global de archivo ----------------------------------------------


@dataclass(frozen=True)
class ControlArchivo:
    """Resultado del control de totales (prompt seccion 7, decision de
    poblacion documentada en docs/matriz_equivalencia.md seccion 6)."""

    archivo_origen: str

    cantidad_pies: int
    cantidad_calculada: int
    cantidad_declarada: int | None
    cantidad_importes_nulos: int
    importe_total_calculado: Decimal
    importe_total_declarado: Decimal | None

    totales_validos: bool
    motivos: tuple[str, ...] = field(default_factory=tuple)
