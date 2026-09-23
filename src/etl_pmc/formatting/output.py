"""Formateo de salida de 280 posiciones (poc_pmc, NO_VERIFICADA -- prompt
seccion 10). Ningun campo SAP crudo (identificador, importe, ReferenciaCliente)
se trunca en silencio cuando desborda su ancho de destino: se falla con
OutputFormatError, tal como exige GDC-1000 seccion B ("el valor de SAP, luego
de TRIM, no puede superar la longitud definida para el campo destino").
Unica excepcion: los mensajes de ticket/pantalla, que este motor compone y
que GDC-1000 pide truncar explicitamente a un ancho fijo -- ahi sigue
aplicando el corte silencioso, es el comportamiento pedido, no una omision.
"""

from __future__ import annotations

import unicodedata
from datetime import date
from decimal import Decimal

LARGO_REGISTRO = 280


class OutputFormatError(Exception):
    """Un valor no entra en el ancho fijo de salida (prompt seccion 10:
    'agregá tests especificos, no lo presupongas')."""


def _ajustar_texto(valor: str, ancho: int, *, trim: bool = True) -> str:
    """Trunca-y-rellena. Uso reservado a strings ya COMPUESTOS por este motor
    (mensajes de ticket/pantalla), donde GDC-1000 pide explicitamente
    truncar a un ancho fijo ('primeros N caracteres'). No usar para volcar
    un campo SAP crudo -- ver _texto_o_desborda."""
    v = valor.strip() if trim else valor
    return v[:ancho].ljust(ancho)


def _texto_o_desborda(valor: str, ancho: int, *, nombre_campo: str) -> str:
    """GDC-1000 seccion B: 'el valor de SAP (luego de TRIM) no puede superar
    la longitud definida para el campo destino' -- error, no truncamiento
    silencioso. Para campos CHAR mapeados 1:1 desde SAP (ReferenciaCliente),
    a diferencia de los mensajes compuestos por este motor."""
    v = valor.strip()
    if len(v) > ancho:
        raise OutputFormatError(f"{nombre_campo}='{valor}' (tras trim: {len(v)} caracteres) excede el ancho de {ancho} posiciones")
    return v.ljust(ancho)


def _ceros_izquierda(valor: str, ancho: int, *, nombre_campo: str) -> str:
    v = valor.strip()
    if len(v) > ancho:
        raise OutputFormatError(f"{nombre_campo}='{valor}' excede el ancho de {ancho} posiciones")
    return v.rjust(ancho, "0")

def _exacto(valor: str, ancho: int, *, nombre_campo: str) -> str:
    if len(valor) != ancho:
        raise OutputFormatError(f"{nombre_campo}='{valor}' debe tener exactamente {ancho} caracteres, tiene {len(valor)}")
    return valor


def _importe_a_centavos(valor: Decimal, ancho: int, *, nombre_campo: str) -> str:
    centavos = int((valor * 100).quantize(Decimal("1")))
    if centavos < 0:
        raise OutputFormatError(f"{nombre_campo}={valor} es negativo, no soportado en el layout de salida")
    texto = str(centavos)
    if len(texto) > ancho:
        raise OutputFormatError(f"{nombre_campo}={valor} ({texto} centavos) excede el ancho de {ancho} posiciones")
    return texto.rjust(ancho, "0")


def _fecha(valor: date) -> str:
    return valor.strftime("%Y%m%d")


def _sin_acentos(texto: str) -> str:
    """GDC-1000 (seccion C, campo 'Mensaje Ticket'): 'Aceptar caracteres
    especiales, mapear vocales sin acento'. Se usa descomposicion NFKD y se
    descartan las marcas diacriticas, lo que de paso normaliza otros
    caracteres acentuados/diacriticos (p.ej. enie) a su forma ASCII base --
    mas amplio que 'solo vocales', pero consistente con que el resto del
    layout de salida es ASCII de ancho fijo."""
    descompuesto = unicodedata.normalize("NFKD", texto)
    return "".join(ch for ch in descompuesto if not unicodedata.combining(ch))


def construir_mensaje_ticket(concepto: str, referencia_cliente: str, id_deuda: str, cuota_pmc: str) -> str:
    ramo = _sin_acentos(concepto.strip()).upper()
    base = f"{ramo[:4]} Pza{referencia_cliente.strip()} Rec{id_deuda.strip()} Cta{cuota_pmc}"
    return _ajustar_texto(base, 40, trim=False)


def construir_mensaje_pantalla(concepto: str, id_deuda: str) -> str:
    ramo = _sin_acentos(concepto.strip()).upper()
    base = f"{ramo[:5]} Rec {id_deuda.strip()}"
    return _ajustar_texto(base, 15, trim=False)


def formatear_detalle(
    *,
    tipo_registro_det_pmc: str,
    referencia_cliente: str,
    id_deuda: str,
    primer_vencimiento: date,
    importe_principal: Decimal,
    segundo_vencimiento: date,
    importe_segundo_vencimiento: Decimal,
    tercer_vencimiento: date,
    importe_tercer_vencimiento: Decimal,
    concepto: str,
    cuota_pmc: str,
) -> str:
    partes = [
        _exacto(tipo_registro_det_pmc, 1, nombre_campo="TipoRegistroDetPMC"),
        _texto_o_desborda(referencia_cliente, 19, nombre_campo="ReferenciaCliente"),
        _ceros_izquierda(id_deuda, 20, nombre_campo="IdDeuda"),
        "0",  # codigo de moneda de salida, literal en este perfil
        _fecha(primer_vencimiento),
        _importe_a_centavos(importe_principal, 11, nombre_campo="importe_principal"),
        _fecha(segundo_vencimiento),
        _importe_a_centavos(importe_segundo_vencimiento, 11, nombre_campo="importe_segundo_vencimiento"),
        _fecha(tercer_vencimiento),
        _importe_a_centavos(importe_tercer_vencimiento, 11, nombre_campo="importe_tercer_vencimiento"),
        "0" * 19,
        _texto_o_desborda(referencia_cliente, 19, nombre_campo="ReferenciaAnterior"),  # mismo campo SAP, mismo tratamiento
        construir_mensaje_ticket(concepto, referencia_cliente, id_deuda, cuota_pmc),
        construir_mensaje_pantalla(concepto, id_deuda),
        " " * 60,  # espacio reservado para codigo de barras
        "0" * 29,
    ]
    linea = "".join(partes)
    if len(linea) != LARGO_REGISTRO:
        raise OutputFormatError(f"registro de detalle mal formado: {len(linea)} caracteres, se esperaban {LARGO_REGISTRO}")
    return linea


def formatear_cabecera(
    *,
    tipo_registro_cab_pmc: str,
    cod_banco_final: str,
    codigo_servicio_final: str,
    fecha_cabecera: date,
) -> str:
    partes = [
        _exacto(tipo_registro_cab_pmc, 1, nombre_campo="TipoRegistroCabPMC"),
        _exacto(cod_banco_final, 3, nombre_campo="CodBancoFinal"),
        _exacto(codigo_servicio_final, 4, nombre_campo="CodigoServicioFinal"),
        _fecha(fecha_cabecera),
        "1",
        "0" * 263,
    ]
    linea = "".join(partes)
    if len(linea) != LARGO_REGISTRO:
        raise OutputFormatError(f"registro de cabecera mal formado: {len(linea)} caracteres, se esperaban {LARGO_REGISTRO}")
    return linea


def formatear_pie(
    *,
    tipo_registro_pie_pmc: str,
    cod_banco_final: str,
    codigo_servicio_final: str,
    fecha_cabecera: date,
    cantidad_emitidos: int,
    suma_primer_importe: Decimal,
) -> str:
    partes = [
        _exacto(tipo_registro_pie_pmc, 1, nombre_campo="TipoRegistroPiePMC"),
        _exacto(cod_banco_final, 3, nombre_campo="CodBancoFinal"),
        _exacto(codigo_servicio_final, 4, nombre_campo="CodigoServicioFinal"),
        _fecha(fecha_cabecera),
        _ceros_izquierda(str(cantidad_emitidos), 7, nombre_campo="cantidad_emitidos"),
        "0" * 7,
        _importe_a_centavos(suma_primer_importe, 16, nombre_campo="suma_primer_importe"),
        "0" * 234,
    ]
    linea = "".join(partes)
    if len(linea) != LARGO_REGISTRO:
        raise OutputFormatError(f"registro de pie mal formado: {len(linea)} caracteres, se esperaban {LARGO_REGISTRO}")
    return linea
