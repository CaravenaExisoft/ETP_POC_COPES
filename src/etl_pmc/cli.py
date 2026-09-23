"""CLI del motor ETL PMC (prompt seccion 4): mismo nucleo de negocio para
modo local y modo Azure. No es un servicio web: se ejecuta una vez y termina
(prompt seccion 1)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from etl_pmc.errors import ConfigurationError
from etl_pmc.manifest import cargar_manifiesto_desde_texto
from etl_pmc.pipeline import ejecutar
from etl_pmc.storage.local import LocalStorageAdapter


def _construir_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="etl-pmc", description="Motor ETL Pago Mis Cuentas (POC)")
    subparsers = parser.add_subparsers(dest="comando", required=True)

    run = subparsers.add_parser("run", help="Ejecuta una corrida a partir de un manifiesto")
    run.add_argument(
        "--manifest",
        required=True,
        help="Ruta local al manifiesto JSON, o 'container/blob' dentro de --storage-account-url en modo Azure",
    )
    run.add_argument(
        "--local-root",
        help="Directorio raiz para modo local: cada container del manifiesto (y del propio --manifest) es una subcarpeta de este directorio",
    )
    run.add_argument(
        "--storage-account-url",
        help=(
            "URL de la cuenta de Storage usada SOLO para descargar el manifiesto en modo Azure "
            "(prompt seccion 4: ADF envia unicamente la ubicacion del manifiesto). "
            "El resto de la corrida usa el 'storage_account_url' declarado dentro del propio manifiesto."
        ),
    )
    run.add_argument(
        "--result-out",
        help="Ruta local donde ademas escribir una copia del JSON de resultado (util para inspeccionar en modo local)",
    )

    return parser


def _cargar_storage(args: argparse.Namespace, storage_account_url: str):
    if args.local_root:
        return LocalStorageAdapter(Path(args.local_root))

    from etl_pmc.storage.azure_blob import AzureBlobStorageAdapter

    return AzureBlobStorageAdapter.desde_url_con_identidad_administrada(storage_account_url)


def _leer_manifiesto_local_o_azure(args: argparse.Namespace) -> str:
    if args.local_root:
        return (Path(args.local_root) / args.manifest).read_text(encoding="utf-8")

    ruta = Path(args.manifest)
    if ruta.exists():
        return ruta.read_text(encoding="utf-8")

    # Modo Azure: --manifest es "container/blob" dentro de --storage-account-url,
    # dado que ADF solo envia la ubicacion del manifiesto (prompt seccion 4).
    if not args.storage_account_url:
        raise ConfigurationError(
            "--manifest no es una ruta local existente; en modo Azure se requiere ademas "
            "--storage-account-url para poder descargarlo (formato --manifest 'container/blob')."
        )
    if "/" not in args.manifest:
        raise ConfigurationError("--manifest en modo Azure debe tener el formato 'container/blob'")

    from etl_pmc.storage.azure_blob import AzureBlobStorageAdapter

    storage_manifiesto = AzureBlobStorageAdapter.desde_url_con_identidad_administrada(args.storage_account_url)
    container, blob = args.manifest.split("/", 1)
    if not storage_manifiesto.existe(container, blob):
        raise ConfigurationError(f"no se encontro el manifiesto en '{container}/{blob}'")
    with storage_manifiesto.abrir_lectura(container, blob) as fh:
        return fh.read().decode("utf-8")


def _run(args: argparse.Namespace) -> int:
    try:
        texto_manifiesto = _leer_manifiesto_local_o_azure(args)
        manifiesto = cargar_manifiesto_desde_texto(texto_manifiesto)
        storage = _cargar_storage(args, manifiesto.storage_account_url)
        resultado = ejecutar(manifiesto, storage)
    except ConfigurationError as exc:
        print(f"ERROR_CONFIGURACION: {exc}", file=sys.stderr)
        return 1

    salida_json = resultado.to_json()
    print(salida_json.decode("utf-8"))
    if args.result_out:
        Path(args.result_out).write_bytes(salida_json)

    return resultado.codigo_salida()


def main(argv: list[str] | None = None) -> int:
    parser = _construir_parser()
    args = parser.parse_args(argv)
    if args.comando == "run":
        return _run(args)
    parser.error(f"comando desconocido: {args.comando}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
