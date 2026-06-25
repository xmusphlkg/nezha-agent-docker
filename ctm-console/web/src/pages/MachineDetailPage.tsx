import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link, useParams } from 'react-router-dom';
import {
  Activity,
  ArrowLeft,
  Clock3,
  Cpu,
  Fan,
  FileWarning,
  HardDrive,
  KeyRound,
  MemoryStick,
  Network,
  Server,
  ShieldAlert,
  ShieldCheck,
  Thermometer,
  UserCheck
} from 'lucide-react';
import { EChart } from '../components/EChart';
import { EmptyState } from '../components/EmptyState';
import { HealthBar } from '../components/HealthBar';
import { MetricTile } from '../components/MetricTile';
import { StatusPill } from '../components/StatusPill';
import { api } from '../lib/api';
import { age, bps, bytes, dateTime, healthText, number, pct } from '../lib/format';
import type { Health, Machine, MachineSecurity, Problem, WazuhRecentEvent } from '../types';

export function MachineDetailPage() {
  const { id = '' } = useParams();
  const [range, setRange] = useState<'1h' | '6h' | '24h'>('1h');
  const detail = useQuery({ queryKey: ['machine', id], queryFn: () => api.machine(id), enabled: Boolean(id) });
  const series = useQuery({
    queryKey: ['machine-series', id, range],
    queryFn: () => api.machineSeries(id, range),
    enabled: Boolean(id)
  });

  const chartOption = useMemo(() => {
    const points = series.data?.points ?? [];
    const times = points.map((point) => new Date(point.t * 1000).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }));
    return {
      color: ['#2f7df6', '#15a36d', '#d97706', '#7c3aed', '#dc2626'],
      tooltip: { trigger: 'axis' },
      legend: { top: 4, textStyle: { color: '#5b6472' } },
      grid: { top: 42, left: 42, right: 18, bottom: 34 },
      xAxis: { type: 'category', data: times, boundaryGap: false },
      yAxis: { type: 'value', splitLine: { lineStyle: { color: '#e8edf2' } } },
      series: [
        { name: 'CPU %', type: 'line', showSymbol: false, data: points.map((point) => point.cpuPct ?? null) },
        { name: '内存 %', type: 'line', showSymbol: false, data: points.map((point) => point.memPct ?? null) },
        { name: '磁盘 %', type: 'line', showSymbol: false, data: points.map((point) => point.diskPct ?? null) },
        { name: '温度 °C', type: 'line', showSymbol: false, data: points.map((point) => point.maxTempC ?? null) }
      ]
    };
  }, [series.data]);

  if (detail.isLoading) return <div className="loading-screen">加载中</div>;
  if (detail.isError || !detail.data) {
    return (
      <div className="loading-screen error">
        <strong>无法加载机器详情</strong>
        <span>{detail.error instanceof Error ? detail.error.message : '请检查 API 服务状态'}</span>
      </div>
    );
  }

  const machine = detail.data.machine;
  const security = detail.data.security;
  const SecurityIcon = security.health === 'ok' ? ShieldCheck : ShieldAlert;

  return (
    <div className="machine-page">
      <header className="machine-hero">
        <div className="machine-title">
          <Link to="/hosts" className="back-link">
            <ArrowLeft size={16} />
            主机监控
          </Link>
          <div>
            <h1>{machine.id}</h1>
            <p>{machineLine(machine)}</p>
          </div>
        </div>
        <div className="machine-hero-status">
          <StatusPill health={machine.health} />
          <span className={`security-status ${statusClass(security.health)}`}>{security.enabled ? `安全 ${healthText(security.health)}` : 'Wazuh 未启用'}</span>
        </div>
      </header>

      <section className="metric-grid detail-metrics">
        <MetricTile label="CPU" value={pct(machine.cpuPct)} icon={Cpu} tone={(machine.cpuPct ?? 0) > 85 ? 'warn' : 'default'} />
        <MetricTile label="内存" value={pct(machine.memPct)} icon={MemoryStick} tone={(machine.memPct ?? 0) > 85 ? 'warn' : 'default'} />
        <MetricTile label="磁盘" value={pct(machine.diskPct)} icon={HardDrive} tone={(machine.diskPct ?? 0) > 85 ? 'warn' : 'default'} />
        <MetricTile label="网络" value={bps(machine.netBps)} icon={Activity} />
        <MetricTile label="温度" value={machine.maxTempC ? `${number(machine.maxTempC, 1)}°C` : '—'} icon={Thermometer} tone={(machine.maxTempC ?? 0) > 70 ? 'warn' : 'default'} />
        <MetricTile label="安全" value={securityMetric(security)} icon={SecurityIcon} tone={tileTone(security.health)} />
      </section>

      <section className="machine-overview-grid">
        <InfoPanel machine={machine} />
        <SecuritySummaryPanel security={security} />
      </section>

      <section className="machine-panel">
        <div className="panel-head">
          <h2>资源趋势</h2>
          <div className="segmented">
            {(['1h', '6h', '24h'] as const).map((item) => (
              <button key={item} type="button" className={range === item ? 'active' : ''} onClick={() => setRange(item)}>
                {item}
              </button>
            ))}
          </div>
        </div>
        {series.data?.points.length ? <EChart option={chartOption} /> : <EmptyState label="暂无历史序列" />}
      </section>

      <section className="machine-grid attention-grid">
        <ProblemPanel problems={detail.data.problems} />
        <HardwarePanel machine={machine} />
      </section>

      <SecurityDetailPanel security={security} />
    </div>
  );
}

function InfoPanel({ machine }: { machine: Machine }) {
  return (
    <section className="machine-panel identity-panel">
      <div className="panel-head">
        <h2>系统身份</h2>
        <span>{dateTime(machine.updatedAt)}</span>
      </div>
      <div className="identity-grid">
        <InfoPair icon={Server} label="系统通道" value={machine.sysHost ?? '—'} />
        <InfoPair icon={Server} label="硬件通道" value={machine.phyHost ?? '—'} />
        <InfoPair icon={Cpu} label="CPU" value={machine.cpuModel ?? '—'} detail={machine.cpuCores ? `${number(machine.cpuCores)} cores` : undefined} />
        <InfoPair icon={Activity} label="系统" value={machine.osName ?? '—'} detail={machine.uptimeSec ? `运行 ${age(machine.uptimeSec)}` : undefined} />
      </div>
      <div className="resource-strip">
        <ResourceLine label="CPU" value={machine.cpuPct} />
        <ResourceLine label="内存" value={machine.memPct} detail={capacity(machine.memBytes, machine.maxMemBytes)} />
        <ResourceLine label="磁盘" value={machine.diskPct} detail={capacity(machine.diskBytes, machine.maxDiskBytes)} />
      </div>
    </section>
  );
}

function SecuritySummaryPanel({ security }: { security: MachineSecurity }) {
  const agentCount = security.matchedAgents.length;
  const activeAgents = security.matchedAgents.filter((agent) => agent.status === 'active').length;

  return (
    <section className="machine-panel security-focus">
      <div className="panel-head">
        <h2>安全态势</h2>
        <span className={`security-status ${statusClass(security.health)}`}>{healthText(security.health)}</span>
      </div>
      <div className="security-score-grid">
        <SecurityScore icon={UserCheck} label="Wazuh Agent" value={security.enabled ? `${activeAgents}/${agentCount}` : '—'} tone={agentCount && activeAgents === agentCount ? 'ok' : 'warn'} />
        <SecurityScore icon={KeyRound} label="SSH 24h" value={number(security.sshTotal)} tone={security.sshFailed || security.sshInvalidUser ? 'warn' : 'ok'} />
        <SecurityScore icon={Activity} label="仍在线 SSH" value={number(security.sshActiveSessions)} tone={security.sshActiveSessions ? 'warn' : 'ok'} />
        <SecurityScore icon={FileWarning} label="关键文件" value={number(security.fimKeyEvents)} tone={security.fimKeyEvents ? 'warn' : 'ok'} />
      </div>
      <div className="security-mini-line">
        <span>失败 {number(security.sshFailed + security.sshInvalidUser)}</span>
        <span>Root {number(security.sshRootLogin)}</span>
        <span>Critical {number(security.alertSeverityCounts.critical ?? 0)}</span>
        <span>High {number(security.alertSeverityCounts.high ?? 0)}</span>
      </div>
    </section>
  );
}

function ProblemPanel({ problems }: { problems: Machine['problems'] }) {
  const sorted = [...problems].sort((left, right) => {
    const ackDelta = Number(left.acknowledged) - Number(right.acknowledged);
    if (ackDelta !== 0) return ackDelta;
    const severityDelta = problemSeverityRank(left.severity) - problemSeverityRank(right.severity);
    if (severityDelta !== 0) return severityDelta;
    return right.ageSec - left.ageSec;
  });
  const openCount = problems.filter((problem) => !problem.acknowledged).length;

  return (
    <section className="machine-panel">
      <div className="panel-head">
        <h2>问题事件</h2>
        <span>{openCount ? `未确认 ${openCount} / 共 ${problems.length}` : `${problems.length}`}</span>
      </div>
      {sorted.length ? (
        <div className="table-wrap detail-table problem-table">
          <table>
            <thead>
              <tr>
                <th>状态</th>
                <th>级别</th>
                <th>事件</th>
                <th>来源主机</th>
                <th>持续</th>
                <th>事件 ID</th>
              </tr>
            </thead>
            <tbody>
              {sorted.map((problem) => (
                <tr key={`${problem.source}-${problem.eventId}-${problem.host}-${problem.name}`}>
                  <td>
                    <span className={`ack-badge ${problem.acknowledged ? 'ack' : 'open'}`}>
                      {problem.acknowledged ? '已确认' : '未确认'}
                    </span>
                  </td>
                  <td>
                    <span className={`severity-pill ${problemSeverityClass(problem.severity)}`}>
                      {problemSeverityText(problem.severity)}
                    </span>
                  </td>
                  <td>
                    <strong className="problem-title">{problem.name}</strong>
                    <small>{problem.source}</small>
                  </td>
                  <td>{problem.host || '—'}</td>
                  <td>{age(problem.ageSec)}</td>
                  <td><code>{problem.eventId || '—'}</code></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <EmptyState label="无当前问题" />
      )}
    </section>
  );
}

function HardwarePanel({ machine }: { machine: Machine }) {
  return (
    <section className="machine-panel">
      <div className="panel-head">
        <h2>硬件状态</h2>
        <span>{machine.mode}</span>
      </div>
      <div className="hardware-grid">
        <InfoPair icon={Thermometer} label="最高温度" value={machine.maxTempC ? `${number(machine.maxTempC, 1)}°C` : '—'} />
        <InfoPair icon={Fan} label="风扇" value={machine.fanRpm ? `${number(machine.fanRpm)} RPM` : '—'} />
        <InfoPair icon={Network} label="网络吞吐" value={bps(machine.netBps)} />
        <InfoPair icon={Clock3} label="Agent" value={machine.agentUp === null || machine.agentUp === undefined ? '—' : machine.agentUp ? 'up' : 'down'} />
      </div>
    </section>
  );
}

function SecurityDetailPanel({ security }: { security: MachineSecurity }) {
  return (
    <section className="machine-grid security-detail-grid">
      <section className="machine-panel">
        <div className="panel-head">
          <h2>Wazuh Agent</h2>
          <span>{security.matchedAgents.length}</span>
        </div>
        <div className="table-wrap detail-table">
          <table>
            <thead>
              <tr>
                <th>Agent</th>
                <th>状态</th>
                <th>IP</th>
                <th>系统</th>
                <th>Keepalive</th>
                <th>Rootcheck</th>
              </tr>
            </thead>
            <tbody>
              {security.matchedAgents.map((agent) => (
                <tr key={agent.id}>
                  <td>
                    <strong>{agent.name}</strong>
                    <small>{agent.id}</small>
                  </td>
                  <td><span className={`security-status ${agent.status === 'active' ? 'ok' : 'warn'}`}>{agent.status}</span></td>
                  <td>{agent.ip ?? '—'}</td>
                  <td>{[agent.osName, agent.osVersion].filter(Boolean).join(' ') || '—'}</td>
                  <td>{age(agent.lastKeepaliveAgeSec)}</td>
                  <td>{number(agent.rootcheckOutstanding)}</td>
                </tr>
              ))}
              {!security.matchedAgents.length && <EmptyRow colSpan={6} label={security.enabled ? '未匹配到 Wazuh Agent' : 'Wazuh 未启用'} />}
            </tbody>
          </table>
        </div>
      </section>

      <section className="machine-panel">
        <div className="panel-head">
          <h2>仍在线 SSH</h2>
          <span>{security.activeSessions.length}</span>
        </div>
        <div className="table-wrap detail-table">
          <table>
            <thead>
              <tr>
                <th>用户</th>
                <th>来源</th>
                <th>PID</th>
                <th>登录时间</th>
                <th>持续</th>
              </tr>
            </thead>
            <tbody>
              {security.activeSessions.map((session) => (
                <tr key={`${session.agentName}-${session.pid}-${session.openedAt}`}>
                  <td><strong>{session.user ?? '—'}</strong></td>
                  <td>{session.srcip ?? '—'}{session.srcport ? `:${session.srcport}` : ''}</td>
                  <td>{session.pid ?? '—'}</td>
                  <td>{dateTime(session.openedAt)}</td>
                  <td>{age(session.durationSec)}</td>
                </tr>
              ))}
              {!security.activeSessions.length && <EmptyRow colSpan={5} label="无仍在线 SSH 会话" />}
            </tbody>
          </table>
        </div>
      </section>

      <section className="machine-panel recent-security-panel">
        <div className="panel-head">
          <h2>安全事件</h2>
          <span>{security.recentEvents.length}</span>
        </div>
        <div className="event-list">
          {security.recentEvents.map((event, index) => (
            <article key={`${event.kind}-${event.timestamp}-${index}`} className={`security-event ${event.severity ?? 'info'}`}>
              <div>
                <strong>{eventTitle(event)}</strong>
                <small>{eventMeta(event)}</small>
              </div>
              <time>{dateTime(event.timestamp)}</time>
            </article>
          ))}
          {!security.recentEvents.length && <EmptyState label="无近期安全事件" />}
        </div>
      </section>
    </section>
  );
}

function InfoPair({ icon: Icon, label, value, detail }: { icon: typeof Server; label: string; value: string; detail?: string }) {
  return (
    <div className="info-pair">
      <Icon size={17} />
      <span>{label}</span>
      <strong>{value}</strong>
      {detail && <small>{detail}</small>}
    </div>
  );
}

function ResourceLine({ label, value, detail }: { label: string; value?: number | null; detail?: string }) {
  return (
    <div className="resource-line">
      <span>{label}</span>
      <HealthBar value={value} />
      <b>{pct(value)}</b>
      {detail && <small>{detail}</small>}
    </div>
  );
}

function SecurityScore({ icon: Icon, label, value, tone }: { icon: typeof ShieldCheck; label: string; value: string; tone: 'ok' | 'warn' | 'bad' }) {
  return (
    <div className={`security-score ${tone}`}>
      <Icon size={17} />
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function EmptyRow({ colSpan, label }: { colSpan: number; label: string }) {
  return (
    <tr>
      <td className="table-empty" colSpan={colSpan}>{label}</td>
    </tr>
  );
}

function machineLine(machine: Machine) {
  return [machine.osName, machine.cpuModel, machine.cpuCores ? `${number(machine.cpuCores)} cores` : null].filter(Boolean).join(' · ') || '—';
}

function capacity(used?: number | null, total?: number | null) {
  if (!used || !total) return undefined;
  return `${bytes(used)} / ${bytes(total)}`;
}

function securityMetric(security: MachineSecurity) {
  if (!security.enabled) return '—';
  if (!security.matchedAgents.length) return '未匹配';
  const attention = (security.sshFailed + security.sshInvalidUser + security.sshRootLogin + security.fimKeyEvents + (security.alertSeverityCounts.critical ?? 0) + (security.alertSeverityCounts.high ?? 0));
  return attention ? number(attention) : healthText(security.health);
}

function tileTone(health: Health): 'default' | 'good' | 'warn' | 'bad' {
  if (health === 'ok') return 'good';
  if (health === 'critical' || health === 'offline') return 'bad';
  if (health === 'warning' || health === 'stale') return 'warn';
  return 'default';
}

function statusClass(health: Health) {
  if (health === 'ok') return 'ok';
  if (health === 'critical' || health === 'offline') return 'bad';
  if (health === 'warning' || health === 'stale') return 'warn';
  return '';
}

function problemSeverityRank(severity: string) {
  const order: Record<string, number> = {
    disaster: 0,
    high: 1,
    critical: 1,
    average: 2,
    warning: 3,
    information: 4,
    info: 4,
    'not-classified': 5,
    unknown: 6
  };
  return order[severity] ?? 6;
}

function problemSeverityClass(severity: string) {
  if (severity === 'disaster' || severity === 'high' || severity === 'critical') return 'bad';
  if (severity === 'average' || severity === 'warning') return 'warn';
  if (severity === 'information' || severity === 'info') return 'info';
  return 'muted';
}

function problemSeverityText(severity: Problem['severity']) {
  const text: Record<string, string> = {
    disaster: '灾难',
    high: '高',
    critical: '严重',
    average: '一般',
    warning: '警告',
    information: '信息',
    info: '信息',
    'not-classified': '未分类',
    unknown: '未知'
  };
  return text[severity] ?? severity;
}

function eventTitle(event: WazuhRecentEvent) {
  if (event.kind === 'ssh') return `${event.outcome ?? 'ssh'} · ${event.user ?? 'unknown'}`;
  return `${event.event ?? 'fim'} · ${event.path ?? 'unknown'}`;
}

function eventMeta(event: WazuhRecentEvent) {
  if (event.kind === 'ssh') return [event.agentName, event.srcip, event.description].filter(Boolean).join(' / ') || '—';
  return [event.agentName, event.ruleId, event.description].filter(Boolean).join(' / ') || '—';
}
