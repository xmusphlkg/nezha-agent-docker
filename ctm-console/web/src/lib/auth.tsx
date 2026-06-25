import { createContext, useContext, type ReactNode } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { api, ApiError } from './api';
import type { CurrentUser } from '../types';

interface AuthContextValue {
  user: CurrentUser | null;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) {
    throw new Error('useAuth must be used inside AuthProvider');
  }
  return value;
}

interface AuthProviderProps {
  user: CurrentUser | null;
  children: ReactNode;
}

export function AuthProvider({ user, children }: AuthProviderProps) {
  const queryClient = useQueryClient();
  const logout = async () => {
    await api.logout().catch(() => undefined);
    queryClient.clear();
  };

  return <AuthContext.Provider value={{ user, logout }}>{children}</AuthContext.Provider>;
}

export function useSessionQuery() {
  return useQuery({
    queryKey: ['auth', 'me'],
    queryFn: api.me,
    refetchInterval: false,
    refetchOnReconnect: false,
    refetchOnWindowFocus: false,
    staleTime: Number.POSITIVE_INFINITY,
    retry: (failureCount, error) => {
      if (error instanceof ApiError && error.status === 401) return false;
      return failureCount < 1;
    }
  });
}
