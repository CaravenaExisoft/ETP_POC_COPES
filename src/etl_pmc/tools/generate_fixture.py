"""Generador de lotes sinteticos (prompt seccion 16): semilla reproducible,
cantidad configurable, IDs compatibles con el CSV de enriquecimiento
sintetico, pie calculado DESPUES de generar los detalles, y casos malos
controlados e identificables como tales. Los datos son ficticios: no se usan
para certificar el formato real, solo para probar el motor.
"""

from __future__ import annotations

import argparse
import random
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

_LARGO_CABECERA = 88
_LARGO_DETALLE = 713
_LARGO_PIE = 24

_CONCEPTOS = ("Automotores", "Hogar", "Vida", "Salud", "Comercio")

CASOS_MALOS_DISPONIBLES = (
    "id_deuda_con_letras",
    "moneda_invalida",
    "importe_con_punto",
    "fecha_invalida_calendario",
    "longitud_incorrecta",
    "referencia_cliente_corta",
)


def _rellenar(texto: str, largo: int) -> str:
    return texto.ljust(largo)[:largo]


def _importe_texto_simple(valor: Decimal, digitos_enteros: int) -> str:
    entero = int(valor)
    centavos = int((valor * 100) % 100)
    return str(entero).rjust(digitos_enteros, "0") + "," + str(centavos).rjust(2, "0")


def _construir_detalle(
    *,
    referencia_cliente: str,
    id_deuda: str,
    primer_vencimiento: date,
    moneda: str,
    importe_principal: Decimal,
    nombre_entidad: str,
    concepto: str,
    segundo_vencimiento: date,
    importe_segundo: Decimal,
    tercer_vencimiento: date,
    importe_tercer: Decimal,
) -> str:
    chars = ["0"] * _LARGO_DETALLE
    chars[0] = "2"

    def poner(inicio_1based: int, texto: str) -> None:
        for i, ch in enumerate(texto):
            chars[inicio_1based - 1 + i] = ch

    poner(58, referencia_cliente.rjust(8, "0")[:8])
    poner(103, id_deuda.rjust(9, "0")[:9])
    poner(144, primer_vencimiento.strftime("%Y%m%d"))
    poner(168, moneda[:3].ljust(3))
    poner(173, _importe_texto_simple(importe_principal, 10))
    poner(323, _rellenar(nombre_entidad, 37))
    poner(434, _rellenar(concepto, 28))
    poner(666, segundo_vencimiento.strftime("%Y%m%d"))
    poner(674, _importe_texto_simple(importe_segundo, 10))
    poner(687, tercer_vencimiento.strftime("%Y%m%d"))
    poner(695, _importe_texto_simple(importe_tercer, 10))
    return "".join(chars)


def _construir_cabecera(fecha_cabecera: date) -> str:
    chars = ["0"] * _LARGO_CABECERA
    chars[0] = "1"
    for i, ch in enumerate(fecha_cabecera.strftime("%Y%m%d")):
        chars[1 + i] = ch
    return "".join(chars)


def _construir_pie(cantidad: int, importe_total: Decimal) -> str:
    chars = ["0"] * _LARGO_PIE
    chars[0] = "3"
    for i, ch in enumerate(str(cantidad).rjust(8, "0")):
        chars[1 + i] = ch
    importe_texto = _importe_texto_simple(importe_total, 12)
    for i, ch in enumerate(importe_texto):
        chars[9 + i] = ch
    return "".join(chars)


@dataclass
class LoteSintetico:
    contenido: bytes
    fecha_cabecera: date
    cantidad_detalles_buenos: int
    casos_malos_inyectados: list[str] = field(default_factory=list)
    importe_total_esperado: Decimal = Decimal("0")
    csv_enriquecimiento: bytes = b""


def generar_lote_sintetico(
    *,
    cantidad: int,
    seed: int,
    fecha_cabecera: date | None = None,
    casos_malos: dict[str, int] | None = None,
) -> LoteSintetico:
    if fecha_cabecera is None:
        fecha_cabecera = date(2026, 1, 1)
    rng = random.Random(seed)
    casos_malos = dict(casos_malos or {})
    for caso in casos_malos:
        if caso not in CASOS_MALOS_DISPONIBLES:
            raise ValueError(f"caso malo desconocido: '{caso}'; disponibles: {CASOS_MALOS_DISPONIBLES}")

    lineas: list[str] = []
    casos_inyectados: list[str] = []
    importe_total = Decimal("0")
    cantidad_buenos = 0

    casos_pendientes = [caso for caso, n in casos_malos.items() for _ in range(n)]
    rng.shuffle(casos_pendientes)

    for i in range(cantidad):
        referencia_cliente = str(rng.randint(10_000_000, 99_999_999))
        id_deuda = str(rng.randint(100_000_000, 999_999_999))
        offset_dias = rng.randint(0, 200)
        primer_vencimiento = fecha_cabecera + timedelta(days=offset_dias)
        segundo_vencimiento = primer_vencimiento + timedelta(days=rng.randint(1, 30))
        tercer_vencimiento = segundo_vencimiento + timedelta(days=rng.randint(1, 30))
        importe = Decimal(rng.randint(100, 999_999)) / 100
        concepto = rng.choice(_CONCEPTOS)
        nombre_entidad = f"ENTIDAD SINTETICA {i:04d}"

        caso = casos_pendientes.pop() if casos_pendientes else None

        if caso == "longitud_incorrecta":
            linea = _construir_detalle(
                referencia_cliente=referencia_cliente, id_deuda=id_deuda, primer_vencimiento=primer_vencimiento,
                moneda="ARS", importe_principal=importe, nombre_entidad=nombre_entidad, concepto=concepto,
                segundo_vencimiento=segundo_vencimiento, importe_segundo=importe,
                tercer_vencimiento=tercer_vencimiento, importe_tercer=importe,
            )[:-1]
            casos_inyectados.append(f"linea {i + 2}: longitud_incorrecta")
            lineas.append(linea)
            continue

        if caso == "id_deuda_con_letras":
            id_deuda = "AB" + id_deuda[2:]
        moneda = "USD" if caso == "moneda_invalida" else "ARS"

        linea = _construir_detalle(
            referencia_cliente=referencia_cliente,
            id_deuda=id_deuda,
            primer_vencimiento=primer_vencimiento,
            moneda=moneda,
            importe_principal=importe,
            nombre_entidad=nombre_entidad,
            concepto=concepto,
            segundo_vencimiento=segundo_vencimiento,
            importe_segundo=importe,
            tercer_vencimiento=tercer_vencimiento,
            importe_tercer=importe,
        )

        if caso == "importe_con_punto":
            linea = linea[:172] + linea[172:185].replace(",", ".") + linea[185:]
        elif caso == "fecha_invalida_calendario":
            linea = linea[:143] + "20260231" + linea[151:]
        elif caso == "referencia_cliente_corta":
            # Espacios de relleno (no ceros): el campo queda con menos de 8
            # digitos reales y no matchea ^[0-9]{8}$ (a diferencia de
            # rjust con ceros, que "arreglaria" el campo sin querer).
            linea = linea[:57] + referencia_cliente[:5].rjust(5, "0") + "   " + linea[65:]

        if caso is not None:
            casos_inyectados.append(f"linea {i + 2}: {caso}")
        else:
            cantidad_buenos += 1
            importe_total += importe

        lineas.append(linea)

    # El pie se calcula DESPUES de generar los detalles (prompt seccion 16),
    # y se deriva re-parseando las lineas realmente generadas con la MISMA
    # conversion que usa el motor (etl_pmc.parsing.conversions), para que el
    # pie sea consistente con la poblacion de control tal como el propio
    # motor la define (docs/matriz_equivalencia.md seccion 6: todos los
    # detalles de tipo/longitud correcta, no solo los individualmente
    # validos). Un caso "importe_con_punto" corrompe ese campo a proposito:
    # el archivo resultante queda con importes nulos en la poblacion de
    # control y por lo tanto se rechaza a nivel archivo, tal como se espera.
    from etl_pmc.parsing.conversions import convertir_importe

    cantidad_control = 0
    importe_control = Decimal("0")
    for linea in lineas:
        if len(linea) == _LARGO_DETALLE and linea[0] == "2":
            cantidad_control += 1
            valor, valido = convertir_importe(linea[172:185], 13)
            if valido:
                importe_control += valor

    cabecera = _construir_cabecera(fecha_cabecera)
    pie = _construir_pie(cantidad_control, importe_control)

    todas_las_lineas = [cabecera, *lineas, pie]
    contenido = ("\r\n".join(todas_las_lineas) + "\r\n").encode("utf-8")

    csv_enriquecimiento = (
        "CodEntidad,Descripcion,CodBanco,CodigoServicio\r\n"
        "SINTETICO,Entidad Sintetica de Prueba,001,0001\r\n"
    ).encode("utf-8")

    return LoteSintetico(
        contenido=contenido,
        fecha_cabecera=fecha_cabecera,
        cantidad_detalles_buenos=cantidad_buenos,
        casos_malos_inyectados=casos_inyectados,
        importe_total_esperado=importe_total,
        csv_enriquecimiento=csv_enriquecimiento,
    )


def _construir_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="generate-fixture", description="Genera un lote sintetico de prueba (datos ficticios)")
    parser.add_argument("--cantidad", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", required=True, help="Ruta del TXT sintetico a escribir")
    parser.add_argument("--out-enrichment", help="Ruta del CSV de enriquecimiento sintetico a escribir")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _construir_parser().parse_args(argv)
    lote = generar_lote_sintetico(cantidad=args.cantidad, seed=args.seed)
    Path(args.out).write_bytes(lote.contenido)
    print(f"Generado {args.out}: {lote.cantidad_detalles_buenos} detalles validos, seed={args.seed} (datos FICTICIOS)")
    if args.out_enrichment:
        Path(args.out_enrichment).write_bytes(lote.csv_enriquecimiento)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
