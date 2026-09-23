"""Corre el generador sintetico a traves del pipeline completo, para validar
extremo a extremo el manejo de rechazos individuales (SUCCEEDED_WITH_REJECTIONS)
y el rechazo global por importes nulos en la poblacion de control (REJECTED),
sin depender de Azure ni del archivo real."""

from __future__ import annotations

from etl_pmc.audit.result import EstadoEjecucion
from etl_pmc.manifest import parsear_manifiesto
from etl_pmc.pipeline import ejecutar
from etl_pmc.storage.local import LocalStorageAdapter
from etl_pmc.tools.generate_fixture import generar_lote_sintetico
from tests.integration.test_pipeline_end_to_end import _manifiesto_dict


def _preparar_storage_sintetico(tmp_path, lote) -> LocalStorageAdapter:
    storage = LocalStorageAdapter(tmp_path)
    storage.escribir_bytes("inbound", "sap/demo/lote_real001/entrada_real_1000.txt", lote.contenido)
    storage.escribir_bytes("enrichment", "sap/demo/lote_real001/enrichment.csv", lote.csv_enriquecimiento)
    return storage


def test_lote_sintetico_sin_casos_malos_es_exitoso(tmp_path):
    lote = generar_lote_sintetico(cantidad=100, seed=1)
    storage = _preparar_storage_sintetico(tmp_path, lote)
    resultado = ejecutar(parsear_manifiesto(_manifiesto_dict()), storage)

    assert resultado.estado == EstadoEjecucion.SUCCEEDED
    assert resultado.cantidad_leida == 102
    assert resultado.cantidad_valida == 100
    assert resultado.cantidad_emitida == 100


def test_lote_sintetico_con_rechazos_individuales_sigue_publicando(tmp_path):
    lote = generar_lote_sintetico(
        cantidad=100,
        seed=2,
        casos_malos={
            "moneda_invalida": 3,
            "id_deuda_con_letras": 2,
            "referencia_cliente_corta": 2,
            "fecha_invalida_calendario": 1,
            "longitud_incorrecta": 1,
        },
    )
    storage = _preparar_storage_sintetico(tmp_path, lote)
    resultado = ejecutar(parsear_manifiesto(_manifiesto_dict()), storage)

    assert resultado.estado == EstadoEjecucion.SUCCEEDED_WITH_REJECTIONS
    assert resultado.control_cabecera_valido is True
    assert resultado.control_archivo_valido is True
    assert resultado.cantidad_leida == 102
    assert resultado.cantidad_rechazada == 9  # los 9 casos malos inyectados
    assert resultado.cantidad_valida == 91
    assert resultado.cantidad_emitida == 91
    assert resultado.ruta_errores is not None


def test_lote_con_importe_corrupto_se_rechaza_a_nivel_archivo(tmp_path):
    # docs/matriz_equivalencia.md seccion 6: cero importes nulos es condicion
    # de todo el archivo, no solo del registro afectado.
    lote = generar_lote_sintetico(cantidad=50, seed=3, casos_malos={"importe_con_punto": 1})
    storage = _preparar_storage_sintetico(tmp_path, lote)
    resultado = ejecutar(parsear_manifiesto(_manifiesto_dict()), storage)

    assert resultado.estado == EstadoEjecucion.REJECTED
    assert resultado.control_archivo_valido is False
    assert "IMPORTES_NULOS_EN_POBLACION" in resultado.motivos_rechazo_globales
