"""Control de cabecera (poc_pmc, NO_VERIFICADA -- docs/matriz_equivalencia.md
seccion 7). Sin export ADF no hay confirmacion de que pasa ante cabecera
ausente/duplicada/invalida; la politica de POC es rechazar el archivo
completo en cualquiera de esos casos, sin fabricar una cabecera de exito."""

from __future__ import annotations

from dataclasses import dataclass

from etl_pmc.models import CabeceraConvertida

MOTIVO_CABECERA_AUSENTE = "CABECERA_AUSENTE"
MOTIVO_CABECERA_DUPLICADA = "CABECERA_DUPLICADA"
MOTIVO_FECHA_CABECERA_INVALIDA = "FECHA_CABECERA_INVALIDA"


@dataclass(frozen=True)
class ControlCabecera:
    valida: bool
    cabecera: CabeceraConvertida | None
    motivos: tuple[str, ...]


def validar_cabeceras(cabeceras: list[CabeceraConvertida]) -> ControlCabecera:
    if len(cabeceras) == 0:
        return ControlCabecera(valida=False, cabecera=None, motivos=(MOTIVO_CABECERA_AUSENTE,))
    if len(cabeceras) > 1:
        return ControlCabecera(valida=False, cabecera=None, motivos=(MOTIVO_CABECERA_DUPLICADA,))

    cabecera = cabeceras[0]
    if not cabecera.fecha_cabecera_valida:
        return ControlCabecera(valida=False, cabecera=cabecera, motivos=(MOTIVO_FECHA_CABECERA_INVALIDA,))

    return ControlCabecera(valida=True, cabecera=cabecera, motivos=())
