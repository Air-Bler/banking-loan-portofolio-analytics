#!/usr/bin/env bash
# Step 9: save the queries in infra/monitoring/ to Log Analytics so they appear in the Azure portal.
# Run again after changing a query: bash infra/monitoring_setup.sh
export AZURE_CORE_OUTPUT=none
RG=rg_gtgh_data_09
WS=workspace-rggtghdata09wtuo
for F in infra/monitoring/*.kql; do
  NAME=$(basename "$F" .kql)
  az monitor log-analytics workspace saved-search create -g $RG --workspace-name $WS -n "team2-$NAME" \
    --category "Team 2 API" --display-name "$NAME" --saved-query "$(cat "$F")"
  echo "saved $NAME"
done
