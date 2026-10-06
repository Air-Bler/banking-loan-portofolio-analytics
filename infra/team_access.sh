#!/usr/bin/env bash

RG=rg_gtgh_data_09; P=loant2gk
source infra/team.local 
RG_ID=$(az group show -n $RG --query id -o tsv)
KV_ID=$(az keyvault show -n kv-$P --query id -o tsv)

# Teammates 
for U in $TEAM; do
  az role assignment create --assignee $U --role Contributor --scope $RG_ID -o none
done

# Me
az role assignment create --assignee $(az ad signed-in-user show --query id -o tsv) --role "Key Vault Secrets Officer" --scope $KV_ID -o none


for ENV in dev prod; do
  PID=$(az containerapp show -g $RG -n ca-$P-$ENV --query identity.principalId -o tsv)
  az role assignment create --assignee-object-id $PID --assignee-principal-type ServicePrincipal \
    --role "Key Vault Secrets User" --scope $KV_ID -o none
done