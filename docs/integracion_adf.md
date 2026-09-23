# Integración con ADF

Este documento describe cómo `PL_EJECUTAR_ETL_POC` (o un pipeline de prueba clonado de él) debería invocar el Container Apps Job y verificar su resultado. **No hay un export ADF confiable disponible en este repositorio** (ver `docs/matriz_equivalencia.md` sección 0): lo que sigue es la integración propuesta para esta POC, no una confirmación de que ADF ya la implemente así. Los pasos marcados **PENDIENTE DE VALIDACIÓN** requieren verificar la versión de API/CLI vigente en la documentación oficial de Azure antes de implementarlos contra un entorno real — no se inventan payloads ni nombres de actividad.

## Resumen del flujo propuesto

1. **Conservar** `EpComprobarEntrada` y `PL_EXTRAER_SQL` tal como están: la detección de archivo y la extracción SQL siguen siendo responsabilidad de ADF (prompt sección 1). El Container App no reemplaza esas etapas.
2. **Clonar** `DF_GENERAR_BANELCO`/el pipeline que lo invoca, o agregar una selección explícita de motor (parámetro `MotorTransformacion` con valores `data_flow` / `container_app`) sin romper el recorrido actual de `PL_EJECUTAR_ETL_POC`. No se reemplaza el Data Flow existente; se agrega una rama alternativa para poder comparar.
3. **Crear el manifiesto inmutable** después de que `PL_EXTRAER_SQL` termine, con una actividad `Copy`/`SetVariable`+`Web` (o una Azure Function si el proyecto ya usa una) que escriba el JSON del manifiesto (ver `examples/manifiesto.example.json`) a un blob con nombre único por corrida, por ejemplo `manifests/<lote>/<run_id>.json`. El manifiesto es la única forma en la que los parámetros de ADF llegan al Job — **los parámetros de pipeline no se transfieren solos** (prompt sección 15).
4. **Iniciar la ejecución del Job** con la identidad de ADF, vía una actividad `Web` (o `WebHook`) contra la API de Azure Container Apps Jobs, pasando el `run_id`/ubicación del manifiesto como argumento de línea de comandos (`--manifest <container>/<blob> --storage-account-url <url>`), no como variable de entorno con datos sensibles.
5. **Conservar el identificador exacto** de la ejecución del Job que devuelve el `start` (execution name/ID), guardándolo en una variable de pipeline para el paso siguiente. No asumir que la respuesta de `start` es sincrónica.
6. **Esperar y consultar** esa ejecución hasta un estado terminal (`Succeeded`/`Failed`), con `Until` + `Wait` acotados por un timeout de pipeline, consultando el estado de ejecución del Job (no solo si `start` fue aceptado — una respuesta 200 en el `start` **no significa que el ETL terminó bien**, prompt sección 15).
7. **Leer el manifiesto de resultado de aplicación** (el JSON que produce `ResultadoEjecucion.to_json()`, ver `examples/resultado.example.json`) desde `audit/<prefix>/` o donde el manifiesto de entrada indique, y validar `estado`, `lote_id` y `archivos_producidos` antes de continuar. El código de salida del proceso (0/1) es una señal complementaria, no la única fuente de verdad — los estados de aplicación (`SUCCEEDED`, `SUCCEEDED_WITH_REJECTIONS`, `REJECTED`, `FAILED`, `ALREADY_PROCESSED`) son los que ADF debe leer para decidir la rama siguiente.
8. **Archivar el `inbound`** solo después de: (a) éxito de aplicación (`SUCCEEDED` o `SUCCEEDED_WITH_REJECTIONS`, nunca `REJECTED`/`FAILED`) y (b) verificación de que el archivo de salida existe y su tamaño/hash es razonable. El Container App nunca borra ni mueve el archivo de `inbound` (prompt sección 12): esa responsabilidad queda enteramente en ADF, igual que hoy.
9. **En fallos** (`FAILED`, o el Job termina con estado de ejecución fallido sin producir un JSON de resultado legible), seguir la rama de error existente de `PL_EJECUTAR_ETL_POC`, conservando el manifiesto de entrada y cualquier CSV de errores parcial como evidencia. No reintentar automáticamente sin acotar reintentos.

## Autenticación e identidad

- El Job usa una identidad administrada (user-assigned) con permisos mínimos sobre el Storage Account existente (`Storage Blob Data Contributor`, ver `infra/deploy_container_app_job.sh`) y `AcrPull` sobre el registro de contenedores. Nunca Owner/Contributor de la suscripción (prompt sección 12).
- La identidad de ADF que inicia el Job necesita permiso para iniciar/consultar ejecuciones de Container Apps Jobs (`Microsoft.App/jobs/start/action` y lectura de `executions`) sobre el recurso del Job específico, no sobre todo el resource group. **PENDIENTE DE VALIDACIÓN**: el nombre exacto del rol built-in más ajustado (o si conviene un rol custom) depende de la versión de Azure RBAC vigente al momento de implementar esto — verificar contra la documentación oficial antes de asignarlo.
- Sin secretos en el manifiesto, en los argumentos del contenedor ni en los logs (prompt sección 12): la única credencial en juego es la identidad administrada, resuelta por el SDK en tiempo de ejecución.

## Payload del manifiesto

Ver `examples/manifiesto.example.json` — es el mismo contrato de la sección 4 del prompt, con los placeholders ya reemplazados por valores de una corrida real (`test-run-001` sobre `entrada_real_1000.txt`, ejecutada localmente para validar el motor, no contra Azure real). Los valores de `format` (encoding, `output_newline: "CRLF"`, `output_bom: false`, `final_newline: true`) son explícitos para reproducibilidad; **no están verificados contra la salida real de ADF** (no hay una disponible) — si al comparar con `compare-adf` aparece una diferencia de encoding/BOM/newline, ajustar estos campos y volver a generar, dejando registrada la corrección en `docs/matriz_equivalencia.md`.

## Resultado de aplicación

Ver `examples/resultado.example.json` — es la salida real (`to_json()`) de una corrida exitosa contra `entrada_real_1000.txt` en modo local. Campos clave para la actividad ADF que lo lea:

- `estado`: mapear a la rama del pipeline (éxito / éxito con rechazos / rechazo de negocio / falla técnica / ya procesado).
- `cantidad_leida/valida/rechazada/excluida_negocio/emitida`: para páneles de Monitor y para decidir si un `SUCCEEDED_WITH_REJECTIONS` es aceptable para este lote o debe tratarse como error operativo.
- `hash_entrada`/`hash_enriquecimiento`: para trazabilidad y para la clave de idempotencia (`docs/matriz_equivalencia.md` no cubre esto; ver `etl_pmc.idempotency`).
- `ruta_errores`: dónde está el CSV de errores de esta corrida, si lo hay.

## Benchmark comparativo (ADF vs Container App)

Para comparar fidelidad/tiempo/consumo (prompt sección 1 y 16): extraer el SQL una única vez con `PL_EXTRAER_SQL`, conservar tanto la entrada como el extracto, y ejecutar **ambos** motores contra el mismo snapshot con destinos de salida separados (`pmc/adf/<entidad>/<lote>/` vs `pmc/containerapp/<entidad>/<lote>/`, prompt sección 3). No ejecutar los dos motores contra el mismo `inbound` compitiendo por retirarlo. Archivar el `inbound` solo al terminar la comparación de ambos resultados con `compare-adf`.

## Qué falta para que esto sea ejecutable contra Azure real

Todo lo anterior es la integración propuesta; lo siguiente está **pendiente de validación** antes de un primer intento real (no se ha desplegado nada, prompt sección 13/15):

- Nombre y payload exacto de la actividad ADF que inicia un Container Apps Job (API REST vs. actividad nativa si ya existe una en el momento de implementar esto).
- Formato exacto de la respuesta de `start` y de la consulta de estado de ejecución (nombres de campo pueden cambiar entre versiones de API).
- Rol RBAC más ajustado para que la identidad de ADF pueda iniciar/consultar el Job.
- Validación de que `az containerapp job create` en `infra/deploy_container_app_job.sh` sigue aceptando exactamente esos flags en la versión de Azure CLI vigente al desplegar.
