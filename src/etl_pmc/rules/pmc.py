"""Reglas de negocio Pago Mis Cuentas (poc_pmc, NO_VERIFICADA -- prompt
seccion 9). Orden de aplicacion obligatorio: primero se calcula el rango por
cliente sobre TODOS los detalles autorizados, y recien despues se aplican
conjuntamente los filtros de importe/fecha/rango -- nunca al reves, porque
filtrar primero y luego tomar "los dos siguientes" da otros recibos.

Filtro de antiguedad (GDC-1000 "Filtro 1"): INVENTADO a pedido explicito del
usuario. GDC-1000 no da campo/posicion para "fecha de emision de la deuda"
(el prompt lo deja fuera de alcance por eso); se usa
DetalleConvertido.fecha_emision_deuda_sintetica, un campo de posicion
tambien inventada (ver docs/matriz_equivalencia.md seccion 9.1 y
config/layout_data/poc_pmc_v1.json). Apagado por defecto
(AplicarFiltroAntiguedad); casi seguro no matchea contra datos reales.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from etl_pmc.models import DetalleValidado

IMPORTE_PRINCIPAL_MAXIMO = Decimal("999999999.99")
DIAS_FILTRO_VENCIMIENTO = 30
MESES_FILTRO_ANTIGUEDAD = 10

MOTIVO_IMPORTE_SUPERA_MAXIMO = "IMPORTE_SUPERA_MAXIMO"
MOTIVO_ANTIGUEDAD_SUPERA_10_MESES = "ANTIGUEDAD_SUPERA_10_MESES"
MOTIVO_ANTIGUEDAD_NO_CALCULABLE = "ANTIGUEDAD_NO_CALCULABLE"
MOTIVO_VENCIMIENTO_SUPERA_30_DIAS = "VENCIMIENTO_SUPERA_30_DIAS"
MOTIVO_MAXIMO_DOS_RECIBOS_CLIENTE = "MAXIMO_DOS_RECIBOS_CLIENTE"

# Orden de prioridad cuando un detalle incumple mas de una regla (prompt
# seccion 9, mas MOTIVO_ANTIGUEDAD_* insertado como decision de POC: GDC-1000
# agrupa antiguedad y vencimiento en un unico "Filtro 1", asi que se prioriza
# junto al de vencimiento): se reporta la primera que aplique, en este orden.
_ORDEN_PRIORIDAD = (
    MOTIVO_IMPORTE_SUPERA_MAXIMO,
    MOTIVO_ANTIGUEDAD_NO_CALCULABLE,
    MOTIVO_ANTIGUEDAD_SUPERA_10_MESES,
    MOTIVO_VENCIMIENTO_SUPERA_30_DIAS,
    MOTIVO_MAXIMO_DOS_RECIBOS_CLIENTE,
)


def _sumar_meses(fecha: date, meses: int) -> date:
    """Suma meses calendario (no dias fijos) a una fecha, recortando el dia
    si el mes destino es mas corto (ej. 31 ene + 1 mes -> 28/29 feb)."""
    mes_total = fecha.month - 1 + meses
    anio = fecha.year + mes_total // 12
    mes = mes_total % 12 + 1
    ultimo_dia_mes = (date(anio + (mes // 12), mes % 12 + 1, 1) - timedelta(days=1)).day
    dia = min(fecha.day, ultimo_dia_mes)
    return date(anio, mes, dia)


@dataclass(frozen=True)
class ResultadoFiltroDetalle:
    detalle: DetalleValidado
    rango_cliente: int  # 1-based, calculado ANTES de filtrar
    incluido: bool
    motivo: str | None


def _rango_por_cliente(detalles: list[DetalleValidado]) -> dict[int, int]:
    """Calcula, para cada detalle (identificado por numero de linea), su
    posicion (1-based) dentro del grupo de su ReferenciaCliente, ordenando por
    primer_vencimiento e id_deuda ascendentes; numero de linea como desempate
    estable ante empate completo (prompt seccion 9)."""
    grupos: dict[str, list[DetalleValidado]] = {}
    for d in detalles:
        grupos.setdefault(d.convertido.referencia_cliente, []).append(d)

    rango_por_linea: dict[int, int] = {}
    for miembros in grupos.values():
        ordenados = sorted(
            miembros,
            key=lambda d: (
                d.convertido.primer_vencimiento,
                d.convertido.id_deuda,
                d.linea.numero_linea,
            ),
        )
        for idx, m in enumerate(ordenados, start=1):
            rango_por_linea[m.linea.numero_linea] = idx
    return rango_por_linea


def aplicar_reglas_negocio(
    detalles: list[DetalleValidado],
    *,
    fecha_cabecera: date,
    aplicar_filtro_30_dias: bool,
    aplicar_max_dos_cliente: bool,
    aplicar_filtro_antiguedad: bool = False,
) -> list[ResultadoFiltroDetalle]:
    rango_por_linea = _rango_por_cliente(detalles)
    limite_vencimiento = fecha_cabecera + timedelta(days=DIAS_FILTRO_VENCIMIENTO)
    limite_antiguedad = _sumar_meses(fecha_cabecera, -MESES_FILTRO_ANTIGUEDAD)

    resultados: list[ResultadoFiltroDetalle] = []
    for d in detalles:
        rango = rango_por_linea[d.linea.numero_linea]

        motivos_incumplidos: set[str] = set()
        if d.convertido.importe_principal > IMPORTE_PRINCIPAL_MAXIMO:
            motivos_incumplidos.add(MOTIVO_IMPORTE_SUPERA_MAXIMO)
        if aplicar_filtro_antiguedad:
            fecha_emision = d.convertido.fecha_emision_deuda_sintetica
            if not d.convertido.fecha_emision_deuda_sintetica_valida or fecha_emision is None:
                motivos_incumplidos.add(MOTIVO_ANTIGUEDAD_NO_CALCULABLE)
            elif fecha_emision < limite_antiguedad:
                motivos_incumplidos.add(MOTIVO_ANTIGUEDAD_SUPERA_10_MESES)
        if aplicar_filtro_30_dias and d.convertido.primer_vencimiento > limite_vencimiento:
            motivos_incumplidos.add(MOTIVO_VENCIMIENTO_SUPERA_30_DIAS)
        if aplicar_max_dos_cliente and rango > 2:
            motivos_incumplidos.add(MOTIVO_MAXIMO_DOS_RECIBOS_CLIENTE)

        motivo = next((m for m in _ORDEN_PRIORIDAD if m in motivos_incumplidos), None)

        resultados.append(
            ResultadoFiltroDetalle(detalle=d, rango_cliente=rango, incluido=motivo is None, motivo=motivo)
        )
    return resultados
