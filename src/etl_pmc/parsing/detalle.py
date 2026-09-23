from __future__ import annotations

from etl_pmc.config.layouts import Layout
from etl_pmc.models import DetalleConvertido, DetalleCrudo, LineaCruda
from etl_pmc.parsing.conversions import convertir_fecha_yyyymmdd, convertir_importe, convertir_texto


def extraer_detalle_crudo(linea: LineaCruda, layout: Layout) -> DetalleCrudo:
    def raw(nombre: str) -> str:
        return layout.detalle_field(nombre).extract_raw(linea.contenido)

    return DetalleCrudo(
        linea=linea,
        referencia_cliente_raw=raw("referencia_cliente"),
        id_deuda_raw=raw("id_deuda"),
        primer_vencimiento_raw=raw("primer_vencimiento"),
        moneda_raw=raw("moneda"),
        importe_principal_raw=raw("importe_principal"),
        nombre_entidad_raw=raw("nombre_entidad"),
        concepto_raw=raw("concepto"),
        segundo_vencimiento_raw=raw("segundo_vencimiento"),
        importe_segundo_vencimiento_raw=raw("importe_segundo_vencimiento"),
        tercer_vencimiento_raw=raw("tercer_vencimiento"),
        importe_tercer_vencimiento_raw=raw("importe_tercer_vencimiento"),
        fecha_emision_deuda_sintetica_raw=raw("fecha_emision_deuda_sintetica"),
    )


def convertir_detalle(crudo: DetalleCrudo, layout: Layout) -> DetalleConvertido:
    referencia_cliente, _ = convertir_texto(crudo.referencia_cliente_raw)
    id_deuda, _ = convertir_texto(crudo.id_deuda_raw)
    moneda, _ = convertir_texto(crudo.moneda_raw)
    nombre_entidad, _ = convertir_texto(crudo.nombre_entidad_raw)
    concepto, _ = convertir_texto(crudo.concepto_raw)

    primer_vencimiento, primer_vencimiento_valido = convertir_fecha_yyyymmdd(crudo.primer_vencimiento_raw)
    segundo_vencimiento, segundo_vencimiento_valido = convertir_fecha_yyyymmdd(crudo.segundo_vencimiento_raw)
    tercer_vencimiento, tercer_vencimiento_valido = convertir_fecha_yyyymmdd(crudo.tercer_vencimiento_raw)

    importe_principal, importe_principal_valido = convertir_importe(
        crudo.importe_principal_raw, layout.detalle_field("importe_principal").length
    )
    importe_segundo_vencimiento, importe_segundo_vencimiento_valido = convertir_importe(
        crudo.importe_segundo_vencimiento_raw, layout.detalle_field("importe_segundo_vencimiento").length
    )
    importe_tercer_vencimiento, importe_tercer_vencimiento_valido = convertir_importe(
        crudo.importe_tercer_vencimiento_raw, layout.detalle_field("importe_tercer_vencimiento").length
    )
    fecha_emision_deuda_sintetica, fecha_emision_deuda_sintetica_valida = convertir_fecha_yyyymmdd(
        crudo.fecha_emision_deuda_sintetica_raw
    )

    return DetalleConvertido(
        crudo=crudo,
        referencia_cliente=referencia_cliente,
        id_deuda=id_deuda,
        primer_vencimiento=primer_vencimiento,
        primer_vencimiento_valido=primer_vencimiento_valido,
        moneda=moneda,
        importe_principal=importe_principal,
        importe_principal_valido=importe_principal_valido,
        nombre_entidad=nombre_entidad,
        concepto=concepto,
        segundo_vencimiento=segundo_vencimiento,
        segundo_vencimiento_valido=segundo_vencimiento_valido,
        importe_segundo_vencimiento=importe_segundo_vencimiento,
        importe_segundo_vencimiento_valido=importe_segundo_vencimiento_valido,
        tercer_vencimiento=tercer_vencimiento,
        tercer_vencimiento_valido=tercer_vencimiento_valido,
        importe_tercer_vencimiento=importe_tercer_vencimiento,
        importe_tercer_vencimiento_valido=importe_tercer_vencimiento_valido,
        fecha_emision_deuda_sintetica=fecha_emision_deuda_sintetica,
        fecha_emision_deuda_sintetica_valida=fecha_emision_deuda_sintetica_valida,
    )


def parsear_detalle(linea: LineaCruda, layout: Layout) -> DetalleConvertido:
    return convertir_detalle(extraer_detalle_crudo(linea, layout), layout)
