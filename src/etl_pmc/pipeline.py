"""Orquestacion de dos pasadas del motor (prompt seccion 11):
pasada 1 valida/agrega y almacena detalles en SQLite temporal; pasada 2
enriquece/filtra/ordena y emite. No se publica salida antes de conocer los
controles globales (prompt seccion 7/13).

Limitacion conocida (documentada en docs/supuestos_y_pendientes.md): la
pasada 2 materializa en memoria el conjunto de detalles autorizados (no el
archivo completo ni sus lineas crudas) para calcular el ranking de negocio
por cliente; para el volumen de prueba (~1000, hasta ~630000 en evaluacion
posterior) es aceptable como primer corte, con una version streaming del
ranking como optimizacion pendiente.
"""

from __future__ import annotations

import csv
import hashlib
import io
import shutil
import tempfile
import time
from decimal import Decimal
from pathlib import Path
from typing import BinaryIO

from etl_pmc.audit.errors import (
    CATEGORIA_ENTRADA,
    CATEGORIA_ENRIQUECIMIENTO,
    CATEGORIA_FORMATO_SALIDA,
    CATEGORIA_FORMATO_SCHEMA_SINTETICO,
    CATEGORIA_NEGOCIO,
    FilaError,
    escribir_csv_errores,
)
from etl_pmc.audit.result import EstadoEjecucion, ResultadoEjecucion
from etl_pmc.config.layouts import load_layout
from etl_pmc.control.cabecera import validar_cabeceras
from etl_pmc.control.totales import AcumuladorControlArchivo
from etl_pmc.enrichment.record_join import ConfiguracionRecordJoin, construir_indice, enriquecer
from etl_pmc.enrichment.single_configuration import cargar_single_configuration, resolver_codigos_finales
from etl_pmc.errors import EnrichmentError
from etl_pmc.formatting.output import OutputFormatError, formatear_cabecera, formatear_detalle, formatear_pie
from etl_pmc.idempotency import ClaveIdempotencia, construir_marca, hash_bytes, marca_ya_procesado
from etl_pmc.manifest import Manifiesto
from etl_pmc.models import DetalleConvertido, DetalleCrudo, DetalleValidado, LineaCruda, TipoRegistro
from etl_pmc.parsing.cabecera import parsear_cabecera
from etl_pmc.parsing.detalle import parsear_detalle
from etl_pmc.parsing.identify import identificar_tipo
from etl_pmc.parsing.pie import parsear_pie
from etl_pmc.parsing.reader import DecodificacionError, leer_lineas
from etl_pmc.rules.pmc import aplicar_reglas_negocio
from etl_pmc.storage.base import StorageAdapter
from etl_pmc.storage.tempdb import AlmacenTemporalDetalle, DetalleAutorizadoFila
from etl_pmc.validation.detalle import validar_detalle
from etl_pmc.validation.schema_sintetico import SchemaSinteticoError, validar_detalle_schema

VERSION_CODIGO = "0.1.0"


class _StreamHasher(io.RawIOBase):
    """Envuelve un BinaryIO calculando SHA-256 de forma incremental, sin
    buferizar el contenido completo (prompt seccion 11)."""

    def __init__(self, origen: BinaryIO) -> None:
        self._origen = origen
        self.hasher = hashlib.sha256()

    def readable(self) -> bool:
        return True

    def readinto(self, b) -> int:  # type: ignore[override]
        datos = self._origen.read(len(b))
        n = len(datos)
        b[:n] = datos
        if n:
            self.hasher.update(bytes(b[:n]))
        return n


def _reconstruir_detalle_validado(fila: DetalleAutorizadoFila) -> DetalleValidado:
    """Reconstruye un DetalleValidado 'liviano' a partir de una fila de
    SQLite ya sabida valida; los *_raw quedan vacios porque no se necesitan
    despues de la conversion tipada."""
    linea = LineaCruda(archivo_origen="", numero_linea=fila.numero_linea, contenido="")
    crudo = DetalleCrudo(
        linea=linea,
        referencia_cliente_raw="",
        id_deuda_raw="",
        primer_vencimiento_raw="",
        moneda_raw="",
        importe_principal_raw="",
        nombre_entidad_raw="",
        concepto_raw="",
        segundo_vencimiento_raw="",
        importe_segundo_vencimiento_raw="",
        tercer_vencimiento_raw="",
        importe_tercer_vencimiento_raw="",
    )
    convertido = DetalleConvertido(
        crudo=crudo,
        referencia_cliente=fila.referencia_cliente,
        id_deuda=fila.id_deuda,
        primer_vencimiento=fila.primer_vencimiento,
        primer_vencimiento_valido=True,
        moneda=fila.moneda,
        importe_principal=fila.importe_principal,
        importe_principal_valido=True,
        nombre_entidad=fila.nombre_entidad,
        concepto=fila.concepto,
        segundo_vencimiento=fila.segundo_vencimiento,
        segundo_vencimiento_valido=True,
        importe_segundo_vencimiento=fila.importe_segundo_vencimiento,
        importe_segundo_vencimiento_valido=True,
        tercer_vencimiento=fila.tercer_vencimiento,
        tercer_vencimiento_valido=True,
        importe_tercer_vencimiento=fila.importe_tercer_vencimiento,
        importe_tercer_vencimiento_valido=True,
        fecha_emision_deuda_sintetica=fila.fecha_emision_deuda_sintetica,
        fecha_emision_deuda_sintetica_valida=fila.fecha_emision_deuda_sintetica is not None,
    )
    return DetalleValidado(
        convertido=convertido,
        identificacion_valida=True,
        moneda_valida=True,
        importes_validos=True,
        fechas_validas=True,
    )


def _leer_filas_csv(contenido: bytes) -> list[dict[str, str]]:
    texto = contenido.decode("utf-8-sig")
    return list(csv.DictReader(io.StringIO(texto)))


def ejecutar(manifiesto: Manifiesto, storage: StorageAdapter) -> ResultadoEjecucion:
    duraciones: dict[str, float] = {}
    layout = load_layout(manifiesto.profile)

    base = dict(
        run_id=manifiesto.run_id,
        pipeline_run_id=manifiesto.pipeline_run_id,
        lote_id=manifiesto.lote_id,
        version_codigo=VERSION_CODIGO,
        profile=manifiesto.profile,
        layout_version=layout.layout_version,
    )

    if not storage.existe(manifiesto.input.container, manifiesto.input.blob):
        return ResultadoEjecucion(
            estado=EstadoEjecucion.FAILED,
            **base,
            warnings=[f"no se encontro el blob de entrada '{manifiesto.input.container}/{manifiesto.input.blob}'"],
        )

    archivos_consumidos = [f"{manifiesto.input.container}/{manifiesto.input.blob}"]

    # --- Enriquecimiento: se resuelve antes de procesar el TXT porque un
    # problema en single_configuration invalida toda la corrida (prompt
    # seccion 8). record_join no tiene todavia un campo de salida que use sus
    # columnas (el layout de poc_pmc no lo especifica); se valida su
    # configuracion pero no se aplica a la salida -- ver
    # docs/supuestos_y_pendientes.md. ---
    t0 = time.monotonic()
    hash_enriquecimiento: str | None = None
    cod_banco_final = manifiesto.parameters.cod_banco_pmc
    codigo_servicio_final = manifiesto.parameters.codigo_servicio_pmc
    indice_record_join: dict[str, dict[str, str]] | None = None
    try:
        filas_csv: list[dict[str, str]] | None = None
        if storage.existe(manifiesto.enrichment.container, manifiesto.enrichment.blob):
            with storage.abrir_lectura(manifiesto.enrichment.container, manifiesto.enrichment.blob) as fh:
                contenido_csv = fh.read()
            hash_enriquecimiento = hash_bytes(contenido_csv)
            filas_csv = _leer_filas_csv(contenido_csv)
            archivos_consumidos.append(f"{manifiesto.enrichment.container}/{manifiesto.enrichment.blob}")

        if manifiesto.enrichment.mode == "single_configuration":
            config = cargar_single_configuration(filas_csv)
            cod_banco_final, codigo_servicio_final = resolver_codigos_finales(
                config,
                cod_banco_parametro=manifiesto.parameters.cod_banco_pmc,
                codigo_servicio_parametro=manifiesto.parameters.codigo_servicio_pmc,
            )
        else:
            config_rj = ConfiguracionRecordJoin(
                columna_clave_csv=manifiesto.enrichment.columna_clave_csv or "",
                columnas_a_incorporar=manifiesto.enrichment.columnas_a_incorporar,
            )
            # Clave del lado del detalle: id_deuda, fijado como decision de
            # POC para simular el proceso (docs/matriz_equivalencia.md
            # seccion 8.1) -- no es un dato productivo confirmado.
            indice_record_join = construir_indice(filas_csv, config_rj)
    except EnrichmentError as exc:
        duraciones["enriquecimiento"] = time.monotonic() - t0
        ruta_errores = None
        try:
            nombre = f"{manifiesto.errors.prefix}/errores_enriquecimiento.csv"
            fila = FilaError(
                run_id=manifiesto.run_id,
                archivo=manifiesto.enrichment.blob,
                numero_linea=None,
                categoria=CATEGORIA_ENRIQUECIMIENTO,
                codigo=exc.codigo,
                campo="enrichment",
                motivo=str(exc),
            )
            storage.escribir_bytes(manifiesto.errors.container, nombre, escribir_csv_errores([fila]))
            ruta_errores = f"{manifiesto.errors.container}/{nombre}"
        except Exception:  # el registro de auditoria nunca debe ocultar el rechazo original
            pass
        return ResultadoEjecucion(
            estado=EstadoEjecucion.REJECTED,
            **base,
            hash_enriquecimiento=hash_enriquecimiento,
            archivos_consumidos=archivos_consumidos,
            duraciones_segundos=duraciones,
            motivos_rechazo_globales=(exc.codigo,),
            warnings=[str(exc)],
            ruta_errores=ruta_errores,
        )
    duraciones["enriquecimiento"] = time.monotonic() - t0

    tmp_dir = tempfile.mkdtemp(prefix="etl_pmc_")
    try:
        ruta_db = Path(tmp_dir) / "detalle.sqlite3"

        cabeceras = []
        pies = []
        acumulador = AcumuladorControlArchivo(manifiesto.input.blob)
        cantidad_leida = 0
        cantidad_valida = 0
        cantidad_rechazada = 0
        filas_error: list[FilaError] = []
        tiempo_schema_sintetico = 0.0

        t0 = time.monotonic()
        with AlmacenTemporalDetalle(ruta_db) as almacen:
            with storage.abrir_lectura(manifiesto.input.container, manifiesto.input.blob) as fh_original:
                hasher = _StreamHasher(fh_original)
                try:
                    for linea in leer_lineas(hasher, manifiesto.input.blob, encoding=manifiesto.format.input_encoding):
                        cantidad_leida += 1
                        tipo = identificar_tipo(linea, layout)
                        if tipo == TipoRegistro.CABECERA:
                            cabeceras.append(parsear_cabecera(linea, layout))
                        elif tipo == TipoRegistro.PIE:
                            pies.append(parsear_pie(linea, layout))
                        elif tipo == TipoRegistro.DETALLE:
                            detalle = parsear_detalle(linea, layout)

                            if manifiesto.format.simular_validacion_schema:
                                t_schema = time.monotonic()
                                try:
                                    validar_detalle_schema(detalle.crudo)
                                except SchemaSinteticoError as exc:
                                    tiempo_schema_sintetico += time.monotonic() - t_schema
                                    cantidad_rechazada += 1
                                    filas_error.append(
                                        FilaError(
                                            run_id=manifiesto.run_id,
                                            archivo=manifiesto.input.blob,
                                            numero_linea=linea.numero_linea,
                                            categoria=CATEGORIA_FORMATO_SCHEMA_SINTETICO,
                                            codigo="SCHEMA_SINTETICO_INVALIDO",
                                            campo="detalle",
                                            motivo=str(exc),
                                        )
                                    )
                                    continue
                                tiempo_schema_sintetico += time.monotonic() - t_schema

                            validado = validar_detalle(detalle)
                            acumulador.agregar(validado)
                            almacen.insertar(validado)
                            if validado.detalle_valido:
                                cantidad_valida += 1
                            else:
                                cantidad_rechazada += 1
                                filas_error.append(
                                    FilaError(
                                        run_id=manifiesto.run_id,
                                        archivo=manifiesto.input.blob,
                                        numero_linea=linea.numero_linea,
                                        categoria=CATEGORIA_ENTRADA,
                                        codigo=",".join(validado.motivos_rechazo),
                                        campo="detalle",
                                        motivo="detalle individualmente invalido",
                                    )
                                )
                        else:
                            cantidad_rechazada += 1
                            filas_error.append(
                                FilaError(
                                    run_id=manifiesto.run_id,
                                    archivo=manifiesto.input.blob,
                                    numero_linea=linea.numero_linea,
                                    categoria=CATEGORIA_ENTRADA,
                                    codigo="TIPO_O_LONGITUD_INVALIDA",
                                    campo="tipo_registro",
                                    motivo=f"linea de {len(linea.contenido)} caracteres no matchea ningun tipo declarado",
                                )
                            )
                except DecodificacionError as exc:
                    duraciones["lectura_y_validacion"] = time.monotonic() - t0
                    return ResultadoEjecucion(
                        estado=EstadoEjecucion.FAILED,
                        **base,
                        archivos_consumidos=archivos_consumidos,
                        hash_enriquecimiento=hash_enriquecimiento,
                        duraciones_segundos=duraciones,
                        warnings=[str(exc)],
                    )
                hash_entrada = hasher.hasher.hexdigest()

            almacen.finalizar_carga()
            duraciones["lectura_y_validacion"] = time.monotonic() - t0
            if manifiesto.format.simular_validacion_schema:
                duraciones["validacion_schema_sintetica"] = tiempo_schema_sintetico

            control_cabecera = validar_cabeceras(cabeceras)
            control_archivo = acumulador.finalizar(pies)

            ruta_errores: str | None = None

            def _publicar_errores() -> str | None:
                if not filas_error:
                    return None
                nombre = f"{manifiesto.errors.prefix}/errores_entrada.csv"
                storage.escribir_bytes(manifiesto.errors.container, nombre, escribir_csv_errores(filas_error))
                return f"{manifiesto.errors.container}/{nombre}"

            if not (control_cabecera.valida and control_archivo.totales_validos):
                ruta_errores = _publicar_errores()
                return ResultadoEjecucion(
                    estado=EstadoEjecucion.REJECTED,
                    **base,
                    hash_entrada=hash_entrada,
                    hash_enriquecimiento=hash_enriquecimiento,
                    archivos_consumidos=archivos_consumidos,
                    cantidad_leida=cantidad_leida,
                    cantidad_valida=cantidad_valida,
                    cantidad_rechazada=cantidad_rechazada,
                    importe_total_declarado=control_archivo.importe_total_declarado,
                    importe_total_calculado=control_archivo.importe_total_calculado,
                    control_cabecera_valido=control_cabecera.valida,
                    control_archivo_valido=control_archivo.totales_validos,
                    duraciones_segundos=duraciones,
                    ruta_errores=ruta_errores,
                    motivos_rechazo_globales=control_cabecera.motivos + control_archivo.motivos,
                )

            # --- idempotencia: se chequea recien aca porque hash_entrada solo
            # se conoce completo tras terminar de leer el archivo en streaming
            # (prompt seccion 13) ---
            clave_idempotencia = ClaveIdempotencia(
                hash_entrada=hash_entrada,
                hash_enriquecimiento=hash_enriquecimiento or "",
                profile=manifiesto.profile,
                layout_version=layout.layout_version,
                parametros_relevantes={
                    "AplicarFiltro30Dias": manifiesto.parameters.aplicar_filtro_30_dias,
                    "AplicarMaxDosCliente": manifiesto.parameters.aplicar_max_dos_cliente,
                    "CuotaPMC": manifiesto.parameters.cuota_pmc,
                    "output_filename": manifiesto.output.filename,
                },
            )
            marca_blob = f"{manifiesto.audit.prefix}/idempotencia.json"
            marca_previa: bytes | None = None
            if storage.existe(manifiesto.audit.container, marca_blob):
                with storage.abrir_lectura(manifiesto.audit.container, marca_blob) as fh:
                    marca_previa = fh.read()
            if marca_ya_procesado(marca_previa, clave_idempotencia):
                return ResultadoEjecucion(
                    estado=EstadoEjecucion.ALREADY_PROCESSED,
                    **base,
                    hash_entrada=hash_entrada,
                    hash_enriquecimiento=hash_enriquecimiento,
                    archivos_consumidos=archivos_consumidos,
                    control_cabecera_valido=True,
                    control_archivo_valido=True,
                    duraciones_segundos=duraciones,
                )

            fecha_cabecera = control_cabecera.cabecera.fecha_cabecera

            # --- pasada 2: reglas de negocio + formateo ---
            t0 = time.monotonic()
            detalles_autorizados = [
                _reconstruir_detalle_validado(fila) for fila in almacen.iterar_autorizados_ordenados()
            ]

        resultados_negocio = aplicar_reglas_negocio(
            detalles_autorizados,
            fecha_cabecera=fecha_cabecera,
            aplicar_filtro_30_dias=manifiesto.parameters.aplicar_filtro_30_dias,
            aplicar_max_dos_cliente=manifiesto.parameters.aplicar_max_dos_cliente,
            aplicar_filtro_antiguedad=manifiesto.parameters.aplicar_filtro_antiguedad,
        )

        lineas_salida: list[str] = []
        cantidad_emitida = 0
        cantidad_excluida_negocio = 0
        suma_primer_importe = Decimal("0")
        cantidad_enriquecimiento_coincidente = 0
        cantidad_enriquecimiento_sin_coincidencia = 0

        for r in resultados_negocio:
            if indice_record_join is not None:
                # Simulacion de cantidades para record_join (docs/matriz_equivalencia.md
                # seccion 8.1): se registra coincidencia/no-coincidencia contra
                # DebtEnrichmentPoc, pero NO se excluye de la salida por esto --
                # no hay confirmacion de que una deuda sin coincidencia deba
                # rechazarse, y el layout de salida no usa ninguna columna de
                # esta tabla.
                if enriquecer(r.detalle.convertido.id_deuda, indice_record_join) is not None:
                    cantidad_enriquecimiento_coincidente += 1
                else:
                    cantidad_enriquecimiento_sin_coincidencia += 1
                    filas_error.append(
                        FilaError(
                            run_id=manifiesto.run_id,
                            archivo=manifiesto.enrichment.blob,
                            numero_linea=r.detalle.linea.numero_linea,
                            categoria=CATEGORIA_ENRIQUECIMIENTO,
                            codigo="SIN_COINCIDENCIA_RECORD_JOIN",
                            campo="id_deuda",
                            motivo=f"id_deuda='{r.detalle.convertido.id_deuda}' sin fila correspondiente en DebtEnrichmentPoc (informativo, no excluye de la salida)",
                        )
                    )

            if not r.incluido:
                cantidad_excluida_negocio += 1
                filas_error.append(
                    FilaError(
                        run_id=manifiesto.run_id,
                        archivo=manifiesto.input.blob,
                        numero_linea=r.detalle.linea.numero_linea,
                        categoria=CATEGORIA_NEGOCIO,
                        codigo=r.motivo or "",
                        campo="detalle",
                        motivo="excluido por regla de negocio",
                    )
                )
                continue
            c = r.detalle.convertido
            try:
                linea_salida = formatear_detalle(
                    tipo_registro_det_pmc=manifiesto.parameters.tipo_registro_det_pmc,
                    referencia_cliente=c.referencia_cliente,
                    id_deuda=c.id_deuda,
                    primer_vencimiento=c.primer_vencimiento,
                    importe_principal=c.importe_principal,
                    segundo_vencimiento=c.segundo_vencimiento,
                    importe_segundo_vencimiento=c.importe_segundo_vencimiento,
                    tercer_vencimiento=c.tercer_vencimiento,
                    importe_tercer_vencimiento=c.importe_tercer_vencimiento,
                    concepto=c.concepto,
                    cuota_pmc=manifiesto.parameters.cuota_pmc,
                )
            except OutputFormatError as exc:
                cantidad_excluida_negocio += 1
                filas_error.append(
                    FilaError(
                        run_id=manifiesto.run_id,
                        archivo=manifiesto.input.blob,
                        numero_linea=r.detalle.linea.numero_linea,
                        categoria=CATEGORIA_FORMATO_SALIDA,
                        codigo="DESBORDE_FORMATO_SALIDA",
                        campo="detalle",
                        motivo=str(exc),
                    )
                )
                continue

            lineas_salida.append(linea_salida)
            cantidad_emitida += 1
            suma_primer_importe += c.importe_principal

        duraciones["reglas_y_formato"] = time.monotonic() - t0

        if cantidad_emitida == 0:
            ruta_errores = _publicar_errores()
            return ResultadoEjecucion(
                estado=EstadoEjecucion.REJECTED,
                **base,
                hash_entrada=hash_entrada,
                hash_enriquecimiento=hash_enriquecimiento,
                archivos_consumidos=archivos_consumidos,
                cantidad_leida=cantidad_leida,
                cantidad_valida=cantidad_valida,
                cantidad_rechazada=cantidad_rechazada,
                cantidad_excluida_negocio=cantidad_excluida_negocio,
                importe_total_declarado=control_archivo.importe_total_declarado,
                importe_total_calculado=control_archivo.importe_total_calculado,
                control_cabecera_valido=True,
                control_archivo_valido=True,
                duraciones_segundos=duraciones,
                ruta_errores=ruta_errores,
                motivos_rechazo_globales=("CERO_DETALLES_EMITIDOS",),
                warnings=["archivo con controles validos pero cero detalles sobrevivieron a las reglas de negocio"],
            )

        try:
            cabecera_linea = formatear_cabecera(
                tipo_registro_cab_pmc=manifiesto.parameters.tipo_registro_cab_pmc,
                cod_banco_final=cod_banco_final,
                codigo_servicio_final=codigo_servicio_final,
                fecha_cabecera=fecha_cabecera,
            )
            pie_linea = formatear_pie(
                tipo_registro_pie_pmc=manifiesto.parameters.tipo_registro_pie_pmc,
                cod_banco_final=cod_banco_final,
                codigo_servicio_final=codigo_servicio_final,
                fecha_cabecera=fecha_cabecera,
                cantidad_emitidos=cantidad_emitida,
                suma_primer_importe=suma_primer_importe,
            )
        except OutputFormatError as exc:
            return ResultadoEjecucion(
                estado=EstadoEjecucion.FAILED,
                **base,
                hash_entrada=hash_entrada,
                hash_enriquecimiento=hash_enriquecimiento,
                archivos_consumidos=archivos_consumidos,
                duraciones_segundos=duraciones,
                warnings=[f"error de formato en cabecera/pie: {exc}"],
            )

        newline = "\r\n" if manifiesto.format.output_newline == "CRLF" else "\n"
        texto_completo = newline.join([cabecera_linea, *lineas_salida, pie_linea])
        if manifiesto.format.final_newline:
            texto_completo += newline
        contenido_bytes = texto_completo.encode(manifiesto.format.output_encoding)
        if manifiesto.format.output_bom:
            contenido_bytes = b"\xef\xbb\xbf" + contenido_bytes

        nombre_salida = f"{manifiesto.output.prefix}/{manifiesto.output.filename}"
        storage.escribir_bytes(manifiesto.output.container, nombre_salida, contenido_bytes)
        archivos_producidos = [f"{manifiesto.output.container}/{nombre_salida}"]

        storage.escribir_bytes(manifiesto.audit.container, marca_blob, construir_marca(clave_idempotencia, run_id=manifiesto.run_id))

        ruta_errores = _publicar_errores()

        estado_final = (
            EstadoEjecucion.SUCCEEDED
            if cantidad_rechazada == 0 and cantidad_excluida_negocio == 0
            else EstadoEjecucion.SUCCEEDED_WITH_REJECTIONS
        )

        return ResultadoEjecucion(
            estado=estado_final,
            **base,
            hash_entrada=hash_entrada,
            hash_enriquecimiento=hash_enriquecimiento,
            archivos_consumidos=archivos_consumidos,
            archivos_producidos=archivos_producidos,
            cantidad_leida=cantidad_leida,
            cantidad_valida=cantidad_valida,
            cantidad_rechazada=cantidad_rechazada,
            cantidad_excluida_negocio=cantidad_excluida_negocio,
            cantidad_emitida=cantidad_emitida,
            cantidad_enriquecimiento_coincidente=cantidad_enriquecimiento_coincidente,
            cantidad_enriquecimiento_sin_coincidencia=cantidad_enriquecimiento_sin_coincidencia,
            importe_total_declarado=control_archivo.importe_total_declarado,
            importe_total_calculado=control_archivo.importe_total_calculado,
            importe_total_salida=suma_primer_importe,
            control_cabecera_valido=True,
            control_archivo_valido=True,
            duraciones_segundos=duraciones,
            ruta_errores=ruta_errores,
        )
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
