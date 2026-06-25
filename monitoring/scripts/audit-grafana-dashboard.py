#!/usr/bin/env python3
"""Audit the CTM Grafana dashboard against live Prometheus and Zabbix datasources."""

from __future__ import annotations

import argparse
import base64
import copy
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from collections import Counter
from typing import Any


DEFAULT_EMPTY_OK_TITLES = {
    "Prometheus Down Targets",
    "Blackbox 失败明细",
    "失败探测",
    "失败探测优先看",
    "温度趋势",
}

SUBSTITUTION_OVERRIDES: dict[str, str] = {}
ZABBIX_FROM_TIME = "now-6h"
ZABBIX_TO_TIME = "now"


def http_json(url: str, *, auth: str | None = None, data: dict[str, Any] | None = None) -> Any:
    headers = {"Content-Type": "application/json"}
    if auth:
        headers["Authorization"] = auth
    body = json.dumps(data).encode() if data is not None else None
    request = urllib.request.Request(url, data=body, headers=headers)
    with urllib.request.urlopen(request, timeout=25) as response:
        return json.load(response)


def substitute_query(query: str, start: int, end: int) -> str:
    replacements = {
        "$tailnet_user": ".*",
        "$tailnet_node": ".*",
        "$zbx_group": "/.*/",
        "$zbx_host": "/.*/",
        "$machine": ".*",
        "$zbx_iface_type": ".*",
        "$zbx_plugin_group": "/.*/",
        "$zbx_plugin_host": "/.*/",
        "$bb_zbx_group": ".*",
        "$bb_zbx_host": ".*",
        "$bb_iface_type": ".*",
        "${tailnet_user:regex}": ".*",
        "${tailnet_node:regex}": ".*",
        "${zbx_group:regex}": ".*",
        "${zbx_host:regex}": ".*",
        "${machine:regex}": ".*",
        "${zbx_iface_type:regex}": ".*",
        "${zbx_plugin_group:regex}": ".*",
        "${zbx_plugin_host:regex}": ".*",
        "${bb_zbx_group:regex}": ".*",
        "${bb_zbx_host:regex}": ".*",
        "${bb_iface_type:regex}": ".*",
        "$__rate_interval": "5m",
    }
    replacements.update(SUBSTITUTION_OVERRIDES)
    for source, replacement in replacements.items():
        query = query.replace(source, replacement)
    return re.sub(
        r"\$__unixEpochFilter\(([^)]+)\)",
        lambda match: f"{match.group(1)} BETWEEN {start} AND {end}",
        query,
    )


def substitute_json(value: Any) -> Any:
    if isinstance(value, str):
        return substitute_query(value, int(time.time()) - 6 * 3600, int(time.time()))
    if isinstance(value, list):
        return [substitute_json(item) for item in value]
    if isinstance(value, dict):
        return {key: substitute_json(item) for key, item in value.items()}
    return value


def query_prometheus(prometheus_url: str, expr: str) -> tuple[str, str, int]:
    url = prometheus_url.rstrip("/") + "/api/v1/query?" + urllib.parse.urlencode({"query": expr})
    try:
        payload = http_json(url)
    except Exception as error:  # noqa: BLE001
        return "ERR", str(error), 0
    if payload.get("status") != "success":
        return "ERR", payload.get("error", "unknown Prometheus error"), 0
    return "OK", "", len(payload.get("data", {}).get("result", []))


def query_zabbix(grafana_url: str, auth: str, target: dict[str, Any]) -> tuple[str, str, int]:
    query = substitute_json(copy.deepcopy(target))
    payload = {
        "queries": [query],
        "from": ZABBIX_FROM_TIME,
        "to": ZABBIX_TO_TIME,
    }
    try:
        response = http_json(grafana_url.rstrip("/") + "/api/ds/query", auth=auth, data=payload)
    except Exception as error:  # noqa: BLE001
        return "ERR", str(error), 0
    result = response.get("results", {}).get(query.get("refId", "A"), {})
    if result.get("status") != 200:
        return "ERR", result.get("error", "unknown Zabbix datasource error"), 0
    frames = result.get("frames") or []
    points = 0
    for frame in frames:
        values = frame.get("data", {}).get("values", [])
        if values and isinstance(values[0], list):
            points += len(values[0])
    return "OK", "", points


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--grafana-url", default="http://192.168.30.91:30037")
    parser.add_argument("--prometheus-url", default="http://192.168.3.222:9090")
    parser.add_argument("--dashboard-uid", default="ctm-unified-infra")
    parser.add_argument("--user", default="admin")
    parser.add_argument("--password", required=True)
    parser.add_argument("--from-time", default="now-6h")
    parser.add_argument("--to-time", default="now")
    parser.add_argument("--zbx-group-filter", default="/.*/")
    parser.add_argument("--zbx-host-filter", default="/.*/")
    args = parser.parse_args()

    global ZABBIX_FROM_TIME, ZABBIX_TO_TIME
    ZABBIX_FROM_TIME = args.from_time
    ZABBIX_TO_TIME = args.to_time
    SUBSTITUTION_OVERRIDES.update(
        {
            "$zbx_group": args.zbx_group_filter,
            "$zbx_host": args.zbx_host_filter,
            "$zbx_plugin_group": args.zbx_group_filter,
            "$zbx_plugin_host": args.zbx_host_filter,
        }
    )

    auth = "Basic " + base64.b64encode(f"{args.user}:{args.password}".encode()).decode()
    dashboard_payload = http_json(
        f"{args.grafana_url.rstrip('/')}/api/dashboards/uid/{args.dashboard_uid}",
        auth=auth,
    )
    dashboard = dashboard_payload["dashboard"]
    start = int(time.time()) - 6 * 3600
    end = int(time.time())

    findings: list[tuple[str, int, str, int, str, str]] = []
    summary: Counter[tuple[str, str]] = Counter()
    audited = 0
    for panel in dashboard.get("panels", []):
        if panel.get("type") == "row":
            continue
        title = panel.get("title", "")
        panel_id = panel.get("id", 0)
        for target in panel.get("targets", []):
            datasource = target.get("datasource") or panel.get("datasource") or {}
            datasource_type = datasource.get("type", "")
            if datasource_type == "prometheus" and target.get("expr"):
                status, error, rows = query_prometheus(
                    args.prometheus_url,
                    substitute_query(target["expr"], start, end),
                )
            elif datasource_type == "mysql":
                status, error, rows = "ERR", "MySQL datasource remains in dashboard", 0
            elif (
                datasource_type == "alexanderzobnin-zabbix-datasource"
                and target.get("queryType") == "0"
                and target.get("resultFormat") == "time_series"
            ):
                status, error, rows = query_zabbix(args.grafana_url, auth, target)
            else:
                continue
            audited += 1
            summary[(status, datasource_type)] += 1
            if status != "OK" or (rows == 0 and title not in DEFAULT_EMPTY_OK_TITLES):
                findings.append((status, rows, datasource_type, panel_id, title, error))

    print(f"dashboard={dashboard.get('title')} version={dashboard.get('version')} panels={len(dashboard.get('panels', []))}")
    print(f"audited_targets={audited}")
    print(f"summary={dict(summary)}")
    if findings:
        print("findings:")
        for status, rows, datasource_type, panel_id, title, error in findings:
            print(f"- {status} rows={rows} type={datasource_type} panel={panel_id} title={title} error={error[:180]}")
        return 1
    print("findings=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
