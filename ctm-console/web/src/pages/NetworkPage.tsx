import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { SearchInput } from '../components/SearchInput';
import { StatusPill } from '../components/StatusPill';
import { api } from '../lib/api';
import { bps, dateTime, number } from '../lib/format';

export function NetworkPage() {
  const [search, setSearch] = useState('');
  const { data = [] } = useQuery({ queryKey: ['network-devices'], queryFn: api.networkDevices });
  const rows = useMemo(() => {
    const query = search.trim().toLowerCase();
    return data.filter((device) => !query || `${device.host} ${device.id}`.toLowerCase().includes(query));
  }, [data, search]);

  return (
    <div className="page">
      <div className="page-head">
        <h1>网络与设备</h1>
        <div className="toolbar">
          <SearchInput value={search} onChange={setSearch} placeholder="搜索交换机、PDU、UPS" />
        </div>
      </div>
      <div className="panel">
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>设备</th>
                <th>状态</th>
                <th>吞吐</th>
                <th>Uptime</th>
                <th>问题</th>
                <th>更新</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((device) => (
                <tr key={device.id}>
                  <td>
                    <strong>{device.host}</strong>
                    <small>{device.id}</small>
                  </td>
                  <td>
                    <StatusPill health={device.health} />
                  </td>
                  <td>{bps(device.netBps)}</td>
                  <td>{device.uptimeSec ? `${number(device.uptimeSec / 86400, 1)} d` : '—'}</td>
                  <td>{device.problems.length}</td>
                  <td>{dateTime(device.updatedAt)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
