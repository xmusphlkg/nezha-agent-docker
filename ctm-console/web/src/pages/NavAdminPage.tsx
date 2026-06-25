import { FormEvent, useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Check, ExternalLink, EyeOff, Pencil, Plus, Radar, Save, Sparkles, Trash2, X } from 'lucide-react';
import { api } from '../lib/api';
import { appHref } from '../lib/paths';
import type { DiscoveryRun, NavCandidate, NavLink, NavLinkInput, NavLinkPatch, NavLinkPreview } from '../types';

const emptyForm: NavLinkInput = {
  title: '',
  url: '',
  category: '待分类',
  description: '',
  icon: '',
  tags: [],
  favorite: false,
  enabled: true
};

const iconOptions = ['console', 'dashboard', 'grafana', 'prometheus', 'zabbix', 'monitor', 'network', 'router', 'switch', 'chat', 'database', 'security', 'server', 'app', 'web'];

export function NavAdminPage() {
  const queryClient = useQueryClient();
  const links = useQuery({ queryKey: ['nav', 'links', 'admin'], queryFn: () => api.navLinks(true) });
  const candidates = useQuery({ queryKey: ['nav', 'candidates'], queryFn: () => api.navCandidates() });
  const [editing, setEditing] = useState<NavLink | null>(null);
  const [form, setForm] = useState<NavLinkInput>(emptyForm);
  const [tagText, setTagText] = useState('');
  const [run, setRun] = useState<DiscoveryRun | null>(null);
  const [scanCidrText, setScanCidrText] = useState('192.168.3.0/24');
  const [lastPreviewUrl, setLastPreviewUrl] = useState('');
  const [candidateQuery, setCandidateQuery] = useState('');
  const [candidateCategory, setCandidateCategory] = useState('全部');
  const [candidateStatus, setCandidateStatus] = useState('全部');

  const runQuery = useQuery({
    queryKey: ['nav', 'scan-run', run?.id],
    queryFn: () => api.discoveryRun(run!.id),
    enabled: Boolean(run?.id && run.status === 'running'),
    refetchInterval: 2500
  });

  useEffect(() => {
    if (runQuery.data) {
      setRun(runQuery.data);
      if (runQuery.data.status !== 'running') {
        queryClient.invalidateQueries({ queryKey: ['nav', 'candidates'] });
      }
    }
  }, [queryClient, runQuery.data]);

  const save = useMutation({
    mutationFn: async () => {
      const payload = { ...form, tags: parseTags(tagText) };
      if (editing) {
        const patch: NavLinkPatch = { ...payload, sortOrder: payload.sortOrder ?? undefined };
        return api.updateNavLink(editing.id, patch);
      }
      return api.createNavLink(payload);
    },
    onSuccess: () => {
      setEditing(null);
      setForm(emptyForm);
      setTagText('');
      queryClient.invalidateQueries({ queryKey: ['nav', 'links'] });
      queryClient.invalidateQueries({ queryKey: ['nav', 'candidates'] });
    }
  });
  const remove = useMutation({
    mutationFn: api.deleteNavLink,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['nav', 'links'] })
  });
  const toggle = useMutation({
    mutationFn: (item: NavLink) => api.updateNavLink(item.id, { enabled: !item.enabled }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['nav', 'links'] })
  });
  const scan = useMutation({
    mutationFn: () => {
      const cidrs = parseCidrs(scanCidrText);
      return api.discoveryScan(cidrs.length ? { cidrs } : undefined);
    },
    onSuccess: (data) => setRun(data)
  });
  const preview = useMutation({
    mutationFn: ({ url }: { url: string; force: boolean }) => api.previewNavLink({ url }),
    onSuccess: (data, variables) => applyPreview(data, variables.force)
  });
  const importCandidate = useMutation({
    mutationFn: api.importCandidate,
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ['nav', 'links'] });
      queryClient.invalidateQueries({ queryKey: ['nav', 'candidates'] });
    }
  });
  const ignoreCandidate = useMutation({
    mutationFn: (item: NavCandidate) => api.updateCandidate(item.id, { ignored: true }),
    onSettled: () => queryClient.invalidateQueries({ queryKey: ['nav', 'candidates'] })
  });

  const categories = useMemo(() => {
    const values = new Set((links.data ?? []).map((item) => item.category));
    ['监控', 'Grafana', '网络', '应用', '待分类'].forEach((item) => values.add(item));
    return Array.from(values).sort((a, b) => a.localeCompare(b, 'zh-CN'));
  }, [links.data]);

  const candidateModel = useMemo(() => {
    const items = candidates.data ?? [];
    const categories = ['全部', ...Array.from(new Set(items.map((item) => item.category))).sort((a, b) => a.localeCompare(b, 'zh-CN'))];
    const needle = candidateQuery.trim().toLowerCase();
    const filtered = items.filter((item) => {
      if (candidateCategory !== '全部' && item.category !== candidateCategory) return false;
      if (candidateStatus !== '全部') {
        const code = item.statusCode ?? 0;
        if (candidateStatus === '正常' && (code < 200 || code >= 400)) return false;
        if (candidateStatus === '异常' && (!item.statusCode || (code >= 200 && code < 400))) return false;
        if (candidateStatus === '未知' && item.statusCode) return false;
      }
      if (!needle) return true;
      return [
        item.title,
        item.url,
        item.host,
        item.category,
        item.suggestionReason ?? '',
        item.serverHeader ?? '',
        ...item.tags
      ].join(' ').toLowerCase().includes(needle);
    });
    return { categories, filtered, total: items.length };
  }, [candidateCategory, candidateQuery, candidateStatus, candidates.data]);

  const beginEdit = (item: NavLink) => {
    setEditing(item);
    setForm({
      title: item.title,
      url: item.url,
      category: item.category,
      description: item.description ?? '',
      icon: item.icon ?? '',
      tags: item.tags,
      favorite: item.favorite,
      enabled: item.enabled,
      sortOrder: item.sortOrder
    });
    setTagText(item.tags.join(', '));
    setLastPreviewUrl(item.url);
  };

  const applyPreview = (data: NavLinkPreview, force: boolean) => {
    const incomingTags = data.tags.slice(0, 12);
    setLastPreviewUrl(data.url);
    setForm((current) => ({
      ...current,
      url: data.url,
      title: force || !current.title.trim() ? data.title : current.title,
      category: force || !current.category.trim() || current.category === '待分类' ? data.category : current.category,
      description: force || !(current.description ?? '').trim() ? data.description ?? '' : current.description,
      icon: force || !(current.icon ?? '').trim() ? data.icon : current.icon,
      tags: force || !parseTags(tagText).length ? incomingTags : current.tags
    }));
    setTagText((current) => (force || !current.trim() ? incomingTags.join(', ') : current));
  };

  const identifyUrl = (force = false) => {
    const url = form.url.trim();
    if (!isPreviewableUrl(url) || preview.isPending) return;
    preview.mutate({ url, force });
  };

  const maybeAutoPreview = () => {
    const url = form.url.trim();
    if (editing || !isPreviewableUrl(url) || url === lastPreviewUrl || preview.isPending) return;
    if (!form.title.trim() || form.category === '待分类' || !tagText.trim()) {
      identifyUrl(false);
    }
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    save.mutate();
  };

  return (
    <div className="admin-page">
      <section className="admin-hero">
        <div>
          <h1>导航管理</h1>
          <p>维护正式入口，审核扫描候选项。</p>
        </div>
        <div className="scan-controls">
          <label>
            <span>扫描 IP 段</span>
            <input
              value={scanCidrText}
              placeholder="192.168.3.0/24, 192.168.10.0/24"
              onChange={(event) => setScanCidrText(event.target.value)}
            />
          </label>
          <button type="button" onClick={() => scan.mutate()} disabled={scan.isPending || run?.status === 'running' || !parseCidrs(scanCidrText).length}>
            <Radar size={17} />
            {run?.status === 'running' ? '扫描中' : '手动扫描'}
          </button>
        </div>
      </section>

      {run && (
        <section className={`scan-status ${run.status}`}>
          <strong>扫描任务 #{run.id}</strong>
          <span>
            {run.status === 'running'
              ? `正在扫描 ${run.cidrs.join(', ')}`
              : run.status === 'completed'
                ? `完成，发现 ${run.foundCount} 个入口，${run.importableCount} 个进入候选`
                : run.errorMessage || '扫描失败'}
          </span>
        </section>
      )}

      <section className="admin-layout">
        <form className="nav-edit-form" onSubmit={submit}>
          <div className="admin-section-title">
            <h2>{editing ? '编辑入口' : '新增入口'}</h2>
            {editing && (
              <button className="icon-button" type="button" onClick={() => { setEditing(null); setForm(emptyForm); setTagText(''); setLastPreviewUrl(''); }}>
                <X size={16} />
              </button>
            )}
          </div>
          <label>
            <span>名称</span>
            <input value={form.title} onChange={(event) => setForm({ ...form, title: event.target.value })} required />
          </label>
          <label>
            <span>地址</span>
            <div className="url-field">
              <input
                value={form.url}
                onBlur={maybeAutoPreview}
                onChange={(event) => setForm({ ...form, url: event.target.value })}
                required
              />
              <button className="url-preview-button" type="button" onClick={() => identifyUrl(true)} disabled={!isPreviewableUrl(form.url) || preview.isPending}>
                <Sparkles size={16} />
                {preview.isPending ? '识别中' : '识别'}
              </button>
            </div>
          </label>
          <label>
            <span>分类</span>
            <input list="nav-categories" value={form.category} onChange={(event) => setForm({ ...form, category: event.target.value })} required />
            <datalist id="nav-categories">
              {categories.map((item) => (
                <option key={item} value={item} />
              ))}
            </datalist>
          </label>
          <label>
            <span>图标</span>
            <input list="nav-icons" value={form.icon ?? ''} placeholder="自动识别" onChange={(event) => setForm({ ...form, icon: event.target.value })} />
            <datalist id="nav-icons">
              {iconOptions.map((item) => (
                <option key={item} value={item} />
              ))}
            </datalist>
          </label>
          <label>
            <span>描述</span>
            <textarea value={form.description ?? ''} onChange={(event) => setForm({ ...form, description: event.target.value })} />
          </label>
          <label>
            <span>标签</span>
            <input value={tagText} placeholder="grafana, dashboard" onChange={(event) => setTagText(event.target.value)} />
          </label>
          <div className="form-switches">
            <label>
              <input type="checkbox" checked={form.favorite} onChange={(event) => setForm({ ...form, favorite: event.target.checked })} />
              常用
            </label>
            <label>
              <input type="checkbox" checked={form.enabled} onChange={(event) => setForm({ ...form, enabled: event.target.checked })} />
              启用
            </label>
          </div>
          {preview.error instanceof Error && <div className="form-error">{preview.error.message}</div>}
          {save.error instanceof Error && <div className="form-error">{save.error.message}</div>}
          <button type="submit" disabled={save.isPending}>
            {editing ? <Save size={17} /> : <Plus size={17} />}
            {editing ? '保存修改' : '添加入口'}
          </button>
        </form>

        <section className="admin-list">
          <div className="admin-section-title">
            <h2>正式入口</h2>
            <span>{links.data?.length ?? 0}</span>
          </div>
          <div className="admin-table">
            {(links.data ?? []).map((item) => (
              <div className={item.enabled ? 'admin-row' : 'admin-row disabled'} key={item.id}>
                <div>
                  <strong>{item.title}</strong>
                  <span>{item.category} · {item.url}</span>
                </div>
                <div className="admin-row-actions">
                  <a className="icon-button" href={appHref(item.url)} target={item.url.startsWith('/') ? undefined : '_blank'} rel="noreferrer">
                    <ExternalLink size={16} />
                  </a>
                  <button className="icon-button" type="button" onClick={() => beginEdit(item)}>
                    <Pencil size={16} />
                  </button>
                  <button className="icon-button" type="button" onClick={() => toggle.mutate(item)}>
                    {item.enabled ? <EyeOff size={16} /> : <Check size={16} />}
                  </button>
                  <button className="icon-button danger" type="button" onClick={() => remove.mutate(item.id)}>
                    <Trash2 size={16} />
                  </button>
                </div>
              </div>
            ))}
            {links.isLoading && <div className="nav-empty">加载正式入口</div>}
          </div>
        </section>
      </section>

      <section className="candidate-section">
        <div className="admin-section-title">
          <h2>候选入口</h2>
          <span>{candidateModel.filtered.length}/{candidateModel.total}</span>
        </div>
        <div className="candidate-toolbar">
          <input value={candidateQuery} placeholder="搜索候选入口" onChange={(event) => setCandidateQuery(event.target.value)} />
          <select value={candidateCategory} onChange={(event) => setCandidateCategory(event.target.value)}>
            {candidateModel.categories.map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>
          <select value={candidateStatus} onChange={(event) => setCandidateStatus(event.target.value)}>
            {['全部', '正常', '异常', '未知'].map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>
        </div>
        <div className="candidate-grid">
          {candidateModel.filtered.map((item) => (
            <article className="candidate-card" key={item.id}>
              <div>
                <strong>{item.title}</strong>
                <span>{item.url}</span>
              </div>
              <p>{item.suggestionReason || `${item.host}:${item.port}`}</p>
              <div className="candidate-meta">
                <span>{item.category}</span>
                {item.statusCode && <span>HTTP {item.statusCode}</span>}
                {item.serverHeader && <span>{item.serverHeader}</span>}
              </div>
              <div className="candidate-actions">
                <a href={item.url} target="_blank" rel="noreferrer">
                  <ExternalLink size={16} />
                  打开
                </a>
                <button type="button" onClick={() => importCandidate.mutate(item.id)} disabled={importCandidate.isPending || ignoreCandidate.isPending}>
                  <Check size={16} />
                  导入
                </button>
                <button type="button" onClick={() => ignoreCandidate.mutate(item)} disabled={importCandidate.isPending || ignoreCandidate.isPending}>
                  <EyeOff size={16} />
                  忽略
                </button>
              </div>
            </article>
          ))}
          {!candidates.isLoading && !candidateModel.filtered.length && <div className="nav-empty">暂无匹配的候选项</div>}
        </div>
      </section>
    </div>
  );
}

function parseTags(value: string) {
  return Array.from(
    new Set(
      value
        .split(/[,\s]+/)
        .map((item) => item.trim())
        .filter(Boolean)
    )
  ).slice(0, 12);
}

function parseCidrs(value: string) {
  return Array.from(
    new Set(
      value
        .split(/[,\s]+/)
        .map((item) => item.trim())
        .filter(Boolean)
    )
  );
}

function isPreviewableUrl(value: string) {
  const url = value.trim();
  return url.startsWith('/') || /^https?:\/\//i.test(url);
}
