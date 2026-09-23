from __future__ import annotations

from etl_pmc.tools.compare_adf import comparar_bytes, comparar_csv_errores, comparar_semantico


def _linea_detalle(referencia_cliente: str = "10855959") -> str:
    return ("1" + referencia_cliente.ljust(19) + "0" * (280 - 20)).ljust(280, "0")[:280]


def _archivo(lineas: list[str]) -> bytes:
    return ("\r\n".join(lineas) + "\r\n").encode("utf-8")


def test_archivos_identicos():
    cabecera = "0" + "0" * 279
    pie = "9" + "0" * 279
    contenido = _archivo([cabecera, _linea_detalle(), pie])
    resultado = comparar_bytes(contenido, contenido)
    assert resultado.identicos_bytes is True
    assert resultado.primera_diferencia is None


def test_detecta_primera_diferencia_en_referencia_cliente():
    cabecera = "0" + "0" * 279
    pie = "9" + "0" * 279
    adf = _archivo([cabecera, _linea_detalle("10855959"), pie])
    container = _archivo([cabecera, _linea_detalle("99999999"), pie])

    resultado = comparar_bytes(adf, container)
    assert resultado.identicos_bytes is False
    assert resultado.primera_diferencia["numero_linea"] == 2
    assert resultado.primera_diferencia["campo"] == "ReferenciaCliente"


def test_redact_oculta_referencia_cliente():
    cabecera = "0" + "0" * 279
    pie = "9" + "0" * 279
    adf = _archivo([cabecera, _linea_detalle("10855959"), pie])
    container = _archivo([cabecera, _linea_detalle("99999999"), pie])

    resultado = comparar_bytes(adf, container, redactar=True)
    assert "10855959" not in resultado.primera_diferencia["linea_adf"]
    assert "99999999" not in resultado.primera_diferencia["linea_container"]
    # ReferenciaCliente (posiciones 2-20) queda enmascarado salvo los ultimos
    # 2 caracteres, que en este fixture son espacios de relleno.
    assert resultado.primera_diferencia["linea_adf"][1:20] == "*" * 17 + "  "


def test_diferente_cantidad_de_lineas():
    cabecera = "0" + "0" * 279
    pie = "9" + "0" * 279
    detalle = _linea_detalle()
    adf = _archivo([cabecera, detalle, pie])
    container = _archivo([cabecera, detalle])  # falta el pie, pero lo comun coincide

    resultado = comparar_bytes(adf, container)
    assert resultado.cantidad_lineas_adf == 3
    assert resultado.cantidad_lineas_container == 2
    assert "cantidad" in resultado.primera_diferencia.get("motivo", "")


def test_newline_distinto_se_detecta():
    contenido_crlf = b"AAA\r\nBBB\r\n"
    contenido_lf = b"AAA\nBBB\n"
    resultado = comparar_bytes(contenido_crlf, contenido_lf)
    assert resultado.newline_adf == "CRLF"
    assert resultado.newline_container == "LF"


def test_comparacion_semantica_ignora_orden():
    cabecera = "CAB"
    pie = "PIE"
    lineas_adf = [cabecera, "det-1", "det-2", pie]
    lineas_container = [cabecera, "det-2", "det-1", pie]
    resultado = comparar_semantico(lineas_adf, lineas_container)
    assert resultado["cabecera_igual"] is True
    assert resultado["pie_igual"] is True
    assert resultado["detalles_solo_en_adf"] == 0
    assert resultado["detalles_solo_en_container"] == 0
    assert resultado["detalles_coincidentes"] == 2


def test_comparacion_csv_errores_multiconjunto():
    filas_adf = [{"a": "1"}, {"a": "1"}, {"a": "2"}]
    filas_container = [{"a": "2"}, {"a": "1"}, {"a": "1"}]
    resultado = comparar_csv_errores(filas_adf, filas_container)
    assert resultado["identico_como_multiconjunto"] is True


def test_comparacion_csv_errores_detecta_diferencia_de_multiplicidad():
    filas_adf = [{"a": "1"}, {"a": "1"}]
    filas_container = [{"a": "1"}]
    resultado = comparar_csv_errores(filas_adf, filas_container)
    assert resultado["identico_como_multiconjunto"] is False
    assert resultado["solo_en_adf"] == 1
