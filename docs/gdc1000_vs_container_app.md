# GDC-1000 vs Container App

Checklist que compara, paso a paso, lo que documenta **GDC-1000** (Envío de Deuda a Cobrar — análisis de negocio del proceso IIB actual) contra lo que implementa el motor `etl_pmc` de este repositorio (perfil `poc_pmc`). No certifica equivalencia con ADF ni con IIB — es un mapa de cobertura, no una certificación.

Versión HTML interactiva: [artifact](https://claude.ai/artifact/Uxn1DYTz1wRqNMXzJbBY1w)

## Estado de cobertura — 26 pasos del documento

| Estado | Cantidad |
|---|---:|
| ✅ Implementado | 14 |
| ⚠️ Divergencia documentada | 3 |
| 🔵 Simulado (inventado a pedido explícito) | 2 |
| ↪ Adaptado | 1 |
| ⬜ Fuera de alcance | 6 |

## A · Detectar y leer mensaje (GDC-1000 §A)

| Paso | GDC-1000 | Estado | Nota |
|---|---|---|---|
| Dispatcher deposita el TXT según `Path_Entity_Out` | SAP genera el archivo y el Dispatcher lo deja en la carpeta de la Tabla Intermedia. | ⬜ Fuera de alcance | Responsabilidad de ADF (detección de archivo), no del Job. |
| Nombre de archivo AAAAMMDD+id+VVV+Y | El Dispatcher distribuye el mismo archivo a Pago Mis Cuentas y a Link Pagos. | ⬜ Fuera de alcance | El Job recibe la ruta del blob ya resuelta en el manifiesto. |
| ESB escucha la carpeta FTP y dispara | Pull del ESB cada 15 minutos, ventana 7x24. | ⬜ Fuera de alcance | El polling queda en ADF; el Job se invoca puntualmente, no re-implementa un scheduler. |
| Copia para histórico de transacciones | Se guarda copia antes de procesar. | ⬜ Fuera de alcance | Archivado de `inbound` es responsabilidad de ADF; el Job nunca borra ni mueve el original. |
| 3 tipos de registro: cabecera, detalle, pie | Formato de ancho fijo definido en "Formato Salida SAP" (v3). | ✅ Implementado | `parsing/identify.py` — verificado empíricamente contra `entrada_real_1000.txt`. |

## B · Validaciones (GDC-1000 §B)

| Validación | GDC-1000 | Estado | Nota |
|---|---|---|---|
| Cantidad de caracteres por tipo de registro | Cada registro debe tener el largo esperado según su tipo. | ✅ Implementado | `parsing/identify.py` |
| Longitud de campo tras TRIM no supera el destino | Si el valor de SAP (post-TRIM) excede el campo destino, es error. | ✅ Implementado | `formatting/output.py::_texto_o_desborda` — antes truncaba en silencio, corregido. |
| Control de registros (tipo esperado) | El indicador "Tipo de registro" debe coincidir (ej. detalle = "2"). | ✅ Implementado | Mismo módulo que la fila anterior. |
| Control de totales (cantidad + suma de importes vs. pie) | Debe coincidir con lo informado en el registro de pie. | ⚠️ Divergencia | `control/totales.py` — implementado; población = *todos* los detalles leídos, no solo los válidos (decisión de POC, sin ADF real para confirmar). |
| Control de formatos (XSD) | Todos los datos deben cumplir el XSD de la integración. | 🔵 Simulado | `validation/schema_sintetico.py` — schema **inventado** (no hay XSD productivo). Usado solo para medir costo por registro, ver benchmark. |

## C · Aplicar formato para la entidad (GDC-1000 §C)

| Regla | GDC-1000 | Estado | Nota |
|---|---|---|---|
| 1 cabecera + n detalle + 1 pie | Se generan 2 registros fijos + n de detalle. | ✅ Implementado | `pipeline.py` |
| TRIM antes de mapear valores de la Tabla Intermedia | Se aplica TRIM a los valores antes del mapeo. | ✅ Implementado | `enrichment/single_configuration.py` |
| Padding CHAR→espacios der. / NUM→ceros izq. | Regla de relleno por tipo de dato. | ✅ Implementado | `formatting/output.py` |
| Filtro: importe > $999.999.999,99 | Se excluyen detalles que superen ese tope. | ✅ Implementado | `rules/pmc.py` |
| Filtro: vencimiento > 30 días desde fecha de archivo | Parte del "Filtro 1" (antigüedad o vencimiento). | ✅ Implementado | Flag `AplicarFiltro30Dias`, default apagado. |
| Filtro: antigüedad > 10 meses | Otra mitad del "Filtro 1". | 🔵 Simulado | Sin campo real: se inventó una posición (`fecha_emision_deuda_sintetica`, pos. 152) a pedido explícito. Flag opcional `AplicarFiltroAntiguedad`, apagado por default. Contra el archivo real rechaza los 1.000 detalles — la posición inventada "parece" fecha pero no lo es. |
| Máximo 2 recibos pendientes por cliente | Alcance funcional del proceso completo (no aparece como filtro explícito en §C). | ⚠️ Divergencia | Implementado como filtro (`AplicarMaxDosCliente`) — abierto si en producción esto ya lo garantiza SAP en origen. |
| Layout cabecera — 280 bytes | Cabecera de 280 bytes, campos 1 a 6. | ✅ Implementado | `formatting/output.py::formatear_cabecera` |
| Layout detalle — 280 bytes | Detalle de 280 bytes, campos 1 a 16. | ✅ Implementado | `formatting/output.py::formatear_detalle` |
| Layout pie — 346 bytes | Pie de 346 bytes, con un campo final en pos. 347–348 (inconsistencia 346 vs 348 en el propio documento). | ⚠️ Diverge a propósito | Perfil POC usa pie de **280** bytes. Ambigüedad 346/348 documentada, no resuelta ni inventada (instrucción explícita del prompt original). |
| Mensaje Ticket (fórmula + vocales sin acento) | Ramo + " Pza" + Póliza + " Rec" + Recibo + " Cta" + Cuota; mapear vocales sin acento. | ✅ Implementado | `formatting/output.py::construir_mensaje_ticket` |
| Mensaje Pantalla | Ramo (5) + " Rec " + Nro Recibo. | ✅ Implementado | `formatting/output.py::construir_mensaje_pantalla` |

## D · Generar archivo & E · Notificar (GDC-1000 §D–E)

| Paso | GDC-1000 | Estado | Nota |
|---|---|---|---|
| Nombre de salida `FACXXXX.ddmmaa` | XXXX = CodigoServicio, ddmmaa = fecha de generación. | ✅ Implementado | Coincide exacto con el nombre de ejemplo del prompt. |
| Comprimir (zip) | El archivo se comprime antes de publicarse. | ⬜ Fuera de alcance | Pospuesto explícitamente (prompt §17). |
| Guardar en `PAGOMISCUENTAS/OUT` (FTP) | Carpeta fija del FTP de la entidad. | ↪ Adaptado | Container/prefijo configurables por manifiesto (Blob Storage), no FTP. |
| Notificar por email (éxito y error) | Según especificación "Tabla Emails". | ⬜ Fuera de alcance | Pospuesto explícitamente (prompt §17) — sin Tabla Emails disponible. |

## Benchmark: 1.000 vs 660.000 registros

Misma corrida (modo local, un solo proceso, sin Azure), con la validación de schema sintética activada en ambas — para medir su costo real, no solo estimarlo.

| Fase | 1.000 registros | 660.000 registros |
|---|---:|---:|
| Lectura + validación | 0,047 s | 33,72 s |
| Schema sintético | 0,015 s | 10,59 s |
| Enriquecimiento (record_join, 250k filas) | — | 1,08 s |
| Reglas + formato | 0,031 s | 24,70 s |
| **Total** | **0,285 s** | **62,07 s** |
| Entrada | 715 KB | 452 MB |
| Resultado | SUCCEEDED | SUCCEEDED |

**Hallazgo clave**: 660 veces más datos (1.000→660.000) tardó ~218x más tiempo (0,29s→62s), no 660x — la segunda pasada del motor todavía materializa los detalles autorizados en memoria para el ranking de negocio en vez de calcularlo en streaming (límite conocido, ver `docs/supuestos_y_pendientes.md`). Aun así, sigue en el orden de **un minuto**, no de horas: la validación de schema (aunque inventada) agregó solo **~16 microsegundos por registro** — a escala completa eso es ~10s, lejos de explicar una diferencia de 9 horas contra el proceso IIB actual.

## Fuentes

- `GDC-1000 Pago Mis Cuentas — Envío de Deuda a Cobrar` (documento de análisis)
- `Prompt_Container_Apps_ETL_Equivalente_ADF_Poc.md`
- Código y benchmarks de este repositorio (`etl_pmc`, perfil `poc_pmc`)
- Detalle completo: `docs/matriz_equivalencia.md`, `docs/supuestos_y_pendientes.md`
