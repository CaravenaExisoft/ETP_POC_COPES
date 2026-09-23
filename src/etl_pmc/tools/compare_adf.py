"""compare-adf (prompt seccion 16): compara la salida de ADF contra la del
Container App para el mismo lote.

Orden de verificacion: SHA-256 y bytes completos primero; recien si difieren
se calcula un reporte de primera diferencia (linea, posicion, campo segun el
layout de salida de 280 posiciones). No normaliza ni reordena nada para
declarar igualdad exacta -- eso solo pasa, explicitamente, en --semantic.
Sin una salida ADF real de un lote, este comparador solo puede probarse
contra fixtures sinteticas (ver docs/matriz_equivalencia.md seccion 12).
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import sys
from collections import Counter
from dataclasses import dataclass

# Campos de salida (prompt seccion 10). Se usan solo para nombrar la primera
# diferencia en un reporte, no para reinterpretar el contenido.
_CAMPOS_DETALLE = [
    ("TipoRegistroDetPMC", 1, 1),
    ("ReferenciaCliente", 2, 19),
    ("IdDeuda", 21, 20),
    ("CodigoMonedaSalida", 41, 1),
    ("PrimerVencimiento", 42, 8),
    ("PrimerImporteCentavos", 50, 11),
    ("SegundoVencimiento", 61, 8),
    ("SegundoImporteCentavos", 69, 11),
    ("TercerVencimiento", 80, 8),
    ("TercerImporteCentavos", 88, 11),
    ("Reservado_99_117", 99, 19),
    ("ReferenciaAnterior", 118, 19),
    ("MensajeTicket", 137, 40),
    ("MensajePantalla", 177, 15),
    ("EspacioCodigoBarras", 192, 60),
    ("Reservado_252_280", 252, 29),
]

_CAMPOS_CABECERA = [
    ("TipoRegistroCabPMC", 1, 1),
    ("CodBancoFinal", 2, 3),
    ("CodigoServicioFinal", 5, 4),
    ("FechaCabecera", 9, 8),
    ("Literal1", 17, 1),
    ("Reservado_18_280", 18, 263),
]

_CAMPOS_PIE = [
    ("TipoRegistroPiePMC", 1, 1),
    ("CodBancoFinal", 2, 3),
    ("CodigoServicioFinal", 5, 4),
    ("FechaCabecera", 9, 8),
    ("CantidadEmitidos", 17, 7),
    ("Reservado_24_30", 24, 7),
    ("SumaPrimerImporteCentavos", 31, 16),
    ("Reservado_47_280", 47, 234),
]

# Campos que se redactan en --redact para no exponer datos personales
# completos en el reporte (prompt seccion 16).
_CAMPOS_SENSIBLES = {"ReferenciaCliente", "IdDeuda", "ReferenciaAnterior"}


def _campo_en_posicion(campos: list[tuple[str, int, int]], posicion_1based: int) -> str | None:
    for nombre, inicio, largo in campos:
        if inicio <= posicion_1based < inicio + largo:
            return nombre
    return None


def _campos_para_linea(indice_linea: int, total_lineas: int) -> list[tuple[str, int, int]]:
    if indice_linea == 0:
        return _CAMPOS_CABECERA
    if indice_linea == total_lineas - 1:
        return _CAMPOS_PIE
    return _CAMPOS_DETALLE


def _redactar(valor: str) -> str:
    if len(valor) <= 2:
        return "*" * len(valor)
    return "*" * (len(valor) - 2) + valor[-2:]


@dataclass
class ResultadoComparacion:
    identicos_bytes: bool
    sha256_adf: str
    sha256_container: str
    tamano_adf: int
    tamano_container: int
    newline_adf: str
    newline_container: str
    primera_diferencia: dict | None
    cantidad_lineas_adf: int
    cantidad_lineas_container: int


def _detectar_newline(contenido: bytes) -> str:
    if b"\r\n" in contenido:
        return "CRLF"
    if b"\n" in contenido:
        return "LF"
    return "SIN_TERMINADOR"


def comparar_bytes(contenido_adf: bytes, contenido_container: bytes, *, redactar: bool = False) -> ResultadoComparacion:
    sha_adf = hashlib.sha256(contenido_adf).hexdigest()
    sha_container = hashlib.sha256(contenido_container).hexdigest()
    identicos = sha_adf == sha_container

    newline_adf = _detectar_newline(contenido_adf)
    newline_container = _detectar_newline(contenido_container)

    lineas_adf = contenido_adf.decode("utf-8", errors="replace").split("\r\n" if newline_adf == "CRLF" else "\n")
    lineas_adf = [l for l in lineas_adf if l != ""]
    lineas_container = contenido_container.decode("utf-8", errors="replace").split(
        "\r\n" if newline_container == "CRLF" else "\n"
    )
    lineas_container = [l for l in lineas_container if l != ""]

    primera_diferencia = None
    if not identicos:
        primera_diferencia = _primera_diferencia(lineas_adf, lineas_container, redactar=redactar)

    return ResultadoComparacion(
        identicos_bytes=identicos,
        sha256_adf=sha_adf,
        sha256_container=sha_container,
        tamano_adf=len(contenido_adf),
        tamano_container=len(contenido_container),
        newline_adf=newline_adf,
        newline_container=newline_container,
        primera_diferencia=primera_diferencia,
        cantidad_lineas_adf=len(lineas_adf),
        cantidad_lineas_container=len(lineas_container),
    )


def _primera_diferencia(lineas_adf: list[str], lineas_container: list[str], *, redactar: bool) -> dict:
    total_adf = len(lineas_adf)
    total_container = len(lineas_container)
    n = min(total_adf, total_container)

    for i in range(n):
        if lineas_adf[i] != lineas_container[i]:
            a, c = lineas_adf[i], lineas_container[i]
            pos = next((j for j in range(min(len(a), len(c))) if a[j] != c[j]), min(len(a), len(c)))
            campos = _campos_para_linea(i, max(total_adf, total_container))
            campo = _campo_en_posicion(campos, pos + 1)

            valor_adf = a
            valor_container = c
            if redactar and campo in _CAMPOS_SENSIBLES:
                nombre, inicio, largo = next(f for f in campos if f[0] == campo)
                valor_adf = a[: inicio - 1] + _redactar(a[inicio - 1 : inicio - 1 + largo]) + a[inicio - 1 + largo :]
                valor_container = (
                    c[: inicio - 1] + _redactar(c[inicio - 1 : inicio - 1 + largo]) + c[inicio - 1 + largo :]
                )

            return {
                "numero_linea": i + 1,
                "posicion_1based": pos + 1,
                "campo": campo,
                "longitud_adf": len(a),
                "longitud_container": len(c),
                "linea_adf": valor_adf,
                "linea_container": valor_container,
            }

    return {
        "numero_linea": n + 1,
        "posicion_1based": None,
        "campo": None,
        "motivo": f"un archivo tiene {total_adf} lineas y el otro {total_container}; no coinciden en cantidad",
    }


def comparar_semantico(lineas_adf: list[str], lineas_container: list[str]) -> dict:
    """Comparacion adicional, claramente no exacta: multiset de detalles
    (ignora orden), asumiendo que la primera y ultima linea son
    cabecera/pie. No declara igualdad exacta de archivo."""
    detalles_adf = Counter(lineas_adf[1:-1])
    detalles_container = Counter(lineas_container[1:-1])
    return {
        "advertencia": "comparacion semantica (multiset sin orden), no reemplaza la comparacion exacta de bytes",
        "cabecera_igual": lineas_adf[0] == lineas_container[0] if lineas_adf and lineas_container else False,
        "pie_igual": lineas_adf[-1] == lineas_container[-1] if lineas_adf and lineas_container else False,
        "detalles_solo_en_adf": sum((detalles_adf - detalles_container).values()),
        "detalles_solo_en_container": sum((detalles_container - detalles_adf).values()),
        "detalles_coincidentes": sum((detalles_adf & detalles_container).values()),
    }


def comparar_csv_errores(filas_adf: list[dict], filas_container: list[dict]) -> dict:
    """Los CSV de error pueden salir en orden no determinista en ADF: se
    comparan como multiconjuntos con multiplicidad (prompt seccion 16)."""

    def _clave(fila: dict) -> tuple:
        return tuple(sorted(fila.items()))

    contador_adf = Counter(_clave(f) for f in filas_adf)
    contador_container = Counter(_clave(f) for f in filas_container)
    return {
        "identico_como_multiconjunto": contador_adf == contador_container,
        "solo_en_adf": sum((contador_adf - contador_container).values()),
        "solo_en_container": sum((contador_container - contador_adf).values()),
    }


def _construir_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="compare-adf", description="Compara salida ADF vs Container App para el mismo lote")
    parser.add_argument("--adf", required=True, help="Ruta al archivo de salida generado por ADF")
    parser.add_argument("--container", required=True, help="Ruta al archivo de salida generado por el Container App")
    parser.add_argument("--redact", action="store_true", help="Redacta campos con datos personales en el reporte de diferencias")
    parser.add_argument("--semantic", action="store_true", help="Ademas de la comparacion exacta, reporta una comparacion semantica (multiset, sin orden)")
    parser.add_argument("--errors-adf", help="CSV de errores de ADF, para comparar como multiconjunto")
    parser.add_argument("--errors-container", help="CSV de errores del Container App, para comparar como multiconjunto")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _construir_parser().parse_args(argv)

    with open(args.adf, "rb") as fh:
        contenido_adf = fh.read()
    with open(args.container, "rb") as fh:
        contenido_container = fh.read()

    resultado = comparar_bytes(contenido_adf, contenido_container, redactar=args.redact)

    print(f"SHA-256 ADF:       {resultado.sha256_adf}")
    print(f"SHA-256 Container: {resultado.sha256_container}")
    print(f"Tamano ADF:        {resultado.tamano_adf} bytes ({resultado.cantidad_lineas_adf} lineas, newline={resultado.newline_adf})")
    print(f"Tamano Container:  {resultado.tamano_container} bytes ({resultado.cantidad_lineas_container} lineas, newline={resultado.newline_container})")

    if resultado.identicos_bytes:
        print("RESULTADO: IDENTICOS byte a byte.")
    else:
        print("RESULTADO: DIFIEREN.")
        print(f"Primera diferencia: {resultado.primera_diferencia}")
        if resultado.newline_adf != resultado.newline_container:
            print("DIAGNOSTICO: los estilos de fin de linea difieren (CRLF vs LF) -- revisar format.output_newline del manifiesto.")

    if args.semantic:
        newline_a = "\r\n" if resultado.newline_adf == "CRLF" else "\n"
        newline_c = "\r\n" if resultado.newline_container == "CRLF" else "\n"
        lineas_a = [l for l in contenido_adf.decode("utf-8", errors="replace").split(newline_a) if l]
        lineas_c = [l for l in contenido_container.decode("utf-8", errors="replace").split(newline_c) if l]
        print(f"Comparacion semantica: {comparar_semantico(lineas_a, lineas_c)}")

    if args.errors_adf and args.errors_container:
        with open(args.errors_adf, newline="", encoding="utf-8") as fh:
            filas_adf = list(csv.DictReader(fh))
        with open(args.errors_container, newline="", encoding="utf-8") as fh:
            filas_container = list(csv.DictReader(fh))
        print(f"Comparacion CSV de errores (multiconjunto): {comparar_csv_errores(filas_adf, filas_container)}")

    return 0 if resultado.identicos_bytes else 1


if __name__ == "__main__":
    raise SystemExit(main())
