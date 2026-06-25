import type { Health } from '../types';

export function pct(value?: number | null): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  return `${value.toFixed(value >= 10 ? 0 : 1)}%`;
}

export function number(value?: number | null, digits = 0): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  return value.toLocaleString('zh-CN', { maximumFractionDigits: digits });
}

export function bps(value?: number | null): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  const units = ['bps', 'Kbps', 'Mbps', 'Gbps', 'Tbps'];
  let current = value;
  let unit = 0;
  while (current >= 1000 && unit < units.length - 1) {
    current /= 1000;
    unit += 1;
  }
  return `${current.toFixed(current >= 10 ? 0 : 1)} ${units[unit]}`;
}

export function bytes(value?: number | null): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  const units = ['B', 'KiB', 'MiB', 'GiB', 'TiB', 'PiB'];
  let current = value;
  let unit = 0;
  while (current >= 1024 && unit < units.length - 1) {
    current /= 1024;
    unit += 1;
  }
  return `${current.toFixed(current >= 10 ? 0 : 1)} ${units[unit]}`;
}

export function age(seconds?: number | null): string {
  if (seconds === null || seconds === undefined || Number.isNaN(seconds)) return '—';
  if (seconds < 60) return `${Math.floor(seconds)}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h`;
  return `${Math.floor(seconds / 86400)}d`;
}

export function dateTime(value?: string | null): string {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '—';
  return date.toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit'
  });
}

export function healthText(health: Health): string {
  return {
    ok: '正常',
    warning: '注意',
    critical: '严重',
    offline: '离线',
    stale: '过期',
    unknown: '未知'
  }[health];
}
