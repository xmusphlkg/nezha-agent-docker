from __future__ import annotations

import time
from typing import Any

from ..models import (
    Health,
    LanDevice,
    LanSummary,
    Problem,
    PrometheusTarget,
    ServiceProbe,
    ServicesSummary,
    TailnetKey,
    TailnetNode,
    TailnetSummary,
    WazuhAgent,
    WazuhAlertSummary,
    WazuhFimSummary,
    WazuhRecentEvent,
    WazuhSshSession,
    WazuhSshSummary,
    WazuhSummary,
    WazuhTopItem,
)


def prom_value(sample: dict[str, Any]) -> float:
    value = sample.get("value") or [0, 0]
    try:
        return float(value[1])
    except (TypeError, ValueError, IndexError):
        return 0.0


def prom_metric(sample: dict[str, Any]) -> dict[str, str]:
    return {str(k): str(v) for k, v in (sample.get("metric") or {}).items()}


def vector_scalar(samples: list[dict[str, Any]]) -> float | None:
    if not samples:
        return None
    return prom_value(samples[0])


def build_tailnet(
    online: list[dict[str, Any]],
    info: list[dict[str, Any]],
    last_seen: list[dict[str, Any]],
    routes_available: list[dict[str, Any]],
    routes_approved: list[dict[str, Any]],
    api_up: list[dict[str, Any]],
    db_ok: list[dict[str, Any]],
    keys: list[dict[str, Any]],
    *,
    stale: bool = False,
) -> TailnetSummary:
    info_by_id = {prom_metric(sample).get("id") or prom_metric(sample).get("name"): sample for sample in info}
    last_seen_by_id = {prom_metric(sample).get("id") or prom_metric(sample).get("name"): prom_value(sample) for sample in last_seen}
    available_by_id = {prom_metric(sample).get("id") or prom_metric(sample).get("name"): prom_value(sample) for sample in routes_available}
    approved_by_id = {prom_metric(sample).get("id") or prom_metric(sample).get("name"): prom_value(sample) for sample in routes_approved}

    nodes: list[TailnetNode] = []
    for sample in online:
        metric = prom_metric(sample)
        node_id = metric.get("id") or metric.get("name") or metric.get("instance") or "unknown"
        info_metric = prom_metric(info_by_id.get(node_id, {}))
        last_seen_ts = last_seen_by_id.get(node_id)
        last_seen_age = None
        if last_seen_ts:
            last_seen_age = max(time.time() - last_seen_ts, 0)
        nodes.append(
            TailnetNode(
                id=node_id,
                name=metric.get("name") or info_metric.get("name") or node_id,
                user=metric.get("user") or info_metric.get("user"),
                online=prom_value(sample) > 0,
                lastSeenAgeSec=last_seen_age,
                availableRoutes=available_by_id.get(node_id),
                approvedRoutes=approved_by_id.get(node_id),
            )
        )

    parsed_keys: list[TailnetKey] = []
    expiring_keys = 0
    for sample in keys:
        metric = prom_metric(sample)
        expires_in = prom_value(sample)
        if expires_in > 0 and expires_in < 7 * 24 * 3600:
            expiring_keys += 1
        parsed_keys.append(
            TailnetKey(
                user=metric.get("user"),
                reusable=metric.get("reusable"),
                expiresInSec=expires_in,
            )
        )

    total = len(nodes)
    online_count = sum(1 for node in nodes if node.online)
    api_is_up = (vector_scalar(api_up) or 0) > 0 if api_up else None
    database_ok = (vector_scalar(db_ok) or 0) > 0 if db_ok else None
    route_delta = sum((node.availableRoutes or 0) - (node.approvedRoutes or 0) for node in nodes)
    if stale:
        health = Health.STALE
    elif api_is_up is False or database_ok is False:
        health = Health.CRITICAL
    elif total and online_count < total or route_delta > 0 or expiring_keys > 0:
        health = Health.WARNING
    elif total:
        health = Health.OK
    else:
        health = Health.UNKNOWN

    return TailnetSummary(
        health=health,
        apiUp=api_is_up,
        databaseOk=database_ok,
        totalNodes=total,
        onlineNodes=online_count,
        offlineNodes=max(total - online_count, 0),
        routeDelta=route_delta,
        expiringKeys=expiring_keys,
        nodes=sorted(nodes, key=lambda node: (node.online, node.name.lower())),
        keys=parsed_keys,
        stale=stale,
    )


def build_services(
    probes: list[dict[str, Any]],
    durations: list[dict[str, Any]],
    targets: list[dict[str, Any]],
    *,
    stale: bool = False,
) -> ServicesSummary:
    duration_by_key: dict[tuple[str, str], float] = {}
    for sample in durations:
        metric = prom_metric(sample)
        duration_by_key[(metric.get("job", ""), metric.get("instance", ""))] = prom_value(sample)

    parsed_probes: list[ServiceProbe] = []
    for sample in probes:
        metric = prom_metric(sample)
        job = metric.get("job", "")
        instance = metric.get("instance", "")
        parsed_probes.append(
            ServiceProbe(
                id=f"{job}:{instance}:{metric.get('target', '')}",
                job=job,
                instance=instance,
                target=metric.get("target"),
                name=metric.get("zbx_name") or metric.get("name"),
                group=metric.get("zbx_group"),
                ifaceType=metric.get("iface_type"),
                success=prom_value(sample) > 0,
                durationSec=duration_by_key.get((job, instance)),
            )
        )

    parsed_targets: list[PrometheusTarget] = []
    for target in targets:
        labels = target.get("labels") or {}
        parsed_targets.append(
            PrometheusTarget(
                id=str(target.get("scrapeUrl") or target.get("globalUrl") or labels),
                job=labels.get("job"),
                scrapeUrl=str(target.get("scrapeUrl") or target.get("globalUrl") or ""),
                health=str(target.get("health") or "unknown"),
                lastScrape=target.get("lastScrape"),
                lastError=target.get("lastError") or None,
            )
        )

    failed = sum(1 for probe in parsed_probes if not probe.success)
    down = sum(1 for target in parsed_targets if target.health != "up")
    if stale:
        health = Health.STALE
    elif failed or down:
        health = Health.WARNING
    elif parsed_probes or parsed_targets:
        health = Health.OK
    else:
        health = Health.UNKNOWN
    return ServicesSummary(
        health=health,
        probeTotal=len(parsed_probes),
        probeFailed=failed,
        targetTotal=len(parsed_targets),
        targetDown=down,
        probes=sorted(parsed_probes, key=lambda probe: (probe.success, probe.job, probe.name or probe.instance)),
        targets=sorted(parsed_targets, key=lambda target: (target.health == "up", target.job or "", target.scrapeUrl)),
        stale=stale,
    )


def build_lan_summary(samples: list[dict[str, Any]], *, stale: bool = False) -> LanSummary:
    devices: list[LanDevice] = []
    seen: set[str] = set()
    for sample in samples:
        metric = prom_metric(sample)
        ip = (metric.get("ip") or "").strip()
        mac = (metric.get("mac") or "").strip().lower()
        if not ip or not mac:
            continue

        device_id = mac or ip
        if device_id in seen:
            continue
        seen.add(device_id)

        name = (metric.get("name") or "").strip() or None
        iface = (metric.get("iface") or "").strip() or None
        known = (metric.get("known") or "").strip().lower() in {"1", "true", "yes"}
        online = prom_value(sample) > 0
        if stale:
            health = Health.STALE
        elif online and not known:
            health = Health.WARNING
        elif online:
            health = Health.OK
        else:
            health = Health.OFFLINE

        devices.append(
            LanDevice(
                id=device_id,
                ip=ip,
                mac=mac,
                name=name,
                iface=iface,
                known=known,
                online=online,
                health=health,
            )
        )

    total = len(devices)
    online_count = sum(1 for device in devices if device.online)
    known_count = sum(1 for device in devices if device.known)
    unknown_online = sum(1 for device in devices if device.online and not device.known)
    known_online = sum(1 for device in devices if device.online and device.known)
    interfaces = sorted({device.iface for device in devices if device.iface})
    if stale:
        health = Health.STALE
    elif unknown_online:
        health = Health.WARNING
    elif total:
        health = Health.OK
    else:
        health = Health.UNKNOWN

    return LanSummary(
        health=health,
        totalDevices=total,
        onlineDevices=online_count,
        knownDevices=known_count,
        unknownDevices=max(total - known_count, 0),
        knownOnline=known_online,
        unknownOnline=unknown_online,
        interfaces=interfaces,
        devices=sorted(
            devices,
            key=lambda device: (
                not device.online,
                device.known,
                _ip_sort_key(device.ip),
                device.name or "",
                device.mac,
            ),
        ),
        stale=stale,
    )


def build_prometheus_problems(alerts: list[dict[str, Any]]) -> list[Problem]:
    problems: list[Problem] = []
    now = time.time()
    for alert in alerts:
        if alert.get("state") not in {"firing", "pending"}:
            continue
        labels = alert.get("labels") or {}
        annotations = alert.get("annotations") or {}
        active_at = alert.get("activeAt")
        started = now
        if active_at:
            try:
                started = time.mktime(time.strptime(active_at[:19], "%Y-%m-%dT%H:%M:%S"))
            except ValueError:
                started = now
        name = annotations.get("summary") or labels.get("alertname") or "Prometheus alert"
        problems.append(
            Problem(
                source="prometheus",
                severity=labels.get("severity") or alert.get("state") or "warning",
                host=labels.get("instance") or labels.get("job") or "prometheus",
                name=name,
                ageSec=max(int(now - started), 0),
                eventId=f"{labels.get('alertname', name)}:{labels.get('instance', '')}",
                acknowledged=False,
            )
        )
    return problems


def _ip_sort_key(value: str) -> tuple[int, ...]:
    parts = value.split(".")
    if len(parts) != 4:
        return (999, 999, 999, 999)
    try:
        return tuple(int(part) for part in parts)
    except ValueError:
        return (999, 999, 999, 999)


def build_wazuh_summary(
    *,
    enabled: bool,
    modules: set[str],
    window: str,
    metrics: dict[str, list[dict[str, Any]]],
    stale: bool = False,
    recent_limit: int = 12,
) -> WazuhSummary:
    selected_modules = sorted(modules)
    if not enabled:
        return WazuhSummary(enabled=False, modules=[], health=Health.UNKNOWN, stale=stale)

    api_up = _vector_bool(metrics.get("api_up", []))
    needs_indexer = bool(modules & {"alerts", "ssh", "fim"})
    indexer_up = _vector_bool(metrics.get("indexer_up", [])) if needs_indexer else None
    manager_critical_down = vector_scalar(metrics.get("manager_critical_down", [])) or 0

    agents = _build_wazuh_agents(metrics) if "agents" in modules else []
    agent_total, active_agents, inactive_agents = _agent_counts(
        metrics.get("agents_status", []),
        agents,
    )
    rootcheck_total = sum(
        _non_negative(prom_value(sample)) or 0
        for sample in metrics.get("rootcheck_outstanding", [])
    )
    syscheck_total = sum(
        _non_negative(prom_value(sample)) or 0
        for sample in metrics.get("syscheck_findings", [])
    )

    alerts = (
        _build_wazuh_alerts(window, metrics)
        if "alerts" in modules
        else WazuhAlertSummary(window=window)
    )
    ssh = (
        _build_wazuh_ssh(window, metrics, recent_limit)
        if "ssh" in modules
        else WazuhSshSummary(window=window)
    )
    fim = (
        _build_wazuh_fim(window, metrics, recent_limit)
        if "fim" in modules
        else WazuhFimSummary(window=window)
    )

    health = _wazuh_health(
        api_up=api_up,
        indexer_up=indexer_up,
        needs_indexer=needs_indexer,
        manager_critical_down=manager_critical_down,
        inactive_agents=inactive_agents,
        rootcheck_total=rootcheck_total,
        alerts=alerts,
        ssh=ssh,
        fim=fim,
        stale=stale,
    )

    return WazuhSummary(
        enabled=True,
        modules=selected_modules,
        health=health,
        apiUp=api_up,
        indexerUp=indexer_up,
        agentTotal=agent_total,
        activeAgents=active_agents,
        inactiveAgents=inactive_agents,
        managerCriticalDown=manager_critical_down,
        rootcheckOutstanding=rootcheck_total,
        syscheckFindings=syscheck_total,
        agents=agents,
        alerts=alerts,
        ssh=ssh,
        fim=fim,
        stale=stale,
    )


def _build_wazuh_agents(metrics: dict[str, list[dict[str, Any]]]) -> list[WazuhAgent]:
    keepalive = _samples_by_agent(metrics.get("agent_keepalive", []))
    group_sync = _samples_by_agent(metrics.get("agent_group_sync", []))
    rootcheck = _samples_by_agent(metrics.get("rootcheck_outstanding", []))
    syscheck = _samples_by_agent(metrics.get("syscheck_findings", []))

    agents: list[WazuhAgent] = []
    now = time.time()
    for sample in metrics.get("agent_status", []):
        metric = prom_metric(sample)
        agent_id = metric.get("agent_id") or metric.get("id") or metric.get("name") or "unknown"
        if agent_id == "000":
            continue
        key = _agent_key(metric)
        keepalive_ts = prom_value(keepalive[key]) if key in keepalive else 0
        last_keepalive_age = max(now - keepalive_ts, 0) if keepalive_ts > 0 else None
        agents.append(
            WazuhAgent(
                id=agent_id,
                name=metric.get("name") or agent_id,
                ip=_blank_none(metric.get("ip")),
                status=metric.get("status") or "unknown",
                osName=_blank_none(metric.get("os")),
                osVersion=_blank_none(metric.get("os_version")),
                manager=_blank_none(metric.get("manager")),
                node=_blank_none(metric.get("node")),
                lastKeepaliveAgeSec=last_keepalive_age,
                groupConfigSynced=(prom_value(group_sync[key]) > 0) if key in group_sync else None,
                rootcheckOutstanding=(
                    _non_negative(prom_value(rootcheck[key])) if key in rootcheck else None
                ),
                syscheckFindings=(
                    _non_negative(prom_value(syscheck[key])) if key in syscheck else None
                ),
            )
        )

    return sorted(agents, key=lambda agent: (agent.status == "active", agent.name.lower()))


def _build_wazuh_alerts(window: str, metrics: dict[str, list[dict[str, Any]]]) -> WazuhAlertSummary:
    severity_counts: dict[str, float] = {}
    for sample in metrics.get("alert_counts", []):
        metric = prom_metric(sample)
        severity = metric.get("severity")
        value = prom_value(sample)
        if severity and value > 0:
            severity_counts[severity] = severity_counts.get(severity, 0) + value

    return WazuhAlertSummary(
        window=window,
        severityCounts=severity_counts,
        topAgents=_top_items(metrics.get("alert_top_agents", []), ("agent_name", "name")),
        topRules=_top_items(metrics.get("alert_top_rules", []), ("rule_id",)),
        topTactics=_top_items(metrics.get("alert_top_tactics", []), ("tactic",)),
    )


def _build_wazuh_ssh(
    window: str,
    metrics: dict[str, list[dict[str, Any]]],
    recent_limit: int,
) -> WazuhSshSummary:
    counts: dict[str, float] = {}
    for sample in metrics.get("ssh_counts", []):
        metric = prom_metric(sample)
        outcome = metric.get("outcome")
        value = prom_value(sample)
        if outcome and value > 0:
            counts[outcome] = counts.get(outcome, 0) + value

    active_session_items = build_wazuh_ssh_sessions(metrics.get("ssh_active_sessions", []))
    active_sessions = len(active_session_items)

    recent: list[WazuhRecentEvent] = []
    for sample in _ranked_samples(metrics.get("ssh_recent", []))[:recent_limit]:
        metric = prom_metric(sample)
        if prom_value(sample) <= 0:
            continue
        recent.append(
            WazuhRecentEvent(
                kind="ssh",
                timestamp=_blank_none(metric.get("timestamp")),
                agentName=_blank_none(metric.get("agent_name")),
                agentId=_blank_none(metric.get("agent_id")),
                agentIp=_blank_none(metric.get("agent_ip")),
                srcip=_blank_none(metric.get("srcip")),
                user=_blank_none(metric.get("user")),
                outcome=_blank_none(metric.get("outcome")),
                ruleId=_blank_none(metric.get("rule_id")),
                severity=_blank_none(metric.get("severity")),
                level=_float_label(metric, "level"),
                description=_blank_none(metric.get("description")),
            )
        )

    return WazuhSshSummary(
        window=window,
        total=counts.get("all", 0),
        success=counts.get("success", 0),
        failed=counts.get("failed", 0),
        invalidUser=counts.get("invalid_user", 0),
        rootLogin=counts.get("root_login", 0),
        activeSessions=active_sessions,
        topSources=_top_items(metrics.get("ssh_top_sources", []), ("srcip",)),
        topUsers=_top_items(metrics.get("ssh_top_users", []), ("user",)),
        topAgents=_top_items(metrics.get("ssh_top_agents", []), ("agent_name", "name")),
        topRules=_top_items(metrics.get("ssh_top_rules", []), ("rule_id",)),
        recent=recent,
        activeSessionItems=active_session_items,
    )


def build_wazuh_ssh_sessions(samples: list[dict[str, Any]]) -> list[WazuhSshSession]:
    sessions: list[WazuhSshSession] = []
    for sample in samples:
        metric = prom_metric(sample)
        if not any(metric.get(key) for key in ("agent_name", "agent_id", "pid", "user", "srcip")):
            continue
        sessions.append(
            WazuhSshSession(
                agentName=_blank_none(metric.get("agent_name")),
                agentId=_blank_none(metric.get("agent_id")),
                agentIp=_blank_none(metric.get("agent_ip")),
                user=_blank_none(metric.get("user")),
                srcip=_blank_none(metric.get("srcip")),
                srcport=_blank_none(metric.get("srcport")),
                authMethod=_blank_none(metric.get("auth_method")),
                pid=_blank_none(metric.get("pid")),
                openedAt=_blank_none(metric.get("opened_at")),
                durationSec=prom_value(sample),
                state=_blank_none(metric.get("state")),
            )
        )
    return sorted(
        sessions,
        key=lambda session: (-(session.durationSec or 0), session.agentName or "", session.user or ""),
    )


def _build_wazuh_fim(
    window: str,
    metrics: dict[str, list[dict[str, Any]]],
    recent_limit: int,
) -> WazuhFimSummary:
    counts: dict[str, float] = {}
    for sample in metrics.get("fim_counts", []):
        metric = prom_metric(sample)
        event = metric.get("event")
        value = prom_value(sample)
        if event and value > 0:
            counts[event] = counts.get(event, 0) + value

    recent: list[WazuhRecentEvent] = []
    for sample in _ranked_samples(metrics.get("fim_recent", []))[:recent_limit]:
        metric = prom_metric(sample)
        if prom_value(sample) <= 0:
            continue
        recent.append(
            WazuhRecentEvent(
                kind="fim",
                timestamp=_blank_none(metric.get("timestamp")),
                agentName=_blank_none(metric.get("agent_name")),
                agentId=_blank_none(metric.get("agent_id")),
                agentIp=_blank_none(metric.get("agent_ip")),
                user=_blank_none(metric.get("user")),
                event=_blank_none(metric.get("event")),
                path=_blank_none(metric.get("path")),
                mode=_blank_none(metric.get("mode")),
                ruleId=_blank_none(metric.get("rule_id")),
                severity=_blank_none(metric.get("severity")),
                level=_float_label(metric, "level"),
                description=_blank_none(metric.get("description")),
            )
        )

    return WazuhFimSummary(
        window=window,
        keyEvents=sum(counts.values()),
        keyModified=counts.get("modified", 0),
        keyAdded=counts.get("added", 0),
        keyDeleted=counts.get("deleted", 0),
        topPaths=_top_items(metrics.get("fim_top_paths", []), ("path",)),
        topAgents=_top_items(metrics.get("fim_top_agents", []), ("agent_name", "name")),
        topRules=_top_items(metrics.get("fim_top_rules", []), ("rule_id",)),
        recent=recent,
    )


def _wazuh_health(
    *,
    api_up: bool | None,
    indexer_up: bool | None,
    needs_indexer: bool,
    manager_critical_down: float,
    inactive_agents: int,
    rootcheck_total: float,
    alerts: WazuhAlertSummary,
    ssh: WazuhSshSummary,
    fim: WazuhFimSummary,
    stale: bool,
) -> Health:
    if stale:
        return Health.STALE
    if api_up is False or (needs_indexer and indexer_up is False):
        return Health.CRITICAL
    if manager_critical_down > 0 or alerts.severityCounts.get("critical", 0) > 0:
        return Health.CRITICAL
    if (
        inactive_agents > 0
        or rootcheck_total > 0
        or alerts.severityCounts.get("high", 0) > 0
        or ssh.failed > 0
        or ssh.invalidUser > 0
        or ssh.rootLogin > 0
        or fim.keyEvents > 0
    ):
        return Health.WARNING
    if api_up is True:
        return Health.OK
    return Health.UNKNOWN


def _agent_counts(samples: list[dict[str, Any]], agents: list[WazuhAgent]) -> tuple[int, int, int]:
    counts: dict[str, int] = {}
    for sample in samples:
        metric = prom_metric(sample)
        status = metric.get("status")
        if status:
            counts[status] = counts.get(status, 0) + int(prom_value(sample))

    if counts:
        total = sum(counts.values())
        active = counts.get("active", 0)
        return total, active, max(total - active, 0)

    total = len(agents)
    active = sum(1 for agent in agents if agent.status == "active")
    return total, active, max(total - active, 0)


def _samples_by_agent(samples: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {_agent_key(prom_metric(sample)): sample for sample in samples}


def _agent_key(metric: dict[str, str]) -> str:
    return "|".join(
        [
            metric.get("agent_id") or metric.get("id") or "",
            metric.get("name") or metric.get("agent_name") or "",
            metric.get("ip") or metric.get("agent_ip") or "",
        ]
    )


def _top_items(samples: list[dict[str, Any]], label_keys: tuple[str, ...]) -> list[WazuhTopItem]:
    items: list[WazuhTopItem] = []
    for sample in samples:
        value = prom_value(sample)
        if value <= 0:
            continue
        metric = prom_metric(sample)
        label = next((metric[key] for key in label_keys if metric.get(key)), "")
        if not label:
            continue
        items.append(
            WazuhTopItem(
                label=label,
                value=value,
                agentId=_blank_none(metric.get("agent_id")),
                severity=_blank_none(metric.get("severity")),
                level=_float_label(metric, "max_level") or _float_label(metric, "level"),
                description=_blank_none(metric.get("description")),
            )
        )
    return sorted(items, key=lambda item: (-item.value, item.label))


def _ranked_samples(samples: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(samples, key=lambda sample: _int_label(prom_metric(sample), "rank") or 999999)


def _vector_bool(samples: list[dict[str, Any]]) -> bool | None:
    value = vector_scalar(samples)
    if value is None:
        return None
    return value > 0


def _blank_none(value: Any) -> str | None:
    text = "" if value is None else str(value).strip()
    return text or None


def _non_negative(value: float) -> float | None:
    return value if value >= 0 else None


def _int_label(metric: dict[str, str], key: str) -> int | None:
    try:
        return int(float(metric[key]))
    except (KeyError, TypeError, ValueError):
        return None


def _float_label(metric: dict[str, str], key: str) -> float | None:
    try:
        return float(metric[key])
    except (KeyError, TypeError, ValueError):
        return None
