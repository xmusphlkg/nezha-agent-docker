# CTM Monitor

Lightweight infrastructure monitor for the internal network. It presents compact
sub-panels for Zabbix hosts and optional PVE VM/CT resources.

Runtime state is stored in the configured MySQL host. The app runs with
host networking and creates a small `ctm_console_cache` KV table in the `dashboard`
database for snapshots and short series cache.

## Run on 8088

Prepare MySQL for your configured `MYSQL_*` values so the API container can connect to it locally:

```sql
GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, INDEX, ALTER
  ON dashboard.* TO 'dashboard'@'localhost';
GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, INDEX, ALTER
  ON dashboard.* TO 'dashboard'@'127.0.0.1';
```

```bash
cp .env.example .env
chmod 600 .env
docker compose up -d --build
```

Open `${PUBLIC_BASE_URL}` after editing `.env` (default is `http://127.0.0.1:8088`).

Required `.env` fields:

- `ZABBIX_TOKEN`
- `MYSQL_HOST`
- `MYSQL_PORT`
- `MYSQL_USER`
- `MYSQL_PASSWORD`
- `MYSQL_DATABASE`
- `CTM_ADMIN_PASSWORD`
- `CTM_SESSION_SECRET`

Navigation/login fields:

- `CTM_ADMIN_USERNAME=admin`
- `CTM_ADMIN_PASSWORD`
- `CTM_SESSION_SECRET`
- `CTM_SESSION_TTL_HOURS=12`
- `NAV_SCAN_CIDRS=192.168.3.0/24`
- `NAV_SCAN_PORTS=80,443,3000,3001,5000,5001,5173,5601,8000,8006,8080,8081,8088,8090,8443,8888,9000,9001,9090,9091,9093,9200,9443`
- `VITE_NAV_SCAN_CIDRS_DEFAULT=192.168.3.0/24`
- `VITE_NAV_SCAN_CIDRS_PLACEHOLDER=192.168.3.0/24, 192.168.10.0/24`

The first startup creates the initial admin user if `ctm_nav_users` is empty.
Keep the admin password and session secret only in `.env`.
Default navigation links and initial candidates are seeded only when their tables
are empty; restarts and upgrades do not restore deleted links or overwrite edits.
Admins can override the default scan range from the navigation management page.
The scan input accepts one or more CIDR ranges separated by commas, spaces, or newlines.
When adding a navigation link, admins can enter a URL and let the console probe
the page to prefill title, category, description, tags, and icon. Icons are stored
as semantic names such as `grafana`, `prometheus`, `router`, `chat`, and `web`.

Optional PVE fields:

- `PVE_HOST`
- `PVE_PORT`
- `PVE_NAME`
- `PVE_TOKEN_ID`
- `PVE_TOKEN_SECRET`
- `PVE_VERIFY_SSL`

For multiple PVE clusters, set `PVE_SERVERS_JSON` to a JSON array of objects with
`name`, `host`, `port`, `token_id`, `token_secret`, and `verify_ssl`.

Optional Wazuh fields:

- `CTM_WAZUH_ENABLED=true`
- `CTM_WAZUH_MODULES=agents,alerts,ssh,fim`
- `CTM_WAZUH_WINDOW=24h`
- `CTM_WAZUH_TOP_LIMIT=8`
- `CTM_WAZUH_RECENT_LIMIT=12`

`CTM_WAZUH_MODULES` is selective. Use values such as `agents,ssh` or `alerts,fim`
when the console should only read part of the Wazuh exporter metrics from Prometheus.

Optional Grafana integration field:

- `GRAFANA_BASE_URL=http://127.0.0.1:3000`
- `GRAFANA_ORG_ID=1`
- `GRAFANA_DEFAULT_FROM=now-6h`
- `GRAFANA_DEFAULT_TO=now`
- `GRAFANA_TIMEZONE=browser`
- `GRAFANA_REFRESH=30s`

The console uses this base URL to build deep links into the existing Grafana
dashboards, including machine drilldown links to `ctm-server-trends`.

## Runtime Access

The production deployment can serve CTM Console directly on its app port, or
behind nginx under `/console/` when intermediate network equipment blocks custom
ports. Grafana is kept as an external system through `GRAFANA_BASE_URL`, so the
console port and Grafana port do not need to compete with each other.

```bash
sed -i 's/CTM_CONSOLE_PORT=8088/CTM_CONSOLE_PORT=3030/' .env
sed -i 's#PUBLIC_BASE_URL=http://127.0.0.1:8088#PUBLIC_BASE_URL=http://192.168.3.222/console#' .env
echo 'VITE_API_PROXY=http://127.0.0.1:8088' >> .env
echo 'VITE_BASE_PATH=/console/' >> .env
docker compose up -d
```

## Interfaces

- `GET /healthz`
- `POST /api/auth/login`
- `POST /api/auth/logout`
- `GET /api/auth/me`
- `GET /api/auth/users`
- `POST /api/auth/users`
- `PATCH /api/auth/users/{id}`
- `GET /api/nav/links`
- `POST /api/nav/links`
- `POST /api/nav/links/preview`
- `GET /api/nav/links/{id}`
- `PATCH /api/nav/links/{id}`
- `DELETE /api/nav/links/{id}`
- `PATCH /api/nav/links/reorder`
- `POST /api/nav/discovery/scan`
- `GET /api/nav/discovery/runs/{run_id}`
- `GET /api/nav/discovery/candidates`
- `POST /api/nav/discovery/candidates/{id}/import`
- `PATCH /api/nav/discovery/candidates/{id}`
- `GET /api/overview`
- `GET /api/machines`
- `GET /api/machines/{machine_id}`
- `GET /api/machines/{machine_id}/series?range=1h|6h|24h`
- `GET /api/network/devices`
- `GET /api/tailnet`
- `GET /api/services`
- `GET /api/pve`
- `GET /api/wazuh`
- `GET /api/grafana`
- `GET /api/alerts`
- `GET /api/diagnostics`
