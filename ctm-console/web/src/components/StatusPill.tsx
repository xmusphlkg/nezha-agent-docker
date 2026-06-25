import { AlertTriangle, CheckCircle2, Clock3, HelpCircle, RadioTower, XCircle } from 'lucide-react';
import type { Health } from '../types';
import { healthText } from '../lib/format';

const icons = {
  ok: CheckCircle2,
  warning: AlertTriangle,
  critical: XCircle,
  offline: RadioTower,
  stale: Clock3,
  unknown: HelpCircle
};

interface Props {
  health: Health;
  compact?: boolean;
}

export function StatusPill({ health, compact = false }: Props) {
  const Icon = icons[health];
  return (
    <span className={`status-pill ${health}`} title={healthText(health)}>
      <Icon size={14} />
      {!compact && <span>{healthText(health)}</span>}
    </span>
  );
}
