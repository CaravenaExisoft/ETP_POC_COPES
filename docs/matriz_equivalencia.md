# Matriz de equivalencia — ADF vs Container App ETL (PMC)

Estado: el motor descripto en este documento **está implementado y probado** (139 tests, ver `docs/supuestos_y_pendientes.md` para el detalle de qué se ejecutó realmente), incluyendo una corrida de punta a punta contra `entrada_real_1000.txt`. No se declara "equivalencia" de nada que no esté verificado contra una salida ADF real del mismo lote mediante `compare-adf` — eso sigue sin poder hacerse porque no existe todavía esa salida ADF real. Este documento se sigue actualizando a medida que cambie la disponibilidad de fuentes ADF.

## 0. Inventario de fuentes y decisión sobre el export de ADF

| Fuente | Estado | Rol |
|---|---|---|
| `Prompt_Container_Apps_ETL_Equivalente_ADF_Poc.md` | Disponible (`docs/`) | Especificación normativa de este trabajo. Fuente principal de posiciones, reglas y contrato de manifiesto |
| `Guia_Implementacion_POC_ADF_Pago_Mis_Cuentas.docx` | Disponible (raíz del repo) | Cambios **propuestos** sobre el flujo ADF, no confirma que estén desplegados |
| `entrada_real_1000.txt` | Disponible (`docs/`) | Archivo real de muestra (1002 líneas: 1 cabecera + 1000 detalles + 1 pie). Única fuente de datos real disponible; usado para verificar empíricamente las posiciones del layout (ver §2–§5) |
| Export JSON de ADF (pipeline, Data Flow, dataset) | **Retirado por el dueño del proceso** | El flujo ADF real todavía no está terminado; los JSON que se habían adjuntado eran un borrador de trabajo y el dueño del proceso pidió no usarlos para no inducir a conclusiones erróneas sobre un flujo todavía incompleto. **No se citan ni se usan como fuente de verdad en este documento ni en el código.** |
| CSV de enriquecimiento real / export de una ejecución ADF | No adjunto | Sin esto no se puede ejecutar `compare-adf` en modo completo ni confirmar claves/cardinalidad de enriquecimiento |
| GDC-1000 | No adjunto | No bloquea la POC según el prompt |

**Consecuencia directa (aplicando el propio fallback del prompt, sección 2):** "Si falta el export ADF, avanzá con un perfil `poc_pmc` basado en las especificaciones disponibles y dejá la equivalencia como `NO_VERIFICADA`." Esto es exactamente lo que se hace aquí. El perfil `adf_actual` queda declarado en el código como estructura vacía/placeholder, lista para poblarse el día que exista un export confiable y una salida ADF real del mismo lote para comparar — no se implementa con reglas inventadas.

## 1. Método: verificación empírica contra el archivo real (sin export ADF)

Ante la falta de export, las posiciones del layout de Detalle/Cabecera/Pie se tomaron de las tablas del prompt (§5, §6, §10) cuando estaban documentadas, y para los campos que el prompt solo describe conceptualmente (`IdDeuda`, `ReferenciaCliente`, moneda, importe principal, entidad, `Concepto`) se generaron posiciones candidatas y **se verificaron contra `entrada_real_1000.txt`** con dos pruebas objetivas:

1. Cada campo debe cumplir un patrón razonable de forma consistente en las 1000 líneas de detalle (dígitos exactos para IDs, `ARS` para moneda, patrón `dígitos,dígitos` para importes, `yyyyMMdd` numérico para fechas).
2. **Prueba de control cruzado**: la suma de los 1000 importes principales extraídos en la posición candidata (173, longitud 13) debe coincidir con el total declarado en el pie del archivo (posición 10, longitud 15).

Resultado de la verificación (reproducible, script ad-hoc ejecutado sobre el archivo real):

- 1000/1000 detalles cumplen el patrón esperado en las 8 posiciones candidatas (`ReferenciaCliente`@58/8, `IdDeuda`@103/9, `Moneda`@168/3, `ImportePrincipal`@173/13, tres fechas de vencimiento @144/8, @666/8, @687/8). Cero fallos.
- Suma de `ImportePrincipal` en los 1000 detalles = **50.948.381.232 centavos**. Total declarado en el pie (posición 10, longitud 15) = **50.948.381.232 centavos**. **Coinciden exactamente.**
- La cantidad declarada en el pie (posición 2, longitud 8) = `00001000` = 1000, coincide con la cantidad real de líneas de detalle del archivo.
- Las tres fechas de vencimiento extraídas (144→2026-07-10, 666→2026-10-30, 687→2026-11-13) son fechas válidas y quedan en orden cronológico ascendente, consistente con "primer/segundo/tercer vencimiento".
- `NombreEntidad`@323/37 y `Concepto`@434/28 producen texto legible y plausible (p. ej. `"GOBIERNO DE LA CIUDAD DE BUENOS AIRES"`, `"Automotores"`), no basura binaria ni texto truncado a mitad de palabra.

Esto **no es una confirmación ADF** (no hay script ni export que lo respalde) pero es bastante más fuerte que una suposición sin verificar: es una hipótesis de layout que reproduce exactamente un control de totales independiente sobre 1000 registros reales. Se clasifica como `SUPUESTO_POC` (verificado empíricamente contra archivo real), nunca como `CONFIRMADA_ADF`. Cualquier divergencia futura contra un export real de ADF debe registrarse aquí, no corregirse en silencio.

## 2. Identificación de tipo de registro — verificado empíricamente

| Tipo | Dígito en posición 1 | Longitud total | Cantidad en archivo real | Estado |
|---|---|---:|---:|---|
| Cabecera | `1` | 88 | 1 | SUPUESTO_POC (verificado empíricamente) |
| Detalle | `2` | 713 | 1000 | SUPUESTO_POC (verificado empíricamente) |
| Pie | `3` | 24 | 1 | SUPUESTO_POC (verificado empíricamente) |
| Registro inválido | cualquier otro dígito, o longitud que no matchea el tipo | — | 0 en este archivo | SUPUESTO_POC — política propia: cualquier línea que no matchee exactamente tipo+longitud esperados se clasifica inválida, nunca se trunca/rellena para forzar el match |

Módulo Python: `etl_pmc.parsing.identify`. Test: longitudes límite (87/88/89, 712/713/714, 23/24/25) y tipo desconocido.

## 3. Layout de entrada — Detalle (tipo `2`, 713 caracteres)

| Campo | Inicio | Longitud | Origen | Estado |
|---|---:|---:|---|---|
| `tipo_registro` | 1 | 1 | Empírico | SUPUESTO_POC |
| `referencia_cliente` | 58 | 8 | Inferido + verificado empíricamente (patrón `^[0-9]{8}$` en 1000/1000 líneas) | SUPUESTO_POC |
| `id_deuda` | 103 | 9 | Inferido + verificado empíricamente (patrón `^[0-9]{9}$` en 1000/1000 líneas) | SUPUESTO_POC |
| `primer_vencimiento` | 144 | 8 | Prompt §6 (tabla de posiciones documentada) + verificado empíricamente (fecha válida, cronológicamente la más temprana de las tres) | PROPUESTA_GUIA, verificado empíricamente |
| `moneda` | 168 | 3 | Inferido + verificado empíricamente (`ARS` en 1000/1000 líneas) | SUPUESTO_POC |
| `importe_principal` | 173 | 13 | Inferido + **verificado por control cruzado de totales contra el pie** (ver §1) | SUPUESTO_POC (verificación fuerte) |
| `nombre_entidad` | 323 | 37 | Inferido + verificado empíricamente (texto legible, sin truncamientos a mitad de palabra en la muestra) | SUPUESTO_POC |
| `concepto` | 434 | 28 | Inferido + verificado empíricamente (texto legible) | SUPUESTO_POC |
| `segundo_vencimiento` | 666 | 8 | Prompt §6 (tabla) + verificado empíricamente | PROPUESTA_GUIA, verificado empíricamente |
| `importe_segundo_vencimiento` | 674 | 13 | Prompt §6 (tabla) + verificado empíricamente (patrón importe válido en 1000/1000) | PROPUESTA_GUIA, verificado empíricamente |
| `tercer_vencimiento` | 687 | 8 | Prompt §6 (tabla) + verificado empíricamente | PROPUESTA_GUIA, verificado empíricamente |
| `importe_tercer_vencimiento` | 695 | 13 | Prompt §6 (tabla) + verificado empíricamente | PROPUESTA_GUIA, verificado empíricamente |
| 708–713 (6 caracteres finales) | 708 | 6 | Sin uso identificado (espacios en la muestra real) | POSTERGADA — no se expone como campo de negocio, se documenta como relleno reservado |

Nombres de campo elegidos deliberadamente en español llano (`primer_vencimiento`, `segundo_vencimiento`, `tercer_vencimiento`) para evitar arrastrar el desorden de nomenclatura que traía el borrador retirado (que llamaba `Vencimiento1`/`Vencimiento2` a los campos de las posiciones 666/687, dejando sin nombre el de la posición 144). Con datos reales, el orden cronológico real es 144 < 666 < 687, así que la numeración "primero/segundo/tercero" coincide con el orden de las posiciones y con el orden de las fechas.

Módulo Python: `etl_pmc.parsing.detalle`. Test: cada patrón en el límite exacto, y el test de control cruzado de totales como test de regresión del layout completo (`tests/unit/test_layout_totales.py`, corre contra `entrada_real_1000.txt`).

## 4. Validaciones de Detalle — `poc_pmc`, basadas en prompt §6

No hay script ADF confirmado que fije la validación byte a byte; se implementa lo que pide el prompt, con decisiones explícitas donde el prompt deja criterio abierto:

| Regla | Implementación | Estado / decisión |
|---|---|---|
| Identificación válida | `id_deuda` y `referencia_cliente` deben cumplir los patrones de longitud fija observados (9 y 8 dígitos respectivamente) | SUPUESTO_POC — patrón tomado de la observación empírica (§1), no de una regla ADF confirmada |
| Moneda válida | `moneda == 'ARS'` | PROPUESTA_GUIA (prompt: "extraé esa regla de ADF"; sin ADF disponible, se usa el único valor observado en la muestra real) |
| Importes válidos | Los tres importes (`importe_principal` + 2 de vencimiento) deben cumplir patrón `^[0-9]{10},[0-9]{2}$` (coma decimal, sin separador de miles) y convertir a `Decimal >= 0` | SUPUESTO_POC — patrón observado en la muestra real; prompt exige `Decimal`, nunca `float` (§6) |
| Fechas válidas | Las tres fechas deben ser parseables como `yyyyMMdd` | PROPUESTA_GUIA (prompt §6: "tres fechas parseables") |
| Orden cronológico entre vencimientos | **No se exige** orden ascendente entre los tres vencimientos como condición de rechazo | Decisión de POC: el prompt no pide esta regla explícitamente (a diferencia del borrador retirado, que sí la tenía); no se agrega una restricción no solicitada. Se documenta como posible divergencia futura si el ADF real la aplica |

Módulo Python: `etl_pmc.validation.detalle`. Tests obligatorios (prompt §16): patrones al límite, moneda distinta de `ARS`, importe con punto en vez de coma, fechas inválidas, importes negativos/nulos/con overflow.

## 5. Layout y control de Pie (tipo `3`, 24 caracteres) — verificado empíricamente

| Campo | Inicio | Longitud | Verificación | Estado |
|---|---:|---:|---|---|
| `cantidad_declarada` | 2 | 8 | `00001000` = 1000, coincide con la cantidad real de detalles del archivo | SUPUESTO_POC (verificado empíricamente) |
| `importe_total_declarado` | 10 | 15 | Coincide exactamente con la suma de los 1000 `importe_principal` (ver §1) | SUPUESTO_POC (verificación fuerte) |

24 = 1 (tipo) + 8 (cantidad) + 15 (importe): sin relleno adicional. Coincide con la tabla del prompt §6 (que documenta cantidad@2/8 e importe@10/15 sin dar la longitud total del registro; la longitud total de 24 es la observación empírica).

## 6. Controles globales de archivo — `poc_pmc`, basado en prompt §7

El prompt exige explícitamente: "Inspeccioná exactamente desde qué rama nace la agregación ADF. No decidas por conveniencia si cuenta todos los detalles o sólo los válidos." Sin export ADF no hay rama que inspeccionar, así que se documenta la decisión tomada en su lugar, para que sea auditable y corregible cuando exista una fuente real:

**Decisión de POC**: el control de totales (cantidad y suma de importes) se calcula sobre **todos los detalles leídos del archivo** (tipo `2`, longitud correcta), incluyendo los que luego resulten individualmente inválidos por moneda/importe/fecha — no solo sobre los válidos. Motivo: un archivo con detalles corruptos que "desaparecen" del conteo antes del control haría que el control de totales nunca detecte esa corrupción, lo que parece más peligroso que la alternativa. Esto debe verificarse contra ADF real en cuanto exista un export; si ADF cuenta solo los válidos, se documentará como divergencia explícita, no se cambiará el código en silencio sin registrar el cambio.

| Regla | Implementación | Estado |
|---|---|---|
| Un pie por archivo | Falla si hay 0 o más de 1 línea tipo `3` | PROPUESTA_GUIA |
| Cero importes nulos en la población de control | Un importe "nulo" es uno que no matchea el patrón esperado (no convierte a `Decimal`) | PROPUESTA_GUIA |
| Cantidad calculada == cantidad declarada | Sobre la población definida arriba (todos los detalles leídos) | SUPUESTO_POC (decisión de población, ver arriba) |
| Diferencia de importe ≤ `Decimal('0.01')` | `abs(calculado - declarado) <= Decimal('0.01')` | PROPUESTA_GUIA (tolerancia exacta dada por el prompt §7) |
| Publicación condicionada | Solo los detalles individualmente válidos **y** con archivo globalmente válido pasan a reglas de negocio (`DetalleAutorizado`); el resto va a `ErrorControlArchivo` | PROPUESTA_GUIA |

Módulo Python: `etl_pmc.control.totales`. Tests: pie ausente, pie duplicado, tolerancia exacta 0.00/0.01/0.02, un detalle inválido afecta el conteo/suma aunque no se publique.

## 7. Cabecera de entrada — `poc_pmc`

| Campo | Inicio | Longitud | Verificación | Estado |
|---|---:|---:|---|---|
| `fecha_cabecera` | 2 | 8 | Prompt §6 (tabla, "longitud de cabecera propuesta: 88") + verificado empíricamente (fecha válida, `20260921` en la muestra) | PROPUESTA_GUIA, verificado empíricamente |

Sin export ADF no hay confirmación de qué pasa si la cabecera falta, está duplicada, o tiene fecha inválida. Política aplicada en `poc_pmc` (prompt §7: "no fabriques cabecera y pie de éxito sin evidencia de que corresponde"): cabecera ausente, duplicada o con fecha inválida ⇒ archivo rechazado globalmente (`REJECTED`), sin publicar salida. Documentado como decisión de POC, `NO_VERIFICADA`.

## 8. Enriquecimiento — `poc_pmc`, `NO_VERIFICADA`

### 8.1 Esquema real de las tablas SQL (aportado por el dueño del proceso)

No es un export ni una vista de ADF, pero sí el DDL real de las dos tablas SQL detrás del enriquecimiento (`intdb.DebtEnrichmentPoc`, ~100 filas de prueba cargadas, y `intdb.FixedValues`). Reemplaza los nombres de columna que el prompt sugería (`DescripcionEntidad`, `CodBancoConfig`, `CodigoServicioConfig`), que no existen en las tablas reales:

- **`intdb.DebtEnrichmentPoc`** (`CodEntidad, LoteId, IdDeuda, Documento, NumeroCuenta, CBU, CodigoPago, FechaVencimiento, FechaProceso, ImporteSQL, EstadoSQL, Referencia, Canal, Segmento, Activo, FechaAltaUTC, FechaModificacionUTC`) es la tabla de **`record_join`**: una fila por deuda. Corresponde al nodo `DERLIMPIARENRIQ` que sí estaba confirmado en el export de ADF retirado (limpiaba tanto `IdDeuda` como `Documento`, sin aclarar cuál es la clave real).
- **`intdb.FixedValues`** es la **"Tabla Intermedia"** que cita GDC-1000 literalmente (`PATH_ENTITY_OUT` coincide con el campo `Path_Entity_Out` que GDC-1000 menciona por nombre). Trae, entre decenas de columnas heredadas del ESB IBM Integration Bus, `CodEntidad`, `Descripcion`, `TipoRegistroCab`, `TipoRegistroDet`, `TipoRegistroPie`, `CodigoServicio`, `CodBanco` — es la fuente real de **`single_configuration`**. Los módulos `single_configuration.py` y el CSV de ejemplo ya se actualizaron a estos nombres (`CodEntidad, Descripcion, CodBanco, CodigoServicio`).

Decisiones explícitas del dueño del proceso (no inferidas): la clave de `record_join` no es información productiva todavía disponible — se fija `IdDeuda` como clave por defecto, marcado como **decisión de POC para simular el proceso, no dato confirmado**. `TipoRegistroCabPMC`/`DetPMC`/`PiePMC` **siguen viniendo como parámetro del manifiesto**, no se leen de `FixedValues` (aunque la tabla real los tenga) — decisión explícita para esta entrega.

- **`record_join`**: clave = `IdDeuda` (decisión de POC, ver arriba, no confirmada contra producción). Columnas, filtros y cardinalidad siguen siendo configuración requerida del perfil; sin esa configuración, el motor falla con un error claro en vez de adivinar. Sigue sin estar cableada a ningún campo de la salida (el layout de 280 posiciones no usa ninguna columna de `DebtEnrichmentPoc`); su rol es, como mucho, validar existencia/estado de la deuda, no confirmado. `NO_VERIFICADA`.
- **`single_configuration`**: consume como máximo una fila de `FixedValues`; ausencia de archivo, CSV vacío, columna ausente, nulo, cadena vacía y múltiples filas se tratan como errores distintos y explícitos (prompt §8); múltiples filas ⇒ fallo por cardinalidad, nunca producto cartesiano ni `TOP(1)` arbitrario. `NO_VERIFICADA`.

Módulo Python: `etl_pmc.enrichment.record_join`, `etl_pmc.enrichment.single_configuration`.

## 9. Reglas de negocio PMC — `poc_pmc`, `NO_VERIFICADA`

Implementadas íntegramente según prompt §9: filtro opcional de 30 días (`AplicarFiltro30Dias`, default `false`), máximo dos recibos por cliente (`AplicarMaxDosCliente`, default `false`), orden de aplicación (primero rango por cliente, luego filtros conjuntos de importe/fecha/rango — no al revés), desempate por número de línea. Motivos de exclusión con la prioridad indicada: `IMPORTE_SUPERA_MAXIMO`, `VENCIMIENTO_SUPERA_30_DIAS`, `MAXIMO_DOS_RECIBOS_CLIENTE`. Sin export ADF, no hay forma de confirmar el orden real de aplicación contra producción; se sigue literalmente el orden que indica el prompt.

### 9.1 Filtro de antigüedad — `INVENTADO`, a pedido explícito del usuario

GDC-1000 (§C, "Filtro 1") excluye registros con "antigüedad mayor a 10 meses **o** vencimiento más de 30 días posterior a la fecha de creación del archivo". La mitad de vencimiento ya estaba cubierta (`AplicarFiltro30Dias`); la mitad de antigüedad quedaba fuera de alcance porque **no existe ningún campo ni posición documentada** para "fecha de emisión de la deuda" — ni en el prompt, ni verificado empíricamente, ni en GDC-1000 (que tampoco da una posición para este dato).

A pedido explícito del usuario ("si no sabemos las reglas inventá algunas acordes"), se implementó de todos modos, dejando constancia expresa de que es una invención sin ninguna base:

- **Posición inventada**: `fecha_emision_deuda_sintetica`, detalle, posición 152, longitud 8 (`yyyyMMdd`) — un hueco del registro sin uso conocido (entre `primer_vencimiento`@144 y `moneda`@168). No hay ninguna razón para creer que un archivo SAP real tenga una fecha de emisión ahí; es solo un lugar disponible para poder simular el filtro.
- **Regla**: se excluye el detalle si `fecha_emision_deuda_sintetica < fecha_cabecera - 10 meses` (aritmética de meses calendario, recortando el día en meses más cortos). Si el campo no parsea como fecha válida — lo esperable contra datos reales, ya que la posición es inventada — el detalle se excluye con motivo `ANTIGUEDAD_NO_CALCULABLE`, no se lo deja pasar en silencio.
- **Flag**: `AplicarFiltroAntiguedad`, **opcional** en el manifiesto (default `false`), a diferencia de los otros dos filtros que son obligatorios — asimetría deliberada para señalar que este es el único parámetro sin ningún respaldo documental, ni siquiera de la guía.
- **Prioridad de motivos**: se insertó entre `IMPORTE_SUPERA_MAXIMO` y `VENCIMIENTO_SUPERA_30_DIAS`, ya que GDC-1000 los agrupa en un único "Filtro 1" — decisión de POC, sin forma de confirmar el orden real.
- Módulo: `etl_pmc.rules.pmc` (`MOTIVO_ANTIGUEDAD_SUPERA_10_MESES`, `MOTIVO_ANTIGUEDAD_NO_CALCULABLE`). Tests: `tests/unit/test_rules_pmc.py` (apagado por defecto, campo no calculable, límite exacto de 10 meses, caso reciente).

**Verificado contra `entrada_real_1000.txt`**: con el flag activado, los 1000 detalles se rechazan — pero no por `ANTIGUEDAD_NO_CALCULABLE` como se podría esperar, sino por `ANTIGUEDAD_SUPERA_10_MESES`: la posición 152 sí contiene 8 dígitos con forma de fecha en el archivo real (es contenido real de otro campo SAP, casualmente con esa forma), y esa fecha cae fuera de la ventana de 10 meses. Es decir, el campo "parece" válido pero no significa lo que la regla asume — exactamente el riesgo de inventar una posición sin base, y por eso el flag queda apagado por defecto. No usar este resultado como evidencia de nada contra datos reales.

## 10. Layout de salida (280 posiciones) — `poc_pmc`, `NO_VERIFICADA`

Implementado íntegramente según la tabla del prompt §10 (detalle, cabecera y pie de 280 posiciones, fórmulas de mensaje de ticket/pantalla). No se promueve a `adf_actual` bajo ninguna circunstancia hasta contar con una salida ADF real del mismo lote para comparar byte a byte con `compare-adf`.

## 11. Perfiles de implementación

- **`adf_actual`**: declarado en el código como estructura vacía/placeholder. No se puebla con ninguna regla mientras no exista un export de ADF confiable y una salida real del mismo lote para verificar. Intentar seleccionar este perfil sin esa configuración produce un error de configuración explícito, no un fallback silencioso a `poc_pmc`.
- **`poc_pmc`**: perfil activo de esta POC. Todo lo documentado en §2–§10, con cada regla marcada `PROPUESTA_GUIA` o `SUPUESTO_POC` según su origen, y equivalencia `NO_VERIFICADA` de punta a punta hasta correr `compare-adf` contra una salida ADF real.

## 12. Pendientes / `POSTERGADA`

- Contenido real de los 6 caracteres finales (708–713) del registro Detalle.
- Confirmación ADF de la población exacta usada en el control de totales (todos los detalles vs. solo válidos) — decisión de POC documentada en §6, pendiente de confirmar.
- Clave y cardinalidad reales de enriquecimiento por registro (`record_join`) — no hay CSV real ni nodos de join disponibles.
- Semántica exacta de selección de fila única en `single_configuration` en el ADF real.
- Formato y contenido real de un pie de página productivo de 346/348 posiciones (fuera de alcance, prompt §17).
- Verificación de `lpad`/`zfill` en desbordes de ancho (prompt §10, pendiente de test específico).
- `compare-adf` solo podrá ejecutarse en modo completo cuando exista una salida ADF real del mismo lote; hasta entonces solo se prueba contra fixtures sintéticos y contra `entrada_real_1000.txt` procesado por este motor.
- Reincorporar un export de ADF a este documento cuando el flujo esté terminado y el dueño del proceso confirme que puede usarse como fuente de verdad.
