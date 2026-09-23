from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from etl_pmc.formatting.output import (
    LARGO_REGISTRO,
    OutputFormatError,
    construir_mensaje_pantalla,
    construir_mensaje_ticket,
    formatear_cabecera,
    formatear_detalle,
    formatear_pie,
)


def _detalle_kwargs(**overrides):
    base = dict(
        tipo_registro_det_pmc="1",
        referencia_cliente="10855959",
        id_deuda="843289651",
        primer_vencimiento=date(2026, 7, 10),
        importe_principal=Decimal("594310.07"),
        segundo_vencimiento=date(2026, 10, 30),
        importe_segundo_vencimiento=Decimal("594310.07"),
        tercer_vencimiento=date(2026, 11, 13),
        importe_tercer_vencimiento=Decimal("594310.07"),
        concepto="Automotores",
        cuota_pmc="01",
    )
    base.update(overrides)
    return base


def test_mensaje_ticket_formula_exacta():
    ticket = construir_mensaje_ticket("Automotores", "10855959", "843289651", "01")
    assert len(ticket) == 40
    assert ticket == "AUTO Pza10855959 Rec843289651 Cta01".ljust(40)


def test_mensaje_ticket_mapea_vocales_acentuadas_sin_acento():
    # GDC-1000, seccion C, "Mensaje Ticket": "mapear vocales sin acento".
    ticket = construir_mensaje_ticket("Automóvil", "10855959", "843289651", "01")
    assert ticket.startswith("AUTO ")
    assert "Ó" not in ticket and "ó" not in ticket


def test_mensaje_pantalla_mapea_vocales_acentuadas_sin_acento():
    pantalla = construir_mensaje_pantalla("Automóvil", "843289651")
    assert pantalla == "AUTOM Rec 84328"


def test_mensaje_pantalla_formula_exacta():
    pantalla = construir_mensaje_pantalla("Automotores", "843289651")
    assert len(pantalla) == 15
    assert pantalla == "AUTOM Rec 84328"


def test_detalle_tiene_280_posiciones_y_campos_en_su_lugar():
    linea = formatear_detalle(**_detalle_kwargs())
    assert len(linea) == LARGO_REGISTRO

    assert linea[0] == "1"  # TipoRegistroDetPMC
    assert linea[1:20] == "10855959".ljust(19)  # 2-20
    assert linea[20:40] == "843289651".rjust(20, "0")  # 21-40
    assert linea[40] == "0"  # 41: moneda de salida
    assert linea[41:49] == "20260710"  # 42-49
    assert linea[49:60] == "00059431007".rjust(11, "0")  # 50-60: 594310.07 -> 59431007 centavos
    assert linea[60:68] == "20261030"  # 61-68
    assert linea[68:79] == "59431007".rjust(11, "0")  # 69-79
    assert linea[79:87] == "20261113"  # 80-87
    assert linea[87:98] == "59431007".rjust(11, "0")  # 88-98
    assert linea[98:117] == "0" * 19  # 99-117
    assert linea[117:136] == "10855959".ljust(19)  # 118-136: referencia anterior
    assert linea[136:176] == "AUTO Pza10855959 Rec843289651 Cta01".ljust(40)  # 137-176
    assert linea[176:191] == "AUTOM Rec 84328"  # 177-191
    assert linea[191:251] == " " * 60  # 192-251
    assert linea[251:280] == "0" * 29  # 252-280


def test_referencia_cliente_mas_de_19_caracteres_desborda():
    # GDC-1000 seccion B: "el valor de SAP (luego de TRIM) no puede superar
    # la longitud definida para el campo destino" -- error, no truncamiento.
    with pytest.raises(OutputFormatError):
        formatear_detalle(**_detalle_kwargs(referencia_cliente="123456789012345678901"))


def test_id_deuda_mas_de_20_caracteres_desborda():
    with pytest.raises(OutputFormatError):
        formatear_detalle(**_detalle_kwargs(id_deuda="1" * 21))


def test_importe_maximo_de_negocio_entra_justo_en_11_posiciones():
    # 999999999.99 (tope de negocio, prompt seccion 9) = 99999999999 centavos,
    # exactamente 11 digitos: entra justo en el campo de salida.
    linea = formatear_detalle(**_detalle_kwargs(importe_principal=Decimal("999999999.99")))
    assert linea[49:60] == "99999999999"


def test_importe_que_desborda_11_posiciones_de_centavos():
    with pytest.raises(OutputFormatError):
        formatear_detalle(**_detalle_kwargs(importe_principal=Decimal("1000000000.00")))


def test_cabecera_280_posiciones():
    linea = formatear_cabecera(
        tipo_registro_cab_pmc="0",
        cod_banco_final="001",
        codigo_servicio_final="0001",
        fecha_cabecera=date(2026, 9, 21),
    )
    assert len(linea) == LARGO_REGISTRO
    assert linea[0] == "0"
    assert linea[1:4] == "001"
    assert linea[4:8] == "0001"
    assert linea[8:16] == "20260921"
    assert linea[16] == "1"
    assert linea[17:280] == "0" * 263


def test_cod_banco_final_debe_tener_exactamente_3_caracteres():
    with pytest.raises(OutputFormatError):
        formatear_cabecera(
            tipo_registro_cab_pmc="0",
            cod_banco_final="1",
            codigo_servicio_final="0001",
            fecha_cabecera=date(2026, 9, 21),
        )


def test_pie_280_posiciones():
    linea = formatear_pie(
        tipo_registro_pie_pmc="9",
        cod_banco_final="001",
        codigo_servicio_final="0001",
        fecha_cabecera=date(2026, 9, 21),
        cantidad_emitidos=1000,
        suma_primer_importe=Decimal("509483812.32"),
    )
    assert len(linea) == LARGO_REGISTRO
    assert linea[0] == "9"
    assert linea[1:4] == "001"
    assert linea[4:8] == "0001"
    assert linea[8:16] == "20260921"
    assert linea[16:23] == "0001000"
    assert linea[23:30] == "0" * 7
    assert linea[30:46] == "50948381232".rjust(16, "0")
    assert linea[46:280] == "0" * 234
