import { Navigate, Route, Routes } from 'react-router-dom';
import type { ReactNode } from 'react';
import { Layout } from './components/Layout';
import { AuthProvider, useSessionQuery } from './lib/auth';
import { LoginPage } from './pages/LoginPage';
import { NavigationPage } from './pages/NavigationPage';
import { NavAdminPage } from './pages/NavAdminPage';
import { OverviewPage } from './pages/OverviewPage';
import { LanPage } from './pages/LanPage';
import { MachineDetailPage } from './pages/MachineDetailPage';
import type { CurrentUser } from './types';

export default function App() {
  const session = useSessionQuery();
  const user = session.data ?? null;

  return (
    <AuthProvider user={user}>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/" element={<NavigationPage />} />
          <Route
            path="/nav/admin"
            element={
              <AdminOnly user={user} loading={session.isLoading}>
                <NavAdminPage />
              </AdminOnly>
            }
          />
          <Route path="/monitor" element={<OverviewPage />} />
          <Route path="/hosts" element={<OverviewPage />} />
          <Route path="/machines" element={<Navigate to="/monitor" replace />} />
          <Route path="/machines/:id" element={<MachineDetailPage />} />
          <Route path="/pve" element={<OverviewPage />} />
          <Route path="/security" element={<OverviewPage />} />
          <Route path="/lan" element={<LanPage />} />
          <Route path="/network" element={<Navigate to="/lan" replace />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </AuthProvider>
  );
}

function AdminOnly({ user, loading, children }: { user: CurrentUser | null; loading: boolean; children: ReactNode }) {
  if (loading) return <div className="loading-screen">检查管理登录状态</div>;
  if (!user) return <LoginPage embedded />;
  return children;
}
