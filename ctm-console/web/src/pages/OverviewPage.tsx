import { useEffect, useMemo, useState, type ReactNode } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useLocation, useNavigate } from 'react-router-dom';
import {
  Activity,
  AlertTriangle,
  ArrowDown,
  ArrowDownWideNarrow,
  ArrowUp,
  CircleDot,
  Cpu,
  Database,
  ExternalLink,
  FileWarning,
  HardDrive,
  KeyRound,
  Layers3,
  MemoryStick,
  Network,
  Server,
  ShieldAlert,
  ShieldCheck,
  UserCheck
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { api } from '../lib/api';
import { age, bps, bytes, dateTime, healthText, number as formatNumber, pct } from '../lib/format';
import type {
  Health,
  GrafanaIntegration,
  Machine,
  Overview,
  PVEResource,
  PVESummary,
  SourceStatus,
  WazuhRecentEvent,
  WazuhSummary,
  WazuhTopItem
} from '../types';

type Tone = 'good' | 'warn' | 'bad' | 'info' | 'neutral';
type MetricTone = 'ok' | 'warn' | 'bad' | 'empty';
type ReportingState = 'online' | 'offline' | 'stale' | 'unknown';
type Panel = 'hosts' | 'pve' | 'security';
type HostGroup = 'all' | 'server' | 'cloud';
type HostSort = 'health' | 'name' | 'cpu' | 'mem' | 'disk' | 'net' | 'uptime' | 'problems';
type PVETypeFilter = 'all' | 'qemu' | 'lxc';
type PVESort = 'cpu' | 'mem' | 'disk' | 'uptime' | 'name' | 'vmid' | 'node' | 'type' | 'status';
type SortDir = 'asc' | 'desc';
type SecurityTone = 'bad' | 'warn' | 'good';

interface HostSettings {
  group: HostGroup;
  sort: HostSort;
  dir: SortDir;
}

interface PVESettings {
  type: PVETypeFilter;
  node: string;
  sort: PVESort;
  dir: SortDir;
}

interface SecurityAction {
  key: string;
  icon: LucideIcon;
  title: string;
  value: string;
  detail: string;
  tone: SecurityTone;
}

const healthOrder: Record<Health, number> = {
  critical: 0,
  offline: 1,
  warning: 2,
  stale: 3,
  unknown: 4,
  ok: 5
};

const modeText: Record<Machine['mode'], string> = {
  paired: 'Sys + Phy',
  standalone: '单通道',
  'sys-only': '系统',
  'phy-only': '硬件'
};

const hostGroupLabels: Record<HostGroup, string> = {
  all: '全部',
  server: 'Server',
  cloud: 'Cloud'
};

const hostSortOptions: Array<{ value: HostSort; label: string }> = [
  { value: 'health', label: '健康状态' },
  { value: 'cpu', label: 'CPU 占用' },
  { value: 'mem', label: '内存占用' },
  { value: 'disk', label: '存储占用' },
  { value: 'net', label: '网络吞吐' },
  { value: 'uptime', label: '运行时间' },
  { value: 'problems', label: '问题数量' },
  { value: 'name', label: '名称' }
];

const pveTypeLabels: Record<PVETypeFilter, string> = {
  all: '全部',
  qemu: 'VM',
  lxc: 'CT'
};

const pveSortOptions: Array<{ value: PVESort; label: string }> = [
  { value: 'cpu', label: 'CPU 占用' },
  { value: 'mem', label: '内存占用' },
  { value: 'disk', label: '存储' },
  { value: 'uptime', label: '运行时间' },
  { value: 'node', label: '节点' },
  { value: 'status', label: '状态' },
  { value: 'type', label: '类型' },
  { value: 'vmid', label: 'VMID' },
  { value: 'name', label: '名称' }
];

export function OverviewPage() {
  const location = useLocation();
  const navigate = useNavigate();
  const overview = useQuery({ queryKey: ['overview'], queryFn: api.overview });
  const now = useNow();
  const activePanel = panelFromLocation(location);
  const searchParams = useMemo(() => new URLSearchParams(location.search), [location.search]);
  const hostSettings = readHostSettings(searchParams);
  const pveSettings = readPVESettings(searchParams);
  const updateUrl = (patch: Record<string, string | null>, panel: Panel = activePanel, replace = true) => {
    const params = new URLSearchParams(location.search);
    params.delete('panel');
    Object.entries(patch).forEach(([key, value]) => {
      if (!value) {
        params.delete(key);
      } else {
        params.set(key, value);
      }
    });
    const search = params.toString();
    navigate({ pathname: panelPath(panel), search: search ? `?${search}` : '' }, { replace });
  };
  const model = useMemo(() => (overview.data ? buildDashboardModel(overview.data, hostSettings) : null), [overview.data, hostSettings.group, hostSettings.sort, hostSettings.dir]);

  if (overview.isLoading) {
    return <div className="loading-screen">加载中</div>;
  }

  if (overview.isError || !overview.data || !model) {
    return (
      <div className="loading-screen error">
        <strong>无法加载面板数据</strong>
        <span>{overview.error instanceof Error ? overview.error.message : '请检查 API 服务状态'}</span>
      </div>
    );
  }

  const data = overview.data;
  const currentTime = now.toLocaleTimeString('zh-CN', { hour12: false });

  return (
    <div className="dashboard-page">
      <section className="overview-hero">
        <div>
          <h1>运行概览</h1>
          <p>
            当前时间 <strong>{currentTime}</strong>
          </p>
        </div>
        <SourceStrip sources={data.sourceStatuses} stale={data.stale} />
      </section>

      <section className="panel-tabs" aria-label="监控子面板">
        <button className={activePanel === 'hosts' ? 'active' : ''} type="button" onClick={() => updateUrl({}, 'hosts', false)}>
          <Server size={16} />
          主机监控
        </button>
        <button className={activePanel === 'pve' ? 'active' : ''} type="button" onClick={() => updateUrl({}, 'pve', false)}>
          <Cpu size={16} />
          PVE 监控
          <b className={data.pve.configured ? '' : 'muted'}>{data.pve.configured ? data.pve.totalGuests : '未配置'}</b>
        </button>
        <button className={activePanel === 'security' ? 'active' : ''} type="button" onClick={() => updateUrl({}, 'security', false)}>
          <ShieldCheck size={16} />
          安全态势
          <b className={data.wazuh.enabled ? '' : 'muted'}>{data.wazuh.enabled ? securityAttention(data.wazuh) : '未启用'}</b>
        </button>
      </section>

      <GrafanaContextLinks panel={activePanel} grafana={data.grafana} />

      {activePanel === 'hosts' ? (
        <>
          <section className="summary-grid" aria-label="Overview counters">
            <SummaryCard icon={Server} title="服务器总数" value={data.machines.length} detail="来自 Zabbix 主机采集" tone="info" />
            <SummaryCard icon={CircleDot} title="在线服务器" value={model.onlineMachines} detail="Agent 正常或仍在上报" tone="good" />
            <SummaryCard icon={AlertTriangle} title="离线服务器" value={model.offlineMachines} detail={`${model.unknownMachines} 未知 / ${model.attentionMachines} 需关注`} tone={model.offlineMachines ? 'bad' : 'neutral'} />
            <SummaryCard icon={Network} title="网络吞吐" value={bps(model.networkBps)} detail={`${model.serviceHealthy}/${model.serviceTotal} 服务可达`} tone={model.serviceIssues ? 'warn' : 'info'}>
              <span className="network-mini">
                <b>{data.networkDevices.length}</b> 设备
                <i />
                <b>{model.openProblems}</b> 告警
              </span>
            </SummaryCard>
          </section>

          <HostControls
            counts={model.hostGroupCounts}
            settings={hostSettings}
            shown={model.machines.length}
            total={data.machines.length}
            onGroup={(group) => updateUrl({ hostGroup: group === 'all' ? null : group })}
            onSort={(sort) => updateUrl({ hostSort: sort })}
            onDir={(dir) => updateUrl({ hostDir: dir })}
          />

          <section className="server-list" aria-label="Server list">
            {model.machines.map((machine) => (
              <ServerRow key={machine.id} machine={machine} grafana={data.grafana} />
            ))}
            {!model.machines.length && (
              <div className="pve-empty compact">
                <div>
                  <h2>当前分组暂无主机</h2>
                  <p>可以切换到 Server / Cloud 或修改 URL 中的 `hostGroup` 参数。</p>
                </div>
              </div>
            )}
          </section>
        </>
      ) : activePanel === 'pve' ? (
        <PVEPanel
          pve={data.pve}
          settings={pveSettings}
          onType={(type) => updateUrl({ pveType: type === 'all' ? null : type }, 'pve')}
          onNode={(node) => updateUrl({ pveNode: node === 'all' ? null : node }, 'pve')}
          onSort={(sort) => updateUrl({ pveSort: sort }, 'pve')}
          onDir={(dir) => updateUrl({ pveDir: dir }, 'pve')}
        />
      ) : (
        <SecurityPanel wazuh={data.wazuh} grafana={data.grafana} />
      )}

      <footer className="dashboard-footer">
        <span>CTM Monitor</span>
        <span>数据来自 Zabbix / Prometheus / MySQL / PVE / Wazuh</span>
      </footer>
    </div>
  );
}

function buildDashboardModel(data: Overview, settings: HostSettings) {
  const allMachines = [...data.machines];
  const hostGroupCounts = {
    all: allMachines.length,
    server: allMachines.filter((machine) => hostGroupOf(machine) === 'server').length,
    cloud: allMachines.filter((machine) => hostGroupOf(machine) === 'cloud').length
  };
  const machines = sortMachines(
    allMachines.filter((machine) => settings.group === 'all' || hostGroupOf(machine) === settings.group),
    settings.sort,
    settings.dir
  );
  const onlineMachines = allMachines.filter((machine) => reportingState(machine) === 'online').length;
  const offlineMachines = allMachines.filter((machine) => ['offline', 'stale'].includes(reportingState(machine))).length;
  const unknownMachines = allMachines.length - onlineMachines - offlineMachines;
  const attentionMachines = allMachines.filter((machine) => !['ok', 'unknown'].includes(machine.health) || machine.problems.length > 0).length;
  const networkBps = sum([
    ...allMachines.map((machine) => machine.netBps),
    ...data.networkDevices.map((device) => device.netBps)
  ]);
  const serviceTotal = data.services.probeTotal + data.services.targetTotal;
  const serviceIssues = data.services.probeFailed + data.services.targetDown;
  const serviceHealthy = Math.max(serviceTotal - serviceIssues, 0);
  const openProblems = data.problems.filter((problem) => !problem.acknowledged).length;

  return {
    machines,
    hostGroupCounts,
    onlineMachines,
    offlineMachines,
    unknownMachines,
    attentionMachines,
    networkBps,
    serviceTotal,
    serviceIssues,
    serviceHealthy,
    openProblems
  };
}

function GrafanaContextLinks({ panel, grafana }: { panel: Panel; grafana?: GrafanaIntegration | null }) {
  if (!grafana?.dashboards.length) return null;
  const ids: Record<Panel, string[]> = {
    hosts: ['hosts', 'resources', 'server-trends', 'unified'],
    pve: ['main', 'unified'],
    security: ['wazuh', 'wazuh-ssh', 'wazuh-fim', 'alerts'],
  };
  const links = ids[panel]
    .map((id) => grafana.dashboards.find((dashboard) => dashboard.id === id))
    .filter((link): link is NonNullable<typeof link> => Boolean(link));

  return (
    <section className="grafana-links" aria-label="Grafana dashboards">
      <span>
        <ExternalLink size={14} />
        Grafana 深挖
      </span>
      {links.map((link) => (
        <a key={link.id} href={link.url} target="_blank" rel="noreferrer" title={link.description}>
          {link.title}
        </a>
      ))}
    </section>
  );
}

function useNow() {
  const [now, setNow] = useState(() => new Date());

  useEffect(() => {
    const id = window.setInterval(() => setNow(new Date()), 1000);
    return () => window.clearInterval(id);
  }, []);

  return now;
}

function ServerRow({ machine, grafana }: { machine: Machine; grafana?: GrafanaIntegration | null }) {
  const navigate = useNavigate();
  const state = reportingState(machine);
  const uptime = uptimeDisplay(machine);
  const trendsUrl = grafanaDashboardUrl(grafana, 'server-trends', {
    'var-machine': zabbixHostVariable(machine),
    from: 'now-6h',
    to: 'now',
  });
  const openDetail = () => navigate(`/machines/${encodeURIComponent(machine.id)}`);

  return (
    <article
      className={`server-row ${machine.health}`}
      role="link"
      tabIndex={0}
      onClick={openDetail}
      onKeyDown={(event) => {
        if (event.key === 'Enter') openDetail();
      }}
    >
      <div className="server-identity">
        <span className={`status-dot ${state}`} title={`${healthText(machine.health)} / ${state}`} />
        <span className="machine-token">{machine.id.slice(0, 1).toUpperCase()}</span>
        <span className="server-name">
          <strong>
            {machine.id}
            {trendsUrl && (
              <a
                className="row-grafana-link"
                href={trendsUrl}
                target="_blank"
                rel="noreferrer"
                title="打开 Grafana 单机 6h 趋势"
                onClick={(event) => event.stopPropagation()}
              >
                <ExternalLink size={12} />
              </a>
            )}
          </strong>
          <small>{hostLine(machine)}</small>
          <small className="machine-spec">{machineSpecLine(machine)}</small>
        </span>
      </div>

      <span className="server-divider" aria-hidden="true" />

      <InfoCell label="系统" value={machine.osName ?? '-'} className="os-cell" />
      <InfoCell label={uptime.label} value={uptime.value} />
      <ResourceMetric icon={Cpu} label="CPU" value={machine.cpuPct} />
      <UsageMetric icon={MemoryStick} label="MEM" value={machine.memPct} detail={capacityText(machine.memBytes, machine.maxMemBytes)} warn={80} bad={92} />
      <UsageMetric icon={HardDrive} label="STG" value={machine.diskPct} detail={capacityText(machine.diskBytes, machine.maxDiskBytes)} />
      <InfoCell label="网络" value={bps(machine.netBps)} />
      <InfoCell label="温度" value={machine.maxTempC ? `${formatNumber(machine.maxTempC, 1)}°C` : '-'} />
      <InfoCell label="问题" value={machine.problems.length ? String(machine.problems.length) : '0'} strong={machine.problems.length > 0} />
    </article>
  );
}

function HostControls({
  counts,
  settings,
  shown,
  total,
  onGroup,
  onSort,
  onDir
}: {
  counts: Record<HostGroup, number>;
  settings: HostSettings;
  shown: number;
  total: number;
  onGroup: (group: HostGroup) => void;
  onSort: (sort: HostSort) => void;
  onDir: (dir: SortDir) => void;
}) {
  return (
    <section className="control-bar" aria-label="主机显示设置">
      <div className="control-group">
        <span className="control-label">
          <Layers3 size={15} />
          分组
        </span>
        <div className="segmented-control">
          {(Object.keys(hostGroupLabels) as HostGroup[]).map((group) => (
            <button key={group} className={settings.group === group ? 'active' : ''} type="button" onClick={() => onGroup(group)}>
              {hostGroupLabels[group]}
              <b>{counts[group]}</b>
            </button>
          ))}
        </div>
      </div>

      <SortControls
        label={`${shown}/${total} 主机`}
        sort={settings.sort}
        dir={settings.dir}
        options={hostSortOptions}
        onSort={(value) => onSort(value as HostSort)}
        onDir={onDir}
      />
    </section>
  );
}

function PVEPanel({
  pve,
  settings,
  onType,
  onNode,
  onSort,
  onDir
}: {
  pve: PVESummary;
  settings: PVESettings;
  onType: (type: PVETypeFilter) => void;
  onNode: (node: string) => void;
  onSort: (sort: PVESort) => void;
  onDir: (dir: SortDir) => void;
}) {
  if (!pve.configured) {
    return (
      <section className="pve-empty">
        <div>
          <h2>PVE 监控未配置</h2>
          <p>在 CTM Monitor 的 `.env` 中配置 `PVE_HOST`、`PVE_TOKEN_ID`、`PVE_TOKEN_SECRET`，或使用 `PVE_SERVERS_JSON` 配置多个 PVE 数据源。</p>
        </div>
      </section>
    );
  }

  const view = buildPVEView(pve, settings);

  return (
    <>
      <section className="summary-grid" aria-label="PVE counters">
        <SummaryCard icon={Server} title="PVE 服务器" value={`${pve.onlineServers}/${pve.totalServers}`} detail={`${pve.onlineNodes}/${pve.totalNodes} 节点在线`} tone={pve.onlineServers === pve.totalServers ? 'good' : 'warn'} />
        <SummaryCard icon={Activity} title="运行实例" value={`${pve.runningGuests}/${pve.totalGuests}`} detail={`${pve.qemuGuests} VM / ${pve.lxcGuests} CT`} tone="info" />
        <SummaryCard icon={Cpu} title="节点 CPU" value={pct(pve.cpuPct)} detail="PVE 节点平均负载" tone={(pve.cpuPct ?? 0) > 85 ? 'warn' : 'neutral'} />
        <SummaryCard icon={MemoryStick} title="节点内存" value={pct(pve.memPct)} detail={`磁盘 ${pct(pve.diskPct)}`} tone={(pve.memPct ?? 0) > 85 ? 'warn' : 'neutral'} />
      </section>

      <PVEControls view={view} settings={settings} onType={onType} onNode={onNode} onSort={onSort} onDir={onDir} />

      <section className="server-list" aria-label="PVE VM and CT list">
        {view.guests.length ? (
          view.guests.map((guest) => <PVEGuestRow key={guest.id} guest={guest} />)
        ) : (
          <div className="pve-empty compact">
            <div>
              <h2>当前筛选暂无资源</h2>
              <p>可以切换 VM / CT、节点，或修改 URL 中的 PVE 参数。</p>
            </div>
          </div>
        )}
      </section>
    </>
  );
}

function SecurityPanel({ wazuh, grafana }: { wazuh: WazuhSummary; grafana?: GrafanaIntegration | null }) {
  if (!wazuh.enabled) {
    return (
      <section className="pve-empty">
        <div>
          <h2>未接入 Wazuh 安全数据</h2>
          <p>设置 `CTM_WAZUH_ENABLED=true` 后，只读取 `CTM_WAZUH_MODULES` 指定模块；值班建议先启用 agents、alerts、ssh、fim 建立基线。</p>
        </div>
      </section>
    );
  }

  const criticalAlerts = wazuh.alerts.severityCounts.critical ?? 0;
  const highAlerts = wazuh.alerts.severityCounts.high ?? 0;
  const actions = buildSecurityActions(wazuh);
  const urgentActions = actions.filter((item) => item.tone !== 'good');

  return (
    <>
      <section className={`security-command ${wazuh.health}`} aria-label="Security operation focus">
        <div className="security-command-main">
          <span className={`security-command-icon ${criticalAlerts ? 'bad' : urgentActions.length ? 'warn' : 'good'}`}>
            {criticalAlerts ? <ShieldAlert size={22} /> : urgentActions.length ? <AlertTriangle size={22} /> : <ShieldCheck size={22} />}
          </span>
          <div>
            <h2>{criticalAlerts ? '当前优先级 P0' : urgentActions.length ? '当前优先级 P1' : '当前无 P0/P1 安全事项'}</h2>
            <strong>{urgentActions[0]?.title ?? '继续常规巡检'}</strong>
            <p>{urgentActions[0]?.detail ?? `${wazuh.activeAgents}/${wazuh.agentTotal} Agent active，采集链路与索引查询正常`}</p>
          </div>
        </div>
        <div className="security-command-facts" aria-label="Security facts">
          <span className={wazuh.apiUp ? 'ok' : 'bad'}>采集 API {boolText(wazuh.apiUp)}</span>
          <span className={wazuh.indexerUp ? 'ok' : 'bad'}>索引 {boolText(wazuh.indexerUp)}</span>
          <span className={wazuh.inactiveAgents ? 'warn' : 'ok'}>Agent {wazuh.activeAgents}/{wazuh.agentTotal} active</span>
          <span className={criticalAlerts ? 'bad' : highAlerts ? 'warn' : 'ok'}>{formatNumber(criticalAlerts, 0)} Critical</span>
        </div>
      </section>

      <section className="security-action-grid" aria-label="Security action queue">
        {actions.slice(0, 6).map((item) => (
          <SecurityActionCard key={item.key} action={item} />
        ))}
      </section>

      <section className="security-grid" aria-label="Wazuh details">
        {moduleEnabled(wazuh, 'alerts') && (
          <div className="security-panel">
            <SecurityPanelHead title="告警规则集中点" meta={`${wazuh.alerts.window} · 按触发量排序`} href={grafanaDashboardUrl(grafana, 'wazuh')} />
            <TopItemsTable items={wazuh.alerts.topRules} empty="当前窗口无 Wazuh 规则触发" />
          </div>
        )}

        {moduleEnabled(wazuh, 'agents') && (
          <div className="security-panel">
            <SecurityPanelHead title="Agent 异常与待处理项" meta={`${wazuh.activeAgents}/${wazuh.agentTotal} active`} href={grafanaDashboardUrl(grafana, 'wazuh')} />
            <AgentAttentionTable wazuh={wazuh} />
          </div>
        )}

        {moduleEnabled(wazuh, 'ssh') && (
          <div className="security-panel">
            <SecurityPanelHead title="SSH 最近登录与攻击" meta={`${wazuh.ssh.window} · 最新事件`} href={grafanaDashboardUrl(grafana, 'wazuh-ssh')} />
            <RecentEventsTable events={wazuh.ssh.recent} kind="ssh" />
          </div>
        )}

        {moduleEnabled(wazuh, 'fim') && (
          <div className="security-panel">
            <SecurityPanelHead title="关键文件最近变更" meta={`${wazuh.fim.window} · 关键路径`} href={grafanaDashboardUrl(grafana, 'wazuh-fim')} />
            <RecentEventsTable events={wazuh.fim.recent} kind="fim" />
          </div>
        )}
      </section>
    </>
  );
}

function SecurityActionCard({ action }: { action: SecurityAction }) {
  const Icon = action.icon;
  return (
    <article className={`security-action ${action.tone}`}>
      <span>
        <Icon size={17} />
      </span>
      <div>
        <h3>{action.title}</h3>
        <strong>{action.value}</strong>
        <p>{action.detail}</p>
      </div>
    </article>
  );
}

function AgentAttentionTable({ wazuh }: { wazuh: WazuhSummary }) {
  const agents = wazuh.agents
    .filter((agent) => agent.status !== 'active' || agent.groupConfigSynced === false || (agent.rootcheckOutstanding ?? 0) > 0)
    .sort((a, b) => {
      const rank = agentAttentionRank(b) - agentAttentionRank(a);
      return rank || a.name.localeCompare(b.name, 'zh-CN');
    });

  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>主机</th>
            <th>处置原因</th>
            <th>最近心跳</th>
            <th>连接状态</th>
          </tr>
        </thead>
        <tbody>
          {agents.map((agent) => (
            <tr key={agent.id}>
              <td>
                <strong>{agent.name}</strong>
                <small>{[agent.ip, agent.osName].filter(Boolean).join(' · ') || agent.id}</small>
              </td>
              <td>{agentAttentionText(agent)}</td>
              <td>{age(agent.lastKeepaliveAgeSec)}</td>
              <td><span className={`security-status ${agent.status === 'active' ? 'ok' : 'warn'}`}>{agent.status}</span></td>
            </tr>
          ))}
          {!agents.length && <EmptyTableRow colSpan={4} label="所有 Agent active，且无 outstanding rootcheck" />}
        </tbody>
      </table>
    </div>
  );
}

function SecurityPanelHead({ title, meta, href }: { title: string; meta: string; href?: string | null }) {
  return (
    <div className="security-panel-head">
      <h2>{title}</h2>
      <span>{meta}</span>
      {href && (
        <a href={href} target="_blank" rel="noreferrer" title="打开 Grafana 对应仪表盘">
          <ExternalLink size={13} />
          Grafana
        </a>
      )}
    </div>
  );
}

function TopItemsTable({ items, empty }: { items: WazuhTopItem[]; empty: string }) {
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>触发规则 / 聚合对象</th>
            <th>级别</th>
            <th>触发量</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr key={`${item.label}-${item.description ?? ''}`}>
              <td>
                <strong>{item.label}</strong>
                {item.description && <small>{item.description}</small>}
              </td>
              <td>{item.severity ? <span className={`security-status ${severityTone(item.severity)}`}>{item.severity}</span> : '未分级'}</td>
              <td>{formatNumber(item.value, 0)}</td>
            </tr>
          ))}
          {!items.length && <EmptyTableRow colSpan={3} label={empty} />}
        </tbody>
      </table>
    </div>
  );
}

function RecentEventsTable({ events, kind }: { events: WazuhRecentEvent[]; kind: 'ssh' | 'fim' }) {
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>时间</th>
            <th>目标主机</th>
            <th>{kind === 'ssh' ? '来源 IP / 用户' : '文件路径'}</th>
            <th>{kind === 'ssh' ? '登录结果' : '变更动作'}</th>
            <th>规则说明</th>
          </tr>
        </thead>
        <tbody>
          {events.map((event, index) => (
            <tr key={`${event.kind}-${event.timestamp ?? index}-${event.ruleId ?? ''}`}>
              <td>{dateTime(event.timestamp)}</td>
              <td>
                <strong>{event.agentName ?? event.agentId ?? '未标注主机'}</strong>
                <small>{event.agentIp ?? ''}</small>
              </td>
              <td>
                {kind === 'ssh' ? (
                  <>
                    <strong>{event.srcip ?? '未标注来源'}</strong>
                    <small>{event.user ?? '未标注用户'}</small>
                  </>
                ) : (
                  <code>{event.path ?? '未标注路径'}</code>
                )}
              </td>
              <td><span className={`security-status ${severityTone(event.severity ?? event.outcome ?? event.event ?? '')}`}>{event.outcome ?? event.event ?? '未分类'}</span></td>
              <td>
                <strong>{event.ruleId ?? '未标注规则'}</strong>
                <small>{event.description ?? event.severity ?? ''}</small>
              </td>
            </tr>
          ))}
          {!events.length && <EmptyTableRow colSpan={5} label={kind === 'ssh' ? '当前窗口无 SSH 登录或攻击事件' : '当前窗口无关键文件变更'} />}
        </tbody>
      </table>
    </div>
  );
}

function EmptyTableRow({ colSpan, label }: { colSpan: number; label: string }) {
  return (
    <tr>
      <td className="table-empty" colSpan={colSpan}>{label}</td>
    </tr>
  );
}

function PVEControls({
  view,
  settings,
  onType,
  onNode,
  onSort,
  onDir
}: {
  view: PVEView;
  settings: PVESettings;
  onType: (type: PVETypeFilter) => void;
  onNode: (node: string) => void;
  onSort: (sort: PVESort) => void;
  onDir: (dir: SortDir) => void;
}) {
  return (
    <section className="control-bar" aria-label="PVE 显示设置">
      <div className="control-group">
        <span className="control-label">
          <Layers3 size={15} />
          类型
        </span>
        <div className="segmented-control">
          {(Object.keys(pveTypeLabels) as PVETypeFilter[]).map((type) => (
            <button key={type} className={settings.type === type ? 'active' : ''} type="button" onClick={() => onType(type)}>
              {pveTypeLabels[type]}
              <b>{view.typeCounts[type]}</b>
            </button>
          ))}
        </div>
      </div>

      <div className="control-group compact-control">
        <span className="control-label">节点</span>
        <select value={view.nodeOptions.some((node) => node.value === settings.node) ? settings.node : 'all'} onChange={(event) => onNode(event.target.value)}>
          <option value="all">全部节点</option>
          {view.nodeOptions.map((node) => (
            <option key={node.value} value={node.value}>
              {node.label} ({node.count})
            </option>
          ))}
        </select>
      </div>

      <SortControls
        label={`${view.guests.length}/${view.totalGuests} 资源`}
        sort={settings.sort}
        dir={settings.dir}
        options={pveSortOptions}
        onSort={(value) => onSort(value as PVESort)}
        onDir={onDir}
      />
    </section>
  );
}

function SortControls<TSort extends string>({
  label,
  sort,
  dir,
  options,
  onSort,
  onDir
}: {
  label: string;
  sort: TSort;
  dir: SortDir;
  options: Array<{ value: TSort; label: string }>;
  onSort: (sort: TSort) => void;
  onDir: (dir: SortDir) => void;
}) {
  return (
    <div className="sort-controls">
      <span className="control-label">
        <ArrowDownWideNarrow size={15} />
        {label}
      </span>
      <select value={sort} onChange={(event) => onSort(event.target.value as TSort)}>
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
      <button className="icon-toggle" type="button" onClick={() => onDir(dir === 'desc' ? 'asc' : 'desc')} title={dir === 'desc' ? '降序' : '升序'} aria-label={dir === 'desc' ? '降序' : '升序'}>
        {dir === 'desc' ? <ArrowDown size={15} /> : <ArrowUp size={15} />}
      </button>
    </div>
  );
}

function PVEGuestRow({ guest }: { guest: PVEResource }) {
  const memPct = usagePct(guest.memBytes, guest.maxMemBytes);
  return (
    <article className={`server-row pve-row ${guest.status === 'running' ? 'ok' : 'stale'}`}>
      <div className="server-identity">
        <span className={`status-dot ${guest.status === 'running' ? 'online' : 'stale'}`} title={guest.status} />
        <span className="machine-token">{guest.type === 'qemu' ? 'VM' : 'CT'}</span>
        <span className="server-name">
          <strong>{guest.name}</strong>
          <small>{guest.node} · VMID {guest.vmid}</small>
        </span>
      </div>

      <span className="server-divider" aria-hidden="true" />

      <InfoCell label="类型" value={guest.type === 'qemu' ? '虚拟机' : '容器'} />
      <InfoCell label="运行" value={guest.uptimeSec ? duration(guest.uptimeSec) : guest.status} />
      <ResourceMetric icon={Cpu} label="CPU" value={guest.cpuPct} />
      <UsageMetric icon={MemoryStick} label="MEM" value={memPct} detail={capacityText(guest.memBytes, guest.maxMemBytes)} warn={80} bad={92} />
      <PVEStorageCell guest={guest} />
      <InfoCell label="节点" value={guest.node} />
      <InfoCell label="核心" value={guest.cpus ? formatNumber(guest.cpus, 1) : '-'} />
      <InfoCell label="状态" value={pveStatusText(guest.status)} strong={guest.status !== 'running'} />
    </article>
  );
}

function PVEStorageCell({ guest }: { guest: PVEResource }) {
  const usage = pveStorageUsagePct(guest);
  if (usage !== null) {
    return <UsageMetric icon={HardDrive} label="STG" value={usage} detail={capacityText(guest.diskBytes, guest.maxDiskBytes)} />;
  }

  const capacity = pveStorageCapacity(guest);
  return (
    <span className="resource-cell">
      <small>
        <HardDrive size={13} />
        STG
      </small>
      <b>{capacity ? bytes(capacity) : '—'}</b>
      <em>{pveStorageCapacityDetail(guest, Boolean(capacity))}</em>
      <span className="mini-bar empty">
        <i />
      </span>
    </span>
  );
}

function SummaryCard({
  icon: Icon,
  title,
  value,
  detail,
  tone,
  children
}: {
  icon: LucideIcon;
  title: string;
  value: string | number;
  detail: string;
  tone: Tone;
  children?: ReactNode;
}) {
  return (
    <article className={`summary-card ${tone}`}>
      <span className="summary-icon">
        <Icon size={18} />
      </span>
      <div>
        <h2>{title}</h2>
        <strong>{value}</strong>
        <p>{detail}</p>
        {children}
      </div>
    </article>
  );
}

function UsageMetric({
  icon: Icon,
  label,
  value,
  detail,
  warn = 85,
  bad = 95
}: {
  icon: LucideIcon;
  label: string;
  value?: number | null;
  detail: string;
  warn?: number;
  bad?: number;
}) {
  const tone = metricTone(value, warn, bad);
  const width = value === null || value === undefined || Number.isNaN(value) ? 0 : Math.min(Math.max(value, 0), 100);

  return (
    <span className="resource-cell">
      <small>
        <Icon size={13} />
        {label}
      </small>
      <b>{pct(value)}</b>
      <em>{detail}</em>
      <span className={`mini-bar ${tone}`}>
        <i style={{ width: `${width}%` }} />
      </span>
    </span>
  );
}

function SourceStrip({ sources, stale }: { sources: SourceStatus[]; stale: boolean }) {
  return (
    <div className="source-strip" aria-label="Data sources">
      {sources.map((source) => (
        <span key={source.source} className={source.ok ? 'ok' : 'bad'} title={source.lastError ?? source.source}>
          <Database size={14} />
          {source.source}
        </span>
      ))}
      {stale && <span className="warn">stale</span>}
    </div>
  );
}

function InfoCell({
  label,
  value,
  strong = false,
  className = ''
}: {
  label: string;
  value: string;
  strong?: boolean;
  className?: string;
}) {
  return (
    <span className={`info-cell ${strong ? 'strong' : ''} ${className}`.trim()}>
      <small>{label}</small>
      <b>{value}</b>
    </span>
  );
}

function ResourceMetric({
  icon: Icon,
  label,
  value,
  warn = 85,
  bad = 95
}: {
  icon: LucideIcon;
  label: string;
  value?: number | null;
  warn?: number;
  bad?: number;
}) {
  const tone = metricTone(value, warn, bad);
  const width = value === null || value === undefined || Number.isNaN(value) ? 0 : Math.min(Math.max(value, 0), 100);

  return (
    <span className="resource-cell">
      <small>
        <Icon size={13} />
        {label}
      </small>
      <b>{pct(value)}</b>
      <span className={`mini-bar ${tone}`}>
        <i style={{ width: `${width}%` }} />
      </span>
    </span>
  );
}

function hostLine(machine: Machine) {
  const hosts = [machine.sysHost, machine.phyHost].filter(Boolean).join(' / ');
  if (hosts) return hosts;
  return hasAnyMetric(machine) ? modeText[machine.mode] : '暂无 Zabbix 指标';
}

function machineSpecLine(machine: Machine) {
  const cores = machine.cpuCores ? `${formatNumber(machine.cpuCores, 0)} 核` : '';
  if (machine.cpuModel && cores) return `${machine.cpuModel} · ${cores}`;
  if (machine.cpuModel) return machine.cpuModel;
  if (cores) return `CPU ${cores}`;
  return 'CPU 信息待采集';
}

function metricTone(value: number | null | undefined, warn: number, bad: number): MetricTone {
  if (value === null || value === undefined || Number.isNaN(value)) return 'empty';
  if (value >= bad) return 'bad';
  if (value >= warn) return 'warn';
  return 'ok';
}

function sum(values: Array<number | null | undefined>) {
  return values.reduce<number>((total, value) => total + (value ?? 0), 0);
}

function panelPath(panel: Panel) {
  if (panel === 'pve') return '/pve';
  if (panel === 'security') return '/security';
  return '/hosts';
}

function grafanaDashboardUrl(
  grafana: GrafanaIntegration | null | undefined,
  id: string,
  params?: Record<string, string>
) {
  const dashboard = grafana?.dashboards.find((item) => item.id === id);
  if (!dashboard) return null;
  if (!params) return dashboard.url;
  const url = new URL(dashboard.url);
  Object.entries(params).forEach(([key, value]) => url.searchParams.set(key, value));
  return url.toString();
}

function panelFromLocation(location: { pathname: string; search: string }): Panel {
  if (location.pathname.startsWith('/security')) return 'security';
  if (location.pathname.startsWith('/pve')) return 'pve';
  if (location.pathname.startsWith('/hosts')) return 'hosts';
  return readEnum(new URLSearchParams(location.search).get('panel'), ['hosts', 'pve', 'security'], 'hosts');
}

function securityAttention(wazuh: WazuhSummary) {
  if (!wazuh.enabled) return 0;
  return Math.round(
    wazuh.inactiveAgents
    + wazuh.managerCriticalDown
    + (wazuh.alerts.severityCounts.critical ?? 0)
    + (wazuh.alerts.severityCounts.high ?? 0)
    + wazuh.ssh.failed
    + wazuh.ssh.invalidUser
    + wazuh.ssh.rootLogin
    + wazuh.fim.keyEvents
  );
}

function buildSecurityActions(wazuh: WazuhSummary): SecurityAction[] {
  const actions: SecurityAction[] = [];
  const criticalAlerts = wazuh.alerts.severityCounts.critical ?? 0;
  const highAlerts = wazuh.alerts.severityCounts.high ?? 0;
  const sshAttack = wazuh.ssh.failed + wazuh.ssh.invalidUser;
  const topRule = wazuh.alerts.topRules[0];
  const topAlertAgent = wazuh.alerts.topAgents[0];
  const topSource = wazuh.ssh.topSources[0];
  const topPath = wazuh.fim.topPaths[0];
  const rootLoginEvent = wazuh.ssh.recent.find((event) => event.outcome === 'root_login');
  const rootcheckAgent = [...wazuh.agents].sort((a, b) => (b.rootcheckOutstanding ?? 0) - (a.rootcheckOutstanding ?? 0))[0];

  if (wazuh.apiUp === false || wazuh.indexerUp === false) {
    actions.push({
      key: 'pipeline',
      icon: Database,
      title: '安全数据链路异常',
      value: `API ${boolText(wazuh.apiUp)} / Indexer ${boolText(wazuh.indexerUp)}`,
      detail: '先查 Wazuh exporter、Prometheus target、API/Indexer；链路恢复前不要按当前告警数下结论',
      tone: 'bad',
    });
  }

  if (wazuh.managerCriticalDown > 0) {
    actions.push({
      key: 'manager',
      icon: ShieldAlert,
      title: 'Wazuh 核心进程异常',
      value: formatNumber(wazuh.managerCriticalDown, 0),
      detail: '影响告警分析和 Agent 通信；先在 Wazuh 主机检查 manager 进程与 exporter 日志',
      tone: 'bad',
    });
  }

  if (criticalAlerts > 0) {
    actions.push({
      key: 'critical-alerts',
      icon: ShieldAlert,
      title: 'Critical 告警',
      value: formatNumber(criticalAlerts, 0),
      detail: criticalAlertDetail(topRule, topAlertAgent),
      tone: 'bad',
    });
  }

  if (wazuh.ssh.rootLogin > 0) {
    actions.push({
      key: 'root-login',
      icon: KeyRound,
      title: 'Root SSH 登录',
      value: formatNumber(wazuh.ssh.rootLogin, 0),
      detail: rootLoginEvent
        ? `${rootLoginEvent.agentName ?? '未知主机'} · ${rootLoginEvent.srcip ?? '未知来源'} · ${rootLoginEvent.user ?? 'root'}`
        : '先核对来源 IP、登录时间和授权工单；未知登录立即查命令历史',
      tone: 'bad',
    });
  }

  if (wazuh.fim.keyEvents > 0) {
    actions.push({
      key: 'fim',
      icon: FileWarning,
      title: '关键文件变更',
      value: formatNumber(wazuh.fim.keyEvents, 0),
      detail: topPath ? `${topPath.label} · ${formatNumber(topPath.value, 0)} 次；先确认是否为变更窗口` : '优先核对 ssh、sudo、cron、systemd 相关变更',
      tone: 'warn',
    });
  }

  if (sshAttack > 0) {
    actions.push({
      key: 'ssh-attack',
      icon: AlertTriangle,
      title: 'SSH 失败/非法用户',
      value: formatNumber(sshAttack, 0),
      detail: topSource ? `${topSource.label} · ${formatNumber(topSource.value, 0)} 次；判断是否封禁或加白` : '按来源 IP 和用户名聚合，判断暴力尝试还是误配置',
      tone: 'warn',
    });
  }

  if (highAlerts > 0) {
    actions.push({
      key: 'high-alerts',
      icon: ShieldAlert,
      title: 'High 告警',
      value: formatNumber(highAlerts, 0),
      detail: topRule ? `同 Critical 规则集中在 ${topRule.label}；先合并同类事件` : '排在 Critical 后处理，按规则和主机集中度合并',
      tone: 'warn',
    });
  }

  if (wazuh.inactiveAgents > 0) {
    actions.push({
      key: 'inactive-agents',
      icon: UserCheck,
      title: 'Agent 非 active',
      value: formatNumber(wazuh.inactiveAgents, 0),
      detail: '先区分主机离线还是 agent 故障；离线主机同时核对 Zabbix/PVE 状态',
      tone: 'warn',
    });
  }

  if (wazuh.rootcheckOutstanding > 0) {
    actions.push({
      key: 'rootcheck',
      icon: FileWarning,
      title: 'Rootcheck 未处理',
      value: formatNumber(wazuh.rootcheckOutstanding, 0),
      detail: rootcheckAgent?.rootcheckOutstanding ? `${rootcheckAgent.name} · ${formatNumber(rootcheckAgent.rootcheckOutstanding, 0)} 项 outstanding` : '优先处理 outstanding 项，不按 syscheck 总量排序',
      tone: 'warn',
    });
  }

  if (!actions.length) {
    actions.push({
      key: 'ok',
      icon: ShieldCheck,
      title: '链路正常，继续巡检',
      value: `${wazuh.activeAgents}/${wazuh.agentTotal}`,
      detail: '采集链路正常，Agent 全部 active；继续按最新事件巡检',
      tone: 'good',
    });
  }

  return actions;
}

function criticalAlertDetail(rule?: WazuhTopItem, agent?: WazuhTopItem) {
  const ruleText = rule
    ? `${rule.label}${rule.description ? ` · ${rule.description}` : ''}`
    : '无规则聚合数据';
  const agentText = agent ? `影响主机集中在 ${agent.label}` : '先按影响主机聚合';
  return `${ruleText}；${agentText}`;
}

function agentAttentionRank(agent: WazuhSummary['agents'][number]) {
  if (agent.status !== 'active') return 3;
  if ((agent.rootcheckOutstanding ?? 0) > 0) return 2;
  if (agent.groupConfigSynced === false) return 1;
  return 0;
}

function agentAttentionText(agent: WazuhSummary['agents'][number]) {
  if (agent.status !== 'active') return 'Agent 非 active';
  if ((agent.rootcheckOutstanding ?? 0) > 0) return `Rootcheck ${formatNumber(agent.rootcheckOutstanding, 0)}`;
  if (agent.groupConfigSynced === false) return '配置未同步';
  return '无异常';
}

function moduleEnabled(wazuh: WazuhSummary, module: string) {
  return wazuh.modules.includes(module);
}

function boolText(value?: boolean | null) {
  if (value === true) return '正常';
  if (value === false) return '中断';
  return '无数据';
}

function severityTone(value: string) {
  const normalized = value.toLowerCase();
  if (['critical', 'high', 'root_login', 'deleted'].includes(normalized)) return 'bad';
  if (['medium', 'failed', 'invalid_user', 'modified', 'added', 'warning'].includes(normalized)) return 'warn';
  if (['low', 'info', 'success', 'ok'].includes(normalized)) return 'ok';
  return 'neutral';
}

function zabbixHostVariable(machine: Machine) {
  return machine.sysHost ?? machine.phyHost ?? machine.id;
}

function readHostSettings(params: URLSearchParams): HostSettings {
  return {
    group: readEnum(params.get('hostGroup') ?? params.get('group'), ['all', 'server', 'cloud'], 'all'),
    sort: readEnum(params.get('hostSort'), ['health', 'name', 'cpu', 'mem', 'disk', 'net', 'uptime', 'problems'], 'health'),
    dir: readEnum(params.get('hostDir'), ['asc', 'desc'], 'desc')
  };
}

function readPVESettings(params: URLSearchParams): PVESettings {
  return {
    type: readEnum(params.get('pveType') ?? params.get('type'), ['all', 'qemu', 'lxc'], 'all'),
    node: params.get('pveNode') ?? params.get('node') ?? 'all',
    sort: readEnum(params.get('pveSort'), ['cpu', 'mem', 'disk', 'uptime', 'name', 'vmid', 'node', 'type', 'status'], 'cpu'),
    dir: readEnum(params.get('pveDir'), ['asc', 'desc'], 'desc')
  };
}

function readEnum<T extends string>(value: string | null, allowed: readonly T[], fallback: T): T {
  return value && allowed.includes(value as T) ? (value as T) : fallback;
}

function hostGroupOf(machine: Machine): Exclude<HostGroup, 'all'> {
  const text = [machine.id, machine.sysHost, machine.phyHost].filter(Boolean).join(' ').toLowerCase();
  if (text.includes('cloud') || machine.id.toLowerCase().startsWith('cloud_')) return 'cloud';
  if (machine.mode === 'standalone' && !machine.sysHost && !machine.phyHost) return 'cloud';
  return 'server';
}

function sortMachines(machines: Machine[], sort: HostSort, dir: SortDir) {
  return [...machines].sort((a, b) => {
    const result = compareSortValue(hostSortValue(a, sort), hostSortValue(b, sort), dir);
    return result || a.id.localeCompare(b.id, 'zh-CN');
  });
}

function hostSortValue(machine: Machine, sort: HostSort): string | number | null | undefined {
  if (sort === 'health') return healthSeverity(machine.health);
  if (sort === 'name') return machine.id;
  if (sort === 'cpu') return machine.cpuPct;
  if (sort === 'mem') return machine.memPct;
  if (sort === 'disk') return machine.diskPct;
  if (sort === 'net') return machine.netBps;
  if (sort === 'uptime') return machine.uptimeSec;
  return machine.problems.length;
}

function healthSeverity(health: Health) {
  return {
    critical: 6,
    offline: 5,
    warning: 4,
    stale: 3,
    unknown: 2,
    ok: 1
  }[health];
}

interface PVEView {
  guests: PVEResource[];
  totalGuests: number;
  typeCounts: Record<PVETypeFilter, number>;
  nodeOptions: Array<{ value: string; label: string; count: number }>;
}

function buildPVEView(pve: PVESummary, settings: PVESettings): PVEView {
  const typeCounts = {
    all: pve.guests.length,
    qemu: pve.guests.filter((guest) => guest.type === 'qemu').length,
    lxc: pve.guests.filter((guest) => guest.type === 'lxc').length
  };
  const nodeMap = new Map<string, { value: string; label: string; count: number }>();
  const multiServer = new Set(pve.nodes.map((node) => node.server)).size > 1;

  pve.nodes.forEach((node) => {
    const value = pveNodeKey(node.server, node.node);
    nodeMap.set(value, {
      value,
      label: multiServer ? `${node.server}/${node.node}` : node.node,
      count: 0
    });
  });
  pve.guests.forEach((guest) => {
    const value = pveNodeKey(guest.server, guest.node);
    const current = nodeMap.get(value) ?? {
      value,
      label: multiServer ? `${guest.server}/${guest.node}` : guest.node,
      count: 0
    };
    current.count += 1;
    nodeMap.set(value, current);
  });

  const nodeOptions = [...nodeMap.values()].sort((a, b) => a.label.localeCompare(b.label, 'zh-CN'));
  const activeNode = nodeOptions.some((node) => node.value === settings.node) ? settings.node : 'all';
  const guests = sortPVEGuests(
    pve.guests.filter((guest) => (settings.type === 'all' || guest.type === settings.type) && (activeNode === 'all' || pveNodeKey(guest.server, guest.node) === activeNode)),
    settings.sort,
    settings.dir
  );

  return { guests, totalGuests: pve.guests.length, typeCounts, nodeOptions };
}

function sortPVEGuests(guests: PVEResource[], sort: PVESort, dir: SortDir) {
  return [...guests].sort((a, b) => {
    const result = compareSortValue(pveSortValue(a, sort), pveSortValue(b, sort), dir);
    return result || a.node.localeCompare(b.node, 'zh-CN') || a.vmid - b.vmid;
  });
}

function pveSortValue(guest: PVEResource, sort: PVESort): string | number | null | undefined {
  if (sort === 'cpu') return guest.cpuPct;
  if (sort === 'mem') return usagePct(guest.memBytes, guest.maxMemBytes) ?? guest.memBytes;
  if (sort === 'disk') return pveStorageUsagePct(guest) ?? pveStorageCapacity(guest);
  if (sort === 'uptime') return guest.uptimeSec;
  if (sort === 'name') return guest.name;
  if (sort === 'vmid') return guest.vmid;
  if (sort === 'node') return `${guest.server}/${guest.node}`;
  if (sort === 'type') return guest.type;
  return pveStatusRank(guest.status);
}

function pveStatusRank(status: string) {
  if (status === 'running') return 3;
  if (status === 'paused') return 2;
  if (status === 'stopped') return 1;
  return 0;
}

function pveNodeKey(server: string, node: string) {
  return `${server}/${node}`;
}

function compareSortValue(a: string | number | null | undefined, b: string | number | null | undefined, dir: SortDir) {
  const aMissing = a === null || a === undefined || (typeof a === 'number' && Number.isNaN(a));
  const bMissing = b === null || b === undefined || (typeof b === 'number' && Number.isNaN(b));
  if (aMissing && bMissing) return 0;
  if (aMissing) return 1;
  if (bMissing) return -1;

  let result = 0;
  if (typeof a === 'string' || typeof b === 'string') {
    result = String(a).localeCompare(String(b), 'zh-CN', { numeric: true });
  } else {
    result = a - b;
  }
  return dir === 'desc' ? -result : result;
}

function usagePct(value?: number | null, total?: number | null) {
  if (value === null || value === undefined || total === null || total === undefined || total <= 0) return null;
  return Math.min(Math.max((value / total) * 100, 0), 100);
}

function pveStorageUsagePct(guest: PVEResource) {
  if (guest.type === 'qemu' && !(guest.diskBytes && guest.diskBytes > 0)) return null;
  return usagePct(guest.diskBytes, guest.maxDiskBytes);
}

function pveStorageCapacity(guest: PVEResource) {
  if (guest.maxDiskBytes && guest.maxDiskBytes > 0) return guest.maxDiskBytes;
  if (guest.diskBytes && guest.diskBytes > 0) return guest.diskBytes;
  return null;
}

function pveStorageCapacityDetail(guest: PVEResource, hasCapacity: boolean) {
  if (!hasCapacity) return '容量未上报';
  return guest.type === 'qemu' ? '已分配虚拟盘' : '已用容量';
}

function capacityText(value?: number | null, total?: number | null) {
  if (value === null || value === undefined || total === null || total === undefined) return '—';
  return `${bytes(value)} / ${bytes(total)}`;
}

function reportingState(machine: Machine): ReportingState {
  if (machine.stale || machine.health === 'stale') return 'stale';
  if (machine.agentUp === false || machine.health === 'offline') return 'offline';
  if (machine.agentUp === true) return 'online';
  if (machine.health !== 'unknown' && hasAnyMetric(machine)) return 'online';
  return 'unknown';
}

function hasAnyMetric(machine: Machine) {
  return [machine.cpuPct, machine.memPct, machine.diskPct, machine.netBps, machine.maxTempC, machine.fanRpm].some(
    (value) => value !== null && value !== undefined && !Number.isNaN(value)
  );
}

function seenAge(value?: string | null) {
  if (!value) return '-';
  const time = new Date(value).getTime();
  if (Number.isNaN(time)) return '-';
  const seconds = Math.max(Math.floor((Date.now() - time) / 1000), 0);
  if (seconds < 60) return `${seconds} 秒前`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)} 分钟前`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)} 小时前`;
  return `${Math.floor(seconds / 86400)} 天前`;
}

function uptimeDisplay(machine: Machine) {
  if (machine.uptimeSec === null || machine.uptimeSec === undefined || Number.isNaN(machine.uptimeSec)) {
    return { label: '最近', value: seenAge(machine.updatedAt) };
  }
  return { label: '运行', value: duration(machine.uptimeSec) };
}

function duration(seconds: number) {
  if (seconds < 60) return `${Math.floor(seconds)} 秒`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)} 分钟`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)} 小时`;
  return `${Math.floor(seconds / 86400)} 天`;
}

function pveStatusText(status: string) {
  return {
    running: '运行中',
    stopped: '已停止',
    paused: '已暂停',
    unknown: '未知'
  }[status] ?? status;
}
