#!/usr/bin/env bash
# Step 8c: Entra ID app that prod uses to check sign-in tokens (JWT). Run once: bash infra/auth_setup.sh
export AZURE_CORE_OUTPUT=none
source infra/team.local                        # TEAM: teammates' emails (gitignored)
RG=rg_gtgh_data_09
GRAPH=https://graph.microsoft.com/v1.0
AZ_CLI=04b07795-8ddb-461a-bbee-02f9e1bf7b46    # Azure CLI's public app ID: lets the team get tokens with az
TENANT=$(az account show --query tenantId -o tsv)
SCOPE_ID=$(python3 -c "import uuid; print(uuid.uuid4())")
ROLE_ID=$(python3 -c "import uuid; print(uuid.uuid4())")

# 1. The app registration: its tokens carry aud=<app ID> and roles=["Loan.Read"]
APP_ID=$(az ad app create --display-name api-loant2gk --sign-in-audience AzureADMyOrg --query appId -o tsv)
sleep 15                                       # let the new app reach all of Entra ID
SCOPE='{"id": "'$SCOPE_ID'", "value": "access_as_user", "type": "User", "isEnabled": true,
  "adminConsentDisplayName": "Call the loan analytics API", "adminConsentDescription": "Call the loan analytics API as the signed-in user",
  "userConsentDisplayName": "Call the loan analytics API", "userConsentDescription": "Call the loan analytics API as you"}'
cat > /tmp/api-app.json <<JSON
{"identifierUris": ["api://$APP_ID"],
 "appRoles": [{"id": "$ROLE_ID", "value": "Loan.Read", "displayName": "Loan reader",
   "description": "Can call the loan analytics API", "allowedMemberTypes": ["User"], "isEnabled": true}],
 "api": {"requestedAccessTokenVersion": 2, "oauth2PermissionScopes": [$SCOPE]}}
JSON
az rest --method PATCH --uri "$GRAPH/applications(appId='$APP_ID')" --headers Content-Type=application/json --body @/tmp/api-app.json
cat > /tmp/api-app.json <<JSON
{"api": {"requestedAccessTokenVersion": 2, "oauth2PermissionScopes": [$SCOPE],
 "preAuthorizedApplications": [{"appId": "$AZ_CLI", "delegatedPermissionIds": ["$SCOPE_ID"]}]}}
JSON
az rest --method PATCH --uri "$GRAPH/applications(appId='$APP_ID')" --headers Content-Type=application/json --body @/tmp/api-app.json

# 2. Only people with the Loan.Read role can get a token: you and the team
SP_ID=$(az ad sp create --id $APP_ID --query id -o tsv)
az rest --method PATCH --uri "$GRAPH/servicePrincipals/$SP_ID" --headers Content-Type=application/json \
  --body '{"appRoleAssignmentRequired": true}'
for U in $TEAM; do                        # TEAM includes you
  OID=$(az ad user show --id "$U" --query id -o tsv)
  az rest --method POST --uri "$GRAPH/servicePrincipals/$SP_ID/appRoleAssignedTo" --headers Content-Type=application/json \
    --body '{"principalId": "'$OID'", "resourceId": "'$SP_ID'", "appRoleId": "'$ROLE_ID'"}'
  echo "Loan.Read: $U"
done

# 3. Tell prod which tenant and audience to accept
az containerapp update -g $RG -n ca-loant2gk-prod --set-env-vars AUTH_TENANT_ID=$TENANT AUTH_AUDIENCE=$APP_ID
echo "AUTH_TENANT_ID=$TENANT"
echo "AUTH_AUDIENCE=$APP_ID"

# 4. Addresses the frontend may sign in from (the "Sign in with Microsoft" button, MSAL.js)
PROD_URL=https://$(az containerapp show -g $RG -n ca-loant2gk-prod --query properties.configuration.ingress.fqdn -o tsv)/
DEV_URL=https://$(az containerapp show -g $RG -n ca-loant2gk-dev --query properties.configuration.ingress.fqdn -o tsv)/
az rest --method PATCH --uri "$GRAPH/applications(appId='$APP_ID')" --headers Content-Type=application/json \
  --body '{"spa":{"redirectUris":["'$PROD_URL'","'$DEV_URL'","http://localhost:8000/"]}}'
