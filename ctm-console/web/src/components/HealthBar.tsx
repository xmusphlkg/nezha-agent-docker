interface Props {
  value?: number | null;
  warn?: number;
  bad?: number;
}

export function HealthBar({ value, warn = 85, bad = 95 }: Props) {
  const pct = value ?? 0;
  const tone = value === null || value === undefined ? 'empty' : pct >= bad ? 'bad' : pct >= warn ? 'warn' : 'ok';
  return (
    <div className="health-bar" title={value === null || value === undefined ? 'No data' : `${pct.toFixed(1)}%`}>
      <span className={tone} style={{ width: `${Math.min(Math.max(pct, 0), 100)}%` }} />
    </div>
  );
}
