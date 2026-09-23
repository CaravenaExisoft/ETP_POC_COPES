"""Almacen temporal de Detalle en SQLite local (prompt seccion 11: orden
global y ranking que no entran en RAM se resuelven con una solucion acotada
como SQLite; centavos como enteros, nunca REAL; se preservan tipos/orden de
IDs). Primera pasada: se insertan todos los detalles leidos (validos e
invalidos, para no perder trazabilidad). Segunda pasada: se leen ordenados
por referencia_cliente/primer_vencimiento/id_deuda -- ese orden sirve a la
vez para el ranking de negocio y para el orden final de salida (prompt
seccion 10), sin cargar todos los detalles en memoria de Python.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

from etl_pmc.models import DetalleValidado

_DDL = """
CREATE TABLE detalle (
    numero_linea INTEGER PRIMARY KEY,
    referencia_cliente TEXT NOT NULL,
    id_deuda TEXT NOT NULL,
    primer_vencimiento TEXT,
    moneda TEXT,
    importe_principal_centavos INTEGER,
    nombre_entidad TEXT,
    concepto TEXT,
    segundo_vencimiento TEXT,
    importe_segundo_vencimiento_centavos INTEGER,
    tercer_vencimiento TEXT,
    importe_tercer_vencimiento_centavos INTEGER,
    fecha_emision_deuda_sintetica TEXT,
    detalle_valido INTEGER NOT NULL,
    motivos_rechazo TEXT NOT NULL
);
"""

_INDEX = """
CREATE INDEX idx_orden_autorizado
    ON detalle(referencia_cliente, primer_vencimiento, id_deuda, numero_linea)
    WHERE detalle_valido = 1;
"""


def _a_centavos(valor: Decimal | None) -> int | None:
    if valor is None:
        return None
    return int((valor * 100).quantize(Decimal("1")))


def _de_centavos(valor: int | None) -> Decimal | None:
    if valor is None:
        return None
    return Decimal(valor) / Decimal(100)


def _fecha_a_texto(valor: date | None) -> str | None:
    return valor.isoformat() if valor is not None else None


def _texto_a_fecha(valor: str | None) -> date | None:
    return date.fromisoformat(valor) if valor is not None else None


@dataclass(frozen=True)
class DetalleAutorizadoFila:
    numero_linea: int
    referencia_cliente: str
    id_deuda: str
    primer_vencimiento: date
    moneda: str
    importe_principal: Decimal
    nombre_entidad: str
    concepto: str
    segundo_vencimiento: date
    importe_segundo_vencimiento: Decimal
    tercer_vencimiento: date
    importe_tercer_vencimiento: Decimal
    # INVENTADO (ver etl_pmc.rules.pmc); None si no parseo como fecha valida.
    fecha_emision_deuda_sintetica: date | None


class AlmacenTemporalDetalle:
    """Envuelve una base SQLite de un solo archivo temporal por corrida."""

    def __init__(self, ruta_db: Path) -> None:
        self._conn = sqlite3.connect(ruta_db)
        self._conn.execute("PRAGMA journal_mode=OFF")
        self._conn.execute("PRAGMA synchronous=OFF")
        self._conn.execute(_DDL)

    def cerrar(self) -> None:
        self._conn.close()

    def __enter__(self) -> "AlmacenTemporalDetalle":
        return self

    def __exit__(self, *_exc) -> None:
        self.cerrar()

    def insertar(self, detalle: DetalleValidado) -> None:
        c = detalle.convertido
        self._conn.execute(
            """
            INSERT INTO detalle (
                numero_linea, referencia_cliente, id_deuda, primer_vencimiento, moneda,
                importe_principal_centavos, nombre_entidad, concepto,
                segundo_vencimiento, importe_segundo_vencimiento_centavos,
                tercer_vencimiento, importe_tercer_vencimiento_centavos,
                fecha_emision_deuda_sintetica,
                detalle_valido, motivos_rechazo
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                detalle.linea.numero_linea,
                c.referencia_cliente,
                c.id_deuda,
                _fecha_a_texto(c.primer_vencimiento),
                c.moneda,
                _a_centavos(c.importe_principal),
                c.nombre_entidad,
                c.concepto,
                _fecha_a_texto(c.segundo_vencimiento),
                _a_centavos(c.importe_segundo_vencimiento),
                _fecha_a_texto(c.tercer_vencimiento),
                _a_centavos(c.importe_tercer_vencimiento),
                _fecha_a_texto(c.fecha_emision_deuda_sintetica) if c.fecha_emision_deuda_sintetica_valida else None,
                1 if detalle.detalle_valido else 0,
                ",".join(detalle.motivos_rechazo),
            ),
        )

    def finalizar_carga(self) -> None:
        """Crea el indice recien despues de cargar todo: mas rapido que
        mantenerlo actualizado insercion a insercion."""
        self._conn.execute(_INDEX)
        self._conn.commit()

    def contar_detalles(self) -> int:
        (n,) = self._conn.execute("SELECT COUNT(*) FROM detalle").fetchone()
        return n

    def iterar_autorizados_ordenados(self) -> Iterator[DetalleAutorizadoFila]:
        """Detalles individualmente validos, en el orden requerido para
        ranking de negocio y para el archivo de salida (prompt seccion 10)."""
        cursor = self._conn.execute(
            """
            SELECT numero_linea, referencia_cliente, id_deuda, primer_vencimiento, moneda,
                   importe_principal_centavos, nombre_entidad, concepto,
                   segundo_vencimiento, importe_segundo_vencimiento_centavos,
                   tercer_vencimiento, importe_tercer_vencimiento_centavos,
                   fecha_emision_deuda_sintetica
            FROM detalle
            WHERE detalle_valido = 1
            ORDER BY referencia_cliente, primer_vencimiento, id_deuda, numero_linea
            """
        )
        for row in cursor:
            yield DetalleAutorizadoFila(
                numero_linea=row[0],
                referencia_cliente=row[1],
                id_deuda=row[2],
                primer_vencimiento=_texto_a_fecha(row[3]),
                moneda=row[4],
                importe_principal=_de_centavos(row[5]),
                nombre_entidad=row[6],
                concepto=row[7],
                segundo_vencimiento=_texto_a_fecha(row[8]),
                importe_segundo_vencimiento=_de_centavos(row[9]),
                tercer_vencimiento=_texto_a_fecha(row[10]),
                importe_tercer_vencimiento=_de_centavos(row[11]),
                fecha_emision_deuda_sintetica=_texto_a_fecha(row[12]),
            )
