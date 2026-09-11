import axios from 'axios';

export const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL ?? '/api',
  timeout: 15000,
});

api.interceptors.request.use((c) => {
  const t = localStorage.getItem('token');
  if (t) c.headers.Authorization = `Bearer ${t}`;
  return c;
});

function signOut() {
  localStorage.removeItem('token');
  localStorage.removeItem('refresh_token');
  localStorage.removeItem('role');
  if (!location.pathname.startsWith('/login')) {
    location.href = '/login?expired=1';
  }
}

api.interceptors.response.use(
  (r) => r,
  async (e) => {
    const cfg: any = e?.config || {};
    if (e?.response?.status === 401 && !cfg._retried && !cfg.url?.includes('/auth/')) {
      cfg._retried = true;
      const rt = localStorage.getItem('refresh_token');
      if (rt) {
        try {
          const { data } = await api.post('/auth/refresh', { refresh_token: rt });
          localStorage.setItem('token', data.access_token);
          if (data.refresh_token) localStorage.setItem('refresh_token', data.refresh_token);
          cfg.headers = cfg.headers || {};
          cfg.headers.Authorization = `Bearer ${data.access_token}`;
          return api(cfg);
        } catch {
          // fall through to sign out
        }
      }
      signOut();
    }
    return Promise.reject(e);
  },
);
