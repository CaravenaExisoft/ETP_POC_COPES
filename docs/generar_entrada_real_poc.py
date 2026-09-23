#!/usr/bin/env python3
"""Genera datos de prueba de ancho fijo a partir del TXT de referencia.

Python 3.8+; solo biblioteca estandar. No instala paquetes ni accede a Azure.
Ejemplo (Windows):
  py generar_entrada_real_poc.py --plantilla "archivo ejemplo.txt" --registros 1000 --salida entrada_real_1000.txt

Layout INFERIDO, no especificacion bancaria:
  cabecera: 88 caracteres; detalle: 713; pie: 24; terminadores CRLF.
  detalle: ID de deuda 103-111; importe principal 173-185;
  vencimientos supuestos 666-673 y 687-694; importes 674-686 y 695-707.
  pie: tipo 1; cantidad 2-9; total 10-24.

Se elige un detalle original al azar para cada nueva fila. Se conservan
literalmente los campos no interpretados, incluidas referencias de cliente,
entidad, concepto, fechas historicas y espacios. NO es una anonimizacion.
Los nuevos IDs son unicos DENTRO del archivo; requieren enriquecimiento SQL
de prueba compatible. La misma semilla y fecha reproducen el mismo archivo.
"""

import argparse
from datetime import date, timedelta
from pathlib import Path
import random
import sys


def importe(centavos, ancho):
    texto = "{}.{:02d}".format(centavos // 100, centavos % 100).replace(".", ",")
    if centavos < 0 or len(texto) > ancho:
        raise ValueError("El importe no cabe en {} posiciones".format(ancho))
    return texto.zfill(ancho)


def centavos(texto):
    partes = texto.split(",")
    if len(partes) != 2 or len(partes[1]) != 2 or not all(p.isdigit() for p in partes):
        raise ValueError("Importe invalido: {!r}".format(texto))
    return int(partes[0]) * 100 + int(partes[1])


def poner(linea, inicio, fin, valor):
    if len(valor) != fin - inicio + 1:
        raise ValueError("Longitud incorrecta para posiciones {}-{}".format(inicio, fin))
    return linea[:inicio - 1] + valor + linea[fin:]


def leer_plantilla(ruta):
    # splitlines conserva espacios; no usar strip/rstrip sobre las filas.
    filas = ruta.read_bytes().decode("ascii").splitlines()
    if len(filas) < 3 or len(filas[0]) != 88 or not filas[0].startswith("1"):
        raise ValueError("Se esperaba cabecera tipo 1 de 88 caracteres")
    if len(filas[-1]) != 24 or not filas[-1].startswith("3"):
        raise ValueError("Se esperaba pie tipo 3 de 24 caracteres")
    detalles = filas[1:-1]
    if any(len(f) != 713 or not f.startswith("2") for f in detalles):
        raise ValueError("Todos los detalles deben ser tipo 2 de 713 caracteres")
    if int(filas[-1][1:9]) != len(detalles):
        raise ValueError("La cantidad del pie de la plantilla no coincide")
    if centavos(filas[-1][9:24]) != sum(centavos(f[172:185]) for f in detalles):
        raise ValueError("El total del pie de la plantilla no coincide")
    return filas[0], detalles


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--plantilla", type=Path, default=Path("archivo ejemplo.txt"))
    parser.add_argument("--salida", type=Path, default=Path("entrada_real_1000.txt"))
    parser.add_argument("--registros", type=int, default=1000, help="Cantidad de detalles; se agregan cabecera y pie")
    parser.add_argument("--semilla", type=int, default=42, help="Cambiarla genera otros datos; predeterminado 42")
    parser.add_argument("--fecha", type=date.fromisoformat, default=date.today(), help="Fecha base AAAA-MM-DD; por defecto hoy")
    args = parser.parse_args()
    try:
        if not 1 <= args.registros <= 99999999:
            raise ValueError("--registros debe estar entre 1 y 99999999")
        if args.plantilla.resolve() == args.salida.resolve():
            raise ValueError("La salida no puede ser la plantilla")
        cabecera, plantillas = leer_plantilla(args.plantilla)
        # 2-9 se interpreta provisionalmente como fecha de generacion.
        cabecera = poner(cabecera, 2, 9, args.fecha.strftime("%Y%m%d"))
        rng = random.Random(args.semilla)
        # IDs aleatorios sin repeticion, de nueve digitos.
        ids = rng.sample(range(500000000, 900000000), args.registros)
        total = 0
        detalles = []
        for identificador in ids:
            fila = rng.choice(plantillas)
            valor = rng.randint(10000, 100000000)  # 100,00 a 1.000.000,00 pesos.
            fecha1 = args.fecha + timedelta(days=rng.randint(1, 90))
            fecha2 = fecha1 + timedelta(days=14)
            fila = poner(fila, 103, 111, str(identificador))
            for inicio, fin in [(173, 185), (674, 686), (695, 707)]:
                fila = poner(fila, inicio, fin, importe(valor, 13))
            fila = poner(fila, 666, 673, fecha1.strftime("%Y%m%d"))
            fila = poner(fila, 687, 694, fecha2.strftime("%Y%m%d"))
            if len(fila) != 713:
                raise ValueError("Longitud de detalle incorrecta")
            detalles.append(fila)
            total += valor
        pie = "3" + str(args.registros).zfill(8) + importe(total, 15)
        contenido = ("\r\n".join([cabecera] + detalles + [pie]) + "\r\n").encode("ascii")
        # Exclusivo: no sobrescribe un archivo existente.
        with args.salida.open("xb") as archivo:
            archivo.write(contenido)
        print("Archivo: {}".format(args.salida.resolve()))
        print("Detalles: {:,}; lineas totales: {:,}".format(args.registros, args.registros + 2))
        print("Total ARS: {}".format(importe(total, 15)))
        print("Longitudes: 88 / 713 / 24; CRLF; ASCII sin BOM")
        print("Bytes: {}; semilla: {}; fecha: {}".format(len(contenido), args.semilla, args.fecha))
        print("IDs nuevos: preparar sus datos SQL antes de ejecutar el enriquecimiento.")
    except (OSError, ValueError, OverflowError) as error:
        print("Error: {}".format(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
