from __future__ import annotations

import copy
import json

import pytest

from etl_pmc.errors import ConfigurationError
from etl_pmc.manifest import cargar_manifiesto_desde_texto, parsear_manifiesto


def _manifiesto_valido() -> dict:
    return {
        "schema_version": "1.0",
        "run_id": "poc-lote-real001-ca-001",
        "pipeline_run_id": "identificador-de-ejecucion-adf",
        "lote_id": "LOTE_REAL001",
        "profile": "poc_pmc",
        "storage_account_url": "https://storagepoc.blob.core.windows.net",
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


def test_manifiesto_valido_parsea_ok():
    m = parsear_manifiesto(_manifiesto_valido())
    assert m.profile == "poc_pmc"
    assert m.parameters.aplicar_filtro_30_dias is False
    assert m.enrichment.mode == "single_configuration"
    assert m.format.output_newline == "CRLF"


def test_json_invalido():
    with pytest.raises(ConfigurationError):
        cargar_manifiesto_desde_texto("{no es json")


def test_falta_campo_obligatorio():
    data = _manifiesto_valido()
    del data["run_id"]
    with pytest.raises(ConfigurationError):
        parsear_manifiesto(data)


def test_placeholder_sin_reemplazar():
    data = _manifiesto_valido()
    data["storage_account_url"] = "https://<storage>.blob.core.windows.net"
    with pytest.raises(ConfigurationError):
        parsear_manifiesto(data)


def test_booleano_como_string_no_se_interpreta_como_true():
    data = _manifiesto_valido()
    data["parameters"]["AplicarFiltro30Dias"] = "false"
    with pytest.raises(ConfigurationError):
        parsear_manifiesto(data)


def test_perfil_desconocido():
    data = _manifiesto_valido()
    data["profile"] = "no_existe"
    with pytest.raises(ConfigurationError):
        parsear_manifiesto(data)


def test_cod_banco_pmc_ancho_incorrecto():
    data = _manifiesto_valido()
    data["parameters"]["CodBancoPMC"] = "1"
    with pytest.raises(ConfigurationError):
        parsear_manifiesto(data)


def test_ruta_con_traversal_es_rechazada():
    data = _manifiesto_valido()
    data["input"]["blob"] = "sap/../../etc/passwd"
    with pytest.raises(ConfigurationError):
        parsear_manifiesto(data)


def test_ruta_absoluta_es_rechazada():
    data = _manifiesto_valido()
    data["input"]["blob"] = "/etc/passwd"
    with pytest.raises(ConfigurationError):
        parsear_manifiesto(data)


def test_newline_invalido():
    data = _manifiesto_valido()
    data["format"]["output_newline"] = "CR"
    with pytest.raises(ConfigurationError):
        parsear_manifiesto(data)


def test_enrichment_mode_desconocido():
    data = _manifiesto_valido()
    data["enrichment"]["mode"] = "otro"
    with pytest.raises(ConfigurationError):
        parsear_manifiesto(data)


def test_record_join_sin_configuracion_falla():
    data = _manifiesto_valido()
    data["enrichment"]["mode"] = "record_join"
    with pytest.raises(ConfigurationError):
        parsear_manifiesto(data)


def test_record_join_con_configuracion_completa_ok():
    data = _manifiesto_valido()
    data["enrichment"]["mode"] = "record_join"
    data["enrichment"]["record_join"] = {
        "columna_clave_csv": "IdDeuda",
        "columnas_a_incorporar": ["CodEntidad", "DescripcionEntidad"],
    }
    m = parsear_manifiesto(data)
    assert m.enrichment.columna_clave_csv == "IdDeuda"
    assert m.enrichment.columnas_a_incorporar == ("CodEntidad", "DescripcionEntidad")


def test_fecha_ejecucion_invalida():
    data = _manifiesto_valido()
    data["parameters"]["FechaEjecucionUTC"] = "no-es-fecha"
    with pytest.raises(ConfigurationError):
        parsear_manifiesto(data)


def test_manifiesto_completo_desde_texto_json():
    texto = json.dumps(_manifiesto_valido())
    m = cargar_manifiesto_desde_texto(texto)
    assert m.run_id == "poc-lote-real001-ca-001"
