from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Health(StrEnum):
    OK = "ok"
    WARNING = "warning"
    CRITICAL = "critical"
    OFFLINE = "offline"
    STALE = "stale"
    UNKNOWN = "unknown"


class SourceName(StrEnum):
    ZABBIX = "zabbix"
    PROMETHEUS = "prometheus"
    MYSQL = "mysql"
    COLLECTOR = "collector"
    WAZUH = "wazuh"


class Problem(BaseModel):
    source: Literal["zabbix", "prometheus"]
    severity: str
    host: str
    name: str
    ageSec: int = 0
    eventId: str
    acknowledged: bool = False


class Machine(BaseModel):
    id: str
    sysHost: str | None = None
    phyHost: str | None = None
    mode: Literal["paired", "standalone", "sys-only", "phy-only"] = "standalone"
    health: Health = Health.UNKNOWN
    osName: str | None = None
    cpuModel: str | None = None
    cpuCores: float | None = None
    cpuPct: float | None = None
    memPct: float | None = None
    memBytes: float | None = None
    maxMemBytes: float | None = None
    diskPct: float | None = None
    diskBytes: float | None = None
    maxDiskBytes: float | None = None
    netBps: float | None = None
    uptimeSec: float | None = None
    maxTempC: float | None = None
    fanRpm: float | None = None
    agentUp: bool | None = None
    problems: list[Problem] = Field(default_factory=list)
    updatedAt: datetime = Field(default_factory=utc_now)
    stale: bool = False


class NetworkDevice(BaseModel):
    id: str
    host: str
    health: Health = Health.UNKNOWN
    uptimeSec: float | None = None
    netBps: float | None = None
    problems: list[Problem] = Field(default_factory=list)
    updatedAt: datetime = Field(default_factory=utc_now)
    stale: bool = False


class TailnetNode(BaseModel):
    id: str
    name: str
    user: str | None = None
    online: bool
    lastSeenAgeSec: float | None = None
    availableRoutes: float | None = None
    approvedRoutes: float | None = None


class TailnetKey(BaseModel):
    user: str | None = None
    reusable: str | None = None
    expiresInSec: float | None = None


class TailnetSummary(BaseModel):
    health: Health = Health.UNKNOWN
    apiUp: bool | None = None
    databaseOk: bool | None = None
    totalNodes: int = 0
    onlineNodes: int = 0
    offlineNodes: int = 0
    routeDelta: float = 0
    expiringKeys: int = 0
    nodes: list[TailnetNode] = Field(default_factory=list)
    keys: list[TailnetKey] = Field(default_factory=list)
    updatedAt: datetime = Field(default_factory=utc_now)
    stale: bool = False


class ServiceProbe(BaseModel):
    id: str
    job: str
    instance: str
    target: str | None = None
    name: str | None = None
    group: str | None = None
    ifaceType: str | None = None
    success: bool
    durationSec: float | None = None


class PrometheusTarget(BaseModel):
    id: str
    job: str | None = None
    scrapeUrl: str
    health: str
    lastScrape: str | None = None
    lastError: str | None = None


class ServicesSummary(BaseModel):
    health: Health = Health.UNKNOWN
    probeTotal: int = 0
    probeFailed: int = 0
    targetTotal: int = 0
    targetDown: int = 0
    probes: list[ServiceProbe] = Field(default_factory=list)
    targets: list[PrometheusTarget] = Field(default_factory=list)
    updatedAt: datetime = Field(default_factory=utc_now)
    stale: bool = False


class LanDevice(BaseModel):
    id: str
    ip: str
    mac: str
    name: str | None = None
    iface: str | None = None
    known: bool = False
    online: bool = False
    health: Health = Health.UNKNOWN


class LanSummary(BaseModel):
    health: Health = Health.UNKNOWN
    totalDevices: int = 0
    onlineDevices: int = 0
    knownDevices: int = 0
    unknownDevices: int = 0
    knownOnline: int = 0
    unknownOnline: int = 0
    interfaces: list[str] = Field(default_factory=list)
    devices: list[LanDevice] = Field(default_factory=list)
    updatedAt: datetime = Field(default_factory=utc_now)
    stale: bool = False


class PVEResource(BaseModel):
    id: str
    server: str
    node: str
    vmid: int
    type: Literal["qemu", "lxc"]
    name: str
    status: str = "unknown"
    cpuPct: float | None = None
    cpus: float | None = None
    memBytes: float | None = None
    maxMemBytes: float | None = None
    diskBytes: float | None = None
    maxDiskBytes: float | None = None
    uptimeSec: float | None = None
    template: bool = False


class PVENode(BaseModel):
    id: str
    server: str
    node: str
    status: str = "unknown"
    cpuPct: float | None = None
    memBytes: float | None = None
    maxMemBytes: float | None = None
    diskBytes: float | None = None
    maxDiskBytes: float | None = None
    uptimeSec: float | None = None


class PVEServerStatus(BaseModel):
    name: str
    host: str
    ok: bool
    latencyMs: float | None = None
    version: str | None = None
    lastError: str | None = None


class PVESummary(BaseModel):
    health: Health = Health.UNKNOWN
    configured: bool = False
    totalServers: int = 0
    onlineServers: int = 0
    totalNodes: int = 0
    onlineNodes: int = 0
    totalGuests: int = 0
    runningGuests: int = 0
    qemuGuests: int = 0
    lxcGuests: int = 0
    cpuPct: float | None = None
    memPct: float | None = None
    diskPct: float | None = None
    nodes: list[PVENode] = Field(default_factory=list)
    guests: list[PVEResource] = Field(default_factory=list)
    serverStatuses: list[PVEServerStatus] = Field(default_factory=list)
    updatedAt: datetime = Field(default_factory=utc_now)
    stale: bool = False


class WazuhTopItem(BaseModel):
    label: str
    value: float = 0
    agentId: str | None = None
    severity: str | None = None
    level: float | None = None
    description: str | None = None


class WazuhAgent(BaseModel):
    id: str
    name: str
    ip: str | None = None
    status: str = "unknown"
    osName: str | None = None
    osVersion: str | None = None
    manager: str | None = None
    node: str | None = None
    lastKeepaliveAgeSec: float | None = None
    groupConfigSynced: bool | None = None
    rootcheckOutstanding: float | None = None
    syscheckFindings: float | None = None


class WazuhRecentEvent(BaseModel):
    kind: Literal["ssh", "fim"]
    timestamp: str | None = None
    agentName: str | None = None
    agentId: str | None = None
    agentIp: str | None = None
    srcip: str | None = None
    user: str | None = None
    outcome: str | None = None
    event: str | None = None
    path: str | None = None
    mode: str | None = None
    ruleId: str | None = None
    severity: str | None = None
    level: float | None = None
    description: str | None = None


class WazuhSshSession(BaseModel):
    agentName: str | None = None
    agentId: str | None = None
    agentIp: str | None = None
    user: str | None = None
    srcip: str | None = None
    srcport: str | None = None
    authMethod: str | None = None
    pid: str | None = None
    openedAt: str | None = None
    durationSec: float | None = None
    state: str | None = None


class WazuhAlertSummary(BaseModel):
    window: str = "24h"
    severityCounts: dict[str, float] = Field(default_factory=dict)
    topAgents: list[WazuhTopItem] = Field(default_factory=list)
    topRules: list[WazuhTopItem] = Field(default_factory=list)
    topTactics: list[WazuhTopItem] = Field(default_factory=list)


class WazuhSshSummary(BaseModel):
    window: str = "24h"
    total: float = 0
    success: float = 0
    failed: float = 0
    invalidUser: float = 0
    rootLogin: float = 0
    activeSessions: int = 0
    topSources: list[WazuhTopItem] = Field(default_factory=list)
    topUsers: list[WazuhTopItem] = Field(default_factory=list)
    topAgents: list[WazuhTopItem] = Field(default_factory=list)
    topRules: list[WazuhTopItem] = Field(default_factory=list)
    recent: list[WazuhRecentEvent] = Field(default_factory=list)
    activeSessionItems: list[WazuhSshSession] = Field(default_factory=list)


class WazuhFimSummary(BaseModel):
    window: str = "24h"
    keyEvents: float = 0
    keyModified: float = 0
    keyAdded: float = 0
    keyDeleted: float = 0
    topPaths: list[WazuhTopItem] = Field(default_factory=list)
    topAgents: list[WazuhTopItem] = Field(default_factory=list)
    topRules: list[WazuhTopItem] = Field(default_factory=list)
    recent: list[WazuhRecentEvent] = Field(default_factory=list)


class WazuhSummary(BaseModel):
    enabled: bool = False
    modules: list[str] = Field(default_factory=list)
    health: Health = Health.UNKNOWN
    apiUp: bool | None = None
    indexerUp: bool | None = None
    agentTotal: int = 0
    activeAgents: int = 0
    inactiveAgents: int = 0
    managerCriticalDown: float = 0
    rootcheckOutstanding: float = 0
    syscheckFindings: float = 0
    agents: list[WazuhAgent] = Field(default_factory=list)
    alerts: WazuhAlertSummary = Field(default_factory=WazuhAlertSummary)
    ssh: WazuhSshSummary = Field(default_factory=WazuhSshSummary)
    fim: WazuhFimSummary = Field(default_factory=WazuhFimSummary)
    updatedAt: datetime = Field(default_factory=utc_now)
    stale: bool = False


class MachineSecurity(BaseModel):
    enabled: bool = False
    health: Health = Health.UNKNOWN
    matchedAgents: list[WazuhAgent] = Field(default_factory=list)
    alertSeverityCounts: dict[str, float] = Field(default_factory=dict)
    sshTotal: float = 0
    sshSuccess: float = 0
    sshFailed: float = 0
    sshInvalidUser: float = 0
    sshRootLogin: float = 0
    sshActiveSessions: int = 0
    fimKeyEvents: float = 0
    fimModified: float = 0
    fimAdded: float = 0
    fimDeleted: float = 0
    activeSessions: list[WazuhSshSession] = Field(default_factory=list)
    recentEvents: list[WazuhRecentEvent] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    stale: bool = False


class GrafanaDashboardLink(BaseModel):
    id: str
    title: str
    description: str
    url: str


class GrafanaIntegration(BaseModel):
    baseUrl: str
    dashboards: list[GrafanaDashboardLink] = Field(default_factory=list)


class CurrentUser(BaseModel):
    id: int
    username: str
    displayName: str | None = None
    role: Literal["admin", "viewer"] = "admin"
    active: bool = True


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=256)


class UserCreate(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=8, max_length=256)
    displayName: str | None = Field(default=None, max_length=120)
    role: Literal["admin", "viewer"] = "admin"
    active: bool = True


class UserUpdate(BaseModel):
    password: str | None = Field(default=None, min_length=8, max_length=256)
    displayName: str | None = Field(default=None, max_length=120)
    role: Literal["admin", "viewer"] | None = None
    active: bool | None = None


class NavLinkBase(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    url: str = Field(min_length=1, max_length=2048)
    category: str = Field(default="其他", min_length=1, max_length=80)
    description: str | None = Field(default=None, max_length=500)
    icon: str | None = Field(default=None, max_length=80)
    tags: list[str] = Field(default_factory=list)
    favorite: bool = False
    enabled: bool = True

    @field_validator("title", "url", "category", "description", "icon", mode="before")
    @classmethod
    def strip_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return str(value).strip()

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        if value.startswith(("/", "http://", "https://")):
            return value
        raise ValueError("URL must start with /, http://, or https://")

    @field_validator("tags")
    @classmethod
    def normalize_tags(cls, value: list[str]) -> list[str]:
        seen: set[str] = set()
        tags: list[str] = []
        for item in value:
            tag = str(item).strip()
            if not tag or tag in seen:
                continue
            seen.add(tag)
            tags.append(tag[:40])
        return tags[:12]


class NavLinkCreate(NavLinkBase):
    sortOrder: int | None = None


class NavLinkUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=160)
    url: str | None = Field(default=None, min_length=1, max_length=2048)
    category: str | None = Field(default=None, min_length=1, max_length=80)
    description: str | None = Field(default=None, max_length=500)
    icon: str | None = Field(default=None, max_length=80)
    tags: list[str] | None = None
    favorite: bool | None = None
    enabled: bool | None = None
    sortOrder: int | None = None
    status: Literal["unknown", "ok", "warning", "down"] | None = None

    @field_validator("title", "url", "category", "description", "icon", mode="before")
    @classmethod
    def strip_update_strings(cls, value: str | None) -> str | None:
        return NavLinkBase.strip_strings(value)

    @field_validator("url")
    @classmethod
    def validate_update_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return NavLinkBase.validate_url(value)

    @field_validator("tags")
    @classmethod
    def normalize_update_tags(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        return NavLinkBase.normalize_tags(value)


class NavLink(NavLinkBase):
    id: int
    source: str = "manual"
    sourceKey: str | None = None
    sortOrder: int = 0
    status: Literal["unknown", "ok", "warning", "down"] = "unknown"
    statusCode: int | None = None
    lastCheckedAt: datetime | None = None
    createdAt: datetime
    updatedAt: datetime


class NavLinkPreviewRequest(BaseModel):
    url: str = Field(min_length=1, max_length=2048)

    @field_validator("url", mode="before")
    @classmethod
    def strip_preview_url(cls, value: str) -> str:
        return str(value).strip()

    @field_validator("url")
    @classmethod
    def validate_preview_url(cls, value: str) -> str:
        return NavLinkBase.validate_url(value)


class NavLinkPreview(BaseModel):
    title: str
    url: str
    category: str = "待分类"
    description: str | None = None
    icon: str = "web"
    tags: list[str] = Field(default_factory=list)
    status: Literal["unknown", "ok", "warning", "down"] = "unknown"
    statusCode: int | None = None
    serverHeader: str | None = None
    contentType: str | None = None
    reachable: bool = False


class NavReorderItem(BaseModel):
    id: int
    sortOrder: int


class NavReorderRequest(BaseModel):
    items: list[NavReorderItem]


class DiscoveryRun(BaseModel):
    id: int
    status: Literal["running", "completed", "failed"] = "running"
    cidrs: list[str] = Field(default_factory=list)
    ports: list[int] = Field(default_factory=list)
    foundCount: int = 0
    importableCount: int = 0
    errorMessage: str | None = None
    startedAt: datetime
    finishedAt: datetime | None = None


class DiscoveryScanRequest(BaseModel):
    cidrs: list[str] | None = None
    ports: list[int] | None = None


class NavCandidate(BaseModel):
    id: int
    runId: int | None = None
    title: str
    url: str
    host: str
    port: int
    scheme: Literal["http", "https"]
    statusCode: int | None = None
    serverHeader: str | None = None
    contentType: str | None = None
    category: str = "待分类"
    suggestionReason: str | None = None
    tags: list[str] = Field(default_factory=list)
    source: str = "scan"
    ignored: bool = False
    importedLinkId: int | None = None
    createdAt: datetime
    updatedAt: datetime


class NavCandidateUpdate(BaseModel):
    ignored: bool | None = None
    title: str | None = Field(default=None, min_length=1, max_length=160)
    category: str | None = Field(default=None, min_length=1, max_length=80)
    tags: list[str] | None = None

    @field_validator("title", "category", mode="before")
    @classmethod
    def strip_candidate_strings(cls, value: str | None) -> str | None:
        return NavLinkBase.strip_strings(value)

    @field_validator("tags")
    @classmethod
    def normalize_candidate_tags(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        return NavLinkBase.normalize_tags(value)


class SourceStatus(BaseModel):
    source: str
    ok: bool
    latencyMs: float | None = None
    lastSuccessAt: datetime | None = None
    lastError: str | None = None


class Overview(BaseModel):
    generatedAt: datetime = Field(default_factory=utc_now)
    stale: bool = False
    machines: list[Machine] = Field(default_factory=list)
    networkDevices: list[NetworkDevice] = Field(default_factory=list)
    tailnet: TailnetSummary = Field(default_factory=TailnetSummary)
    services: ServicesSummary = Field(default_factory=ServicesSummary)
    lan: LanSummary = Field(default_factory=LanSummary)
    pve: PVESummary = Field(default_factory=PVESummary)
    wazuh: WazuhSummary = Field(default_factory=WazuhSummary)
    grafana: GrafanaIntegration | None = None
    problems: list[Problem] = Field(default_factory=list)
    sourceStatuses: list[SourceStatus] = Field(default_factory=list)
    summary: dict[str, Any] = Field(default_factory=dict)


class SeriesPoint(BaseModel):
    t: int
    cpuPct: float | None = None
    memPct: float | None = None
    diskPct: float | None = None
    netBps: float | None = None
    maxTempC: float | None = None
    fanRpm: float | None = None


class MachineDetail(BaseModel):
    machine: Machine
    systemItems: list[dict[str, Any]] = Field(default_factory=list)
    hardwareItems: list[dict[str, Any]] = Field(default_factory=list)
    problems: list[Problem] = Field(default_factory=list)
    security: MachineSecurity = Field(default_factory=MachineSecurity)


class Diagnostics(BaseModel):
    sourceStatuses: list[SourceStatus]
    cache: dict[str, Any] = Field(default_factory=dict)
    collector: dict[str, Any] = Field(default_factory=dict)
