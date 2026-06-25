import { Activity, Check, Clock3, LogIn, LogOut, Navigation, Network, Settings } from 'lucide-react';
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { api } from '../lib/api';
import { useAuth } from '../lib/auth';
import { dateTime } from '../lib/format';
import type { Machine } from '../types';

function isOnline(machine: Machine) {
  if (machine.stale || machine.health === 'stale') return false;
  if (machine.agentUp === false || machine.health === 'offline') return false;
  if (machine.agentUp === true) return true;
  return machine.health !== 'unknown' && hasAnyMetric(machine);
}

function hasAnyMetric(machine: Machine) {
  return [machine.cpuPct, machine.memPct, machine.diskPct, machine.netBps, machine.maxTempC, machine.fanRpm].some(
    (value) => value !== null && value !== undefined && !Number.isNaN(value)
  );
}

export function Layout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const overview = useQuery({ queryKey: ['overview'], queryFn: api.overview });
  const online = overview.data?.machines.filter(isOnline).length ?? 0;
  const total = overview.data?.machines.length ?? 0;
  const isAdminRoute = location.pathname.startsWith('/nav/admin');
  const onLogout = async () => {
    await logout();
    navigate('/');
  };
  const onLogin = () => {
    navigate('/nav/admin');
  };

  return (
    <div className="monitor-shell">
      <header className="monitor-header">
        <div className="brand-mark" aria-label="CTM Monitor">
          <span className="brand-logo">C</span>
          <strong>CTM</strong>
          <i />
          <span>Monitor</span>
        </div>

        <nav className="main-nav" aria-label="主导航">
          <NavLink to="/">
            <Navigation size={15} />
            导航
          </NavLink>
          <NavLink to="/monitor">
            <Activity size={15} />
            监控
          </NavLink>
          <NavLink to="/lan">
            <Network size={15} />
            资产
          </NavLink>
          <NavLink to="/nav/admin">
            <Settings size={15} />
            管理
          </NavLink>
        </nav>

        <div className="header-status">
          <span className="header-sync">
            <Clock3 size={15} />
            {overview.data ? dateTime(overview.data.generatedAt) : '同步中'}
          </span>
          <span className="online-pill">
            <Check size={15} />
            {online}/{total} 在线
            <b />
          </span>
          {user ? (
            <button className="user-menu" type="button" onClick={onLogout} title="退出登录">
              <span>{user.displayName || user.username}</span>
              <LogOut size={15} />
            </button>
          ) : !isAdminRoute ? (
            <button className="user-menu" type="button" onClick={onLogin} title="管理登录">
              <span>管理登录</span>
              <LogIn size={15} />
            </button>
          ) : null}
        </div>
      </header>

      <main className="monitor-main">
        <Outlet />
      </main>
    </div>
  );
}
