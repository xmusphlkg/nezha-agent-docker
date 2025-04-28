#!/bin/sh

# Default values or skip setting if not provided
CLIENT_SECRET=${CLIENT_SECRET:-""}
SERVER=${SERVER:-""}

# Check for required environment variables
if [ -z "$CLIENT_SECRET" ] || [ -z "$SERVER" ]; then
  echo "CLIENT_SECRET or SERVER not provided. Configuration will be set at runtime."
fi  # Closing the if statement

# Generate UUID if not provided
if command -v uuidgen >/dev/null 2>&1; then
  UUID=${UUID:-$(uuidgen)}
else
  echo "uuidgen not found, using fallback method to generate UUID."
  UUID=${UUID:-$(cat /proc/sys/kernel/random/uuid 2>/dev/null || openssl rand -hex 16 | sed 's/^\(.\{8\}\)\(.\{4\}\)\(.\{4\}\)\(.\{4\}\)\(.\{12\}\)$/\1-\2-\3-\4-\5/') }
fi

# Print UUID
echo "Your UUID: $UUID"

# Create config.yml with the provided or default settings
cat <<EOF > /usr/local/bin/nezha/config.yml
client_secret: $CLIENT_SECRET
debug: ${DEBUG:-true}
disable_auto_update: ${DISABLE_AUTO_UPDATE:-true}
disable_command_execute: ${DISABLE_COMMAND_EXECUTE:-false}
disable_force_update: ${DISABLE_FORCE_UPDATE:-true}
disable_nat: ${DISABLE_NAT:-false}
disable_send_query: ${DISABLE_SEND_QUERY:-false}
gpu: ${GPU:-false}
insecure_tls: ${INSECURE_TLS:-false}
ip_report_period: ${IP_REPORT_PERIOD:-1800}
report_delay: ${REPORT_DELAY:-3}
self_update_period: ${SELF_UPDATE_PERIOD:-0}
server: $SERVER
skip_connection_count: ${SKIP_CONNECTION_COUNT:-false}
skip_procs_count: ${SKIP_PROCS_COUNT:-false}
temperature: ${TEMPERATURE:-false}
tls: ${TLS:-false}
use_gitee_to_upgrade: ${USE_GITEE_TO_UPGRADE:-false}
use_ipv6_country_code: ${USE_IPV6_COUNTRY_CODE:-false}
uuid: $UUID
EOF

echo "Config setup completed."

