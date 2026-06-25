from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass, field
from typing import Any, Literal

from ..cache import JsonCache, json_ready
from ..clients.prometheus import PrometheusClient
from ..clients.pve import PVEClient, PVEServerConfig
from ..clients.zabbix import ZabbixClient
from ..config import Settings
from ..models import (
    Diagnostics,
    Health,
    LanSummary,
    MachineDetail,
    MachineSecurity,
    Overview,
    Problem,
    PVESummary,
    SourceStatus,
    WazuhAgent,
    WazuhRecentEvent,
    WazuhSummary,
    utc_now,
)
from .normalizer import (
    cpu_value,
    disk_free_percent_value,
    disk_percent_value,
    host_ids_for_machine,
    memory_value,
    normalize_machines,
    normalize_problem,
    safe_id,
    summarize_items,
)
from .grafana_links import build_grafana_integration
from .pve_mapper import build_pve_summary
from .prometheus_mapper import (
    build_lan_summary,
    build_prometheus_problems,
    build_services,
    build_tailnet,
    build_wazuh_ssh_sessions,
    build_wazuh_summary,
    prom_metric,
    prom_value,
)


CACHE_OVERVIEW = "snapshot:overview"
CACHE_ZABBIX = "snapshot:zabbix"
CACHE_PROMETHEUS = "snapshot:prometheus"
CACHE_PVE = "snapshot:pve"
CACHE_WAZUH = "snapshot:wazuh"
CACHE_STATUSES = "snapshot:statuses"


@dataclass
class Collector:
    settings: Settings
    cache: JsonCache
    zabbix: ZabbixClient
    prometheus: PrometheusClient
    pve: PVEClient
    task: asyncio.Task[None] | None = None
    last_snapshot_ms: float | None = None
    last_error: str | None = None
    iteration: int = 0
    wazuh_status: SourceStatus = field(
        default_factory=lambda: SourceStatus(
            source="wazuh",
            ok=False,
            lastError="not collected yet",
        )
    )
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def start(self) -> None:
        if self.task is None:
            self.task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
            self.task = None

    async def _loop(self) -> None:
        while True:
            try:
                await self.refresh()
            except Exception as exc:
                self.last_error = str(exc)
            await asyncio.sleep(self.settings.snapshot_interval_sec)

    async def refresh(self) -> Overview:
        async with self._lock:
            started = time.perf_counter()
            zabbix_task = asyncio.create_task(self._collect_zabbix())
            prometheus_task = asyncio.create_task(self._collect_prometheus())
            pve_task = asyncio.create_task(self._collect_pve())
            wazuh_task = asyncio.create_task(self._collect_wazuh())
            zabbix_data, prometheus_data, pve_summary, wazuh_summary = await asyncio.gather(
                zabbix_task,
                prometheus_task,
                pve_task,
                wazuh_task,
            )

            zabbix_problems: list[Problem] = zabbix_data.get("problems", [])
            prom_problems: list[Problem] = prometheus_data.get("problems", [])
            machines, network_devices = normalize_machines(
                zabbix_data.get("hosts", []),
                zabbix_data.get("items", []),
                zabbix_problems,
                stale=zabbix_data.get("stale", False),
            )
            all_problems = sorted(
                [*zabbix_problems, *prom_problems],
                key=lambda problem: (severity_rank(problem.severity), -problem.ageSec),
            )
            overview = Overview(
                generatedAt=utc_now(),
                stale=zabbix_data.get("stale", False) or prometheus_data.get("stale", False),
                machines=machines,
                networkDevices=network_devices,
                tailnet=prometheus_data["tailnet"],
                services=prometheus_data["services"],
                lan=prometheus_data["lan"],
                pve=pve_summary,
                wazuh=wazuh_summary,
                grafana=build_grafana_integration(self.settings),
                problems=all_problems,
                sourceStatuses=await self.source_statuses(),
                summary={
                    "machineTotal": len(machines),
                    "machineAttention": sum(1 for m in machines if m.health not in {"ok", "unknown"}),
                    "networkTotal": len(network_devices),
                    "networkAttention": sum(1 for d in network_devices if d.health not in {"ok", "unknown"}),
                    "lanOnline": prometheus_data["lan"].onlineDevices,
                    "lanUnknownOnline": prometheus_data["lan"].unknownOnline,
                    "problemTotal": len(all_problems),
                    "pveGuestTotal": pve_summary.totalGuests,
                    "pveRunningGuests": pve_summary.runningGuests,
                    "wazuhInactiveAgents": wazuh_summary.inactiveAgents,
                    "wazuhCriticalAlerts": int(
                        wazuh_summary.alerts.severityCounts.get("critical", 0)
                    ),
                    "wazuhSshFailures": int(
                        wazuh_summary.ssh.failed + wazuh_summary.ssh.invalidUser
                    ),
                    "wazuhFimKeyEvents": int(wazuh_summary.fim.keyEvents),
                    "criticalProblems": sum(
                        1 for p in all_problems if p.severity in {"disaster", "high", "critical"}
                    ),
                },
            )
            await self.cache.set(CACHE_OVERVIEW, json_ready(overview), ttl=self.settings.snapshot_interval_sec * 6)
            await self.cache.set(
                CACHE_STATUSES,
                [status.model_dump(mode="json") for status in overview.sourceStatuses],
                ttl=self.settings.snapshot_interval_sec * 6,
            )
            self.last_snapshot_ms = (time.perf_counter() - started) * 1000
            self.last_error = None
            self.iteration += 1
            return overview

    async def _collect_zabbix(self) -> dict[str, Any]:
        try:
            hosts = await self.zabbix.hosts()
            hostids = [str(host["hostid"]) for host in hosts]
            items_task = asyncio.create_task(self.zabbix.items_for_hosts(hostids))
            problems_task = asyncio.create_task(self.zabbix.problems())
            items, raw_problems = await asyncio.gather(items_task, problems_task)
            trigger_hosts = await self._trigger_host_index(raw_problems)
            enriched_problems = []
            for problem in raw_problems:
                if not problem.get("hosts"):
                    problem = {**problem, "hosts": trigger_hosts.get(str(problem.get("objectid")), [])}
                enriched_problems.append(problem)
            normalized_problems = [normalize_problem(problem) for problem in enriched_problems]
            data = {
                "hosts": hosts,
                "items": items,
                "problems": normalized_problems,
                "stale": False,
                "collectedAt": utc_now().isoformat(),
            }
            cache_data = {
                **data,
                "problems": [problem.model_dump(mode="json") for problem in normalized_problems],
            }
            await self.cache.set(CACHE_ZABBIX, cache_data, ttl=self.settings.snapshot_interval_sec * 10)
            return data
        except Exception as exc:
            self.last_error = str(exc)
            cached = await self.cache.get(CACHE_ZABBIX)
            if cached:
                cached["stale"] = True
                cached["lastError"] = str(exc)
                cached["problems"] = [Problem.model_validate(problem) for problem in cached.get("problems", [])]
                return cached
            return {"hosts": [], "items": [], "problems": [], "stale": True, "lastError": str(exc)}

    async def _trigger_host_index(self, raw_problems: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
        triggerids = sorted(
            {
                str(problem.get("objectid"))
                for problem in raw_problems
                if problem.get("objectid")
            }
        )
        triggers = await self.zabbix.triggers(triggerids)
        return {str(trigger.get("triggerid")): trigger.get("hosts", []) for trigger in triggers}

    async def _collect_prometheus(self) -> dict[str, Any]:
        try:
            (
                tail_online,
                tail_info,
                tail_last_seen,
                routes_available,
                routes_approved,
                api_up,
                db_ok,
                keys,
                probes,
                probe_duration,
                lan_devices,
                targets,
                alerts,
            ) = await asyncio.gather(
                self.prometheus.query("headscale_nodes_online"),
                self.prometheus.query("headscale_nodes_info"),
                self.prometheus.query("headscale_nodes_last_seen_timestamp"),
                self.prometheus.query("headscale_nodes_available_routes"),
                self.prometheus.query("headscale_nodes_approved_routes"),
                self.prometheus.query("max(headscale_up)"),
                self.prometheus.query("max(headscale_health_database_connectivity)"),
                self.prometheus.query("headscale_preauthkeys_expiration_timestamp - time()"),
                self.prometheus.query('probe_success{job=~"blackbox-zabbix-file-sd|blackbox-core-http"}'),
                self.prometheus.query('probe_duration_seconds{job=~"blackbox-zabbix-file-sd|blackbox-core-http"}'),
                self.prometheus.query('watch_your_lan_up{ip!="",mac!=""}'),
                self.prometheus.targets(),
                self.prometheus.alerts(),
            )
            tailnet = build_tailnet(
                tail_online,
                tail_info,
                tail_last_seen,
                routes_available,
                routes_approved,
                api_up,
                db_ok,
                keys,
            )
            services = build_services(probes, probe_duration, targets)
            lan = build_lan_summary(lan_devices)
            problems = build_prometheus_problems(alerts)
            data = {
                "tailnet": tailnet.model_dump(mode="json"),
                "services": services.model_dump(mode="json"),
                "lan": lan.model_dump(mode="json"),
                "problems": [problem.model_dump(mode="json") for problem in problems],
                "stale": False,
                "collectedAt": utc_now().isoformat(),
            }
            await self.cache.set(CACHE_PROMETHEUS, data, ttl=self.settings.snapshot_interval_sec * 10)
            return {
                "tailnet": tailnet,
                "services": services,
                "lan": lan,
                "problems": problems,
                "stale": False,
            }
        except Exception as exc:
            self.last_error = str(exc)
            cached = await self.cache.get(CACHE_PROMETHEUS)
            if cached:
                tailnet = build_tailnet([], [], [], [], [], [], [], [], stale=True)
                services = build_services([], [], [], stale=True)
                lan = build_lan_summary([], stale=True)
                if cached.get("tailnet"):
                    from ..models import TailnetSummary

                    tailnet = TailnetSummary.model_validate({**cached["tailnet"], "stale": True, "health": "stale"})
                if cached.get("services"):
                    from ..models import ServicesSummary

                    services = ServicesSummary.model_validate(
                        {**cached["services"], "stale": True, "health": "stale"}
                    )
                if cached.get("lan"):
                    from ..models import LanSummary

                    lan = LanSummary.model_validate({**cached["lan"], "stale": True, "health": "stale"})
                return {
                    "tailnet": tailnet,
                    "services": services,
                    "lan": lan,
                    "problems": [Problem.model_validate(problem) for problem in cached.get("problems", [])],
                    "stale": True,
                    "lastError": str(exc),
                }
            return {
                "tailnet": build_tailnet([], [], [], [], [], [], [], [], stale=True),
                "services": build_services([], [], [], stale=True),
                "lan": build_lan_summary([], stale=True),
                "problems": [],
                "stale": True,
                "lastError": str(exc),
            }

    async def _collect_wazuh(self) -> WazuhSummary:
        if not self.settings.ctm_wazuh_enabled:
            self.wazuh_status = SourceStatus(source="wazuh", ok=False, lastError="disabled")
            return build_wazuh_summary(
                enabled=False,
                modules=set(),
                window=self.settings.ctm_wazuh_window,
                metrics={},
            )

        modules = self.settings.wazuh_modules()
        query_map = self._wazuh_queries(modules)
        metrics: dict[str, list[dict[str, Any]]] = {}
        try:
            results = await asyncio.gather(
                *(self.prometheus.query(expr) for expr in query_map.values())
            )
            metrics = dict(zip(query_map.keys(), results, strict=True))
            summary = build_wazuh_summary(
                enabled=True,
                modules=modules,
                window=self.settings.ctm_wazuh_window,
                metrics=metrics,
                recent_limit=self.settings.ctm_wazuh_recent_limit,
            )
            needs_indexer = bool(modules & {"alerts", "ssh", "fim"})
            ok = summary.apiUp is True and (not needs_indexer or summary.indexerUp is True)
            self.wazuh_status = SourceStatus(
                source="wazuh",
                ok=ok,
                lastSuccessAt=utc_now() if ok else self.wazuh_status.lastSuccessAt,
                lastError=None if ok else "Wazuh exporter or indexer is down",
            )
            await self.cache.set(
                CACHE_WAZUH,
                summary.model_dump(mode="json"),
                ttl=self.settings.snapshot_interval_sec * 10,
            )
            return summary
        except Exception as exc:
            cached = await self.cache.get(CACHE_WAZUH)
            self.wazuh_status = SourceStatus(
                source="wazuh",
                ok=False,
                lastSuccessAt=self.wazuh_status.lastSuccessAt,
                lastError=str(exc),
            )
            if cached:
                return WazuhSummary.model_validate(
                    {**cached, "stale": True, "health": "stale"}
                )
            return build_wazuh_summary(
                enabled=True,
                modules=modules,
                window=self.settings.ctm_wazuh_window,
                metrics=metrics,
                stale=True,
                recent_limit=self.settings.ctm_wazuh_recent_limit,
            )

    def _wazuh_queries(self, modules: set[str]) -> dict[str, str]:
        window = self.settings.ctm_wazuh_window
        top = max(1, self.settings.ctm_wazuh_top_limit)
        queries = {
            "api_up": "max(ctm_wazuh_api_up) or vector(0)",
            "agents_status": "ctm_wazuh_agents_status",
            "manager_critical_down": (
                'sum(1 - ctm_wazuh_manager_process_status{critical="true"}) or vector(0)'
            ),
        }

        if modules & {"alerts", "ssh", "fim"}:
            queries["indexer_up"] = "max(ctm_wazuh_indexer_up) or vector(0)"

        if "agents" in modules:
            queries.update(
                {
                    "agent_status": "ctm_wazuh_agent_status",
                    "agent_keepalive": "ctm_wazuh_agent_last_keepalive_timestamp_seconds",
                    "agent_group_sync": "ctm_wazuh_agent_group_config_synced",
                    "rootcheck_outstanding": (
                        'ctm_wazuh_rootcheck_findings_total{finding_status="outstanding"}'
                    ),
                    "syscheck_findings": "ctm_wazuh_syscheck_findings_total",
                }
            )

        if "alerts" in modules:
            queries.update(
                {
                    "alert_counts": (
                        f'sum by (severity) '
                        f'(ctm_wazuh_alerts_total{{window="{window}"}}) or vector(0)'
                    ),
                    "alert_top_agents": (
                        f'topk({top}, ctm_wazuh_alerts_agent_top{{window="{window}"}})'
                    ),
                    "alert_top_rules": (
                        f'topk({top}, ctm_wazuh_alerts_rule_top{{window="{window}"}})'
                    ),
                    "alert_top_tactics": (
                        f'topk({top}, ctm_wazuh_alerts_mitre_tactic_top{{window="{window}"}})'
                    ),
                }
            )

        if "ssh" in modules:
            queries.update(
                {
                    "ssh_counts": (
                        f'sum by (outcome) '
                        f'(ctm_wazuh_ssh_events_total{{window="{window}"}}) or vector(0)'
                    ),
                    "ssh_top_sources": (
                        f'topk({top}, '
                        f'ctm_wazuh_ssh_source_top{{window="{window}",outcome="all"}})'
                    ),
                    "ssh_top_users": (
                        f'topk({top}, '
                        f'ctm_wazuh_ssh_user_top{{window="{window}",outcome="all"}})'
                    ),
                    "ssh_top_agents": (
                        f'topk({top}, '
                        f'ctm_wazuh_ssh_agent_top{{window="{window}",outcome="all"}})'
                    ),
                    "ssh_top_rules": (
                        f'topk({top}, '
                        f'ctm_wazuh_ssh_rule_top{{window="{window}",outcome="all"}})'
                    ),
                    "ssh_recent": "ctm_wazuh_ssh_recent_event",
                    "ssh_active_sessions": "ctm_wazuh_ssh_active_session_duration_seconds",
                }
            )

        if "fim" in modules:
            queries.update(
                {
                    "fim_counts": (
                        f'sum by (event) '
                        f'(ctm_wazuh_fim_events_total{{window="{window}",scope="key"}}) '
                        "or vector(0)"
                    ),
                    "fim_top_paths": (
                        f'topk({top}, '
                        f'ctm_wazuh_fim_path_top{{window="{window}",scope="key"}})'
                    ),
                    "fim_top_agents": (
                        f'topk({top}, '
                        f'ctm_wazuh_fim_agent_top{{window="{window}",scope="key"}})'
                    ),
                    "fim_top_rules": (
                        f'topk({top}, '
                        f'ctm_wazuh_fim_rule_top{{window="{window}",scope="key"}})'
                    ),
                    "fim_recent": "ctm_wazuh_fim_recent_event",
                }
            )

        return queries

    async def _collect_pve(self) -> PVESummary:
        try:
            servers = self.pve.servers()
        except Exception as exc:
            self.pve.mark_error(str(exc))
            return build_pve_summary(configured=False, collected=[], errors=[])
        if not servers:
            self.pve.mark_error("not configured")
            summary = build_pve_summary(configured=False, collected=[], errors=[])
            await self.cache.set(CACHE_PVE, summary.model_dump(mode="json"), ttl=self.settings.snapshot_interval_sec * 10)
            return summary

        semaphore = asyncio.Semaphore(max(1, self.settings.pve_concurrency))

        async def collect_one(server: PVEServerConfig) -> tuple[dict[str, Any] | None, tuple[PVEServerConfig, str] | None]:
            async with semaphore:
                try:
                    return await self.pve.collect_server(server), None
                except Exception as exc:
                    return None, (server, str(exc))

        results = await asyncio.gather(*(collect_one(server) for server in servers))
        collected = [result for result, _ in results if result is not None]
        errors = [error for _, error in results if error is not None]
        summary = build_pve_summary(configured=True, collected=collected, errors=errors)
        if errors:
            self.pve.mark_error("; ".join(f"{server.name}: {error}" for server, error in errors))
        else:
            self.pve.mark_ok(avg_latency(collected))
        await self.cache.set(CACHE_PVE, summary.model_dump(mode="json"), ttl=self.settings.snapshot_interval_sec * 10)
        return summary

    async def get_overview(self) -> Overview:
        cached = await self.cache.get(CACHE_OVERVIEW)
        if cached:
            return Overview.model_validate(cached)
        return await self.refresh()

    async def get_pve(self) -> PVESummary:
        cached = await self.cache.get(CACHE_PVE)
        if cached:
            return PVESummary.model_validate(cached)
        overview = await self.get_overview()
        return overview.pve

    async def get_wazuh(self) -> WazuhSummary:
        cached = await self.cache.get(CACHE_WAZUH)
        if cached:
            return WazuhSummary.model_validate(cached)
        overview = await self.get_overview()
        return overview.wazuh

    async def get_lan(self) -> LanSummary:
        cached = await self.cache.get(CACHE_PROMETHEUS)
        if cached and cached.get("lan"):
            return LanSummary.model_validate(cached["lan"])
        overview = await self.get_overview()
        return overview.lan

    async def get_machine_detail(self, machine_id: str) -> MachineDetail:
        overview = await self.get_overview()
        machine = next((item for item in overview.machines if item.id == machine_id), None)
        if not machine:
            raise KeyError(machine_id)
        zabbix_data = await self.cache.get(CACHE_ZABBIX) or {}
        hosts = zabbix_data.get("hosts", [])
        items = zabbix_data.get("items", [])
        ids = host_ids_for_machine(hosts, machine_id)
        standalone_ids = {value for key, value in ids.items() if key.startswith("standalone:")}
        sys_hostids = ({ids["sys"]} if ids.get("sys") else set()) | standalone_ids
        sys_items = [item for item in items if str(item.get("hostid")) in sys_hostids]
        phy_items = [item for item in items if str(item.get("hostid")) == ids.get("phy")]
        machine_hosts = [host for host in hosts if str(host.get("hostid")) in set(ids.values())]
        security = await self._machine_security(
            machine,
            machine_hosts,
            [*sys_items, *phy_items],
            overview.wazuh,
        )
        return MachineDetail(
            machine=machine,
            systemItems=compact_items(sys_items),
            hardwareItems=compact_items(phy_items),
            problems=machine.problems,
            security=security,
        )

    async def _machine_security(
        self,
        machine: Any,
        hosts: list[dict[str, Any]],
        items: list[dict[str, Any]],
        wazuh: WazuhSummary,
    ) -> MachineSecurity:
        if not self.settings.ctm_wazuh_enabled or not wazuh.enabled:
            return MachineSecurity(
                enabled=False,
                health=Health.UNKNOWN,
                notes=["Wazuh 未启用"],
            )

        names, normalized_names, ips = machine_match_terms(machine, hosts, items)
        matched_agents = [
            agent
            for agent in wazuh.agents
            if agent_matches_machine(agent, names, normalized_names, ips)
        ]

        agent_names = sorted({agent.name for agent in matched_agents if agent.name} | names)
        agent_regex = prom_label_regex(agent_names)
        if not agent_regex:
            return MachineSecurity(
                enabled=True,
                health=Health.UNKNOWN,
                matchedAgents=matched_agents,
                stale=wazuh.stale,
                notes=["Wazuh Agent 缺少可查询名称"],
            )

        window = self.settings.ctm_wazuh_window
        queries = {
            "alert_counts": (
                f'sum by (severity) '
                f'(ctm_wazuh_alerts_agent_top{{window="{window}",agent_name=~"{agent_regex}"}}) '
                "or on() vector(0)"
            ),
            "ssh_counts": (
                f'sum by (outcome) '
                f'(ctm_wazuh_ssh_agent_top{{window="{window}",agent_name=~"{agent_regex}"}}) '
                "or on() vector(0)"
            ),
            "fim_counts": (
                f'sum by (event) '
                f'(ctm_wazuh_fim_agent_top{{window="{window}",scope="key",agent_name=~"{agent_regex}"}}) '
                "or on() vector(0)"
            ),
            "active_sessions": (
                f'ctm_wazuh_ssh_active_session_duration_seconds{{agent_name=~"{agent_regex}"}} '
                "or on() vector(0)"
            ),
            "ssh_recent": (
                f'ctm_wazuh_ssh_recent_event{{agent_name=~"{agent_regex}"}} '
                "or on() vector(0)"
            ),
            "fim_recent": (
                f'ctm_wazuh_fim_recent_event{{agent_name=~"{agent_regex}"}} '
                "or on() vector(0)"
            ),
        }

        try:
            results = await asyncio.gather(
                *(self.prometheus.query(expr) for expr in queries.values())
            )
            metrics = dict(zip(queries.keys(), results, strict=True))
        except Exception as exc:
            return MachineSecurity(
                enabled=True,
                health=Health.STALE,
                matchedAgents=matched_agents,
                stale=True,
                notes=[f"Wazuh 机器安全查询失败: {exc}"],
            )

        alert_counts = counts_by_label(metrics["alert_counts"], "severity")
        ssh_counts = counts_by_label(metrics["ssh_counts"], "outcome")
        fim_counts = counts_by_label(metrics["fim_counts"], "event")
        active_sessions = build_wazuh_ssh_sessions(metrics["active_sessions"])
        recent_events = [
            *recent_events_from_samples(metrics["ssh_recent"], "ssh"),
            *recent_events_from_samples(metrics["fim_recent"], "fim"),
        ]
        recent_events.sort(key=lambda event: event.timestamp or "", reverse=True)
        matched_agents = merge_wazuh_agents(
            matched_agents,
            [
                *metrics["alert_counts"],
                *metrics["ssh_counts"],
                *metrics["fim_counts"],
                *metrics["active_sessions"],
                *metrics["ssh_recent"],
                *metrics["fim_recent"],
            ],
        )

        has_security_data = bool(
            matched_agents
            or alert_counts
            or any(value > 0 for value in ssh_counts.values())
            or any(value > 0 for value in fim_counts.values())
            or active_sessions
            or recent_events
        )
        if not has_security_data:
            return MachineSecurity(
                enabled=True,
                health=Health.UNKNOWN if not wazuh.stale else Health.STALE,
                stale=wazuh.stale,
                notes=["未匹配到 Wazuh Agent"],
            )

        security = MachineSecurity(
            enabled=True,
            matchedAgents=matched_agents,
            alertSeverityCounts=alert_counts,
            sshTotal=ssh_counts.get("all", 0),
            sshSuccess=ssh_counts.get("success", 0),
            sshFailed=ssh_counts.get("failed", 0),
            sshInvalidUser=ssh_counts.get("invalid_user", 0),
            sshRootLogin=ssh_counts.get("root_login", 0),
            sshActiveSessions=len(active_sessions),
            fimKeyEvents=sum(fim_counts.values()),
            fimModified=fim_counts.get("modified", 0),
            fimAdded=fim_counts.get("added", 0),
            fimDeleted=fim_counts.get("deleted", 0),
            activeSessions=active_sessions,
            recentEvents=recent_events[: self.settings.ctm_wazuh_recent_limit],
            stale=wazuh.stale,
            notes=[
                "按 Zabbix 主机名、接口 IP 与系统主机名匹配 Wazuh Agent",
                f"统计窗口 {window}",
            ],
        )
        security.health = machine_security_health(security)
        return security

    async def get_machine_series(
        self, machine_id: str, range_name: Literal["1h", "6h", "24h"]
    ) -> dict[str, Any]:
        cache_key = f"series:{machine_id}:{range_name}"
        cached = await self.cache.get(cache_key)
        if cached:
            return cached
        seconds = {"1h": 3600, "6h": 21600, "24h": 86400}[range_name]
        time_till = int(time.time())
        time_from = time_till - seconds
        zabbix_data = await self.cache.get(CACHE_ZABBIX) or {}
        hosts = zabbix_data.get("hosts", [])
        items = zabbix_data.get("items", [])
        ids = host_ids_for_machine(hosts, machine_id)
        machine_hostids = set(ids.values())
        candidate_items = [
            item
            for item in items
            if str(item.get("hostid")) in machine_hostids
            and series_metric_name(item) is not None
        ]
        points_by_clock: dict[int, dict[str, Any]] = {}
        for item in select_series_items(candidate_items):
            metric_name = series_metric_name(item)
            if not metric_name:
                continue
            history_type = int(item.get("value_type") or 0)
            rows = await self.zabbix.history(
                [str(item["itemid"])],
                history_type=history_type,
                time_from=time_from,
                time_till=time_till,
                limit=1500,
            )
            for row in rows:
                clock = int(float(row["clock"]))
                bucket = clock - (clock % 60)
                points_by_clock.setdefault(bucket, {"t": bucket})
                value = series_metric_value(item, row["value"], metric_name)
                if value is None:
                    continue
                points_by_clock[bucket][metric_name] = aggregate_metric(
                    points_by_clock[bucket].get(metric_name), value, metric_name
                )
        result = {"machineId": machine_id, "range": range_name, "points": list(points_by_clock.values())}
        result["points"].sort(key=lambda point: point["t"])
        await self.cache.set(cache_key, result, ttl=self.settings.series_cache_ttl_sec)
        return result

    async def diagnostics(self) -> Diagnostics:
        cache_info: dict[str, Any] = {}
        try:
            cache_info = await self.cache.info_memory()
            cache_info["ok"] = await self.cache.ping()
        except Exception as exc:
            cache_info = {"ok": False, "lastError": str(exc)}
        return Diagnostics(
            sourceStatuses=await self.source_statuses(),
            cache=cache_info,
            collector={
                "iteration": self.iteration,
                "lastSnapshotMs": self.last_snapshot_ms,
                "lastError": self.last_error,
                "snapshotIntervalSec": self.settings.snapshot_interval_sec,
                "seriesCacheTtlSec": self.settings.series_cache_ttl_sec,
            },
        )

    async def source_statuses(self) -> list[SourceStatus]:
        mysql_status = SourceStatus(source="mysql", ok=False)
        try:
            started = time.perf_counter()
            await self.cache.ping()
            mysql_status = SourceStatus(
                source="mysql",
                ok=True,
                latencyMs=(time.perf_counter() - started) * 1000,
                lastSuccessAt=utc_now(),
            )
        except Exception as exc:
            mysql_status = SourceStatus(source="mysql", ok=False, lastError=str(exc))
        statuses = [self.zabbix.status, self.prometheus.status, mysql_status]
        try:
            if self.pve.servers():
                statuses.append(self.pve.status)
        except Exception as exc:
            statuses.append(SourceStatus(source="pve", ok=False, lastError=str(exc)))
        if self.settings.ctm_wazuh_enabled:
            statuses.append(self.wazuh_status)
        return statuses


def severity_rank(severity: str) -> int:
    order = {
        "disaster": 0,
        "critical": 0,
        "high": 1,
        "average": 2,
        "warning": 3,
        "pending": 4,
        "info": 5,
        "information": 5,
    }
    return order.get(severity, 6)


def avg_latency(items: list[dict[str, Any]]) -> float | None:
    values = [float(item["latencyMs"]) for item in items if item.get("latencyMs") is not None]
    if not values:
        return None
    return sum(values) / len(values)


def compact_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for item in items:
        result.append(
            {
                "itemid": item.get("itemid"),
                "name": item.get("name"),
                "key": item.get("key_"),
                "lastvalue": item.get("lastvalue"),
                "units": item.get("units"),
                "lastclock": item.get("lastclock"),
            }
        )
    return result[:300]


IDENTITY_ITEM_KEYS = {
    "agent.hostname",
    "system.hostname",
    "system.name",
}
IGNORED_IDENTITY_VALUES = {
    "localhost",
    "localhost.localdomain",
    "unknown",
    "none",
    "null",
    "n/a",
}


def machine_match_terms(
    machine: Any,
    hosts: list[dict[str, Any]],
    items: list[dict[str, Any]] | None = None,
) -> tuple[set[str], set[str], set[str]]:
    names = set(expand_match_name(str(machine.id)))
    for value in (machine.sysHost, machine.phyHost):
        if value:
            names.update(expand_match_name(str(value)))
    ips: set[str] = set()

    for host in hosts:
        for key in ("host", "name"):
            value = str(host.get(key) or "").strip()
            if value:
                names.update(expand_match_name(value))
        for interface in host.get("interfaces") or []:
            for key in ("ip", "dns"):
                value = str(interface.get(key) or "").strip()
                if value and value != "127.0.0.1":
                    ips.add(value)

    for item in items or []:
        for value in item_identity_names(item):
            names.update(expand_match_name(value))

    expanded = set(names)
    for name in names:
        lowered = name.lower()
        match = re.match(r"^(sys|phy)[_\s-]+(.+)$", lowered)
        if match:
            expanded.update(expand_match_name(match.group(2)))
    normalized = {safe_id(name) for name in expanded if name}
    return {name.lower() for name in expanded if name}, normalized, ips


def expand_match_name(value: str) -> set[str]:
    value = value.strip()
    if not value:
        return set()
    lowered = value.lower()
    if lowered in IGNORED_IDENTITY_VALUES:
        return set()

    names = {value}
    normalized = safe_id(value)
    if normalized:
        names.add(normalized)

    match = re.fullmatch(r"s(\d{1,3})", normalized, flags=re.IGNORECASE)
    if match:
        number = int(match.group(1))
        names.add(f"server{number:02d}")
        names.add(f"server{number}")

    return names


def item_identity_names(item: dict[str, Any]) -> set[str]:
    key = str(item.get("key_") or item.get("key") or "").strip()
    value = str(item.get("lastvalue") or "").strip()
    if not value:
        return set()

    names: set[str] = set()
    if key in IDENTITY_ITEM_KEYS:
        names.add(value)
    elif key.startswith("system.uname"):
        match = re.match(r"Linux\s+(\S+)", value, flags=re.IGNORECASE)
        if match:
            names.add(match.group(1))
    elif key.startswith("system.descr"):
        match = re.match(r"Linux\s+(\S+)", value, flags=re.IGNORECASE)
        if match:
            names.add(match.group(1))

    return {name for name in names if safe_id(name) not in IGNORED_IDENTITY_VALUES}


def agent_matches_machine(agent: Any, names: set[str], normalized_names: set[str], ips: set[str]) -> bool:
    agent_name = str(agent.name or "").strip()
    agent_ip = str(agent.ip or "").strip()
    if agent_ip and agent_ip in ips:
        return True
    if agent_name.lower() in names:
        return True
    normalized_agent = safe_id(agent_name)
    if normalized_agent in normalized_names:
        return True
    match = re.match(r"^(sys|phy)[_\s-]+(.+)$", agent_name, flags=re.IGNORECASE)
    return bool(match and safe_id(match.group(2)) in normalized_names)


def prom_label_regex(values: list[str]) -> str:
    clean = [value for value in values if value]
    if not clean:
        return ""
    pattern = "|".join(re.escape(value) for value in clean)
    pattern = f"(?i)(?:{pattern})"
    return pattern.replace("\\", "\\\\").replace('"', '\\"')


def merge_wazuh_agents(
    agents: list[WazuhAgent],
    samples: list[dict[str, Any]],
) -> list[WazuhAgent]:
    merged: dict[str, WazuhAgent] = {agent.name.lower(): agent for agent in agents if agent.name}
    for sample in samples:
        if prom_value(sample) <= 0:
            continue
        metric = prom_metric(sample)
        name = blank_none(metric.get("agent_name")) or blank_none(metric.get("name"))
        if not name or name.lower() in merged:
            continue
        agent_id = blank_none(metric.get("agent_id")) or safe_id(name)
        merged[name.lower()] = WazuhAgent(
            id=agent_id,
            name=name,
            ip=blank_none(metric.get("agent_ip")) or blank_none(metric.get("ip")),
            status="historical",
        )
    return sorted(merged.values(), key=lambda agent: (agent.status != "active", agent.name.lower()))



def counts_by_label(samples: list[dict[str, Any]], label: str) -> dict[str, float]:
    counts: dict[str, float] = {}
    for sample in samples:
        metric = prom_metric(sample)
        key = metric.get(label)
        value = prom_value(sample)
        if key and value > 0:
            counts[key] = counts.get(key, 0) + value
    return counts


def recent_events_from_samples(samples: list[dict[str, Any]], kind: Literal["ssh", "fim"]) -> list[WazuhRecentEvent]:
    events: list[WazuhRecentEvent] = []
    for sample in sorted(samples, key=lambda item: event_rank(prom_metric(item))):
        metric = prom_metric(sample)
        if prom_value(sample) <= 0 or not metric.get("agent_name"):
            continue
        events.append(
            WazuhRecentEvent(
                kind=kind,
                timestamp=blank_none(metric.get("timestamp")),
                agentName=blank_none(metric.get("agent_name")),
                agentId=blank_none(metric.get("agent_id")),
                agentIp=blank_none(metric.get("agent_ip")),
                srcip=blank_none(metric.get("srcip")),
                user=blank_none(metric.get("user")),
                outcome=blank_none(metric.get("outcome")),
                event=blank_none(metric.get("event")),
                path=blank_none(metric.get("path")),
                mode=blank_none(metric.get("mode")),
                ruleId=blank_none(metric.get("rule_id")),
                severity=blank_none(metric.get("severity")),
                level=float_label(metric, "level"),
                description=blank_none(metric.get("description")),
            )
        )
    return events


def event_rank(metric: dict[str, str]) -> int:
    try:
        return int(float(metric.get("rank", "999999")))
    except (TypeError, ValueError):
        return 999999


def float_label(metric: dict[str, str], key: str) -> float | None:
    try:
        return float(metric[key])
    except (KeyError, TypeError, ValueError):
        return None


def blank_none(value: Any) -> str | None:
    text = "" if value is None else str(value).strip()
    return text or None


def machine_security_health(security: MachineSecurity) -> Health:
    if security.stale:
        return Health.STALE
    if not security.enabled:
        return Health.UNKNOWN
    if not security.matchedAgents:
        return Health.UNKNOWN
    if any(agent.status != "active" for agent in security.matchedAgents):
        return Health.WARNING
    if (
        security.alertSeverityCounts.get("critical", 0) > 0
        or security.sshRootLogin > 0
        or any(session.user == "root" for session in security.activeSessions)
    ):
        return Health.CRITICAL
    if (
        security.alertSeverityCounts.get("high", 0) > 0
        or security.sshFailed > 0
        or security.sshInvalidUser > 0
        or security.fimKeyEvents > 0
        or any((agent.rootcheckOutstanding or 0) > 0 for agent in security.matchedAgents)
    ):
        return Health.WARNING
    return Health.OK


def series_metric_name(item: dict[str, Any]) -> str | None:
    metrics = summarize_items([item])
    if metrics.cpu:
        return "cpuPct"
    if metrics.mem:
        return "memPct"
    if metrics.disk:
        return "diskPct"
    if metrics.net:
        return "netBps"
    if metrics.temp:
        return "maxTempC"
    if metrics.fan:
        return "fanRpm"
    return None


def select_series_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {
        "cpuPct": [],
        "memPct": [],
        "diskPct": [],
        "netBps": [],
        "maxTempC": [],
        "fanRpm": [],
    }
    for item in items:
        metric_name = series_metric_name(item)
        if metric_name:
            grouped[metric_name].append(item)

    limits = {
        "cpuPct": 8,
        "memPct": 4,
        "diskPct": 10,
        "netBps": 10,
        "maxTempC": 8,
        "fanRpm": 4,
    }
    selected: list[dict[str, Any]] = []
    for metric_name in ["cpuPct", "memPct", "diskPct", "netBps", "maxTempC", "fanRpm"]:
        ranked = sorted(
            grouped[metric_name],
            key=lambda item, metric=metric_name: series_item_priority(item, metric),
        )
        selected.extend(ranked[: limits[metric_name]])
    return selected


def series_metric_value(item: dict[str, Any], raw_value: Any, metric_name: str) -> float | None:
    value_item = {**item, "lastvalue": raw_value}
    if metric_name == "cpuPct":
        return cpu_value(value_item)
    if metric_name == "memPct":
        return memory_value(value_item)
    if metric_name == "diskPct":
        disk_pct = disk_percent_value(value_item)
        if disk_pct is not None:
            return disk_pct
        free_pct = disk_free_percent_value(value_item)
        if free_pct is not None:
            return max(0, min(100, 100 - free_pct))
        return None
    try:
        value = float(raw_value)
    except (TypeError, ValueError):
        return None
    return value


def series_item_priority(item: dict[str, Any], metric_name: str) -> tuple[int, str]:
    text = f"{item.get('name', '')} {item.get('key_', '')}".lower()
    key = str(item.get("key_") or "").lower()

    if metric_name == "cpuPct":
        if "utilization" in text or "system.cpu.util" in key:
            return (0, text)
        return (5, text)
    if metric_name == "memPct":
        if "memory utilization" in text or "vm.memory.util" in key:
            return (0, text)
        if "pavailable" in key or "pused" in key:
            return (1, text)
        return (5, text)
    if metric_name == "diskPct":
        if ",pused" in key or "pused]" in key:
            if "[/," in key or "[c:," in key:
                return (0, text)
            return (1, text)
        return (5, text)
    if metric_name == "netBps":
        if any(token in text for token in ["docker", "veth", "loopback", "lo:"]):
            return (8, text)
        return (0, text)
    return (0, text)


def aggregate_metric(current: float | None, value: float, metric_name: str) -> float:
    if current is None:
        return value
    if metric_name in {"diskPct", "maxTempC", "fanRpm"}:
        return max(current, value)
    if metric_name == "netBps":
        return current + value
    return (current + value) / 2
