import { FormEvent, useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { LockKeyhole, LogIn } from 'lucide-react';
import { api, ApiError } from '../lib/api';

export function LoginPage({ embedded = false }: { embedded?: boolean }) {
  const queryClient = useQueryClient();
  const [username, setUsername] = useState('admin');
  const [password, setPassword] = useState('');
  const login = useMutation({
    mutationFn: api.login,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['auth', 'me'] });
    }
  });

  const submit = (event: FormEvent) => {
    event.preventDefault();
    login.mutate({ username, password });
  };

  const error = login.error instanceof ApiError ? login.error.message : login.error instanceof Error ? login.error.message : '';

  return (
    <main className={embedded ? 'login-page embedded' : 'login-page'}>
      <section className="login-panel">
        <div className="login-brand">
          <span className="brand-logo">C</span>
          <div>
            <strong>CTM Console</strong>
            <span>统一导航与监控入口</span>
          </div>
        </div>

        <form className="login-form" onSubmit={submit}>
          <label>
            <span>用户名</span>
            <input value={username} autoComplete="username" onChange={(event) => setUsername(event.target.value)} />
          </label>
          <label>
            <span>密码</span>
            <input
              value={password}
              type="password"
              autoComplete="current-password"
              onChange={(event) => setPassword(event.target.value)}
            />
          </label>
          {error && <div className="login-error">{error}</div>}
          <button type="submit" disabled={login.isPending || !username || !password}>
            {login.isPending ? <LockKeyhole size={18} /> : <LogIn size={18} />}
            {login.isPending ? '登录中' : '登录'}
          </button>
        </form>
      </section>
    </main>
  );
}
