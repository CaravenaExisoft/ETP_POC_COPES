# Reporte de POC: ADF Mapping Data Flow vs. motor `etl_pmc` (Azure Container Apps)

**Alcance**: se evalúan **dos opciones independientes** para la transformación de deuda SAP a TXT Banelco/Pago Mis Cuentas — el Mapping Data Flow de Azure Data Factory (`DF_GENERAR_BANELCO_copy1` dentro de `PL_EJECUTAR_ETL_POC_REAL`) y el motor Python `etl_pmc`, perfil `poc_pmc`, destinado a Azure Container Apps. **Integrar ambas opciones entre sí no es requisito de esta POC** y no se evalúa en este documento.

**Fecha de corte de la evidencia**: 2026-09-23. **Estado general**: ninguna de las dos opciones tiene, a la fecha de este reporte, una comparación controlada y equivalente entre sí — hay diferencias de configuración, de entorno de medición y de alcance funcional que se detallan más abajo. Este documento no certifica equivalencia funcional, cumplimiento de SLA productivo, ni ventaja de costo.

---

## 1. Resumen ejecutivo

- **Ambas opciones procesaron con éxito un lote de 660.000 detalles** (`Succeeded` en ADF; `SUCCEEDED` en el motor), sin filas de error reportadas en ninguna de las dos. Esto confirma que **ambas rutas de procesamiento pueden completar el volumen de evaluación previsto**, no que produzcan el mismo resultado byte a byte (no se comparó la salida de ambas con `compare-adf`; no hay export de ADF disponible para esa comparación — ver §4 y §7).
- **Tiempos observados no son directamente comparables todavía**: el dato de ADF (`319 s` de Data Flow, corrida en Azure) y el dato del motor (`62,07 s`) provienen de **entornos de medición distintos** (Azure real vs. una máquina de desarrollo local, un solo proceso) **y de configuraciones distintas** (ADF usa lo que el responsable de la prueba describe como "configuración global"; la corrida citada del motor usa el modo `record_join` con 250.000 filas de enriquecimiento **más una validación de schema XSD inventada** para fines de medición, no un requisito productivo). Los cocientes descriptivos que resultan de estos números (**≈3,01× y ≈5,14×**, ver §3) son comparaciones entre mediciones distintas, **no una aceleración certificada ni un ahorro de costo**.
- **La identidad del archivo de entrada (mismo lote de 660.000 detalles en ambas pruebas) fue confirmada por el responsable de la prueba**, pero **no está verificada criptográficamente entre ambos entornos**: se dispone del SHA-256 del archivo usado en las corridas del motor; no se dispone de un hash equivalente del lado de ADF (§2, §9).
- **Quedan sin resolver, y se listan como pendientes priorizados (§7)**: XSD productivo (no existe; se usó uno inventado para medir costo), campo de antigüedad confiable (no existe; se usó una posición inventada), ambigüedad del layout de pie productivo (346 vs. 348 bytes), confirmación de si los flags de 30 días / máximo dos recibos estaban activos en la corrida de ADF medida, y evidencia de comportamiento negativo/de error del lado de ADF (las tres corridas de ADF disponibles terminaron en `Succeeded`).
- **Recomendación** (condicionada a la evidencia disponible, ver §8): continuar la POC recolectando una corrida controlada y comparable (misma configuración de enriquecimiento, mismos flags, ambas en su entorno real de destino) antes de sacar conclusiones de performance o de equivalencia funcional.

---

## 2. Inventario de evidencia — estado confirmado / reportado / pendiente

| Ítem | Estado | Detalle |
|---|---|---|
| Código y tests del motor `etl_pmc` | **Confirmado** | Repositorio `ETP_POC_COPES`, 153 tests automatizados (`pytest -q`), sin necesidad de Azure |
| Corridas del motor contra 660.000 detalles (4 configuraciones) | **Reportado** | Ejecutadas y observadas en esta sesión de trabajo; ver §3 |
| SHA-256 del archivo de 660.000 usado por el motor | **Confirmado** | `9863c2f2b0aa1633f7be2eb8b6e85c7710a7ddbe58d1f91cfab50a30d97636f5` (constante en las 4 corridas del motor) |
| SHA-256 del archivo de 660.000 usado por ADF | **Pendiente** | No provisto; la identidad de archivo entre entornos descansa en la confirmación verbal del responsable, no en un hash comparado |
| Corridas de `PL_EJECUTAR_ETL_POC_REAL` (Azure Monitor) | **Reportado** | 3 corridas, capturas de pantalla del usuario, 2026-09-23; ver §3 |
| Detalle de actividad `DF_GENERAR_BANELCO_copy1` | **Reportado** | Solo para 1 de las 3 corridas (la de 369 s); las otras 2 sin desglose de actividad |
| Vínculo de las otras 2 corridas de ADF con el archivo de 660.000 | **Pendiente** | No hay `FilasSalida` ni desglose de actividad que lo confirme para esas 2 corridas |
| Flags `AplicarFiltro30Dias` / `AplicarMaxDosCliente` en la corrida de ADF medida | **Pendiente** | No informado si estaban activos o no |
| XSD productivo | **Pendiente / no existe** | Se usó un schema **inventado** solo para medir costo de un paso de validación (`etl_pmc/config/schema_sintetico/registro_sap_sintetico.xsd`) |
| Campo de antigüedad confiable (>10 meses) | **Pendiente / no existe** | Se usó una posición de campo **inventada** (`fecha_emision_deuda_sintetica`, detalle, posición 152) para poder simular el filtro; ver `docs/matriz_equivalencia.md` §9.1 |
| Layout de pie productivo | **Pendiente / ambiguo** | El documento fuente (GDC-1000) es internamente inconsistente entre 346 y 348 bytes; el perfil `poc_pmc` usa 280 bytes, sin resolver esa ambigüedad |
| Comportamiento de ADF ante desborde de campo (ej. `ReferenciaCliente` > 19 caracteres) | **Pendiente** | No confirmado; el motor lo trata como rechazo explícito (`OutputFormatError`), decisión de POC más estricta que lo conocido de ADF, no verificada |
| Evidencia de rechazo/error del lado de ADF | **Pendiente** | Las 3 corridas de ADF disponibles terminan en `Succeeded`; no se proveyó ninguna corrida en estado de error o rechazo |
| Evidencia de polling de ADF (detección de archivo) | **Pendiente** | No se proveyó evidencia de esta sesión sobre el comportamiento real de polling |
| Evidencia de idempotencia / omisión de lote ya procesado — motor | **Confirmado** | Test automatizado, ver §6 |
| Evidencia de idempotencia / omisión de lote ya procesado — ADF | **Pendiente** | No se proveyó evidencia de una corrida repetida deliberada sobre el mismo lote en ADF |
| Container Apps Job desplegado en Azure | **Parcial** | Imagen construida y publicada en ACR (`acrargoexi`, 2 builds exitosos); identidad administrada creada (`uami-job-etl-pmc`); permisos RBAC y creación del Job **bloqueados por una restricción de permisos (condición ABAC)** sobre la cuenta usada, pendiente de resolución por un administrador con más privilegios |
| CI/CD (GitHub Actions) | **Parcial** | Suite de tests corriendo en cada push; job de build/deploy configurado pero pendiente de las variables de Azure (bloqueado por el mismo motivo que el punto anterior) |

---

## 3. Resultados por corrida y por entorno

### 3.1 Azure Data Factory — pipeline `PL_EJECUTAR_ETL_POC_REAL`

| RunId | Inicio (UTC) | Fin (UTC) | Duración de pipeline (s) | Estado | Vínculo confirmado a archivo de 660.000 |
|---|---|---|---:|---|---|
| `f6100c48-f91d-4d6c-85d1-52c2a3b5947e` | 2026-09-23T19:50:22Z | 2026-09-23T19:56:31Z | 369 | Succeeded | **Sí** — ver detalle de actividad abajo (`FilasSalida=660.002`) |
| `3489884c-c5a0-41ff-9544-2d2ad9a5ab8c` | 2026-09-23T19:38:32Z | 2026-09-23T19:43:38Z | 306 | Succeeded | Pendiente — sin detalle de actividad provisto |
| `2ab478fd-d443-4dca-9623-b633c071cdee` | 2026-09-23T19:35:31Z | 2026-09-23T19:35:54Z | 23 | Succeeded | Pendiente — duración muy corta; posible corrida por rama de comprobación de archivo sin ejecución del Data Flow, **no confirmado** |

Mediana / mínimo / máximo de duración de pipeline (n=3, sin filtrar por volumen confirmado): mediana 306 s, mínimo 23 s, máximo 369 s. **Esta mediana no debe leerse como "tiempo típico para 660.000 registros"**: solo 1 de las 3 corridas tiene el volumen confirmado.

**Detalle de actividad `DF_GENERAR_BANELCO_copy1`** (única corrida con vínculo confirmado, `RunId f6100c48...`):

| Métrica | Valor | Unidad |
|---|---:|---|
| Estado | Succeeded | — |
| Inicio de actividad (UTC) | 2026-09-23T19:51:10Z | — |
| Fin de actividad (UTC) | 2026-09-23T19:56:29Z | — |
| Duración total del Data Flow | 319 | s |
| Arranque de clúster | 131,924 | s |
| Sin arranque* | 187,076 | s |
| Receptor Banelco | 111,926 | s |
| Receptor errores | 31,193 | s |
| Filas de salida | 660.002 | filas |
| Filas de error | 0 | filas |

\* "Sin arranque" incluye tareas internas del motor de Data Flow (Spark); **no es tiempo de CPU puro**. El total del Data Flow (319 s) es el tiempo de **esa actividad**, no del pipeline completo (369 s) — la diferencia (50 s) corresponde a otras actividades del pipeline (`EpComprobarEntrada`, `PL_EXTRAER_SQL`, orquestación), no desglosadas en esta evidencia.

### 3.2 Motor `etl_pmc` — benchmarks LOCALES, un solo proceso, **no medidos en Azure Container Apps**

| Config. | Enriquecimiento | Schema sintético (inventado) | Filtros de negocio | Total interno* (s) | Total de proceso (s) |
|---|---|---|---|---:|---:|
| A (línea base) | `single_configuration`, 1 fila | Apagado | Apagados | 89,86 | 91,20 |
| B | `record_join`, 1.000 filas | Apagado | Apagados | 82,28 | 86,17 |
| C | `record_join`, 250.000 filas | Apagado | Apagados | 53,45 | 56,97 |
| **D** — citada en este reporte | `record_join`, 250.000 filas | **Encendido** | Apagados | 70,09** | **62,07** |

\* Suma de los tiempos por fase que reporta el propio motor (`duraciones_segundos`). \*\* Ver nota crítica abajo.

**Desglose de la corrida D** (la que trae los números citados para este reporte):

| Fase | Duración (s) |
|---|---:|
| Enriquecimiento (`record_join`, carga de 250.000 filas) | 1,08 |
| Lectura y validación | 33,72 |
| Validación de schema sintético (inventado) | 10,59 |
| Reglas de negocio y formato | 24,70 |
| **Suma de fases** | **70,09** |
| **Total de proceso reportado** | **62,07** |

> **Nota crítica, sin reconciliar**: la suma de las 4 fases (70,09 s) **no coincide** con el total de proceso reportado (62,07 s) — la suma excede al total en ~8 s. No se determinó en esta sesión si hay superposición entre fases (ejecución parcialmente concurrente), un artefacto de medición, o si el "total de proceso" mide algo distinto a la suma de fases internas. **Se deja pendiente la definición de ese solapamiento** (§7) y no se corrige ni se apila una cifra sobre otra en este reporte.

Estado de las 4 corridas: `SUCCEEDED`, 660.000 detalles emitidos, 0 rechazados, 0 excluidos por reglas de negocio (los filtros de 30 días y máximo 2 recibos estaban **apagados** en las 4). SHA-256 del archivo de entrada, idéntico en las 4: `9863c2f2b0aa1633f7be2eb8b6e85c7710a7ddbe58d1f91cfab50a30d97636f5`.

Mediana / mínimo / máximo del total de proceso (n=4): ordenados 56,97 / 62,07 / 86,17 / 91,20 → **mediana 74,12 s**, **mínimo 56,97 s**, **máximo 91,20 s**. **Importante**: estas 4 corridas **no son repeticiones de la misma configuración** (difieren en modo de enriquecimiento y en si la validación de schema estaba encendida) — esta mediana describe el **rango observado bajo variantes de configuración**, no "la" performance del motor bajo una condición fija. Una batería de repeticiones bajo una única configuración fija queda pendiente (§7).

### 3.3 Cocientes descriptivos (usando la corrida D del motor, la única con desglose citado en este reporte)

| Comparación | Cálculo | Resultado |
|---|---|---:|
| Data Flow total vs. motor (config. D) | 319 s ÷ 62,07 s | **≈5,14×** |
| Data Flow sin arranque vs. motor (config. D) | 187,076 s ÷ 62,07 s | **≈3,01×** |

**Estas cifras son descriptivas, no certificadas.** Comparan un runtime medido *dentro de Azure* (ADF) contra un runtime medido *localmente en una máquina de desarrollo* (motor), bajo configuraciones de enriquecimiento no equivalentes ("configuración global" en ADF, según el responsable de la prueba, vs. `record_join` de 250.000 filas + validación de schema inventada en el motor). No implican una aceleración certificada del motor sobre ADF ni un ahorro de costo — para eso hace falta una corrida controlada de ambas opciones bajo la misma configuración funcional y, del lado del motor, dentro del entorno real de Azure Container Apps (no local).

---

## 4. Matriz de equivalencia y divergencias (resumen)

El detalle completo, campo por campo, está en `docs/matriz_equivalencia.md`. Resumen de los puntos relevantes para este reporte:

| Punto | Estado en la matriz actual | Nota |
|---|---|---|
| Export de ADF confiable disponible | **No existe** | Ningún dato de layout/reglas del motor está clasificado `CONFIRMADA_ADF`; todo lo que no viene del prompt normativo es `SUPUESTO_POC` o `PROPUESTA_GUIA`, verificado empíricamente contra el único archivo real disponible (`entrada_real_1000.txt`) |
| Población del control de totales (todos los detalles vs. solo válidos) | **Divergencia abierta** | Decisión de POC documentada, sin confirmación contra ADF real |
| Máximo 2 recibos por cliente: ¿lo garantiza SAP en origen o es un filtro del transformador? | **Divergencia abierta** | GDC-1000 lo menciona como alcance funcional del proceso completo, no como filtro explícito de la etapa de transformación |
| Layout de pie productivo (346 vs. 348 bytes) | **Ambigüedad no resuelta, a propósito** | El perfil `poc_pmc` usa 280 bytes; no se inventó una resolución de esa ambigüedad, conforme a instrucción explícita del prompt original |
| Desborde de campo crudo (`ReferenciaCliente` > 19 caracteres) | **No resuelta** | El motor **rechaza el registro** (`OutputFormatError`) en vez de truncar en silencio, tras revisar GDC-1000 §B ("el valor de SAP, luego de TRIM, no puede superar la longitud del campo destino, es error"); el comportamiento real de ADF ante este caso **no está confirmado** |
| Truncamiento de mensajes Ticket/Pantalla a 40/15 posiciones | **Implementado, sin divergencia conocida** | El motor trunca estos dos campos **compuestos** (no campos crudos de SAP) a 40 y 15 posiciones respectivamente, tal como indica GDC-1000; no se identificó una divergencia distinta a la del punto anterior |
| Filtro de antigüedad >10 meses | **Simulado, no productivo** | Posición de campo inventada; ver §2 y `docs/matriz_equivalencia.md` §9.1 |
| Control de formato tipo XSD | **Simulado, no productivo** | Schema inventado; ver §2 y `docs/matriz_equivalencia.md` §8.1 |
| TRIM antes de mapear valores de la Tabla Intermedia | **Implementado** | `enrichment/single_configuration.py`, verificado con tests unitarios |
| Normalización de vocales acentuadas en mensajes | **Implementado** | Requisito explícito de GDC-1000 §C; verificado con tests unitarios |
| Flags 30 días / máximo 2 recibos (motor) | **Implementados, apagados por defecto** | Ambos verificados con tests unitarios y con corridas reales contra `entrada_real_1000.txt` (ver §5); estado de estos flags en la corrida de ADF medida en este reporte: **pendiente** |

**No se afirma equivalencia entre ADF y el motor por el solo hecho de que ambos terminen en estado exitoso** (`Succeeded` / `SUCCEEDED`): no hay comparación de la salida byte a byte (`compare-adf`) contra una salida real de ADF del mismo lote, porque esa salida no está disponible para este reporte.

---

## 5. Pruebas negativas — esperado vs. observado

| Caso | Esperado | Observado | Tipo | Evidencia |
|---|---|---|---|---|
| CSV de enriquecimiento faltante (`single_configuration`) | Rechazo de archivo completo, motivo explícito | `REJECTED`, motivo `ARCHIVO_FALTANTE`, fila de auditoría generada | Error técnico de configuración de la corrida | `tests/integration/test_pipeline_end_to_end.py::test_pipeline_rechaza_si_falta_csv_de_enriquecimiento` |
| Filtro de antigüedad activado (posición inventada) contra `entrada_real_1000.txt` | Rechazo generalizado, dado que la posición no tiene base real | `REJECTED`, 1.000/1.000 detalles excluidos por `ANTIGUEDAD_SUPERA_10_MESES`, motivo global `CERO_DETALLES_EMITIDOS` | Rechazo de negocio (por diseño, sobre una regla simulada) | Corrida real de esta sesión, `docs/entrada_real_1000.txt` |
| Filtros 30 días + máximo 2 recibos activados contra `entrada_real_1000.txt` (archivo con solo 3 `ReferenciaCliente` distintos) | Reducción drástica por baja diversidad de clientes en ese archivo puntual | `SUCCEEDED_WITH_REJECTIONS`, 994/1.000 excluidos (`MAXIMO_DOS_RECIBOS_CLIENTE`), 6 emitidos | Rechazo de negocio (comportamiento correcto del filtro, dato de entrada no representativo) | Corrida real de esta sesión |
| `ReferenciaCliente` > 19 caracteres (campo crudo SAP) | Rechazo explícito, no truncamiento | Confirmado a nivel unitario (`OutputFormatError`) | Error técnico de formato de salida | `tests/unit/test_formatting_output.py::test_referencia_cliente_mas_de_19_caracteres_desborda` (no probado a nivel de corrida completa end-to-end) |
| Reprocesamiento del mismo lote (idempotencia) | Segunda corrida detectada como ya procesada, sin republicar salida | `ALREADY_PROCESSED` | Salida correcta (comportamiento esperado) | `tests/integration/test_pipeline_end_to_end.py::test_pipeline_es_idempotente_en_la_segunda_corrida` |
| Casos de error/rechazo del lado de ADF | — | **Sin evidencia provista** — las 3 corridas de ADF disponibles terminan en `Succeeded` | — | **Pendiente** |

---

## 6. Evidencia de polling y de omisión de lotes ya procesados

- **Motor (`etl_pmc`)**: confirmado por test automatizado. Una primera corrida contra un lote produce `SUCCEEDED` y una marca de idempotencia (hash de entrada + hash de snapshot de enriquecimiento + perfil + parámetros relevantes); una segunda corrida contra el mismo lote y misma configuración se detecta como `ALREADY_PROCESSED`, sin volver a publicar la salida. Fuente: `tests/integration/test_pipeline_end_to_end.py::test_pipeline_es_idempotente_en_la_segunda_corrida`.
- **ADF**: el polling de detección de archivo (cada 5 minutos para la demo, 15 minutos como referencia futura, según GDC-1000 y el prompt normativo) es responsabilidad de ADF por diseño de esta POC. **No se proveyó, en esta sesión, evidencia de una corrida repetida deliberada sobre el mismo lote en ADF**, ni logs del comportamiento real de polling. **Pendiente.**

---

## 7. Pendientes priorizados

1. **Obtener un export confiable de ADF** (Data Flow completo, con los sinks de salida `DS_SALIDA_PMC_V2`/`DS_ERRORES_PMC_V2` que se están incorporando) para poder promover reglas de `SUPUESTO_POC`/`PROPUESTA_GUIA` a `CONFIRMADA_ADF` en la matriz de equivalencia.
2. **Correr `compare-adf`** contra una salida real de ADF del mismo lote y la salida del motor, para una comparación byte a byte — hoy no hay salida real de ADF disponible para esto.
3. **Confirmar si los flags de 30 días / máximo 2 recibos estaban activos** en la corrida de ADF de 369 s/319 s citada en este reporte.
4. **Reconciliar la discrepancia entre la suma de fases (70,09 s) y el total reportado (62,07 s)** de la corrida D del motor (§3.2) — no resuelta en esta sesión.
5. **Ejecutar el motor dentro de Azure Container Apps real** (no local) para que una comparación de tiempos contra ADF sea metodológicamente válida.
6. **Correr una batería de repeticiones bajo una configuración fija** (misma cantidad de filas de enriquecimiento, mismo estado de schema/filtros) en ambos entornos, para tener una mediana/mínimo/máximo comparable entre sí, no solo dentro de cada entorno.
7. **Resolver el bloqueo de permisos RBAC** (condición ABAC sobre la cuenta `caravena@exisoft.com.ar`) que impide hoy crear el Container Apps Job real y completar el pipeline de CI/CD.
8. **Definir el campo real de antigüedad de deuda** (o confirmar que la regla de 10 meses no aplica a esta POC) y, si corresponde, el XSD productivo real — ambos siguen simulados con datos inventados.
9. **Resolver la ambigüedad del layout de pie productivo** (346 vs. 348 bytes) contra una fuente autorizada, o confirmar formalmente que queda fuera de alcance de esta POC.
10. **Obtener evidencia de rechazo/error del lado de ADF** (hoy solo hay corridas exitosas) y de su comportamiento de polling/reprocesamiento.

---

## 8. Recomendación condicionada por evidencia

Con la evidencia disponible a la fecha de este reporte:

- **No se recomienda** tomar una decisión de arquitectura (elegir Data Flow vs. Container App como solución definitiva) basada en los tiempos de este reporte: las mediciones no son metodológicamente comparables (entornos distintos, configuraciones distintas, sin corrida controlada).
- **Sí se puede afirmar**, con la evidencia disponible, que **ambas opciones completan el volumen de 660.000 detalles sin errores** en sus respectivas corridas citadas — esto valida que ninguna de las dos opciones está descartada por incapacidad de procesar el volumen objetivo.
- **Se recomienda priorizar los pendientes 1, 2 y 5** de la sección anterior (export de ADF, `compare-adf` contra salida real, y corrida del motor dentro de Azure real) antes de emitir cualquier comparación de performance o costo con valor de decisión.
- Esta recomendación **no constituye** una afirmación de conformidad total con requisitos productivos, de cumplimiento de SLA, ni de ventaja de costo — ninguna de las dos está evaluada todavía con evidencia suficiente para eso.

---

## 9. Índice de fuentes

- Esta sesión de trabajo (2026-09-23): capturas de Azure Monitor/consulta de ejecución de `PL_EJECUTAR_ETL_POC_REAL` y de la actividad `DF_GENERAR_BANELCO_copy1`, provistas por el usuario; capturas del diseño del Data Flow (`SRCSAP`, `DS_ENTRADA_REAL_TXT`, `LS_ADLS_POC`); benchmarks del motor `etl_pmc` (4 corridas contra 660.000 detalles, corridas contra `entrada_real_1000.txt` con distintos flags).
- `docs/matriz_equivalencia.md` — reglas confirmadas/propuestas/supuestas/inventadas, con su origen.
- `docs/supuestos_y_pendientes.md` — limitaciones conocidas, benchmark histórico del motor (1.000/100.000/660.000 filas sin schema), hallazgos de escala.
- `docs/gdc1000_vs_container_app.md` — checklist paso a paso GDC-1000 vs. implementación.
- `docs/integracion_adf.md` — diseño de integración propuesto entre ADF y el Job (no implementado aún, ver pendiente 7).
- `Prompt_Container_Apps_ETL_Equivalente_ADF_Poc.md` — especificación normativa de esta POC.
- `tests/unit/`, `tests/integration/` — 153 tests automatizados; los citados puntualmente en §5 y §6.
- `src/etl_pmc/config/schema_sintetico/registro_sap_sintetico.xsd`, `src/etl_pmc/rules/pmc.py` — implementación de las dos reglas simuladas/inventadas (schema XSD, filtro de antigüedad).
