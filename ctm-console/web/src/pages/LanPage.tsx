import { useMemo, useState, type ReactNode } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  Activity,
  BadgeCheck,
  CircleHelp,
  EthernetPort,
  ExternalLink,
  RadioTower,
  Router
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { SearchInput } from '../components/SearchInput';
import { StatusPill } from '../components/StatusPill';
import { api } from '../lib/api';
import { dateTime, number as formatNumber } from '../lib/format';
import type { LanDevice, LanSummary } from '../types';

type Tone = 'good' | 'warn' | 'bad' | 'info' | 'neutral';
type LanFilter = 'online' | 'unknown-online' | 'known' | 'all';

const filterLabels: Record<LanFilter, string> = {
  online: '在线',
  'unknown-online': '未知在线',
  known: '已知',
  all: '全部'
};

export function LanPage() {
  const [search, setSearch] = useState('');
  const [filter, setFilter] = useState<LanFilter>('online');
  const lan = useQuery({ queryKey: ['lan'], queryFn: api.lan });
  const grafana = useQuery({ queryKey: ['grafana'], queryFn: api.grafana });
  const lanDashboard = grafana.data?.dashboards.find((dashboard) => dashboard.id === 'lan');
  const rows = useMemo(() => {
    if (!lan.data) return [];
    const query = search.trim().toLowerCase();
    return lan.data.devices.filter((device) => {
      if (!matchesFilter(device, filter)) return false;
      if (!query) return true;
      return [device.name, device.ip, device.mac, device.iface, device.known ? 'known' : 'unknown']
        .filter(Boolean)
        .join(' ')
        .toLowerCase()
        .includes(query);
    });
  }, [lan.data, search, filter]);

  if (lan.isLoading) {
    return <div className="loading-screen">加载中</div>;
  }

  if (lan.isError || !lan.data) {
    return (
      <div className="loading-screen error">
        <strong>无法加载 LAN 资产</strong>
        <span>{lan.error instanceof Error ? lan.error.message : '请检查 API 服务状态'}</span>
      </div>
    );
  }

  const data = lan.data;

  return (
    <div className="dashboard-page lan-page">
      <section className="overview-hero">
        <div>
          <h1>局域网资产</h1>
          <p>
            更新时间 <strong>{dateTime(data.updatedAt)}</strong>
          </p>
        </div>
        <div className="source-strip">
          <span className={data.stale ? 'warn' : 'ok'}>
            <Activity size={14} />
            {data.stale ? '缓存数据' : 'Prometheus'}
          </span>
          <span className={data.unknownOnline ? 'warn' : 'ok'}>
            <CircleHelp size={14} />
            {data.unknownOnline} 未知在线
          </span>
          {lanDashboard && (
            <a href={lanDashboard.url} target="_blank" rel="noreferrer">
              <ExternalLink size={14} />
              Grafana
            </a>
          )}
        </div>
      </section>

      <section className="summary-grid" aria-label="LAN counters">
        <SummaryCard
          icon={Router}
          title="LAN 资产"
          value={formatNumber(data.totalDevices, 0)}
          detail={`${formatNumber(data.onlineDevices, 0)} 在线 / ${data.interfaces.length} 接口`}
          tone="info"
        />
        <SummaryCard
          icon={RadioTower}
          title="在线设备"
          value={formatNumber(data.onlineDevices, 0)}
          detail={`${formatNumber(data.knownOnline, 0)} 已知 / ${formatNumber(data.unknownOnline, 0)} 未知`}
          tone={data.onlineDevices ? 'good' : 'neutral'}
        />
        <SummaryCard
          icon={CircleHelp}
          title="未知在线"
          value={formatNumber(data.unknownOnline, 0)}
          detail={`${formatNumber(data.unknownDevices, 0)} 未登记历史资产`}
          tone={data.unknownOnline ? 'warn' : 'neutral'}
        />
        <SummaryCard
          icon={EthernetPort}
          title="采集接口"
          value={data.interfaces.length || '—'}
          detail={interfaceText(data)}
          tone="neutral"
        />
      </section>

      <section className="control-bar lan-control-bar" aria-label="LAN filters">
        <div className="control-group">
          <span className="control-label">
            <BadgeCheck size={15} />
            状态
          </span>
          <div className="segmented-control">
            {(Object.keys(filterLabels) as LanFilter[]).map((value) => (
              <button
                className={filter === value ? 'active' : ''}
                type="button"
                key={value}
                onClick={() => setFilter(value)}
              >
                {filterLabels[value]}
                <b>{filterCount(data, value)}</b>
              </button>
            ))}
          </div>
        </div>
        <SearchInput value={search} onChange={setSearch} placeholder="搜索 IP、MAC、名称" />
      </section>

      <section className="security-panel lan-panel">
        <div className="security-panel-head">
          <h2>设备清单</h2>
          <span>
            {formatNumber(rows.length, 0)} / {formatNumber(data.devices.length, 0)}
          </span>
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>设备</th>
                <th>状态</th>
                <th>IP</th>
                <th>MAC</th>
                <th>接口</th>
                <th>资产</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((device) => (
                <tr key={device.id}>
                  <td>
                    <strong>{deviceTitle(device)}</strong>
                    <small>{deviceSubtitle(device)}</small>
                  </td>
                  <td>
                    <StatusPill health={device.health} compact />
                  </td>
                  <td>
                    <code>{device.ip}</code>
                  </td>
                  <td>
                    <code>{device.mac}</code>
                  </td>
                  <td>{device.iface || '—'}</td>
                  <td>
                    <span className={`lan-known ${device.known ? 'known' : 'unknown'}`}>
                      {device.known ? '已知' : '未知'}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {!rows.length && <div className="lan-empty">暂无匹配设备</div>}
        </div>
      </section>
    </div>
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

function matchesFilter(device: LanDevice, filter: LanFilter) {
  if (filter === 'online') return device.online;
  if (filter === 'unknown-online') return device.online && !device.known;
  if (filter === 'known') return device.known;
  return true;
}

function filterCount(data: LanSummary, filter: LanFilter) {
  if (filter === 'online') return data.onlineDevices;
  if (filter === 'unknown-online') return data.unknownOnline;
  if (filter === 'known') return data.knownDevices;
  return data.totalDevices;
}

function interfaceText(data: LanSummary) {
  if (!data.interfaces.length) return '无接口数据';
  if (data.interfaces.length <= 2) return data.interfaces.join(' / ');
  return `${data.interfaces.slice(0, 2).join(' / ')} +${data.interfaces.length - 2}`;
}

function deviceTitle(device: LanDevice) {
  const name = device.name?.trim();
  if (name && name.toLowerCase() !== 'unknown') return name;
  return device.ip;
}

function deviceSubtitle(device: LanDevice) {
  const name = device.name?.trim();
  if (name && name.toLowerCase() !== 'unknown') return device.ip;
  return device.mac;
}
