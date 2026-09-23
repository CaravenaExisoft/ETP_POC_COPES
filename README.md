# etl-pmc — Motor ETL Pago Mis Cuentas (POC, Azure Container Apps Job)

Motor Python que reemplaza el **motor de transformación** del Mapping Data Flow `DF_TRANSFORMAR_BANELCO_POC` para correr como Azure Container Apps Job: lee un TXT SAP de ancho fijo y un CSV de enriquecimiento ya extraído por ADF, valida, aplica reglas de Pago Mis Cuentas y escribe el archivo Banelco de salida. ADF conserva la detección de archivo, la extracción SQL y la orquestación (ver `Prompt_Container_Apps_ETL_Equivalente_ADF_Poc.md`, la especificación normativa de este proyecto).

**Estado**: no hay un export ADF confiable disponible (ver `docs/matriz_equivalencia.md` sección 0), así que nada acá se presenta como "equivalente a ADF" — es el perfil `poc_pmc`, verificado empíricamente contra el único archivo real disponible y probado de punta a punta en modo local. El detalle completo de qué está confirmado, qué es propuesta, y qué falta está en `docs/matriz_equivalencia.md` y `docs/supuestos_y_pendientes.md`.

## Instalación

Requiere Python 3.11+.

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate   |   Linux/Mac: source .venv/bin/activate
pip install -e ".[dev]"
```

## Pruebas

```bash
pytest -q
```

153 tests (unitarios + integración), sin necesidad de Azure. Incluyen:

- Verificación de layout y control de totales contra el archivo real `docs/entrada_real_1000.txt` (copiado a `tests/fixtures/real/`).
- Corrida end-to-end del pipeline completo en modo local (`tests/integration/test_pipeline_end_to_end.py`).
- Corridas contra lotes sintéticos con casos malos inyectados (`tests/integration/test_pipeline_synthetic.py`).
- CLI instalada, ejecutada como subproceso lógico vía `etl_pmc.cli.main` (`tests/integration/test_cli.py`).

Para correr un solo archivo o test: `pytest -q tests/unit/test_layout_totales.py -k control_de_totales`.

## Ejecución local (sin Azure)

Un "container" es una subcarpeta de `--local-root`; un "blob" es una ruta relativa dentro de esa subcarpeta — así el mismo manifiesto sirve para modo local y modo Azure.

```bash
# Estructura esperada bajo <root>/:
#   inbound/sap/demo/lote_real001/entrada_real_1000.txt
#   enrichment/sap/demo/lote_real001/enrichment.csv
#   (out/, audit/, error/ se crean solos al escribir)

etl-pmc run --manifest <root>/manifiesto.json --local-root <root> --result-out <root>/resultado.json
```

Ver `examples/manifiesto.example.json` y `examples/resultado.example.json`: son el manifiesto y el resultado **reales** de una corrida contra `docs/entrada_real_1000.txt` con un CSV de enriquecimiento sintético (`examples/enrichment_single_configuration.example.csv`, no hay uno real disponible).

## Generar un lote sintético de prueba

```bash
generate-fixture --cantidad 1000 --seed 42 --out lote_sintetico.txt --out-enrichment enrichment_sintetico.csv
```

Datos completamente ficticios, con semilla reproducible. Ver `etl_pmc.tools.generate_fixture.CASOS_MALOS_DISPONIBLES` para inyectar casos malos controlados (moneda inválida, ID con letras, fecha de calendario inválida, longitud incorrecta, etc.) vía la función `generar_lote_sintetico(..., casos_malos={...})`.

## Comparar contra una salida ADF real

```bash
compare-adf --adf salida_adf.txt --container salida_container.txt [--redact] [--semantic]
```

Compara SHA-256 y bytes completos primero; si difieren, reporta línea/posición/campo de la primera diferencia según el layout de salida de 280 posiciones. `--semantic` agrega (sin reemplazar la comparación exacta) un conteo por multiconjunto de detalles, útil si el orden no es significativo. `--redact` enmascara campos con datos personales (`ReferenciaCliente`, `IdDeuda`) en el reporte. **No hay una salida ADF real de este lote para comparar todavía** — sin eso, no hay equivalencia certificada, solo el motor probado contra sí mismo y contra fixtures sintéticas.

## Demo local con interfaz web

**Esto no es el Container Apps Job** — es una herramienta de desarrollo aparte, pensada para mostrar el motor sin usar la línea de comandos. Corre 100% local (`127.0.0.1`), llama a la misma función `etl_pmc.pipeline.ejecutar` que usa la CLI, y no se instala en la imagen Docker (Flask vive en el extra opcional `demo`, que el `Dockerfile` nunca instala).

```bash
pip install -e ".[demo]"
python demo_ui/server.py
# abrir http://127.0.0.1:5050
```

Subís el TXT de entrada (y opcionalmente un CSV de enriquecimiento — si no subís uno, usa el de ejemplo del repo), tildás los filtros que quieras probar, apretás **Ejecutar**, y al terminar ves: estado y cantidades, tiempos medidos por etapa, una muestra decodificada de las primeras líneas de detalle del archivo de salida, y botones para descargar el archivo final, el `resultado.json`, el CSV de errores (si hubo) y el manifiesto usado. Las corridas quedan en `demo_ui/runs/<job_id>/` (ignorado por git).

## Docker

```bash
docker build -t etl-pmc:0.1.0 .
docker run --rm etl-pmc:0.1.0 run --help
```

La imagen no expone puertos ni corre un servidor: es un job batch finito, proceso no root (ver `Dockerfile`). Para correr una corrida local dentro del contenedor, montar el directorio raíz local como volumen y pasar `--local-root` apuntando al punto de montaje.

## Azure

`infra/deploy_container_app_job.sh` tiene los comandos de Azure CLI de referencia (build+push a ACR, identidad administrada, permisos mínimos, creación del Container Apps Job con trigger manual). **No se ejecutó nada de esto contra una suscripción real** — son comandos a revisar y correr manualmente, con placeholders explícitos para suscripción/resource group/ACR/environment/identidad, conforme a lo pedido (no desplegar sin autorización). `docs/integracion_adf.md` describe cómo `PL_EJECUTAR_ETL_POC` debería invocar el Job y leer su resultado, y qué queda pendiente de validar contra la documentación oficial de Azure antes de un primer intento real.

## Troubleshooting

- **`ConfigurationError` al arrancar**: el manifiesto tiene un campo faltante, un placeholder sin reemplazar (`<...>`), un booleano como string, un ancho de código incorrecto, o una ruta de blob con `..`/absoluta. El mensaje de error nombra el campo exacto — no es necesario adivinar.
- **`profile: adf_actual` falla siempre**: es intencional; no hay un layout `adf_actual` cargable todavía (ver "Estado" arriba). Usar `poc_pmc`.
- **`EnrichmentError` (`ARCHIVO_FALTANTE`, `CSV_VACIO`, `MULTIPLES_FILAS`, ...)**: problema con el CSV de enriquecimiento de esta corrida puntual, no del código. El archivo queda `REJECTED` con el motivo exacto en `resultado.motivos_rechazo_globales` y una fila en `error/<prefix>/errores_enriquecimiento.csv`.
- **Resultado `REJECTED` con `IMPORTES_NULOS_EN_POBLACION`**: al menos un detalle tiene el campo de importe principal en un formato que no matchea el patrón esperado (coma decimal, sin separador de miles). Por diseño, esto rechaza el archivo completo, no solo ese registro (ver `docs/matriz_equivalencia.md` sección 6).
- **`OutputFormatError` (via categoría `formato_salida` en el CSV de errores)**: un identificador o importe de un detalle puntual excede el ancho fijo de salida; ese detalle se excluye y se registra, el resto del archivo se sigue publicando.

## Estructura del repositorio

```
src/etl_pmc/          paquete instalable (parsing, validacion, control, enriquecimiento,
                       reglas de negocio, formateo de salida, storage, pipeline, cli, tools)
tests/unit/            tests sin Azure, por modulo
tests/integration/     pipeline y CLI de punta a punta (local, sin Azure)
tests/fixtures/real/   copia de docs/entrada_real_1000.txt para los tests
docs/                  spec normativa, matriz de equivalencia, integracion ADF, pendientes
examples/              manifiesto y resultado reales de una corrida, CSV de enriquecimiento sintetico
infra/                 comandos de Azure CLI de referencia (no ejecutados)
demo_ui/               pagina web local de demo (Flask, no forma parte del Job ni de la imagen Docker)
Dockerfile, .dockerignore
```
