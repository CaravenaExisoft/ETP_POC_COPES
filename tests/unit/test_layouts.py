from __future__ import annotations

import pytest

from etl_pmc.config.layouts import FieldSpec, load_layout
from etl_pmc.errors import LayoutError


def test_load_poc_pmc_layout():
    layout = load_layout("poc_pmc")
    assert layout.profile == "poc_pmc"
    assert layout.record_types["cabecera"].length == 88
    assert layout.record_types["detalle"].length == 713
    assert layout.record_types["pie"].length == 24


def test_adf_actual_not_available():
    with pytest.raises(LayoutError):
        load_layout("adf_actual")


def test_unknown_profile_raises():
    with pytest.raises(LayoutError):
        load_layout("no_existe")


def test_field_slice_is_zero_based():
    f = FieldSpec(name="x", start=1, length=1, kind="text", estado="SUPUESTO_POC")
    assert f.slice() == slice(0, 1)
    assert f.extract_raw("ABC") == "A"


def test_field_slice_matches_1based_positions():
    # posicion 58, longitud 8 -> caracteres 58..65 inclusive (1-based)
    f = FieldSpec(name="referencia_cliente", start=58, length=8, kind="text", estado="SUPUESTO_POC")
    linea = "0" * 57 + "12345678" + "9" * 10
    assert f.extract_raw(linea) == "12345678"
    assert f.end == 65


def test_text_trim_strips_only_that_field():
    f = FieldSpec(name="concepto", start=1, length=6, kind="text_trim", estado="SUPUESTO_POC")
    assert f.extract_raw("  hi  resto") == "hi"


def test_field_rejects_non_1based_start():
    with pytest.raises(LayoutError):
        FieldSpec(name="x", start=0, length=1, kind="text", estado="SUPUESTO_POC")


def test_layout_rejects_field_exceeding_record_length(poc_pmc_layout):
    from dataclasses import replace

    campo_invalido = replace(poc_pmc_layout.detalle_fields[0], start=1, length=10_000)
    layout_roto = replace(poc_pmc_layout, detalle_fields=(campo_invalido,))
    with pytest.raises(LayoutError):
        layout_roto.validate_against_record_length()
