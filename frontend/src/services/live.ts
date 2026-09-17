// Live lead updates: SSE (/api/stream/leads) with polling fallback.
// Backend bumps a seq on every insert (Sheets push, Excel confirm/promote).
// Event carries ids only; callers refetch their list (no PII in stream).
export function subscribeLeadUpdates(onUpdate: () => void): () => void {
  const base = (import.meta.env.VITE_API_URL ?? '/api').replace(/\/$/, '');
  const token = localStorage.getItem('token') || '';
  let es: EventSource | null = null;
  let timer: ReturnType<typeof setInterval> | null = null;
  let stopped = false;
  try {
    es = new EventSource(`${base}/stream/leads?token=${encodeURIComponent(token)}`);
    es.addEventListener('leads', () => { if (!stopped) onUpdate(); });
    es.onerror = () => { /* fallback poll keeps us fresh; browser auto-reconnects */ };
  } catch { es = null; }
  timer = setInterval(() => { if (!stopped) onUpdate(); }, 30000);
  return () => {
    stopped = true;
    try { es?.close(); } catch { /* noop */ }
    if (timer) clearInterval(timer);
  };
}
