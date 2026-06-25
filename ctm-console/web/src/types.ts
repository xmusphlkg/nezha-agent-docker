export type Health = 'ok' | 'warning' | 'critical' | 'offline' | 'stale' | 'unknown';

export interface Problem {
  source: 'zabbix' | 'prometheus';
  severity: string;
  host: string;
  name: string;
  ageSec: number;
  eventId: string;
  acknowledged: boolean;
}

export interface Machine {
  id: string;
  sysHost?: string | null;
  phyHost?: string | null;
  mode: 'paired' | 'standalone' | 'sys-only' | 'phy-only';
  health: Health;
  osName?: string | null;
  cpuModel?: string | null;
  cpuCores?: number | null;
  cpuPct?: number | null;
  memPct?: number | null;
  memBytes?: number | null;
  maxMemBytes?: number | null;
  diskPct?: number | null;
  diskBytes?: number | null;
  maxDiskBytes?: number | null;
  netBps?: number | null;
  uptimeSec?: number | null;
  maxTempC?: number | null;
  fanRpm?: number | null;
  agentUp?: boolean | null;
  problems: Problem[];
  updatedAt: string;
  stale: boolean;
}

export interface NetworkDevice {
  id: string;
  host: string;
  health: Health;
  uptimeSec?: number | null;
  netBps?: number | null;
  problems: Problem[];
  updatedAt: string;
  stale: boolean;
}

export interface TailnetNode {
  id: string;
  name: string;
  user?: string | null;
  online: boolean;
  lastSeenAgeSec?: number | null;
  availableRoutes?: number | null;
  approvedRoutes?: number | null;
}

export interface TailnetKey {
  user?: string | null;
  reusable?: string | null;
  expiresInSec?: number | null;
}

export interface TailnetSummary {
  health: Health;
  apiUp?: boolean | null;
  databaseOk?: boolean | null;
  totalNodes: number;
  onlineNodes: number;
  offlineNodes: number;
  routeDelta: number;
  expiringKeys: number;
  nodes: TailnetNode[];
  keys: TailnetKey[];
  updatedAt: string;
  stale: boolean;
}

export interface ServiceProbe {
  id: string;
  job: string;
  instance: string;
  target?: string | null;
  name?: string | null;
  group?: string | null;
  ifaceType?: string | null;
  success: boolean;
  durationSec?: number | null;
}

export interface PrometheusTarget {
  id: string;
  job?: string | null;
  scrapeUrl: string;
  health: string;
  lastScrape?: string | null;
  lastError?: string | null;
}

export interface ServicesSummary {
  health: Health;
  probeTotal: number;
  probeFailed: number;
  targetTotal: number;
  targetDown: number;
  probes: ServiceProbe[];
  targets: PrometheusTarget[];
  updatedAt: string;
  stale: boolean;
}

export interface LanDevice {
  id: string;
  ip: string;
  mac: string;
  name?: string | null;
  iface?: string | null;
  known: boolean;
  online: boolean;
  health: Health;
}

export interface LanSummary {
  health: Health;
  totalDevices: number;
  onlineDevices: number;
  knownDevices: number;
  unknownDevices: number;
  knownOnline: number;
  unknownOnline: number;
  interfaces: string[];
  devices: LanDevice[];
  updatedAt: string;
  stale: boolean;
}

export interface PVEResource {
  id: string;
  server: string;
  node: string;
  vmid: number;
  type: 'qemu' | 'lxc';
  name: string;
  status: string;
  cpuPct?: number | null;
  cpus?: number | null;
  memBytes?: number | null;
  maxMemBytes?: number | null;
  diskBytes?: number | null;
  maxDiskBytes?: number | null;
  uptimeSec?: number | null;
  template: boolean;
}

export interface PVENode {
  id: string;
  server: string;
  node: string;
  status: string;
  cpuPct?: number | null;
  memBytes?: number | null;
  maxMemBytes?: number | null;
  diskBytes?: number | null;
  maxDiskBytes?: number | null;
  uptimeSec?: number | null;
}

export interface PVEServerStatus {
  name: string;
  host: string;
  ok: boolean;
  latencyMs?: number | null;
  version?: string | null;
  lastError?: string | null;
}

export interface PVESummary {
  health: Health;
  configured: boolean;
  totalServers: number;
  onlineServers: number;
  totalNodes: number;
  onlineNodes: number;
  totalGuests: number;
  runningGuests: number;
  qemuGuests: number;
  lxcGuests: number;
  cpuPct?: number | null;
  memPct?: number | null;
  diskPct?: number | null;
  nodes: PVENode[];
  guests: PVEResource[];
  serverStatuses: PVEServerStatus[];
  updatedAt: string;
  stale: boolean;
}

export interface WazuhTopItem {
  label: string;
  value: number;
  agentId?: string | null;
  severity?: string | null;
  level?: number | null;
  description?: string | null;
}

export interface WazuhAgent {
  id: string;
  name: string;
  ip?: string | null;
  status: string;
  osName?: string | null;
  osVersion?: string | null;
  manager?: string | null;
  node?: string | null;
  lastKeepaliveAgeSec?: number | null;
  groupConfigSynced?: boolean | null;
  rootcheckOutstanding?: number | null;
  syscheckFindings?: number | null;
}

export interface WazuhRecentEvent {
  kind: 'ssh' | 'fim';
  timestamp?: string | null;
  agentName?: string | null;
  agentId?: string | null;
  agentIp?: string | null;
  srcip?: string | null;
  user?: string | null;
  outcome?: string | null;
  event?: string | null;
  path?: string | null;
  mode?: string | null;
  ruleId?: string | null;
  severity?: string | null;
  level?: number | null;
  description?: string | null;
}

export interface WazuhSshSession {
  agentName?: string | null;
  agentId?: string | null;
  agentIp?: string | null;
  user?: string | null;
  srcip?: string | null;
  srcport?: string | null;
  authMethod?: string | null;
  pid?: string | null;
  openedAt?: string | null;
  durationSec?: number | null;
  state?: string | null;
}

export interface WazuhAlertSummary {
  window: string;
  severityCounts: Record<string, number>;
  topAgents: WazuhTopItem[];
  topRules: WazuhTopItem[];
  topTactics: WazuhTopItem[];
}

export interface WazuhSshSummary {
  window: string;
  total: number;
  success: number;
  failed: number;
  invalidUser: number;
  rootLogin: number;
  activeSessions: number;
  topSources: WazuhTopItem[];
  topUsers: WazuhTopItem[];
  topAgents: WazuhTopItem[];
  topRules: WazuhTopItem[];
  recent: WazuhRecentEvent[];
  activeSessionItems: WazuhSshSession[];
}

export interface WazuhFimSummary {
  window: string;
  keyEvents: number;
  keyModified: number;
  keyAdded: number;
  keyDeleted: number;
  topPaths: WazuhTopItem[];
  topAgents: WazuhTopItem[];
  topRules: WazuhTopItem[];
  recent: WazuhRecentEvent[];
}

export interface WazuhSummary {
  enabled: boolean;
  modules: string[];
  health: Health;
  apiUp?: boolean | null;
  indexerUp?: boolean | null;
  agentTotal: number;
  activeAgents: number;
  inactiveAgents: number;
  managerCriticalDown: number;
  rootcheckOutstanding: number;
  syscheckFindings: number;
  agents: WazuhAgent[];
  alerts: WazuhAlertSummary;
  ssh: WazuhSshSummary;
  fim: WazuhFimSummary;
  updatedAt: string;
  stale: boolean;
}

export interface MachineSecurity {
  enabled: boolean;
  health: Health;
  matchedAgents: WazuhAgent[];
  alertSeverityCounts: Record<string, number>;
  sshTotal: number;
  sshSuccess: number;
  sshFailed: number;
  sshInvalidUser: number;
  sshRootLogin: number;
  sshActiveSessions: number;
  fimKeyEvents: number;
  fimModified: number;
  fimAdded: number;
  fimDeleted: number;
  activeSessions: WazuhSshSession[];
  recentEvents: WazuhRecentEvent[];
  notes: string[];
  stale: boolean;
}

export interface GrafanaDashboardLink {
  id: string;
  title: string;
  description: string;
  url: string;
}

export interface GrafanaIntegration {
  baseUrl: string;
  dashboards: GrafanaDashboardLink[];
}

export interface CurrentUser {
  id: number;
  username: string;
  displayName?: string | null;
  role: 'admin' | 'viewer';
  active: boolean;
}

export interface LoginRequest {
  username: string;
  password: string;
}

export interface UserCreate {
  username: string;
  password: string;
  displayName?: string | null;
  role: 'admin' | 'viewer';
  active: boolean;
}

export interface UserUpdate {
  password?: string;
  displayName?: string | null;
  role?: 'admin' | 'viewer';
  active?: boolean;
}

export interface NavLink {
  id: number;
  title: string;
  url: string;
  category: string;
  description?: string | null;
  icon?: string | null;
  tags: string[];
  source: string;
  sourceKey?: string | null;
  favorite: boolean;
  enabled: boolean;
  sortOrder: number;
  status: 'unknown' | 'ok' | 'warning' | 'down';
  statusCode?: number | null;
  lastCheckedAt?: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface NavLinkInput {
  title: string;
  url: string;
  category: string;
  description?: string | null;
  icon?: string | null;
  tags: string[];
  favorite: boolean;
  enabled: boolean;
  sortOrder?: number | null;
}

export interface NavLinkPatch {
  title?: string;
  url?: string;
  category?: string;
  description?: string | null;
  icon?: string | null;
  tags?: string[];
  favorite?: boolean;
  enabled?: boolean;
  sortOrder?: number;
  status?: 'unknown' | 'ok' | 'warning' | 'down';
}

export interface NavLinkPreview {
  title: string;
  url: string;
  category: string;
  description?: string | null;
  icon: string;
  tags: string[];
  status: 'unknown' | 'ok' | 'warning' | 'down';
  statusCode?: number | null;
  serverHeader?: string | null;
  contentType?: string | null;
  reachable: boolean;
}

export interface DiscoveryRun {
  id: number;
  status: 'running' | 'completed' | 'failed';
  cidrs: string[];
  ports: number[];
  foundCount: number;
  importableCount: number;
  errorMessage?: string | null;
  startedAt: string;
  finishedAt?: string | null;
}

export interface NavCandidate {
  id: number;
  runId?: number | null;
  title: string;
  url: string;
  host: string;
  port: number;
  scheme: 'http' | 'https';
  statusCode?: number | null;
  serverHeader?: string | null;
  contentType?: string | null;
  category: string;
  suggestionReason?: string | null;
  tags: string[];
  source: string;
  ignored: boolean;
  importedLinkId?: number | null;
  createdAt: string;
  updatedAt: string;
}

export interface NavCandidatePatch {
  ignored?: boolean;
  title?: string;
  category?: string;
  tags?: string[];
}

export interface SourceStatus {
  source: string;
  ok: boolean;
  latencyMs?: number | null;
  lastSuccessAt?: string | null;
  lastError?: string | null;
}

export interface Overview {
  generatedAt: string;
  stale: boolean;
  machines: Machine[];
  networkDevices: NetworkDevice[];
  tailnet: TailnetSummary;
  services: ServicesSummary;
  lan: LanSummary;
  pve: PVESummary;
  wazuh: WazuhSummary;
  grafana?: GrafanaIntegration | null;
  problems: Problem[];
  sourceStatuses: SourceStatus[];
  summary: Record<string, number>;
}

export interface MachineDetail {
  machine: Machine;
  systemItems: ItemValue[];
  hardwareItems: ItemValue[];
  problems: Problem[];
  security: MachineSecurity;
}

export interface ItemValue {
  itemid: string;
  name: string;
  key: string;
  lastvalue: string;
  units?: string | null;
  lastclock?: string | null;
}

export interface SeriesPoint {
  t: number;
  cpuPct?: number;
  memPct?: number;
  diskPct?: number;
  netBps?: number;
  maxTempC?: number;
  fanRpm?: number;
}

export interface MachineSeries {
  machineId: string;
  range: '1h' | '6h' | '24h';
  points: SeriesPoint[];
}

export interface Diagnostics {
  sourceStatuses: SourceStatus[];
  cache: Record<string, unknown>;
  collector: Record<string, unknown>;
}
