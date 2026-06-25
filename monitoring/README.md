# CTM Monitoring Dashboards

Grafana home dashboard: `http://192.168.30.91:30037/d/ctm-ops-overview`

## Deployment Status

Implemented on `192.168.3.222` on 2026-06-21:

| Component | Status |
| --- | --- |
| Grafana dashboard suite | Scenario-based dashboard suite imported; Grafana home is `ctm-ops-overview` |
| Blackbox exporter | Docker container `ctm-blackbox-exporter`, network `1panel-network` |
| Zabbix file_sd generation | `prometheus-zabbix-file-sd.timer`, every 5 minutes |
| Prometheus Blackbox jobs | `blackbox-zabbix-file-sd`, `blackbox-core-http` |
| Prometheus alert rules | `rules/ctm-alert-rules.yml`, core and Tailnet rules; `rules/ctm-wazuh-rules.yml`, Wazuh security rules |
| DingTalk notification path | Alertmanager -> `ctm-dingtalk-relay` prepared; fill the DingTalk robot webhook before enabling |

Remote deployment paths:

| Path | Purpose |
| --- | --- |
| `/usr/local/sbin/generate-zabbix-blackbox-file-sd.py` | Reads Zabbix DB and writes file_sd JSON |
| `/etc/ctm-monitoring/zabbix-file-sd.env` | Root-only Zabbix DB credentials |
| `/opt/1panel/apps/prometheus/prometheus/conf/file_sd/` | Prometheus file_sd target files |
| `/opt/1panel/apps/prometheus/prometheus/conf/rules/ctm-alert-rules.yml` | Prometheus alert rules |
| `/opt/1panel/apps/prometheus/prometheus/conf/rules/ctm-wazuh-rules.yml` | Prometheus Wazuh alert rules |
| `/etc/alertmanager/alertmanager.yml` | Alertmanager route to the local DingTalk relay |
| `/etc/ctm-monitoring/dingtalk-relay.env` | Root-only DingTalk robot webhook and optional signature secret |
| `/etc/ctm-monitoring/tailnet-watch.env` | Tailnet watcher settings for new-device notifications |
| `/usr/local/sbin/ctm-dingtalk-relay.py` | Converts Alertmanager webhook payloads to DingTalk robot markdown messages |
| `/usr/local/sbin/ctm-tailnet-watch.py` | Detects newly added Headscale/Tailscale devices and posts to the DingTalk relay |
| `/opt/ctm-monitoring/blackbox.yml` | Blackbox exporter modules |

## Current Discovery

The monitoring stack is reachable on `192.168.3.222`:

| Component | Endpoint | Status |
| --- | --- | --- |
| Grafana | `192.168.30.91:30037` | existing runtime used by CTM Console deep links |
| Prometheus | `:9090` | ready |
| Zabbix | `:8080` | API version 7.2.12 |

Prometheus initially had 3 active scrape targets:

| Job | Instance | Status |
| --- | --- | --- |
| `prometheus` | `localhost:9090` | up |
| `headscale` | `metrics.rdp.monitor.ctmodelling.cn` | up |
| `headscale_exporter` | `metrics.rdp.monitor.ctmodelling.cn` | up |

Headscale/Tailnet data currently visible in Prometheus:

| Metric | Current value |
| --- | --- |
| Tailnet nodes | 11 |
| Online nodes | 10 |
| Offline nodes | 1 |
| Headscale API | up |
| Headscale database connectivity | healthy |
| PreAuth keys expiring within 7 days | 3 |
| Available routes not yet approved | 3 |

Zabbix guest login works, but guest has no API permission for `host.get` or `problem.get`. The existing Grafana Zabbix datasource is therefore kept on its current token-based configuration.

Current automatic discovery coverage:

| Source | Active targets |
| --- | --- |
| Zabbix Blackbox ICMP | 24 |
| Core HTTP Blackbox | 3 |
| Headscale/Tailnet nodes | 11 |
| WatchYourLAN LAN discovery | 1 exporter |

## Dashboard Suite

The dashboard set is split into one operational home page and detail dashboards:

| Dashboard | UID | Purpose |
| --- | --- | --- |
| CTM Main | `ctm-ops-overview` | Operational home page: Zabbix unresolved problems, Tailnet key state, and a current server health table for CPU, memory, summed non-docker network throughput, summed disk usage, and health |
| CTM 设备健康 | `ctm-zabbix-operations` | Device and hardware health: agent/ICMP, CPU, memory, CPU temperature, current problems, hardware values, text inventory |
| CTM 资源容量 | `ctm-zabbix-resources` | Capacity and performance: CPU, memory, filesystem, ICMP, and temperature trends |
| CTM 服务器趋势 | `ctm-server-trends` | Drilldown opened from CTM Main server names: CPU, memory, network, disk, health, and temperature trends for the selected host |
| CTM 远程网络 | `ctm-tailnet-headscale` | Remote-access scenario: Headscale API/DB, Tailnet online state, routes, keys, NodeStore latency, last-seen data |
| CTM 服务可达 | `ctm-service-blackbox` | Service reachability: Prometheus target health, Blackbox success rate, failed probes, scrape duration, core HTTP checks |
| CTM 局域网资产 | `ctm-lan-assets` | LAN discovery view from WatchYourLAN: online devices, unknown online devices, interfaces, and asset inventory |
| CTM 告警安全 | `ctm-alerts-security` | Incident and security scenario: Zabbix events, Grafana alerts, stale nodes, Tailnet key inventory, route approvals |
| CTM 全量排障 | `ctm-unified-infra` | Cross-domain drilldown ordered by response workflow, not the old panel dump |

All Grafana panels that display Zabbix data use `alexanderzobnin-zabbix-datasource`. The dashboard intentionally no longer uses MySQL or raw SQL for Zabbix panels. Prometheus is still used for Headscale, Blackbox, and alerting signals.

Dashboard variables:

| Variable | Source | Purpose |
| --- | --- | --- |
| `tailnet_user` | `headscale_nodes_online` | Filter Tailnet owner/user |
| `tailnet_node` | `headscale_nodes_online` | Filter Tailnet node |
| `zbx_group` | Zabbix plugin | Filter Zabbix API panels by group |
| `zbx_host` | Zabbix plugin | Filter Zabbix API panels by host |
| `bb_zbx_group` | `probe_success` labels | Filter Blackbox Zabbix probes by generated Zabbix group label |
| `bb_zbx_host` | `probe_success` labels | Filter Blackbox Zabbix probes by generated Zabbix host label |
| `bb_iface_type` | `probe_success` labels | Filter Blackbox Zabbix probes by interface type |

## Files

| File | Purpose |
| --- | --- |
| `grafana/dashboards/ctm-ops-overview.json` | CTM Main operational home dashboard |
| `grafana/dashboards/ctm-zabbix-operations.json` | Device health dashboard |
| `grafana/dashboards/ctm-zabbix-resources.json` | Resource capacity dashboard |
| `grafana/dashboards/ctm-server-trends.json` | Per-server trend drilldown dashboard linked from CTM Main |
| `grafana/dashboards/ctm-tailnet-headscale.json` | Remote network dashboard |
| `grafana/dashboards/ctm-service-blackbox.json` | Service reachability dashboard |
| `grafana/dashboards/ctm-lan-assets.json` | WatchYourLAN LAN asset dashboard |
| `grafana/dashboards/ctm-alerts-security.json` | Alerts and security dashboard |
| `grafana/dashboards/ctm-unified-infra.json` | Full drilldown dashboard |
| `grafana/provisioning/datasources/datasources.yml` | Datasource provisioning template |
| `prometheus/scrape-extra.yml` | Additional scrape jobs for Blackbox, WatchYourLAN, SNMP, IPMI |
| `prometheus/ctm-alert-rules.yml` | Prometheus alert rules for core infrastructure and selected Tailnet signals |
| `prometheus/ctm-wazuh-rules.yml` | Prometheus alert rules for Wazuh API, agents, alerts, SSH, and FIM signals |
| `prometheus/alertmanager-extra.yml` | Prometheus `rule_files` and `alerting` snippet for Alertmanager integration |
| `alertmanager/alertmanager.yml` | Alertmanager receiver and routing example for DingTalk |
| `examples/dingtalk-relay.env.example` | DingTalk relay environment template; copy to `/etc/ctm-monitoring/dingtalk-relay.env` |
| `examples/tailnet-watch.env.example` | Tailnet watcher environment template; copy to `/etc/ctm-monitoring/tailnet-watch.env` |
| `scripts/ctm-dingtalk-relay.py` | Alertmanager-to-DingTalk webhook relay |
| `scripts/ctm-tailnet-watch.py` | New Tailnet device watcher |
| `scripts/install-dingtalk-alerting.sh` | Installs the relay script, env template, and systemd service |
| `scripts/import-grafana-dashboard.sh` | Idempotent dashboard import script |
| `scripts/import-all-grafana-dashboards.sh` | Imports the complete CTM dashboard suite and can set Grafana home |
| `scripts/generate-zabbix-blackbox-file-sd.py` | Zabbix-to-Prometheus file_sd generator |
| `scripts/audit-grafana-dashboard.py` | Live dashboard query auditor |
| `systemd/prometheus-zabbix-file-sd.service` | One-shot file_sd refresh service |
| `systemd/prometheus-zabbix-file-sd.timer` | 5-minute auto-refresh timer |
| `systemd/ctm-tailnet-watch.service` | One-shot Tailnet device watcher |
| `systemd/ctm-tailnet-watch.timer` | 5-minute Tailnet watcher timer |
| `prometheus/blackbox.yml` | Blackbox exporter modules |

## WatchYourLAN LAN Assets

WatchYourLAN is consumed as a Prometheus exporter, not as a Zabbix host source.
The active scrape job is in `prometheus/scrape-extra.yml`:

```yaml
- job_name: watchyourlan
  scrape_interval: 60s
  static_configs:
    - targets:
        - 192.168.30.185:8840
      labels:
        area: lan
        role: asset-discovery
```

After merging the job into the active Prometheus config, reload Prometheus and
import `grafana/dashboards/ctm-lan-assets.json`. No WatchYourLAN alert rules are
defined; LAN data is used for inventory and visibility only.

## DingTalk Alerting

Wazuh alert data is already collected as Prometheus metrics. DingTalk is used as
a security notification channel, not as a general device online/offline channel.
Zabbix remains responsible for normal device availability notifications.

Notifications use this path:

```text
Wazuh exporter -> Prometheus rules -> Alertmanager -> ctm-dingtalk-relay -> DingTalk robot
Headscale metrics -> Prometheus rules -> Alertmanager -> ctm-dingtalk-relay -> DingTalk robot
ctm-tailnet-watch -> ctm-dingtalk-relay -> DingTalk robot
```

The relay is needed because Alertmanager's webhook payload is not the same JSON
shape expected by a DingTalk group robot. The relay also supports DingTalk
signature validation.

Alertmanager routes `area="wazuh"` security alerts, selected `area="tailscale"`
reminders, and critical `area="headscale"` health alerts to DingTalk. This keeps
noisy infrastructure and availability alerts, such as Tailnet node offline or
Blackbox/Zabbix-style reachability events, out of the DingTalk group. The
security and reminder notification set focuses on:

- SSH root login, active root sessions, invalid users, and failure bursts,
- key file additions, modifications, deletions, and FIM queue health,
- critical/high Wazuh security alerts,
- critical Wazuh API/indexer/manager process failures that would blind security monitoring.
- new Tailnet devices detected from `headscale_nodes_info`,
- new Headscale preauth keys detected from `headscale_preauthkeys_info`,
- Headscale exporter/database failures that would blind Tailnet monitoring,
- Tailnet route advertisements awaiting approval.

The Tailnet watcher keeps its baseline in
`/var/lib/ctm-monitoring/tailnet-watch.json`. The first run records the current
device/key set without notifying; later runs notify only when a device or
preauth key appears that was not in the previous baseline.

Install the relay:

```bash
sudo monitoring/scripts/install-dingtalk-alerting.sh
sudo monitoring/scripts/install-dingtalk-alerting.sh --configure
sudo systemctl enable --now ctm-dingtalk-relay
curl -s http://127.0.0.1:8066/healthz
```

Keep the DingTalk webhook only in `/etc/ctm-monitoring/dingtalk-relay.env`.
Set `DINGTALK_SECRET` only if the DingTalk robot has signature validation
enabled. Keep `DINGTALK_KEYWORD=CTM` if the robot uses keyword validation.
For non-interactive deployment, the installer also accepts `DINGTALK_WEBHOOK`
and `DINGTALK_SECRET` from the environment.

Load both rule files into Prometheus and connect Prometheus to Alertmanager. The
merge snippet is in `prometheus/alertmanager-extra.yml`:

```yaml
rule_files:
  - /etc/prometheus/rules/ctm-alert-rules.yml
  - /etc/prometheus/rules/ctm-wazuh-rules.yml

alerting:
  alertmanagers:
    - static_configs:
        - targets:
            - 127.0.0.1:9093
```

Copy `alertmanager/alertmanager.yml` to the active Alertmanager configuration
path. If Alertmanager runs in Docker without host networking, replace
`http://127.0.0.1:8066/alertmanager` with an address that can reach the host
relay.

Useful checks:

```bash
curl -s http://127.0.0.1:9090/api/v1/rules | jq '.data.groups[] | select(.name=="ctm-wazuh")'
curl -s http://127.0.0.1:9090/api/v1/alerts | jq '.data.alerts[] | select(.labels.area=="wazuh")'
curl -sG http://127.0.0.1:9090/api/v1/query --data-urlencode 'query=sum(ctm_wazuh_alerts_total{window="15m"}) by (severity)'
```

## Validation

Run the live dashboard auditor after changing CTM Main. Use the short Main time window so the high-cardinality Zabbix network and disk items are not queried as long history:

```bash
monitoring/scripts/audit-grafana-dashboard.py \
  --grafana-url http://192.168.30.91:30037 \
  --dashboard-uid ctm-ops-overview \
  --from-time now-5m \
  --password '<grafana-admin-password>'
```

For the per-server trend drilldown, audit one host at a time:

```bash
monitoring/scripts/audit-grafana-dashboard.py \
  --grafana-url http://192.168.30.91:30037 \
  --dashboard-uid ctm-server-trends \
  --from-time now-1h \
  --zbx-host-filter '监控' \
  --password '<grafana-admin-password>'
```

Expected current result:

| Check | Expected |
| --- | --- |
| Grafana home dashboard | `ctm-ops-overview` |
| Imported dashboards | 8 |
| Findings | 0 |
| MySQL/raw SQL in dashboard | 0 |
| Prometheus targets | 30 active, 30 up |
| Blackbox Zabbix probes | 24/24 successful |
| Blackbox core HTTP probes | 3/3 successful |

To import all dashboards:

```bash
GRAFANA_USER='admin' GRAFANA_PASSWORD='<grafana-admin-password>' \
  GRAFANA_URL='http://192.168.30.91:30037' \
  SET_GRAFANA_HOME=1 \
  monitoring/scripts/import-all-grafana-dashboards.sh
```

## Coverage Roadmap

### Phase 1: Already Active

- Prometheus self-monitoring.
- Headscale server metrics.
- Headscale/Tailnet exporter metrics.
- Existing Grafana Zabbix datasource and Zabbix dashboards.

### Phase 2: Network and Hardware Coverage

Use `snmp_exporter` for switches, routers, NAS, and UPS devices. Use `ipmi_exporter` for physical servers with BMC/IPMI.

Populate the empty `targets` lists in:

- `snmp-network`
- `ipmi-physical`

### Phase 3: Container Coverage

Container-level metrics are intentionally deferred. If needed later, install cAdvisor on Docker hosts and add cAdvisor scrape jobs.

### Phase 4: Alerts and Runbooks

Load `prometheus/ctm-alert-rules.yml` into Prometheus rule files, then connect Alertmanager or Grafana Alerting notifications.

Initial alert priorities:

| Alert | Severity |
| --- | --- |
| Headscale exporter down | critical |
| Headscale database unhealthy | critical |
| Tailnet node offline | warning |
| Prometheus target down | warning |
| Blackbox probe failed | warning |
| Host CPU/memory/disk pressure | warning |
| Headscale routes awaiting approval | info |
