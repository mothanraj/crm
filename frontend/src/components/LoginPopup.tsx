import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../services/api';

const POP_FLAG = 'crm:login-popup';
const QUEUE_CAP = 500;
const ROW_CAP = 8;

type Bucket = 'overdue' | 'reminders' | 'new';

function todayISO(): string {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Kolkata', year: 'numeric', month: '2-digit', day: '2-digit',
  }).formatToParts(new Date());
  const get = (t: string) => parts.find((p) => p.type === t)?.value || '';
  return `${get('year')}-${get('month')}-${get('day')}`;
}

function latestRemarks(l: any): string {
  const hist = Array.isArray(l.work_history) ? l.work_history : [];
  if (hist.length) return String(hist[hist.length - 1]?.remarks || '').trim();
  return String(l.employee_remarks || '').trim();
}

function greeting(): string {
  const h = Number(new Intl.DateTimeFormat('en-IN', { timeZone: 'Asia/Kolkata', hour: 'numeric', hour12: false }).format(new Date()));
  if (h < 12) return 'Good morning';
  if (h < 17) return 'Good afternoon';
  return 'Good evening';
}

const SECTIONS: Array<{ key: Bucket; title: string; hint: string; bar: string; badge: string }> = [
  { key: 'overdue', title: 'Overdue follow-ups', hint: 'Act now', bar: 'border-[#E03131]', badge: 'bg-[#E03131] text-white' },
  { key: 'reminders', title: 'Reminders due', hint: 'Due today or earlier', bar: 'border-[#E8890C]', badge: 'bg-[#E8890C] text-white' },
  { key: 'new', title: 'Newly assigned leads', hint: 'Speak to customer', bar: 'border-[#2F9E44]', badge: 'bg-[#2F9E44] text-white' },
];

/**
 * One-time login popup for employees: overdue (red), reminders due (amber),
 * newly assigned (green) — priority ordered. Silent when there is nothing to show.
 */
export function EmployeeLoginPopup() {
  const [open, setOpen] = useState(false);
  const [groups, setGroups] = useState<Record<Bucket, any[]>>({ overdue: [], reminders: [], new: [] });
  const [totals, setTotals] = useState<Record<Bucket, number>>({ overdue: 0, reminders: 0, new: 0 });
  const [userName, setUserName] = useState('');

  useEffect(() => {
    if (localStorage.getItem('role') !== 'EMPLOYEE') return;
    let armed = false;
    let testMode = false;
    try {
      armed = sessionStorage.getItem(POP_FLAG) === '1';
      testMode = new URLSearchParams(window.location.search).get('popup') === 'test';
    } catch { armed = false; }
    if (!armed && !testMode) return;
    // NOTE: the flag is consumed only AFTER the fetch resolves (see below), so
    // React StrictMode's double-mount in dev cannot swallow this one-shot popup.
    setUserName(localStorage.getItem('user_name') || 'there');
    let cancelled = false;
    const consume = () => { try { sessionStorage.removeItem(POP_FLAG); } catch { /* private mode */ } };
    api.get('/leads', { params: { page: 1, size: 1 } })
      .then((r) => {
        const full = Math.min(Math.max(r.data.total ?? 0, 1), QUEUE_CAP);
        return api.get('/leads', { params: { page: 1, size: full } });
      })
      .then((r) => {
        if (cancelled) return;
        consume();
        const items: any[] = r.data.items || [];
        const today = todayISO();
        const live = items.filter((l) => l.sla_state !== 'COMPLETED');
        const overdue = live
          .filter((l) => l.sla_state === 'OVERDUE')
          .sort((a, b) => String(a.sla_deadline || 'zzz').localeCompare(String(b.sla_deadline || 'zzz')));
        const reminders = live
          .filter((l) => {
            const d = String(l.reminder_date || '').slice(0, 10);
            return !!d && d <= today && !l.reminder_done;
          })
          .sort((a, b) => String(a.reminder_date || '').localeCompare(String(b.reminder_date || '')));
        const fresh = live
          .filter((l) => !l.first_contact_at)
          .sort((a, b) => String(b.enquiry_date || '').localeCompare(String(a.enquiry_date || '')));
        if (overdue.length + reminders.length + fresh.length === 0) return;
        setGroups({ overdue, reminders, new: fresh });
        setTotals({ overdue: overdue.length, reminders: reminders.length, new: fresh.length });
        setOpen(true);
      })
      .catch(() => { consume(); /* stay silent on failure — dashboard still loads */ });
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open ]);

  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 bg-black/45 flex items-center justify-center p-3 sm:p-6 pb-[env(safe-area-inset-bottom)]" onClick={() => setOpen(false)}>
      <div
        role="dialog" aria-modal="true" aria-labelledby="login-popup-title"
        className="card w-full max-w-lg max-h-[90dvh] overflow-y-auto p-4 sm:p-6"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <h2 id="login-popup-title" className="text-lg sm:text-xl font-bold text-graphite-900 break-words">
              {greeting()}, {userName}
            </h2>
            <p className="text-sm text-graphite-500 mt-0.5">
              {new Date().toLocaleDateString('en-IN', { weekday: 'long', day: 'numeric', month: 'short' })} · here's what needs you today
            </p>
          </div>
          <button type="button" aria-label="Close notifications" onClick={() => setOpen(false)} className="btn-secondary !px-3 min-h-[44px] shrink-0">✕</button>
        </div>
        <div className="mt-4 space-y-4">
          {SECTIONS.map((s) => {
            const rows = groups[s.key] || [];
            if (!rows.length) return null;
            return (
              <section key={s.key} aria-label={s.title}>
                <div className="flex items-center gap-2">
                  <span className={`inline-flex items-center justify-center min-w-[1.75rem] h-7 px-2 rounded-full text-sm font-bold tabular-nums ${s.badge}`}>{totals[s.key]}</span>
                  <h3 className="text-sm font-bold uppercase tracking-wide text-graphite-700">{s.title}</h3>
                  <span className="text-xs text-graphite-400">· {s.hint}</span>
                </div>
                <ul className={`mt-2 space-y-2 border-l-4 ${s.bar} pl-2`}>
                  {rows.slice(0, ROW_CAP).map((l: any) => (
                    <li key={`${s.key}-${l.id}`} className="rounded-lg border border-graphite-200 bg-white px-3 py-2 shadow-sm">
                      <div className="flex items-center justify-between gap-2">
                        <Link to={`/leads/${l.id}`} onClick={() => setOpen(false)} className="font-semibold text-brand-700 hover:underline text-sm break-words min-w-0">
                          {l.enquiry_number}
                        </Link>
                        {s.key === 'reminders' && (
                          <span className="text-[11px] font-semibold tabular-nums text-graphite-600 bg-graphite-100 rounded px-1.5 py-0.5 shrink-0">
                            {String(l.reminder_date || '').slice(0, 10)}
                          </span>
                        )}
                      </div>
                      <div className="text-sm font-medium text-graphite-900 break-words mt-0.5">{l.customer_name || '—'}</div>
                      {latestRemarks(l) && (
                        <div className="text-xs text-graphite-500 break-words mt-0.5 [display:-webkit-box] [-webkit-line-clamp:2] [-webkit-box-orient:vertical] overflow-hidden">
                          {latestRemarks(l)}
                        </div>
                      )}
                    </li>
                  ))}
                </ul>
                {totals[s.key] > ROW_CAP && (
                  <Link to="/leads" onClick={() => setOpen(false)} className="inline-block mt-1.5 text-xs font-semibold text-brand-700 hover:underline">
                    +{totals[s.key] - ROW_CAP} more → View all my leads
                  </Link>
                )}
              </section>
            );
          })}
        </div>
        <div className="mt-5 flex flex-col sm:flex-row gap-2">
          <Link to="/leads" onClick={() => setOpen(false)} className="btn-primary flex-1 text-center min-h-[44px] flex items-center justify-center">View all my leads →</Link>
          <button type="button" onClick={() => setOpen(false)} className="btn-secondary flex-1 min-h-[44px]">Got it</button>
        </div>
      </div>
    </div>
  );
}
