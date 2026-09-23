from __future__ import annotations

from datetime import date
from decimal import Decimal

from etl_pmc.models import DetalleConvertido, DetalleCrudo, DetalleValidado, LineaCruda
from etl_pmc.rules.pmc import (
    MOTIVO_ANTIGUEDAD_NO_CALCULABLE,
    MOTIVO_ANTIGUEDAD_SUPERA_10_MESES,
    MOTIVO_IMPORTE_SUPERA_MAXIMO,
    MOTIVO_MAXIMO_DOS_RECIBOS_CLIENTE,
    MOTIVO_VENCIMIENTO_SUPERA_30_DIAS,
    aplicar_reglas_negocio,
)


def _detalle(
    numero_linea: int,
    referencia_cliente: str,
    id_deuda: str,
    primer_vencimiento: date,
    importe_principal: Decimal,
    fecha_emision_deuda_sintetica: date | None = None,
) -> DetalleValidado:
    linea = LineaCruda(archivo_origen="f.txt", numero_linea=numero_linea, contenido="2" + "0" * 712)
    crudo = DetalleCrudo(
        linea=linea,
        referencia_cliente_raw=referencia_cliente,
        id_deuda_raw=id_deuda,
        primer_vencimiento_raw="",
        moneda_raw="ARS",
        importe_principal_raw="",
        nombre_entidad_raw="",
        concepto_raw="Automotores",
        segundo_vencimiento_raw="",
        importe_segundo_vencimiento_raw="",
        tercer_vencimiento_raw="",
        importe_tercer_vencimiento_raw="",
    )
    convertido = DetalleConvertido(
        crudo=crudo,
        referencia_cliente=referencia_cliente,
        id_deuda=id_deuda,
        primer_vencimiento=primer_vencimiento,
        primer_vencimiento_valido=True,
        moneda="ARS",
        importe_principal=importe_principal,
        importe_principal_valido=True,
        nombre_entidad="",
        concepto="Automotores",
        segundo_vencimiento=primer_vencimiento,
        segundo_vencimiento_valido=True,
        importe_segundo_vencimiento=importe_principal,
        importe_segundo_vencimiento_valido=True,
        tercer_vencimiento=primer_vencimiento,
        tercer_vencimiento_valido=True,
        importe_tercer_vencimiento=importe_principal,
        importe_tercer_vencimiento_valido=True,
        fecha_emision_deuda_sintetica=fecha_emision_deuda_sintetica,
        fecha_emision_deuda_sintetica_valida=fecha_emision_deuda_sintetica is not None,
    )
    return DetalleValidado(
        convertido=convertido,
        identificacion_valida=True,
        moneda_valida=True,
        importes_validos=True,
        fechas_validas=True,
    )


def test_sin_filtros_todo_incluido():
    detalles = [
        _detalle(1, "11111111", "100000001", date(2026, 1, 10), Decimal("100")),
        _detalle(2, "11111111", "100000002", date(2026, 1, 20), Decimal("100")),
        _detalle(3, "11111111", "100000003", date(2026, 1, 30), Decimal("100")),
    ]
    resultados = aplicar_reglas_negocio(
        detalles, fecha_cabecera=date(2026, 1, 1), aplicar_filtro_30_dias=False, aplicar_max_dos_cliente=False
    )
    assert all(r.incluido for r in resultados)


def test_importe_supera_maximo():
    detalles = [_detalle(1, "11111111", "100000001", date(2026, 1, 10), Decimal("1000000000.00"))]
    resultados = aplicar_reglas_negocio(
        detalles, fecha_cabecera=date(2026, 1, 1), aplicar_filtro_30_dias=False, aplicar_max_dos_cliente=False
    )
    assert resultados[0].incluido is False
    assert resultados[0].motivo == MOTIVO_IMPORTE_SUPERA_MAXIMO


def test_filtro_30_dias_limite_exacto_incluido():
    # fecha_cabecera + 30 dias exacto: el prompt no impone limite inferior,
    # y el limite superior es inclusive ("<= 30 dias").
    fecha_cabecera = date(2026, 1, 1)
    limite = fecha_cabecera + __import__("datetime").timedelta(days=30)
    detalles = [_detalle(1, "11111111", "100000001", limite, Decimal("100"))]
    resultados = aplicar_reglas_negocio(
        detalles, fecha_cabecera=fecha_cabecera, aplicar_filtro_30_dias=True, aplicar_max_dos_cliente=False
    )
    assert resultados[0].incluido is True


def test_filtro_30_dias_un_dia_despues_excluido():
    fecha_cabecera = date(2026, 1, 1)
    limite_mas_uno = fecha_cabecera + __import__("datetime").timedelta(days=31)
    detalles = [_detalle(1, "11111111", "100000001", limite_mas_uno, Decimal("100"))]
    resultados = aplicar_reglas_negocio(
        detalles, fecha_cabecera=fecha_cabecera, aplicar_filtro_30_dias=True, aplicar_max_dos_cliente=False
    )
    assert resultados[0].incluido is False
    assert resultados[0].motivo == MOTIVO_VENCIMIENTO_SUPERA_30_DIAS


def test_filtro_30_dias_fecha_anterior_a_cabecera_no_se_rechaza():
    # El prompt dice explicitamente que no hay limite inferior.
    fecha_cabecera = date(2026, 6, 1)
    anterior = date(2020, 1, 1)
    detalles = [_detalle(1, "11111111", "100000001", anterior, Decimal("100"))]
    resultados = aplicar_reglas_negocio(
        detalles, fecha_cabecera=fecha_cabecera, aplicar_filtro_30_dias=True, aplicar_max_dos_cliente=False
    )
    assert resultados[0].incluido is True


def test_maximo_dos_recibos_por_cliente_conserva_los_dos_mas_tempranos():
    detalles = [
        _detalle(1, "11111111", "100000003", date(2026, 3, 1), Decimal("100")),
        _detalle(2, "11111111", "100000001", date(2026, 1, 1), Decimal("100")),
        _detalle(3, "11111111", "100000002", date(2026, 2, 1), Decimal("100")),
    ]
    resultados = aplicar_reglas_negocio(
        detalles, fecha_cabecera=date(2026, 1, 1), aplicar_filtro_30_dias=False, aplicar_max_dos_cliente=True
    )
    incluidos = {r.detalle.convertido.id_deuda for r in resultados if r.incluido}
    assert incluidos == {"100000001", "100000002"}
    excluido = next(r for r in resultados if not r.incluido)
    assert excluido.motivo == MOTIVO_MAXIMO_DOS_RECIBOS_CLIENTE


def test_rango_se_calcula_antes_de_filtrar_por_importe():
    # El primero (mas temprano) tiene importe excesivo: debe rechazarse por
    # importe, pero SIN correr el rango de los otros dos hacia arriba (si se
    # filtrara primero por importe y luego se recalculara el rango, el
    # segundo y tercero pasarian a ser rango 1 y 2 de todos modos aca, pero la
    # clave es que el rango de cada uno no cambia por la exclusion de otro).
    detalles = [
        _detalle(1, "22222222", "200000001", date(2026, 1, 1), Decimal("1000000000.00")),  # excede maximo
        _detalle(2, "22222222", "200000002", date(2026, 1, 2), Decimal("100")),
        _detalle(3, "22222222", "200000003", date(2026, 1, 3), Decimal("100")),
        _detalle(4, "22222222", "200000004", date(2026, 1, 4), Decimal("100")),
    ]
    resultados = aplicar_reglas_negocio(
        detalles, fecha_cabecera=date(2026, 1, 1), aplicar_filtro_30_dias=False, aplicar_max_dos_cliente=True
    )
    por_id = {r.detalle.convertido.id_deuda: r for r in resultados}
    assert por_id["200000001"].rango_cliente == 1
    assert por_id["200000001"].motivo == MOTIVO_IMPORTE_SUPERA_MAXIMO
    assert por_id["200000002"].rango_cliente == 2
    assert por_id["200000002"].incluido is True
    assert por_id["200000003"].rango_cliente == 3
    assert por_id["200000003"].motivo == MOTIVO_MAXIMO_DOS_RECIBOS_CLIENTE
    assert por_id["200000004"].rango_cliente == 4


def test_desempate_por_numero_de_linea_en_empate_completo():
    misma_fecha = date(2026, 1, 1)
    detalles = [
        _detalle(5, "33333333", "300000001", misma_fecha, Decimal("100")),
        _detalle(2, "33333333", "300000001", misma_fecha, Decimal("100")),
    ]
    resultados = aplicar_reglas_negocio(
        detalles, fecha_cabecera=date(2026, 1, 1), aplicar_filtro_30_dias=False, aplicar_max_dos_cliente=True
    )
    por_linea = {r.detalle.linea.numero_linea: r.rango_cliente for r in resultados}
    assert por_linea[2] == 1
    assert por_linea[5] == 2


# --- Filtro de antiguedad: INVENTADO a pedido del usuario (ver rules/pmc.py
# docstring y docs/matriz_equivalencia.md seccion 9.1). Apagado por defecto. ---


def test_filtro_antiguedad_apagado_por_defecto_no_excluye_nada():
    detalles = [_detalle(1, "11111111", "100000001", date(2026, 1, 10), Decimal("100"))]
    resultados = aplicar_reglas_negocio(
        detalles, fecha_cabecera=date(2026, 1, 1), aplicar_filtro_30_dias=False, aplicar_max_dos_cliente=False
    )
    assert resultados[0].incluido is True


def test_filtro_antiguedad_campo_no_calculable_excluye():
    detalles = [
        _detalle(1, "11111111", "100000001", date(2026, 1, 10), Decimal("100"), fecha_emision_deuda_sintetica=None)
    ]
    resultados = aplicar_reglas_negocio(
        detalles,
        fecha_cabecera=date(2026, 1, 1),
        aplicar_filtro_30_dias=False,
        aplicar_max_dos_cliente=False,
        aplicar_filtro_antiguedad=True,
    )
    assert resultados[0].incluido is False
    assert resultados[0].motivo == MOTIVO_ANTIGUEDAD_NO_CALCULABLE


def test_filtro_antiguedad_mas_de_10_meses_excluye():
    detalles = [
        _detalle(
            1,
            "11111111",
            "100000001",
            date(2026, 1, 10),
            Decimal("100"),
            fecha_emision_deuda_sintetica=date(2025, 2, 28),  # mas de 10 meses antes del 2026-01-01
        )
    ]
    resultados = aplicar_reglas_negocio(
        detalles,
        fecha_cabecera=date(2026, 1, 1),
        aplicar_filtro_30_dias=False,
        aplicar_max_dos_cliente=False,
        aplicar_filtro_antiguedad=True,
    )
    assert resultados[0].incluido is False
    assert resultados[0].motivo == MOTIVO_ANTIGUEDAD_SUPERA_10_MESES


def test_filtro_antiguedad_limite_exacto_10_meses_incluido():
    detalles = [
        _detalle(
            1,
            "11111111",
            "100000001",
            date(2026, 1, 10),
            Decimal("100"),
            fecha_emision_deuda_sintetica=date(2025, 3, 1),  # exactamente 10 meses antes
        )
    ]
    resultados = aplicar_reglas_negocio(
        detalles,
        fecha_cabecera=date(2026, 1, 1),
        aplicar_filtro_30_dias=False,
        aplicar_max_dos_cliente=False,
        aplicar_filtro_antiguedad=True,
    )
    assert resultados[0].incluido is True


def test_filtro_antiguedad_reciente_incluido():
    detalles = [
        _detalle(
            1,
            "11111111",
            "100000001",
            date(2026, 1, 10),
            Decimal("100"),
            fecha_emision_deuda_sintetica=date(2025, 12, 1),
        )
    ]
    resultados = aplicar_reglas_negocio(
        detalles,
        fecha_cabecera=date(2026, 1, 1),
        aplicar_filtro_30_dias=False,
        aplicar_max_dos_cliente=False,
        aplicar_filtro_antiguedad=True,
    )
    assert resultados[0].incluido is True


def test_sumar_meses_recorta_dia_en_mes_mas_corto():
    from etl_pmc.rules.pmc import _sumar_meses

    assert _sumar_meses(date(2026, 3, 31), -1) == date(2026, 2, 28)  # 2026 no es bisiesto
    assert _sumar_meses(date(2024, 3, 31), -1) == date(2024, 2, 29)  # 2024 si es bisiesto
    assert _sumar_meses(date(2026, 1, 1), -10) == date(2025, 3, 1)
