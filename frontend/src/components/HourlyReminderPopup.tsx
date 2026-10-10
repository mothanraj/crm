import { useCallback, useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../services/api';

const SNOOZE_KEY = 'crm:reminder-snooze-until';
const HOUR_MS = 60 * 60 * 1000;
const ROW_CAP = 20;

type ReminderRow = {
  id: string;
  enquiry_number: string;
  customer_name: string;
  reminder_date?: string | null;
};

/**
 * Hourly remainder popup for employees: reminder date + lead name + enq no.
 * Polls GET /dashboard/reminder-pulse every hour (today's dues only).
 * Repeats until the employee saves Work Progress (which flips reminder_done,
 * so the next poll returns empty). Silent when nothing is due.
 */
export function HourlyReminderPopup() {
  const [open, setOpen] = useState(false);
  const [rows, setRows] = useState<ReminderRow[]>([]);
  const [total, setTotal] = useState(0);
  const timer = useRef<number | null>(null);

  const fetchDue = useCallback(async (first = false) => {
    try {
      if (localStorage.getItem('role') !== 'EMPLOYEE') return;
      if (new URLSearchParams(window.location.search).get('popup') === 'test' && first) {
        // fall through — test mode forces a check even on first load
      } else if (first) {
        return; // first fire is after 1h, never immediately (login popup owns first paint)
      }
      const snoozedUntil = Number(localStorage.getItem(SNOOZE_KEY) || '0');
      if (Date.now() < snoozedUntil) return;
      const { data } = await api.get('/dashboard/reminder-pulse', { params: { limit: ROW_CAP } });
      const list: ReminderRow[] = Array.isArray(data?.rows) ? data.rows : [];
      const count = Number(data?.total ?? list.length ?? 0);
      if (!list.length || count === 0) {
        // Remainder closed (Work Progress saved) — stay quiet.
        setOpen(false);
        setRows([]);
        setTotal(0);
        return;
      }
      setRows(list.slice(0, ROW_CAP));
      setTotal(count);
      setOpen(true);
      // Nudge the bell badge to include the fresh hourly REMINDER_DUE rows.
      window.dispatchEvent(new Event('crm:reminders-due'));
    } catch {
      // stay silent — dashboard still loads
    }
  }, []);

  useEffect(() => {
    if (localStorage.getItem('role') !== 'EMPLOYEE') return;
    timer.current = window.setInterval(() => { void fetchDue(false); }, HOUR_MS);
    const onFocus = () => {
      const last = Number((window as any).__crmReminderLast || '0');
      if (Date.now() - last > HOUR_MS) {
        (window as any).__crmReminderLast = Date.now();
        void fetchDue(false);
      }
    };
    // Test hook: ?popup=test checks immediately.
    if (new URLSearchParams(window.location.search).get('popup') === 'test') {
      void fetchDue(true);
    }
    (window as any).__crmReminderLast = Date.now();
    window.addEventListener('focus', onFocus);
    document.addEventListener('visibilitychange', onFocus);
    return () => {
      if (timer.current) window.clearInterval(timer.current);
      window.removeEventListener('focus', onFocus);
      document.removeEventListener('visibilitychange', onFocus);
    };
  }, [fetchDue]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open ]);

  if (!open) return null;
  const snooze = () => {
    try { localStorage.setItem(SNOOZE_KEY, String(Date.now() + HOUR_MS)); } catch { /* private mode */ }
    setOpen(false);
  };
  return (
    <div className="fixed inset-0 z-50 bg-black/45 flex items-center justify-center p-3 sm:p-6 pb-[env(safe-area-inset-bottom)]" onClick={() => setOpen(false)}>
      <div
        role="dialog" aria-modal="true" aria-labelledby="hourly-reminder-title"
        className="card w-full max-w-lg max-h-[90dvh] overflow-y-auto p-4 sm:p-6"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <h2 id="hourly-reminder-title" className="text-lg sm:text-xl font-bold text-graphite-900">
              ⏰ Reminders due {total > 0 && <span className="ml-1 inline-flex items-center justify-center min-w-[1.75rem] h-7 px-2 rounded-full text-sm font-bold tabular-nums bg-[#E8890C] text-white">{total}</span>}
            </h2>
            <p className="text-sm text-graphite-500 mt-0.5">
              Today's follow-ups — repeats every hour until Work Progress is saved
            </p>
          </div>
          <button type="button" aria-label="Close reminders" onClick={() => setOpen(false)} className="btn-secondary !px-3 min-h-[44px] shrink-0">✕</button>
        </div>
        <div className="mt-3 overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs uppercase tracking-wide text-graphite-500">
                <th className="py-1.5 pr-2">Reminder date</th>
                <th className="py-1.5 pr-2">Lead name</th>
                <th className="py-1.5">Enq no</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((l) => (
                <tr key={l.id} className="border-t border-graphite-200">
                  <td className="py-2 pr-2 tabular-nums font-semibold text-[#E8890C] whitespace-nowrap">
                    {String(l.reminder_date || '').slice(0, 10) || '—'}
                  </td>
                  <td className="py-2 pr-2 font-medium text-graphite-900 break-words">{l.customer_name || '—'}</td>
                  <td className="py-2">
                    <Link to={`/leads/${l.id}`} onClick={() => setOpen(false)} className="font-semibold text-brand-700 hover:underline break-words">
                      {l.enquiry_number}
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {total > ROW_CAP && (
            <Link to="/leads" onClick={() => setOpen(false)} className="inline-block mt-1.5 text-xs font-semibold text-brand-700 hover:underline">
              +{total - ROW_CAP} more → View all my leads
            </Link>
          )}
        </div>
        <div className="mt-5 flex flex-col sm:flex-row gap-2">
          <Link to="/leads" onClick={() => setOpen(false)} className="btn-primary flex-1 text-center min-h-[44px] flex items-center justify-center">Open my leads →</Link>
          <button type="button" onClick={snooze} className="btn-secondary flex-1 min-h-[44px]">Snooze 1 hour</button>
        </div>
      </div>
    </div>
  );
}
