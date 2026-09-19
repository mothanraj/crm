// Shared live lead updates: one SSE connection for the whole app (+ light poll fallback).
// Backend bumps a seq on inserts; callers refetch their lists (no PII in stream).

type Listener = () => void;

const listeners = new Set<Listener>();
let es: EventSource | null = null;
let pollTimer: ReturnType<typeof setInterval> | null = null;
let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
let started = false;

function baseUrl(): string {
  return (import.meta.env.VITE_API_URL ?? '/api').replace(/\/$/, '');
}

function notify() {
  listeners.forEach((fn) => {
    try { fn(); } catch { /* ignore listener errors */ }
  });
}

function closeEs() {
  try { es?.close(); } catch { /* noop */ }
  es = null;
}

function connect() {
  if (!started || listeners.size === 0) return;
  const token = localStorage.getItem('token') || '';
  if (!token) return;
  closeEs();
  try {
    es = new EventSource(`${baseUrl()}/stream/leads?token=${encodeURIComponent(token)}`);
    es.addEventListener('leads', () => notify());
    es.onerror = () => {
      // Stop browser auto-reconnect storm; we schedule a single retry.
      closeEs();
      if (reconnectTimer) clearTimeout(reconnectTimer);
      reconnectTimer = setTimeout(connect, 5000);
    };
  } catch {
    es = null;
  }
}

function ensureStarted() {
  if (started) return;
  started = true;
  connect();
  // Fallback poll every 60s only (SSE is primary)
  pollTimer = setInterval(() => notify(), 60000);
}

function maybeStop() {
  if (listeners.size > 0) return;
  started = false;
  closeEs();
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
  if (reconnectTimer) { clearTimeout(reconnectTimer); reconnectTimer = null; }
}

export function subscribeLeadUpdates(onUpdate: Listener): () => void {
  listeners.add(onUpdate);
  ensureStarted();
  return () => {
    listeners.delete(onUpdate);
    maybeStop();
  };
}
