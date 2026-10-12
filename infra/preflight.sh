#!/usr/bin/env bash
# Presentation-day check of the cloud setup:   bash infra/preflight.sh
# Keep prod and the SQL warehouse awake:       bash infra/preflight.sh --keep-warm   (Ctrl+C to stop)
RG=rg_gtgh_data_09
SCOPE=api://ea9e7159-2ca6-44b0-bc6c-fa2637d51347/access_as_user
QUESTION="What was the approval rate by branch in 2025?"
url() { echo "https://$(az containerapp show -g $RG -n ca-loant2gk-$1 --query properties.configuration.ingress.fqdn -o tsv)"; }
token() { az account get-access-token --scope "$SCOPE" --query accessToken -o tsv; }
PROD=$(url prod); DEV=$(url dev)

if [ "$1" = "--keep-warm" ]; then
  while true; do
    curl -s -o /dev/null -m 90 -w "$(date +%T) prod /ready %{http_code}\n" -H "Authorization: Bearer $(token)" "$PROD/ready"
    sleep 240
  done
fi

TOKEN=$(token)
KEY=$(az keyvault secret show --vault-name kv-loant2gk -n api-keys-dev --query value -o tsv)
FAILED=0
ok()  { echo "PASS  $1"; }
bad() { echo "FAIL  $1"; FAILED=1; }

# 1. Both apps answer, and which version each runs
for ENV in prod dev; do
  V=$(curl -s -m 60 "$(url $ENV)/health" | python3 -c "import sys,json;print(json.load(sys.stdin)['version'])" 2>/dev/null)
  [ -n "$V" ] && ok "$ENV /health (version $V)" || bad "$ENV /health"
done

# 2. Prod reaches the Gold data with a sign-in token
CODE=$(curl -s -o /dev/null -m 90 -w "%{http_code}" -H "Authorization: Bearer $TOKEN" "$PROD/ready")
[ "$CODE" = 200 ] && ok "prod /ready with a token" || bad "prod /ready with a token ($CODE)"

# 3. Prod analytics returns rows
ROWS=$(curl -s -m 90 -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"metric": "approval_rate", "group_by": "branch"}' "$PROD/analytics/query" \
  | python3 -c "import sys,json;print(len(json.load(sys.stdin)['rows']))" 2>/dev/null)
[ "${ROWS:-0}" -gt 0 ] && ok "prod analytics query ($ROWS rows)" || bad "prod analytics query"

# 4. Prod assistant answers with evidence
STATUS=$(curl -s -m 120 -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d "{\"question\": \"$QUESTION\"}" "$PROD/assistant/query" \
  | python3 -c "import sys,json;b=json.load(sys.stdin);print(b['status'] if b.get('evidence') else 'no evidence')" 2>/dev/null)
[ "$STATUS" = answered ] && ok "prod assistant answers" || bad "prod assistant (${STATUS:-no reply})"

# 5. Dev works as the backup, with the API key
CODE=$(curl -s -o /dev/null -m 90 -w "%{http_code}" -H "X-API-Key: $KEY" "$DEV/ready")
[ "$CODE" = 200 ] && ok "dev /ready with the API key (backup)" || bad "dev /ready with the API key ($CODE)"

# 6. Prod keeps a copy running (no cold start)
MIN=$(az containerapp show -g $RG -n ca-loant2gk-prod --query properties.template.scale.minReplicas -o tsv)
[ "${MIN:-0}" -ge 1 ] 2>/dev/null && ok "prod keeps $MIN copy running" || bad "prod min replicas is ${MIN:-0} (cold starts)"

[ $FAILED = 0 ] && echo "All checks passed." || { echo "Something failed, see above."; exit 1; }
