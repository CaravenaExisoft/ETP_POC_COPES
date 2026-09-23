from __future__ import annotations

import pytest

from etl_pmc.storage.local import LocalStorageAdapter


def test_escribir_y_leer(tmp_path):
    adapter = LocalStorageAdapter(tmp_path)
    adapter.escribir_bytes("out", "a/b/c.txt", b"hola")
    assert adapter.existe("out", "a/b/c.txt") is True
    with adapter.abrir_lectura("out", "a/b/c.txt") as fh:
        assert fh.read() == b"hola"


def test_existe_false_si_no_esta(tmp_path):
    adapter = LocalStorageAdapter(tmp_path)
    assert adapter.existe("inbound", "no/existe.txt") is False


def test_rechaza_traversal(tmp_path):
    adapter = LocalStorageAdapter(tmp_path)
    with pytest.raises(ValueError):
        adapter.existe("inbound", "../fuera.txt")


def test_rechaza_absoluta(tmp_path):
    adapter = LocalStorageAdapter(tmp_path)
    with pytest.raises(ValueError):
        adapter.existe("inbound", "/etc/passwd")


def test_escritura_no_deja_temporales(tmp_path):
    adapter = LocalStorageAdapter(tmp_path)
    adapter.escribir_bytes("out", "f.txt", b"x")
    restantes = list((tmp_path / "out").iterdir())
    assert restantes == [tmp_path / "out" / "f.txt"]
