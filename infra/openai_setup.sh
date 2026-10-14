#!/usr/bin/env bash
# Azure OpenAI for the assistant: one resource, two deployments.
#   gpt-4.1-mini       prod only
#   gpt-4.1-mini-eval  dev and local eval runs (keeps eval load off prod)
# Capacity is in thousands of tokens per minute. At 20, eval runs sharing the
# prod deployment caused 429s and 20 s answers (14 Oct 2026), so both are 100.
# Already applied. Re-running is safe but creates a new revision of both apps.
# Assumes the apps' managed identities can read the Key Vault secret.
set -euo pipefail

RG=rg_gtgh_data_09
LOC=germanywestcentral
OAI=oai-loant2gk
KV=kv-loant2gk
MODEL=gpt-4.1-mini
VERSION=2025-04-14
API_VERSION=2024-10-21
CAPACITY=100

# 1. Resource
az cognitiveservices account show -g $RG -n $OAI -o none 2>/dev/null || \
  az cognitiveservices account create -g $RG -n $OAI -l $LOC \
    --kind OpenAI --sku S0 --custom-domain $OAI -o none

# 2. Deployments
for DEP in $MODEL $MODEL-eval; do
  az cognitiveservices account deployment create -g $RG -n $OAI \
    --deployment-name $DEP --model-name $MODEL --model-version $VERSION \
    --model-format OpenAI --sku-name GlobalStandard --sku-capacity $CAPACITY -o none
done

# 3. Key into Key Vault (apps read it from there, never from plain settings)
az keyvault secret set --vault-name $KV -n azure-openai-api-key -o none \
  --value "$(az cognitiveservices account keys list -g $RG -n $OAI --query key1 -o tsv)"

# 4. App settings: prod uses the prod deployment, dev the eval one
for APP in ca-loant2gk-prod ca-loant2gk-dev; do
  DEP=$MODEL; [ "$APP" = ca-loant2gk-dev ] && DEP=$MODEL-eval
  az containerapp secret set -g $RG -n $APP -o none \
    --secrets openai-key=keyvaultref:https://$KV.vault.azure.net/secrets/azure-openai-api-key,identityref:system
  az containerapp update -g $RG -n $APP -o none --set-env-vars \
    AZURE_OPENAI_ENDPOINT=https://$OAI.openai.azure.com/ AZURE_OPENAI_DEPLOYMENT=$DEP \
    AZURE_OPENAI_API_VERSION=$API_VERSION AZURE_OPENAI_API_KEY=secretref:openai-key
done
