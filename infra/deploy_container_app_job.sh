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

SUBSCRIPTION_ID="<subscription-id>"
RESOURCE_GROUP="<resource-group>"
LOCATION="<location>"                      # ej. eastus2, brazilsouth
CONTAINERAPPS_ENVIRONMENT="<nombre-environment-existente>"
ACR_NAME="<nombre-acr-existente>"
IMAGE_NAME="etl-pmc"
IMAGE_TAG="0.1.0"
JOB_NAME="job-etl-pmc-poc"
USER_ASSIGNED_IDENTITY="<identidad-administrada-existente-o-a-crear>"
STORAGE_ACCOUNT_URL="https://<storage>.blob.core.windows.net"

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
STORAGE_ACCOUNT_ID="<resource-id-del-storage-account-existente>"
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
