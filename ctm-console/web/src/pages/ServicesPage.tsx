import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Activity, Crosshair, Target, XCircle } from 'lucide-react';
import { MetricTile } from '../components/MetricTile';
import { SearchInput } from '../components/SearchInput';
import { StatusPill } from '../components/StatusPill';
import { api } from '../lib/api';
import { number } from '../lib/format';

export function ServicesPage() {
  const [search, setSearch] = useState('');
  const { data } = useQuery({ queryKey: ['services'], queryFn: api.services });
  const probes = useMemo(() => {
    const query = search.trim().toLowerCase();
    return (data?.probes ?? []).filter((probe) => !query || `${probe.job} ${probe.instance} ${probe.name ?? ''} ${probe.group ?? ''}`.toLowerCase().includes(query));
  }, [data, search]);

  if (!data) return <div className="page loading">加载中</div>;

  return (
    <div className="page">
      <div className="page-head">
        <h1>服务</h1>
        <div className="toolbar">
          <SearchInput value={search} onChange={setSearch} placeholder="搜索 probe、target" />
        </div>
      </div>
      <section className="metric-grid">
        <MetricTile label="Probe 总数" value={data.probeTotal} icon={Activity} />
        <MetricTile label="Probe 失败" value={data.probeFailed} icon={XCircle} tone={data.probeFailed ? 'warn' : 'good'} />
        <MetricTile label="Target 总数" value={data.targetTotal} icon={Target} />
        <MetricTile label="Target Down" value={data.targetDown} icon={Crosshair} tone={data.targetDown ? 'warn' : 'good'} />
      </section>
      <section className="work-grid two">
        <div className="panel">
          <div className="panel-head">
            <h2>Blackbox</h2>
            <StatusPill health={data.health} />
          </div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>名称</th>
                  <th>Job</th>
                  <th>结果</th>
                  <th>耗时</th>
                  <th>分组</th>
                </tr>
              </thead>
              <tbody>
                {probes.map((probe) => (
                  <tr key={probe.id}>
                    <td>
                      <strong>{probe.name ?? probe.target ?? probe.instance}</strong>
                      <small>{probe.instance}</small>
                    </td>
                    <td>{probe.job}</td>
                    <td><span className={probe.success ? 'text-ok' : 'text-bad'}>{probe.success ? 'up' : 'down'}</span></td>
                    <td>{probe.durationSec ? `${number(probe.durationSec * 1000, 0)} ms` : '—'}</td>
                    <td>{probe.group ?? probe.ifaceType ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
        <div className="panel">
          <div className="panel-head">
            <h2>Prometheus Targets</h2>
          </div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Job</th>
                  <th>状态</th>
                  <th>地址</th>
                  <th>错误</th>
                </tr>
              </thead>
              <tbody>
                {data.targets.map((target) => (
                  <tr key={target.id}>
                    <td>{target.job ?? '—'}</td>
                    <td><span className={target.health === 'up' ? 'text-ok' : 'text-bad'}>{target.health}</span></td>
                    <td><code>{target.scrapeUrl}</code></td>
                    <td>{target.lastError ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </section>
    </div>
  );
}
