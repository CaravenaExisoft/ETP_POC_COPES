"""Manifiesto de ejecucion (prompt seccion 4). Un manifiesto invalido debe
fallar rapido y claro, antes de descargar ningun archivo: tipos, booleanos
reales (no strings), anchos de codigos, perfil existente, placeholders sin
reemplazar, y rutas de blob sin ambiguedad ni traversal.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from etl_pmc.errors import ConfigurationError

_PLACEHOLDER_RE = re.compile(r"<[^<>]+>")
_PERFILES_CONOCIDOS = ("poc_pmc", "adf_actual")
_MODOS_ENRIQUECIMIENTO = ("record_join", "single_configuration")
_NEWLINES_VALIDOS = ("CRLF", "LF")


def _requerir(data: dict, clave: str, contexto: str) -> Any:
    if clave not in data:
        raise ConfigurationError(f"Falta '{clave}' en {contexto} del manifiesto")
    return data[clave]


def _requerir_str(data: dict, clave: str, contexto: str) -> str:
    valor = _requerir(data, clave, contexto)
    if not isinstance(valor, str) or valor == "":
        raise ConfigurationError(f"'{clave}' en {contexto} debe ser una cadena no vacia, recibido: {valor!r}")
    if _PLACEHOLDER_RE.search(valor):
        raise ConfigurationError(
            f"'{clave}' en {contexto} contiene un placeholder sin reemplazar: {valor!r}"
        )
    return valor


def _requerir_bool(data: dict, clave: str, contexto: str) -> bool:
    valor = _requerir(data, clave, contexto)
    if not isinstance(valor, bool):
        raise ConfigurationError(
            f"'{clave}' en {contexto} debe ser booleano real (true/false de JSON), "
            f"no una cadena ni un numero; recibido: {valor!r}"
        )
    return valor


def _validar_ruta_blob(valor: str, *, nombre_campo: str) -> str:
    if valor.startswith("/") or valor.startswith("\\"):
        raise ConfigurationError(f"'{nombre_campo}'='{valor}' no puede ser una ruta absoluta")
    partes = re.split(r"[\\/]", valor)
    if any(p in ("..", ".") for p in partes) or any(p == "" for p in partes[1:-1]):
        raise ConfigurationError(f"'{nombre_campo}'='{valor}' contiene una ruta ambigua o traversal ('..')")
    return valor


def _validar_ancho_exacto(valor: str, ancho: int, *, nombre_campo: str) -> str:
    if len(valor) != ancho:
        raise ConfigurationError(f"'{nombre_campo}'='{valor}' debe tener exactamente {ancho} caracteres")
    return valor


@dataclass(frozen=True)
class ManifiestoInput:
    container: str
    blob: str
    etag: str | None


@dataclass(frozen=True)
class ManifiestoEnrichment:
    container: str
    blob: str
    mode: Literal["record_join", "single_configuration"]
    columna_clave_csv: str | None
    columnas_a_incorporar: tuple[str, ...]


@dataclass(frozen=True)
class ManifiestoOutput:
    container: str
    prefix: str
    filename: str


@dataclass(frozen=True)
class ManifiestoDestino:
    container: str
    prefix: str


@dataclass(frozen=True)
class ManifiestoParametros:
    cod_banco_pmc: str
    codigo_servicio_pmc: str
    tipo_registro_cab_pmc: str
    tipo_registro_det_pmc: str
    tipo_registro_pie_pmc: str
    aplicar_filtro_30_dias: bool
    aplicar_max_dos_cliente: bool
    cuota_pmc: str
    fecha_ejecucion_utc: datetime
    # Opcional, default False: filtro de antiguedad INVENTADO (GDC-1000
    # "Filtro 1"; sin campo real, ver etl_pmc.rules.pmc). No es un parametro
    # del prompt original -- por eso es opcional, a diferencia de los otros
    # dos flags de filtro que si son obligatorios en el manifiesto.
    aplicar_filtro_antiguedad: bool = False


@dataclass(frozen=True)
class ManifiestoFormato:
    input_encoding: str
    output_encoding: str
    output_newline: Literal["CRLF", "LF"]
    output_bom: bool
    final_newline: bool
    # Opcional, default False: activa etl_pmc.validation.schema_sintetico
    # (schema XSD INVENTADO, no productivo -- ver ese modulo) para medir el
    # costo de un paso de validacion por registro comparable al de IIB.
    simular_validacion_schema: bool = False


@dataclass(frozen=True)
class Manifiesto:
    schema_version: str
    run_id: str
    pipeline_run_id: str
    lote_id: str
    profile: str
    storage_account_url: str
    input: ManifiestoInput
    enrichment: ManifiestoEnrichment
    output: ManifiestoOutput
    audit: ManifiestoDestino
    errors: ManifiestoDestino
    parameters: ManifiestoParametros
    format: ManifiestoFormato


def _parsear_input(data: dict) -> ManifiestoInput:
    contexto = "input"
    container = _requerir_str(data, "container", contexto)
    blob = _validar_ruta_blob(_requerir_str(data, "blob", contexto), nombre_campo="input.blob")
    etag = data.get("etag")
    if etag is not None and not isinstance(etag, str):
        raise ConfigurationError("'etag' en input debe ser string o null")
    return ManifiestoInput(container=container, blob=blob, etag=etag)


def _parsear_enrichment(data: dict) -> ManifiestoEnrichment:
    contexto = "enrichment"
    container = _requerir_str(data, "container", contexto)
    blob = _validar_ruta_blob(_requerir_str(data, "blob", contexto), nombre_campo="enrichment.blob")
    mode = _requerir_str(data, "mode", contexto)
    if mode not in _MODOS_ENRIQUECIMIENTO:
        raise ConfigurationError(f"'enrichment.mode'='{mode}' invalido; valores validos: {_MODOS_ENRIQUECIMIENTO}")

    columna_clave_csv = None
    columnas_a_incorporar: tuple[str, ...] = ()
    if mode == "record_join":
        record_join_cfg = data.get("record_join")
        if not isinstance(record_join_cfg, dict):
            raise ConfigurationError(
                "enrichment.mode='record_join' requiere el objeto 'enrichment.record_join' "
                "con 'columna_clave_csv' y 'columnas_a_incorporar' (prompt seccion 8: "
                "no se asume IdDeuda como clave por defecto)"
            )
        columna_clave_csv = _requerir_str(record_join_cfg, "columna_clave_csv", "enrichment.record_join")
        columnas = record_join_cfg.get("columnas_a_incorporar")
        if not isinstance(columnas, list) or not columnas or not all(isinstance(c, str) for c in columnas):
            raise ConfigurationError("enrichment.record_join.columnas_a_incorporar debe ser una lista de strings no vacia")
        columnas_a_incorporar = tuple(columnas)

    return ManifiestoEnrichment(
        container=container,
        blob=blob,
        mode=mode,  # type: ignore[arg-type]
        columna_clave_csv=columna_clave_csv,
        columnas_a_incorporar=columnas_a_incorporar,
    )


def _parsear_output(data: dict) -> ManifiestoOutput:
    contexto = "output"
    container = _requerir_str(data, "container", contexto)
    prefix = _validar_ruta_blob(_requerir_str(data, "prefix", contexto), nombre_campo="output.prefix")
    filename = _requerir_str(data, "filename", contexto)
    return ManifiestoOutput(container=container, prefix=prefix, filename=filename)


def _parsear_destino(data: dict, contexto: str) -> ManifiestoDestino:
    container = _requerir_str(data, "container", contexto)
    prefix = _validar_ruta_blob(_requerir_str(data, "prefix", contexto), nombre_campo=f"{contexto}.prefix")
    return ManifiestoDestino(container=container, prefix=prefix)


def _parsear_parametros(data: dict) -> ManifiestoParametros:
    contexto = "parameters"
    cod_banco_pmc = _validar_ancho_exacto(
        _requerir_str(data, "CodBancoPMC", contexto), 3, nombre_campo="CodBancoPMC"
    )
    codigo_servicio_pmc = _validar_ancho_exacto(
        _requerir_str(data, "CodigoServicioPMC", contexto), 4, nombre_campo="CodigoServicioPMC"
    )
    tipo_cab = _validar_ancho_exacto(
        _requerir_str(data, "TipoRegistroCabPMC", contexto), 1, nombre_campo="TipoRegistroCabPMC"
    )
    tipo_det = _validar_ancho_exacto(
        _requerir_str(data, "TipoRegistroDetPMC", contexto), 1, nombre_campo="TipoRegistroDetPMC"
    )
    tipo_pie = _validar_ancho_exacto(
        _requerir_str(data, "TipoRegistroPiePMC", contexto), 1, nombre_campo="TipoRegistroPiePMC"
    )
    aplicar_filtro_30_dias = _requerir_bool(data, "AplicarFiltro30Dias", contexto)
    aplicar_max_dos_cliente = _requerir_bool(data, "AplicarMaxDosCliente", contexto)
    aplicar_filtro_antiguedad = data.get("AplicarFiltroAntiguedad", False)
    if not isinstance(aplicar_filtro_antiguedad, bool):
        raise ConfigurationError("'AplicarFiltroAntiguedad' debe ser booleano real si se especifica")
    cuota_pmc = _requerir_str(data, "CuotaPMC", contexto)

    fecha_texto = _requerir_str(data, "FechaEjecucionUTC", contexto)
    try:
        fecha_ejecucion_utc = datetime.fromisoformat(fecha_texto.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ConfigurationError(f"'FechaEjecucionUTC'='{fecha_texto}' no es ISO-8601 valido") from exc

    return ManifiestoParametros(
        cod_banco_pmc=cod_banco_pmc,
        codigo_servicio_pmc=codigo_servicio_pmc,
        tipo_registro_cab_pmc=tipo_cab,
        tipo_registro_det_pmc=tipo_det,
        tipo_registro_pie_pmc=tipo_pie,
        aplicar_filtro_30_dias=aplicar_filtro_30_dias,
        aplicar_max_dos_cliente=aplicar_max_dos_cliente,
        aplicar_filtro_antiguedad=aplicar_filtro_antiguedad,
        cuota_pmc=cuota_pmc,
        fecha_ejecucion_utc=fecha_ejecucion_utc,
    )


def _parsear_formato(data: dict) -> ManifiestoFormato:
    contexto = "format"
    input_encoding = _requerir_str(data, "input_encoding", contexto)
    output_encoding = _requerir_str(data, "output_encoding", contexto)
    output_newline = _requerir_str(data, "output_newline", contexto)
    if output_newline not in _NEWLINES_VALIDOS:
        raise ConfigurationError(f"'format.output_newline'='{output_newline}' invalido; valores validos: {_NEWLINES_VALIDOS}")
    output_bom = _requerir_bool(data, "output_bom", contexto)
    final_newline = _requerir_bool(data, "final_newline", contexto)
    simular_validacion_schema = data.get("simular_validacion_schema", False)
    if not isinstance(simular_validacion_schema, bool):
        raise ConfigurationError("'format.simular_validacion_schema' debe ser booleano real si se especifica")
    return ManifiestoFormato(
        input_encoding=input_encoding,
        output_encoding=output_encoding,
        output_newline=output_newline,  # type: ignore[arg-type]
        output_bom=output_bom,
        final_newline=final_newline,
        simular_validacion_schema=simular_validacion_schema,
    )


def parsear_manifiesto(data: dict) -> Manifiesto:
    schema_version = _requerir_str(data, "schema_version", "manifiesto")
    if schema_version != "1.0":
        raise ConfigurationError(f"schema_version '{schema_version}' no soportada; se espera '1.0'")

    run_id = _requerir_str(data, "run_id", "manifiesto")
    pipeline_run_id = _requerir_str(data, "pipeline_run_id", "manifiesto")
    lote_id = _requerir_str(data, "lote_id", "manifiesto")
    profile = _requerir_str(data, "profile", "manifiesto")
    if profile not in _PERFILES_CONOCIDOS:
        raise ConfigurationError(f"profile '{profile}' desconocido; perfiles validos: {_PERFILES_CONOCIDOS}")

    storage_account_url = _requerir_str(data, "storage_account_url", "manifiesto")

    return Manifiesto(
        schema_version=schema_version,
        run_id=run_id,
        pipeline_run_id=pipeline_run_id,
        lote_id=lote_id,
        profile=profile,
        storage_account_url=storage_account_url,
        input=_parsear_input(_requerir(data, "input", "manifiesto")),
        enrichment=_parsear_enrichment(_requerir(data, "enrichment", "manifiesto")),
        output=_parsear_output(_requerir(data, "output", "manifiesto")),
        audit=_parsear_destino(_requerir(data, "audit", "manifiesto"), "audit"),
        errors=_parsear_destino(_requerir(data, "errors", "manifiesto"), "errors"),
        parameters=_parsear_parametros(_requerir(data, "parameters", "manifiesto")),
        format=_parsear_formato(_requerir(data, "format", "manifiesto")),
    )


def cargar_manifiesto_desde_texto(texto_json: str) -> Manifiesto:
    try:
        data = json.loads(texto_json)
    except json.JSONDecodeError as exc:
        raise ConfigurationError(f"el manifiesto no es JSON valido: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigurationError("el manifiesto debe ser un objeto JSON")
    return parsear_manifiesto(data)
