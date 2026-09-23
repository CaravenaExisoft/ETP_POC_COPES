from __future__ import annotations

import json

from etl_pmc.cli import main
from etl_pmc.storage.local import LocalStorageAdapter
from tests.integration.test_pipeline_end_to_end import _manifiesto_dict, _preparar_storage


def test_cli_run_modo_local_contra_archivo_real(tmp_path, real_sample_path, capsys):
    _preparar_storage(tmp_path, real_sample_path)

    manifiesto_path = tmp_path / "manifiesto.json"
    manifiesto_path.write_text(json.dumps(_manifiesto_dict()), encoding="utf-8")

    resultado_path = tmp_path / "resultado.json"

    codigo = main(
        [
            "run",
            "--manifest",
            str(manifiesto_path),
            "--local-root",
            str(tmp_path),
            "--result-out",
            str(resultado_path),
        ]
    )

    assert codigo == 0
    salida = json.loads(capsys.readouterr().out)
    assert salida["estado"] == "SUCCEEDED"
    assert salida["cantidad_emitida"] == 1000

    assert resultado_path.is_file()
    assert json.loads(resultado_path.read_text(encoding="utf-8"))["run_id"] == "test-run-001"


def test_cli_modo_azure_sin_storage_account_url_falla_claro(tmp_path):
    codigo = main(["run", "--manifest", "no-existe-localmente/manifiesto.json"])
    assert codigo == 1


def test_cli_manifiesto_invalido_devuelve_codigo_1(tmp_path):
    manifiesto_path = tmp_path / "manifiesto.json"
    manifiesto_path.write_text("{esto no es json valido", encoding="utf-8")

    codigo = main(["run", "--manifest", str(manifiesto_path), "--local-root", str(tmp_path)])

    assert codigo == 1
