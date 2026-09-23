from __future__ import annotations

from etl_pmc.config.layouts import Layout
from etl_pmc.models import CabeceraConvertida, LineaCruda
from etl_pmc.parsing.conversions import convertir_fecha_yyyymmdd


def parsear_cabecera(linea: LineaCruda, layout: Layout) -> CabeceraConvertida:
    raw = layout.cabecera_field("fecha_cabecera").extract_raw(linea.contenido)
    fecha, valida = convertir_fecha_yyyymmdd(raw)
    return CabeceraConvertida(
        linea=linea,
        fecha_cabecera_raw=raw,
        fecha_cabecera=fecha,
        fecha_cabecera_valida=valida,
    )
