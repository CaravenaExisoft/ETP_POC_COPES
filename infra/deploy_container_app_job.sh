#!/usr/bin/env bash
# Comandos de Azure CLI para crear el Container Apps Job de esta POC.
# NO SE EJECUTA AUTOMATICAMENTE: son comandos de referencia, a correr
# manualmente y con autorizacion explicita (prompt seccion 15). Reutiliza
# Storage/ADF/SQL existentes; no crea otra base SQL ni duplica infraestructura.
#
# Reemplazar todos los placeholders <...> antes de ejecutar. Verificar
# siempre la version de API/CLI vigente en la documentacion oficial de Azure
# antes de correr esto contra un entorno real (prompt seccion 15: "no
# inventes comandos"). Los nombres de recurso y flags de az cli pueden variar
# entre versiones del CLI; validar con `az containerapp job --help` primero.

set -euo pipefail

# Si esto corre en Git Bash / MSYS en Windows: MSYS convierte automaticamente
# cualquier argumento que empiece con "/" (como los resource ID de Azure,
# "/subscriptions/...") en una ruta de Windows, rompiendo --scope en los
# role assignment. Desactivarlo es necesario en ese entorno; no tiene efecto
# en bash real (Linux/WSL/macOS).
export MSYS_NO_PATHCONV=1

# Valores reales de la subscription "Exisoft", confirmados por consulta de
# solo lectura (az acr show / az containerapp env list / az storage account
# list) el 2026-09-23. El ACR y el Environment ya existen en RG-Proyecto-ARGO;
# el storage account real de esta POC (con los containers inbound/enrichment/
# out/audit/error/stage ya creados) esta en RG-COPES-ETL-POC, resource group
# distinto -- por eso STORAGE_ACCOUNT_ID abajo apunta a otro RG que el resto:
# los resource groups no son una frontera de permisos, el scope del role
# assignment es el resource ID puntual.
SUBSCRIPTION_ID="c19f6e07-a376-4cc2-9496-6aa9e4129caf"
RESOURCE_GROUP="RG-Proyecto-ARGO"
LOCATION="westus3"
CONTAINERAPPS_ENVIRONMENT="cae-argo-dev"
ACR_NAME="acrargoexi"
IMAGE_NAME="etl-pmc"
IMAGE_TAG="0.1.0"
JOB_NAME="job-etl-pmc-poc"
USER_ASSIGNED_IDENTITY="uami-job-etl-pmc"
STORAGE_ACCOUNT_URL="https://copesetlpoc.blob.core.windows.net"

az account set --subscription "${SUBSCRIPTION_ID}"

# 1) Build & push de la imagen al ACR existente (no crea un ACR nuevo).
az acr build \
  --registry "${ACR_NAME}" \
  --image "${IMAGE_NAME}:${IMAGE_TAG}" \
  .

# 2) Identidad administrada para el Job (si no existe una a reutilizar).
#    Documentar aparte los permisos otorgados (paso 3) -- nunca Owner/Contributor
#    de toda la suscripcion (prompt seccion 12).
az identity show \
  --name "${USER_ASSIGNED_IDENTITY}" \
  --resource-group "${RESOURCE_GROUP}" \
  --query id -o tsv || \
az identity create \
  --name "${USER_ASSIGNED_IDENTITY}" \
  --resource-group "${RESOURCE_GROUP}" \
  --location "${LOCATION}"

IDENTITY_ID=$(az identity show \
  --name "${USER_ASSIGNED_IDENTITY}" \
  --resource-group "${RESOURCE_GROUP}" \
  --query id -o tsv)
IDENTITY_PRINCIPAL_ID=$(az identity show \
  --name "${USER_ASSIGNED_IDENTITY}" \
  --resource-group "${RESOURCE_GROUP}" \
  --query principalId -o tsv)

# 3) Permisos MINIMOS sobre el Storage Account existente (no sobre toda la
#    suscripcion). "Storage Blob Data Contributor" alcanza para leer inbound/
#    enrichment y escribir out/audit/error. Si se prefiere separar lectura de
#    escritura por contenedor, usar asignaciones a nivel de contenedor
#    (--scope apuntando al contenedor especifico) en vez de a nivel de cuenta.
STORAGE_ACCOUNT_ID="/subscriptions/${SUBSCRIPTION_ID}/resourceGroups/RG-COPES-ETL-POC/providers/Microsoft.Storage/storageAccounts/copesetlpoc"
az role assignment create \
  --assignee-object-id "${IDENTITY_PRINCIPAL_ID}" \
  --assignee-principal-type ServicePrincipal \
  --role "Storage Blob Data Contributor" \
  --scope "${STORAGE_ACCOUNT_ID}"

# 4) Permiso de pull de imagen desde ACR para esta identidad.
ACR_ID=$(az acr show --name "${ACR_NAME}" --query id -o tsv)
az role assignment create \
  --assignee-object-id "${IDENTITY_PRINCIPAL_ID}" \
  --assignee-principal-type ServicePrincipal \
  --role "AcrPull" \
  --scope "${ACR_ID}"

# 5) Creacion del Container Apps Job. Trigger "manual": ADF lo inicia via una
#    actividad Web/REST contra la API de Container Apps Jobs (ver
#    docs/integracion_adf.md), no un segundo scheduler. Recursos iniciales
#    conservadores (una replica, paralelismo 1); ajustar segun mediciones
#    reales de tiempo/memoria (prompt seccion 15), no antes.
az containerapp job create \
  --name "${JOB_NAME}" \
  --resource-group "${RESOURCE_GROUP}" \
  --environment "${CONTAINERAPPS_ENVIRONMENT}" \
  --trigger-type Manual \
  --replica-timeout 3600 \
  --replica-retry-limit 0 \
  --parallelism 1 \
  --replica-completion-count 1 \
  --image "${ACR_NAME}.azurecr.io/${IMAGE_NAME}:${IMAGE_TAG}" \
  --cpu "1.0" \
  --memory "2Gi" \
  --registry-server "${ACR_NAME}.azurecr.io" \
  --registry-identity "${IDENTITY_ID}" \
  --mi-user-assigned "${IDENTITY_ID}" \
  --command "etl-pmc" \
  --args "run" "--manifest" "<se-sobreescribe-por-ejecucion-ver-docs/integracion_adf.md>"

echo "Job creado. Para iniciar una ejecucion puntual de prueba (no automatico):"
echo "  az containerapp job start --name ${JOB_NAME} --resource-group ${RESOURCE_GROUP} \\"
echo "    --args 'run' '--manifest' '<container>/<blob-del-manifiesto>'"
