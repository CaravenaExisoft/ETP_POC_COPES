"""Control global de totales de archivo (poc_pmc). Ver
docs/matriz_equivalencia.md seccion 6: sin export ADF, la poblacion usada para
el control es TODOS los detalles leidos (validos e invalidos), no solo los
validos -- decision de POC documentada explicitamente, no una suposicion
oculta. La tolerancia (0.01) y las condiciones vienen del prompt seccion 7.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from decimal import Decimal

from etl_pmc.models import ControlArchivo, DetalleValidado, PieConvertido

TOLERANCIA_IMPORTE = Decimal("0.01")

MOTIVO_PIE_AUSENTE = "PIE_AUSENTE"
MOTIVO_PIE_DUPLICADO = "PIE_DUPLICADO"
MOTIVO_PIE_INVALIDO = "PIE_INVALIDO"
MOTIVO_IMPORTES_NULOS = "IMPORTES_NULOS_EN_POBLACION"
MOTIVO_CANTIDAD_NO_COINCIDE = "CANTIDAD_NO_COINCIDE"
MOTIVO_IMPORTE_NO_COINCIDE = "IMPORTE_NO_COINCIDE"


@dataclass
class AcumuladorControlArchivo:
    """Version incremental de calcular_control_archivo, para usar durante la
    primera pasada del pipeline sin materializar todos los detalles en
    memoria (prompt seccion 11: no cargar 500 MB y sus representaciones)."""

    archivo_origen: str
    cantidad_calculada: int = 0
    cantidad_importes_nulos: int = 0
    importe_total_calculado: Decimal = field(default_factory=lambda: Decimal("0"))

    def agregar(self, detalle: DetalleValidado) -> None:
        self.cantidad_calculada += 1
        importe = detalle.convertido.importe_principal
        if importe is None:
            self.cantidad_importes_nulos += 1
        else:
            self.importe_total_calculado += importe

    def finalizar(self, pies: Sequence[PieConvertido]) -> ControlArchivo:
        motivos: list[str] = []
        cantidad_pies = len(pies)
        cantidad_declarada: int | None = None
        importe_total_declarado: Decimal | None = None

        if cantidad_pies == 0:
            motivos.append(MOTIVO_PIE_AUSENTE)
        elif cantidad_pies > 1:
            motivos.append(MOTIVO_PIE_DUPLICADO)
        else:
            pie = pies[0]
            if not (pie.cantidad_declarada_valida and pie.importe_total_declarado_valido):
                motivos.append(MOTIVO_PIE_INVALIDO)
            else:
                cantidad_declarada = pie.cantidad_declarada
                importe_total_declarado = pie.importe_total_declarado

        if self.cantidad_importes_nulos > 0:
            motivos.append(MOTIVO_IMPORTES_NULOS)

        if cantidad_declarada is not None and self.cantidad_calculada != cantidad_declarada:
            motivos.append(MOTIVO_CANTIDAD_NO_COINCIDE)

        if importe_total_declarado is not None:
            diferencia = abs(self.importe_total_calculado - importe_total_declarado)
            if diferencia > TOLERANCIA_IMPORTE:
                motivos.append(MOTIVO_IMPORTE_NO_COINCIDE)

        totales_validos = (
            cantidad_pies == 1
            and self.cantidad_importes_nulos == 0
            and cantidad_declarada is not None
            and self.cantidad_calculada == cantidad_declarada
            and importe_total_declarado is not None
            and abs(self.importe_total_calculado - importe_total_declarado) <= TOLERANCIA_IMPORTE
        )

        return ControlArchivo(
            archivo_origen=self.archivo_origen,
            cantidad_pies=cantidad_pies,
            cantidad_calculada=self.cantidad_calculada,
            cantidad_declarada=cantidad_declarada,
            cantidad_importes_nulos=self.cantidad_importes_nulos,
            importe_total_calculado=self.importe_total_calculado,
            importe_total_declarado=importe_total_declarado,
            totales_validos=totales_validos,
            motivos=tuple(motivos),
        )


def calcular_control_archivo(
    archivo_origen: str,
    detalles: Iterable[DetalleValidado],
    pies: Sequence[PieConvertido],
) -> ControlArchivo:
    acumulador = AcumuladorControlArchivo(archivo_origen)
    for detalle in detalles:
        acumulador.agregar(detalle)
    return acumulador.finalizar(pies)
