# Supuestos y pendientes

Este documento junta, en un solo lugar, las decisiones de POC que no están confirmadas contra ADF real y las limitaciones conocidas de esta implementación. El detalle campo por campo con su origen y estado (`CONFIRMADA_ADF` / `PROPUESTA_GUIA` / `SUPUESTO_POC` / `POSTERGADA`) vive en `docs/matriz_equivalencia.md`; acá se resume qué falta y qué se decidió sin poder verificarlo.

## No hay export ADF disponible

Los JSON de export de ADF que se habían adjunto al inicio de este trabajo fueron retirados por el dueño del proceso: el flujo ADF todavía no está terminado y no se quería que un snapshot parcial confundiera la implementación. Como consecuencia:

- El perfil `adf_actual` está declarado en el código (`etl_pmc.config.layouts`) pero **sin ningún layout cargable** — seleccionarlo produce un error de configuración explícito, no un fallback silencioso a `poc_pmc`.
- Todo lo implementado corre bajo el perfil `poc_pmc`, siguiendo el fallback que el propio prompt indica para este caso (sección 2): avanzar con las especificaciones disponibles y dejar la equivalencia como `NO_VERIFICADA`.
- Las posiciones del layout de entrada que el prompt no documenta explícitamente (`referencia_cliente`, `id_deuda`, `moneda`, `importe_principal`, `nombre_entidad`, `concepto`) se infirieron y se **verificaron empíricamente** contra el único archivo real disponible (`entrada_real_1000.txt`): los patrones de los 1000 detalles cumplen exactamente, y la suma de los 1000 importes principales coincide centavo a centavo con el total declarado en el pie del archivo. Es una verificación fuerte, pero no reemplaza un export ADF.

## Decisiones de POC sin confirmación ADF

- **Población del control de totales** (`docs/matriz_equivalencia.md` sección 6): se cuentan y suman **todos** los detalles leídos (tipo/longitud correcta), no solo los individualmente válidos. Si ADF real cuenta distinto, esto es una divergencia a registrar, no a corregir en silencio.
- **Orden entre vencimientos**: no se exige que los tres vencimientos estén en orden cronológico ascendente como condición de rechazo (el prompt no lo pide explícitamente). Si un export ADF real confirma esa regla, hay que agregarla y registrar el cambio.
- **Cabecera ausente/duplicada/con fecha inválida**: rechaza el archivo completo (`REJECTED`), sin fabricar cabecera de éxito. No hay confirmación de que ADF haga lo mismo (no hay nodos de cabecera confirmados).
- **Cero detalles emitidos tras las reglas de negocio**: se trata como `REJECTED` (motivo `CERO_DETALLES_EMITIDOS`), no como éxito trivial con archivo vacío.
- **record_join**: la clave (`id_deuda`, decisión de POC confirmada por el usuario — "no es info productiva, podemos usar la que queramos") y las columnas a incorporar son configuración del manifiesto. El motor construye el índice, hace el lookup por registro y **reporta cantidades de coincidencia/no-coincidencia** (`cantidad_enriquecimiento_coincidente/sin_coincidencia` en el resultado, ver benchmark de 250k filas en `docs/matriz_equivalencia.md`), pero **no aplica ninguna columna de `record_join` a la salida**: el layout de 280 posiciones no define ningún campo que provenga de ahí — solo usa `CodBancoFinal`/`CodigoServicioFinal`, que vienen de `single_configuration`.

### Reglas explícitamente INVENTADAS (a pedido directo del usuario, sin ninguna base documental)

A diferencia de las decisiones de POC de arriba (que son inferencias razonadas ante información faltante), estas dos son fabricaciones deliberadas, pedidas explícitamente para poder simular el proceso completo y medir tiempos, no para acercarse a un comportamiento real:

- **Validación de schema XSD sintética** (`etl_pmc.validation.schema_sintetico`, flag opcional `format.simular_validacion_schema`): schema XSD inventado, no es el productivo (que no existe en este repositorio). Ver benchmark en `docs/matriz_equivalencia.md` sección 8.1 — el costo medido (~16µs/registro) no alcanza para explicar una diferencia de horas contra el proceso IIB.
- **Filtro de antigüedad >10 meses** (`AplicarFiltroAntiguedad`, opcional, default `false`): usa una posición de campo `fecha_emision_deuda_sintetica` totalmente inventada (detalle, posición 152, sin ninguna base). Verificado contra `entrada_real_1000.txt`: rechaza los 1000 detalles (la posición inventada sí contiene algo con forma de fecha en el archivo real, pero no es una fecha de emisión real). Ver `docs/matriz_equivalencia.md` sección 9.1.

## Limitaciones de escala conocidas

- **Ranking de negocio en memoria**: la segunda pasada (`etl_pmc.pipeline.ejecutar`) materializa en memoria la lista de detalles autorizados (los que pasaron validación individual y control de archivo) para calcular el rango por cliente (filtro de máximo dos recibos). Es un candidato a reemplazar por un cálculo de rango en streaming sobre el mismo orden SQL ya usado (`referencia_cliente, primer_vencimiento, id_deuda`), sin necesidad de rediseñar el resto del pipeline. Los números medidos abajo muestran que esto empieza a pesar antes de los 630.000 registros.
- **CSV de enriquecimiento cargado completo en memoria**: razonable para `single_configuration` (una fila) y para tablas de configuración chicas; si `record_join` se termina de cablear a futuro con un CSV grande, esto también debería revisarse.

### Benchmark medido (mismo hardware, un solo proceso, modo local sin Azure)

Archivos generados con `docs/generar_entrada_real_poc.py`, usando `entrada_real_1000.txt` como plantilla (datos ficticios, IDs/importes/vencimientos regenerados; `ReferenciaCliente`/`Concepto`/`Entidad` reciclados de las 1000 filas reales de la plantilla). Corridos con `etl-pmc run` end-to-end (lectura, validación, control de totales, reglas de negocio, formateo, escritura), un único proceso, sin paralelismo:

| Detalles | Tamaño entrada | `lectura_y_validacion` | `reglas_y_formato` | Total interno | Tiempo de proceso completo |
|---:|---:|---:|---:|---:|---:|
| 1.000 | 715 KB | 0.031 s | 0.032 s | 0.063 s | — |
| 100.000 | 69 MB | 3.34 s | 3.58 s | 6.92 s | 7.40 s |
| 660.000 | 451 MB | 45.75 s | 44.11 s | 89.86 s | 91.20 s |

Los tres corrieron `SUCCEEDED` con totales de control exactos. La escala **no es lineal**: de 100.000 a 660.000 detalles (6,6x más datos) el tiempo interno subió ~13x, no ~6,6x. Esto es consistente con la limitación de arriba (la segunda pasada materializa objetos Python para el ranking en vez de calcularlo en streaming) empezando a doler a esta escala, y posiblemente con presión de garbage collector por la cantidad de objetos vivos simultáneamente. No se perfiló en detalle (no se midió memoria pico ni se aisló cuánto del tiempo es GC vs. trabajo real) — sería el primer paso antes de optimizar.

No se corrió contra Azure real ni contra Container Apps Jobs: estos números son de esta máquina de desarrollo, en un solo proceso Python, sin el overhead/latencia de descarga de blob ni el cold start del contenedor. No usar estos números para dimensionar recursos de producción sin repetir la medición en el entorno real.

## Fuera de alcance (heredado del prompt, sección 17)

FTP/SFTP productivo, compresión ZIP, notificaciones por correo, XSD productivo, regla de antigüedad de diez meses, layout de pie productivo ambiguo 346/348, códigos reales de banco/servicio no confirmados, despliegue automático a Azure.

## Qué se ejecutó realmente para validar esta entrega

- Suite completa de tests unitarios e integración (`pytest`, ver comando en `README.md`): **139 tests, todos verdes**, incluyendo:
  - Parseo y validación de layout verificados contra `entrada_real_1000.txt` con el control cruzado de totales descrito arriba.
  - Corrida end-to-end del pipeline completo (modo local, sin Azure) contra `entrada_real_1000.txt`, con un CSV de enriquecimiento **sintético** (no hay uno real disponible): `SUCCEEDED`, 1000 detalles leídos y emitidos, totales de entrada y salida coincidentes.
  - Corrida repetida del mismo lote: segunda ejecución detectada como `ALREADY_PROCESSED` (idempotencia).
  - Corridas contra lotes sintéticos generados con `generate-fixture`, con casos malos inyectados deliberadamente (moneda inválida, identificadores con letras, referencia corta, fecha de calendario inválida, longitud incorrecta, importe corrupto), verificando tanto `SUCCEEDED_WITH_REJECTIONS` (rechazos individuales que no bloquean el archivo) como `REJECTED` a nivel de archivo completo (cuando hay importes nulos en la población de control).
  - CLI instalada (`etl-pmc run ...`) ejecutada de punta a punta contra `entrada_real_1000.txt` fuera de pytest, con el resultado real guardado en `examples/resultado.example.json`.
  - `compare-adf` probado contra copias idénticas y modificadas de esa misma salida (no contra una salida ADF real, que no existe todavía para este lote).
- **No se corrió nada contra Azure real** (Storage, Container Apps Jobs, ACR): no se desplegó ningún recurso, conforme a lo pedido explícitamente. El adaptador de Azure Blob Storage (`etl_pmc.storage.azure_blob`) está implementado con streaming real y publicación por copia+commit, pero solo se verificó por lectura de código, no con una cuenta de Storage real.
- **No se certificó equivalencia con ADF**: no hay una salida ADF real de `entrada_real_1000.txt` para comparar. Todo lo que este documento y la matriz llaman "verificado" se refiere a consistencia interna del motor contra datos reales de entrada, no a paridad con el Data Flow.
