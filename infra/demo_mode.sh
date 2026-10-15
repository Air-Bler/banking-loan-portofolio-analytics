#!/usr/bin/env bash
# Demo mode: keep one replica of each app running, so the first request does
# not wait for a cold start (~20 s). Turn it off after the presentation:
# with min replicas 1 the apps are billed even when idle.
# Changing the scale creates a new revision; run the pre-flight afterwards.
#   bash infra/demo_mode.sh on       # the evening before the presentation
#   bash infra/demo_mode.sh off      # after the presentation
#   bash infra/demo_mode.sh          # show the current setting
set -euo pipefail

RG=rg_gtgh_data_09
APPS="ca-loant2gk-prod ca-loant2gk-dev"

case "${1:-status}" in
  on)     MIN=1 ;;
  off)    MIN=0 ;;
  status) MIN="" ;;
  *)      echo "usage: $0 [on|off|status]"; exit 1 ;;
esac

for APP in $APPS; do
  if [ -n "$MIN" ]; then
    az containerapp update -g "$RG" -n "$APP" --min-replicas "$MIN" -o none
  fi
  read -r LO HI < <(az containerapp show -g "$RG" -n "$APP" \
    --query "[properties.template.scale.minReplicas, properties.template.scale.maxReplicas]" -o tsv | tr '\n' ' ')
  printf '%-18s min=%s max=%s\n' "$APP" "$LO" "$HI"
done
