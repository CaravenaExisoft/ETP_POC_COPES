from __future__ import annotations

from decimal import Decimal

import pytest

from etl_pmc.control.totales import (
    MOTIVO_CANTIDAD_NO_COINCIDE,
    MOTIVO_IMPORTE_NO_COINCIDE,
    MOTIVO_IMPORTES_NULOS,
    MOTIVO_PIE_AUSENTE,
    MOTIVO_PIE_DUPLICADO,
    calcular_control_archivo,
)
from etl_pmc.models import (
    DetalleConvertido,
    DetalleCrudo,
    DetalleValidado,
    LineaCruda,
    PieConvertido,
)


def _linea(n: int) -> LineaCruda:
    return LineaCruda(archivo_origen="f.txt", numero_linea=n, contenido="2" + "0" * 712)


def _detalle_validado(importe_principal: Decimal | None) -> DetalleValidado:
    linea = _linea(1)
    crudo = DetalleCrudo(
        linea=linea,
        referencia_cliente_raw="12345678",
        id_deuda_raw="123456789",
        primer_vencimiento_raw="20260101",
        moneda_raw="ARS",
        importe_principal_raw="",
        nombre_entidad_raw="",
        concepto_raw="",
        segundo_vencimiento_raw="20260101",
        importe_segundo_vencimiento_raw="",
        tercer_vencimiento_raw="20260101",
        importe_tercer_vencimiento_raw="",
    )
    convertido = DetalleConvertido(
        crudo=crudo,
        referencia_cliente="12345678",
        id_deuda="123456789",
        primer_vencimiento=None,
        primer_vencimiento_valido=True,
        moneda="ARS",
        importe_principal=importe_principal,
        importe_principal_valido=importe_principal is not None,
        nombre_entidad="",
        concepto="",
        segundo_vencimiento=None,
        segundo_vencimiento_valido=True,
        importe_segundo_vencimiento=Decimal("0"),
        importe_segundo_vencimiento_valido=True,
        tercer_vencimiento=None,
        tercer_vencimiento_valido=True,
        importe_tercer_vencimiento=Decimal("0"),
        importe_tercer_vencimiento_valido=True,
    )
    return DetalleValidado(
        convertido=convertido,
        identificacion_valida=True,
        moneda_valida=True,
        importes_validos=importe_principal is not None,
        fechas_validas=True,
    )


def _pie(cantidad: int, importe: Decimal, *, cantidad_valida: bool = True, importe_valida: bool = True) -> PieConvertido:
    return PieConvertido(
        linea=_linea(999),
        cantidad_declarada=cantidad,
        cantidad_declarada_valida=cantidad_valida,
        importe_total_declarado=importe,
        importe_total_declarado_valido=importe_valida,
    )


def test_control_valido_cuando_todo_cierra():
    detalles = [_detalle_validado(Decimal("100.00")), _detalle_validado(Decimal("50.00"))]
    pies = [_pie(2, Decimal("150.00"))]
    control = calcular_control_archivo("f.txt", detalles, pies)
    assert control.totales_validos is True
    assert control.motivos == ()


def test_pie_ausente():
    control = calcular_control_archivo("f.txt", [_detalle_validado(Decimal("1"))], [])
    assert control.totales_validos is False
    assert MOTIVO_PIE_AUSENTE in control.motivos


def test_pie_duplicado():
    detalles = [_detalle_validado(Decimal("1"))]
    pies = [_pie(1, Decimal("1")), _pie(1, Decimal("1"))]
    control = calcular_control_archivo("f.txt", detalles, pies)
    assert control.totales_validos is False
    assert MOTIVO_PIE_DUPLICADO in control.motivos


def test_cantidad_no_coincide():
    detalles = [_detalle_validado(Decimal("1")), _detalle_validado(Decimal("1"))]
    pies = [_pie(3, Decimal("2"))]
    control = calcular_control_archivo("f.txt", detalles, pies)
    assert control.totales_validos is False
    assert MOTIVO_CANTIDAD_NO_COINCIDE in control.motivos


def test_importe_nulo_en_poblacion_invalida_el_control():
    detalles = [_detalle_validado(Decimal("100.00")), _detalle_validado(None)]
    pies = [_pie(2, Decimal("100.00"))]
    control = calcular_control_archivo("f.txt", detalles, pies)
    assert control.cantidad_importes_nulos == 1
    assert control.totales_validos is False
    assert MOTIVO_IMPORTES_NULOS in control.motivos


@pytest.mark.parametrize(
    ("declarado", "calculado", "valido"),
    [
        (Decimal("100.00"), Decimal("100.00"), True),
        (Decimal("100.00"), Decimal("100.01"), True),
        (Decimal("100.00"), Decimal("99.99"), True),
        (Decimal("100.00"), Decimal("100.02"), False),
        (Decimal("100.00"), Decimal("99.98"), False),
    ],
)
def test_tolerancia_de_importe_0_00_0_01_0_02(declarado, calculado, valido):
    detalles = [_detalle_validado(calculado)]
    pies = [_pie(1, declarado)]
    control = calcular_control_archivo("f.txt", detalles, pies)
    assert control.totales_validos is valido
    assert (MOTIVO_IMPORTE_NO_COINCIDE in control.motivos) is (not valido)


def test_un_detalle_invalido_igual_contamina_el_conteo_aunque_no_se_publique():
    # Un detalle con importe corrupto (invalido a nivel registro) sigue
    # contando para el control global (decision de poblacion documentada en
    # docs/matriz_equivalencia.md seccion 6): no desaparece del conteo.
    detalles = [_detalle_validado(Decimal("100.00")), _detalle_validado(None)]
    pies = [_pie(2, Decimal("100.00"))]
    control = calcular_control_archivo("f.txt", detalles, pies)
    assert control.cantidad_calculada == 2
