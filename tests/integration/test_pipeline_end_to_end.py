"""Prueba de extremo a extremo del motor completo (modo local, sin Azure)
contra el unico archivo real disponible: entrada_real_1000.txt. El CSV de
enriquecimiento es SINTETICO (no hay uno real adjunto, ver
docs/matriz_equivalencia.md seccion 8) e identificado como tal aca mismo.
Esto valida que el motor corre de punta a punta y que su propio control de
totales interno cierra; no certifica equivalencia con ADF (no hay salida ADF
real de este lote para comparar con compare-adf).
"""

from __future__ import annotations

import json

from etl_pmc.audit.result import EstadoEjecucion
from etl_pmc.formatting.output import LARGO_REGISTRO
from etl_pmc.manifest import parsear_manifiesto
from etl_pmc.pipeline import ejecutar
from etl_pmc.storage.local import LocalStorageAdapter


def _manifiesto_dict() -> dict:
    return {
        "schema_version": "1.0",
        "run_id": "test-run-001",
        "pipeline_run_id": "test-pipeline-run-001",
        "lote_id": "LOTE_REAL001",
        "profile": "poc_pmc",
        "storage_account_url": "https://storagelocal.invalid",
        "input": {"container": "inbound", "blob": "sap/demo/lote_real001/entrada_real_1000.txt", "etag": None},
        "enrichment": {
            "container": "enrichment",
            "blob": "sap/demo/lote_real001/enrichment.csv",
            "mode": "single_configuration",
        },
        "output": {
            "container": "out",
            "prefix": "pmc/containerapp/demo/lote_real001",
            "filename": "FAC0001.220926",
        },
        "audit": {"container": "audit", "prefix": "containerapp/demo/lote_real001"},
        "errors": {"container": "error", "prefix": "containerapp/demo/lote_real001"},
        "parameters": {
            "CodBancoPMC": "001",
            "CodigoServicioPMC": "0001",
            "TipoRegistroCabPMC": "0",
            "TipoRegistroDetPMC": "1",
            "TipoRegistroPiePMC": "9",
            "AplicarFiltro30Dias": False,
            "AplicarMaxDosCliente": False,
            "CuotaPMC": "01",
            "FechaEjecucionUTC": "2026-09-22T12:00:00Z",
        },
        "format": {
            "input_encoding": "utf-8",
            "output_encoding": "utf-8",
            "output_newline": "CRLF",
            "output_bom": False,
            "final_newline": True,
        },
    }


def _preparar_storage(tmp_path, real_sample_path) -> LocalStorageAdapter:
    storage = LocalStorageAdapter(tmp_path)
    contenido_entrada = real_sample_path.read_bytes()
    storage.escribir_bytes("inbound", "sap/demo/lote_real001/entrada_real_1000.txt", contenido_entrada)

    # CSV de enriquecimiento SINTETICO (no es un extracto real de
    # PL_EXTRAER_SQL), pero usa el unico dato real disponible de la Tabla
    # Intermedia citado en GDC-1000: CodEntidad="324", Descripcion="Pago Mis
    # Cuentas". CodBanco/CodigoServicio siguen siendo valores de POC, no
    # confirmados (prompt seccion 17).
    csv_sintetico = (
        "CodEntidad,Descripcion,CodBanco,CodigoServicio\r\n"
        "324,Pago Mis Cuentas,001,0001\r\n"
    ).encode("utf-8")
    storage.escribir_bytes("enrichment", "sap/demo/lote_real001/enrichment.csv", csv_sintetico)
    return storage


def test_pipeline_end_to_end_contra_archivo_real(tmp_path, real_sample_path):
    storage = _preparar_storage(tmp_path, real_sample_path)
    manifiesto = parsear_manifiesto(_manifiesto_dict())

    resultado = ejecutar(manifiesto, storage)

    assert resultado.estado == EstadoEjecucion.SUCCEEDED
    assert resultado.cantidad_leida == 1002
    assert resultado.cantidad_valida == 1000
    assert resultado.cantidad_rechazada == 0
    assert resultado.cantidad_excluida_negocio == 0
    assert resultado.cantidad_emitida == 1000
    assert resultado.control_cabecera_valido is True
    assert resultado.control_archivo_valido is True
    assert resultado.importe_total_calculado == resultado.importe_total_declarado
    assert resultado.hash_entrada is not None
    assert resultado.hash_enriquecimiento is not None

    salida_path = tmp_path / "out" / "pmc" / "containerapp" / "demo" / "lote_real001" / "FAC0001.220926"
    assert salida_path.is_file()
    contenido = salida_path.read_bytes()

    texto = contenido.decode("utf-8")
    assert texto.endswith("\r\n")
    lineas = texto[:-2].split("\r\n")
    assert len(lineas) == 1002  # cabecera + 1000 detalles + pie
    assert all(len(l) == LARGO_REGISTRO for l in lineas)
    assert lineas[0][0] == "0"  # TipoRegistroCabPMC
    assert lineas[-1][0] == "9"  # TipoRegistroPiePMC
    assert all(l[0] == "1" for l in lineas[1:-1])  # TipoRegistroDetPMC

    # cantidad emitida en el pie (posiciones 17-23, 1-based)
    assert lineas[-1][16:23] == "0001000"

    marca_path = tmp_path / "audit" / "containerapp" / "demo" / "lote_real001" / "idempotencia.json"
    assert marca_path.is_file()


def test_pipeline_es_idempotente_en_la_segunda_corrida(tmp_path, real_sample_path):
    storage = _preparar_storage(tmp_path, real_sample_path)
    manifiesto = parsear_manifiesto(_manifiesto_dict())

    primer_resultado = ejecutar(manifiesto, storage)
    assert primer_resultado.estado == EstadoEjecucion.SUCCEEDED

    segundo_resultado = ejecutar(manifiesto, storage)
    assert segundo_resultado.estado == EstadoEjecucion.ALREADY_PROCESSED


def test_pipeline_rechaza_si_falta_csv_de_enriquecimiento(tmp_path, real_sample_path):
    storage = LocalStorageAdapter(tmp_path)
    storage.escribir_bytes(
        "inbound", "sap/demo/lote_real001/entrada_real_1000.txt", real_sample_path.read_bytes()
    )
    manifiesto = parsear_manifiesto(_manifiesto_dict())

    resultado = ejecutar(manifiesto, storage)

    assert resultado.estado == EstadoEjecucion.REJECTED
    assert "ARCHIVO_FALTANTE" in resultado.motivos_rechazo_globales
    assert resultado.ruta_errores is not None
