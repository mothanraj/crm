import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  PieChart, Pie, Cell, BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid,
  ResponsiveContainer, Legend, LineChart, Line,
} from 'recharts';
import { api } from '../services/api';
import { Card, EmptyState, KpiCard, PageHeader, SlaBadge, Spinner, StatusBadge } from '../components/ui';

const COLORS = ['#65A30D', '#6E6E6E', '#B5CC18', '#3F6212', '#A3A380', '#2F9E44', '#E8890C', '#84cc16', '#a3a380', '#4d7c0f', '#14b8a6', '#1971C2'];

/* ================= LOGIN ================= */
export function Login() {
  const [email, setEmail] = useState('admin@crm.local');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true); setError('');
    try {
      const { data } = await api.post('/auth/login', { email, password });
      localStorage.setItem('token', data.access_token);
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
          <div>
            <label className="text-xs font-medium text-graphite-600">Email</label>
            <input className="input mt-1" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@crm.local" />
          </div>
          <div>
            <label className="text-xs font-medium text-graphite-600">Password</label>
            <input className="input mt-1" type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="••••••••" />
          </div>
          <button className="btn-primary w-full !py-2.5" disabled={busy}>{busy ? 'Signing in…' : 'Sign in'}</button>
          <p className="text-xs text-graphite-400 text-center">Demo: admin@crm.local / Admin123! · staff use name@crm.local / Temp123!</p>
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
  useEffect(() => {
    api.get('/dashboard').then((r) => setD(r.data));
    api.get('/dashboard/by-source').then((r) => setSrc(r.data));
    api.get('/reports/monthly').then((r) => setMonthly(r.data)).catch(() => {});
  }, []);
  const pie = useMemo(() => Object.entries(src || {}).map(([name, v]: any) => ({ name, value: v.total ?? 0 })), [src]);
  const srcRows = useMemo(() => Object.entries(src || {}).map(([name, v]: any) => ({ name, ...(v as object) })).sort((a: any, b: any) => b.total - a.total), [src]);
  if (!d) return <Spinner />;
  return (
    <div className="space-y-6">
      <PageHeader title="Leads funnel" subtitle="Live view — calculated from the database, never hard-coded." />
      {d.warning && (
        <div className="bg-amber-50 border border-amber-300 text-amber-800 rounded-xl px-4 py-3 text-sm flex items-center gap-2">
          <span>⚠</span> {d.warning} Showing capped value below — click through to Leads for the full list.
        </div>
      )}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <KpiCard label="Total leads" value={d.total} icon="◧" tone="blue" />
        <KpiCard label="New leads" value={<>{d.new_lead_display}{d.new_lead_capped && <span className="text-brand-500">+</span>}</>} sub={d.new_lead_capped ? `actual ${d.new_lead_actual} — over threshold` : 'within threshold'} icon="✦" tone={d.new_lead_capped ? 'amber' : 'slate'} />
        <KpiCard label="SLA overdue" value={d.sla_overdue} icon="⏰" tone={d.sla_overdue ? 'red' : 'slate'} sub="needs first contact" />
        <KpiCard label="Unassigned" value={d.unassigned} icon="👤" tone={d.unassigned ? 'amber' : 'slate'} />
        <KpiCard label="Quotations" value={d.quotations} icon="🧾" />
        <KpiCard label="Site visits" value={d.visits} icon="📍" />
        <KpiCard label="Converted" value={d.by_status?.Converted ?? 0} icon="🏆" tone="green"
          sub={d.total ? `${(((d.by_status?.Converted ?? 0) / d.total) * 100).toFixed(1)}% conversion` : undefined} />
      </div>

      <Card title="Pipeline by status">
        <div className="flex flex-wrap gap-2">
          {Object.entries(d.by_status || {}).map(([k, v]: any) => (
            <span key={k} className="inline-flex items-center gap-2 bg-graphite-50 border border-graphite-200 rounded-lg px-3 py-1.5 text-sm">
              <StatusBadge value={k} /><b>{v}</b>
            </span>
          ))}
          {Object.keys(d.by_status || {}).length === 0 && <EmptyState title="No leads yet" hint="Import the Excel tracker to populate the funnel." />}
        </div>
      </Card>

      <div className="grid lg:grid-cols-2 gap-4">
        <Card title="Leads by source">
          {pie.length === 0 ? <EmptyState title="No data" /> : (
            <div className="h-72">
              <ResponsiveContainer>
                <PieChart>
                  <Pie data={pie} dataKey="value" nameKey="name" outerRadius={105} labelLine={false}>
                    {pie.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
                  </Pie>
                  <Tooltip /><Legend />
                </PieChart>
              </ResponsiveContainer>
            </div>
          )}
        </Card>
        <Card title="Monthly volume">
          {monthly.length === 0 ? <EmptyState title="No dated leads" /> : (
            <div className="h-72">
              <ResponsiveContainer>
                <LineChart data={monthly}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                  <XAxis dataKey="month" tick={{ fontSize: 12 }} />
                  <YAxis allowDecimals={false} tick={{ fontSize: 12 }} />
                  <Tooltip /><Legend />
                  <Line type="monotone" dataKey="leads" stroke="#65A30D" strokeWidth={2} dot={false} name="Leads" />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}
        </Card>
      </div>

      <Card title="Source summary">
        <div className="overflow-x-auto -mx-5 px-5">
          <table className="w-full min-w-[720px]">
            <thead><tr><th className="th">Source</th><th className="th text-right">Total</th><th className="th text-right">In Followup</th><th className="th text-right">Prospect</th><th className="th text-right">RNR</th><th className="th text-right">Not Int.</th><th className="th text-right">Converted</th><th className="th text-right">Conv. %</th></tr></thead>
            <tbody>
              {srcRows.map((r: any) => (
                <tr key={r.name} className="hover:bg-graphite-50">
                  <td className="td font-medium">{r.name}</td>
                  <td className="td text-right font-bold">{r.total}</td>
                  <td className="td text-right">{r['In Followup'] ?? 0}</td>
                  <td className="td text-right">{r['A - Prospect'] ?? 0}</td>
                  <td className="td text-right">{r['RNR / Not reachable'] ?? 0}</td>
                  <td className="td text-right">{r['Not Interested'] ?? 0}</td>
                  <td className="td text-right">{r.Converted ?? 0}</td>
                  <td className="td text-right">{r.total ? (((r.Converted ?? 0) / r.total) * 100).toFixed(1) : '0.0'}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
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
  const [sla, setSla] = useState('');
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const size = 15;
  useEffect(() => { api.get('/masters').then((r) => setMasters(r.data)).catch(() => {}); }, []);
  useEffect(() => {
    setLoading(true);
    api.get('/leads', { params: { search, status, sla, page, size } })
      .then((r) => { setItems(r.data.items); setTotal(r.data.total); })
      .finally(() => setLoading(false));
  }, [search, status, sla, page]);
  const nameOf = (kind: 'statuses' | 'sources' | 'employees' | 'products', id?: string) =>
    masters?.[kind]?.find((x: any) => x.id === id)?.name ?? '—';
  return (
    <div>
      <PageHeader title="Leads" subtitle={`${total} lead${total === 1 ? '' : 's'} found`} />
      <div className="card p-4 mb-4 flex flex-wrap gap-3">
        <input className="input !w-64" placeholder="🔍 Search name, company, phone…" value={search} onChange={(e) => { setSearch(e.target.value); setPage(1); }} />
        <select className="input !w-52" value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }}>
          <option value="">All statuses</option>
          {masters?.statuses?.map((s: any) => <option key={s.id} value={s.id}>{s.name}</option>)}
        </select>
        <select className="input !w-44" value={sla} onChange={(e) => { setSla(e.target.value); setPage(1); }}>
          <option value="">All SLA states</option>
          <option value="PENDING">Pending</option>
          <option value="OVERDUE">Overdue</option>
          <option value="COMPLETED">Completed</option>
        </select>
      </div>
      <div className="card overflow-hidden">
        {loading ? <Spinner /> : items.length === 0 ? <EmptyState title="No leads match" hint="Adjust filters or import the Excel tracker." /> : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[900px]">
              <thead className="bg-graphite-50"><tr>
                <th className="th">Enquiry</th><th className="th">Customer / Company</th><th className="th">Contact</th>
                <th className="th">Source</th><th className="th">Status</th><th className="th">Owner</th><th className="th">SLA</th>
              </tr></thead>
              <tbody>
                {items.map((l) => (
                  <tr key={l.id} className="hover:bg-brand-50/50">
                    <td className="td font-semibold text-brand-700 whitespace-nowrap"><Link to={`/leads/${l.id}`}>{l.enquiry_number}</Link></td>
                    <td className="td"><div className="font-medium text-graphite-900">{l.customer_name || '—'}</div><div className="text-xs text-graphite-500">{l.company_name}</div></td>
                    <td className="td whitespace-nowrap">{l.contact_number || '—'}</td>
                    <td className="td">{nameOf('sources', l.source_id)}</td>
                    <td className="td"><StatusBadge value={nameOf('statuses', l.status_id)} /></td>
                    <td className="td">{nameOf('employees', l.primary_employee_id)}</td>
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

/* ================= LEAD DETAIL ================= */
export function LeadDetail({ id }: { id: string }) {
  const [l, setL] = useState<any>(null);
  const [masters, setMasters] = useState<any>(null);
  const [note, setNote] = useState('');
  const [tab, setTab] = useState<'timeline' | 'quotes' | 'visits' | 'docs' | 'history'>('timeline');
  const reload = () => api.get(`/leads/${id}`).then((r) => setL(r.data));
  useEffect(() => { reload(); api.get('/masters').then((r) => setMasters(r.data)).catch(() => {}); }, [id]);
  if (!l) return <Spinner />;
  const nameOf = (kind: string, v?: string) => masters?.[kind]?.find((x: any) => x.id === v)?.name ?? (v ?? '—');
  const add = async () => {
    if (!note.trim()) return;
    await api.post(`/leads/${id}/activities`, { activity_type: 'Note', notes: note });
    setNote(''); reload();
  };
  return (
    <div className="space-y-5">
      <div className="card p-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-3 flex-wrap">
              <h1 className="text-2xl font-bold text-graphite-900">{l.enquiry_number}</h1>
              <StatusBadge value={nameOf('statuses', l.status_id)} />
              <SlaBadge value={l.sla_state} />
            </div>
            <p className="text-graphite-600 mt-1 text-lg">{l.customer_name} {l.company_name && <span className="text-graphite-400">· {l.company_name}</span>}</p>
            <div className="flex flex-wrap gap-x-5 gap-y-1 mt-2 text-sm text-graphite-500">
              <span>📞 {l.contact_number || '—'}</span>
              <span>✉️ {l.email || '—'}</span>
              <span>📍 {l.city || '—'}</span>
              <span>🏷 {nameOf('sources', l.source_id)}</span>
              <span>📦 {nameOf('products', l.product_id)}</span>
            </div>
          </div>
          <Link to="/leads" className="btn-secondary">← All leads</Link>
        </div>
      </div>

      <div className="grid lg:grid-cols-3 gap-4">
        <Card title="Log follow-up" className="lg:col-span-1">
          <textarea className="input min-h-[110px]" placeholder="Call outcome, customer response…" value={note} onChange={(e) => setNote(e.target.value)} />
          <button onClick={add} className="btn-primary w-full mt-3">Add to timeline</button>
        </Card>
        <div className="card lg:col-span-2">
          <div className="flex gap-1 border-b border-graphite-200 px-4 pt-3 text-sm font-medium">
            {(['timeline', 'quotes', 'visits', 'docs', 'history'] as const).map((t) => (
              <button key={t} onClick={() => setTab(t)}
                className={`px-3 py-2 capitalize rounded-t-lg ${tab === t ? 'text-brand-700 border-b-2 border-brand-600 -mb-px bg-brand-50/50' : 'text-graphite-500 hover:text-graphite-800'}`}>
                {t} ({t === 'timeline' ? l.activities?.length ?? 0 : t === 'quotes' ? l.quotations?.length ?? 0 : t === 'visits' ? l.visits?.length ?? 0 : t === 'docs' ? l.documents?.length ?? 0 : l.history?.length ?? 0})
              </button>
            ))}
          </div>
          <div className="p-5">
            {tab === 'timeline' && ((l.activities || []).length === 0 ? <EmptyState title="No activity yet" hint="Log the first follow-up above." /> : (
              <ol className="relative border-l-2 border-graphite-200 ml-2 space-y-5">
                {(l.activities || []).map((a: any) => (
                  <li key={a.id} className="ml-5">
                    <span className="absolute -left-[7px] mt-1 w-3 h-3 rounded-full bg-brand-500 ring-4 ring-brand-100" />
                    <div className="flex items-center gap-2 text-sm"><b>{a.type}</b><span className="text-xs text-graphite-400">{a.at?.slice(0, 16).replace('T', ' ')}</span></div>
                    <p className="text-sm text-graphite-700 mt-1 whitespace-pre-wrap">{a.notes}</p>
                  </li>
                ))}
              </ol>
            ))}
            {tab === 'quotes' && ((l.quotations || []).length === 0 ? <EmptyState title="No quotations" /> : (
              <table className="w-full"><thead><tr><th className="th">Number</th><th className="th text-right">Total</th></tr></thead>
                <tbody>{l.quotations.map((q: any) => <tr key={q.id}><td className="td font-medium">{q.number}</td><td className="td text-right">{q.total ?? '—'}</td></tr>)}</tbody></table>
            ))}
            {tab === 'visits' && ((l.visits || []).length === 0 ? <EmptyState title="No site visits" /> : (
              l.visits.map((v: any) => <div key={v.id} className="border-b py-2 text-sm"><b>{v.status}</b><div className="text-graphite-600">{v.notes}</div></div>)
            ))}
            {tab === 'docs' && ((l.documents || []).length === 0 ? <EmptyState title="No documents" /> : (
              l.documents.map((x: any) => <div key={x.id} className="border-b py-2 text-sm">📎 {x.name}</div>)
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
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const errMsg = (e: any) => e?.response?.data?.detail || 'Upload failed. Is the backend running?';
  const up = async (withSheet?: string) => {
    if (!file) return;
    setBusy(true); setDone(null); setError('');
    try {
      const fd = new FormData();
      fd.append('file', file);
      if (withSheet) fd.append('sheet', withSheet);
      const { data } = await api.post('/import/excel', fd);
      if (data.batch_id) {
        setRes(data);
      } else {
        // sheet discovery response
        setSheets(data.sheets || []);
        setSheet(data.suggested || '');
        setRes(null);
      }
    } catch (e: any) { setError(errMsg(e)); } finally { setBusy(false); }
  };
  const confirm = async () => {
    setError('');
    try {
      const { data } = await api.post(`/import/${res.batch_id}/confirm`);
      setDone(data);
    } catch (e: any) { setError(errMsg(e)); }
  };
  const pickFile = (f: File | null) => {
    setFile(f); setSheets([]); setSheet(''); setRes(null); setDone(null); setError('');
  };
  return (
    <div className="space-y-5 max-w-4xl">
      <PageHeader title="Import from Excel" subtitle="Upload → pick sheet → preview & validate → confirm. Nothing is written until you confirm." />
      {error && <div className="bg-[#E03131]/10 border border-[#E03131]/40 text-[#B32727] text-sm rounded-xl px-4 py-3">❌ {error}</div>}
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
        <Card title={`3 · Preview — ${res.sheet || ''}`}>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
            {[['Total rows', res.total, 'slate'], ['Duplicates', res.duplicates, 'amber'], ['Invalid', res.invalid, 'red'], ['Ready', res.valid, 'green']].map(([k, v, t]: any) => (
              <div key={k} className="bg-graphite-50 border rounded-lg p-3 text-center">
                <div className={`text-2xl font-bold ${t === 'red' ? 'text-[#E03131]' : t === 'amber' ? 'text-[#E8890C]' : t === 'green' ? 'text-[#2F9E44]' : ''}`}>{v}</div>
                <div className="text-xs text-graphite-500 uppercase tracking-wide">{k}</div>
              </div>
            ))}
          </div>
          <div className="overflow-x-auto -mx-5 px-5">
            <table className="w-full min-w-[640px]"><thead className="bg-graphite-50"><tr>
              <th className="th">Row</th><th className="th">Name</th><th className="th">Phone</th><th className="th">Source</th><th className="th">Status</th><th className="th">Flags</th>
            </tr></thead>
              <tbody>{(res.preview || []).slice(0, 15).map((r: any) => (
                <tr key={r.row} className={r.dup || r.errors ? 'bg-red-50/60' : ''}>
                  <td className="td">{r.row}</td><td className="td">{r.name || '—'}</td><td className="td">{r.phone || '—'}</td>
                  <td className="td">{r.source || '—'}</td><td className="td">{r.status || '—'}</td>
                  <td className="td text-xs">{r.dup ? '⚠ duplicate ' : ''}{r.errors ? `❌ ${r.errors.join(', ')}` : '✓ ok'}</td>
                </tr>
              ))}</tbody></table>
          </div>
          <button onClick={confirm} disabled={!res.valid} className="btn-primary mt-4">
            4 · Confirm import ({res.valid} leads)
          </button>
          {!res.valid && <p className="text-xs text-graphite-500 mt-2">No valid rows to import — duplicates and invalid rows are skipped.</p>}
        </Card>
      )}
      {done && (
        <div className="bg-[#2F9E44]/10 border border-[#2F9E44]/40 rounded-xl p-5 text-sm">
          <b>Import complete:</b> {done.imported} imported · {done.duplicates} duplicates · {done.invalid} invalid · {done.skipped} skipped (of {done.total}).
        </div>
      )}
    </div>
  );
}

/* ================= REPORTS ================= */
function BarCard({ title, data, x, y }: { title: string; data: any[]; x: string; y: string }) {
  return (
    <Card title={title}>
      {data.length === 0 ? <EmptyState title="No data" /> : (
        <div className="h-72">
          <ResponsiveContainer>
            <BarChart data={data} layout="vertical" margin={{ left: 8, right: 16 }}>
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
  const [prod, setProd] = useState<any[]>([]);
  const [srcrep, setSrcrep] = useState<any[]>([]);
  const [emp, setEmp] = useState<any[]>([]);
  useEffect(() => {
    api.get('/reports/product-wise').then((r) => setProd(r.data)).catch(() => {});
    api.get('/reports/source-wise').then((r) => setSrcrep(r.data)).catch(() => {});
    api.get('/reports/employee-wise').then((r) => setEmp(r.data)).catch(() => {});
  }, []);
  return (
    <div className="space-y-5">
      <PageHeader title="Reports" subtitle="Product, source and workload analysis from live data." />
      <div className="grid lg:grid-cols-2 gap-4">
        <BarCard title="Product-wise leads" data={prod} x="product" y="leads" />
        <BarCard title="Source-wise leads" data={srcrep} x="source" y="leads" />
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

/* ================= NOTIFICATIONS ================= */
export function NotificationsPage() {
  const [items, setItems] = useState<any[]>([]);
  useEffect(() => { api.get('/notifications').then((r) => setItems(r.data)).catch(() => {}); }, []);
  return (
    <div className="max-w-3xl space-y-4">
      <PageHeader title="Notifications" subtitle="SLA breaches, assignments and follow-up reminders." />
      {items.length === 0 ? <div className="card"><EmptyState title="All caught up" hint="No notifications." /></div> : items.map((n) => (
        <div key={n.id} className="card p-4 flex gap-3">
          <div className="w-9 h-9 rounded-lg bg-red-100 text-red-600 flex items-center justify-center shrink-0">⚠</div>
          <div><div className="font-semibold text-sm">{n.title}</div><div className="text-sm text-graphite-600 mt-0.5">{n.body}</div></div>
        </div>
      ))}
    </div>
  );
}
