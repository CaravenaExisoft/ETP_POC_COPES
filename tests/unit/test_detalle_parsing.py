from __future__ import annotations

from decimal import Decimal

from etl_pmc.models import LineaCruda
from etl_pmc.parsing.detalle import parsear_detalle


def _detalle_real() -> str:
    # Primera linea de detalle real de entrada_real_1000.txt (713 caracteres).
    campos = {
        58: ("10855959", 8),
        103: ("843289651", 9),
        144: ("20260710", 8),
        168: ("ARS", 3),
        173: ("0000594310,07", 13),
        323: ("GOBIERNO DE LA CIUDAD DE BUENOS AIRES".ljust(37), 37),
        434: ("Automotores".ljust(28), 28),
        666: ("20261030", 8),
        674: ("0000594310,07", 13),
        687: ("20261113", 8),
        695: ("0000594310,07", 13),
    }
    linea = ["0"] * 713
    linea[0] = "2"
    for start, (valor, length) in campos.items():
        for i, ch in enumerate(valor):
            linea[start - 1 + i] = ch
    return "".join(linea)


def test_parsea_detalle_realista(poc_pmc_layout):
    contenido = _detalle_real()
    linea = LineaCruda(archivo_origen="f.txt", numero_linea=2, contenido=contenido)
    convertido = parsear_detalle(linea, poc_pmc_layout)

    assert convertido.referencia_cliente == "10855959"
    assert convertido.id_deuda == "843289651"
    assert convertido.moneda == "ARS"
    assert convertido.importe_principal == Decimal("594310.07")
    assert convertido.importe_principal_valido is True
    assert convertido.nombre_entidad == "GOBIERNO DE LA CIUDAD DE BUENOS AIRES"
    assert convertido.concepto == "Automotores"
    assert convertido.primer_vencimiento.isoformat() == "2026-07-10"
    assert convertido.segundo_vencimiento.isoformat() == "2026-10-30"
    assert convertido.tercer_vencimiento.isoformat() == "2026-11-13"


def test_id_deuda_y_referencia_conservan_ceros_a_izquierda(poc_pmc_layout):
    contenido = list(_detalle_real())
    # IdDeuda con ceros a la izquierda: posiciones 103..111 (1-based)
    for i, ch in enumerate("000000012"):
        contenido[103 - 1 + i] = ch
    linea = LineaCruda(archivo_origen="f.txt", numero_linea=2, contenido="".join(contenido))
    convertido = parsear_detalle(linea, poc_pmc_layout)
    assert convertido.id_deuda == "000000012"
