from __future__ import annotations

from etl_pmc.config.layouts import Layout
from etl_pmc.models import LineaCruda, PieConvertido
from etl_pmc.parsing.conversions import convertir_entero, convertir_importe


def parsear_pie(linea: LineaCruda, layout: Layout) -> PieConvertido:
    cantidad_field = layout.pie_field("cantidad_declarada")
    importe_field = layout.pie_field("importe_total_declarado")

    cantidad_raw = cantidad_field.extract_raw(linea.contenido)
    importe_raw = importe_field.extract_raw(linea.contenido)

    cantidad, cantidad_valida = convertir_entero(cantidad_raw)
    importe, importe_valido = convertir_importe(importe_raw, importe_field.length)

    return PieConvertido(
        linea=linea,
        cantidad_declarada=cantidad,
        cantidad_declarada_valida=cantidad_valida,
        importe_total_declarado=importe,
        importe_total_declarado_valido=importe_valido,
    )
