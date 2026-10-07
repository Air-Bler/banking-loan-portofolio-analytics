#!/usr/bin/env bash

RG=rg_gtgh_data_09; P=loant2gk
REPO=IoannisPan11/banking-loan-portofolio-analytics

CLIENT_ID=$(az ad app create --display-name gh-deploy-$P --query appId -o tsv)
SP_ID=$(az ad sp create --id $CLIENT_ID --query id -o tsv)
az ad app federated-credential create --id $CLIENT_ID -o none --parameters \
  "{\"name\":\"main\",\"issuer\":\"https://token.actions.githubusercontent.com\",\"subject\":\"repo:$REPO:ref:refs/heads/main\",\"audiences\":[\"api://AzureADTokenExchange\"]}"

grant() { az role assignment create --assignee-object-id $SP_ID --assignee-principal-type ServicePrincipal --role "$1" --scope "$2" -o none; }
grant AcrPush "$(az acr show -n acr$P --query id -o tsv)"
grant Contributor "$(az containerapp show -g $RG -n ca-$P-dev --query id -o tsv)"
grant Contributor "$(az containerapp show -g $RG -n ca-$P-prod --query id -o tsv)"
grant Contributor "$(az containerapp env show -g $RG -n cae-$P --query id -o tsv)"

gh secret set AZURE_CLIENT_ID --repo $REPO --body "$CLIENT_ID"
gh secret set AZURE_TENANT_ID --repo $REPO --body "$(az account show --query tenantId -o tsv)"
gh secret set AZURE_SUBSCRIPTION_ID --repo $REPO --body "$(az account show --query id -o tsv)"

for ENV in dev prod; do
  az containerapp ingress update -g $RG -n ca-$P-$ENV --target-port 8000 -o none
  az containerapp update -g $RG -n ca-$P-$ENV --min-replicas 0 --max-replicas 1 -o none
done