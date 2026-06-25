import type {
  CurrentUser,
  Diagnostics,
  DiscoveryRun,
  Machine,
  MachineDetail,
  MachineSeries,
  GrafanaIntegration,
  LanSummary,
  LoginRequest,
  NavCandidate,
  NavCandidatePatch,
  NavLink,
  NavLinkInput,
  NavLinkPatch,
  NavLinkPreview,
  NetworkDevice,
  Overview,
  Problem,
  PVESummary,
  ServicesSummary,
  TailnetSummary,
  UserCreate,
  UserUpdate,
  WazuhSummary
} from '../types';
import { appHref } from './paths';

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(appHref(path), {
    ...init,
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers ?? {})
    }
  });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      detail = body.detail ?? detail;
    } catch {
      detail = response.statusText;
    }
    throw new ApiError(detail, response.status);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return response.json() as Promise<T>;
}

function jsonRequest<T>(path: string, method: string, body?: unknown): Promise<T> {
  return request<T>(path, {
    method,
    body: body === undefined ? undefined : JSON.stringify(body)
  });
}

export const api = {
  login: (payload: LoginRequest) => jsonRequest<CurrentUser>('/api/auth/login', 'POST', payload),
  logout: () => jsonRequest<{ ok: boolean }>('/api/auth/logout', 'POST'),
  me: () => request<CurrentUser>('/api/auth/me'),
  users: () => request<CurrentUser[]>('/api/auth/users'),
  createUser: (payload: UserCreate) => jsonRequest<CurrentUser>('/api/auth/users', 'POST', payload),
  updateUser: (id: number, payload: UserUpdate) => jsonRequest<CurrentUser>(`/api/auth/users/${id}`, 'PATCH', payload),
  overview: () => request<Overview>('/api/overview'),
  machines: () => request<Machine[]>('/api/machines'),
  machine: (id: string) => request<MachineDetail>(`/api/machines/${encodeURIComponent(id)}`),
  machineSeries: (id: string, range: '1h' | '6h' | '24h') =>
    request<MachineSeries>(`/api/machines/${encodeURIComponent(id)}/series?range=${range}`),
  networkDevices: () => request<NetworkDevice[]>('/api/network/devices'),
  tailnet: () => request<TailnetSummary>('/api/tailnet'),
  services: () => request<ServicesSummary>('/api/services'),
  lan: () => request<LanSummary>('/api/lan'),
  pve: () => request<PVESummary>('/api/pve'),
  wazuh: () => request<WazuhSummary>('/api/wazuh'),
  grafana: () => request<GrafanaIntegration>('/api/grafana'),
  alerts: () => request<Problem[]>('/api/alerts'),
  diagnostics: () => request<Diagnostics>('/api/diagnostics'),
  navLinks: (includeDisabled = false) =>
    request<NavLink[]>(`/api/nav/links${includeDisabled ? '?includeDisabled=true' : ''}`),
  navLink: (id: number) => request<NavLink>(`/api/nav/links/${id}`),
  previewNavLink: (payload: { url: string }) => jsonRequest<NavLinkPreview>('/api/nav/links/preview', 'POST', payload),
  createNavLink: (payload: NavLinkInput) => jsonRequest<NavLink>('/api/nav/links', 'POST', payload),
  updateNavLink: (id: number, payload: NavLinkPatch) => jsonRequest<NavLink>(`/api/nav/links/${id}`, 'PATCH', payload),
  deleteNavLink: (id: number) => jsonRequest<{ ok: boolean }>(`/api/nav/links/${id}`, 'DELETE'),
  reorderNavLinks: (items: Array<{ id: number; sortOrder: number }>) =>
    jsonRequest<{ ok: boolean }>('/api/nav/links/reorder', 'PATCH', { items }),
  discoveryScan: (payload?: { cidrs?: string[]; ports?: number[] }) =>
    jsonRequest<DiscoveryRun>('/api/nav/discovery/scan', 'POST', payload ?? {}),
  discoveryRun: (id: number) => request<DiscoveryRun>(`/api/nav/discovery/runs/${id}`),
  navCandidates: (options?: { includeIgnored?: boolean; includeImported?: boolean }) => {
    const params = new URLSearchParams();
    if (options?.includeIgnored) params.set('includeIgnored', 'true');
    if (options?.includeImported) params.set('includeImported', 'true');
    const query = params.toString();
    return request<NavCandidate[]>(`/api/nav/discovery/candidates${query ? `?${query}` : ''}`);
  },
  importCandidate: (id: number) => jsonRequest<NavLink>(`/api/nav/discovery/candidates/${id}/import`, 'POST'),
  updateCandidate: (id: number, payload: NavCandidatePatch) =>
    jsonRequest<NavCandidate>(`/api/nav/discovery/candidates/${id}`, 'PATCH', payload)
};
