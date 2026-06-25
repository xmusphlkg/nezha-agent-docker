import { useQuery } from '@tanstack/react-query';
import { Database, HeartPulse, TimerReset } from 'lucide-react';
import { MetricTile } from '../components/MetricTile';
import { api } from '../lib/api';
import { dateTime, number } from '../lib/format';

export function DiagnosticsPage() {
  const { data } = useQuery({ queryKey: ['diagnostics'], queryFn: api.diagnostics });
  if (!data) return <div className="page loading">加载中</div>;

  return (
    <div className="page">
      <div className="page-head">
        <h1>诊断</h1>
      </div>
      <section className="metric-grid">
        <MetricTile label="采集轮次" value={String(data.collector.iteration ?? '—')} icon={HeartPulse} />
        <MetricTile label="采集耗时" value={data.collector.lastSnapshotMs ? `${number(data.collector.lastSnapshotMs as number, 0)} ms` : '—'} icon={TimerReset} />
        <MetricTile label="Redis 内存" value={String(data.cache.usedMemoryHuman ?? '—')} icon={Database} />
      </section>
      <section className="work-grid two">
        <div className="panel">
          <div className="panel-head">
            <h2>源系统</h2>
          </div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Source</th>
                  <th>OK</th>
                  <th>Latency</th>
                  <th>Last success</th>
                  <th>Error</th>
                </tr>
              </thead>
              <tbody>
                {data.sourceStatuses.map((source) => (
                  <tr key={source.source}>
                    <td>{source.source}</td>
                    <td><span className={source.ok ? 'text-ok' : 'text-bad'}>{source.ok ? 'ok' : 'bad'}</span></td>
                    <td>{source.latencyMs ? `${number(source.latencyMs, 0)} ms` : '—'}</td>
                    <td>{dateTime(source.lastSuccessAt)}</td>
                    <td>{source.lastError ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
        <div className="panel">
          <div className="panel-head">
            <h2>缓存与采集器</h2>
          </div>
          <pre className="json-block">{JSON.stringify({ cache: data.cache, collector: data.collector }, null, 2)}</pre>
        </div>
      </section>
    </div>
  );
}
