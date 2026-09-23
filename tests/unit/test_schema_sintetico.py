from __future__ import annotations

import pytest

from etl_pmc.models import DetalleCrudo, LineaCruda
from etl_pmc.validation.schema_sintetico import SchemaSinteticoError, validar_detalle_schema


def _crudo_valido() -> DetalleCrudo:
    linea = LineaCruda(archivo_origen="f.txt", numero_linea=2, contenido="2" + "0" * 712)
    return DetalleCrudo(
        linea=linea,
        referencia_cliente_raw="10855959",
        id_deuda_raw="843289651",
        primer_vencimiento_raw="20260710",
        moneda_raw="ARS",
        importe_principal_raw="0000594310,07",
        nombre_entidad_raw="GOBIERNO DE LA CIUDAD DE BUENOS AIRES",
        concepto_raw="Automotores".ljust(28),
        segundo_vencimiento_raw="20261030",
        importe_segundo_vencimiento_raw="0000594310,07",
        tercer_vencimiento_raw="20261113",
        importe_tercer_vencimiento_raw="0000594310,07",
    )


def test_registro_valido_no_lanza():
    validar_detalle_schema(_crudo_valido())  # no debe lanzar


def test_id_deuda_con_letras_falla_schema():
    from dataclasses import replace

    crudo = replace(_crudo_valido(), id_deuda_raw="AB3289651")
    with pytest.raises(SchemaSinteticoError):
        validar_detalle_schema(crudo)


def test_importe_con_punto_falla_schema():
    from dataclasses import replace

    crudo = replace(_crudo_valido(), importe_principal_raw="0000594310.07")
    with pytest.raises(SchemaSinteticoError):
        validar_detalle_schema(crudo)


def test_referencia_cliente_con_espacio_falla_schema():
    from dataclasses import replace

    crudo = replace(_crudo_valido(), referencia_cliente_raw=" 1234567")
    with pytest.raises(SchemaSinteticoError):
        validar_detalle_schema(crudo)
