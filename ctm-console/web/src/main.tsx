import React from 'react';
import { createRoot } from 'react-dom/client';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { BrowserRouter } from 'react-router-dom';
import App from './App';
import './styles.css';

const basename = import.meta.env.BASE_URL === '/' ? undefined : import.meta.env.BASE_URL.replace(/\/$/, '');

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchInterval: 10000,
      staleTime: 8000,
      retry: 1
    }
  }
});

createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter basename={basename}>
        <App />
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>
);
