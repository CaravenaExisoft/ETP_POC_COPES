#!/usr/bin/env bash
# Configuracion UNICA (una sola vez) de autenticacion OIDC entre GitHub
# Actions y Azure, para el workflow .github/workflows/deploy.yml.
#
# NO SE EJECUTA AUTOMATICAMENTE: son comandos de referencia, a correr
# manualmente con autorizacion explicita (mismo criterio que
# infra/deploy_container_app_job.sh). Reemplazar todos los placeholders <...>
# antes de ejecutar. Verificar la sintaxis vigente de az cli/API contra la
# documentacion oficial de Azure antes de correr esto en un entorno real.
#
# Por que OIDC y no un service principal con secreto: sin credencial de larga
# duracion que rotar ni guardar como secret de GitHub -- el token se negocia
# en cada corrida del workflow contra el federated credential scopeado a
# este repo/rama especifico.

set -euo pipefail

# Ver infra/deploy_container_app_job.sh: necesario en Git Bash/MSYS en
# Windows, donde "/subscriptions/..." se malinterpreta como ruta de Windows.
export MSYS_NO_PATHCONV=1

# Valores reales de la subscription "Exisoft" (mismos que
# infra/deploy_container_app_job.sh). CONTAINERAPP_JOB_RESOURCE_ID solo se
# puede completar DESPUES de correr ese script (el Job todavia no existe).
SUBSCRIPTION_ID="c19f6e07-a376-4cc2-9496-6aa9e4129caf"
RESOURCE_GROUP_IDENTITY="RG-Proyecto-ARGO"
LOCATION="westus3"
UAMI_NAME="uami-github-actions-etl-pmc"

REPO="CaravenaExisoft/ETP_POC_COPES"
RAMA="main"

# Recursos existentes a los que esta identidad va a necesitar acceso.
ACR_RESOURCE_ID="/subscriptions/${SUBSCRIPTION_ID}/resourceGroups/RG-Proyecto-ARGO/providers/Microsoft.ContainerRegistry/registries/acrargoexi"
CONTAINERAPP_JOB_RESOURCE_ID="/subscriptions/${SUBSCRIPTION_ID}/resourceGroups/RG-Proyecto-ARGO/providers/Microsoft.App/jobs/job-etl-pmc-poc"  # existe recien despues de correr deploy_container_app_job.sh

az account set --subscription "${SUBSCRIPTION_ID}"

# 1) Identidad administrada asignada por el usuario, dedicada a este pipeline
#    de CI/CD (no reutilizar la identidad del propio Job -- separar quien
#    construye/publica la imagen de quien la ejecuta).
az identity create \
  --name "${UAMI_NAME}" \
  --resource-group "${RESOURCE_GROUP_IDENTITY}" \
  --location "${LOCATION}"

CLIENT_ID=$(az identity show --name "${UAMI_NAME}" --resource-group "${RESOURCE_GROUP_IDENTITY}" --query clientId -o tsv)
PRINCIPAL_ID=$(az identity show --name "${UAMI_NAME}" --resource-group "${RESOURCE_GROUP_IDENTITY}" --query principalId -o tsv)
TENANT_ID=$(az account show --query tenantId -o tsv)

echo "CLIENT_ID=${CLIENT_ID}"
echo "TENANT_ID=${TENANT_ID}"
echo "SUBSCRIPTION_ID=${SUBSCRIPTION_ID}"
echo "--> Cargar estos tres valores como Variables (no Secrets) del repo/entorno de GitHub Actions."

# 2) Federated credential: solo el workflow corriendo sobre la rama indicada
#    de ESTE repo puede pedir un token con esta identidad. Agregar una
#    entrada mas si tambien se quiere permitir Pull Requests (subject
#    "repo:${REPO}:pull_request") o un environment protegido de GitHub
#    ("repo:${REPO}:environment:<nombre>").
az identity federated-credential create \
  --name "github-actions-${RAMA}" \
  --identity-name "${UAMI_NAME}" \
  --resource-group "${RESOURCE_GROUP_IDENTITY}" \
  --issuer "https://token.actions.githubusercontent.com" \
  --subject "repo:${REPO}:ref:refs/heads/${RAMA}" \
  --audiences "api://AzureADTokenExchange"

# 3) Permisos MINIMOS: push de imagenes al ACR existente (en su propio
#    resource group, eso no importa -- el scope es el resource ID del ACR,
#    no el resource group) y actualizar el Container Apps Job existente.
#    Nada de Owner/Contributor de suscripcion (prompt seccion 12, mismo
#    criterio que infra/deploy_container_app_job.sh).
az role assignment create \
  --assignee-object-id "${PRINCIPAL_ID}" \
  --assignee-principal-type ServicePrincipal \
  --role "AcrPush" \
  --scope "${ACR_RESOURCE_ID}"

az role assignment create \
  --assignee-object-id "${PRINCIPAL_ID}" \
  --assignee-principal-type ServicePrincipal \
  --role "Container Apps Contributor" \
  --scope "${CONTAINERAPP_JOB_RESOURCE_ID}"

echo "Listo. Cargar CLIENT_ID/TENANT_ID/SUBSCRIPTION_ID en GitHub (Settings > Secrets and variables > Actions > Variables)"
echo "con los nombres AZURE_CLIENT_ID, AZURE_TENANT_ID, AZURE_SUBSCRIPTION_ID -- los usa .github/workflows/deploy.yml."
