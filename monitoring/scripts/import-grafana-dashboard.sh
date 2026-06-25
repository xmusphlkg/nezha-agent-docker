#!/usr/bin/env bash
set -euo pipefail

GRAFANA_URL="${GRAFANA_URL:-http://192.168.30.91:30037}"
DASHBOARD_FILE="${DASHBOARD_FILE:-$(dirname "$0")/../grafana/dashboards/ctm-unified-infra.json}"

if ! command -v jq >/dev/null 2>&1; then
  echo "jq is required" >&2
  exit 1
fi

if [ ! -f "$DASHBOARD_FILE" ]; then
  echo "dashboard file not found: $DASHBOARD_FILE" >&2
  exit 1
fi

auth_args=()
if [ -n "${GRAFANA_TOKEN:-}" ]; then
  auth_args=(-H "Authorization: Bearer ${GRAFANA_TOKEN}")
elif [ -n "${GRAFANA_USER:-}" ] && [ -n "${GRAFANA_PASSWORD:-}" ]; then
  auth_args=(-u "${GRAFANA_USER}:${GRAFANA_PASSWORD}")
else
  echo "Set GRAFANA_TOKEN or GRAFANA_USER/GRAFANA_PASSWORD before importing." >&2
  exit 1
fi

jq -n --slurpfile dashboard "$DASHBOARD_FILE" '
  ({
    dashboard: $dashboard[0],
    overwrite: true,
    message: "Import CTM unified infrastructure dashboard"
  } + if (env.GRAFANA_FOLDER_UID // "") == "" then {} else {folderUid: env.GRAFANA_FOLDER_UID} end)
'>/tmp/ctm-grafana-dashboard-payload.json

curl -fsS \
  "${auth_args[@]}" \
  -H "Content-Type: application/json" \
  -X POST \
  --data-binary @/tmp/ctm-grafana-dashboard-payload.json \
  "${GRAFANA_URL%/}/api/dashboards/db"

echo
