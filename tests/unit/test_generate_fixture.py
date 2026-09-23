from __future__ import annotations

from etl_pmc.tools.generate_fixture import generar_lote_sintetico


def test_generador_es_reproducible_con_la_misma_semilla():
    lote1 = generar_lote_sintetico(cantidad=50, seed=7)
    lote2 = generar_lote_sintetico(cantidad=50, seed=7)
    assert lote1.contenido == lote2.contenido


def test_generador_distinta_semilla_distinto_contenido():
    lote1 = generar_lote_sintetico(cantidad=50, seed=1)
    lote2 = generar_lote_sintetico(cantidad=50, seed=2)
    assert lote1.contenido != lote2.contenido


def test_estructura_basica_del_lote_sin_casos_malos():
    lote = generar_lote_sintetico(cantidad=20, seed=1)
    texto = lote.contenido.decode("utf-8")
    assert texto.endswith("\r\n")
    lineas = [l for l in texto.split("\r\n") if l]
    assert len(lineas) == 22  # cabecera + 20 detalles + pie
    assert lineas[0][0] == "1" and len(lineas[0]) == 88
    assert lineas[-1][0] == "3" and len(lineas[-1]) == 24
    assert all(l[0] == "2" and len(l) == 713 for l in lineas[1:-1])
    assert lote.cantidad_detalles_buenos == 20
    assert lote.casos_malos_inyectados == []


def test_pie_declara_cantidad_y_total_coherentes_con_los_detalles_buenos():
    lote = generar_lote_sintetico(cantidad=30, seed=3)
    texto = lote.contenido.decode("utf-8")
    lineas = [l for l in texto.split("\r\n") if l]
    pie = lineas[-1]
    cantidad_declarada = int(pie[1:9])
    assert cantidad_declarada == lote.cantidad_detalles_buenos == 30


def test_casos_malos_se_inyectan_y_se_reportan():
    lote = generar_lote_sintetico(
        cantidad=20,
        seed=5,
        casos_malos={"moneda_invalida": 2, "id_deuda_con_letras": 1, "longitud_incorrecta": 1},
    )
    assert len(lote.casos_malos_inyectados) == 4
    assert lote.cantidad_detalles_buenos == 16


def test_caso_malo_desconocido_lanza_error():
    import pytest

    with pytest.raises(ValueError):
        generar_lote_sintetico(cantidad=5, seed=1, casos_malos={"no_existe": 1})
