import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  Activity,
  BarChart3,
  Database,
  ExternalLink,
  Filter,
  Gauge,
  Globe2,
  Heart,
  LayoutDashboard,
  MessageSquare,
  MonitorCog,
  Network,
  Router,
  Search,
  Server,
  ShieldCheck,
  type LucideIcon
} from 'lucide-react';
import { api } from '../lib/api';
import { appHref } from '../lib/paths';
import type { NavLink } from '../types';

const iconComponents = {
  app: Globe2,
  chat: MessageSquare,
  console: MonitorCog,
  dashboard: LayoutDashboard,
  database: Database,
  grafana: Gauge,
  monitor: Activity,
  network: Network,
  prometheus: BarChart3,
  router: Router,
  security: ShieldCheck,
  server: Server,
  switch: Network,
  web: Globe2,
  zabbix: MonitorCog
} satisfies Record<string, LucideIcon>;

type NavIconName = keyof typeof iconComponents;

const iconTones: Record<NavIconName, string> = {
  app: 'blue',
  chat: 'green',
  console: 'dark',
  dashboard: 'violet',
  database: 'amber',
  grafana: 'orange',
  monitor: 'blue',
  network: 'teal',
  prometheus: 'red',
  router: 'teal',
  security: 'green',
  server: 'slate',
  switch: 'teal',
  web: 'slate',
  zabbix: 'red'
};

export function NavigationPage() {
  const links = useQuery({ queryKey: ['nav', 'links'], queryFn: () => api.navLinks(false) });
  const [query, setQuery] = useState('');
  const [category, setCategory] = useState('全部');
  const [tag, setTag] = useState('全部');

  const model = useMemo(() => {
    const items = links.data ?? [];
    const categories = ['全部', ...Array.from(new Set(items.map((item) => item.category))).sort((a, b) => a.localeCompare(b, 'zh-CN'))];
    const tags = ['全部', ...Array.from(new Set(items.flatMap((item) => item.tags))).sort((a, b) => a.localeCompare(b, 'zh-CN'))];
    const needle = query.trim().toLowerCase();
    const filtered = items.filter((item) => {
      if (category !== '全部' && item.category !== category) return false;
      if (tag !== '全部' && !item.tags.includes(tag)) return false;
      if (!needle) return true;
      return [item.title, item.url, item.category, item.description ?? '', ...item.tags].join(' ').toLowerCase().includes(needle);
    });
    return { categories, tags, filtered };
  }, [links.data, query, category, tag]);

  if (links.isLoading) return <div className="loading-screen">加载导航</div>;
  if (links.isError) {
    return (
      <div className="loading-screen error">
        <strong>无法加载导航</strong>
        <span>{links.error instanceof Error ? links.error.message : '请检查 API 服务状态'}</span>
      </div>
    );
  }

  return (
    <div className="nav-page">
      <section className="nav-hero">
        <div>
          <h1>统一导航</h1>
          <p>监控、面板、应用和设备管理入口集中在这里。</p>
        </div>
        <a className="nav-admin-link" href={appHref('/nav/admin')}>
          <ShieldCheck size={17} />
          管理入口
        </a>
      </section>

      <section className="nav-controls">
        <label className="nav-search">
          <Search size={18} />
          <input value={query} placeholder="搜索名称、地址、标签" onChange={(event) => setQuery(event.target.value)} />
        </label>
        <label className="nav-filter">
          <Filter size={17} />
          <select value={category} onChange={(event) => setCategory(event.target.value)}>
            {model.categories.map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>
        </label>
        <label className="nav-filter">
          <Filter size={17} />
          <select value={tag} onChange={(event) => setTag(event.target.value)}>
            {model.tags.map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>
        </label>
      </section>

      <section className="nav-section">
        <div className="nav-section-heading">
          <h2>常用入口</h2>
          <span>{model.filtered.filter((item) => item.favorite).length}</span>
        </div>
        <div className="nav-link-grid">
          {model.filtered.filter((item) => item.favorite).map((item) => (
            <NavCard key={item.id} item={item} />
          ))}
        </div>
      </section>

      <section className="nav-section">
        <div className="nav-section-heading">
          <h2>全部入口</h2>
          <span>{model.filtered.length}</span>
        </div>
        <div className="nav-link-grid">
          {model.filtered.map((item) => (
            <NavCard key={item.id} item={item} />
          ))}
          {!model.filtered.length && <div className="nav-empty">没有匹配的导航入口</div>}
        </div>
      </section>
    </div>
  );
}

function NavCard({ item }: { item: NavLink }) {
  const hostname = displayHost(item.url);
  const iconName = iconNameForLink(item);
  const Icon = iconComponents[iconName];
  return (
    <a className={`nav-card ${item.status}`} href={appHref(item.url)} target={item.url.startsWith('/') ? undefined : '_blank'} rel="noreferrer">
      <div className="nav-card-top">
        <span className={`nav-card-icon tone-${iconTones[iconName]}`}>
          <Icon size={18} strokeWidth={2.25} />
        </span>
        <span className="nav-card-status">{statusText(item)}</span>
      </div>
      <strong>{item.title}</strong>
      <p>{item.description || hostname}</p>
      <div className="nav-card-meta">
        <span>{item.category}</span>
        <span>{hostname}</span>
      </div>
      <div className="nav-card-tags">
        {item.favorite && (
          <span>
            <Heart size={12} />
            常用
          </span>
        )}
        {item.tags.slice(0, 4).map((tag) => (
          <span key={tag}>{tag}</span>
        ))}
      </div>
      <ExternalLink className="nav-card-open" size={16} />
    </a>
  );
}

function iconNameForLink(item: NavLink): NavIconName {
  const explicit = (item.icon ?? '').trim().toLowerCase();
  if (isKnownIcon(explicit)) return explicit;
  const text = [item.title, item.url, item.category, item.description ?? '', ...item.tags].join(' ').toLowerCase();
  if (item.url.startsWith('/')) return 'console';
  if (text.includes('grafana')) return text.includes('/d/') || item.tags.includes('dashboard') ? 'dashboard' : 'grafana';
  if (text.includes('prometheus') || text.includes(':9090')) return 'prometheus';
  if (text.includes('zabbix') || text.includes(':8080')) return 'zabbix';
  if (text.includes('wazuh') || text.includes('security') || text.includes('安全')) return 'security';
  if (text.includes('nextchat') || text.includes('chat') || text.includes('聊天')) return 'chat';
  if (text.includes('router') || text.includes('路由') || text.includes('zte')) return 'router';
  if (text.includes('switch') || text.includes('交换机')) return 'switch';
  if (text.includes('mysql') || text.includes('redis') || text.includes('数据库')) return 'database';
  if (text.includes('pve') || text.includes('proxmox') || text.includes('虚拟')) return 'server';
  if (item.category === '监控') return 'monitor';
  if (item.category === '网络') return 'network';
  if (item.category === '应用') return 'app';
  return 'web';
}

function isKnownIcon(value: string): value is NavIconName {
  return Object.prototype.hasOwnProperty.call(iconComponents, value);
}

function displayHost(url: string) {
  if (url.startsWith('/')) return 'CTM Console';
  try {
    const parsed = new URL(url);
    return parsed.port ? `${parsed.hostname}:${parsed.port}` : parsed.hostname;
  } catch {
    return url;
  }
}

function statusText(item: NavLink) {
  if (item.status === 'ok') return item.statusCode ? `HTTP ${item.statusCode}` : '正常';
  if (item.status === 'down') return '不可达';
  if (item.status === 'warning') return '需关注';
  return item.enabled ? '未探测' : '停用';
}
