import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  PieChart, Pie, Cell, BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid,
  ResponsiveContainer, Legend,
} from 'recharts';
import { api } from '../services/api';
import { Card, EmptyState, PageHeader, SlaBadge, Spinner, StatusBadge } from '../components/ui';

const COLORS = ['#65A30D', '#6E6E6E', '#B5CC18', '#3F6212', '#A3A380', '#2F9E44', '#E8890C', '#84cc16', '#a3a380', '#4d7c0f', '#14b8a6', '#1971C2'];

function fmtDT(v: any, len = 16) {
  if (!v) return '—';
  return String(v).slice(0, len).replace('T', ' ');
}

async function downloadReport(path: string, filename: string, params?: Record<string, string>) {
  const res = await api.get(path, { responseType: 'blob', params });
  const ctype = res.headers?.['content-type'] || '';
  if (ctype.includes('application/json')) {
    const text = await (res.data as Blob).text();
    let detail = 'Download failed';
    try { detail = JSON.parse(text)?.detail || detail; } catch { /* keep default */ }
    throw new Error(detail);
  }
  const url = URL.createObjectURL(res.data);
  try {
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
  } finally {
    setTimeout(() => URL.revokeObjectURL(url), 2000);
  }
}

/* ================= LOGIN ================= */
export function Login() {
  const devDefault = import.meta.env.DEV ? 'admin@crm.local' : '';
  const [email, setEmail] = useState(devDefault);
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const expired = new URLSearchParams(location.search).get('expired') === '1';
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true); setError('');
    try {
      const { data } = await api.post('/auth/login', { email, password });
      localStorage.setItem('token', data.access_token);
      if (data.refresh_token) localStorage.setItem('refresh_token', data.refresh_token);
      localStorage.setItem('role', data.user.role);
      location.href = '/dashboard';
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Cannot reach the server. Is the backend running on port 8000?');
    } finally { setBusy(false); }
  };
  return (
    <div className="min-h-screen grid md:grid-cols-2">
      <div className="hidden md:flex flex-col justify-between text-white p-12 relative overflow-hidden bg-gradient-to-br from-graphite-700 via-graphite-800 to-graphite-950">
        <div className="absolute -top-24 -right-24 w-96 h-96 rounded-full bg-brand-400/20 blur-3xl pointer-events-none" />
        <div className="flex items-center gap-2.5 relative">
          <div className="w-10 h-10 rounded-xl bg-brand-400 flex items-center justify-center text-signalink font-bold">E★</div>
          <div className="font-bold text-lg">E-Star CRM</div>
        </div>
        <div className="relative">
          <h1 className="text-4xl font-bold leading-tight">Every lead,<br />followed up.</h1>
          <p className="text-graphite-200 mt-4 max-w-sm">Live funnel dashboard, 3-day contact SLA, automatic assignment and full activity history — replacing the Excel tracker.</p>
          <div className="grid grid-cols-3 gap-4 mt-8 text-sm">
            {['Live funnel', 'SLA alerts', 'Reports'].map((t, i) => (
              <div key={t} className="bg-white/10 backdrop-blur rounded-xl p-4 border border-white/10">
                <div className="text-2xl font-bold text-brand-400">{['629', '72h', '4'][i]}</div>
                <div className="text-graphite-100 mt-1">{t}</div>
              </div>
            ))}
          </div>
        </div>
        <div className="text-xs text-graphite-300 relative">Lead Management CRM · v0.1</div>
      </div>
      <div className="flex items-center justify-center p-8 bg-graphite-100">
        <form onSubmit={submit} className="card p-8 w-full max-w-sm space-y-4">
          <div>
            <h2 className="text-xl font-bold text-graphite-900">Welcome back</h2>
            <p className="text-sm text-graphite-500">Sign in to your CRM account</p>
          </div>
          {error && <div className="bg-red-50 border border-red-200 text-red-700 text-sm rounded-lg px-3 py-2">{error}</div>}
          {!error && expired && <div className="bg-amber-50 border border-amber-200 text-amber-800 text-sm rounded-lg px-3 py-2">Session expired — please sign in again.</div>}
          <div>
            <label className="text-xs font-medium text-graphite-600">Email</label>
            <input className="input mt-1" type="email" required autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@crm.local" />
          </div>
          <div>
            <label className="text-xs font-medium text-graphite-600">Password</label>
            <input className="input mt-1" type="password" required autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="••••••••" />
          </div>
          <button className="btn-primary w-full !py-2.5" disabled={busy}>{busy ? 'Signing in…' : 'Sign in'}</button>
          {import.meta.env.DEV && <p className="text-xs text-graphite-400 text-center">Dev: admin@crm.local / Admin123! — employees are created by admin</p>}
        </form>
      </div>
    </div>
  );
}

/* ================= DASHBOARD ================= */
export function Dashboard() {
  const [d, setD] = useState<any>(null);
  const [src, setSrc] = useState<any>(null);
  const [monthly, setMonthly] = useState<any[]>([]);
  const [error, setError] = useState('');
  const [dlError, setDlError] = useState('');
  const [loading, setLoading] = useState(true);
  const dl = async (path: string, filename: string, params?: Record<string, string>) => {
    setDlError('');
    try { await downloadReport(path, filename, params); }
    catch (e: any) { setDlError(e?.message || 'Download failed'); }
  };
  const load = () => {
    setLoading(true); setError('');
    Promise.allSettled([
      api.get('/dashboard'),
      api.get('/dashboard/by-source'),
      api.get('/reports/monthly'),
    ]).then(([dr, sr, mr]) => {
      if (dr.status === 'fulfilled') setD(dr.value.data);
      else setError(dr.reason?.response?.data?.detail || 'Failed to load dashboard. Check backend / login again.');
      if (sr.status === 'fulfilled') setSrc(sr.value.data);
      if (mr.status === 'fulfilled') setMonthly(Array.isArray(mr.value.data) ? mr.value.data : []);
    }).finally(() => setLoading(false));
  };
  useEffect(() => { load(); }, []);
  const pie = useMemo(() => Object.entries(src || {}).map(([name, v]: any) => ({ name, value: v.total ?? 0 })).filter((x) => x.value > 0), [src]);
  const srcRows = useMemo(() => Object.entries(src || {}).map(([name, v]: any) => ({ name, ...(v as object) })).sort((a: any, b: any) => (b.total || 0) - (a.total || 0)), [src]);
  const srcTotals = useMemo(() => {
    const t = { total: 0, follow: 0, prospect: 0, rnr: 0, notInt: 0, converted: 0 };
    for (const r of srcRows as any[]) {
      t.total += r.total || 0;
      t.follow += r['In Followup'] || 0;
      t.prospect += r['A - Prospect'] || 0;
      t.rnr += r['RNR / Not reachable'] || 0;
      t.notInt += (r['Not Interested'] || 0) + (r['Not Interested/Spam'] || 0);
      t.converted += r.Converted || 0;
    }
    return t;
  }, [srcRows]);
  if (loading && !d) return <Spinner />;
  if (error && !d) {
    return (
      <div>
        <PageHeader title="Leads Funnel — Live Dashboard" subtitle="Status cards, source mix and monthly volume from live database data." />
        <div className="card p-8 text-center">
          <p className="font-medium text-graphite-700">Could not load dashboard</p>
          <p className="text-sm text-graphite-500 mt-1">{error}</p>
          <button className="btn-primary mt-4" onClick={load}>Retry</button>
        </div>
      </div>
    );
  }
  if (!d) return <Spinner />;
  const f = d.funnel || {};
  const tiles = [
    { label: 'Total Leads', value: f.total ?? d.total, bg: 'bg-[#1e3a5f]', text: 'text-white' },
    { label: 'In Followup', value: f.in_followup ?? 0, bg: 'bg-[#c0392b]', text: 'text-white' },
    { label: 'Prospect / A', value: f.prospect ?? 0, bg: 'bg-[#27ae60]', text: 'text-white' },
    { label: 'RNR / Not Resp.', value: f.rnr ?? 0, bg: 'bg-[#e67e22]', text: 'text-white' },
    { label: 'Pipeline / A+', value: f.pipeline ?? 0, bg: 'bg-[#1e8449]', text: 'text-white' },
    { label: 'Not Interested', value: f.not_interested ?? 0, bg: 'bg-[#7b241c]', text: 'text-white' },
    { label: 'Converted', value: f.converted ?? 0, bg: 'bg-[#196f3d]', text: 'text-white' },
    { label: 'New Lead', value: f.new_lead ?? 0, bg: 'bg-[#1c2833]', text: 'text-white' },
    { label: 'Assigned', value: f.assigned ?? 0, bg: 'bg-[#0e7490]', text: 'text-white' },
  ];
  return (
    <div className="space-y-5">
      <PageHeader title="Leads Funnel — Live Dashboard" subtitle="Status cards, source mix and monthly volume from live database data." />
      {d.warning && (
        <div className="bg-amber-50 border border-amber-300 text-amber-800 rounded-xl px-4 py-3 text-sm">⚠ {d.warning}</div>
      )}
      {dlError && (
        <div className="bg-red-50 border border-red-200 text-red-700 rounded-xl px-4 py-3 text-sm">❌ {dlError}</div>
      )}
      <div className="grid lg:grid-cols-2 gap-5">
        <div className="space-y-5">
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
            {tiles.map((t) => (
              <div key={t.label} className={`${t.bg} ${t.text} rounded-lg px-3 py-3 shadow-sm`}>
                <div className="text-[10px] uppercase tracking-wide opacity-90 font-semibold leading-tight">{t.label}</div>
                <div className="text-2xl font-bold mt-1 tabular-nums">{t.value}</div>
              </div>
            ))}
          </div>
          <div className="bg-graphite-100 text-graphite-700 rounded-lg px-3 py-2 text-sm flex justify-between">
            <span className="font-medium">Other / Unmapped status</span>
            <span className="font-bold tabular-nums">{f.other ?? 0}</span>
          </div>

          <Card title="Leads by Source">
            <div className="overflow-x-auto -mx-5 px-5">
              <table className="w-full min-w-[640px] text-sm">
                <thead>
                  <tr className="bg-[#0e7490] text-white">
                    <th className="th !text-white !bg-transparent">Source</th>
                    <th className="th text-right !text-white !bg-transparent">Total</th>
                    <th className="th text-right !text-white !bg-transparent">In Followup</th>
                    <th className="th text-right !text-white !bg-transparent">Prospect</th>
                    <th className="th text-right !text-white !bg-transparent">RNR</th>
                    <th className="th text-right !text-white !bg-transparent">Not Int.</th>
                    <th className="th text-right !text-white !bg-transparent">Converted</th>
                    <th className="th text-right !text-white !bg-transparent">Conv.%</th>
                  </tr>
                </thead>
                <tbody>
                  {srcRows.map((r: any, i: number) => (
                    <tr key={r.name} className={i % 2 ? 'bg-sky-50/60' : 'bg-white'}>
                      <td className="td font-medium">{r.name}</td>
                      <td className="td text-right font-bold">{r.total}</td>
                      <td className="td text-right">{r['In Followup'] ?? 0}</td>
                      <td className="td text-right">{r['A - Prospect'] ?? 0}</td>
                      <td className="td text-right">{r['RNR / Not reachable'] ?? 0}</td>
                      <td className="td text-right">{(r['Not Interested'] ?? 0) + (r['Not Interested/Spam'] ?? 0)}</td>
                      <td className="td text-right">{r.Converted ?? 0}</td>
                      <td className="td text-right">{r.total ? (((r.Converted ?? 0) / r.total) * 100).toFixed(1) : '0.0'}%</td>
                    </tr>
                  ))}
                  {srcRows.length > 0 && (
                    <tr className="bg-graphite-100 font-bold">
                      <td className="td">TOTAL</td>
                      <td className="td text-right">{srcTotals.total}</td>
                      <td className="td text-right">{srcTotals.follow}</td>
                      <td className="td text-right">{srcTotals.prospect}</td>
                      <td className="td text-right">{srcTotals.rnr}</td>
                      <td className="td text-right">{srcTotals.notInt}</td>
                      <td className="td text-right">{srcTotals.converted}</td>
                      <td className="td text-right">{srcTotals.total ? ((srcTotals.converted / srcTotals.total) * 100).toFixed(1) : '0.0'}%</td>
                    </tr>
                  )}
                </tbody>
              </table>
              {srcRows.length === 0 && <EmptyState title="No source data" hint="Import leads to populate the funnel." />}
            </div>
          </Card>
        </div>

        <div className="space-y-5">
          <Card title="Leads by Source">
            {pie.length === 0 ? <EmptyState title="No data" /> : (
              <div className="h-80">
                <ResponsiveContainer>
                  <PieChart>
                    <Pie data={pie} dataKey="value" nameKey="name" outerRadius={110} label={({ percent }) => `${(((percent ?? 0)) * 100).toFixed(0)}%`}>
                      {pie.map((e: any, i: number) => <Cell key={e.name} fill={COLORS[i % COLORS.length]} />)}
                    </Pie>
                    <Tooltip /><Legend />
                  </PieChart>
                </ResponsiveContainer>
              </div>
            )}
          </Card>
          <Card title="Monthly Lead Volume" action={
            <button type="button" className="btn-secondary !px-3 !py-1 text-xs" onClick={() => dl('/reports/monthly/export', 'monthly-lead-volume.xlsx')}>
              Download
            </button>
          }>
            {monthly.length === 0 ? <EmptyState title="No dated leads" /> : (
              <div className="h-80">
                <ResponsiveContainer>
                  <BarChart data={monthly}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                    <XAxis dataKey="month" tick={{ fontSize: 11 }} />
                    <YAxis allowDecimals={false} tick={{ fontSize: 12 }} />
                    <Tooltip /><Legend />
                    <Bar dataKey="leads" fill="#1e3a5f" name="Total Leads" radius={[4, 4, 0, 0]} />
                    <Bar dataKey="converted" fill="#c0392b" name="Converted" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            )}
          </Card>
        </div>
      </div>
    </div>
  );
}

/* ================= LEADS ================= */
export function Leads() {
  const [items, setItems] = useState<any[]>([]);
  const [total, setTotal] = useState(0);
  const [masters, setMasters] = useState<any>(null);
  const [search, setSearch] = useState('');
  const [status, setStatus] = useState('');
  const [source, setSource] = useState('');
  const [sla, setSla] = useState('');
  const [unassigned, setUnassigned] = useState(false);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const size = 15;
  useEffect(() => { api.get('/masters').then((r) => setMasters(r.data)).catch(() => setError('Could not load filters.')); }, []);
  useEffect(() => {
    const ctrl = new AbortController();
    const t = setTimeout(() => {
      setLoading(true); setError('');
      api.get('/leads', {
        params: { search, status, source, sla, unassigned: unassigned ? '1' : '', page, size },
        signal: ctrl.signal,
      })
        .then((r) => {
          setItems(r.data.items || []);
          setTotal(r.data.total ?? 0);
          const pages = Math.max(1, Math.ceil((r.data.total ?? 0) / size));
          if (page > pages) setPage(pages);
        })
        .catch((e: any) => {
          if (e?.code === 'ERR_CANCELED') return;
          setError(e?.response?.data?.detail || 'Could not load leads.');
        })
        .finally(() => { if (!ctrl.signal.aborted) setLoading(false); });
    }, 300);
    return () => { clearTimeout(t); ctrl.abort(); };
  }, [search, status, source, sla, unassigned, page]);
  const nameOf = (kind: 'statuses' | 'sources' | 'employees' | 'products', id?: string) =>
    masters?.[kind]?.find((x: any) => x.id === id)?.name ?? '—';
  return (
    <div>
      <PageHeader title="Leads" subtitle={`${total} lead${total === 1 ? '' : 's'} found · Excel import only · 3 open customers per employee`} />
      <div className="card p-4 mb-4 flex flex-wrap gap-3 items-center">
        <input className="input !w-64" placeholder="🔍 Search name, phone, enquiry…" value={search} onChange={(e) => { setSearch(e.target.value); setPage(1); }} />
        <select className="input !w-52" value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }}>
          <option value="">All statuses</option>
          {masters?.statuses?.map((s: any) => <option key={s.id} value={s.id}>{s.name}</option>)}
        </select>
        <select className="input !w-52" value={source} onChange={(e) => { setSource(e.target.value); setPage(1); }}>
          <option value="">All sources (Excel)</option>
          {masters?.sources?.map((s: any) => <option key={s.id} value={s.id}>{s.name}</option>)}
        </select>
        <select className="input !w-44" value={sla} onChange={(e) => { setSla(e.target.value); setPage(1); }}>
          <option value="">All SLA states</option>
          <option value="PENDING">Pending</option>
          <option value="OVERDUE">Overdue</option>
          <option value="COMPLETED">Completed</option>
        </select>
        <label className="inline-flex items-center gap-2 text-sm text-graphite-600 cursor-pointer">
          <input type="checkbox" checked={unassigned} onChange={(e) => { setUnassigned(e.target.checked); setPage(1); }} />
          Pending assignment only
        </label>
      </div>
      {error && <div className="bg-red-50 border border-red-200 text-red-700 text-sm rounded-xl px-4 py-3 mb-4">{error}</div>}
      <div className="card overflow-hidden">
        {loading ? <Spinner /> : items.length === 0 ? <EmptyState title={error ? 'Could not load leads' : 'No leads match'} hint={error ? 'Check your connection and retry.' : 'Import the Excel tracker or adjust filters.'} /> : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[900px]">
              <thead className="bg-graphite-50"><tr>
                <th className="th">Enquiry</th><th className="th">Customer</th><th className="th">Company</th>
                <th className="th">City</th><th className="th">Source</th><th className="th">Status</th><th className="th">Employee</th><th className="th">SLA</th>
              </tr></thead>
              <tbody>
                {items.map((l) => (
                  <tr key={l.id} className="hover:bg-brand-50/50">
                    <td className="td font-semibold text-brand-700 whitespace-nowrap"><Link to={`/leads/${l.id}`}>{l.enquiry_number}</Link></td>
                    <td className="td"><div className="font-medium text-graphite-900">{l.customer_name || '—'}</div></td>
                    <td className="td">{l.company_name || '—'}</td>
                    <td className="td">{l.city || '—'}</td>
                    <td className="td">{nameOf('sources', l.source_id)}</td>
                    <td className="td"><StatusBadge value={nameOf('statuses', l.status_id)} /></td>
                    <td className="td">{l.primary_employee_id ? nameOf('employees', l.primary_employee_id) : <span className="text-amber-700 text-xs font-medium">Pending</span>}</td>
                    <td className="td"><SlaBadge value={l.sla_state} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <div className="flex items-center justify-between px-4 py-3 border-t border-graphite-100 text-sm">
          <span className="text-graphite-500">Page {page} of {Math.max(1, Math.ceil(total / size))}</span>
          <div className="flex gap-2">
            <button className="btn-secondary !px-3 !py-1" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>← Prev</button>
            <button className="btn-secondary !px-3 !py-1" disabled={page * size >= total} onClick={() => setPage((p) => p + 1)}>Next →</button>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ================= EMPLOYEE LEADS ================= */
export function EmployeeLeads() {
  const [masters, setMasters] = useState<any>(null);
  const [empId, setEmpId] = useState('');
  const [items, setItems] = useState<any[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => {
    api.get('/masters').then((r) => {
      setMasters(r.data);
      const list = r.data?.employees || [];
      if (list.length > 0) setEmpId((cur) => cur || list[0].id);
    }).catch(() => setError('Failed to load employees'));
  }, []);
  const [truncated, setTruncated] = useState(false);
  useEffect(() => {
    if (!empId) { setItems([]); setTotal(0); return; }
    setLoading(true); setError(''); setTruncated(false);
    // Two-step fetch so summary chips cover ALL assigned customers, not just page 1.
    api.get('/leads', { params: { employee: empId, page: 1, size: 1 } })
      .then((r) => {
        const totalCount = r.data.total ?? 0;
        const full = Math.min(Math.max(totalCount, 1), 500);
        setTruncated(totalCount > 500);
        return api.get('/leads', { params: { employee: empId, page: 1, size: full } });
      })
      .then((r) => { setItems(r.data.items || []); setTotal(r.data.total ?? 0); })
      .catch(() => setError('Failed to load assigned customers'))
      .finally(() => setLoading(false));
  }, [empId]);
  const nameOf = (kind: 'statuses' | 'sources' | 'employees' | 'products', id?: string) =>
    masters?.[kind]?.find((x: any) => x.id === id)?.name ?? '—';
  const empName = masters?.employees?.find((x: any) => x.id === empId)?.name ?? '';
  const needsContact = items.filter((l) => !l.first_contact_at).length;
  const overdue = items.filter((l) => l.sla_state === 'OVERDUE').length;
  const done = items.filter((l) => !!l.first_contact_at).length;
  return (
    <div>
      <PageHeader title="Employee Leads" subtitle="Select an employee to see all data of their assigned customers." />
      <div className="card p-4 mb-4 flex flex-wrap gap-3 items-center">
        <label className="text-xs font-medium text-graphite-600">Employee</label>
        <select className="input !w-64" value={empId} onChange={(e) => setEmpId(e.target.value)}>
          <option value="">Select employee…</option>
          {masters?.employees?.map((e: any) => <option key={e.id} value={e.id}>{e.name}</option>)}
        </select>
        {empName && <span className="text-sm text-graphite-500">{total} customer{total === 1 ? '' : 's'} assigned{truncated ? ' (showing first 500)' : ''}</span>}
      </div>
      {error && <div className="bg-red-50 border border-red-200 text-red-700 text-sm rounded-xl px-4 py-3 mb-4">{error}</div>}
      {!empId ? <EmptyState title="No employee selected" hint="Choose an employee above." /> : loading ? <Spinner /> : items.length === 0 ? (
        <EmptyState title={`No customers assigned to ${empName || 'this employee'}`} hint="Assign leads from the Leads page or wait for auto-assignment." />
      ) : (
        <>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 mb-4">
            {[
              { label: 'Total assigned', value: total },
              { label: 'Needs first contact', value: needsContact },
              { label: 'SLA overdue', value: overdue },
              { label: 'Contact done', value: done },
            ].map((s) => (
              <div key={s.label} className="card p-4 text-center">
                <div className="text-2xl font-bold text-graphite-900 tabular-nums">{s.value}</div>
                <div className="text-xs text-graphite-500 uppercase tracking-wide mt-1">{s.label}</div>
              </div>
            ))}
          </div>
          <div className="card overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full min-w-[1200px]">
                <thead className="bg-graphite-50"><tr>
                  <th className="th">Enquiry</th><th className="th">Customer</th><th className="th">Company</th>
                  <th className="th">City</th><th className="th">Contact</th><th className="th">Source</th>
                  <th className="th">Product</th><th className="th">Status</th><th className="th">SLA</th>
                  <th className="th">Due date</th>
                  <th className="th">First contact</th><th className="th">Enquiry date</th>
                </tr></thead>
                <tbody>
                  {items.map((l) => (
                    <tr key={l.id} className="hover:bg-brand-50/50">
                      <td className="td font-semibold text-brand-700 whitespace-nowrap"><Link to={`/leads/${l.id}`}>{l.enquiry_number}</Link></td>
                      <td className="td"><div className="font-medium text-graphite-900">{l.customer_name || '—'}</div><div className="text-xs text-graphite-400">{l.email || ''}</div></td>
                      <td className="td">{l.company_name || '—'}</td>
                      <td className="td">{l.city || '—'}</td>
                      <td className="td whitespace-nowrap">{l.contact_number || '—'}</td>
                      <td className="td">{nameOf('sources', l.source_id)}</td>
                      <td className="td">{nameOf('products', l.product_id)}</td>
                      <td className="td"><StatusBadge value={nameOf('statuses', l.status_id)} /></td>
                      <td className="td"><SlaBadge value={l.sla_state} /></td>
                      <td className={`td whitespace-nowrap tabular-nums ${l.sla_state === 'OVERDUE' ? 'text-red-700 font-semibold' : ''}`}>{fmtDT(l.sla_deadline)}</td>
                      <td className="td whitespace-nowrap">{l.first_contact_at ? `${l.first_contact_method || 'Contacted'} · ${l.first_contact_at.slice(0, 10)}` : <span className="text-amber-700 text-xs font-medium">Pending</span>}</td>
                      <td className="td whitespace-nowrap">{l.enquiry_date || '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

/* ================= LEAD DETAIL ================= */
export function LeadDetail({ id }: { id: string }) {
  const [l, setL] = useState<any>(null);
  const [masters, setMasters] = useState<any>(null);
  const [note, setNote] = useState('');
  const [method, setMethod] = useState('Call');
  const [progressId, setProgressId] = useState('');
  const [remarks, setRemarks] = useState('');
  const [assignEmp, setAssignEmp] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const [okMsg, setOkMsg] = useState('');
  const [tab, setTab] = useState<'timeline' | 'history'>('timeline');
  const role = localStorage.getItem('role') || 'EMPLOYEE';
  const [loadError, setLoadError] = useState('');
  const reload = () => api.get(`/leads/${id}`).then((r) => { setL(r.data); setLoadError(''); });
  useEffect(() => {
    reload().catch((e: any) => setLoadError(e?.response?.data?.detail || 'Could not load this lead.'));
    api.get('/masters').then((r) => setMasters(r.data)).catch(() => {});
  }, [id]);
  useEffect(() => {
    if (l?.status_id) setProgressId((cur) => cur || l.status_id);
  }, [l?.status_id]);
  if (loadError && !l) {
    return (
      <div className="card p-8 text-center">
        <p className="font-medium text-graphite-700">Lead not found or not accessible</p>
        <p className="text-sm text-graphite-500 mt-1">{loadError}</p>
        <Link to="/leads" className="btn-secondary mt-4 inline-block">← All leads</Link>
      </div>
    );
  }
  if (!l) return <Spinner />;
  const nameOf = (kind: string, v?: string) => masters?.[kind]?.find((x: any) => x.id === v)?.name ?? (v ?? '—');
  const needsContact = !l.first_contact_at && !!l.primary_employee_id;
  const canUpdateProgress = role === 'ADMIN' || role === 'MANAGER' || (role === 'EMPLOYEE' && !!l.primary_employee_id);
  const addNote = async () => {
    if (!note.trim() || busy) return;
    setBusy(true); setErr('');
    try {
      await api.post(`/leads/${id}/activities`, { activity_type: 'Note', notes: note });
      setNote(''); await reload();
    } catch (e: any) {
      setErr(e?.response?.data?.detail || 'Could not add note');
    } finally { setBusy(false); }
  };
  const saveProgress = async () => {
    if (!progressId) { setErr('Select work progress'); return; }
    if (!remarks.trim()) { setErr('Enter remarks about the conversation'); return; }
    setBusy(true); setErr(''); setOkMsg('');
    try {
      await api.post(`/leads/${id}/status`, {
        new_status_id: progressId,
        reason: remarks.trim(),
        method,
      });
      setRemarks('');
      setOkMsg('Work progress saved');
      reload();
    } catch (e: any) {
      setErr(e?.response?.data?.detail || 'Could not save work progress');
    } finally { setBusy(false); }
  };
  const doAssign = async () => {
    if (!assignEmp) return;
    setBusy(true); setErr('');
    try {
      await api.post(`/leads/${id}/assign`, { employee_id: assignEmp, role: 'PRIMARY' });
      reload();
    } catch (e: any) {
      setErr(e?.response?.data?.detail || 'Assign failed');
    } finally { setBusy(false); }
  };
  return (
    <div className="space-y-5">
      <div className="card p-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-3 flex-wrap">
              <h1 className="text-2xl font-bold text-graphite-900">{l.enquiry_number}</h1>
              {l.legacy_enquiry_no != null && <span className="text-sm text-graphite-500">Excel #{l.legacy_enquiry_no}</span>}
              <StatusBadge value={nameOf('statuses', l.status_id)} />
              <SlaBadge value={l.pending_assignment ? 'PENDING' : l.sla_state} />
              {l.pending_assignment && <span className="text-xs font-medium text-amber-700 bg-amber-50 ring-1 ring-amber-200 px-2 py-0.5 rounded-full">Unassigned</span>}
              {needsContact && <span className="text-xs font-medium text-sky-800 bg-sky-50 ring-1 ring-sky-200 px-2 py-0.5 rounded-full">Speak to customer</span>}
            </div>
            <p className="text-graphite-600 mt-1 text-lg">{l.customer_name || '—'} {l.company_name && <span className="text-graphite-400">· {l.company_name}</span>}</p>
            <div className="flex flex-wrap gap-x-5 gap-y-1 mt-2 text-sm text-graphite-500">
              <span>📍 {l.city || '—'}</span>
              <span>📅 {l.enquiry_date || '—'}</span>
              <span>🚗 {l.quantity_raw || '—'}</span>
              <span>🏷 {nameOf('sources', l.source_id)}</span>
              <span>📦 {nameOf('products', l.product_id)}</span>
              <span>👤 {nameOf('employees', l.primary_employee_id)}</span>
              {l.sla_deadline && <span>⏱ Contact by {fmtDT(l.sla_deadline)}</span>}
            </div>
          </div>
          <Link to="/leads" className="btn-secondary">← All leads</Link>
        </div>
      </div>
      {err && <div className="bg-red-50 border border-red-200 text-red-700 text-sm rounded-xl px-4 py-3">{err}</div>}
      {okMsg && <div className="bg-emerald-50 border border-emerald-200 text-emerald-800 text-sm rounded-xl px-4 py-3">{okMsg}</div>}

      {role === 'ADMIN' && l.pending_assignment && (
        <Card title="Assign to employee">
          <div className="flex flex-wrap gap-3 items-end">
            <div className="flex-1 min-w-[200px]">
              <label className="text-xs font-medium text-graphite-600">Employee (must be free — 3 open leads max)</label>
              <select className="input mt-1" value={assignEmp} onChange={(e) => setAssignEmp(e.target.value)}>
                <option value="">Select…</option>
                {masters?.employees?.map((e: any) => <option key={e.id} value={e.id}>{e.name}</option>)}
              </select>
            </div>
            <button className="btn-primary" disabled={!assignEmp || busy} onClick={doAssign}>Assign</button>
          </div>
        </Card>
      )}

      <div className="grid lg:grid-cols-3 gap-4">
        <div className="space-y-4 lg:col-span-1">
          {canUpdateProgress && (
            <Card title="Update work progress">
              <p className="text-xs text-graphite-500 mb-3">
                {needsContact
                  ? 'After you speak to the assigned customer, set progress and add remarks. This also completes the 3-day contact SLA.'
                  : 'After each follow-up call, update progress and add remarks.'}
              </p>
              <div className="space-y-2">
                {needsContact && (
                  <div>
                    <label className="text-xs font-medium text-graphite-600">Contact method</label>
                    <select className="input mt-1" value={method} onChange={(e) => setMethod(e.target.value)}>
                      {['Call', 'WhatsApp', 'Email', 'Meeting', 'Other'].map((m) => <option key={m}>{m}</option>)}
                    </select>
                  </div>
                )}
                <div>
                  <label className="text-xs font-medium text-graphite-600">Work progress</label>
                  <select className="input mt-1" value={progressId} onChange={(e) => setProgressId(e.target.value)}>
                    <option value="">Select progress…</option>
                    {masters?.statuses?.map((s: any) => <option key={s.id} value={s.id}>{s.name}</option>)}
                  </select>
                </div>
                <div>
                  <label className="text-xs font-medium text-graphite-600">Remarks</label>
                  <textarea
                    className="input mt-1 min-h-[110px]"
                    placeholder="What did the customer say? Next step…"
                    value={remarks}
                    onChange={(e) => setRemarks(e.target.value)}
                  />
                </div>
                <button onClick={saveProgress} disabled={busy || !progressId || !remarks.trim()} className="btn-primary w-full">
                  {busy ? 'Saving…' : needsContact ? 'Save progress & complete contact' : 'Save work progress'}
                </button>
              </div>
            </Card>
          )}
          {l.first_contact_at && (
            <Card title="First contact recorded">
              <p className="text-sm text-graphite-700"><b>{l.first_contact_method}</b> · {l.first_contact_result}</p>
              <p className="text-xs text-graphite-400 mt-1">{fmtDT(l.first_contact_at)}</p>
              {l.first_contact_notes && <p className="text-sm mt-2 whitespace-pre-wrap">{l.first_contact_notes}</p>}
            </Card>
          )}
          {role !== 'EMPLOYEE' && (
            <Card title="Add note">
              <textarea className="input min-h-[90px]" placeholder="Later follow-up note…" value={note} onChange={(e) => setNote(e.target.value)} />
              <button onClick={addNote} className="btn-secondary w-full mt-3">Add to timeline</button>
            </Card>
          )}
        </div>
        <div className="card lg:col-span-2">
          <div className="flex gap-1 border-b border-graphite-200 px-4 pt-3 text-sm font-medium">
            {(['timeline', 'history'] as const).map((t) => (
              <button key={t} onClick={() => setTab(t)}
                className={`px-3 py-2 capitalize rounded-t-lg ${tab === t ? 'text-brand-700 border-b-2 border-brand-600 -mb-px bg-brand-50/50' : 'text-graphite-500 hover:text-graphite-800'}`}>
                {t} ({t === 'timeline' ? l.activities?.length ?? 0 : l.history?.length ?? 0})
              </button>
            ))}
          </div>
          <div className="p-5">
            {tab === 'timeline' && ((l.activities || []).length === 0 ? <EmptyState title="No activity yet" hint="Speak to the customer and update work progress." /> : (
              <ol className="relative border-l-2 border-graphite-200 ml-2 space-y-5">
                {(l.activities || []).map((a: any) => (
                  <li key={a.id} className="ml-5">
                    <span className="absolute -left-[7px] mt-1 w-3 h-3 rounded-full bg-brand-500 ring-4 ring-brand-100" />
                    <div className="flex items-center gap-2 text-sm"><b>{a.type}</b><span className="text-xs text-graphite-400">{fmtDT(a.at)}</span></div>
                    <p className="text-sm text-graphite-700 mt-1 whitespace-pre-wrap">{a.notes}</p>
                  </li>
                ))}
              </ol>
            ))}
            {tab === 'history' && ((l.history || []).length === 0 ? <EmptyState title="No status changes" /> : (
              l.history.map((h: any) => <div key={h.id} className="border-b py-2 text-sm">{nameOf('statuses', h.old)} → <b>{nameOf('statuses', h.new)}</b>{h.reason && <span className="text-graphite-500"> — {h.reason}</span>}</div>)
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

/* ================= IMPORT ================= */
export function ImportPage() {
  const [file, setFile] = useState<File | null>(null);
  const [sheets, setSheets] = useState<string[]>([]);
  const [sheet, setSheet] = useState('');
  const [res, setRes] = useState<any>(null);
  const [done, setDone] = useState<any>(null);
  const [errors, setErrors] = useState<any[]>([]);
  const [batches, setBatches] = useState<any[]>([]);
  const [editId, setEditId] = useState<string | null>(null);
  const [editForm, setEditForm] = useState({
    name: '', city: '', company: '', phone: '', cars: '', source: '', product: '', enq: '', date: '',
  });
  const [error, setError] = useState('');
  const [okMsg, setOkMsg] = useState('');
  const [busy, setBusy] = useState(false);
  const [tab, setTab] = useState<'duplicates' | 'invalid' | 'ready'>('duplicates');
  const errMsg = (e: any) => e?.response?.data?.detail || 'Upload failed. Is the backend running?';

  const loadBatches = () => api.get('/import/batches').then((r) => setBatches(r.data || [])).catch(() => {});
  useEffect(() => { loadBatches(); }, []);

  const loadErrors = async (batchId: string) => {
    const { data } = await api.get(`/import/${batchId}/errors`);
    setErrors(data.items || []);
    setDone((d: any) => ({ ...(d || {}), batch_id: batchId }));
    if ((data.items || []).length) {
      setTab(data.items.some((x: any) => x.reason === 'DUPLICATE') ? 'duplicates' : 'invalid');
    }
  };

  const up = async (withSheet?: string) => {
    if (!file) return;
    setBusy(true); setDone(null); setError(''); setOkMsg(''); setErrors([]);
    try {
      const fd = new FormData();
      fd.append('file', file);
      if (withSheet) fd.append('sheet', withSheet);
      const { data } = await api.post('/import/excel', fd);
      if (data.batch_id) {
        setRes(data);
        setTab(data.duplicates ? 'duplicates' : 'invalid');
      } else {
        setSheets(data.sheets || []);
        setSheet(data.suggested || '');
        setRes(null);
      }
    } catch (e: any) { setError(errMsg(e)); } finally { setBusy(false); }
  };

  const [confirming, setConfirming] = useState(false);
  const confirm = async () => {
    if (!res?.batch_id || confirming) return;
    setConfirming(true); setError(''); setOkMsg('');
    try {
      const { data } = await api.post(`/import/${res.batch_id}/confirm`);
      setDone(data);
      setErrors(data.errors || []);
      setRes(null);
      loadBatches();
      if ((data.errors || []).length) setTab(data.errors.some((x: any) => x.reason === 'DUPLICATE') ? 'duplicates' : 'invalid');
    } catch (e: any) { setError(errMsg(e)); } finally { setConfirming(false); }
  };

  const pickFile = (f: File | null) => {
    setFile(f); setSheets([]); setSheet(''); setRes(null); setDone(null); setErrors([]); setError(''); setOkMsg('');
  };

  const openEdit = (row: any) => {
    setEditId(row.id);
    setEditForm({
      name: row.name || '',
      city: row.city || '',
      company: row.company || '',
      phone: row.phone || '',
      cars: row.cars || '',
      source: row.source || '',
      product: row.product || '',
      enq: row.enq != null ? String(row.enq) : '',
      date: row.date != null ? String(row.date).slice(0, 10) : '',
    });
    setError(''); setOkMsg('');
  };

  const saveEdit = async () => {
    if (!editId) return;
    setBusy(true); setError('');
    try {
      const { data } = await api.patch(`/import/errors/${editId}`, editForm);
      setErrors((prev) => prev.map((e) => (e.id === editId ? data : e)));
      setEditId(null);
      setOkMsg('Row updated — you can add it to leads now');
    } catch (e: any) { setError(errMsg(e)); } finally { setBusy(false); }
  };

  const promote = async (id: string, force = false) => {
    setBusy(true); setError(''); setOkMsg('');
    try {
      const { data } = await api.post(`/import/errors/${id}/promote`, { force });
      setErrors((prev) => prev.filter((e) => e.id !== id));
      setOkMsg(`Added as ${data.enquiry_number}${data.assigned ? ' (assigned)' : ' (pending assignment)'}`);
      loadBatches();
    } catch (e: any) { setError(errMsg(e)); } finally { setBusy(false); }
  };

  const dismiss = async (id: string) => {
    setBusy(true); setError('');
    try {
      await api.delete(`/import/errors/${id}`);
      setErrors((prev) => prev.filter((e) => e.id !== id));
      setOkMsg('Deleted from skipped list');
      loadBatches();
    } catch (e: any) { setError(errMsg(e)); } finally { setBusy(false); }
  };

  const previewDups = res?.duplicate_rows || [];
  const previewInvalid = res?.invalid_rows || [];
  const skippedDups = errors.filter((e) => e.reason === 'DUPLICATE');
  const skippedInvalid = errors.filter((e) => e.reason === 'INVALID');
  const skippedReady = errors.filter((e) => e.reason !== 'DUPLICATE' && e.reason !== 'INVALID');
  const showReview = errors.length > 0;

  const SkippedTable = ({ rows, mode }: { rows: any[]; mode: 'preview' | 'review' }) => (
    rows.length === 0 ? <EmptyState title="None" hint={mode === 'preview' ? 'No rows in this category.' : 'All cleared.'} /> : (
      <div className="overflow-x-auto -mx-5 px-5">
        <table className="w-full min-w-[980px]">
          <thead className="bg-graphite-50">
            <tr>
              <th className="th">Row</th><th className="th">Enq</th><th className="th">Name</th>
              <th className="th">Company</th><th className="th">Phone</th><th className="th">City</th><th className="th">Cars</th>
              <th className="th">Source</th><th className="th">Product</th><th className="th">Reason</th>
              {mode === 'review' && <th className="th text-right">Actions</th>}
            </tr>
          </thead>
          <tbody>
            {rows.map((r: any) => (
              <tr key={r.id ?? `row-${r.row_number ?? r.row}`} className="bg-red-50/40 hover:bg-red-50/70">
                <td className="td">{r.row_number ?? r.row}</td>
                <td className="td">{r.enq ?? r.legacy_enq ?? '—'}</td>
                <td className="td">{r.name || '—'}</td>
                <td className="td">{r.company || '—'}</td>
                <td className="td">{r.phone || '—'}</td>
                <td className="td">{r.city || '—'}</td>
                <td className="td">{r.cars || '—'}</td>
                <td className="td">{r.source || '—'}</td>
                <td className="td">{r.product || '—'}</td>
                <td className="td text-xs text-red-700">{r.error || (r.errors || []).join(', ') || '—'}</td>
                {mode === 'review' && (
                  <td className="td text-right whitespace-nowrap space-x-1">
                    <button type="button" className="btn-secondary !px-2 !py-1 text-xs" onClick={() => openEdit(r)}>Correct</button>
                    <button type="button" className="btn-primary !px-2 !py-1 text-xs" disabled={busy} onClick={() => promote(r.id)}>Add to leads</button>
                    <button type="button" className="btn-secondary !px-2 !py-1 text-xs" disabled={busy} onClick={() => promote(r.id, true)} title="Create even if enquiry no conflicts">Force add</button>
                    <button type="button" className="btn-secondary !px-2 !py-1 text-xs" disabled={busy} onClick={() => dismiss(r.id)}>Delete</button>
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    )
  );

  return (
    <div className="space-y-5 max-w-6xl">
      <PageHeader
        title="Import from Excel"
        subtitle="Columns: Enq no, Received date, Name, Company (optional), Contact no, City, No. of cars, Lead source, Product/type. Admin can view duplicates/invalid and Add to leads or Delete."
      />
      {error && <div className="bg-[#E03131]/10 border border-[#E03131]/40 text-[#B32727] text-sm rounded-xl px-4 py-3">❌ {error}</div>}
      {okMsg && <div className="bg-[#2F9E44]/10 border border-[#2F9E44]/40 text-[#237A35] text-sm rounded-xl px-4 py-3">✓ {okMsg}</div>}

      <Card title="1 · Upload workbook">
        <div className="flex flex-wrap items-center gap-3">
          <label className="flex-1 min-w-[240px] border-2 border-dashed border-graphite-300 rounded-xl px-4 py-6 text-center cursor-pointer hover:border-brand-400 hover:bg-brand-50/50 transition-colors">
            <div className="text-2xl">📤</div>
            <div className="text-sm font-medium mt-1">{file ? file.name : 'Choose .xlsx file…'}</div>
            <input type="file" accept=".xlsx" className="hidden" onChange={(e) => pickFile(e.target.files?.[0] || null)} />
          </label>
          <button onClick={() => up()} disabled={!file || busy} className="btn-primary">{busy ? 'Reading…' : 'List sheets'}</button>
        </div>
      </Card>

      {sheets.length > 0 && (
        <Card title="2 · Choose sheet">
          <div className="flex flex-wrap items-center gap-3">
            <select className="input !w-80" value={sheet} onChange={(e) => setSheet(e.target.value)}>
              {sheets.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
            <button onClick={() => up(sheet)} disabled={!sheet || busy} className="btn-primary">{busy ? 'Analyzing…' : 'Preview & validate'}</button>
          </div>
        </Card>
      )}

      {res && (
        <>
          <Card title={`3 · Preview — ${res.sheet || ''}`}>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
              {[['Total rows', res.total, 'slate'], ['Duplicates', res.duplicates, 'amber'], ['Invalid', res.invalid, 'red'], ['Ready', res.valid, 'green']].map(([k, v, t]: any) => (
                <div key={k} className="bg-graphite-50 border rounded-lg p-3 text-center">
                  <div className={`text-2xl font-bold ${t === 'red' ? 'text-[#E03131]' : t === 'amber' ? 'text-[#E8890C]' : t === 'green' ? 'text-[#2F9E44]' : ''}`}>{v}</div>
                  <div className="text-xs text-graphite-500 uppercase tracking-wide">{k}</div>
                </div>
              ))}
            </div>
            <p className="text-sm text-graphite-600 mb-3">Ready rows (first 50):</p>
            <div className="overflow-x-auto -mx-5 px-5 mb-4">
              <table className="w-full min-w-[900px]"><thead className="bg-graphite-50"><tr>
                <th className="th">Row</th><th className="th">Enq</th><th className="th">Date</th><th className="th">Name</th>
                <th className="th">Company</th><th className="th">Phone</th><th className="th">City</th><th className="th">Cars</th>
                <th className="th">Source</th><th className="th">Product</th>
              </tr></thead>
                <tbody>{(res.preview || []).map((r: any) => (
                  <tr key={r.row}>
                    <td className="td">{r.row}</td>
                    <td className="td">{r.legacy_enq ?? '—'}</td>
                    <td className="td">{r.date != null ? String(r.date).slice(0, 10) : '—'}</td>
                    <td className="td">{r.name}</td>
                    <td className="td">{r.company || '—'}</td>
                    <td className="td">{r.phone || '—'}</td>
                    <td className="td">{r.city || '—'}</td>
                    <td className="td">{r.cars || '—'}</td>
                    <td className="td">{r.source || '—'}</td>
                    <td className="td">{r.product || '—'}</td>
                  </tr>
                ))}</tbody>
              </table>
            </div>
            <button onClick={confirm} disabled={confirming || (!res.valid && !res.duplicates && !res.invalid)} className="btn-primary">
              {confirming ? 'Importing…' : `4 · Confirm import (${res.valid} leads)`}{res.duplicates || res.invalid ? ` · keep ${res.duplicates + res.invalid} for review` : ''}
            </button>
          </Card>

          {(previewDups.length > 0 || previewInvalid.length > 0) && (
            <Card title="Duplicates & invalid (saved for admin review after confirm)">
              <div className="flex gap-2 mb-3 text-sm font-medium">
                <button type="button" onClick={() => setTab('duplicates')} className={`px-3 py-1.5 rounded-lg ${tab === 'duplicates' ? 'bg-amber-100 text-amber-900' : 'bg-graphite-100 text-graphite-600'}`}>
                  Duplicates ({previewDups.length})
                </button>
                <button type="button" onClick={() => setTab('invalid')} className={`px-3 py-1.5 rounded-lg ${tab === 'invalid' ? 'bg-red-100 text-red-900' : 'bg-graphite-100 text-graphite-600'}`}>
                  Invalid ({previewInvalid.length})
                </button>
              </div>
              <SkippedTable rows={tab === 'duplicates' ? previewDups : previewInvalid} mode="preview" />
            </Card>
          )}
        </>
      )}

      {done && (
        <div className="bg-[#2F9E44]/10 border border-[#2F9E44]/40 rounded-xl p-5 text-sm">
          <b>Import complete:</b> {done.imported} imported · {done.assigned ?? 0} assigned · {done.pending ?? 0} pending · {done.duplicates} duplicates · {done.invalid} invalid.
        </div>
      )}

      {showReview && (
        <Card title="Admin review — Add to leads or Delete">
          <p className="text-sm text-graphite-500 mb-3">
            View skipped rows below. <b>Correct</b> fields if needed, then <b>Add to leads</b>. Use <b>Force add</b> if enquiry no conflicts but it should still become a lead. <b>Delete</b> removes it from this list.
          </p>
          <div className="flex gap-2 mb-3 text-sm font-medium">
            <button type="button" onClick={() => setTab('duplicates')} className={`px-3 py-1.5 rounded-lg ${tab === 'duplicates' ? 'bg-amber-100 text-amber-900' : 'bg-graphite-100 text-graphite-600'}`}>
              Duplicates ({skippedDups.length})
            </button>
            <button type="button" onClick={() => setTab('invalid')} className={`px-3 py-1.5 rounded-lg ${tab === 'invalid' ? 'bg-red-100 text-red-900' : 'bg-graphite-100 text-graphite-600'}`}>
              Invalid ({skippedInvalid.length})
            </button>
            <button type="button" onClick={() => setTab('ready')} className={`px-3 py-1.5 rounded-lg ${tab === 'ready' ? 'bg-emerald-100 text-emerald-900' : 'bg-graphite-100 text-graphite-600'}`}>
              Ready ({skippedReady.length})
            </button>
          </div>
          <SkippedTable rows={tab === 'duplicates' ? skippedDups : tab === 'ready' ? skippedReady : skippedInvalid} mode="review" />
        </Card>
      )}

      {batches.length > 0 && (
        <Card title="Recent import batches">
          <div className="overflow-x-auto -mx-5 px-5">
            <table className="w-full min-w-[640px]">
              <thead className="bg-graphite-50"><tr>
                <th className="th">File</th><th className="th">Status</th><th className="th text-right">Imported</th>
                <th className="th text-right">Dup</th><th className="th text-right">Invalid</th><th className="th text-right">Actions</th>
              </tr></thead>
              <tbody>
                {batches.filter((b) => b.status === 'DONE').slice(0, 10).map((b) => (
                  <tr key={b.id} className="hover:bg-graphite-50">
                    <td className="td text-sm">{b.file_name}<div className="text-xs text-graphite-400">{b.sheet_name}</div></td>
                    <td className="td">{b.status}</td>
                    <td className="td text-right">{b.imported}</td>
                    <td className="td text-right">{b.duplicates}</td>
                    <td className="td text-right">{b.invalid}</td>
                    <td className="td text-right">
                      <button type="button" className="btn-secondary !px-2 !py-1 text-xs" onClick={() => loadErrors(b.id)}>View skipped</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {editId && (
        <div className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-4" onClick={() => setEditId(null)}>
          <div className="card p-6 w-full max-w-lg space-y-3" onClick={(e) => e.stopPropagation()}>
            <h3 className="font-semibold text-graphite-900">Correct row</h3>
            <div className="grid grid-cols-2 gap-3">
              <div className="col-span-2">
                <label className="text-xs font-medium text-graphite-600">Name</label>
                <input className="input mt-1" value={editForm.name} onChange={(e) => setEditForm({ ...editForm, name: e.target.value })} />
              </div>
              <div>
                <label className="text-xs font-medium text-graphite-600">Enquiry no</label>
                <input className="input mt-1" value={editForm.enq} onChange={(e) => setEditForm({ ...editForm, enq: e.target.value })} />
              </div>
              <div>
                <label className="text-xs font-medium text-graphite-600">Received date</label>
                <input className="input mt-1" value={editForm.date} onChange={(e) => setEditForm({ ...editForm, date: e.target.value })} />
              </div>
              <div>
                <label className="text-xs font-medium text-graphite-600">Company (optional)</label>
                <input className="input mt-1" value={editForm.company} onChange={(e) => setEditForm({ ...editForm, company: e.target.value })} />
              </div>
              <div>
                <label className="text-xs font-medium text-graphite-600">Contact no</label>
                <input className="input mt-1" value={editForm.phone} onChange={(e) => setEditForm({ ...editForm, phone: e.target.value })} />
              </div>
              <div>
                <label className="text-xs font-medium text-graphite-600">City</label>
                <input className="input mt-1" value={editForm.city} onChange={(e) => setEditForm({ ...editForm, city: e.target.value })} />
              </div>
              <div>
                <label className="text-xs font-medium text-graphite-600">No. of cars</label>
                <input className="input mt-1" value={editForm.cars} onChange={(e) => setEditForm({ ...editForm, cars: e.target.value })} />
              </div>
              <div>
                <label className="text-xs font-medium text-graphite-600">Lead source</label>
                <input className="input mt-1" value={editForm.source} onChange={(e) => setEditForm({ ...editForm, source: e.target.value })} />
              </div>
              <div className="col-span-2">
                <label className="text-xs font-medium text-graphite-600">Product / type</label>
                <input className="input mt-1" value={editForm.product} onChange={(e) => setEditForm({ ...editForm, product: e.target.value })} />
              </div>
            </div>
            <div className="flex gap-2 justify-end">
              <button type="button" className="btn-secondary" onClick={() => setEditId(null)}>Cancel</button>
              <button type="button" className="btn-primary" disabled={busy} onClick={saveEdit}>Save</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

/* ================= REPORTS ================= */
function money(n: number) {
  return Number(n || 0).toLocaleString('en-IN', { maximumFractionDigits: 2 });
}

function barRows(v: any): any[] {
  return Array.isArray(v) ? v : [];
}

function BarCard({ title, data, x, y, onDownload }: {
  title: string; data: any[]; x: string; y: string; onDownload?: () => void;
}) {
  return (
    <Card title={title} action={onDownload && (
      <button type="button" className="btn-secondary !px-3 !py-1 text-xs" onClick={onDownload}>
        Download Excel
      </button>
    )}>
      {barRows(data).length === 0 ? <EmptyState title="No data" /> : (
        <div className="h-72">
          <ResponsiveContainer>
            <BarChart data={barRows(data)} layout="vertical" margin={{ left: 8, right: 16 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" horizontal={false} />
              <XAxis type="number" allowDecimals={false} tick={{ fontSize: 12 }} />
              <YAxis type="category" dataKey={x} width={170} tick={{ fontSize: 12 }} />
              <Tooltip />
              <Bar dataKey={y} fill="#65A30D" radius={[0, 6, 6, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </Card>
  );
}

export function Reports() {
  const today = new Date();
  const defaultMonth = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}`;
  const [prod, setProd] = useState<any[]>([]);
  const [emp, setEmp] = useState<any[]>([]);
  const [mode, setMode] = useState<'custom' | 'month'>('custom');
  const [month, setMonth] = useState(defaultMonth);
  const [fromDate, setFromDate] = useState(`${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-01`);
  const [toDate, setToDate] = useState(today.toISOString().slice(0, 10));
  const [details, setDetails] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');

  useEffect(() => {
    api.get('/reports/product-wise').then((r) => setProd(Array.isArray(r.data) ? r.data : [])).catch(() => setErr('Could not load product report.'));
    api.get('/reports/employee-wise').then((r) => setEmp(Array.isArray(r.data) ? r.data : [])).catch(() => setErr('Could not load employee report.'));
  }, []);

  const filterParams = () => {
    if (mode === 'month') return { mode: 'month', month };
    return { mode: 'custom', from_date: fromDate, to_date: toDate };
  };

  const loadDetails = async () => {
    if (mode === 'custom' && fromDate > toDate) {
      setErr('From date must be on or before To date.');
      return;
    }
    setBusy(true); setErr('');
    try {
      const { data } = await api.get('/reports/source-details', { params: filterParams() });
      setDetails(data);
    } catch (e: any) {
      setErr(e?.response?.data?.detail || 'Failed to load details report');
    } finally { setBusy(false); }
  };

  const dl = async (path: string, filename: string, params?: Record<string, string>) => {
    try {
      await downloadReport(path, filename, params);
    } catch (e: any) {
      setErr(e?.message || 'Download failed');
    }
  };

  useEffect(() => { loadDetails(); }, []);

  const downloadDetails = async () => {
    if (mode === 'custom' && fromDate > toDate) {
      setErr('From date must be on or before To date.');
      return;
    }
    const p = filterParams();
    const name = mode === 'month'
      ? `leads-by-source-${month}.xlsx`
      : `leads-by-source-${fromDate}_to_${toDate}.xlsx`;
    try {
      await downloadReport('/reports/source-details/export', name, p);
    } catch (e: any) {
      setErr(e?.message || 'Download failed');
    }
  };

  return (
    <div className="space-y-5">
      <PageHeader
        title="Reports"
        subtitle="Details report by lead source (date range / month), product-wise counts, and monthly volume downloads."
      />

      <div className="card overflow-hidden">
        <div className="bg-[#1e3a5f] text-white px-5 py-3 font-semibold tracking-wide">
          DETAILS REPORT — LEADS BY SOURCE
        </div>
        <div className="p-5 space-y-4">
          <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-3 bg-amber-50/80 border border-amber-200 rounded-xl p-4">
            <div>
              <label className="text-xs font-medium text-graphite-600">Report Mode</label>
              <select className="input mt-1" value={mode} onChange={(e) => setMode(e.target.value as 'custom' | 'month')}>
                <option value="custom">Custom Date Range</option>
                <option value="month">Month-wise</option>
              </select>
            </div>
            {mode === 'month' ? (
              <div>
                <label className="text-xs font-medium text-graphite-600">Select Month</label>
                <input type="month" className="input mt-1" value={month} onChange={(e) => setMonth(e.target.value)} />
              </div>
            ) : (
              <>
                <div>
                  <label className="text-xs font-medium text-graphite-600">Custom From Date</label>
                  <input type="date" className="input mt-1" value={fromDate} onChange={(e) => setFromDate(e.target.value)} />
                </div>
                <div>
                  <label className="text-xs font-medium text-graphite-600">Custom To Date</label>
                  <input type="date" className="input mt-1" value={toDate} onChange={(e) => setToDate(e.target.value)} />
                </div>
              </>
            )}
            <div className="flex items-end gap-2">
              <button type="button" className="btn-primary" disabled={busy} onClick={loadDetails}>{busy ? 'Loading…' : 'Apply'}</button>
              <button type="button" className="btn-secondary" disabled={!details} onClick={downloadDetails}>Download Excel</button>
            </div>
          </div>

          {details && (
            <div className="text-sm text-graphite-700 flex flex-wrap gap-6">
              <span><b>Effective From:</b> {details.effective_from || 'All time'}</span>
              <span><b>Effective To:</b> {details.effective_to || 'All time'}</span>
            </div>
          )}
          {err && <div className="text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg px-3 py-2">{err}</div>}

          <div className="overflow-x-auto">
            <table className="w-full min-w-[960px] text-sm">
              <thead>
                <tr className="bg-[#1e3a5f] text-white">
                  <th className="th !text-white !bg-transparent">Lead Source</th>
                  <th className="th text-right !text-white !bg-transparent">Total</th>
                  <th className="th text-right !text-white !bg-transparent">In Followup</th>
                  <th className="th text-right !text-white !bg-transparent">Prospect</th>
                  <th className="th text-right !text-white !bg-transparent">RNR</th>
                  <th className="th text-right !text-white !bg-transparent">Not Int.</th>
                  <th className="th text-right !text-white !bg-transparent">Quote Sent</th>
                  <th className="th text-right !text-white !bg-transparent">Project Value (Rs.)</th>
                  <th className="th text-right !text-white !bg-transparent">Converted</th>
                  <th className="th text-right !text-white !bg-transparent">Sales Amount (Rs.)</th>
                </tr>
              </thead>
              <tbody>
                {(details?.rows || []).map((r: any, i: number) => (
                  <tr key={r.source} className={i % 2 ? 'bg-sky-50/70' : 'bg-white'}>
                    <td className="td font-medium">{r.source}</td>
                    <td className="td text-right font-bold">{r.total}</td>
                    <td className="td text-right">{r.in_followup}</td>
                    <td className="td text-right">{r.prospect}</td>
                    <td className="td text-right">{r.rnr}</td>
                    <td className="td text-right">{r.not_interested}</td>
                    <td className="td text-right">{r.quote_sent}</td>
                    <td className="td text-right">{money(r.project_value)}</td>
                    <td className="td text-right">{r.converted}</td>
                    <td className="td text-right">{money(r.sales_amount)}</td>
                  </tr>
                ))}
                {details?.totals && (
                  <tr className="bg-graphite-100 font-bold">
                    <td className="td">TOTAL</td>
                    <td className="td text-right">{details.totals.total}</td>
                    <td className="td text-right">{details.totals.in_followup}</td>
                    <td className="td text-right">{details.totals.prospect}</td>
                    <td className="td text-right">{details.totals.rnr}</td>
                    <td className="td text-right">{details.totals.not_interested}</td>
                    <td className="td text-right">{details.totals.quote_sent}</td>
                    <td className="td text-right">{money(details.totals.project_value)}</td>
                    <td className="td text-right">{details.totals.converted}</td>
                    <td className="td text-right">{money(details.totals.sales_amount)}</td>
                  </tr>
                )}
              </tbody>
            </table>
            {!details && !busy && <EmptyState title="Apply a date range to load the report" />}
          </div>
        </div>
      </div>

      <div className="grid lg:grid-cols-2 gap-4">
        <BarCard
          title="Product-wise leads"
          data={prod}
          x="product"
          y="leads"
          onDownload={() => dl('/reports/product-wise/export', 'product-wise-report.xlsx')}
        />
        <Card title="Monthly lead volume" action={
          <button type="button" className="btn-secondary !px-3 !py-1 text-xs" onClick={() => dl('/reports/monthly/export', 'monthly-lead-volume.xlsx')}>
            Download monthly Excel
          </button>
        }>
          <p className="text-sm text-graphite-600">Download total leads and converted counts for every month with a valid enquiry date.</p>
        </Card>
      </div>

      <Card title="Employee workload">
        {emp.length === 0 ? <EmptyState title="No data" /> : (
          <table className="w-full"><thead className="bg-graphite-50"><tr><th className="th">Employee</th><th className="th text-right">Assigned leads</th></tr></thead>
            <tbody>{emp.map((e: any) => <tr key={e.employee} className="hover:bg-graphite-50"><td className="td font-medium">{e.employee}</td><td className="td text-right font-bold">{e.assigned}</td></tr>)}</tbody></table>
        )}
      </Card>
    </div>
  );
}

/* ================= EMPLOYEES (ADMIN) ================= */
export function EmployeesPage() {
  const empty = { name: '', email: '', password: '', phone: '' };
  const [items, setItems] = useState<any[]>([]);
  const [form, setForm] = useState(empty);
  const [error, setError] = useState('');
  const [ok, setOk] = useState('');
  const [busy, setBusy] = useState(false);
  const [resetId, setResetId] = useState<string | null>(null);
  const [resetPw, setResetPw] = useState('');
  const load = () => api.get('/employees').then((r) => setItems(r.data)).catch(() => setError('Failed to load employees'));
  useEffect(() => { load(); }, []);
  const create = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true); setError(''); setOk('');
    const emailOk = /^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$/.test(form.email.trim());
    let digits = form.phone.replace(/\D/g, '').replace(/^0+/, '');
    if (digits.length > 10 && digits.startsWith('91')) digits = digits.slice(2);
    digits = digits.slice(-10);
    const phoneOk = /^[6-9]\d{9}$/.test(digits);
    if (!emailOk) {
      setError('Enter a valid email address (e.g. name@company.com)');
      setBusy(false);
      return;
    }
    if (!phoneOk) {
      setError('Enter a valid 10-digit Indian mobile number (starts with 6–9)');
      setBusy(false);
      return;
    }
    try {
      await api.post('/employees', { ...form, phone: digits, role: 'EMPLOYEE', department: '' });
      setForm(empty);
      setOk('Employee created');
      load();
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Create failed');
    } finally { setBusy(false); }
  };
  const toggleActive = async (emp: any) => {
    setError(''); setOk('');
    try {
      await api.patch(`/employees/${emp.id}`, { is_active: !emp.is_active });
      setOk(emp.is_active ? 'Employee deactivated' : 'Employee activated');
      load();
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Update failed');
    }
  };
  const resetPassword = async () => {
    if (!resetId || resetPw.length < 6) {
      setError('Password must be at least 6 characters');
      return;
    }
    setError(''); setOk('');
    try {
      await api.post(`/employees/${resetId}/reset-password`, { password: resetPw });
      setResetId(null); setResetPw('');
      setOk('Password updated');
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Reset failed');
    }
  };
  return (
    <div className="space-y-5 max-w-5xl">
      <PageHeader title="Employees" subtitle="Only admins can create staff accounts and reset passwords." />
      {error && <div className="bg-red-50 border border-red-200 text-red-700 text-sm rounded-xl px-4 py-3">{error}</div>}
      {ok && <div className="bg-[#2F9E44]/10 border border-[#2F9E44]/40 text-[#237A35] text-sm rounded-xl px-4 py-3">{ok}</div>}
      <Card title="Create employee">
        <form onSubmit={create} className="grid sm:grid-cols-2 gap-3">
          <div>
            <label className="text-xs font-medium text-graphite-600">Name</label>
            <input className="input mt-1" required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          </div>
          <div>
            <label className="text-xs font-medium text-graphite-600">Email</label>
            <input className="input mt-1" type="email" required placeholder="name@company.com" pattern="[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}" title="Valid email like name@company.com" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
          </div>
          <div>
            <label className="text-xs font-medium text-graphite-600">Password</label>
            <input className="input mt-1" type="password" required minLength={6} value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />
          </div>
          <div>
            <label className="text-xs font-medium text-graphite-600">Phone</label>
            <input className="input mt-1" required inputMode="tel" placeholder="9876543210" pattern="[6-9][0-9]{9}" title="10-digit Indian mobile starting with 6–9" value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} />
            <p className="text-[11px] text-graphite-400 mt-1">10-digit mobile (6–9…), optional +91</p>
          </div>
          <div className="sm:col-span-2">
            <button className="btn-primary" disabled={busy}>{busy ? 'Creating…' : 'Create employee'}</button>
          </div>
        </form>
      </Card>
      <Card title={`Staff (${items.length})`}>
        {items.length === 0 ? (
          <EmptyState title="No employees yet" hint="Create the first employee above." />
        ) : (
          <div className="overflow-x-auto -mx-5 px-5">
            <table className="w-full min-w-[640px]">
              <thead className="bg-graphite-50">
                <tr>
                  <th className="th">Name</th>
                  <th className="th">Email</th>
                  <th className="th">Phone</th>
                  <th className="th">Status</th>
                  <th className="th text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {items.map((emp) => (
                  <tr key={emp.id} className="hover:bg-graphite-50">
                    <td className="td font-medium">{emp.name}</td>
                    <td className="td">{emp.email}</td>
                    <td className="td">{emp.phone || '—'}</td>
                    <td className="td">
                      <span className={`text-xs font-medium ${emp.is_active ? 'text-[#2F9E44]' : 'text-graphite-400'}`}>
                        {emp.is_active ? 'Active' : 'Inactive'}
                      </span>
                    </td>
                    <td className="td text-right space-x-2 whitespace-nowrap">
                      <button type="button" className="btn-secondary !px-2.5 !py-1 text-xs" onClick={() => { setResetId(emp.id); setResetPw(''); setError(''); setOk(''); }}>
                        Reset password
                      </button>
                      <button type="button" className="btn-secondary !px-2.5 !py-1 text-xs" onClick={() => toggleActive(emp)}>
                        {emp.is_active ? 'Deactivate' : 'Activate'}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
      {resetId && (
        <div className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-4" onClick={() => setResetId(null)}>
          <div className="card p-6 w-full max-w-sm space-y-3" onClick={(e) => e.stopPropagation()}>
            <h3 className="font-semibold text-graphite-900">Assign new password</h3>
            <p className="text-sm text-graphite-500">Set a temporary password and share it with the employee.</p>
            <input className="input" type="password" minLength={6} placeholder="New password (min 6)" value={resetPw} onChange={(e) => setResetPw(e.target.value)} />
            <div className="flex gap-2 justify-end">
              <button type="button" className="btn-secondary" onClick={() => setResetId(null)}>Cancel</button>
              <button type="button" className="btn-primary" onClick={resetPassword}>Save password</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

/* ================= NOTIFICATIONS ================= */
export function NotificationsPage() {
  const [items, setItems] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  useEffect(() => {
    api.get('/notifications')
      .then((r) => setItems(Array.isArray(r.data) ? r.data : []))
      .catch(() => setError('Could not load notifications. Check your connection.'))
      .finally(() => setLoading(false));
  }, []);
  return (
    <div className="max-w-3xl space-y-4">
      <PageHeader title="Notifications" subtitle="SLA breaches, assignments and follow-up reminders." />
      {loading ? <div className="card"><Spinner /></div>
      : error ? <div className="card"><EmptyState title="Could not load notifications" hint={error} /></div>
      : items.length === 0 ? <div className="card"><EmptyState title="All caught up" hint="No notifications." /></div> : items.map((n) => (
        <div key={n.id} className="card p-4 flex gap-3">
          <div className="w-9 h-9 rounded-lg bg-red-100 text-red-600 flex items-center justify-center shrink-0">⚠</div>
          <div><div className="font-semibold text-sm">{n.title}</div><div className="text-sm text-graphite-600 mt-0.5">{n.body}</div></div>
        </div>
      ))}
    </div>
  );
}
