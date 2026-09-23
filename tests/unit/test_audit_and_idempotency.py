from __future__ import annotations

import json
from decimal import Decimal

from etl_pmc.audit.errors import CATEGORIA_NEGOCIO, FilaError, escribir_csv_errores
from etl_pmc.audit.result import EstadoEjecucion, ResultadoEjecucion
from etl_pmc.idempotency import ClaveIdempotencia, construir_marca, marca_ya_procesado


def test_escribir_csv_errores_escapa_correctamente():
    filas = [
        FilaError(run_id="r1", archivo="f.txt", numero_linea=5, categoria=CATEGORIA_NEGOCIO, codigo="X", campo="importe", motivo='contiene, coma y "comillas"'),
    ]
    csv_bytes = escribir_csv_errores(filas)
    texto = csv_bytes.decode("utf-8")
    assert "run_id" in texto.splitlines()[0]
    assert '"contiene, coma y ""comillas"""' in texto


def test_resultado_ejecucion_to_dict_serializa_decimal_como_string():
    resultado = ResultadoEjecucion(
        estado=EstadoEjecucion.SUCCEEDED,
        run_id="r1",
        pipeline_run_id="p1",
        lote_id="L1",
        version_codigo="0.1.0",
        profile="poc_pmc",
        layout_version=1,
        importe_total_calculado=Decimal("100.50"),
    )
    d = resultado.to_dict()
    assert d["importe_total_calculado"] == "100.50"
    assert d["estado"] == "SUCCEEDED"
    json.dumps(d)  # no debe fallar
    assert resultado.codigo_salida() == 0


def test_resultado_failed_tiene_codigo_de_salida_no_cero():
    resultado = ResultadoEjecucion(
        estado=EstadoEjecucion.FAILED,
        run_id="r1",
        pipeline_run_id="p1",
        lote_id="L1",
        version_codigo="0.1.0",
        profile="poc_pmc",
        layout_version=1,
    )
    assert resultado.codigo_salida() != 0


def test_idempotencia_misma_clave_es_ya_procesado():
    clave = ClaveIdempotencia(
        hash_entrada="abc",
        hash_enriquecimiento="def",
        profile="poc_pmc",
        layout_version=1,
        parametros_relevantes={"AplicarFiltro30Dias": False},
    )
    marca = construir_marca(clave, run_id="run-1")
    assert marca_ya_procesado(marca, clave) is True


def test_idempotencia_distinta_entrada_no_es_ya_procesado():
    clave1 = ClaveIdempotencia("abc", "def", "poc_pmc", 1, {})
    clave2 = ClaveIdempotencia("otro-hash", "def", "poc_pmc", 1, {})
    marca = construir_marca(clave1, run_id="run-1")
    assert marca_ya_procesado(marca, clave2) is False


def test_idempotencia_sin_marca_previa():
    clave = ClaveIdempotencia("abc", "def", "poc_pmc", 1, {})
    assert marca_ya_procesado(None, clave) is False
