import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { HealthBar } from '../components/HealthBar';
import { SearchInput } from '../components/SearchInput';
import { StatusPill } from '../components/StatusPill';
import { api } from '../lib/api';
import { bps, dateTime, number, pct } from '../lib/format';

export function MachinesPage() {
  const [search, setSearch] = useState('');
  const [sort, setSort] = useState<'health' | 'cpu' | 'mem' | 'disk' | 'temp' | 'name'>('health');
  const { data = [] } = useQuery({ queryKey: ['machines'], queryFn: api.machines });
  const filtered = useMemo(() => {
    const query = search.trim().toLowerCase();
    const rows = data.filter((machine) => {
      const text = `${machine.id} ${machine.sysHost ?? ''} ${machine.phyHost ?? ''}`.toLowerCase();
      return !query || text.includes(query);
    });
    return [...rows].sort((a, b) => {
      if (sort === 'name') return a.id.localeCompare(b.id);
      if (sort === 'cpu') return (b.cpuPct ?? -1) - (a.cpuPct ?? -1);
      if (sort === 'mem') return (b.memPct ?? -1) - (a.memPct ?? -1);
      if (sort === 'disk') return (b.diskPct ?? -1) - (a.diskPct ?? -1);
      if (sort === 'temp') return (b.maxTempC ?? -1) - (a.maxTempC ?? -1);
      const order = { critical: 0, offline: 1, warning: 2, stale: 3, unknown: 4, ok: 5 };
      return order[a.health] - order[b.health] || a.id.localeCompare(b.id);
    });
  }, [data, search, sort]);

  return (
    <div className="page">
      <div className="page-head">
        <h1>机器</h1>
        <div className="toolbar">
          <SearchInput value={search} onChange={setSearch} placeholder="搜索机器、sys、phy" />
          <select value={sort} onChange={(event) => setSort(event.target.value as typeof sort)}>
            <option value="health">按状态</option>
            <option value="cpu">按 CPU</option>
            <option value="mem">按内存</option>
            <option value="disk">按磁盘</option>
            <option value="temp">按温度</option>
            <option value="name">按名称</option>
          </select>
        </div>
      </div>
      <div className="panel">
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>机器</th>
                <th>通道</th>
                <th>状态</th>
                <th>CPU</th>
                <th>内存</th>
                <th>磁盘</th>
                <th>网络</th>
                <th>温度</th>
                <th>问题</th>
                <th>更新</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((machine) => (
                <tr key={machine.id}>
                  <td>
                    <Link to={`/machines/${machine.id}`} className="strong-link">
                      {machine.id}
                    </Link>
                    <small>{[machine.sysHost, machine.phyHost].filter(Boolean).join(' / ')}</small>
                  </td>
                  <td>{machine.mode}</td>
                  <td>
                    <StatusPill health={machine.health} />
                  </td>
                  <td>
                    <HealthBar value={machine.cpuPct} />
                    {pct(machine.cpuPct)}
                  </td>
                  <td>
                    <HealthBar value={machine.memPct} />
                    {pct(machine.memPct)}
                  </td>
                  <td>
                    <HealthBar value={machine.diskPct} />
                    {pct(machine.diskPct)}
                  </td>
                  <td>{bps(machine.netBps)}</td>
                  <td>{machine.maxTempC ? `${number(machine.maxTempC, 1)}°C` : '—'}</td>
                  <td>{machine.problems.length}</td>
                  <td>{dateTime(machine.updatedAt)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
