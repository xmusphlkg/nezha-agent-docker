import type { LucideIcon } from 'lucide-react';

interface Props {
  label: string;
  value: string | number;
  tone?: 'default' | 'good' | 'warn' | 'bad';
  icon: LucideIcon;
}

export function MetricTile({ label, value, tone = 'default', icon: Icon }: Props) {
  return (
    <section className={`metric-tile ${tone}`}>
      <div className="metric-icon">
        <Icon size={20} />
      </div>
      <div>
        <div className="metric-label">{label}</div>
        <div className="metric-value">{value}</div>
      </div>
    </section>
  );
}
