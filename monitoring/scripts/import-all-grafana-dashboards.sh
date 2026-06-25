#!/usr/bin/env bash
set -euo pipefail

GRAFANA_URL="${GRAFANA_URL:-http://192.168.30.91:30037}"
DASHBOARD_DIR="${DASHBOARD_DIR:-$(dirname "$0")/../grafana/dashboards}"
SET_GRAFANA_HOME="${SET_GRAFANA_HOME:-0}"
HOME_DASHBOARD_UID="${HOME_DASHBOARD_UID:-ctm-ops-overview}"

dashboards=(
  ctm-ops-overview.json
  ctm-zabbix-operations.json
  ctm-zabbix-resources.json
  ctm-server-trends.json
  ctm-tailnet-headscale.json
  ctm-service-blackbox.json
  ctm-lan-assets.json
  ctm-alerts-security.json
  ctm-wazuh-security.json
  ctm-wazuh-ssh.json
  ctm-wazuh-fim.json
  ctm-unified-infra.json
)

for dashboard in "${dashboards[@]}"; do
  DASHBOARD_FILE="${DASHBOARD_DIR}/${dashboard}" "$(dirname "$0")/import-grafana-dashboard.sh"
done

if [ "$SET_GRAFANA_HOME" = "1" ]; then
  auth_args=()
  if [ -n "${GRAFANA_TOKEN:-}" ]; then
    auth_args=(-H "Authorization: Bearer ${GRAFANA_TOKEN}")
  elif [ -n "${GRAFANA_USER:-}" ] && [ -n "${GRAFANA_PASSWORD:-}" ]; then
    auth_args=(-u "${GRAFANA_USER}:${GRAFANA_PASSWORD}")
  else
    echo "Set GRAFANA_TOKEN or GRAFANA_USER/GRAFANA_PASSWORD before setting Grafana home." >&2
    exit 1
  fi

  home_id="$(
    curl -fsS "${auth_args[@]}" "${GRAFANA_URL%/}/api/dashboards/uid/${HOME_DASHBOARD_UID}" |
      jq -r '.dashboard.id'
  )"
  prefs="$(
    curl -fsS "${auth_args[@]}" "${GRAFANA_URL%/}/api/org/preferences" |
      jq --argjson homeDashboardId "$home_id" '. + {homeDashboardId: $homeDashboardId}'
  )"
  curl -fsS \
    "${auth_args[@]}" \
    -H "Content-Type: application/json" \
    -X PUT \
    --data "$prefs" \
    "${GRAFANA_URL%/}/api/org/preferences"
  echo
fi
