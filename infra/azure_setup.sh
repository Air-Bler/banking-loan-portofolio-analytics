#!/usr/bin/env bash

export AZURE_CORE_OUTPUT=none
RG=rg_gtgh_data_09
P=loant2gk                    

az keyvault create -g $RG -n kv-$P
az acr create -g $RG -n acr$P --sku Basic
az containerapp env create -g $RG -n cae-$P -l germanywestcentral   

for ENV in dev prod; do
  az containerapp create -g $RG -n ca-$P-$ENV --environment cae-$P \
    --image mcr.microsoft.com/k8se/quickstart:latest --ingress external --target-port 80 \
    --registry-server acr$P.azurecr.io --registry-identity system --env-vars APP_ENV=$ENV
done