"""Validacion de negocio de Detalle (poc_pmc). Ver docs/matriz_equivalencia.md
seccion 4: sin export ADF, estas reglas siguen el prompt seccion 6 y las
verificaciones empiricas contra entrada_real_1000.txt; no se agregan
condiciones no pedidas (p.ej. orden cronologico entre vencimientos)."""

from __future__ import annotations

import re

from etl_pmc.models import DetalleConvertido, DetalleValidado

_REFERENCIA_CLIENTE_RE = re.compile(r"^[0-9]{8}$")
_ID_DEUDA_RE = re.compile(r"^[0-9]{9}$")

MOTIVO_IDENTIFICACION_INVALIDA = "IDENTIFICACION_INVALIDA"
MOTIVO_MONEDA_INVALIDA = "MONEDA_INVALIDA"
MOTIVO_IMPORTE_INVALIDO = "IMPORTE_INVALIDO"
MOTIVO_FECHA_INVALIDA = "FECHA_INVALIDA"


def validar_detalle(convertido: DetalleConvertido) -> DetalleValidado:
    identificacion_valida = bool(
        _ID_DEUDA_RE.match(convertido.id_deuda) and _REFERENCIA_CLIENTE_RE.match(convertido.referencia_cliente)
    )
    moneda_valida = convertido.moneda == "ARS"
    importes_validos = (
        convertido.importe_principal_valido
        and convertido.importe_segundo_vencimiento_valido
        and convertido.importe_tercer_vencimiento_valido
    )
    fechas_validas = (
        convertido.primer_vencimiento_valido
        and convertido.segundo_vencimiento_valido
        and convertido.tercer_vencimiento_valido
    )

    motivos: list[str] = []
    if not identificacion_valida:
        motivos.append(MOTIVO_IDENTIFICACION_INVALIDA)
    if not moneda_valida:
        motivos.append(MOTIVO_MONEDA_INVALIDA)
    if not importes_validos:
        motivos.append(MOTIVO_IMPORTE_INVALIDO)
    if not fechas_validas:
        motivos.append(MOTIVO_FECHA_INVALIDA)

    return DetalleValidado(
        convertido=convertido,
        identificacion_valida=identificacion_valida,
        moneda_valida=moneda_valida,
        importes_validos=importes_validos,
        fechas_validas=fechas_validas,
        motivos_rechazo=tuple(motivos),
    )
