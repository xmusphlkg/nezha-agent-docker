#!/usr/bin/env python3
"""Expose a small Wazuh API summary as Prometheus metrics."""

from __future__ import annotations

import json
import os
import re
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


API_URL = os.environ.get("WAZUH_API_URL", "https://127.0.0.1:55000").rstrip("/")
API_USER = os.environ.get("WAZUH_API_USERNAME", "")
API_PASSWORD = os.environ.get("WAZUH_API_PASSWORD", "")
VERIFY_TLS = os.environ.get("WAZUH_VERIFY_TLS", "false").lower() in {"1", "true", "yes"}
INDEXER_URL = os.environ.get("WAZUH_INDEXER_URL", "").rstrip("/")
INDEXER_USER = os.environ.get("WAZUH_INDEXER_USERNAME", "")
INDEXER_PASSWORD = os.environ.get("WAZUH_INDEXER_PASSWORD", "")
INDEXER_INDEX = os.environ.get("WAZUH_INDEXER_ALERT_INDEX", "wazuh-alerts-*")
BIND = os.environ.get("CTM_WAZUH_EXPORTER_BIND", "127.0.0.1")
PORT = int(os.environ.get("CTM_WAZUH_EXPORTER_PORT", "9310"))
CACHE_SECONDS = int(os.environ.get("CTM_WAZUH_EXPORTER_CACHE_SECONDS", "45"))
COLLECT_INTERVAL = int(os.environ.get("CTM_WAZUH_EXPORTER_COLLECT_INTERVAL", "60"))
REQUEST_TIMEOUT = int(os.environ.get("CTM_WAZUH_EXPORTER_REQUEST_TIMEOUT", "10"))
INDEXER_TIMEOUT = int(os.environ.get("CTM_WAZUH_INDEXER_REQUEST_TIMEOUT", "12"))

ALERT_WINDOWS = tuple(item.strip() for item in os.environ.get("CTM_WAZUH_ALERT_WINDOWS", "15m,1h,24h").split(",") if item.strip())
SSH_WINDOWS = tuple(item.strip() for item in os.environ.get("CTM_WAZUH_SSH_WINDOWS", "15m,1h,24h").split(",") if item.strip())
SSH_RECENT_LIMIT = int(os.environ.get("CTM_WAZUH_SSH_RECENT_LIMIT", "12"))
SSH_SESSION_LOOKBACK = os.environ.get("CTM_WAZUH_SSH_SESSION_LOOKBACK", "7d")
SSH_SESSION_LIMIT = int(os.environ.get("CTM_WAZUH_SSH_SESSION_LIMIT", "5000"))
FIM_WINDOWS = tuple(item.strip() for item in os.environ.get("CTM_WAZUH_FIM_WINDOWS", "15m,1h,24h").split(",") if item.strip())
FIM_RECENT_LIMIT = int(os.environ.get("CTM_WAZUH_FIM_RECENT_LIMIT", "12"))
FIM_KEY_PATHS = tuple(
    item.strip()
    for item in os.environ.get(
        "CTM_WAZUH_FIM_KEY_PATHS",
        "/etc/passwd,/etc/shadow,/etc/group,/etc/gshadow,/etc/sudoers,/etc/sudoers.d/*,/etc/ssh/*,/root/.ssh/*,/home/*/.ssh/*,/etc/pam.d/*,/etc/security/*,/etc/crontab,/etc/cron.d/*,/etc/cron.daily/*,/etc/cron.hourly/*,/etc/cron.weekly/*,/etc/cron.monthly/*,/var/spool/cron/*,/etc/systemd/system/*,/lib/systemd/system/*,/usr/lib/systemd/system/*,/etc/wazuh/*,/var/ossec/etc/*,/boot/*",
    ).split(",")
    if item.strip()
)

CRITICAL_PROCESSES = {
    "wazuh-analysisd",
    "wazuh-authd",
    "wazuh-db",
    "wazuh-execd",
    "wazuh-logcollector",
    "wazuh-modulesd",
    "wazuh-monitord",
    "wazuh-remoted",
    "wazuh-syscheckd",
    "wazuh-apid",
}

_cache: tuple[float, str] | None = None
_cache_lock = threading.Lock()
_SSHD_PID_RE = re.compile(r"\bsshd\[(\d+)\]:")
_SSHD_SESSION_USER_RE = re.compile(r"session (?:opened|closed) for user ([^\s(]+)")
_SSHD_ACCEPTED_RE = re.compile(r"Accepted\s+(?P<method>\S+)\s+for\s+(?P<user>.+?)\s+from\s+(?P<srcip>\S+)\s+port\s+(?P<srcport>\d+)")


def _ssl_context() -> ssl.SSLContext | None:
    if VERIFY_TLS:
        return None
    return ssl._create_unverified_context()


def _request(path: str, token: str | None = None, *, basic: bool = False) -> Any:
    url = API_URL + path
    headers = {"Accept": "application/json"}
    if basic:
        auth = ("%s:%s" % (API_USER, API_PASSWORD)).encode()
        import base64

        headers["Authorization"] = "Basic " + base64.b64encode(auth).decode()
    elif token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT, context=_ssl_context()) as response:
        body = response.read().decode()
    content_type = response.headers.get("Content-Type", "")
    if "application/json" in content_type or body.startswith("{") or body.startswith("["):
        return json.loads(body)
    return body


def _indexer_request(path: str, payload: dict[str, Any]) -> Any:
    if not INDEXER_URL or not INDEXER_USER or not INDEXER_PASSWORD:
        raise RuntimeError("Wazuh indexer credentials are not configured")
    url = INDEXER_URL + path
    auth = ("%s:%s" % (INDEXER_USER, INDEXER_PASSWORD)).encode()
    import base64

    body = json.dumps(payload).encode()
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": "Basic " + base64.b64encode(auth).decode(),
    }
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=INDEXER_TIMEOUT, context=_ssl_context()) as response:
        return json.loads(response.read().decode())


def _login() -> str:
    token = _request("/security/user/authenticate?raw=true", basic=True)
    if not isinstance(token, str) or not token:
        raise RuntimeError("Wazuh API did not return an authentication token")
    return token


def _items(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    data = payload.get("data") or {}
    items = data.get("affected_items") or []
    return items if isinstance(items, list) else []


def _total(payload: Any) -> float:
    if not isinstance(payload, dict):
        return 0
    data = payload.get("data") or {}
    value = data.get("total_affected_items")
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0


def _label(value: Any) -> str:
    text = "" if value is None else str(value)
    return text.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


def _metric(name: str, value: float, labels: dict[str, Any] | None = None) -> str:
    if labels:
        label_text = ",".join('%s="%s"' % (key, _label(val)) for key, val in sorted(labels.items()))
        return f"{name}{{{label_text}}} {value}"
    return f"{name} {value}"


def _severity(level: int) -> str:
    if level >= 12:
        return "critical"
    if level >= 10:
        return "high"
    if level >= 7:
        return "medium"
    if level >= 4:
        return "low"
    return "info"


def _first_bucket_key(agg: dict[str, Any] | None) -> str:
    buckets = (agg or {}).get("buckets") or []
    if not buckets:
        return ""
    return str(buckets[0].get("key", ""))


def _ssh_outcome(source: dict[str, Any]) -> str:
    rule = source.get("rule") or {}
    groups = set(rule.get("groups") or [])
    rule_id = str(rule.get("id", ""))
    data = source.get("data") or {}
    user = data.get("dstuser") or source.get("dstuser") or ""
    if "authentication_success" in groups and user == "root":
        return "root_login"
    if rule_id == "5710":
        return "invalid_user"
    if "authentication_failed" in groups:
        return "failed"
    if "authentication_success" in groups:
        return "success"
    return "other"


def _fim_key_path_filter() -> dict[str, Any]:
    return {
        "bool": {
            "should": [{"wildcard": {"syscheck.path": pattern}} for pattern in FIM_KEY_PATHS],
            "minimum_should_match": 1,
        }
    }


def _help_lines() -> list[str]:
    return [
        "# HELP ctm_wazuh_api_up Whether the Wazuh API scrape succeeded.",
        "# TYPE ctm_wazuh_api_up gauge",
        "# HELP ctm_wazuh_agent_status Wazuh agent status as one labelled series per agent.",
        "# TYPE ctm_wazuh_agent_status gauge",
        "# HELP ctm_wazuh_agent_last_keepalive_timestamp_seconds Wazuh agent last keepalive unix timestamp.",
        "# TYPE ctm_wazuh_agent_last_keepalive_timestamp_seconds gauge",
        "# HELP ctm_wazuh_agents_status Wazuh agent count by connection status.",
        "# TYPE ctm_wazuh_agents_status gauge",
        "# HELP ctm_wazuh_manager_process_status Wazuh manager process status, 1 means running.",
        "# TYPE ctm_wazuh_manager_process_status gauge",
        "# HELP ctm_wazuh_rootcheck_findings_total Rootcheck finding count by agent and status.",
        "# TYPE ctm_wazuh_rootcheck_findings_total gauge",
        "# HELP ctm_wazuh_syscheck_findings_total FIM finding count by agent.",
        "# TYPE ctm_wazuh_syscheck_findings_total gauge",
        "# HELP ctm_wazuh_indexer_up Whether the Wazuh indexer alert query succeeded.",
        "# TYPE ctm_wazuh_indexer_up gauge",
        "# HELP ctm_wazuh_alerts_total Alert count by window, severity, and level.",
        "# TYPE ctm_wazuh_alerts_total gauge",
        "# HELP ctm_wazuh_alerts_agent_top Top alerting agents by window and severity.",
        "# TYPE ctm_wazuh_alerts_agent_top gauge",
        "# HELP ctm_wazuh_alerts_rule_top Top alerting rules by window and severity.",
        "# TYPE ctm_wazuh_alerts_rule_top gauge",
        "# HELP ctm_wazuh_alerts_mitre_tactic_top Top MITRE tactics by window.",
        "# TYPE ctm_wazuh_alerts_mitre_tactic_top gauge",
        "# HELP ctm_wazuh_ssh_events_total SSH event count by window and outcome.",
        "# TYPE ctm_wazuh_ssh_events_total gauge",
        "# HELP ctm_wazuh_ssh_agent_top Top SSH target agents by window and outcome.",
        "# TYPE ctm_wazuh_ssh_agent_top gauge",
        "# HELP ctm_wazuh_ssh_source_top Top SSH source IPs by window and outcome.",
        "# TYPE ctm_wazuh_ssh_source_top gauge",
        "# HELP ctm_wazuh_ssh_user_top Top SSH users by window and outcome.",
        "# TYPE ctm_wazuh_ssh_user_top gauge",
        "# HELP ctm_wazuh_ssh_rule_top Top SSH rules by window and outcome.",
        "# TYPE ctm_wazuh_ssh_rule_top gauge",
        "# HELP ctm_wazuh_ssh_recent_event Limited recent SSH events as labelled samples.",
        "# TYPE ctm_wazuh_ssh_recent_event gauge",
        "# HELP ctm_wazuh_ssh_active_sessions Currently active SSH sessions inferred from PAM sshd session open/close events.",
        "# TYPE ctm_wazuh_ssh_active_sessions gauge",
        "# HELP ctm_wazuh_ssh_active_session_duration_seconds Currently active SSH session duration as labelled samples.",
        "# TYPE ctm_wazuh_ssh_active_session_duration_seconds gauge",
        "# HELP ctm_wazuh_fim_events_total FIM event count by window, scope, and event.",
        "# TYPE ctm_wazuh_fim_events_total gauge",
        "# HELP ctm_wazuh_fim_agent_top Top FIM agents by window, scope, and event.",
        "# TYPE ctm_wazuh_fim_agent_top gauge",
        "# HELP ctm_wazuh_fim_path_top Top FIM paths by window, scope, and event.",
        "# TYPE ctm_wazuh_fim_path_top gauge",
        "# HELP ctm_wazuh_fim_rule_top Top FIM rules by window, scope, and event.",
        "# TYPE ctm_wazuh_fim_rule_top gauge",
        "# HELP ctm_wazuh_fim_recent_event Limited recent FIM events as labelled samples.",
        "# TYPE ctm_wazuh_fim_recent_event gauge",
    ]


def _timestamp(value: str | None) -> float:
    if not value or value.startswith("9999-"):
        return 0
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0


def _event_timestamp(value: Any) -> float:
    if not value:
        return 0
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0


def _sshd_pid(source: dict[str, Any]) -> str:
    match = _SSHD_PID_RE.search(str(source.get("full_log", "")))
    return match.group(1) if match else ""


def _sshd_session_user(source: dict[str, Any]) -> str:
    data = source.get("data") or {}
    if data.get("dstuser"):
        return str(data.get("dstuser"))
    match = _SSHD_SESSION_USER_RE.search(str(source.get("full_log", "")))
    return match.group(1) if match else ""


def _sshd_session_event(source: dict[str, Any]) -> str:
    text = str(source.get("full_log", ""))
    if "pam_unix(sshd:session)" not in text:
        return ""
    if "session opened" in text:
        return "opened"
    if "session closed" in text:
        return "closed"
    return ""


def _sshd_accepted(source: dict[str, Any]) -> dict[str, Any]:
    data = source.get("data") or {}
    match = _SSHD_ACCEPTED_RE.search(str(source.get("full_log", "")))
    return {
        "user": data.get("dstuser") or (match.group("user") if match else ""),
        "srcip": data.get("srcip") or (match.group("srcip") if match else ""),
        "srcport": data.get("srcport") or (match.group("srcport") if match else ""),
        "method": match.group("method") if match else "",
        "timestamp": source.get("@timestamp", ""),
        "ts": _event_timestamp(source.get("@timestamp")),
    }


def collect() -> str:
    started = time.time()
    lines = _help_lines()
    api_up = 0.0
    try:
        token = _login()
        api_up = 1.0

        root = _request("/", token)
        manager_info = _items(_request("/manager/info", token))
        manager_status = _items(_request("/manager/status", token))
        cluster_status = _request("/cluster/status", token)
        agent_summary = _request("/agents/summary/status", token)
        agents = _items(_request("/agents?limit=500", token))

        lines.append(_metric("ctm_wazuh_api_up", api_up))
        if isinstance(root, dict):
            data = root.get("data") or {}
            lines.append(
                _metric(
                    "ctm_wazuh_api_info",
                    1,
                    {
                        "api_version": data.get("api_version", ""),
                        "hostname": data.get("hostname", ""),
                        "revision": data.get("revision", ""),
                    },
                )
            )

        for info in manager_info:
            lines.append(
                _metric(
                    "ctm_wazuh_manager_info",
                    1,
                    {
                        "version": info.get("version", ""),
                        "type": info.get("type", ""),
                        "uuid": info.get("uuid", ""),
                    },
                )
            )

        for process_map in manager_status:
            for process, status in sorted(process_map.items()):
                if not process.startswith("wazuh-"):
                    continue
                labels = {"process": process, "critical": str(process in CRITICAL_PROCESSES).lower()}
                lines.append(_metric("ctm_wazuh_manager_process_status", 1 if status == "running" else 0, labels))

        if isinstance(cluster_status, dict):
            data = cluster_status.get("data") or {}
            lines.append(_metric("ctm_wazuh_cluster_enabled", 1 if data.get("enabled") == "yes" else 0))
            lines.append(_metric("ctm_wazuh_cluster_running", 1 if data.get("running") == "yes" else 0))

        if isinstance(agent_summary, dict):
            connection = (agent_summary.get("data") or {}).get("connection") or {}
            for status, value in sorted(connection.items()):
                if status == "total":
                    continue
                lines.append(_metric("ctm_wazuh_agents_status", float(value or 0), {"status": status}))
            config = (agent_summary.get("data") or {}).get("configuration") or {}
            for status, value in sorted(config.items()):
                if status == "total":
                    continue
                lines.append(_metric("ctm_wazuh_agents_config_status", float(value or 0), {"status": status}))

        for agent in agents:
            agent_id = agent.get("id", "")
            name = agent.get("name", "")
            status = agent.get("status", "")
            os_info = agent.get("os") or {}
            labels = {
                "agent_id": agent_id,
                "name": name,
                "ip": agent.get("ip", ""),
                "status": status,
                "os": os_info.get("name", ""),
                "os_version": os_info.get("version", ""),
                "manager": agent.get("manager", ""),
                "node": agent.get("node_name", ""),
            }
            lines.append(_metric("ctm_wazuh_agent_status", 1, labels))
            lines.append(_metric("ctm_wazuh_agent_last_keepalive_timestamp_seconds", _timestamp(agent.get("lastKeepAlive")), labels))
            lines.append(_metric("ctm_wazuh_agent_group_config_synced", 1 if agent.get("group_config_status") == "synced" else 0, labels))

            if agent_id and agent_id != "000":
                try:
                    syscheck = _request(f"/syscheck/{urllib.parse.quote(agent_id)}?limit=1", token)
                    lines.append(_metric("ctm_wazuh_syscheck_findings_total", _total(syscheck), labels))
                except Exception:
                    lines.append(_metric("ctm_wazuh_syscheck_findings_total", -1, labels))

                for finding_status in ("outstanding", "solved"):
                    try:
                        rootcheck = _request(
                            f"/rootcheck/{urllib.parse.quote(agent_id)}?limit=1&status={finding_status}",
                            token,
                        )
                        value = _total(rootcheck)
                    except Exception:
                        value = -1
                    root_labels = dict(labels)
                    root_labels["finding_status"] = finding_status
                    lines.append(_metric("ctm_wazuh_rootcheck_findings_total", value, root_labels))

    except Exception as exc:
        lines.append(_metric("ctm_wazuh_api_up", api_up))
        lines.append(_metric("ctm_wazuh_exporter_error", 1, {"message": str(exc)[:180]}))

    collect_indexer(lines)

    lines.append(_metric("ctm_wazuh_scrape_duration_seconds", time.time() - started))
    lines.append("")
    return "\n".join(lines)


def collect_indexer(lines: list[str]) -> None:
    if not INDEXER_URL:
        lines.append(_metric("ctm_wazuh_indexer_up", 0, {"reason": "not_configured"}))
        return

    try:
        lines.append(_metric("ctm_wazuh_indexer_up", 1))
        for window in ALERT_WINDOWS:
            payload = {
                "size": 0,
                "query": {"range": {"@timestamp": {"gte": f"now-{window}"}}},
                "aggs": {
                    "by_level": {"terms": {"field": "rule.level", "size": 32}},
                    "top_agents": {
                        "terms": {"field": "agent.name", "size": 100},
                        "aggs": {
                            "agent_id": {"terms": {"field": "agent.id", "size": 1}},
                            "max_level": {"max": {"field": "rule.level"}},
                        },
                    },
                    "top_rules": {
                        "terms": {"field": "rule.id", "size": 12},
                        "aggs": {
                            "description": {"terms": {"field": "rule.description", "size": 1}},
                            "max_level": {"max": {"field": "rule.level"}},
                        },
                    },
                    "top_mitre_tactics": {"terms": {"field": "rule.mitre.tactic", "size": 12}},
                },
            }
            result = _indexer_request(f"/{urllib.parse.quote(INDEXER_INDEX, safe='*,-_')}/_search", payload)

            level_buckets = ((result.get("aggregations") or {}).get("by_level") or {}).get("buckets") or []
            for bucket in level_buckets:
                level = int(bucket.get("key", 0))
                labels = {"window": window, "severity": _severity(level), "level": level}
                lines.append(_metric("ctm_wazuh_alerts_total", float(bucket.get("doc_count", 0)), labels))

            agent_buckets = ((result.get("aggregations") or {}).get("top_agents") or {}).get("buckets") or []
            for bucket in agent_buckets:
                max_level = int(((bucket.get("max_level") or {}).get("value") or 0))
                agent_ids = ((bucket.get("agent_id") or {}).get("buckets") or [])
                labels = {
                    "window": window,
                    "severity": _severity(max_level),
                    "agent_name": bucket.get("key", ""),
                    "agent_id": agent_ids[0].get("key", "") if agent_ids else "",
                    "max_level": max_level,
                }
                lines.append(_metric("ctm_wazuh_alerts_agent_top", float(bucket.get("doc_count", 0)), labels))

            rule_buckets = ((result.get("aggregations") or {}).get("top_rules") or {}).get("buckets") or []
            for bucket in rule_buckets:
                max_level = int(((bucket.get("max_level") or {}).get("value") or 0))
                descriptions = ((bucket.get("description") or {}).get("buckets") or [])
                labels = {
                    "window": window,
                    "severity": _severity(max_level),
                    "rule_id": bucket.get("key", ""),
                    "description": descriptions[0].get("key", "") if descriptions else "",
                    "max_level": max_level,
                }
                lines.append(_metric("ctm_wazuh_alerts_rule_top", float(bucket.get("doc_count", 0)), labels))

            tactic_buckets = ((result.get("aggregations") or {}).get("top_mitre_tactics") or {}).get("buckets") or []
            for bucket in tactic_buckets:
                labels = {"window": window, "tactic": bucket.get("key", "")}
                lines.append(_metric("ctm_wazuh_alerts_mitre_tactic_top", float(bucket.get("doc_count", 0)), labels))

        collect_ssh_indexer(lines)
        collect_fim_indexer(lines)
    except Exception as exc:
        lines.append(_metric("ctm_wazuh_indexer_up", 0, {"reason": str(exc)[:160]}))


def collect_ssh_indexer(lines: list[str]) -> None:
    for window in SSH_WINDOWS:
        payload = {
            "size": 0,
            "query": {
                "bool": {
                    "filter": [
                        {"range": {"@timestamp": {"gte": f"now-{window}"}}},
                        {"term": {"rule.groups": "sshd"}},
                    ]
                }
            },
            "aggs": {
                "outcomes": {
                    "filters": {
                        "filters": {
                            "all": {"match_all": {}},
                            "success": {"term": {"rule.groups": "authentication_success"}},
                            "failed": {"term": {"rule.groups": "authentication_failed"}},
                            "invalid_user": {"term": {"rule.id": "5710"}},
                            "root_login": {
                                "bool": {
                                    "filter": [{"term": {"rule.groups": "authentication_success"}}],
                                    "should": [
                                        {"term": {"data.dstuser": "root"}},
                                        {"term": {"dstuser": "root"}},
                                    ],
                                    "minimum_should_match": 1,
                                }
                            },
                        }
                    },
                    "aggs": {
                        "top_agents": {
                            "terms": {"field": "agent.name", "size": 100},
                            "aggs": {
                                "agent_id": {"terms": {"field": "agent.id", "size": 1}},
                                "agent_ip": {"terms": {"field": "agent.ip", "size": 1}},
                            },
                        },
                        "top_sources": {"terms": {"field": "data.srcip", "size": 12}},
                        "top_users": {"terms": {"field": "data.dstuser", "size": 12}},
                        "top_rules": {
                            "terms": {"field": "rule.id", "size": 12},
                            "aggs": {
                                "description": {"terms": {"field": "rule.description", "size": 1}},
                                "max_level": {"max": {"field": "rule.level"}},
                            },
                        },
                    },
                }
            },
        }
        result = _indexer_request(f"/{urllib.parse.quote(INDEXER_INDEX, safe='*,-_')}/_search", payload)
        outcome_buckets = ((result.get("aggregations") or {}).get("outcomes") or {}).get("buckets") or {}
        for outcome, bucket in sorted(outcome_buckets.items()):
            labels = {"window": window, "outcome": outcome}
            lines.append(_metric("ctm_wazuh_ssh_events_total", float(bucket.get("doc_count", 0)), labels))

            for item in ((bucket.get("top_agents") or {}).get("buckets") or []):
                agent_labels = dict(labels)
                agent_labels["agent_name"] = item.get("key", "")
                agent_labels["agent_id"] = _first_bucket_key(item.get("agent_id"))
                agent_labels["agent_ip"] = _first_bucket_key(item.get("agent_ip"))
                lines.append(_metric("ctm_wazuh_ssh_agent_top", float(item.get("doc_count", 0)), agent_labels))

            for item in ((bucket.get("top_sources") or {}).get("buckets") or []):
                source_labels = dict(labels)
                source_labels["srcip"] = item.get("key", "")
                lines.append(_metric("ctm_wazuh_ssh_source_top", float(item.get("doc_count", 0)), source_labels))

            for item in ((bucket.get("top_users") or {}).get("buckets") or []):
                user_labels = dict(labels)
                user_labels["user"] = item.get("key", "")
                lines.append(_metric("ctm_wazuh_ssh_user_top", float(item.get("doc_count", 0)), user_labels))

            for item in ((bucket.get("top_rules") or {}).get("buckets") or []):
                level = int(((item.get("max_level") or {}).get("value") or 0))
                rule_labels = dict(labels)
                rule_labels.update(
                    {
                        "rule_id": item.get("key", ""),
                        "description": _first_bucket_key(item.get("description")),
                        "max_level": level,
                        "severity": _severity(level),
                    }
                )
                lines.append(_metric("ctm_wazuh_ssh_rule_top", float(item.get("doc_count", 0)), rule_labels))

    recent_payload = {
        "size": SSH_RECENT_LIMIT,
        "sort": [{"@timestamp": {"order": "desc"}}],
        "query": {
            "bool": {
                "filter": [
                    {"range": {"@timestamp": {"gte": "now-24h"}}},
                    {"term": {"rule.groups": "sshd"}},
                ]
            }
        },
        "_source": [
            "@timestamp",
            "agent.id",
            "agent.name",
            "agent.ip",
            "data.srcip",
            "data.dstuser",
            "dstuser",
            "rule.id",
            "rule.level",
            "rule.description",
            "rule.groups",
        ],
    }
    recent = _indexer_request(f"/{urllib.parse.quote(INDEXER_INDEX, safe='*,-_')}/_search", recent_payload)
    for rank, hit in enumerate(((recent.get("hits") or {}).get("hits") or []), start=1):
        source = hit.get("_source") or {}
        agent = source.get("agent") or {}
        data = source.get("data") or {}
        rule = source.get("rule") or {}
        level = int(rule.get("level") or 0)
        labels = {
            "rank": rank,
            "timestamp": source.get("@timestamp", ""),
            "agent_name": agent.get("name", ""),
            "agent_id": agent.get("id", ""),
            "agent_ip": agent.get("ip", ""),
            "srcip": data.get("srcip", ""),
            "user": data.get("dstuser") or source.get("dstuser") or "",
            "outcome": _ssh_outcome(source),
            "rule_id": rule.get("id", ""),
            "level": level,
            "severity": _severity(level),
            "description": rule.get("description", ""),
        }
        lines.append(_metric("ctm_wazuh_ssh_recent_event", 1, labels))

    collect_ssh_active_sessions(lines)


def collect_ssh_active_sessions(lines: list[str]) -> None:
    session_payload = {
        "size": SSH_SESSION_LIMIT,
        "sort": [{"@timestamp": {"order": "asc"}}],
        "query": {
            "bool": {
                "filter": [
                    {"range": {"@timestamp": {"gte": f"now-{SSH_SESSION_LOOKBACK}"}}},
                    {"match_phrase": {"full_log": "pam_unix(sshd:session)"}},
                ]
            }
        },
        "_source": ["@timestamp", "agent.id", "agent.name", "agent.ip", "data.dstuser", "full_log"],
    }
    accepted_payload = {
        "size": SSH_SESSION_LIMIT,
        "sort": [{"@timestamp": {"order": "asc"}}],
        "query": {
            "bool": {
                "filter": [
                    {"range": {"@timestamp": {"gte": f"now-{SSH_SESSION_LOOKBACK}"}}},
                    {"term": {"rule.groups": "authentication_success"}},
                    {"match_phrase": {"full_log": "Accepted"}},
                ]
            }
        },
        "_source": ["@timestamp", "agent.id", "agent.name", "agent.ip", "data.srcip", "data.srcport", "data.dstuser", "full_log"],
    }

    accepted = _indexer_request(f"/{urllib.parse.quote(INDEXER_INDEX, safe='*,-_')}/_search", accepted_payload)
    accepted_by_pid: dict[tuple[str, str], dict[str, Any]] = {}
    accepted_by_agent_user: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for hit in (accepted.get("hits") or {}).get("hits") or []:
        source = hit.get("_source") or {}
        agent = source.get("agent") or {}
        pid = _sshd_pid(source)
        item = _sshd_accepted(source)
        item.update(
            {
                "agent_id": agent.get("id", ""),
                "agent_name": agent.get("name", ""),
                "agent_ip": agent.get("ip", ""),
                "pid": pid,
            }
        )
        if pid:
            accepted_by_pid[(str(agent.get("id", "")), pid)] = item
        user_key = (str(agent.get("id", "")), str(item.get("user", "")))
        accepted_by_agent_user.setdefault(user_key, []).append(item)

    sessions = _indexer_request(f"/{urllib.parse.quote(INDEXER_INDEX, safe='*,-_')}/_search", session_payload)
    active: dict[tuple[str, str], dict[str, Any]] = {}
    for hit in (sessions.get("hits") or {}).get("hits") or []:
        source = hit.get("_source") or {}
        agent = source.get("agent") or {}
        pid = _sshd_pid(source)
        if not pid:
            continue
        event = _sshd_session_event(source)
        if not event:
            continue
        agent_id = str(agent.get("id", ""))
        key = (agent_id, pid)
        if event == "closed":
            active.pop(key, None)
            continue

        opened_ts = _event_timestamp(source.get("@timestamp"))
        user = _sshd_session_user(source)
        auth = accepted_by_pid.get(key)
        if not auth:
            candidates = accepted_by_agent_user.get((agent_id, user), [])
            previous = [item for item in candidates if item.get("ts", 0) <= opened_ts and opened_ts - item.get("ts", 0) <= 180]
            auth = previous[-1] if previous else {}
        active[key] = {
            "agent_id": agent_id,
            "agent_name": agent.get("name", ""),
            "agent_ip": agent.get("ip", ""),
            "pid": pid,
            "user": user,
            "srcip": auth.get("srcip", ""),
            "srcport": auth.get("srcport", ""),
            "auth_method": auth.get("method", ""),
            "opened_at": source.get("@timestamp", ""),
            "opened_ts": opened_ts,
        }

    counts: dict[tuple[str, str, str, str, str], int] = {}
    now = time.time()
    for session in active.values():
        key = (
            str(session.get("agent_id", "")),
            str(session.get("agent_name", "")),
            str(session.get("agent_ip", "")),
            str(session.get("user", "")),
            str(session.get("srcip", "")),
        )
        counts[key] = counts.get(key, 0) + 1

        labels = {
            "agent_id": session.get("agent_id", ""),
            "agent_name": session.get("agent_name", ""),
            "agent_ip": session.get("agent_ip", ""),
            "pid": session.get("pid", ""),
            "user": session.get("user", ""),
            "srcip": session.get("srcip", ""),
            "srcport": session.get("srcport", ""),
            "auth_method": session.get("auth_method", ""),
            "opened_at": session.get("opened_at", ""),
            "state": "active",
            "source": "wazuh_pam_session",
        }
        duration = max(0.0, now - float(session.get("opened_ts") or now))
        lines.append(_metric("ctm_wazuh_ssh_active_session_duration_seconds", duration, labels))

    for (agent_id, agent_name, agent_ip, user, srcip), count in sorted(counts.items()):
        labels = {
            "agent_id": agent_id,
            "agent_name": agent_name,
            "agent_ip": agent_ip,
            "user": user,
            "srcip": srcip,
            "state": "active",
            "source": "wazuh_pam_session",
        }
        lines.append(_metric("ctm_wazuh_ssh_active_sessions", float(count), labels))


def collect_fim_indexer(lines: list[str]) -> None:
    for window in FIM_WINDOWS:
        for scope in ("all", "key"):
            filters: list[dict[str, Any]] = [
                {"range": {"@timestamp": {"gte": f"now-{window}"}}},
                {
                    "bool": {
                        "should": [
                            {"term": {"rule.groups": "syscheck"}},
                            {"term": {"rule.groups": "syscheck_file"}},
                            {"terms": {"rule.id": ["550", "553", "554", "594", "750", "560"]}},
                        ],
                        "minimum_should_match": 1,
                    }
                },
            ]
            if scope == "key":
                filters.append(_fim_key_path_filter())
            payload = {
                "size": 0,
                "query": {"bool": {"filter": filters}},
                "aggs": {
                    "events": {
                        "terms": {"field": "syscheck.event", "size": 12},
                        "aggs": {
                            "top_agents": {
                                "terms": {"field": "agent.name", "size": 100},
                                "aggs": {"agent_id": {"terms": {"field": "agent.id", "size": 1}}},
                            },
                            "top_paths": {"terms": {"field": "syscheck.path", "size": 12}},
                            "top_rules": {
                                "terms": {"field": "rule.id", "size": 12},
                                "aggs": {
                                    "description": {"terms": {"field": "rule.description", "size": 1}},
                                    "max_level": {"max": {"field": "rule.level"}},
                                },
                            },
                        },
                    }
                },
            }
            result = _indexer_request(f"/{urllib.parse.quote(INDEXER_INDEX, safe='*,-_')}/_search", payload)
            event_buckets = ((result.get("aggregations") or {}).get("events") or {}).get("buckets") or []
            for event_bucket in event_buckets:
                event = event_bucket.get("key", "")
                labels = {"window": window, "scope": scope, "event": event}
                lines.append(_metric("ctm_wazuh_fim_events_total", float(event_bucket.get("doc_count", 0)), labels))

                for item in ((event_bucket.get("top_agents") or {}).get("buckets") or []):
                    agent_labels = dict(labels)
                    agent_labels["agent_name"] = item.get("key", "")
                    agent_labels["agent_id"] = _first_bucket_key(item.get("agent_id"))
                    lines.append(_metric("ctm_wazuh_fim_agent_top", float(item.get("doc_count", 0)), agent_labels))

                for item in ((event_bucket.get("top_paths") or {}).get("buckets") or []):
                    path_labels = dict(labels)
                    path_labels["path"] = item.get("key", "")
                    lines.append(_metric("ctm_wazuh_fim_path_top", float(item.get("doc_count", 0)), path_labels))

                for item in ((event_bucket.get("top_rules") or {}).get("buckets") or []):
                    level = int(((item.get("max_level") or {}).get("value") or 0))
                    rule_labels = dict(labels)
                    rule_labels.update(
                        {
                            "rule_id": item.get("key", ""),
                            "description": _first_bucket_key(item.get("description")),
                            "max_level": level,
                            "severity": _severity(level),
                        }
                    )
                    lines.append(_metric("ctm_wazuh_fim_rule_top", float(item.get("doc_count", 0)), rule_labels))

    recent_filters: list[dict[str, Any]] = [
        {"range": {"@timestamp": {"gte": "now-24h"}}},
        {
            "bool": {
                "should": [
                    {"term": {"rule.groups": "syscheck"}},
                    {"term": {"rule.groups": "syscheck_file"}},
                    {"terms": {"rule.id": ["550", "553", "554", "594", "750", "560"]}},
                ],
                "minimum_should_match": 1,
            }
        },
        _fim_key_path_filter(),
    ]
    recent_payload = {
        "size": FIM_RECENT_LIMIT,
        "sort": [{"@timestamp": {"order": "desc"}}],
        "query": {"bool": {"filter": recent_filters}},
        "_source": [
            "@timestamp",
            "agent.id",
            "agent.name",
            "agent.ip",
            "rule.id",
            "rule.level",
            "rule.description",
            "syscheck.path",
            "syscheck.event",
            "syscheck.mode",
            "syscheck.uname_after",
            "syscheck.gname_after",
            "syscheck.perm_after",
        ],
    }
    recent = _indexer_request(f"/{urllib.parse.quote(INDEXER_INDEX, safe='*,-_')}/_search", recent_payload)
    for rank, hit in enumerate(((recent.get("hits") or {}).get("hits") or []), start=1):
        source = hit.get("_source") or {}
        agent = source.get("agent") or {}
        rule = source.get("rule") or {}
        syscheck = source.get("syscheck") or {}
        level = int(rule.get("level") or 0)
        labels = {
            "rank": rank,
            "timestamp": source.get("@timestamp", ""),
            "agent_name": agent.get("name", ""),
            "agent_id": agent.get("id", ""),
            "agent_ip": agent.get("ip", ""),
            "event": syscheck.get("event", ""),
            "path": syscheck.get("path", ""),
            "mode": syscheck.get("mode", ""),
            "user": syscheck.get("uname_after", ""),
            "group": syscheck.get("gname_after", ""),
            "perm": syscheck.get("perm_after", ""),
            "rule_id": rule.get("id", ""),
            "level": level,
            "severity": _severity(level),
            "description": rule.get("description", ""),
        }
        lines.append(_metric("ctm_wazuh_fim_recent_event", 1, labels))


def cached_collect() -> str:
    now = time.time()
    with _cache_lock:
        if _cache:
            payload = _cache[1]
            age = now - _cache[0]
            return payload + _metric("ctm_wazuh_cache_age_seconds", age) + "\n"
    return "\n".join(
        [
            *_help_lines(),
            _metric("ctm_wazuh_api_up", 0),
            _metric("ctm_wazuh_exporter_cache_ready", 0),
            "",
        ]
    )


def refresh_loop() -> None:
    global _cache
    while True:
        payload = collect()
        with _cache_lock:
            _cache = (time.time(), payload)
        time.sleep(COLLECT_INTERVAL)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path == "/healthz":
            body = b"ok\n"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path.split("?", 1)[0] != "/metrics":
            self.send_response(404)
            self.end_headers()
            return
        body = cached_collect().encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args: Any) -> None:
        return


def main() -> None:
    if not API_USER or not API_PASSWORD:
        raise SystemExit("WAZUH_API_USERNAME and WAZUH_API_PASSWORD are required")
    thread = threading.Thread(target=refresh_loop, daemon=True)
    thread.start()
    server = ThreadingHTTPServer((BIND, PORT), Handler)
    server.serve_forever()


if __name__ == "__main__":
    main()
