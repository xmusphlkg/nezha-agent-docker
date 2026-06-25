import { useQuery } from '@tanstack/react-query';
import { KeyRound, RadioTower, Route, Server, WifiOff } from 'lucide-react';
import { MetricTile } from '../components/MetricTile';
import { StatusPill } from '../components/StatusPill';
import { api } from '../lib/api';
import { age, number } from '../lib/format';

export function TailnetPage() {
  const { data } = useQuery({ queryKey: ['tailnet'], queryFn: api.tailnet });
  if (!data) return <div className="page loading">加载中</div>;

  return (
    <div className="page">
      <div className="page-head">
        <h1>Tailnet</h1>
        <StatusPill health={data.health} />
      </div>
      <section className="metric-grid">
        <MetricTile label="在线节点" value={`${data.onlineNodes}/${data.totalNodes}`} icon={RadioTower} tone={data.offlineNodes ? 'warn' : 'good'} />
        <MetricTile label="离线节点" value={data.offlineNodes} icon={WifiOff} tone={data.offlineNodes ? 'warn' : 'good'} />
        <MetricTile label="路由待批" value={number(data.routeDelta)} icon={Route} tone={data.routeDelta ? 'warn' : 'good'} />
        <MetricTile label="Key 将过期" value={data.expiringKeys} icon={KeyRound} tone={data.expiringKeys ? 'warn' : 'good'} />
        <MetricTile label="API/DB" value={`${data.apiUp ? 'up' : 'down'} / ${data.databaseOk ? 'ok' : 'bad'}`} icon={Server} tone={data.apiUp && data.databaseOk ? 'good' : 'bad'} />
      </section>
      <section className="work-grid two">
        <div className="panel">
          <div className="panel-head">
            <h2>节点</h2>
          </div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>名称</th>
                  <th>用户</th>
                  <th>在线</th>
                  <th>Last seen</th>
                  <th>路由</th>
                </tr>
              </thead>
              <tbody>
                {data.nodes.map((node) => (
                  <tr key={node.id}>
                    <td>
                      <strong>{node.name}</strong>
                      <small>{node.id}</small>
                    </td>
                    <td>{node.user ?? '—'}</td>
                    <td><span className={node.online ? 'text-ok' : 'text-bad'}>{node.online ? 'online' : 'offline'}</span></td>
                    <td>{age(node.lastSeenAgeSec)}</td>
                    <td>{number(node.approvedRoutes)} / {number(node.availableRoutes)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
        <div className="panel">
          <div className="panel-head">
            <h2>PreAuth Keys</h2>
          </div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>用户</th>
                  <th>复用</th>
                  <th>剩余</th>
                </tr>
              </thead>
              <tbody>
                {data.keys.map((key, index) => (
                  <tr key={`${key.user}-${index}`}>
                    <td>{key.user ?? '—'}</td>
                    <td>{key.reusable ?? '—'}</td>
                    <td>{age(key.expiresInSec)}</td>
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
