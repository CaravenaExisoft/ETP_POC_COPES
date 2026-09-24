"""Modo 'single_configuration' (poc_pmc -- prompt seccion 8).

Consume como maximo una fila de configuracion del CSV de enriquecimiento.
Columnas alineadas al esquema real de intdb.FixedValues/vw_EnrichmentPoc
(GDC-1000 + confirmado por el usuario): CodEntidad, Descripcion, CodBanco,
CodigoServicio. No hace fallback silencioso ante archivo faltante, CSV
vacio, columna ausente, nulo, cadena vacia o multiples filas: cada caso es
un EnrichmentError distinto.

Limpieza de CodBanco/CodigoServicio: CONFIRMADA_ADF. El usuario compartio la
query real usada para extraer esta configuracion desde SQL:

    SELECT TOP (1)
           CAST(CodEntidad AS varchar(10)) AS CodEntidad,
           LTRIM(RTRIM(DescripcionEntidad)) AS DescripcionEntidad,
           RIGHT('000' + REPLACE(REPLACE(LTRIM(RTRIM(CodBanco)), '''', ''), 'B', ''), 3)
               AS CodBancoConfig,
           RIGHT('0000' + REPLACE(REPLACE(LTRIM(RTRIM(CodigoServicio)), '''', ''), 'S', ''), 4)
               AS CodigoServicioConfig
    FROM intdb.vw_EnrichmentPoc
    WHERE LoteId = 'LOTE001'
    ORDER BY CodEntidad;

Es decir: en el dato crudo, CodBanco/CodigoServicio vienen con un prefijo de
letra ('B001', 'S0001', confirmado contra 100 filas de muestra de
vw_EnrichmentPoc) y posibles comillas simples embebidas, y la propia query
de SQL ya los limpia (saca comillas, saca la letra, rellena con ceros a
3/4 posiciones) antes de que el extracto llegue a Storage. _limpiar_codigo
replica exactamente esa transformacion -- es un no-op si el CSV ya llega
limpio (ej. "001"), asi que no rompe los fixtures existentes.

Tambien confirma una divergencia ya documentada en
docs/matriz_equivalencia.md seccion 8.1: el "TOP (1) ... ORDER BY CodEntidad"
de la query real selecciona una fila sin controlar cardinalidad -- si hubiera
mas de una fila para el mismo LoteId, ADF tomaria una en silencio. Este
motor, a proposito, NO replica eso: sigue fallando con MULTIPLES_FILAS
(prompt seccion 8: "no copies un TOP (1) dentro del contenedor").
"""

from __future__ import annotations

from dataclasses import dataclass

from etl_pmc.errors import EnrichmentError

COLUMNAS_REQUERIDAS = ("CodEntidad", "Descripcion", "CodBanco", "CodigoServicio")


def _limpiar_codigo(valor: str, letra: str, ancho: int) -> str:
    """Replica RIGHT('0'*ancho + REPLACE(REPLACE(valor, '''', ''), letra, ''), ancho)."""
    sin_comillas = valor.replace("'", "")
    sin_letra = sin_comillas.replace(letra, "")
    return ("0" * ancho + sin_letra)[-ancho:]


@dataclass(frozen=True)
class ConfiguracionEnriquecimiento:
    cod_entidad: str
    descripcion: str
    cod_banco: str | None
    codigo_servicio: str | None


def cargar_single_configuration(filas: list[dict[str, str]] | None) -> ConfiguracionEnriquecimiento:
    if filas is None:
        raise EnrichmentError("ARCHIVO_FALTANTE", "no se encontro el CSV de enriquecimiento en la ruta indicada")
    if len(filas) == 0:
        raise EnrichmentError("CSV_VACIO", "el CSV de enriquecimiento no tiene filas de datos")
    if len(filas) > 1:
        raise EnrichmentError(
            "MULTIPLES_FILAS",
            f"se esperaba una unica fila de configuracion y se encontraron {len(filas)}; "
            "no se aplica ninguna seleccion arbitraria (prohibido por diseño)",
        )

    fila = filas[0]
    for columna in COLUMNAS_REQUERIDAS:
        if columna not in fila:
            raise EnrichmentError("COLUMNA_AUSENTE", f"falta la columna requerida '{columna}' en el CSV")

    # GDC-1000 seccion C: "Antes de mapear, se aplica TRIM a los valores de
    # la tabla intermedia" -- se hace antes de chequear nulo/vacio, para que
    # un valor de solo espacios se trate como vacio, no como presente.
    def _trim(valor: str | None) -> str | None:
        return valor.strip() if valor is not None else None

    cod_entidad = _trim(fila["CodEntidad"])
    descripcion = _trim(fila["Descripcion"])

    if cod_entidad is None:
        raise EnrichmentError("VALOR_NULO", "CodEntidad es nulo")
    if cod_entidad == "":
        raise EnrichmentError("VALOR_VACIO", "CodEntidad es una cadena vacia")
    if descripcion is None:
        raise EnrichmentError("VALOR_NULO", "Descripcion es nulo")
    if descripcion == "":
        raise EnrichmentError("VALOR_VACIO", "Descripcion es una cadena vacia")

    cod_banco_raw = _trim(fila.get("CodBanco")) or None
    codigo_servicio_raw = _trim(fila.get("CodigoServicio")) or None
    cod_banco = _limpiar_codigo(cod_banco_raw, "B", 3) if cod_banco_raw is not None else None
    codigo_servicio = _limpiar_codigo(codigo_servicio_raw, "S", 4) if codigo_servicio_raw is not None else None

    return ConfiguracionEnriquecimiento(
        cod_entidad=cod_entidad,
        descripcion=descripcion,
        cod_banco=cod_banco,
        codigo_servicio=codigo_servicio,
    )


def resolver_codigos_finales(
    config: ConfiguracionEnriquecimiento,
    *,
    cod_banco_parametro: str,
    codigo_servicio_parametro: str,
) -> tuple[str, str]:
    """Prompt seccion 8: resolver CodBancoFinal/CodigoServicioFinal desde el
    CSV si no son nulos; usar los parametros del manifiesto como respaldo."""
    cod_banco_final = config.cod_banco if config.cod_banco is not None else cod_banco_parametro
    codigo_servicio_final = config.codigo_servicio if config.codigo_servicio is not None else codigo_servicio_parametro
    return cod_banco_final, codigo_servicio_final
