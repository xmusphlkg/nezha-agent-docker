import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { SearchInput } from '../components/SearchInput';
import { api } from '../lib/api';
import { age } from '../lib/format';

export function AlertsPage() {
  const [search, setSearch] = useState('');
  const { data = [] } = useQuery({ queryKey: ['alerts'], queryFn: api.alerts });
  const rows = useMemo(() => {
    const query = search.trim().toLowerCase();
    return data.filter((problem) => !query || `${problem.name} ${problem.host} ${problem.source} ${problem.severity}`.toLowerCase().includes(query));
  }, [data, search]);

  return (
    <div className="page">
      <div className="page-head">
        <h1>告警</h1>
        <div className="toolbar">
          <SearchInput value={search} onChange={setSearch} placeholder="搜索告警、主机、来源" />
        </div>
      </div>
      <div className="panel">
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>名称</th>
                <th>主机</th>
                <th>来源</th>
                <th>级别</th>
                <th>持续</th>
                <th>确认</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((problem) => (
                <tr key={`${problem.source}-${problem.eventId}-${problem.name}`}>
                  <td><strong>{problem.name}</strong></td>
                  <td>{problem.host || '—'}</td>
                  <td>{problem.source}</td>
                  <td><span className={`severity ${problem.severity}`}>{problem.severity}</span></td>
                  <td>{age(problem.ageSec)}</td>
                  <td>{problem.acknowledged ? 'yes' : 'no'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
