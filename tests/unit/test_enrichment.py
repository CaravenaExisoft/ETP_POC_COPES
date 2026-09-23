from __future__ import annotations

import pytest

from etl_pmc.enrichment.record_join import ConfiguracionRecordJoin, construir_indice, enriquecer
from etl_pmc.enrichment.single_configuration import (
    cargar_single_configuration,
    resolver_codigos_finales,
)
from etl_pmc.errors import EnrichmentError


def test_single_configuration_ok():
    filas = [
        {
            "CodEntidad": "324",
            "Descripcion": "Pago Mis Cuentas",
            "CodBanco": "001",
            "CodigoServicio": "0001",
        }
    ]
    config = cargar_single_configuration(filas)
    assert config.cod_entidad == "324"
    banco, servicio = resolver_codigos_finales(config, cod_banco_parametro="999", codigo_servicio_parametro="9999")
    assert (banco, servicio) == ("001", "0001")


def test_single_configuration_fallback_a_parametros_si_csv_nulo():
    filas = [{"CodEntidad": "X", "Descripcion": "Y", "CodBanco": None, "CodigoServicio": None}]
    config = cargar_single_configuration(filas)
    banco, servicio = resolver_codigos_finales(config, cod_banco_parametro="999", codigo_servicio_parametro="9999")
    assert (banco, servicio) == ("999", "9999")


def test_single_configuration_aplica_trim_antes_de_mapear():
    # GDC-1000 seccion C: "Antes de mapear, se aplica TRIM a los valores de
    # la tabla intermedia".
    filas = [{"CodEntidad": "  324  ", "Descripcion": " Pago Mis Cuentas ", "CodBanco": " 001 ", "CodigoServicio": " 0001 "}]
    config = cargar_single_configuration(filas)
    assert config.cod_entidad == "324"
    assert config.descripcion == "Pago Mis Cuentas"
    assert config.cod_banco == "001"
    assert config.codigo_servicio == "0001"


def test_single_configuration_solo_espacios_es_valor_vacio_tras_trim():
    filas = [{"CodEntidad": "   ", "Descripcion": "Y", "CodBanco": "1", "CodigoServicio": "1"}]
    with pytest.raises(EnrichmentError) as exc:
        cargar_single_configuration(filas)
    assert exc.value.codigo == "VALOR_VACIO"


def test_single_configuration_archivo_faltante():
    with pytest.raises(EnrichmentError) as exc:
        cargar_single_configuration(None)
    assert exc.value.codigo == "ARCHIVO_FALTANTE"


def test_single_configuration_csv_vacio():
    with pytest.raises(EnrichmentError) as exc:
        cargar_single_configuration([])
    assert exc.value.codigo == "CSV_VACIO"


def test_single_configuration_columna_ausente():
    with pytest.raises(EnrichmentError) as exc:
        cargar_single_configuration([{"CodEntidad": "X"}])
    assert exc.value.codigo == "COLUMNA_AUSENTE"


def test_single_configuration_valor_vacio():
    filas = [{"CodEntidad": "", "Descripcion": "Y", "CodBanco": "1", "CodigoServicio": "1"}]
    with pytest.raises(EnrichmentError) as exc:
        cargar_single_configuration(filas)
    assert exc.value.codigo == "VALOR_VACIO"


def test_single_configuration_multiples_filas_no_hace_top1_arbitrario():
    filas = [
        {"CodEntidad": "A", "Descripcion": "a", "CodBanco": "1", "CodigoServicio": "1"},
        {"CodEntidad": "B", "Descripcion": "b", "CodBanco": "2", "CodigoServicio": "2"},
    ]
    with pytest.raises(EnrichmentError) as exc:
        cargar_single_configuration(filas)
    assert exc.value.codigo == "MULTIPLES_FILAS"


def test_record_join_indice_y_lookup():
    config = ConfiguracionRecordJoin(columna_clave_csv="IdDeuda", columnas_a_incorporar=("CodEntidad",))
    filas = [{"IdDeuda": "1", "CodEntidad": "A"}, {"IdDeuda": "2", "CodEntidad": "B"}]
    indice = construir_indice(filas, config)
    assert enriquecer("1", indice) == {"CodEntidad": "A"}
    assert enriquecer("999", indice) is None


def test_record_join_clave_duplicada_es_error():
    config = ConfiguracionRecordJoin(columna_clave_csv="IdDeuda", columnas_a_incorporar=("CodEntidad",))
    filas = [{"IdDeuda": "1", "CodEntidad": "A"}, {"IdDeuda": "1", "CodEntidad": "B"}]
    with pytest.raises(EnrichmentError) as exc:
        construir_indice(filas, config)
    assert exc.value.codigo == "CLAVE_DUPLICADA"


def test_record_join_columna_ausente():
    config = ConfiguracionRecordJoin(columna_clave_csv="IdDeuda", columnas_a_incorporar=("NoExiste",))
    with pytest.raises(EnrichmentError) as exc:
        construir_indice([{"IdDeuda": "1"}], config)
    assert exc.value.codigo == "COLUMNA_AUSENTE"
