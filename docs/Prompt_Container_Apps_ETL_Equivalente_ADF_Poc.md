# Prompt — Implementar el motor ETL en Azure Container Apps Jobs

Copiá el contenido desde «INICIO DEL PROMPT» hasta el final en la IA que va a implementar el proyecto. Adjuntá, cuando estén disponibles, el JSON/script del Data Flow vigente, sus datasets y pipelines, el TXT real de ejemplo, el CSV de enriquecimiento correspondiente y una salida ADF del mismo lote. Adjuntá también `GDC-1000_Proceso_Pago_Mis_Cuentas.md` y `Guia_Implementacion_POC_ADF_Pago_Mis_Cuentas.docx`.

La guía describe modificaciones propuestas: no constituye evidencia de que todas estén desplegadas. El prompt exige distinguir esa propuesta del comportamiento real de ADF. Sin exportación y archivos comparables se puede implementar y probar la POC, pero no certificar equivalencia.

---

## INICIO DEL PROMPT

Actuá como ingeniero senior Python, arquitecto Azure y especialista en procesamiento batch de archivos de ancho fijo. Implementá el código completo de un motor ETL para ejecutarse como **Azure Container Apps Job**, funcionalmente equivalente al flujo de Azure Data Factory descrito a continuación.

Quiero código ejecutable y verificable, no solamente una propuesta ni pseudocódigo. Trabajá sobre el repositorio disponible, conservando cambios existentes. Si no existe proyecto, creá uno. No despliegues recursos ni modifiques Azure sin mi autorización: entregá los archivos y comandos necesarios para hacerlo.

### 1. Contexto y objetivo

Estamos construyendo una POC para sustituir un proceso actual basado en IBM Integration Bus que recibe un TXT SAP de ancho fijo, valida registros y totales, incorpora datos de SQL y genera un TXT Banelco/Pago Mis Cuentas.

La primera implementación usa ADF Mapping Data Flow. Queremos una segunda implementación con código dentro de un contenedor para comparar fidelidad, tiempo y consumo. No hay que rediseñar el negocio ni reemplazar toda la orquestación.

ADF conserva estas responsabilidades:

1. Detectar/comprobar el archivo en Storage.
2. Realizar la extracción masiva desde SQL a Storage.
3. Iniciar el motor seleccionado y esperar su resultado terminal.
4. Verificar el resultado y gestionar archivo histórico/reprocesamiento.

El Container Apps Job reemplaza el **motor de transformación** del Mapping Data Flow. Lee desde Storage el TXT y el extracto ya generado, procesa el lote, escribe resultados y termina. No consulta SQL por cada registro, no incorpora SQL directo, FTP/SFTP, VPN ni SHIR en esta variante de la POC.

Es un trabajo batch finito: no es una API web, no necesita FastAPI/Flask, ingress ni un bucle permanente de polling. El polling de llegada permanece en ADF: cinco minutos para la demostración; quince minutos como referencia futura. El inicio del Job debe ser manual/invocado por ADF, no un segundo programador que duplique ejecuciones.

Volumen objetivo para diseñar: pruebas de unos 1.000 detalles y evaluación posterior hasta aproximadamente 500 MB / 630.000 registros. No prometas tiempos antes de medir. El menor tiempo observado en una muestra no demuestra rendimiento productivo.

### 2. Fuentes de verdad y manejo de información faltante

Antes de programar reglas, inventariá los adjuntos y creá `docs/matriz_equivalencia.md`.

Orden de referencia:

1. JSON/script del Data Flow vigente, datasets, parámetros efectivos y configuración de la ejecución: definen la implementación ADF que debemos replicar.
2. TXT, CSV de enriquecimiento y resultados de la misma ejecución: permiten verificar entradas, formatos, rechazos y salida real.
3. Guía de implementación: define cambios propuestos, que NO debés suponer desplegados.
4. GDC-1000: referencia de negocio; no obliga a implementar el 100 % para esta POC.

Ante diferencias entre estas fuentes, registralas. No corrijas silenciosamente ADF ni presentes una mejora como equivalencia. Clasificá cada regla como `CONFIRMADA_ADF`, `PROPUESTA_GUIA`, `SUPUESTO_POC` o `POSTERGADA`.

Para cada regla documentá: origen, nodo ADF, entrada, condición/expresión, orden de aplicación, módulo Python, test y estado de equivalencia.

Si falta el export ADF, avanzá con un perfil `poc_pmc` basado en las especificaciones disponibles y dejá la equivalencia como `NO_VERIFICADA`. No inventes un layout completo a partir de nombres de campos. Dejá las posiciones no conocidas como configuración requerida y un error de configuración claro; podés generar fixtures sintéticos para probar el motor, identificándolos como tales. No uses fixtures inventados como evidencia del formato real.

Si disponés del export, implementá el perfil `adf_actual`. Mantené `poc_pmc` separado cuando incluya reglas todavía no presentes allí. Compartí parser y funciones; no dupliques dos aplicaciones completas.

No bloquees todo el proyecto por reglas productivas postergables. Implementá lo verificable y enumerá al final solamente las carencias que impiden ejecutar el formato real o certificar paridad.

### 3. Componentes existentes y límites de integración

| Componente | Nombre conocido | Responsabilidad |
|---|---|---|
| Pipeline principal | `PL_EJECUTAR_ETL_POC` | Comprobación → extracción → transformación |
| Pipeline de comprobación | `PL_COMPROBAR_ENTRADA` | Existencia/tamaño; no ejecutar el motor sin archivo |
| Pipeline SQL | `PL_EXTRAER_SQL` | Extracción masiva al CSV de enriquecimiento |
| Actividad Data Flow | `DF_GENERAR_BANELCO` | Invoca el Mapping Data Flow; puede haber copias |
| Data Flow | `DF_TRANSFORMAR_BANELCO_POC` | Motor visual a comparar |
| Dataset TXT real | `DS_ENTRADA_REAL_TXT` | Entrada de ancho fijo |
| Dataset binario | `DS_ENTRADA_BIN` | Metadatos/copia binaria |
| Dataset enriquecimiento | `DS_ENRICHMENT_CSV` | Extracto SQL |
| Dataset salida | `DS_SALIDA_BANELCO_TXT` | Salida sin delimitador ni encabezado CSV |
| Dataset errores | `DS_ERRORES_CSV` | Rechazos y evidencias |
| Linked service Storage | `LS_ADLS_POC` | Acceso a Blob/ADLS |

No confundas linked services de ADF con credenciales del Job: el contenedor tendrá su propia identidad y permisos.

Rutas conocidas de entrada:

- Contenedor: `inbound`.
- Dataset ADF: carpeta `@concat('sap/', dataset().RutaLote)` y archivo `@dataset().ArchivoEntrada`.
- Caso original: `RutaLote=demo/lote001`, `ArchivoEntrada=entrada.txt` → blob `sap/demo/lote001/entrada.txt`.
- Caso propuesto con volumen: `RutaLote=demo/lote_real001`, `ArchivoEntrada=entrada_real_1000.txt` → blob `sap/demo/lote_real001/entrada_real_1000.txt`.

No agregues `inbound` al blob path ni dupliques `sap/`. Rechazá rutas ambiguas, traversal y combinaciones inválidas antes de descargar.

La salida pertenece al contenedor `out`. Separá las variantes, por ejemplo `pmc/containerapp/<entidad>/<lote>/` y `pmc/adf/<entidad>/<lote>/`. Estos prefijos son una propuesta de aislamiento, no rutas ya confirmadas. El CSV de enriquecimiento se recibe mediante ruta explícita del lote; no asumas un nombre/carpeta no suministrado.

### 4. Contrato de ejecución del Job

Implementá una CLI, por ejemplo `python -m etl_pmc run --manifest ...`, con modo local y modo Azure usando el mismo núcleo de negocio.

Preferí un manifiesto JSON inmutable por ejecución en Storage. ADF envía al Job solamente ubicación del manifiesto e identificador de correlación. También podés permitir argumentos locales equivalentes.

Contrato propuesto del manifiesto:

```json
{
  "schema_version": "1.0",
  "run_id": "poc-lote-real001-ca-001",
  "pipeline_run_id": "identificador-de-ejecucion-adf",
  "lote_id": "LOTE_REAL001",
  "profile": "poc_pmc",
  "storage_account_url": "https://<storage>.blob.core.windows.net",
  "input": {
    "container": "inbound",
    "blob": "sap/demo/lote_real001/entrada_real_1000.txt",
    "etag": null
  },
  "enrichment": {
    "container": "enrichment",
    "blob": "<ruta-exacta-del-extracto-del-lote>",
    "mode": "single_configuration"
  },
  "output": {
    "container": "out",
    "prefix": "pmc/containerapp/demo/lote_real001",
    "filename": "FAC0001.220926"
  },
  "audit": {"container": "audit", "prefix": "containerapp/demo/lote_real001"},
  "errors": {"container": "error", "prefix": "containerapp/demo/lote_real001"},
  "parameters": {
    "CodBancoPMC": "001",
    "CodigoServicioPMC": "0001",
    "TipoRegistroCabPMC": "0",
    "TipoRegistroDetPMC": "1",
    "TipoRegistroPiePMC": "9",
    "AplicarFiltro30Dias": false,
    "AplicarMaxDosCliente": false,
    "CuotaPMC": "01",
    "FechaEjecucionUTC": "2026-09-22T12:00:00Z"
  },
  "format": {
    "input_encoding": "utf-8",
    "output_encoding": "utf-8",
    "output_newline": "CRLF",
    "output_bom": false,
    "final_newline": true
  }
}
```

Es un contrato propuesto, no una configuración desplegada. Encoding, BOM, newline y terminador final deben verificarse contra la salida ADF; los valores del ejemplo son explícitos para reproducibilidad, no hechos confirmados. Los placeholders deben producir error de configuración si se intenta ejecutar con ellos.

Validá tipos, parámetros booleanos, anchos de códigos, existencia de perfil, destinos y combinaciones. `false` no debe interpretarse como verdadero por ser una cadena no vacía. Separá fecha de ejecución de fecha de cabecera.

Para repetir y comparar un lote, usá la misma fecha de ejecución, snapshot SQL, configuración y entradas. No uses la hora actual dentro de reglas de negocio de manera oculta.

### 5. Lectura e identificación de registros

ADF lee el TXT como una sola columna `Column_1`, sin separador de columnas, sin comillas ni escape y sin primera fila como encabezado. Incorpora `ArchivoOrigen`.

Nodos de referencia:

`SRCSAP` → `DerIdentificarRegistro` → `SplitTipoRegistro` con salidas Cabecera, Detalle, Pie y RegistroInvalido.

Implementá:

- Lectura incremental; conservar número de línea y archivo origen.
- Retirar únicamente el terminador de línea, no aplicar `strip()` al registro completo: los espacios finales forman parte del ancho fijo.
- Política explícita de BOM, líneas vacías, CRLF/LF y errores de decodificación.
- Layout declarativo con posiciones 1-based en la documentación y conversión centralizada a slices Python.
- Separación entre dato bruto, extracción de campo y conversión tipada.
- Identificadores como texto para conservar ceros iniciales.
- Distinción entre ancho en caracteres y en bytes. No afirmar que 280 caracteres UTF-8 siempre ocupan 280 bytes.

### 6. Parseo y validación del TXT real

Nodos de detalle: `DerParsearDetalleReal`, `DerConvertirDetalleReal`, `DerValidarDetalleReal`, `SplitValidacionDetalleReal`.

Campos conceptuales: `IdDeuda`, `ReferenciaCliente`, moneda, importe principal, entidad, `Concepto`, fechas e importes de vencimiento. Recuperá del export o layout las posiciones que no estén especificadas abajo.

Posiciones documentadas en la guía, con inicio 1-based y longitud; son base del perfil propuesto, a contrastar con los adjuntos:

| Registro/campo | Inicio | Longitud | Interpretación |
|---|---:|---:|---|
| Cabecera: fecha | 2 | 8 | `yyyyMMdd`; longitud de cabecera propuesta: 88 |
| Detalle: primer vencimiento | 144 | 8 | `yyyyMMdd` |
| Detalle: segundo vencimiento | 666 | 8 | `yyyyMMdd` |
| Detalle: importe segundo vencimiento | 674 | 13 | Decimal con separador documentado |
| Detalle: tercer vencimiento | 687 | 8 | `yyyyMMdd` |
| Detalle: importe tercer vencimiento | 695 | 13 | Decimal con separador documentado |
| Pie: cantidad declarada | 2 | 8 | Entero |
| Pie: importe total declarado | 10 | 15 | Decimal; confirmar semántica con el pie real |

No deduzcas la longitud total del detalle simplemente del último campo listado. No equipares los tipos de registro SAP con los de salida sin comprobarlo.

La propuesta valida identificación y moneda según las reglas actuales; tres fechas parseables; tres importes no nulos y no negativos. No adivines qué monedas o campos vacíos son válidos: extraé esa regla de ADF. Para importes usá `Decimal` o centavos enteros; nunca `float`. No aceptes separadores de miles ni formatos adicionales si ADF no los admite.

Documentá la semántica de redondeo/conversión, nulos y fechas inválidas. Los campos de importes propuestos usan reemplazo de coma por punto y precisión decimal de dos posiciones; cualquier redondeo o rechazo debe reproducirse mediante tests.

### 7. Controles globales antes de publicar

Nodos de referencia: `AggTotalesEntradaReal`, `DerParsearPieReal`, `AggControlPieReal`, `JoinControlTotalesReal`, `DerValidarTotalesReal`, `SelControlArchivoReal`, `JoinDetalleControlReal`, `SplitControlArchivoReal`.

No confundas agregados del archivo de entrada con agregados de los detalles que finalmente se publican.

La guía propone:

- Un pie por archivo.
- Cero importes nulos en la población usada para el control.
- Cantidad calculada igual a cantidad declarada.
- Diferencia absoluta de importe calculado/declarado menor o igual a `Decimal('0.01')`.
- Continuación solamente por `DetalleAutorizado`; errores por `ErrorControlArchivo`.

Inspeccioná exactamente desde qué rama nace la agregación ADF. No decidas por conveniencia si cuenta todos los detalles o sólo los válidos: eso modifica resultados ante rechazos.

La guía agrega `DerParsearCabeceraReal`, `AggCabeceraReal`, `DerValidarCabeceraReal`, `SelCabeceraReal`, `JoinDetalleCabeceraPMC`, `SplitCabeceraValidaPMC`: una cabecera, longitud correcta y fecha válida.

Registrá explícitamente pie/cabecera ausentes o duplicados. Si ADF los pierde por un inner join y queda vacío, documentá esa divergencia; no etiquetes la ausencia de filas como procesamiento exitoso automáticamente.

Ante fallo de controles globales, generá auditoría y no publiques salida aprobada. Para cero detalles válidos/archivo vacío: implementá una política explícita del perfil; no fabriques cabecera y pie de éxito sin evidencia de que corresponde.

### 8. Enriquecimiento: distinguir las dos variantes

ADF ya usa `PL_EXTRAER_SQL` para materializar una extracción SQL; se ha usado `intdb.vw_EnrichmentPoc`. El contenedor consume el CSV generado, sin ejecutar una nueva consulta.

Implementá modos claramente separados:

**Modo `record_join`:** para reproducir el flujo que enriquece por registro. Obtener clave, columnas, filtros, cardinalidad y tratamiento de no encontrados desde ADF. No asumir que `IdDeuda` es siempre la clave correcta. Registrar errores de enriquecimiento como la rama original.

**Modo `single_configuration`:** propuesto por la nueva guía porque los IdDeuda del archivo real no coinciden con las claves `DEU...` del extracto simulado anterior. Consume como máximo una fila de configuración, con columnas `CodEntidad`, `DescripcionEntidad`, `CodBancoConfig`, `CodigoServicioConfig`, y la incorpora sin multiplicar detalles.

En este segundo modo, resolver `CodBancoFinal` y `CodigoServicioFinal` desde el CSV si no son nulos; usar parámetros como respaldo conforme a la guía. Diferenciá archivo faltante, CSV vacío, columna ausente, nulo, cadena vacía y múltiples filas. No conviertas todos esos problemas en un fallback silencioso. Definí la política explícita; varias filas deben provocar fallo por cardinalidad, no un producto cartesiano.

No copies un `TOP (1)` dentro del contenedor ni selecciones arbitrariamente una entidad. La selección del snapshot pertenece a la extracción ADF. Registrá hash/ETag de ese snapshot para la comparación.

### 9. Reglas de negocio propuestas para Pago Mis Cuentas

Implementalas en `poc_pmc` y en `adf_actual` solamente si están confirmadas:

- `ReferenciaCliente`: identificador de cliente para agrupación (supuesto POC).
- `IdDeuda`: recibo/factura (supuesto POC).
- `Concepto`: aproximación del ramo (supuesto POC).
- Cuota de ticket `01`: valor configurable de POC, no dato productivo validado.
- Importe principal máximo `999999999.99`.
- Con `AplicarFiltro30Dias=true`, primer vencimiento ≤ fecha de cabecera + 30 días. La expresión de la guía no impone límite inferior: no agregar uno silenciosamente.
- Con `AplicarMaxDosCliente=true`, conservar rango ≤ 2 por ReferenciaCliente, ordenando primer vencimiento e IdDeuda ascendentes.
- Ambos filtros opcionales comienzan en `false`.

La guía calcula primero el rango por cliente y luego aplica conjuntamente filtros de importe, fecha y rango. No cambiar a «filtrar primero y tomar los dos siguientes» porque daría otros recibos. Si hay empate completo, proponé número de línea como desempate estable y registrá que ADF necesita el mismo criterio para paridad determinista.

Motivos propuestos y prioridad: `IMPORTE_SUPERA_MAXIMO`, `VENCIMIENTO_SUPERA_30_DIAS`, `MAXIMO_DOS_RECIBOS_CLIENTE`.

### 10. Layout de salida del perfil propuesto `poc_pmc`

No confundir este layout POC con certificación bancaria productiva. Confirmá contra ADF antes de llamarlo `adf_actual`.

**Detalle: 280 posiciones, sin terminador de línea.**

| Posiciones | Largo | Campo y regla propuesta |
|---|---:|---|
| 1 | 1 | TipoRegistroDetPMC, inicial `1` |
| 2–20 | 19 | ReferenciaCliente: trim, primeros 19, espacios a derecha |
| 21–40 | 20 | IdDeuda: trim, completar ceros a izquierda |
| 41 | 1 | Código moneda de salida `0` en este perfil |
| 42–49 | 8 | Primer vencimiento `yyyyMMdd` |
| 50–60 | 11 | Primer importe en centavos, ceros a izquierda |
| 61–68 | 8 | Segundo vencimiento |
| 69–79 | 11 | Segundo importe en centavos |
| 80–87 | 8 | Tercer vencimiento |
| 88–98 | 11 | Tercer importe en centavos |
| 99–117 | 19 | Ceros |
| 118–136 | 19 | Referencia anterior = ReferenciaCliente, mismo tratamiento |
| 137–176 | 40 | Mensaje ticket |
| 177–191 | 15 | Mensaje pantalla |
| 192–251 | 60 | Espacios para código de barras |
| 252–280 | 29 | Ceros |

Mensajes de la guía:

```text
ramo = upper(trim(Concepto))
ticket_base = ramo[0:4] + ' Pza' + trim(ReferenciaCliente)
              + ' Rec' + trim(IdDeuda) + ' Cta' + CuotaPMC
ticket = primeros 40 caracteres de ticket_base, espacios a derecha hasta 40
pantalla_base = ramo[0:5] + ' Rec ' + trim(IdDeuda)
pantalla = primeros 15 caracteres de pantalla_base, espacios a derecha hasta 15
```

Importes: convertir a centavos con aritmética exacta y semántica de redondeo verificada. Controlar desbordes de los tres importes y del identificador. Python `zfill`/`rjust` no necesariamente se comportan igual que `lpad` de ADF cuando el texto supera el ancho: agregá tests específicos, no lo presupongas. Cualquier protección más estricta que ADF se documenta como diferencia, no como equivalencia comprobada.

**Cabecera POC: 280 posiciones.**

| Posiciones | Campo |
|---|---|
| 1 | TipoRegistroCabPMC, inicial `0` |
| 2–4 | CodBancoFinal, tres caracteres |
| 5–8 | CodigoServicioFinal, cuatro caracteres |
| 9–16 | Fecha de la cabecera de entrada `yyyyMMdd` |
| 17 | Literal `1` |
| 18–280 | 263 ceros |

**Pie POC: 280 posiciones.**

| Posiciones | Campo |
|---|---|
| 1 | TipoRegistroPiePMC, inicial `9` |
| 2–4 | CodBancoFinal |
| 5–8 | CodigoServicioFinal |
| 9–16 | Fecha de cabecera |
| 17–23 | Cantidad de detalles efectivamente emitidos, siete dígitos |
| 24–30 | Siete ceros |
| 31–46 | Suma del primer importe de detalles emitidos, en centavos, 16 dígitos |
| 47–280 | 234 ceros |

El documento de negocio tiene una ambigüedad de pie 346/348 que la guía posterga. No inventes ese formato ni lo mezcles con el perfil POC de 280.

Orden de archivo: cabecera única, detalles ordenados por ReferenciaCliente / primer vencimiento / IdDeuda, pie único. Sin columnas auxiliares, encabezado CSV, delimitadores, comillas ni truncado final de espacios.

Nombre propuesto: `FAC` + CodigoServicioPMC + `.` + fecha de ejecución UTC en `ddMMyy`. La guía usa el parámetro de servicio para el nombre y puede usar la configuración SQL para el contenido. Detectá y documentá si difieren; no cambies una de las dos fuentes silenciosamente. Para comparación, aceptá nombre explícito enviado por ADF.

### 11. Arquitectura de código y recursos

Usá una versión soportada de Python compatible con las dependencias; fijá versiones reproducibles. Consultá documentación oficial vigente para SDK, autenticación, comandos CLI/API y despliegue.

Separá, como mínimo:

- CLI y configuración/manifiesto.
- Modelos tipados de entrada, detalle, control y resultado.
- Parser de ancho fijo y layouts versionados.
- Validaciones de registro y de archivo.
- Enriquecimiento y controles de cardinalidad.
- Reglas de negocio.
- Formateo de salida.
- Adaptadores de archivos locales y Azure Storage.
- Auditoría, errores, publicación e idempotencia.

El núcleo debe poder probarse sin Azure. No repliques cada nodo visual como un microservicio; conservá semántica y trazabilidad con los nodos.

Leé la entrada por streaming y usá temporales en disco con límites configurables. Para orden global y ranking que no entren en RAM, usá una solución acotada como SQLite local o external sort. Si usás SQLite, almacená centavos como enteros con controles de rango, no `REAL`, y preservá tipos/orden de IDs. No cargues automáticamente un archivo de 500 MB más todas sus representaciones en memoria.

Una implementación en dos pasadas es aceptable: validar/agregar y almacenar detalles temporales; luego enriquecer/filtrar/ordenar y emitir. No publicar salida antes de conocer controles globales. Medí disco temporal máximo y memoria, además del tiempo.

### 12. Seguridad y acceso a Azure

Usá identidad administrada del Job para Storage; desarrollo local con credenciales de desarrollador mediante el mecanismo del SDK. Sin secretos en código, imagen, argumentos, manifiestos o logs.

Documentá por separado permisos de lectura de entrada/enriquecimiento, escritura de stage/out/error/audit e inicio/consulta del Job desde la identidad ADF. No pidas Owner/Contributor de toda la suscripción. Para descarga privada de imagen desde ACR, documentá la identidad y permisos aplicables a la configuración concreta del registro.

No elimines archivos de inbound desde el contenedor: ADF mantiene la responsabilidad de archivar/retirar solamente después de confirmar resultado válido. No actives acceso anónimo ni abras firewalls como solución automática.

### 13. Publicación segura, repetición y fallos

Escribí primero a un destino temporal por run. Tras validación, publicá el resultado con una estrategia explícita compatible con el API de Storage elegido. No asumas que copy+delete de Blob es un rename atómico.

Usá un manifiesto de resultado/commit que marque la salida como consumible sólo al finalizar su escritura y validación. Si ADF copia o archiva, debe comprobar ese estado. Si se usa copy asíncrono, esperar su éxito antes del commit.

Idempotencia basada en identidad/hash de entrada, hash del snapshot, perfil, versión de layout/configuración y parámetros relevantes; no sólo en nombre del TXT ni sólo en run_id. Considerá la fecha/nombre de salida cuando modifica bytes o destino.

Prevení escrituras concurrentes sobre el mismo lote/destino mediante mecanismo condicional o lease con renovación/liberación. Una segunda ejecución no debe sobrescribir salida válida o anunciar éxito mientras la primera sigue procesando. Documentá qué ocurre tras caída entre upload y commit. No permitas sobrescritura implícita: reprocesar debe ser explícito y conservar trazabilidad.

Resultado JSON mínimo: estado, run_id, pipeline_run_id, lote, versión de código y perfil, hashes/ETags, archivos consumidos/producidos, cantidades leídas/válidas/rechazadas/excluidas/emitidas, totales de entrada declarados/calculados, total de salida, resultado de controles, duraciones por etapa, warnings y rutas de errores.

Definí estados como `SUCCEEDED`, `SUCCEEDED_WITH_REJECTIONS`, `REJECTED`, `FAILED`, `ALREADY_PROCESSED`. Son estados de aplicación, no nombres inventados del API de Azure. Documentá su mapeo a códigos de salida del proceso y a decisiones de ADF. Éxito técnico del contenedor no debe ocultar rechazo global del lote.

No depender de que Azure entregue a ADF un código de salida personalizado: la integración debe leer estado de ejecución y resultado de aplicación. Fallos irrecuperables usan código no cero; reintentos deben ser seguros y acotados.

### 14. Errores y observabilidad

Conservar categorías equivalentes: entrada, control de archivo/cabecera, enriquecimiento, exclusión de negocio y formato de salida. Los CSV deben tener esquema explícito y escapado correcto; no concatenarlos manualmente.

Campos sugeridos: run_id, archivo, número de línea, categoría, código, campo, motivo. Si se necesita registro bruto o valores sensibles, escribirlos sólo en almacenamiento de errores autorizado, no en stdout.

Logs estructurados JSON a stdout/stderr con correlación y duración por etapa; sin una línea de log por registro válido. Registrar versión, configuración no sensible, conteos, descargas, parseo, join, orden, formato y publicación. Separar duración de arranque del Job del tiempo interno del ETL.

### 15. Integración con ADF y despliegue

Entregar Dockerfile reproducible, `.dockerignore`, ejecución local, build/push a ACR y definición del Container Apps Job. Proceso no root, dependencias mínimas, sin servicios web innecesarios.

Configuración inicial propuesta: una réplica y paralelismo uno; CPU, memoria, timeout y reintentos configurables. Justificar recursos con mediciones; no vender el mismo ajuste como suficiente para 500 MB sin pruebas.

Entregar comandos de Azure CLI o Bicep para recursos propios del Job, reutilizando Storage/ADF/SQL existentes. Usar placeholders explícitos para suscripción, resource group, ACR, environment e identidades. No crear otra base SQL ni duplicar infraestructura innecesariamente.

Entregar `docs/integracion_adf.md` con pasos y payloads verificados:

1. Clonar un pipeline de prueba o añadir selección explícita de motor sin romper el recorrido ADF.
2. Conservar comprobación y `PL_EXTRAER_SQL`.
3. Crear/referenciar manifiesto inmutable después de la extracción.
4. Iniciar la ejecución del Job con identidad ADF mediante una actividad apropiada.
5. Conservar el identificador exacto de esa ejecución.
6. Esperar y consultar esa ejecución hasta estado terminal, con espera y timeout acotados.
7. Leer el manifiesto de resultado de aplicación y validar lote/estado/salida.
8. Archivar entrada sólo después de éxito de aplicación y de publicación verificada.
9. En fallos conservar evidencia y seguir la rama de error.

Verificá en documentación oficial la versión API, URLs, payloads y estados reales. Los parámetros ADF no se transfieren solos al Job. Si start permite sobrescribir el template de ejecución, documentá qué campos completos deben enviarse para no perder imagen/recursos/configuración necesaria. Una respuesta de inicio aceptado NO significa que el ETL terminó bien.

Si no podés verificar una parte de Azure, marcala pendiente de validación, no inventes comandos ni un pipeline JSON supuestamente importable.

Para el benchmark: extraer SQL una vez, conservar la entrada, ejecutar ambos motores contra el mismo snapshot en destinos separados y archivar sólo al terminar la comparación. No ejecutar dos consumidores que retiren el mismo inbound compitiendo.

### 16. Pruebas obligatorias y herramienta de comparación

Entregar tests automatizados sin Azure, más tests de integración opcionales:

1. Lote válido mínimo y lote con ≥ 1.000 detalles.
2. Longitud inválida, tipo desconocido, línea vacía y BOM.
3. Cabecera/pie ausentes y duplicados; fechas inválidas.
4. Cantidad y total erróneos, límites de tolerancia 0.00/0.01/0.02.
5. Importes nulos, negativos, ceros, desbordes y decimales problemáticos.
6. Filtro 30 días apagado/encendido: justo límite, día posterior y fecha anterior a cabecera.
7. Más de dos recibos por cliente y efecto del orden de ranking/filtros.
8. Join sin coincidencia, duplicados, configuración vacía/múltiple y fallback permitido.
9. Identificadores con ceros iniciales, campos al ancho exacto y excedidos, texto con acentos.
10. Cero detalles emitidos y lote globalmente rechazado sin publicación válida.
11. Orden, espacios, padding, 280 posiciones, BOM/newline/terminador final.
12. Reejecución idéntica, concurrencia, fallo antes de commit y recuperación.

Entregar `compare-adf` que compare resultado ADF y contenedor del mismo lote:

- SHA-256 y bytes completos primero.
- Reporte de primera diferencia con línea, posición y campo según layout.
- Conteos, totales, orden, cabecera/pie y rechazos/exclusiones.
- Diagnóstico separado para encoding, espacios y saltos de línea.
- No normalizar ni reordenar archivos para declarar igualdad exacta. Una comparación semántica adicional puede existir, claramente identificada.
- Orden de filas de CSV de errores puede ser no determinista en ADF: comparar multiconjuntos con multiplicidad cuando corresponda, conservando aparte diferencias físicas.
- Modo de reporte redactado para no exponer datos personales completos.

Crear generador sintético con semilla reproducible, cantidad configurable, IDs compatibles con fixtures de enriquecimiento y pie calculado después de generar detalles. Los datos deben ser ficticios. Añadir casos malos controlados.

Benchmark con mismo hardware configurado, número de corridas y lote; separar cold start, descarga, procesamiento, upload y duración total. No inventar costos ni mediciones si no se ejecutó en Azure.

### 17. Fuera de alcance de esta entrega

- FTP/SFTP productivo, ZIP, correos y destinatarios.
- XSD productivo no entregado.
- Regla de antigüedad de diez meses sin campo/fecha definidos.
- Layout de pie productivo ambiguo 346/348.
- Códigos reales de banco/servicio no confirmados.
- Cambios de reglas para «mejorar» la salida sin registrar divergencia.
- Despliegue automático o cambios no autorizados a Azure.

Dejá puntos de extensión simples, no stubs que aparenten implementar estas funciones.

### 18. Entregables y definición de terminado

Entregar en el repositorio:

- Código Python modular ejecutable, dependencias fijadas y CLI.
- Layouts/configuración versionados y esquema del manifiesto.
- Dockerfile, `.dockerignore`, ejemplo de variables sin secretos.
- Tests, fixtures sintéticos y generador.
- Comparador ADF/contenedor y comandos de benchmark.
- `README.md`: instalación, ejecución local, Docker, pruebas, Azure y troubleshooting.
- `docs/matriz_equivalencia.md`: reglas confirmadas/propuestas, divergencias y tests.
- `docs/integracion_adf.md`: invocación, espera, resultado y archivo histórico.
- `docs/supuestos_y_pendientes.md` y archivos de despliegue.
- Ejemplos de manifiesto de entrada y resultado.

Orden de trabajo: inspeccionar adjuntos → matriz/layout → núcleo y tests → modo local → adaptador Storage → Docker → integración/despliegue → comparación.

Al terminar, informá qué implementaste, qué ejecutaste realmente y sus resultados, qué queda sin información, comandos exactos para probar y siguientes pasos para desplegar. No digas «equivalente a ADF» hasta haber corrido ambos sobre el mismo lote y verificado la comparación. Si solamente validaste fixtures, decilo explícitamente.

Prioridad: fidelidad de datos, control de errores y reproducibilidad; después optimización. Empezá a implementar, no me devuelvas únicamente este plan reformulado.

## FIN DEL PROMPT
