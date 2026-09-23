"""Modo 'record_join' (poc_pmc, NO_VERIFICADA -- prompt seccion 8).

Enriquecimiento por registro. El prompt es explicito: "no asumir que IdDeuda
es siempre la clave correcta". La clave y las columnas a incorporar son
configuracion requerida del manifiesto, sin default: sin esa configuracion el
motor falla con un error claro en vez de adivinar.
"""

from __future__ import annotations

from dataclasses import dataclass

from etl_pmc.errors import EnrichmentError


@dataclass(frozen=True)
class ConfiguracionRecordJoin:
    columna_clave_csv: str
    columnas_a_incorporar: tuple[str, ...]


def construir_indice(filas: list[dict[str, str]] | None, config: ConfiguracionRecordJoin) -> dict[str, dict[str, str]]:
    if filas is None:
        raise EnrichmentError("ARCHIVO_FALTANTE", "no se encontro el CSV de enriquecimiento en la ruta indicada")
    if len(filas) == 0:
        raise EnrichmentError("CSV_VACIO", "el CSV de enriquecimiento no tiene filas de datos")

    indice: dict[str, dict[str, str]] = {}
    for fila in filas:
        if config.columna_clave_csv not in fila:
            raise EnrichmentError("COLUMNA_AUSENTE", f"falta la columna clave '{config.columna_clave_csv}' en el CSV")
        for columna in config.columnas_a_incorporar:
            if columna not in fila:
                raise EnrichmentError("COLUMNA_AUSENTE", f"falta la columna '{columna}' en el CSV")

        clave = fila[config.columna_clave_csv]
        if clave in indice:
            raise EnrichmentError(
                "CLAVE_DUPLICADA",
                f"la clave '{clave}' aparece mas de una vez en el CSV de enriquecimiento; "
                "cardinalidad ambigua, no se aplica un producto cartesiano",
            )
        indice[clave] = {columna: fila[columna] for columna in config.columnas_a_incorporar}

    return indice


def enriquecer(clave_detalle: str, indice: dict[str, dict[str, str]]) -> dict[str, str] | None:
    """None significa 'sin coincidencia'; el llamador decide la politica de
    rechazo (categoria de error 'enriquecimiento', prompt seccion 14)."""
    return indice.get(clave_detalle)
