import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  PieChart, Pie, Cell, BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid,
  ResponsiveContainer, Legend,
} from 'recharts';
import { api } from '../services/api';
import { subscribeLeadUpdates } from '../services/live';
import { Card, EmptyState, PageHeader, SlaBadge, Spinner, StatusBadge } from '../components/ui';

const COLORS = ['#65A30D', '#6E6E6E', '#B5CC18', '#3F6212', '#A3A380', '#2F9E44', '#E8890C', '#84cc16', '#a3a380', '#4d7c0f', '#14b8a6', '#1971C2'];

function leadRowColour(lead: any, status: string) {
  if (lead.sla_state === 'COMPLETED' && status === 'Converted') return 'bg-emerald-50';
  if (lead.sla_state === 'COMPLETED' && ['Not Interested', 'Not Interested/Spam'].includes(status)) return 'bg-red-100';
  return 'bg-white';
}

function fmtDT(v: any, len = 16) {
  if (!v) return '—';
  return String(v).slice(0, len).replace('T', ' ');
}

function prodName(l: any, nameOf: (kind: any, id?: string) => string) {
  // Prefer mapped master product name (canonical 7); fall back to raw Excel text.
  if (l.product_name) return l.product_name;
  const mapped = l.product_id ? nameOf('products', l.product_id) : '';
  if (mapped && mapped !== '—') return mapped;
  if (l.product_raw) return l.product_raw;
  return '—';
}

function inr(n: any) {
  if (n == null || n === '') return '—';
  const v = Math.round(Number(n));
  if (Number.isNaN(v)) return '—';
  return `₹${v.toLocaleString('en-IN', { maximumFractionDigits: 0, minimumFractionDigits: 0 })}`;
}

/** Opens Gmail web compose in a new browser tab (not the desktop mail app). */
function openCustomerGmail(email: string, enquiry?: string) {
  const to = (email || '').trim();
  if (!to) return;
  const params = new URLSearchParams({
    view: 'cm',
    fs: '1',
    tf: '1',
    to,
  });
  if (enquiry) params.set('su', `Regarding your enquiry ${enquiry}`);
  // /mail/u/0/ keeps this on Gmail web in the browser tab.
  const url = `https://mail.google.com/mail/u/0/?${params.toString()}`;
  const a = document.createElement('a');
  a.href = url;
  a.target = '_blank';
  a.rel = 'noopener noreferrer';
  document.body.appendChild(a);
  a.click();
  a.remove();
}

function previewLeadValue(pricePerCar: any, cars: any) {
  const p = Math.round(Number(pricePerCar));
  const c = Math.round(Number(cars));
  if (!Number.isFinite(p) || !Number.isFinite(c) || p < 0 || c <= 0) {
    return { price_per_car: Number.isFinite(p) && p >= 0 ? p : null, base_value: null, gst_amount: null, lead_value: null };
  }
  const base = Math.round(c * p);
  const gst = Math.round(base * 0.18);
  return { price_per_car: p, base_value: base, gst_amount: gst, lead_value: Math.round(base + gst) };
}

async function downloadReport(path: string, filename: string, params?: Record<string, string>) {
  const res = await api.get(path, { responseType: 'blob', params });
  const ctype = String(res.headers?.['content-type'] ?? '');
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
      localStorage.setItem('user_id', data.user.id);
      localStorage.setItem('user_name', data.user.name || data.user.email || data.user.role);
      location.href = '/dashboard';
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Cannot reach the server. Is the backend running on port 8000?');
    } finally { setBusy(false); }
  };
  return (
    <div className="min-h-screen grid md:grid-cols-2">
      <div className="hidden md:flex flex-col justify-between text-white p-12 relative overflow-hidden bg-gradient-to-br from-graphite-700 via-graphite-800 to-graphite-950">
        <div className="absolute -top-24 -right-24 w-96 h-96 rounded-full bg-brand-400/20 blur-3xl pointer-events-none" />
        <div className="flex items-center relative">
          <img src="/estar-logo.jpg" alt="E-Star" className="h-16 w-auto max-w-[200px] rounded-xl object-contain bg-white p-2 shadow-sm" />
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
          <div className="flex items-center justify-center md:hidden">
            <img src="/estar-logo.jpg" alt="E-Star" className="h-14 w-auto max-w-[180px] rounded-xl object-contain" />
          </div>
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
  const [products, setProducts] = useState<any>(null);
  const [error, setError] = useState('');
  const [showLatest, setShowLatest] = useState(false);
  const [loading, setLoading] = useState(true);
  const load = () => {
    setLoading(true); setError('');
    Promise.allSettled([
      api.get('/dashboard'),
      api.get('/dashboard/by-source'),
      api.get('/dashboard/by-product'),
    ]).then(([dr, sr, pr]) => {
      if (dr.status === 'fulfilled') setD(dr.value.data);
      else setError(dr.reason?.response?.data?.detail || 'Failed to load dashboard. Check backend / login again.');
      if (sr.status === 'fulfilled') setSrc(sr.value.data);
      if (pr.status === 'fulfilled') setProducts(pr.value.data);
      else setError('Could not load product data. Please refresh the dashboard.');
    }).finally(() => setLoading(false));
  };
  useEffect(() => { load(); }, []);
  useEffect(() => {
    if (!showLatest) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setShowLatest(false); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [showLatest]);
  const pie = useMemo(() => Object.entries(src || {}).map(([name, v]: any) => ({ name, value: v.total ?? 0 })).filter((x) => x.value > 0), [src]);
  const srcRows = useMemo(() => Object.entries(src || {}).map(([name, v]: any) => ({ name, ...(v as object) })).sort((a: any, b: any) => (b.total || 0) - (a.total || 0)), [src]);
  const srcTotals = useMemo(() => {
    const t = { total: 0, follow: 0, meeting: 0, siteVisit: 0, quote: 0, notInt: 0 };
    for (const r of srcRows as any[]) {
      t.total += r.total || 0;
      t.follow += r['In Followup'] || 0;
      t.meeting += r.Meeting || 0;
      t.siteVisit += r['Site Visit'] || 0;
      t.quote += r['Quotation sent'] || 0;
      t.notInt += (r['Not Interested'] || 0) + (r['Not Interested/Spam'] || 0);
    }
    return t;
  }, [srcRows]);
  const productRows = (products?.rows || []).map((row: any) => ({
    name: row.product, total: row.total, 'In Followup': row.in_followup,
    Meeting: row.meeting, 'Site Visit': row.site_visit,
    'Quotation sent': row.quote_sent, 'Not Interested': row.not_interested,
  }));
  const productPie = productRows.filter((row: any) => row.total > 0).map((row: any) => ({ name: row.name, value: row.total }));
  const productTotals = { total: products?.totals.total ?? 0, follow: products?.totals.in_followup ?? 0,
    meeting: products?.totals.meeting ?? 0, siteVisit: products?.totals.site_visit ?? 0,
    quote: products?.totals.quote_sent ?? 0, notInt: products?.totals.not_interested ?? 0 };
  if (loading && !d) return <Spinner />;
  if (error && !d) {
    return (
      <div>
        <PageHeader title="Leads Funnel — Live Dashboard" subtitle="Status cards, source mix and product data from live database." />
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
  const lv = d.lead_value || {};
  const leadValueByProduct = (lv.by_product || []).map((r: any) => ({
    product: r.product,
    lead_value: Number(r.lead_value || 0),
  }));
  const tiles = [
    { label: 'Total Leads', value: f.total ?? d.total, bg: 'bg-[#1e3a5f]', text: 'text-white' },
    { label: 'Total Lead Value', value: inr(d.total_lead_value ?? lv.total_lead_value), bg: 'bg-[#3F6212]', text: 'text-white', isText: true },
    { label: 'In Followup', value: f.in_followup ?? 0, bg: 'bg-[#c0392b]', text: 'text-white' },
    { label: 'Meeting', value: f.meeting ?? 0, bg: 'bg-[#0284c7]', text: 'text-white' },
    { label: 'Site Visit', value: f.site_visit ?? 0, bg: 'bg-[#65A30D]', text: 'text-white' },
    { label: 'Quotation Sent', value: f.quotation_sent ?? 0, bg: 'bg-[#2F9E44]', text: 'text-white' },
    { label: 'Not Interested', value: f.not_interested ?? 0, bg: 'bg-[#7b241c]', text: 'text-white' },
    { label: 'Assigned', value: f.assigned ?? 0, bg: 'bg-[#0e7490]', text: 'text-white' },
    { label: 'New Lead', value: d.new_lead_display ?? 5, bg: 'bg-[#1c2833]', text: 'text-white' },
  ];
  return (
    <div className="space-y-5">
      <PageHeader title="Leads Funnel — Live Dashboard" subtitle="Status cards, lead value analytics, source mix and product data from live database." />
      {d.warning && (
        <div className="bg-amber-50 border border-amber-300 text-amber-800 rounded-xl px-4 py-3 text-sm">⚠ {d.warning}</div>
      )}
      <div className="grid lg:grid-cols-2 gap-5">
        <div className="space-y-5">
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
            {tiles.map((t) => (
              t.label === 'New Lead' ? (
                <button key={t.label} type="button" onClick={() => setShowLatest(true)} title="Click to view the 5 customers"
                  className={`${t.bg} ${t.text} rounded-lg px-3 py-3 shadow-sm text-left cursor-pointer hover:opacity-90 focus:outline-none focus:ring-2 focus:ring-offset-1 focus:ring-brand-400`}>
                  <div className="text-[10px] uppercase tracking-wide opacity-90 font-semibold leading-tight">{t.label} ⓘ</div>
                  <div className="text-2xl font-bold mt-1 tabular-nums">{t.value}</div>
                </button>
              ) : (
                <div key={t.label} className={`${t.bg} ${t.text} rounded-lg px-3 py-3 shadow-sm`}>
                  <div className="text-[10px] uppercase tracking-wide opacity-90 font-semibold leading-tight">{t.label}</div>
                  <div className={`${(t as any).isText ? 'text-sm sm:text-base' : 'text-2xl'} font-bold mt-1 tabular-nums break-all`}>{t.value}</div>
                </div>
              )
            ))}
          </div>
          {showLatest && (
            <div className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-4" onClick={() => setShowLatest(false)}>
              <div className="card p-6 w-full max-w-2xl" onClick={(e) => e.stopPropagation()}>
                <div className="flex items-center justify-between mb-4">
                  <h3 className="font-semibold text-graphite-900">New Lead — last 5 assigned customers</h3>
                  <button type="button" className="btn-secondary !px-2 !py-1 text-xs" onClick={() => setShowLatest(false)}>✕ Close</button>
                </div>
                {(d.latest_assigned || []).length === 0 ? <EmptyState title="No assigned customers" /> : (
                  <div className="overflow-x-auto -mx-6 px-6">
                    <table className="w-full min-w-[640px] text-sm">
                      <thead className="bg-graphite-50"><tr>
                        <th className="th">Enquiry</th><th className="th">Customer</th><th className="th">Contact / Email</th><th className="th text-center">Cars</th>
                        <th className="th">Employee</th><th className="th">Assigned</th>
                      </tr></thead>
                      <tbody>
                        {(d.latest_assigned || []).map((l: any) => (
                          <tr key={l.lead_id} className="hover:bg-brand-50/50">
                            <td className="td font-semibold text-brand-700 whitespace-nowrap"><Link to={`/leads/${l.lead_id}`}>{l.enquiry_number}</Link></td>
                            <td className="td">{l.customer_name}</td>
                            <td className="td">
                              <div className="whitespace-nowrap">{l.contact_number || '—'}</div>
                              <div className="text-xs mt-0.5 break-all">{l.email ? <a className="text-brand-700 hover:underline" href={`mailto:${l.email}`}>{l.email}</a> : <span className="text-graphite-400">No email</span>}</div>
                            </td>
                            <td className="td text-center">{l.quantity_raw || '—'}</td>
                            <td className="td">{l.employee}</td>
                            <td className="td whitespace-nowrap">{l.assigned_date}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            </div>
          )}
          <div className="bg-graphite-100 text-graphite-700 rounded-lg px-3 py-2 text-sm flex justify-between">
            <span className="font-medium">Other / Unmapped status</span>
            <span className="font-bold tabular-nums">{f.other ?? 0}</span>
          </div>

          <Card title="Leads by Source">
            <div className="overflow-x-auto -mx-5 px-5">
              <table className="w-full min-w-[640px] text-sm text-center">
                <thead>
                  <tr className="bg-[#0e7490] text-white">
                    <th className="th !text-white !bg-transparent !text-center">Source</th>
                    <th className="th !text-white !bg-transparent !text-center">Total Leads</th>
                    <th className="th !text-white !bg-transparent !text-center">In Followup</th>
                    <th className="th !text-white !bg-transparent !text-center">Meeting</th>
                    <th className="th !text-white !bg-transparent !text-center">Site Visit</th>
                    <th className="th !text-white !bg-transparent !text-center">Quotation sent</th>
                    <th className="th !text-white !bg-transparent !text-center">Not Interested</th>
                  </tr>
                </thead>
                <tbody>
                  {srcRows.map((r: any, i: number) => (
                    <tr key={r.name} className={i % 2 ? 'bg-sky-50/60' : 'bg-white'}>
                      <td className="td font-medium text-center">{r.name}</td>
                      <td className="td font-bold text-center">{r.total}</td>
                      <td className="td text-center">{r['In Followup'] ?? 0}</td>
                      <td className="td text-center">{r.Meeting ?? 0}</td>
                      <td className="td text-center">{r['Site Visit'] ?? 0}</td>
                      <td className="td text-center">{r['Quotation sent'] ?? 0}</td>
                      <td className="td text-center">{(r['Not Interested'] ?? 0) + (r['Not Interested/Spam'] ?? 0)}</td>
                    </tr>
                  ))}
                  {srcRows.length > 0 && (
                    <tr className="bg-graphite-100 font-bold">
                      <td className="td text-center">TOTAL</td>
                      <td className="td text-center">{srcTotals.total}</td>
                      <td className="td text-center">{srcTotals.follow}</td>
                      <td className="td text-center">{srcTotals.meeting}</td>
                      <td className="td text-center">{srcTotals.siteVisit}</td>
                      <td className="td text-center">{srcTotals.quote}</td>
                      <td className="td text-center">{srcTotals.notInt}</td>
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
        </div>
      </div>
      <div className="grid xl:grid-cols-[1.4fr_1fr] gap-5">
        <Card title="Leads by Product">
            <div className="overflow-x-auto -mx-5 px-5">
              <table className="w-full min-w-[640px] text-sm text-center">
                <thead>
                  <tr className="bg-[#0e7490] text-white">
                    <th className="th !text-white !bg-transparent !text-center">Product</th>
                    <th className="th !text-white !bg-transparent !text-center">Total Leads</th>
                    <th className="th !text-white !bg-transparent !text-center">In Followup</th>
                    <th className="th !text-white !bg-transparent !text-center">Meeting</th>
                    <th className="th !text-white !bg-transparent !text-center">Site Visit</th>
                    <th className="th !text-white !bg-transparent !text-center">Quotation sent</th>
                    <th className="th !text-white !bg-transparent !text-center">Not Interested</th>
                  </tr>
                </thead>
                <tbody>
                  {productRows.map((r: any, i: number) => (
                    <tr key={r.name} className={i % 2 ? 'bg-sky-50/60' : 'bg-white'}>
                      <td className="td font-medium text-center">{r.name}</td>
                      <td className="td font-bold text-center">{r.total}</td>
                      <td className="td text-center">{r['In Followup'] ?? 0}</td>
                      <td className="td text-center">{r.Meeting ?? 0}</td>
                      <td className="td text-center">{r['Site Visit'] ?? 0}</td>
                      <td className="td text-center">{r['Quotation sent'] ?? 0}</td>
                      <td className="td text-center">{(r['Not Interested'] ?? 0) + (r['Not Interested/Spam'] ?? 0)}</td>
                    </tr>
                  ))}
                  {productRows.length > 0 && (
                    <tr className="bg-graphite-100 font-bold">
                      <td className="td text-center">TOTAL</td>
                      <td className="td text-center">{productTotals.total}</td>
                      <td className="td text-center">{productTotals.follow}</td>
                      <td className="td text-center">{productTotals.meeting}</td>
                      <td className="td text-center">{productTotals.siteVisit}</td>
                      <td className="td text-center">{productTotals.quote}</td>
                      <td className="td text-center">{productTotals.notInt}</td>
                    </tr>
                  )}
                </tbody>
              </table>
              {productRows.length === 0 && <EmptyState title="No product data" hint="Import leads to populate the funnel." />}
            </div>
          </Card>
                  <Card title="Leads by Product">
            {productPie.length === 0 ? <EmptyState title="No data" /> : (
              <div className="h-80">
                <ResponsiveContainer>
                  <PieChart>
                    <Pie data={productPie} dataKey="value" nameKey="name" outerRadius={110} label={({ percent }) => `${(((percent ?? 0)) * 100).toFixed(0)}%`}>
                      {productPie.map((e: any, i: number) => <Cell key={e.name} fill={COLORS[i % COLORS.length]} />)}
                    </Pie>
                    <Tooltip /><Legend />
                  </PieChart>
                </ResponsiveContainer>
              </div>
            )}
          </Card>
      </div>
      <Card title="Customer quotation values">
        {(d?.quoted_customers || []).length === 0 ? <EmptyState title="No quotation values recorded" /> : (
          <div className="overflow-auto max-h-96">
            <table className="w-full text-sm">
              <thead><tr><th className="th">Enquiry Number</th><th className="th">Customer name</th><th className="th">Employee</th><th className="th text-right">Quotation value</th></tr></thead>
              <tbody>{d.quoted_customers.map((lead: any) => <tr key={lead.lead_id}>
                <td className="td"><Link className="text-brand-700 hover:underline" to={`/leads/${lead.lead_id}`}>{lead.enquiry_number}</Link></td>
                <td className="td">{lead.customer_name}</td><td className="td">{lead.employee || '—'}</td>
                <td className="td text-right">{inr(lead.quotation_value)}</td>
              </tr>)}</tbody>
            </table>
          </div>
        )}
      </Card>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
        {[
          { label: 'Total Lead Value', value: inr(d.total_lead_value ?? lv.total_lead_value) },
          { label: 'Total Cars', value: Number(lv.total_cars || 0).toLocaleString('en-IN') },
          { label: 'Average Lead Value', value: inr(lv.average_lead_value) },
          { label: 'Valued Leads', value: lv.total_leads ?? d.total ?? 0 },
        ].map((k) => (
          <div key={k.label} className="card p-4 text-center">
            <div className="text-lg sm:text-xl font-bold text-graphite-900 tabular-nums">{k.value}</div>
            <div className="text-xs text-graphite-500 uppercase tracking-wide mt-1">{k.label}</div>
          </div>
        ))}
      </div>
      <Card title="Lead Value by Product">
        {leadValueByProduct.every((r: any) => !r.lead_value) ? (
          <EmptyState title="No lead values yet" hint="Set product and number of cars on leads to populate this chart." />
        ) : (
          <div className="h-80">
            <ResponsiveContainer>
              <BarChart data={leadValueByProduct} margin={{ top: 8, right: 12, left: 8, bottom: 64 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                <XAxis dataKey="product" interval={0} angle={-28} textAnchor="end" height={70} tick={{ fontSize: 10 }} />
                <YAxis tick={{ fontSize: 11 }} tickFormatter={(v) => `₹${Number(v).toLocaleString('en-IN', { notation: 'compact' })}`} />
                <Tooltip formatter={(v: any) => inr(v)} />
                <Bar dataKey="lead_value" name="Lead Value" fill="#3F6212" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
      </Card>
    </div>
  );
}

/* ================= EMPLOYEE DASHBOARD (personal, assigned leads only) ================= */
const TODO_STRIKE_MS = 24 * 60 * 60 * 1000;
const TODO_CAP = 500;

function todoState(l: any, now: number): 'pending' | 'struck' | 'gone' {
  if (!l.first_contact_at) return 'pending';
  const t = Date.parse(l.first_contact_at);
  if (Number.isNaN(t)) return 'pending';
  return now - t < TODO_STRIKE_MS ? 'struck' : 'gone';
}

function hoursAgo(ts: string, now: number) {
  const h = Math.floor((now - Date.parse(ts)) / 3600000);
  if (h < 1) return 'just now';
  if (h === 1) return '1h ago';
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

function TodoRow({ lead: l, state, leaving, statusLabel, now }: {
  lead: any; state: 'pending' | 'struck'; leaving?: boolean; statusLabel: string; now: number;
}) {
  const done = state === 'struck';
  return (
    <li className={`todo-row flex items-start gap-3 px-1 py-3 ${done && leaving ? 'todo-leaving' : ''}`}>
      <span className={`mt-0.5 w-5 h-5 rounded-full border-2 flex items-center justify-center text-xs shrink-0 ${done ? 'bg-[#2F9E44] border-[#2F9E44] text-white' : 'border-graphite-300 text-transparent'}`}>✓</span>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5">
          <Link to={`/leads/${l.id}`} className={`font-semibold text-brand-700 hover:underline ${done ? 'todo-strike' : ''}`}>{l.customer_name || '—'}</Link>
          <span className="text-xs text-graphite-400">{l.enquiry_number}</span>
          {done ? (
            <span className="text-xs font-medium text-emerald-700">✓ Contacted · {l.first_contact_method || 'Call'} · {hoursAgo(l.first_contact_at, now)}</span>
          ) : (
            <span className="text-[11px] font-semibold uppercase tracking-wide text-amber-700 bg-amber-50 ring-1 ring-amber-200 px-1.5 py-px rounded">New lead</span>
          )}
        </div>
        <div className="text-sm text-graphite-600 mt-0.5 flex flex-wrap gap-x-4 gap-y-0.5">
          <span>📞 {l.contact_number ? <a className="text-brand-700 hover:underline" href={`tel:${String(l.contact_number).replace(/\s/g, '')}`}>{l.contact_number}</a> : '—'}</span>
          <span>✉️ {l.email ? <a className="text-brand-700 hover:underline" href={`mailto:${l.email}`}>{l.email}</a> : <span className="text-graphite-400">No email</span>}</span>
          <span>🚗 {(l.quantity_raw || l.cars) ? `${l.quantity_raw || l.cars} cars` : '—'}</span>
          {l.company_name && <span>🏢 {l.company_name}</span>}
          {l.city && <span>📍 {l.city}</span>}
          {l.sla_deadline && !done && <span>⏱ Contact by {fmtDT(l.sla_deadline)}</span>}
        </div>
      </div>
      <div className="shrink-0 flex flex-col items-end gap-1">
        <StatusBadge value={statusLabel} />
        <SlaBadge value={l.sla_state} />
      </div>
    </li>
  );
}

export function EmployeeDashboard() {
  const [d, setD] = useState<any>(null);
  const [todos, setTodos] = useState<any[]>([]);
  const [truncated, setTruncated] = useState(false);
  const [leaving, setLeaving] = useState<string[]>([]);
  const [notes, setNotes] = useState<any[]>([]);
  const [masters, setMasters] = useState<any>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [now, setNow] = useState(() => Date.now());
  const userName = localStorage.getItem('user_name') || 'there';
  const load = () => {
    setLoading(true); setError('');
    api.get('/masters').then((r) => setMasters(r.data)).catch(() => {});
    const dashP = api.get('/dashboard').then(
      (r) => setD(r.data),
      (e: any) => setError(e?.response?.data?.detail || 'Failed to load your dashboard. Check backend / login again.'),
    );
    const notesP = api.get('/notifications').then(
      (r) => setNotes(Array.isArray(r.data) ? r.data.slice(0, 5) : []),
      () => {},
    );
    // Two-step fetch so the to-do queue covers ALL assigned customers, not just page 1.
    const queueP = api.get('/leads', { params: { page: 1, size: 1 } }).then((r) => {
      const totalCount = r.data.total ?? 0;
      const full = Math.min(Math.max(totalCount, 1), TODO_CAP);
      setTruncated(totalCount > TODO_CAP);
      return api.get('/leads', { params: { page: 1, size: full } });
    }).then(
      (r) => setTodos(r.data.items || []),
      () => setError('Failed to load your to-dos. Check your connection.'),
    );
    Promise.allSettled([dashP, notesP, queueP]).finally(() => setLoading(false));
  };
  useEffect(() => { load(); }, []);
  useEffect(() => subscribeLeadUpdates(() => load()), []);
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 60000);
    return () => clearInterval(t);
  }, []);
  const { pending, struck } = useMemo(() => {
    const p: any[] = []; const s: any[] = [];
    for (const l of todos) {
      const st = todoState(l, now);
      if (st === 'pending') p.push(l);
      else if (st === 'struck') s.push(l);
    }
    p.sort((a, b) => String(a.sla_deadline || 'zzz').localeCompare(String(b.sla_deadline || 'zzz')));
    s.sort((a, b) => Date.parse(b.first_contact_at) - Date.parse(a.first_contact_at));
    return { pending: p, struck: s };
  }, [todos, now]);
  // Drop struck rows once they cross the 24h mark, with a fade/slide-out first.
  useEffect(() => {
    const timers: ReturnType<typeof setTimeout>[] = [];
    for (const l of struck) {
      const ms = Date.parse(l.first_contact_at) + TODO_STRIKE_MS - Date.now();
      if (ms <= 0) {
        setTodos((cur) => (cur.some((x) => x.id === l.id) ? cur.filter((x) => x.id !== l.id) : cur));
      } else if (ms < 2147483647) {
        timers.push(setTimeout(() => {
          setLeaving((cur) => (cur.includes(l.id) ? cur : [...cur, l.id]));
          timers.push(setTimeout(() => {
            setTodos((cur) => cur.filter((x) => x.id !== l.id));
            setLeaving((cur) => cur.filter((id) => id !== l.id));
          }, 500));
        }, ms));
      }
    }
    return () => { timers.forEach(clearTimeout); };
  }, [struck]);
  if (loading && !d) return <Spinner />;
  if (error && !d) {
    return (
      <div>
        <PageHeader title={`Hello, ${userName}`} subtitle="Your assigned leads, follow-ups and SLA alerts." />
        <div className="card p-8 text-center">
          <p className="font-medium text-graphite-700">Could not load your dashboard</p>
          <p className="text-sm text-graphite-500 mt-1">{error}</p>
          <button className="btn-primary mt-4" onClick={load}>Retry</button>
        </div>
      </div>
    );
  }
  if (!d) return <Spinner />;
  const f = d.funnel || {};
  const statusName = (sid?: string) => masters?.statuses?.find((s: any) => s.id === sid)?.name ?? 'Assigned';
  const overduePending = pending.filter((l: any) => l.sla_state === 'OVERDUE').slice(0, 5);
  const recent = todos.slice(0, 5);
  const tiles = [
    { label: 'My assigned leads', value: d.total ?? 0, bg: 'bg-[#1e3a5f]', hint: 'Assigned to me' },
    { label: 'Needs first contact', value: d.needs_first_contact ?? 0, bg: 'bg-[#c0392b]', hint: 'Speak to customer' },
    { label: 'SLA overdue', value: d.sla_overdue ?? 0, bg: 'bg-[#7b241c]', hint: 'Act now' },
    { label: 'Contact done', value: d.contacted ?? 0, bg: 'bg-[#2F9E44]', hint: 'First contact recorded' },
    { label: 'In Followup', value: f.in_followup ?? 0, bg: 'bg-[#0e7490]', hint: 'My pipeline' },
    { label: 'Converted', value: f.converted ?? 0, bg: 'bg-[#65A30D]', hint: 'My wins' },
  ];
  return (
    <div className="space-y-5">
      <PageHeader title={`Hello, ${userName}`} subtitle="Your assigned leads, follow-ups and SLA alerts." actions={
        <Link to="/leads" className="btn-primary">View all my leads →</Link>
      } />
      {d.warning && (
        <div className="bg-amber-50 border border-amber-300 text-amber-800 rounded-xl px-4 py-3 text-sm">⚠ {d.warning}</div>
      )}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2">
        {tiles.map((t) => (
          <div key={t.label} className={`${t.bg} text-white rounded-lg px-3 py-3 shadow-sm`}>
            <div className="text-[10px] uppercase tracking-wide opacity-90 font-semibold leading-tight">{t.label}</div>
            <div className="text-2xl font-bold mt-1 tabular-nums">{t.value}</div>
            <div className="text-[11px] opacity-80 mt-0.5">{t.hint}</div>
          </div>
        ))}
      </div>
      <Card title={`My to-dos — new leads (${pending.length})`} action={
        truncated
          ? <span className="text-xs text-graphite-400">showing first 500</span>
          : <Link to="/leads" className="text-xs text-brand-700 font-semibold hover:underline">All my leads →</Link>
      }>
        {pending.length === 0 && struck.length === 0 ? <EmptyState title="No pending to-dos" hint="New assigned customers will appear here." /> : (
          <ul className="divide-y divide-graphite-100 -my-1">
            {pending.map((l: any) => (
              <TodoRow key={l.id} lead={l} state="pending" statusLabel={statusName(l.status_id)} now={now} />
            ))}
            {struck.map((l: any) => (
              <TodoRow key={l.id} lead={l} state="struck" leaving={leaving.includes(l.id)} statusLabel={statusName(l.status_id)} now={now} />
            ))}
          </ul>
        )}
      </Card>
      <div className="grid lg:grid-cols-2 gap-5">
        <Card title="Needs attention — overdue SLA" action={<Link to="/leads" className="text-xs text-brand-700 font-semibold hover:underline">All my leads →</Link>}>
          {overduePending.length === 0 ? <EmptyState title="Nothing overdue" hint="All caught up on SLAs." /> : (
            <div className="overflow-x-auto -mx-5 px-5">
              <table className="w-full min-w-[560px] text-sm">
                <thead className="bg-graphite-50"><tr>
                  <th className="th">Enquiry</th><th className="th">Customer</th><th className="th">Contact / Email</th><th className="th text-center">Cars</th><th className="th">Due</th>
                </tr></thead>
                <tbody>
                  {overduePending.map((l: any) => (
                    <tr key={l.id} className="hover:bg-brand-50/50">
                      <td className="td font-semibold text-brand-700 whitespace-nowrap"><Link to={`/leads/${l.id}`}>{l.enquiry_number}</Link></td>
                      <td className="td">{l.customer_name || '—'}</td>
                      <td className="td">
                        <div className="whitespace-nowrap">{l.contact_number || '—'}</div>
                        <div className="text-xs mt-0.5 break-all">{l.email ? <a className="text-brand-700 hover:underline" href={`mailto:${l.email}`}>{l.email}</a> : <span className="text-graphite-400">No email</span>}</div>
                      </td>
                      <td className="td text-center">{l.quantity_raw || '—'}</td>
                      <td className="td whitespace-nowrap text-red-700 font-semibold tabular-nums">{fmtDT(l.sla_deadline)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
        <Card title="My recent leads" action={<Link to="/leads" className="text-xs text-brand-700 font-semibold hover:underline">All my leads →</Link>}>
          {recent.length === 0 ? <EmptyState title="No leads assigned yet" hint="New Excel imports will appear here once assigned to you." /> : (
            <div className="overflow-x-auto -mx-5 px-5">
              <table className="w-full min-w-[640px] text-sm">
                <thead className="bg-graphite-50"><tr>
                  <th className="th">Enquiry</th><th className="th">Customer</th><th className="th">Contact / Email</th><th className="th text-center">Cars</th><th className="th">Status</th><th className="th">SLA</th>
                </tr></thead>
                <tbody>
                  {recent.map((l: any) => (
                    <tr key={l.id} className="hover:bg-brand-50/50">
                      <td className="td font-semibold text-brand-700 whitespace-nowrap"><Link to={`/leads/${l.id}`}>{l.enquiry_number}</Link></td>
                      <td className="td">{l.customer_name || '—'}</td>
                      <td className="td">
                        <div className="whitespace-nowrap">{l.contact_number || '—'}</div>
                        <div className="text-xs mt-0.5 break-all">{l.email ? <a className="text-brand-700 hover:underline" href={`mailto:${l.email}`}>{l.email}</a> : <span className="text-graphite-400">No email</span>}</div>
                      </td>
                      <td className="td text-center">{l.quantity_raw || '—'}</td>
                      <td className="td"><StatusBadge value={statusName(l.status_id)} /></td>
                      <td className="td"><SlaBadge value={l.sla_state} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      </div>
      {notes.length > 0 && (
        <Card title="Alerts">
          <div className="space-y-2">
            {notes.map((n: any) => (
              <div key={n.id} className="flex gap-3 items-start bg-graphite-50 rounded-lg px-3 py-2">
                <div className="w-8 h-8 rounded-lg bg-red-100 text-red-600 flex items-center justify-center shrink-0">⚠</div>
                <div><div className="font-semibold text-sm">{n.title}</div><div className="text-sm text-graphite-600">{n.body}</div></div>
              </div>
            ))}
          </div>
        </Card>
      )}
    </div>
  );
}

/* ================= LEADS ================= */
export function Leads() {
  const role = localStorage.getItem('role') || '';
  const reviewOptions = ['A+ (Immediate)', 'A (3-6 months)', 'B (1 year)', 'C (plan stage)'];
  const [items, setItems] = useState<any[]>([]);
  const [total, setTotal] = useState(0);
  const [masters, setMasters] = useState<any>(null);
  const [search, setSearch] = useState('');
  const [status, setStatus] = useState('');
  const [source, setSource] = useState('');
  const [sla, setSla] = useState('');
  const [sort, setSort] = useState('');
  const [validationMessage, setValidationMessage] = useState('');
  const [conversionToConfirm, setConversionToConfirm] = useState<any>(null);
  const [page, setPage] = useState(1);
  const STATUS_FILTERS = ['Assigned', 'In Followup', 'Site Visit', 'Quotation sent', 'Converted', 'Not Interested'];
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [drafts, setDrafts] = useState<Record<string, { remarks: string; review: string; progress: string; quotationValue?: string }>>({});
  const [savingId, setSavingId] = useState<string | null>(null);
  const [expandedRows, setExpandedRows] = useState<Record<string, boolean>>({});
  const [followupForms, setFollowupForms] = useState<Record<string, Array<{ remarks: string; review: string; progress: string; quotationValue?: string }>>>({});
  const size = 15;
  const [liveSeq, setLiveSeq] = useState(0);
  useEffect(() => { api.get('/masters').then((r) => setMasters(r.data)).catch(() => setError('Could not load filters.')); }, []);
  useEffect(() => subscribeLeadUpdates(() => setLiveSeq((s) => s + 1)), []);
  useEffect(() => {
    const ctrl = new AbortController();
    const t = setTimeout(() => {
      setLoading(true); setError('');
      api.get('/leads', {
        params: { search, status, source, sla, page, size, ...(sort ? { sort } : {}) },
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
  }, [search, status, source, sla, sort, page, liveSeq]);
  const nameOf = (kind: 'statuses' | 'sources' | 'employees' | 'products', id?: string) =>
    masters?.[kind]?.find((x: any) => x.id === id)?.name ?? '—';
  const statusLabel = (lead: any) => {
    const selectedStatus = nameOf('statuses', role === 'EMPLOYEE' ? (draftFor(lead).progress || lead.status_id) : lead.status_id);
    return selectedStatus === 'New Lead' && lead.primary_employee_id ? 'Assigned' : selectedStatus;
  };
  const actionOptions = ['In Followup', 'Meeting', 'Site Visit', 'Quotation sent', 'Converted', 'Not Interested'];
  const draftFor = (lead: any) => drafts[lead.id] || { remarks: lead.employee_remarks || '', review: lead.customer_review || '', progress: lead.employee_remarks ? lead.status_id : '', quotationValue: lead.quotation_value ?? '0' };
  const isConvertedLocked = (lead: any) => lead.sla_state === 'COMPLETED' && nameOf('statuses', lead.status_id) === 'Converted';
  const saveLead = async (lead: any, done = false, conversionConfirmed = false) => {
    if (role === 'EMPLOYEE' && isConvertedLocked(lead)) {
      setValidationMessage('Converted leads cannot be edited or reopened.');
      return;
    }
    const draft = draftFor(lead);
    const reopening = !done && lead.sla_state === 'COMPLETED';
    const actionName = nameOf('statuses', draft.progress);
    if (!draft.remarks.trim() || !draft.review || !actionOptions.includes(actionName)) {
      setValidationMessage('Please fill Remarks, Category, and Work Action before saving or completing this lead.');
      return;
    }
    if (actionName === 'Quotation sent' && draft.quotationValue && !/^\d+$/.test(String(draft.quotationValue).trim())) {
      setValidationMessage('Enter a whole-number quotation value (no decimals).');
      return;
    }
    if (done && actionName === 'Converted' && !conversionConfirmed) {
      setConversionToConfirm(lead);
      return;
    }
    setConversionToConfirm(null);
    setSavingId(lead.id);
    try {
      const { data } = await api.post(`/leads/${lead.id}/status`, {
        new_status_id: draft.progress || lead.status_id,
        reason: draft.remarks.trim() || 'Lead completed',
        method: 'Call',
        customer_review: draft.review,
        quotation_value: actionName === 'Quotation sent' && draft.quotationValue ? draft.quotationValue : undefined,
        sla_state: done ? 'COMPLETED' : reopening ? 'PENDING' : lead.sla_state,
      });
      setItems((current) => current.map((item) => item.id === lead.id
        ? { ...item, status_id: draft.progress || item.status_id, employee_remarks: draft.remarks.trim() || 'Lead completed', customer_review: draft.review, quotation_value: actionName === 'Quotation sent' && draft.quotationValue ? draft.quotationValue : item.quotation_value, sla_state: data.sla_state, work_history: data.activity_recorded === false ? item.work_history : [...(item.work_history || []), { remarks: draft.remarks.trim(), category: draft.review, quotation_value: actionName === 'Quotation sent' ? draft.quotationValue : null, work_action: nameOf('statuses', draft.progress || item.status_id) }] }
        : item));
      setDrafts((current) => { const next = { ...current }; delete next[lead.id]; return next; });
      setExpandedRows((current) => ({ ...current, [lead.id]: false }));
      if (done) {
        setFollowupForms((current) => ({ ...current, [lead.id]: [] }));
      }
      if (reopening) setExpandedRows((current) => ({ ...current, [lead.id]: true }));
    } catch (e: any) {
      setValidationMessage(e?.response?.data?.detail || 'Could not save lead remarks');
    } finally { setSavingId(null); }
  };
  const addFollowUp = (lead: any) => {
    setFollowupForms((current) => ({
      ...current,
      [lead.id]: [...(current[lead.id] || []), { remarks: '', review: '', progress: '', quotationValue: '0' }],
    }));
  };
  const closeFollowUp = (lead: any) => {
    setFollowupForms((current) => ({ ...current, [lead.id]: (current[lead.id] || []).slice(0, -1) }));
  };
  const saveFollowup = async (lead: any, index: number) => {
    const form = followupForms[lead.id]?.[index];
    const actionName = form ? nameOf('statuses', form.progress) : '';
    if (!form?.remarks.trim() || !form.review || !actionOptions.includes(actionName)) {
      setValidationMessage('Please fill Remarks, Category, and Work Action for this follow-up.');
      return;
    }
    if (actionName === 'Quotation sent' && form.quotationValue && !/^\d+$/.test(String(form.quotationValue).trim())) {
      setValidationMessage('Enter a whole-number quotation value (no decimals).');
      return;
    }
    setSavingId(lead.id);
    try {
      await api.post(`/leads/${lead.id}/status`, { new_status_id: form.progress || lead.status_id, reason: form.remarks.trim(), method: 'Call', customer_review: form.review, quotation_value: actionName === 'Quotation sent' && form.quotationValue ? form.quotationValue : undefined, sla_state: lead.sla_state });
      setItems((current) => current.map((item) => item.id === lead.id ? { ...item, status_id: form.progress || item.status_id, employee_remarks: form.remarks.trim(), customer_review: form.review, quotation_value: actionName === 'Quotation sent' && form.quotationValue ? form.quotationValue : item.quotation_value, work_history: [...(item.work_history || []), { remarks: form.remarks.trim(), category: form.review, quotation_value: actionName === 'Quotation sent' ? form.quotationValue : null, work_action: nameOf('statuses', form.progress || item.status_id) }] } : item));
      setFollowupForms((current) => ({ ...current, [lead.id]: (current[lead.id] || []).filter((_, i) => i !== index) }));
    } catch (e: any) { setValidationMessage(e?.response?.data?.detail || 'Could not save follow-up'); }
    finally { setSavingId(null); }
  };
  return (
    <div className="min-w-0 max-w-full">
      <PageHeader title="Leads" subtitle={`${total} lead${total === 1 ? '' : 's'} found · Excel import only · every customer auto-assigned round-robin`} />
      <div className="card p-4 mb-4 grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-[2fr_1fr_1fr_1fr_1fr]">
        <input className="input min-w-0" placeholder="🔍 Search name, phone, enquiry…" value={search} onChange={(e) => { setSearch(e.target.value); setPage(1); }} />
        <select className="input min-w-0" value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }}>
          <option value="">All statuses</option>
          {STATUS_FILTERS.map((name) => masters?.statuses?.find((s: any) => s.name === name)).filter(Boolean).map((s: any) => (
            <option key={s.id} value={s.id}>{s.name}</option>
          ))}
        </select>
        <select className="input min-w-0" value={source} onChange={(e) => { setSource(e.target.value); setPage(1); }}>
          <option value="">All sources</option>
          {masters?.sources?.map((s: any) => <option key={s.id} value={s.id}>{s.name}</option>)}
        </select>
        <select className="input min-w-0" value={sla} onChange={(e) => { setSla(e.target.value); setPage(1); }}>
          <option value="">Lead status</option>
          <option value="PENDING">Pending</option>
          <option value="COMPLETED">Completed</option>
          <option value="NOT_INTERESTED">Not Interested</option>
        </select>
        <select className="input min-w-0" value={sort} onChange={(e) => { setSort(e.target.value); setPage(1); }}>
          <option value="">Sort: Recent</option>
          <option value="lead_value_desc">Lead Value ↓</option>
          <option value="lead_value">Lead Value ↑</option>
        </select>
      </div>
      {error && <div className="bg-red-50 border border-red-200 text-red-700 text-sm rounded-xl px-4 py-3 mb-4">{error}</div>}
      <div className="card min-w-0 overflow-hidden">
        {loading ? <Spinner /> : items.length === 0 ? <EmptyState title={error ? 'Could not load leads' : 'No leads match'} hint={error ? 'Check your connection and retry.' : 'Import the Excel tracker or adjust filters.'} /> : (
          <div className="relative isolate w-full overflow-x-auto">
            <table className="w-full table-fixed min-w-[2100px] border-separate border-spacing-0 text-sm [&_td]:border-graphite-100 [&_td]:break-words">
              <thead className="bg-graphite-50"><tr>
                <th className="th whitespace-nowrap align-top w-[144px] sm:w-[160px] !px-2 sm:!px-4 !text-[10px] sm:!text-xs sticky left-0 z-20 bg-graphite-50">Enquiry Number</th>
                <th className="th whitespace-nowrap align-top w-[144px] sm:w-[200px] !px-2 sm:!px-4 !text-[10px] sm:!text-xs sticky left-[144px] sm:left-[160px] z-20 bg-graphite-50 shadow-[4px_0_8px_-4px_rgba(0,0,0,0.15)]">Customer name</th>
                <th className="th whitespace-nowrap align-top w-[160px]">Company</th>
                <th className="th whitespace-nowrap align-top w-[120px]">City</th>
                <th className="th whitespace-nowrap align-top w-[170px]">Contact / Email</th>
                {role === 'EMPLOYEE' && <th className="th whitespace-nowrap align-top w-[100px] text-center">Email</th>}
                <th className="th whitespace-nowrap align-top w-[90px] text-center">Cars</th>
                <th className="th whitespace-nowrap align-top w-[180px]">Product</th>
                <th className="th whitespace-nowrap align-top w-[210px]">Category</th>
                <th className="th whitespace-nowrap align-top w-[280px]">Remarks</th>
                <th className="th whitespace-nowrap align-top w-[210px]">Progress</th>
                <th className="th whitespace-nowrap align-top w-[140px]">Source</th>
                <th className="th whitespace-nowrap align-top w-[170px] text-center">Current status</th>
                <th className="th whitespace-nowrap align-top w-[160px] text-center">Lead status</th>
                {role !== 'EMPLOYEE' && <th className="th whitespace-nowrap align-top w-[170px]">Employee</th>}
                <th className="th whitespace-nowrap align-top w-[130px] text-right">Lead Value</th>
                <th className="th text-right whitespace-nowrap align-top w-[180px]">Quotation value</th>
              </tr></thead>
              <tbody>
                {items.map((l) => (
                  <tr key={l.id} className={leadRowColour(l, nameOf('statuses', l.status_id))}
                    onClickCapture={(event) => {
                      if (role === 'EMPLOYEE' && isConvertedLocked(l) && (event.target as HTMLElement).closest('button, select, textarea')) {
                        event.preventDefault(); event.stopPropagation();
                        setValidationMessage('Converted leads cannot be edited or reopened.');
                      }
                    }}>

                    <td className={`td align-top !px-2 sm:!px-4 sticky left-0 z-10 font-semibold text-brand-700 whitespace-nowrap ${leadRowColour(l, nameOf('statuses', l.status_id))}`}><Link to={`/leads/${l.id}`}>{l.enquiry_number}</Link></td>
                    <td className={`td align-top !px-2 sm:!px-4 sticky left-[144px] sm:left-[160px] z-10 shadow-[4px_0_8px_-4px_rgba(0,0,0,0.15)] ${leadRowColour(l, nameOf('statuses', l.status_id))}`}><div className="font-medium text-graphite-900">{l.customer_name || '—'}</div></td>
                    <td className="td align-top">{l.company_name || '—'}</td>
                    <td className="td align-top">{l.city || '—'}</td>
                    <td className="td align-top">
                      <div className="whitespace-nowrap">{l.contact_number || '—'}</div>
                      <div className="text-xs mt-0.5 break-all">
                        {l.email
                          ? <button type="button" className="text-brand-700 hover:underline text-left break-all" onClick={() => openCustomerGmail(l.email, l.enquiry_number)}>{l.email}</button>
                          : <span className="text-graphite-400">No email</span>}
                      </div>
                    </td>
                    {role === 'EMPLOYEE' && (
                      <td className="td align-top text-center">
                        <button
                          type="button"
                          className="btn-secondary !px-2 !py-1 text-xs"
                          disabled={!l.email}
                          title={l.email ? `Open Gmail web compose to ${l.email}` : 'No customer email on this lead'}
                          onClick={() => openCustomerGmail(l.email, l.enquiry_number)}
                        >
                          ✉️ Email
                        </button>
                      </td>
                    )}
                    <td className="td align-top text-center whitespace-nowrap">{l.quantity_raw || '—'}</td>
                    <td className="td align-top">{prodName(l, nameOf)}</td>
                    <td className="td align-top">
                      {role === 'EMPLOYEE' && (expandedRows[l.id] || !l.employee_remarks) ? (
                        <select className="input text-xs" disabled={l.sla_state === 'COMPLETED'} value={draftFor(l).review}
                          onChange={(e) => setDrafts((current) => ({ ...current, [l.id]: { ...draftFor(l), review: e.target.value } }))}>
                          <option value="">Select category…</option>
                          {reviewOptions.map((option) => <option key={option} value={option}>{option}</option>)}
                        </select>
                      ) : (<div className="max-h-[110px] overflow-y-auto space-y-2 pr-1 text-sm leading-5">{l.work_history?.length ? l.work_history.map((entry: any, index: number) => <div key={`category-${index}`} className="text-sm"><b>{index + 1}.</b> {entry.category || '—'}</div>) : (l.customer_review || '—')}</div>)}
                      {role === 'EMPLOYEE' && (expandedRows[l.id] || !l.employee_remarks) && (l.sla_state === 'COMPLETED'
                        ? <span className="inline-block mt-1 text-xs font-semibold text-emerald-700">✓ Completed — reopen to edit</span>
                        : <button type="button" className="btn-primary !px-2 !py-1 text-xs mt-1" disabled={savingId === l.id || !draftFor(l).remarks.trim()} onClick={() => saveLead(l)}>{savingId === l.id ? 'Saving…' : 'Save'}</button>)}
                      {role === 'EMPLOYEE' && (followupForms[l.id] || []).map((form, index) => <div key={`category-${index}`} className="mt-2"><select className="input text-xs" value={form.review} onChange={(e) => setFollowupForms((current) => ({ ...current, [l.id]: current[l.id].map((item, i) => i === index ? { ...item, review: e.target.value } : item) }))}><option value="">Select category…</option>{reviewOptions.map((option) => <option key={option} value={option}>{option}</option>)}</select><button type="button" className="btn-primary !px-2 !py-1 text-xs mt-1" disabled={savingId === l.id || !form.remarks.trim()} onClick={() => saveFollowup(l, index)}>{savingId === l.id ? 'Saving…' : `Save follow-up ${index + 2}`}</button></div>)}
                    </td>
                    <td className="td align-top">
                      {role === 'EMPLOYEE' && (expandedRows[l.id] || !l.employee_remarks) ? (
                        <textarea className="input min-h-[64px] text-xs" disabled={l.sla_state === 'COMPLETED'} placeholder="Enter customer conversation remarks…"
                          value={draftFor(l).remarks}
                          onChange={(e) => setDrafts((current) => ({ ...current, [l.id]: { ...draftFor(l), remarks: e.target.value } }))} />
                      ) : (<div className="max-h-[110px] overflow-y-auto space-y-2 pr-1 text-sm leading-5">{l.work_history?.length ? l.work_history.map((entry: any, index: number) => <div key={`remark-${index}`} className="text-sm whitespace-pre-wrap"><b>{index + 1}.</b> {entry.remarks}</div>) : <span className="block whitespace-pre-wrap" title={l.employee_remarks || ''}>{l.employee_remarks || '—'}</span>}</div>)}
                      {role === 'EMPLOYEE' && (followupForms[l.id] || []).map((form, index) => <textarea key={`remark-${index}`} className="input min-h-[64px] text-xs mt-2" placeholder={`Follow-up ${index + 2} remarks…`} value={form.remarks} onChange={(e) => setFollowupForms((current) => ({ ...current, [l.id]: current[l.id].map((item, i) => i === index ? { ...item, remarks: e.target.value } : item) }))} />)}
                    </td>
                    <td className="td align-top">
                      {role === 'EMPLOYEE' && (expandedRows[l.id] || !l.employee_remarks) ? (
                        <select className="input text-xs" disabled={l.sla_state === 'COMPLETED'} value={draftFor(l).progress}
                          onChange={(e) => setDrafts((current) => ({ ...current, [l.id]: { ...draftFor(l), progress: e.target.value } }))}>
                          <option value="">Select category…</option>
                          {actionOptions.map((option) => {
                            const match = masters?.statuses?.find((s: any) => s.name.toLowerCase() === option.toLowerCase());
                            return <option key={option} value={match?.id || l.status_id}>{option}</option>;
                          })}
                        </select>
                      ) : (<div className="max-h-[110px] overflow-y-auto space-y-2 pr-1 text-sm leading-5">                      {l.work_history?.length ? l.work_history.map((entry: any, index: number) => <div key={`action-${index}`} className="text-sm"><b>{index + 1}.</b> {entry.work_action || '—'}{entry.quotation_value != null && entry.quotation_value !== '' && <span className="block text-xs">Quotation value: {inr(entry.quotation_value)}</span>}</div>) : nameOf('statuses', l.status_id)}</div>)}
                      {role === 'EMPLOYEE' && (expandedRows[l.id] || !l.employee_remarks) && nameOf('statuses', draftFor(l).progress) === 'Quotation sent' && (
                        <label className="block text-xs text-graphite-600 mt-2">Quotation value
                          <input type="number" min="0" step="1" inputMode="numeric" className="input text-xs mt-1" placeholder="Whole rupees only" disabled={l.sla_state === 'COMPLETED'} value={draftFor(l).quotationValue ?? ''} onChange={(e) => setDrafts((current) => ({ ...current, [l.id]: { ...draftFor(l), quotationValue: e.target.value.replace(/[^\d]/g, '') } }))} />
                        </label>
                      )}
                      {role === 'EMPLOYEE' && (followupForms[l.id] || []).map((form, index) => <div key={`progress-${index}`}><select className="input text-xs mt-2" value={form.progress} onChange={(e) => setFollowupForms((current) => ({ ...current, [l.id]: current[l.id].map((item, i) => i === index ? { ...item, progress: e.target.value } : item) }))}><option value="">Select category…</option>{actionOptions.map((option) => { const match = masters?.statuses?.find((s: any) => s.name.toLowerCase() === option.toLowerCase()); return <option key={option} value={match?.id || l.status_id}>{option}</option>; })}</select>{nameOf('statuses', form.progress) === 'Quotation sent' && <label className="block text-xs text-graphite-600 mt-2">Quotation value<input type="number" min="0" step="1" inputMode="numeric" className="input text-xs mt-1" placeholder="Whole rupees only" value={form.quotationValue ?? ''} onChange={(e) => setFollowupForms((current) => ({ ...current, [l.id]: current[l.id].map((item, i) => i === index ? { ...item, quotationValue: e.target.value.replace(/[^\d]/g, '') } : item) }))} /></label>}</div>)}
                      {role === 'EMPLOYEE' && <button type="button" className="btn-secondary !px-2 !py-1 text-base font-bold ml-2" disabled={l.sla_state === 'COMPLETED'} onClick={() => (followupForms[l.id]?.length ? closeFollowUp(l) : addFollowUp(l))} title={followupForms[l.id]?.length ? 'Close unsaved follow-up' : 'Add follow-up'}>{followupForms[l.id]?.length ? '×' : '+'}</button>}
                    </td>
                    <td className="td align-top">{l.source_name || nameOf('sources', l.source_id)}</td>
                    <td className="td align-top text-center"><StatusBadge value={statusLabel(l)} /></td>
                    <td className="td align-top text-center">
                      <SlaBadge value={l.sla_state} />
                      {role === 'EMPLOYEE' && (
                        <div className="mt-2">
                          {isConvertedLocked(l) ? (
                            <span className="text-xs font-semibold text-emerald-700">✓ Done</span>
                          ) : (
                            <button type="button" className={`btn-secondary !px-3 !py-1 text-xs ${l.sla_state === 'COMPLETED' ? '!bg-amber-100 !text-amber-900 !border-amber-300 hover:!bg-amber-200' : '!bg-blue-600 !text-white !border-blue-600 hover:!bg-blue-700'}`}
                              disabled={savingId === l.id}
                              onClick={() => saveLead(l, l.sla_state !== 'COMPLETED')}>
                              {savingId === l.id ? 'Saving…' : l.sla_state === 'COMPLETED' ? 'Reopen' : 'Done'}
                            </button>
                          )}
                        </div>
                      )}
                    </td>
                    {role !== 'EMPLOYEE' && <td className="td align-top">{l.primary_employee_id ? nameOf('employees', l.primary_employee_id) : <span className="text-amber-700 text-xs font-medium">Pending</span>}</td>}
                    <td className="td align-top text-right whitespace-nowrap tabular-nums font-semibold text-graphite-900">{inr(l.lead_value)}</td>
                    <td className="td align-top text-right whitespace-nowrap">
                      {l.quotation_value != null && l.quotation_value !== '' ? (
                        <span className="inline-block max-w-full overflow-x-auto rounded-md border border-amber-200 bg-amber-50 px-2 py-1 text-xs font-semibold tabular-nums text-amber-900">
                          {inr(l.quotation_value).replace(/^₹/, '')}
                        </span>
                      ) : <span className="text-graphite-400">—</span>}
                    </td>
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
      {conversionToConfirm && (
        <div className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-4" onClick={() => setConversionToConfirm(null)}>
          <div role="dialog" aria-modal="true" aria-labelledby="confirm-conversion-title" className="card w-full max-w-md p-6" onClick={(e) => e.stopPropagation()} onKeyDown={(e) => { if (e.key === 'Escape') setConversionToConfirm(null); }}>
            <h3 id="confirm-conversion-title" className="text-lg font-semibold text-graphite-900">Complete converted lead?</h3>
            <p className="text-sm text-graphite-600 mt-2">Once completed, this converted lead cannot be edited or reopened. Select Cancel to recheck the details, or OK to complete it.</p>
            <div className="flex justify-end gap-2 mt-5">
              <button type="button" className="btn-secondary" autoFocus onClick={() => setConversionToConfirm(null)}>Cancel</button>
              <button type="button" className="btn-primary" onClick={() => saveLead(conversionToConfirm, true, true)}>OK</button>
            </div>
          </div>
        </div>
      )}
      {validationMessage && (
        <div className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-4" onClick={() => setValidationMessage('')}>
          <div className="card w-full max-w-md p-6" onClick={(e) => e.stopPropagation()}>
            <h3 className="text-lg font-semibold text-graphite-900">Complete the lead details</h3>
            <p className="text-sm text-graphite-600 mt-2">{validationMessage}</p>
            <div className="flex justify-end mt-5"><button type="button" className="btn-primary" onClick={() => setValidationMessage('')}>OK</button></div>
          </div>
        </div>
      )}
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
  const reviewOptions = ['A+ (Immediate)', 'A (3-6 months)', 'B (1 year)', 'C (plan stage)'];
  const workActionOptions = ['Assigned', 'In Followup', 'Meeting', 'Site Visit', 'Quotation sent', 'Converted', 'Not Interested'];
  const statusOf = (l: any) => {
    const s = nameOf('statuses', l.status_id);
    return s === 'New Lead' && l.primary_employee_id ? 'Assigned' : s;
  };
  const needsContact = items.filter((l) => !l.first_contact_at).length;
  const overdue = items.filter((l) => l.sla_state === 'OVERDUE').length;
  const done = items.filter((l) => !!l.first_contact_at).length;
  const workActionCounts = workActionOptions.map((label) => ({
    label,
    value: items.filter((l) => statusOf(l) === label).length,
  }));
  const reviewCounts = reviewOptions.map((label) => ({
    label,
    value: items.filter((l) => (l.customer_review || '') === label).length,
  }));
  const unreviewed = items.filter((l) => !(l.customer_review || '').trim()).length;
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
          <div className="mb-4">
            <div className="text-xs font-semibold text-graphite-600 uppercase tracking-wide mb-2">Work action</div>
            <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-2">
              {workActionCounts.map((s) => (
                <div key={s.label} className="card p-4 text-center">
                  <div className="text-2xl font-bold text-graphite-900 tabular-nums">{s.value}</div>
                  <div className="text-xs text-graphite-500 uppercase tracking-wide mt-1">{s.label}</div>
                </div>
              ))}
            </div>
          </div>
          <div className="mb-4">
            <div className="text-xs font-semibold text-graphite-600 uppercase tracking-wide mb-2">Category (A+ / A / B / C)</div>
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-2">
              {reviewCounts.map((s) => (
                <div key={s.label} className="card p-4 text-center">
                  <div className="text-2xl font-bold text-graphite-900 tabular-nums">{s.value}</div>
                  <div className="text-xs text-graphite-500 uppercase tracking-wide mt-1">{s.label}</div>
                </div>
              ))}
              <div className="card p-4 text-center">
                <div className="text-2xl font-bold text-graphite-900 tabular-nums">{unreviewed}</div>
                <div className="text-xs text-graphite-500 uppercase tracking-wide mt-1">Unreviewed</div>
              </div>
            </div>
          </div>
          <div className="card overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full min-w-[1280px]">
                <thead className="bg-graphite-50"><tr>
                  <th className="th">Enquiry</th><th className="th">Customer</th><th className="th">Company</th>
                  <th className="th">City</th><th className="th">Contact / Email</th><th className="th text-center">Cars</th><th className="th text-right">Lead Value</th><th className="th">Source</th>
                  <th className="th">Product</th><th className="th">Status</th><th className="th">SLA</th>
                  <th className="th">Due date</th>
                  <th className="th">First contact</th><th className="th">Enquiry date</th>
                </tr></thead>
                <tbody>
                  {items.map((l) => (
                    <tr key={l.id} className={leadRowColour(l, nameOf('statuses', l.status_id))}>
                      <td className="td font-semibold text-brand-700 whitespace-nowrap"><Link to={`/leads/${l.id}`}>{l.enquiry_number}</Link></td>
                      <td className="td"><div className="font-medium text-graphite-900">{l.customer_name || '—'}</div></td>
                      <td className="td">{l.company_name || '—'}</td>
                      <td className="td">{l.city || '—'}</td>
                      <td className="td">
                        <div className="whitespace-nowrap">{l.contact_number || '—'}{l.alternate_contact ? <span className="block text-xs text-graphite-400">alt: {l.alternate_contact}</span> : null}</div>
                        <div className="text-xs mt-0.5 break-all">{l.email ? <a className="text-brand-700 hover:underline" href={`mailto:${l.email}`}>{l.email}</a> : <span className="text-graphite-400">No email</span>}</div>
                      </td>
                      <td className="td text-center whitespace-nowrap">{l.quantity_raw || '—'}</td>
                      <td className="td text-right whitespace-nowrap tabular-nums font-semibold">{inr(l.lead_value)}</td>
                      <td className="td">{l.source_name || nameOf('sources', l.source_id)}</td>
                      <td className="td">{l.product_name || prodName(l, nameOf)}</td>
                      <td className="td"><StatusBadge value={l.primary_employee_id && nameOf('statuses', l.status_id) === 'New Lead' ? 'Assigned' : nameOf('statuses', l.status_id)} /></td>
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
  const [reassignReason, setReassignReason] = useState('');
  const [productId, setProductId] = useState('');
  const [cars, setCars] = useState('');
  const [busy, setBusy] = useState(false);
  const [pricingBusy, setPricingBusy] = useState(false);
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
    if (l) {
      setProductId(l.product_id || '');
      setCars(l.quantity_raw || (l.quantity_num != null ? String(l.quantity_num) : ''));
    }
  }, [l?.status_id, l?.id, l?.product_id, l?.quantity_raw, l?.quantity_num]);
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
  const selectedProduct = masters?.products?.find((p: any) => p.id === productId);
  const preview = previewLeadValue(selectedProduct?.price_per_car ?? l.price_per_car, cars);
  const needsContact = !l.first_contact_at && !!l.primary_employee_id;
  const canUpdateProgress = role === 'ADMIN' || role === 'MANAGER' || (role === 'EMPLOYEE' && !!l.primary_employee_id);
  const canEditPricing = role === 'ADMIN' || role === 'MANAGER' || (role === 'EMPLOYEE' && l.primary_employee_id);
  const rr = l.reassignment_request;
  const canRequestReassign = role === 'EMPLOYEE' && !!l.primary_employee_id && !rr;
  const canAdminReassign = role === 'ADMIN' && (l.pending_assignment || rr?.status === 'ACCEPTED');
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
    setBusy(true); setErr(''); setOkMsg('');
    try {
      await api.post(`/leads/${id}/assign`, { employee_id: assignEmp, role: 'PRIMARY' });
      setOkMsg(rr?.status === 'ACCEPTED' ? 'Lead reassigned to the selected employee' : 'Lead assigned');
      setAssignEmp('');
      reload();
    } catch (e: any) {
      setErr(e?.response?.data?.detail || 'Assign failed');
    } finally { setBusy(false); }
  };
  const requestReassign = async () => {
    if (!reassignReason.trim() || busy) return;
    setBusy(true); setErr(''); setOkMsg('');
    try {
      await api.post(`/leads/${id}/reassign-request`, { reason: reassignReason.trim() });
      setReassignReason('');
      setOkMsg('Reassignment request sent to admin');
      reload();
    } catch (e: any) {
      setErr(e?.response?.data?.detail || 'Could not send reassignment request');
    } finally { setBusy(false); }
  };
  const savePricing = async () => {
    if (!canEditPricing) return;
    setPricingBusy(true); setErr(''); setOkMsg('');
    try {
      const { data } = await api.put(`/leads/${id}`, {
        product_id: productId || null,
        quantity_raw: cars,
        lead_value: 1,
        price_per_car: 1,
        gst_amount: 1,
      });
      setL(data);
      setOkMsg('Product & lead value updated');
    } catch (e: any) {
      setErr(e?.response?.data?.detail || 'Could not save product / cars');
    } finally { setPricingBusy(false); }
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
              {role === 'EMPLOYEE' ? <SlaBadge value={l.sla_state} /> : <SlaBadge value={l.pending_assignment ? 'PENDING' : l.sla_state} />}
              {l.pending_assignment && <span className="text-xs font-medium text-amber-700 bg-amber-50 ring-1 ring-amber-200 px-2 py-0.5 rounded-full">Unassigned</span>}
              {needsContact && <span className="text-xs font-medium text-sky-800 bg-sky-50 ring-1 ring-sky-200 px-2 py-0.5 rounded-full">Speak to customer</span>}
            </div>
            <p className="text-graphite-600 mt-1 text-lg">{l.customer_name || '—'} {l.company_name && <span className="text-graphite-400">· {l.company_name}</span>}</p>
            <div className="flex flex-wrap gap-x-5 gap-y-1 mt-2 text-sm">
              <span>📞 {l.contact_number ? <a className="text-brand-700 font-semibold hover:underline" href={`tel:${String(l.contact_number).replace(/\s/g, '')}`}>{l.contact_number}</a> : '—'}{l.alternate_contact ? <span className="text-graphite-400"> (alt: {l.alternate_contact})</span> : null}</span>
              <span>✉️ {l.email ? <a className="text-brand-700 font-semibold hover:underline" href={`mailto:${l.email}`}>{l.email}</a> : <span className="text-graphite-400">No email</span>}</span>
              <span>🚗 {l.quantity_raw ? `${l.quantity_raw} cars` : '—'}</span>
              <span className="font-semibold text-graphite-900">💰 Lead Value {inr(l.lead_value)}</span>
            </div>
            <div className="flex flex-wrap gap-x-5 gap-y-1 mt-2 text-sm text-graphite-500">
              <span>📍 {l.city || '—'}</span>
              <span>📅 {l.enquiry_date || '—'}</span>
              <span>🏷 {nameOf('sources', l.source_id)}</span>
              <span>📦 {prodName(l, nameOf)}</span>
              <span>👤 {nameOf('employees', l.primary_employee_id)}</span>
              {l.sla_deadline && <span>⏱ Contact by {fmtDT(l.sla_deadline)}</span>}
            </div>
          </div>
          <Link to="/leads" className="btn-secondary">← All leads</Link>
        </div>
      </div>
      {err && <div className="bg-red-50 border border-red-200 text-red-700 text-sm rounded-xl px-4 py-3">{err}</div>}
      {okMsg && <div className="bg-emerald-50 border border-emerald-200 text-emerald-800 text-sm rounded-xl px-4 py-3">{okMsg}</div>}

      <Card title="Product & Lead Value">
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
          <div>
            <label className="text-xs font-medium text-graphite-600">Product</label>
            <select className="input mt-1" disabled={!canEditPricing} value={productId} onChange={(e) => setProductId(e.target.value)}>
              <option value="">Select product…</option>
              {(masters?.products || []).map((p: any) => (
                <option key={p.id} value={p.id}>{p.name}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="text-xs font-medium text-graphite-600">Number of Cars</label>
            <input className="input mt-1" type="number" min="1" step="1" disabled={!canEditPricing} value={cars} onChange={(e) => setCars(e.target.value)} placeholder="e.g. 10" />
          </div>
          <div>
            <label className="text-xs font-medium text-graphite-600">Price / Car</label>
            <input className="input mt-1 bg-graphite-50" readOnly value={inr(selectedProduct?.price_per_car ?? preview.price_per_car ?? l.price_per_car)} />
          </div>
          <div>
            <label className="text-xs font-medium text-graphite-600">GST %</label>
            <input className="input mt-1 bg-graphite-50" readOnly value="18%" />
          </div>
          <div>
            <label className="text-xs font-medium text-graphite-600">GST Amount</label>
            <input className="input mt-1 bg-graphite-50" readOnly value={inr(preview.gst_amount ?? l.gst_amount)} />
          </div>
          <div>
            <label className="text-xs font-medium text-graphite-600">Lead Value</label>
            <input className="input mt-1 bg-graphite-50 font-semibold" readOnly value={inr(preview.lead_value ?? l.lead_value)} />
          </div>
        </div>
        <p className="text-xs text-graphite-500 mt-3">Lead Value = Cars × Price/Car (excl. GST). For Two Post, Four Post and Pit Stack Parking, Lead Value is half of that. GST 18% is shown separately. Calculated by the server — not editable.</p>
        {canEditPricing && (
          <button type="button" className="btn-primary mt-3" disabled={pricingBusy} onClick={savePricing}>
            {pricingBusy ? 'Saving…' : 'Save product & cars'}
          </button>
        )}
      </Card>

      {canAdminReassign && (
        <Card title={l.pending_assignment ? 'Assign to employee' : 'Reassign to another employee'}>
          {rr?.status === 'ACCEPTED' && (
            <p className="text-sm text-amber-800 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2 mb-3">
              Reassignment accepted for <b>{rr.requested_by_name}</b>. Choose a new employee below — ownership stays unchanged until you assign.
              {rr.reason ? <span className="block text-xs mt-1 text-amber-700">Reason: {rr.reason}</span> : null}
            </p>
          )}
          <div className="flex flex-wrap gap-3 items-end">
            <div className="flex-1 min-w-[200px]">
              <label className="text-xs font-medium text-graphite-600">Employee</label>
              <select className="input mt-1" value={assignEmp} onChange={(e) => setAssignEmp(e.target.value)}>
                <option value="">Select…</option>
                {masters?.employees?.filter((e: any) => e.id !== l.primary_employee_id).map((e: any) => (
                  <option key={e.id} value={e.id}>{e.name}</option>
                ))}
              </select>
            </div>
            <button className="btn-primary" disabled={!assignEmp || busy} onClick={doAssign}>
              {l.pending_assignment ? 'Assign' : 'Reassign'}
            </button>
          </div>
        </Card>
      )}

      {role === 'ADMIN' && rr?.status === 'PENDING' && (
        <Card title="Reassignment request pending">
          <p className="text-sm text-graphite-700">
            <b>{rr.requested_by_name}</b> asked to move this lead. Review it on the{' '}
            <Link className="text-brand-700 underline" to="/reassignments">Reassign</Link> page (accept or decline).
          </p>
          <p className="text-xs text-graphite-500 mt-2">Reason: {rr.reason || '—'}</p>
        </Card>
      )}

      {canRequestReassign && (
        <Card title="Cannot follow this customer?">
          <p className="text-xs text-graphite-500 mb-3">
            Request admin to reassign this lead to another employee. Your ownership stays until admin accepts and manually assigns someone else.
          </p>
          <textarea
            className="input min-h-[90px]"
            placeholder="Why can’t you follow this lead? (language, region, conflict…)"
            value={reassignReason}
            onChange={(e) => setReassignReason(e.target.value)}
          />
          <button
            type="button"
            className="btn-secondary mt-3"
            disabled={busy || reassignReason.trim().length < 3}
            onClick={requestReassign}
          >
            {busy ? 'Sending…' : 'Request reassignment'}
          </button>
        </Card>
      )}

      {role === 'EMPLOYEE' && rr && (
        <Card title="Reassignment request">
          <p className="text-sm">
            Status: <b>{rr.status}</b>
            {rr.status === 'PENDING' && ' — waiting for admin.'}
            {rr.status === 'ACCEPTED' && ' — admin will assign another employee.'}
          </p>
          <p className="text-xs text-graphite-500 mt-2">Reason: {rr.reason || '—'}</p>
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
          {l.employee_remarks && (
            <Card title="Latest employee remarks">
              <p className="text-sm whitespace-pre-wrap">{l.employee_remarks}</p>
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
    name: '', city: '', company: '', phone: '', cars: '', source: '', product: '', enq: '', date: '', email: '',
  });
  const [error, setError] = useState('');
  const [okMsg, setOkMsg] = useState('');
  const [busy, setBusy] = useState(false);
  const [tab, setTab] = useState<'duplicates' | 'invalid' | 'ready'>('duplicates');
  const [importMasters, setImportMasters] = useState<any>(null);
  const errMsg = (e: any) => e?.response?.data?.detail || 'Upload failed. Is the backend running?';

  const loadBatches = () => api.get('/import/batches').then((r) => setBatches(r.data || [])).catch(() => {});
  useEffect(() => {
    loadBatches();
    api.get('/masters').then((r) => setImportMasters(r.data)).catch(() => {});
  }, []);

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
      email: row.email || '',
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
              <th className="th">Company</th><th className="th">Phone</th><th className="th">Email</th><th className="th">City</th><th className="th">Cars</th>
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
                <td className="td">{r.email || '—'}{(r.email_invalid || (r.email && !/^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$/.test(String(r.email).trim()))) && <span className="block text-[11px] text-amber-700 font-medium">⚠ invalid email</span>}</td>
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
        subtitle="Columns: Enq no, Received date, Name, Company (optional), Contact no, Email, City, No. of cars, Lead source, Product/type. Admin can view duplicates/invalid and Add to leads or Delete."
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
                <th className="th">Company</th><th className="th">Phone</th><th className="th">Email</th><th className="th">City</th><th className="th">Cars</th>
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
                    <td className="td">{r.email || '—'}{r.email_invalid && <span className="block text-[11px] text-amber-700 font-medium">⚠ invalid email</span>}</td>
                    <td className="td">{r.city || '—'}</td>
                    <td className="td">{r.cars || '—'}</td>
                    <td className="td">{r.source || '—'}</td>
                    <td className="td">{r.product || '—'}{r.product_unmapped && <span className="block text-[11px] text-amber-700 font-medium">⚠ not recognized — will show as-is</span>}</td>
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
        <Card title="Admin review — Add to leads or Delete" action={
          <button type="button" className="btn-secondary !px-3 !py-1.5 text-sm" onClick={() => { setErrors([]); setEditId(null); }}>
            Close
          </button>
        }>
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
                    <td className="td text-sm">
                      <span className="text-[10px] uppercase tracking-wide text-graphite-400 mr-2">{b.source === 'sheets' ? 'Google Sheet' : 'Excel'}</span>
                      {b.source === 'sheets' ? (b.sheet_name || 'Sheet sync') : b.file_name}
                      <div className="text-xs text-graphite-400">{b.source === 'sheets' ? b.file_name : b.sheet_name}</div>
                    </td>
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
                <label className="text-xs font-medium text-graphite-600">Email</label>
                <input className="input mt-1" type="email" placeholder="name@company.com" value={editForm.email} onChange={(e) => setEditForm({ ...editForm, email: e.target.value })} />
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
                <label className="text-xs font-medium text-graphite-600">Product</label>
                <select className="input mt-1" value={editForm.product} onChange={(e) => setEditForm({ ...editForm, product: e.target.value })}>
                  <option value="">Select product…</option>
                  {(importMasters?.products || []).map((p: any) => (
                    <option key={p.id} value={p.name}>{p.name}</option>
                  ))}
                </select>
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

type ReportFilter = {
  mode: 'custom' | 'week' | 'month';
  month: string;
  week: string;
  fromDate: string;
  toDate: string;
};

export function Reports() {
  const today = new Date();
  const defaultMonth = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}`;
  const defaultWeek = today.toISOString().slice(0, 10);
  const emptyFilter = (): ReportFilter => ({
    mode: 'custom', month: defaultMonth, week: defaultWeek, fromDate: '', toDate: '',
  });

  type ReportId = 'source' | 'product' | 'lead_value' | 'quotation' | 'employee' | 'monthly';
  const REPORT_MENU: Array<{ id: ReportId; title: string; description: string; accent: string }> = [
    { id: 'source', title: 'Lead Source Report', description: 'Leads by source with follow-up, meeting, site visit and quotation counts, plus chart.', accent: 'bg-[#1e3a5f]' },
    { id: 'product', title: 'Product Wise Report', description: 'Product funnel table plus product-wise lead bar chart.', accent: 'bg-[#0f766e]' },
    { id: 'lead_value', title: 'Lead Value Report', description: 'Total lead value by product, source and period with charts.', accent: 'bg-[#3F6212]' },
    { id: 'quotation', title: 'Quotation Report', description: 'Quotation rows with order value, GST and grand total.', accent: 'bg-[#b45309]' },
    { id: 'employee', title: 'Employee Workload Report', description: 'Assigned lead count per employee.', accent: 'bg-[#334155]' },
    { id: 'monthly', title: 'Monthly Lead Volume', description: 'Pick a month range, view the chart and table, then download Excel or PDF.', accent: 'bg-[#4338ca]' },
  ];

  const [activeReport, setActiveReport] = useState<ReportId | null>(null);

  const [lvFilter, setLvFilter] = useState<ReportFilter>(emptyFilter);
  const [quoteFilter, setQuoteFilter] = useState<ReportFilter>(emptyFilter);
  const [sourceFilter, setSourceFilter] = useState<ReportFilter>(emptyFilter);
  const [productFilter, setProductFilter] = useState<ReportFilter>(emptyFilter);
  const [monthlyFilter, setMonthlyFilter] = useState({ fromMonth: defaultMonth, toMonth: defaultMonth });

  const [leadValueReport, setLeadValueReport] = useState<any>(null);
  const [quotationReport, setQuotationReport] = useState<any>(null);
  const [details, setDetails] = useState<any>(null);
  const [productDetails, setProductDetails] = useState<any>(null);
  const [prod, setProd] = useState<any[]>([]);
  const [emp, setEmp] = useState<any[]>([]);
  const [monthlyRows, setMonthlyRows] = useState<any[]>([]);

  const [lvBusy, setLvBusy] = useState(false);
  const [quoteBusy, setQuoteBusy] = useState(false);
  const [sourceBusy, setSourceBusy] = useState(false);
  const [productBusy, setProductBusy] = useState(false);
  const [pdfBusy, setPdfBusy] = useState(false);
  const [empBusy, setEmpBusy] = useState(false);
  const [monthlyBusy, setMonthlyBusy] = useState(false);

  const [lvErr, setLvErr] = useState('');
  const [quoteErr, setQuoteErr] = useState('');
  const [sourceErr, setSourceErr] = useState('');
  const [productErr, setProductErr] = useState('');
  const [empErr, setEmpErr] = useState('');
  const [monthlyErr, setMonthlyErr] = useState('');

  const apiErr = (e: any, fallback: string) => {
    const d = e?.response?.data?.detail;
    if (typeof d === 'string' && d.trim()) return d;
    if (Array.isArray(d) && d.length) {
      return d.map((x: any) => x?.msg || JSON.stringify(x)).join('; ');
    }
    if (e?.response?.status === 401) return 'Session expired — please log in again';
    if (e?.response?.status === 403) return 'Reports require admin or manager role';
    if (e?.message === 'Network Error') return 'Cannot reach the server. Is the backend running?';
    return fallback;
  };

  const toParams = (f: ReportFilter): Record<string, string> => {
    if (f.mode === 'month') return { mode: 'month', month: f.month || defaultMonth };
    if (f.mode === 'week') return { mode: 'week', week: f.week || defaultWeek };
    const p: Record<string, string> = { mode: 'custom' };
    if (f.fromDate) p.from_date = f.fromDate;
    if (f.toDate) p.to_date = f.toDate;
    return p;
  };

  const validate = (f: ReportFilter): string | null => {
    if (f.mode === 'custom' && f.fromDate && f.toDate && f.fromDate > f.toDate) {
      return 'From date must be on or before To date.';
    }
    if (f.mode === 'month' && !/^\d{4}-\d{2}$/.test(f.month || '')) {
      return 'Select a valid month.';
    }
    return null;
  };

  const loadLeadValue = async (f: ReportFilter = lvFilter) => {
    const v = validate(f);
    if (v) { setLvErr(v); return; }
    setLvBusy(true); setLvErr('');
    try {
      const { data } = await api.get('/reports/lead-value', { params: toParams(f) });
      setLeadValueReport(data);
    } catch (e: any) {
      setLvErr(apiErr(e, 'Lead value report failed'));
    } finally { setLvBusy(false); }
  };

  const loadQuotations = async (f: ReportFilter = quoteFilter) => {
    const v = validate(f);
    if (v) { setQuoteErr(v); return; }
    setQuoteBusy(true); setQuoteErr('');
    try {
      const { data } = await api.get('/reports/quotations', { params: toParams(f) });
      setQuotationReport(data);
    } catch (e: any) {
      setQuoteErr(apiErr(e, 'Quotation report failed'));
    } finally { setQuoteBusy(false); }
  };

  const loadSource = async (f: ReportFilter = sourceFilter) => {
    const v = validate(f);
    if (v) { setSourceErr(v); return; }
    setSourceBusy(true); setSourceErr('');
    try {
      const { data } = await api.get('/reports/source-details', { params: toParams(f) });
      setDetails(data);
    } catch (e: any) {
      setSourceErr(apiErr(e, 'Source report failed'));
    } finally { setSourceBusy(false); }
  };

  const loadProduct = async (f: ReportFilter = productFilter) => {
    const v = validate(f);
    if (v) { setProductErr(v); return; }
    setProductBusy(true); setProductErr('');
    try {
      const params = toParams(f);
      const [detailsRes, barRes] = await Promise.all([
        api.get('/reports/product-details', { params }),
        api.get('/reports/product-wise', { params }),
      ]);
      setProductDetails(detailsRes.data);
      setProd(Array.isArray(barRes.data) ? barRes.data : []);
    } catch (e: any) {
      setProductErr(apiErr(e, 'Product report failed'));
    } finally { setProductBusy(false); }
  };

  const loadEmployees = async () => {
    setEmpBusy(true); setEmpErr('');
    try {
      const { data } = await api.get('/reports/employee-wise');
      setEmp(Array.isArray(data) ? data : []);
    } catch (e: any) {
      setEmpErr(apiErr(e, 'Employee report failed'));
    } finally { setEmpBusy(false); }
  };

  const monthlyParams = (f = monthlyFilter): Record<string, string> => {
    const p: Record<string, string> = {};
    if (f.fromMonth) p.from_month = f.fromMonth;
    if (f.toMonth) p.to_month = f.toMonth;
    return p;
  };

  const loadMonthly = async (f = monthlyFilter) => {
    if (f.fromMonth && f.toMonth && f.fromMonth > f.toMonth) {
      setMonthlyErr('From month must be on or before To month.');
      return;
    }
    setMonthlyBusy(true); setMonthlyErr('');
    try {
      const { data } = await api.get('/reports/monthly', { params: monthlyParams(f) });
      setMonthlyRows(Array.isArray(data) ? data : []);
    } catch (e: any) {
      setMonthlyErr(apiErr(e, 'Monthly report failed'));
    } finally { setMonthlyBusy(false); }
  };

  useEffect(() => {
    if (!activeReport) return;
    if (activeReport === 'lead_value') void loadLeadValue();
    if (activeReport === 'quotation') void loadQuotations();
    if (activeReport === 'source') void loadSource();
    if (activeReport === 'product') void loadProduct();
    if (activeReport === 'employee') void loadEmployees();
    if (activeReport === 'monthly') void loadMonthly();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeReport]);

  const dl = async (path: string, filename: string, params: Record<string, string>, setErr: (s: string) => void) => {
    try {
      await downloadReport(path, filename, params);
    } catch (e: any) {
      setErr(apiErr(e, 'Download failed'));
    }
  };

  const downloadPdf = async (
    kind: 'source' | 'product' | 'lead_value' | 'quotation' | 'monthly',
    f: ReportFilter | { fromMonth: string; toMonth: string },
    setErr: (s: string) => void,
  ) => {
    setPdfBusy(true); setErr('');
    const names = {
      source: 'lead-source-report.pdf',
      product: 'product-wise-report.pdf',
      lead_value: 'lead-value-report.pdf',
      quotation: 'quotation-report.pdf',
      monthly: 'monthly-lead-volume.pdf',
    };
    try {
      const params = kind === 'monthly'
        ? { ...monthlyParams(f as { fromMonth: string; toMonth: string }), report_type: kind }
        : { ...toParams(f as ReportFilter), report_type: kind };
      if (kind !== 'monthly') {
        const v = validate(f as ReportFilter);
        if (v) { setErr(v); setPdfBusy(false); return; }
      } else {
        const mf = f as { fromMonth: string; toMonth: string };
        if (mf.fromMonth && mf.toMonth && mf.fromMonth > mf.toMonth) {
          setErr('From month must be on or before To month.');
          setPdfBusy(false);
          return;
        }
      }
      await downloadReport('/reports/pdf', names[kind], params);
    } catch (e: any) {
      const response = e?.response?.data;
      if (response instanceof Blob) {
        try {
          const parsed = JSON.parse(await response.text());
          setErr(typeof parsed?.detail === 'string' ? parsed.detail : 'PDF download failed');
        } catch {
          setErr(apiErr(e, 'PDF download failed'));
        }
      } else {
        setErr(apiErr(e, 'PDF download failed'));
      }
    } finally { setPdfBusy(false); }
  };

  const filterBar = (
    f: ReportFilter,
    setF: (next: ReportFilter) => void,
    busy: boolean,
    onApply: () => void,
    onExcel: () => void,
    excelDisabled: boolean,
    onPdf?: () => void,
  ) => (
    <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-3 bg-amber-50/80 border border-amber-200 rounded-xl p-4">
      <div>
        <label className="text-xs font-medium text-graphite-600">Report Mode</label>
        <select
          className="input mt-1"
          value={f.mode}
          onChange={(e) => setF({ ...f, mode: e.target.value as ReportFilter['mode'] })}
        >
          <option value="custom">From date → To date</option>
          <option value="week">Weekly</option>
          <option value="month">Monthly</option>
        </select>
      </div>
      {f.mode === 'month' ? (
        <div>
          <label className="text-xs font-medium text-graphite-600">Select Month</label>
          <input type="month" className="input mt-1" value={f.month} onChange={(e) => setF({ ...f, month: e.target.value })} />
        </div>
      ) : f.mode === 'week' ? (
        <div>
          <label className="text-xs font-medium text-graphite-600">Any day in the week</label>
          <input type="date" className="input mt-1" value={f.week} onChange={(e) => setF({ ...f, week: e.target.value })} />
        </div>
      ) : (
        <>
          <div>
            <label className="text-xs font-medium text-graphite-600">From Date</label>
            <input type="date" className="input mt-1" value={f.fromDate} onChange={(e) => setF({ ...f, fromDate: e.target.value })} />
          </div>
          <div>
            <label className="text-xs font-medium text-graphite-600">To Date</label>
            <input type="date" className="input mt-1" value={f.toDate} onChange={(e) => setF({ ...f, toDate: e.target.value })} />
          </div>
        </>
      )}
      <div className="flex flex-wrap items-end gap-2">
        <button type="button" className="btn-primary" disabled={busy} onClick={onApply}>{busy ? 'Loading…' : 'Apply'}</button>
        <button type="button" className="btn-secondary" disabled={excelDisabled || busy} onClick={onExcel}>Download Excel</button>
        {onPdf && (
          <button type="button" className="btn-secondary" disabled={pdfBusy || busy} onClick={onPdf}>{pdfBusy ? 'Creating PDF…' : 'Download PDF'}</button>
        )}
      </div>
    </div>
  );

  const lvPeriod = leadValueReport?.by_period || [];
  const lvProducts = leadValueReport?.by_product || [];
  const lvSources = leadValueReport?.by_source || [];
  const activeMeta = REPORT_MENU.find((r) => r.id === activeReport);

  if (!activeReport) {
    return (
      <div className="space-y-5">
        <PageHeader
          title="Reports"
          subtitle="Choose a report to open its table, charts and downloads."
        />
        <div className="grid sm:grid-cols-2 xl:grid-cols-3 gap-4 items-stretch">
          {REPORT_MENU.map((report) => (
            <button
              key={report.id}
              type="button"
              className="card text-left p-0 overflow-hidden h-full flex flex-col hover:shadow-md transition-shadow focus:outline-none focus:ring-2 focus:ring-brand-500"
              onClick={() => setActiveReport(report.id)}
            >
              <div className={`${report.accent} text-white px-5 py-3 font-semibold tracking-wide min-h-[52px] flex items-center`}>
                {report.title}
              </div>
              <div className="p-5 flex flex-col flex-1 gap-3">
                <p className="text-sm text-graphite-600 leading-relaxed flex-1 min-h-[64px]">{report.description}</p>
                <span className="text-sm font-semibold text-brand-700 mt-auto">Open report →</span>
              </div>
            </button>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <PageHeader
        title={activeMeta?.title || 'Report'}
        subtitle={activeMeta?.description || ''}
        actions={
          <button type="button" className="btn-secondary" onClick={() => setActiveReport(null)}>
            Close
          </button>
        }
      />

      {activeReport === 'lead_value' && (
        <div className="card overflow-hidden">
          <div className="bg-[#3F6212] text-white px-5 py-3 font-semibold tracking-wide">LEAD VALUE REPORT</div>
          <div className="p-5 space-y-4">
            {filterBar(
              lvFilter, setLvFilter, lvBusy, () => loadLeadValue(lvFilter),
              () => dl('/reports/lead-value/export', 'lead-value-report.xlsx', toParams(lvFilter), setLvErr),
              !leadValueReport,
              () => downloadPdf('lead_value', lvFilter, setLvErr),
            )}
            {lvErr && <div className="text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg px-3 py-2">{lvErr}</div>}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
              {[
                { label: 'Total Lead Value', value: inr(leadValueReport?.total_lead_value) },
                { label: 'Total Leads', value: leadValueReport?.total_leads ?? '—' },
                { label: 'Total Cars', value: leadValueReport?.total_cars != null ? Number(leadValueReport.total_cars).toLocaleString('en-IN') : '—' },
                { label: 'Average Lead Value', value: inr(leadValueReport?.average_lead_value) },
              ].map((k) => (
                <div key={k.label} className="bg-graphite-50 border border-graphite-200 rounded-lg p-3 text-center">
                  <div className="text-base font-bold text-graphite-900 tabular-nums">{k.value}</div>
                  <div className="text-[10px] uppercase tracking-wide text-graphite-500 mt-1">{k.label}</div>
                </div>
              ))}
            </div>
            <div className="grid lg:grid-cols-2 gap-4">
              <div>
                <h3 className="text-sm font-semibold text-graphite-700 mb-2">Lead Value by Product</h3>
                {lvProducts.every((r: any) => !r.lead_value) ? <EmptyState title="No lead value in this range" /> : (
                  <div className="h-72">
                    <ResponsiveContainer>
                      <BarChart data={lvProducts} margin={{ top: 8, right: 8, left: 0, bottom: 56 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                        <XAxis dataKey="product" interval={0} angle={-25} textAnchor="end" height={60} tick={{ fontSize: 9 }} />
                        <YAxis tick={{ fontSize: 11 }} tickFormatter={(v) => `₹${Number(v).toLocaleString('en-IN', { notation: 'compact' })}`} />
                        <Tooltip formatter={(v: any) => inr(v)} />
                        <Bar dataKey="lead_value" name="Lead Value" fill="#3F6212" radius={[4, 4, 0, 0]} />
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                )}
              </div>
              <div>
                <h3 className="text-sm font-semibold text-graphite-700 mb-2">Lead Value by Source</h3>
                {lvSources.every((r: any) => !r.lead_value) ? <EmptyState title="No source lead value in this range" /> : (
                  <div className="h-72">
                    <ResponsiveContainer>
                      <BarChart data={lvSources} margin={{ top: 8, right: 8, left: 0, bottom: 56 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                        <XAxis dataKey="source" interval={0} angle={-25} textAnchor="end" height={60} tick={{ fontSize: 9 }} />
                        <YAxis tick={{ fontSize: 11 }} tickFormatter={(v) => `₹${Number(v).toLocaleString('en-IN', { notation: 'compact' })}`} />
                        <Tooltip formatter={(v: any) => inr(v)} />
                        <Bar dataKey="lead_value" name="Lead Value" fill="#0e7490" radius={[4, 4, 0, 0]} />
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                )}
              </div>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[480px] text-sm text-center">
                <thead><tr className="bg-graphite-100">
                  <th className="th text-center">Source</th>
                  <th className="th text-center">Leads</th>
                  <th className="th text-center">Lead Value</th>
                </tr></thead>
                <tbody>
                  {lvSources.map((r: any) => (
                    <tr key={r.source} className="hover:bg-graphite-50">
                      <td className="td text-center">{r.source}</td>
                      <td className="td text-center">{r.leads}</td>
                      <td className="td text-center font-semibold tabular-nums">{inr(r.lead_value)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div>
              <h3 className="text-sm font-semibold text-graphite-700 mb-2">
                {lvFilter.mode === 'week' ? 'Lead Value by Day' : 'Lead Value by Week'}
              </h3>
              {lvPeriod.length === 0 ? <EmptyState title="No dated leads in this range" /> : (
                <div className="h-72">
                  <ResponsiveContainer>
                    <BarChart data={lvPeriod} margin={{ top: 8, right: 8, left: 0, bottom: 40 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                      <XAxis dataKey="label" interval={0} angle={-20} textAnchor="end" height={50} tick={{ fontSize: 9 }} />
                      <YAxis tick={{ fontSize: 11 }} tickFormatter={(v) => `₹${Number(v).toLocaleString('en-IN', { notation: 'compact' })}`} />
                      <Tooltip formatter={(v: any) => inr(v)} />
                      <Bar dataKey="lead_value" name="Lead Value" fill="#65A30D" radius={[4, 4, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              )}
            </div>
            {lvPeriod.length > 0 && (
              <div className="overflow-x-auto">
                <table className="w-full min-w-[480px] text-sm text-center">
                  <thead><tr className="bg-graphite-100">
                    <th className="th text-center">Period</th>
                    <th className="th text-center">Leads</th>
                    <th className="th text-center">Lead Value</th>
                  </tr></thead>
                  <tbody>
                    {lvPeriod.map((r: any) => (
                      <tr key={r.period} className="hover:bg-graphite-50">
                        <td className="td text-center">{r.label}</td>
                        <td className="td text-center">{r.leads}</td>
                        <td className="td text-center font-semibold tabular-nums">{inr(r.lead_value)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      )}

      {activeReport === 'quotation' && (
        <div className="card overflow-hidden">
          <div className="bg-[#b45309] text-white px-5 py-3 font-semibold tracking-wide">QUOTATION REPORT</div>
          <div className="p-5 space-y-4">
            {filterBar(
              quoteFilter, setQuoteFilter, quoteBusy, () => loadQuotations(quoteFilter),
              () => dl('/reports/quotations/export', 'quotation-report.xlsx', toParams(quoteFilter), setQuoteErr),
              !quotationReport,
              () => downloadPdf('quotation', quoteFilter, setQuoteErr),
            )}
            {quoteErr && <div className="text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg px-3 py-2">{quoteErr}</div>}
            {quotationReport && (
              <div className="text-sm text-graphite-700 flex flex-wrap gap-6">
                <span><b>Effective From:</b> {quotationReport.effective_from || 'All time'}</span>
                <span><b>Effective To:</b> {quotationReport.effective_to || 'All time'}</span>
                <span><b>Quotations:</b> {quotationReport.totals?.count ?? 0}</span>
              </div>
            )}
            <div className="overflow-x-auto">
              <table className="w-full min-w-[980px] text-sm text-center">
                <thead>
                  <tr className="bg-amber-300 text-graphite-900">
                    <th className="th !bg-transparent !text-center underline">S.No</th>
                    <th className="th !bg-transparent !text-center">Date</th>
                    <th className="th !bg-transparent !text-center">Enquiry No</th>
                    <th className="th !bg-transparent !text-center">Customer Name</th>
                    <th className="th !bg-transparent !text-center">State</th>
                    <th className="th !bg-transparent !text-center">Parking Type</th>
                    <th className="th !bg-transparent !text-center">No. of Units/Cars</th>
                    <th className="th !bg-transparent !text-center">Order Value (Excl GST)</th>
                    <th className="th !bg-transparent !text-center">GST</th>
                    <th className="th !bg-transparent !text-center">Grand Total</th>
                  </tr>
                </thead>
                <tbody>
                  {(quotationReport?.rows || []).map((r: any, i: number) => (
                    <tr key={`${r.enquiry_number}-${i}`} className={i % 2 ? 'bg-amber-50/50' : 'bg-white'}>
                      <td className="td text-center">{i + 1}</td>
                      <td className="td text-center whitespace-nowrap">{r.date || '—'}</td>
                      <td className="td text-center font-medium">{r.enquiry_number || '—'}</td>
                      <td className="td text-center">{r.customer_name || '—'}</td>
                      <td className="td text-center">{r.state || '—'}</td>
                      <td className="td text-center">{r.parking_type || '—'}</td>
                      <td className="td text-center">{r.units ?? '—'}</td>
                      <td className="td text-center tabular-nums font-medium">{inr(r.order_value_excl_gst)}</td>
                      <td className="td text-center tabular-nums">{inr(r.gst)}</td>
                      <td className="td text-center tabular-nums font-semibold">{inr(r.grand_total)}</td>
                    </tr>
                  ))}
                  {quotationReport?.totals && (quotationReport.rows || []).length > 0 && (
                    <tr className="bg-graphite-100 font-bold">
                      <td className="td text-center" colSpan={6}>TOTAL</td>
                      <td className="td text-center" />
                      <td className="td text-center tabular-nums">{inr(quotationReport.totals.order_value_excl_gst)}</td>
                      <td className="td text-center tabular-nums">{inr(quotationReport.totals.gst)}</td>
                      <td className="td text-center tabular-nums">{inr(quotationReport.totals.grand_total)}</td>
                    </tr>
                  )}
                </tbody>
              </table>
              {quotationReport && !(quotationReport.rows || []).length && (
                <EmptyState title="No quotations in this range" hint="Mark leads as Quotation sent with a value, or add quotation rows." />
              )}
            </div>
          </div>
        </div>
      )}

      {activeReport === 'source' && (
        <div className="card overflow-hidden">
          <div className="bg-[#1e3a5f] text-white px-5 py-3 font-semibold tracking-wide">LEAD SOURCE REPORT</div>
          <div className="p-5 space-y-4">
            {filterBar(
              sourceFilter, setSourceFilter, sourceBusy, () => loadSource(sourceFilter),
              () => {
                const p = toParams(sourceFilter);
                const name = sourceFilter.mode === 'month'
                  ? `leads-by-source-${sourceFilter.month}.xlsx`
                  : sourceFilter.mode === 'week'
                    ? `leads-by-source-week-${sourceFilter.week}.xlsx`
                    : `leads-by-source-${sourceFilter.fromDate || 'all'}_to_${sourceFilter.toDate || 'all'}.xlsx`;
                return dl('/reports/source-details/export', name, p, setSourceErr);
              },
              !details,
              () => downloadPdf('source', sourceFilter, setSourceErr),
            )}
            {sourceErr && <div className="text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg px-3 py-2">{sourceErr}</div>}
            {details && (
              <div className="text-sm text-graphite-700 flex flex-wrap gap-6">
                <span><b>Effective From:</b> {details.effective_from || 'All time'}</span>
                <span><b>Effective To:</b> {details.effective_to || 'All time'}</span>
              </div>
            )}
            <div className="overflow-x-auto">
              <table className="w-full min-w-[960px] text-sm text-center">
                <thead>
                  <tr className="bg-[#1e3a5f] text-white">
                    <th className="th !text-white !bg-transparent !text-center">Lead Source</th>
                    <th className="th !text-white !bg-transparent !text-center">Total Leads</th>
                    <th className="th !text-white !bg-transparent !text-center">In Followup</th>
                    <th className="th !text-white !bg-transparent !text-center">Meeting</th>
                    <th className="th !text-white !bg-transparent !text-center">Site Visit</th>
                    <th className="th !text-white !bg-transparent !text-center">Quotation sent</th>
                    <th className="th !text-white !bg-transparent !text-center">Not Interested</th>
                  </tr>
                </thead>
                <tbody>
                  {(details?.rows || []).map((r: any, i: number) => (
                    <tr key={r.source} className={i % 2 ? 'bg-sky-50/70' : 'bg-white'}>
                      <td className="td font-medium text-center">{r.source}</td>
                      <td className="td font-bold text-center">{r.total}</td>
                      <td className="td text-center">{r.in_followup}</td>
                      <td className="td text-center">{r.meeting}</td>
                      <td className="td text-center">{r.site_visit}</td>
                      <td className="td text-center">{r.quote_sent}</td>
                      <td className="td text-center">{r.not_interested}</td>
                    </tr>
                  ))}
                  {details?.totals && (
                    <tr className="bg-graphite-100 font-bold">
                      <td className="td text-center">TOTAL</td>
                      <td className="td text-center">{details.totals.total}</td>
                      <td className="td text-center">{details.totals.in_followup}</td>
                      <td className="td text-center">{details.totals.meeting}</td>
                      <td className="td text-center">{details.totals.site_visit}</td>
                      <td className="td text-center">{details.totals.quote_sent}</td>
                      <td className="td text-center">{details.totals.not_interested}</td>
                    </tr>
                  )}
                </tbody>
              </table>
              {!details && !sourceBusy && <EmptyState title="Apply a date range to load the report" />}
            </div>
            <div>
              <h3 className="text-sm font-semibold text-graphite-700 mb-2">Leads by Source</h3>
              {!(details?.rows || []).some((r: any) => r.total > 0) ? <EmptyState title="No source data to chart" /> : (
                <div className="h-80">
                  <ResponsiveContainer>
                    <BarChart data={(details?.rows || []).filter((r: any) => r.total > 0)} margin={{ top: 8, right: 8, left: 0, bottom: 48 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                      <XAxis dataKey="source" interval={0} angle={-20} textAnchor="end" height={56} tick={{ fontSize: 10 }} />
                      <YAxis allowDecimals={false} tick={{ fontSize: 11 }} />
                      <Tooltip /><Legend />
                      <Bar dataKey="total" fill="#1e3a5f" name="Total Leads" radius={[4, 4, 0, 0]} />
                      <Bar dataKey="in_followup" fill="#f59e0b" name="In Followup" radius={[4, 4, 0, 0]} />
                      <Bar dataKey="meeting" fill="#8b5cf6" name="Meeting" radius={[4, 4, 0, 0]} />
                      <Bar dataKey="site_visit" fill="#10b981" name="Site Visit" radius={[4, 4, 0, 0]} />
                      <Bar dataKey="quote_sent" fill="#0ea5e9" name="Quotation sent" radius={[4, 4, 0, 0]} />
                      <Bar dataKey="not_interested" fill="#ef4444" name="Not Interested" radius={[4, 4, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {activeReport === 'product' && (
        <div className="space-y-4">
          <div className="card overflow-hidden">
            <div className="bg-[#0f766e] text-white px-5 py-3 font-semibold tracking-wide">PRODUCT WISE REPORT</div>
            <div className="p-5 space-y-4">
              {filterBar(
                productFilter, setProductFilter, productBusy, () => loadProduct(productFilter),
                () => dl('/reports/product-details/export', 'product-wise-details.xlsx', toParams(productFilter), setProductErr),
                !productDetails,
                () => downloadPdf('product', productFilter, setProductErr),
              )}
              {productErr && <div className="text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg px-3 py-2">{productErr}</div>}
              <div className="overflow-x-auto">
                <table className="w-full min-w-[900px] text-sm text-center">
                  <thead><tr className="bg-[#0f766e] text-white">
                    {['Product', 'Total Leads', 'In Followup', 'Meeting', 'Site Visit', 'Quotation sent', 'Not Interested'].map((header) => <th key={header} className="th !text-white !bg-transparent !text-center">{header}</th>)}
                  </tr></thead>
                  <tbody>
                    {(productDetails?.rows || []).map((row: any, i: number) => (
                      <tr key={row.product} className={i % 2 ? 'bg-teal-50/70' : 'bg-white'}>
                        <td className="td font-medium text-center">{row.product}</td>
                        <td className="td font-bold text-center">{row.total}</td>
                        <td className="td text-center">{row.in_followup}</td>
                        <td className="td text-center">{row.meeting}</td>
                        <td className="td text-center">{row.site_visit}</td>
                        <td className="td text-center">{row.quote_sent}</td>
                        <td className="td text-center">{row.not_interested}</td>
                      </tr>
                    ))}
                    {productDetails?.totals && (
                      <tr className="bg-graphite-100 font-bold">
                        <td className="td text-center">TOTAL</td>
                        <td className="td text-center">{productDetails.totals.total}</td>
                        <td className="td text-center">{productDetails.totals.in_followup}</td>
                        <td className="td text-center">{productDetails.totals.meeting}</td>
                        <td className="td text-center">{productDetails.totals.site_visit}</td>
                        <td className="td text-center">{productDetails.totals.quote_sent}</td>
                        <td className="td text-center">{productDetails.totals.not_interested}</td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
          <BarCard
            title="Product-wise leads"
            data={prod}
            x="product"
            y="leads"
            onDownload={() => dl('/reports/product-wise/export', 'product-wise-report.xlsx', toParams(productFilter), setProductErr)}
          />
        </div>
      )}

      {activeReport === 'employee' && (
        <div className="card overflow-hidden">
          <div className="bg-[#334155] text-white px-5 py-3 font-semibold tracking-wide flex items-center justify-between gap-3">
            <span>EMPLOYEE WORKLOAD REPORT</span>
            <button
              type="button"
              className="btn-secondary !px-3 !py-1 text-xs"
              disabled={empBusy}
              onClick={() => void loadEmployees()}
            >
              {empBusy ? 'Loading…' : 'Refresh'}
            </button>
          </div>
          <div className="p-5">
            {empErr && <div className="text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg px-3 py-2 mb-4">{empErr}</div>}
            {empBusy && emp.length === 0 ? <Spinner /> : emp.length === 0 ? <EmptyState title="No data" /> : (
              <table className="w-full text-center">
                <thead className="bg-graphite-50">
                  <tr><th className="th text-center">Employee</th><th className="th text-center">Assigned leads</th></tr>
                </thead>
                <tbody>
                  {emp.map((e: any) => (
                    <tr key={e.employee} className="hover:bg-graphite-50">
                      <td className="td font-medium text-center">{e.employee}</td>
                      <td className="td font-bold text-center">{e.assigned}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      )}

      {activeReport === 'monthly' && (
        <div className="card overflow-hidden">
          <div className="bg-[#4338ca] text-white px-5 py-3 font-semibold tracking-wide">MONTHLY LEAD VOLUME</div>
          <div className="p-5 space-y-4">
            <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-3 bg-indigo-50/80 border border-indigo-200 rounded-xl p-4">
              <div>
                <label className="text-xs font-medium text-graphite-600">From Month</label>
                <input
                  type="month"
                  className="input mt-1"
                  value={monthlyFilter.fromMonth}
                  onChange={(e) => setMonthlyFilter((cur) => ({ ...cur, fromMonth: e.target.value }))}
                />
              </div>
              <div>
                <label className="text-xs font-medium text-graphite-600">To Month</label>
                <input
                  type="month"
                  className="input mt-1"
                  value={monthlyFilter.toMonth}
                  onChange={(e) => setMonthlyFilter((cur) => ({ ...cur, toMonth: e.target.value }))}
                />
              </div>
              <div className="flex flex-wrap items-end gap-2 lg:col-span-2">
                <button type="button" className="btn-primary" disabled={monthlyBusy} onClick={() => void loadMonthly(monthlyFilter)}>
                  {monthlyBusy ? 'Loading…' : 'Apply'}
                </button>
                <button
                  type="button"
                  className="btn-secondary"
                  disabled={monthlyBusy || monthlyRows.length === 0}
                  onClick={() => dl('/reports/monthly/export', 'monthly-lead-volume.xlsx', monthlyParams(), setMonthlyErr)}
                >
                  Download Excel
                </button>
                <button
                  type="button"
                  className="btn-secondary"
                  disabled={pdfBusy || monthlyBusy || monthlyRows.length === 0}
                  onClick={() => void downloadPdf('monthly', monthlyFilter, setMonthlyErr)}
                >
                  {pdfBusy ? 'Creating PDF…' : 'Download PDF'}
                </button>
              </div>
            </div>
            {monthlyErr && <div className="text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg px-3 py-2">{monthlyErr}</div>}
            {monthlyBusy && monthlyRows.length === 0 ? <Spinner /> : monthlyRows.length === 0 ? (
              <EmptyState title="No months in this range" hint="Pick From / To month and Apply." />
            ) : (
              <>
                <div className="h-80">
                  <ResponsiveContainer>
                    <BarChart data={monthlyRows}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                      <XAxis dataKey="month" tick={{ fontSize: 11 }} />
                      <YAxis allowDecimals={false} tick={{ fontSize: 12 }} />
                      <Tooltip /><Legend />
                      <Bar dataKey="leads" fill="#1e3a5f" name="Total Leads" radius={[4, 4, 0, 0]} />
                      <Bar dataKey="in_followup" fill="#f59e0b" name="In Followup" radius={[4, 4, 0, 0]} />
                      <Bar dataKey="meeting" fill="#8b5cf6" name="Meeting" radius={[4, 4, 0, 0]} />
                      <Bar dataKey="site_visit" fill="#10b981" name="Site Visit" radius={[4, 4, 0, 0]} />
                      <Bar dataKey="quotation_sent" fill="#0ea5e9" name="Quotation sent" radius={[4, 4, 0, 0]} />
                      <Bar dataKey="not_interested" fill="#ef4444" name="Not Interested" radius={[4, 4, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[960px] text-sm text-center">
                    <thead>
                      <tr className="bg-[#4338ca] text-white">
                        {['Month', 'Total Leads', 'In Followup', 'Meeting', 'Site Visit', 'Quotation sent', 'Not Interested', 'Sources', 'Products'].map((h) => (
                          <th key={h} className="th !text-white !bg-transparent !text-center">{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {monthlyRows.map((row: any, i: number) => (
                        <tr key={row.month_key || row.month} className={i % 2 ? 'bg-indigo-50/60' : 'bg-white'}>
                          <td className="td font-medium text-center">{row.month}</td>
                          <td className="td font-bold text-center">{row.leads}</td>
                          <td className="td text-center">{row.in_followup}</td>
                          <td className="td text-center">{row.meeting}</td>
                          <td className="td text-center">{row.site_visit}</td>
                          <td className="td text-center">{row.quotation_sent}</td>
                          <td className="td text-center">{row.not_interested}</td>
                          <td className="td text-center">{row.sources}</td>
                          <td className="td text-center">{row.products}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </>
            )}
          </div>
        </div>
      )}

      <div className="flex justify-end">
        <button type="button" className="btn-secondary" onClick={() => setActiveReport(null)}>
          Close — back to all reports
        </button>
      </div>
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
  const [selectedEmployee, setSelectedEmployee] = useState<any>(null);
  const [employeeLeads, setEmployeeLeads] = useState<any[]>([]);
  const [leadMasters, setLeadMasters] = useState<any>(null);
  const [loadingEmployeeLeads, setLoadingEmployeeLeads] = useState(false);
  const load = () => api.get('/employees').then((r) => setItems(r.data)).catch(() => setError('Failed to load employees'));
  useEffect(() => { load(); api.get('/masters').then((r) => setLeadMasters(r.data)).catch(() => {}); }, []);
  const viewEmployeeLeads = async (employee: any) => {
    setSelectedEmployee(employee);
    setLoadingEmployeeLeads(true);
    try {
      const { data } = await api.get('/leads', { params: { employee: employee.id, page: 1, size: 1000 } });
      setEmployeeLeads(data.items || []);
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Failed to load employee leads');
      setEmployeeLeads([]);
    } finally { setLoadingEmployeeLeads(false); }
  };
  const leadStatusName = (id: string) => leadMasters?.statuses?.find((s: any) => s.id === id)?.name || '—';
  const reviewOptions = ['A+ (Immediate)', 'A (3-6 months)', 'B (1 year)', 'C (plan stage)'];
  const workActionOptions = ['Assigned', 'In Followup', 'Meeting', 'Site Visit', 'Quotation sent', 'Converted', 'Not Interested'];
  const empLeadStatus = (lead: any) => {
    const s = leadStatusName(lead.status_id);
    return s === 'New Lead' && lead.primary_employee_id ? 'Assigned' : s;
  };
  const empNeedsContact = employeeLeads.filter((l) => !l.first_contact_at).length;
  const empOverdue = employeeLeads.filter((l) => l.sla_state === 'OVERDUE').length;
  const empContactDone = employeeLeads.filter((l) => !!l.first_contact_at).length;
  const empWorkActionCounts = workActionOptions.map((label) => ({
    label,
    value: employeeLeads.filter((l) => empLeadStatus(l) === label).length,
  }));
  const empReviewCounts = reviewOptions.map((label) => ({
    label,
    value: employeeLeads.filter((l) => (l.customer_review || '') === label).length,
  }));
  const empUnreviewed = employeeLeads.filter((l) => !(l.customer_review || '').trim()).length;
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
                    <td className="td font-medium"><button type="button" className="text-brand-700 hover:underline font-semibold" onClick={() => viewEmployeeLeads(emp)}>{emp.name}</button></td>
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
      {selectedEmployee && (
        <Card title={`${selectedEmployee.name} — Assigned leads (${employeeLeads.length})`} action={
          <button type="button" className="btn-secondary !px-3 !py-1 text-xs" onClick={() => setSelectedEmployee(null)}>Close</button>
        }>
          {loadingEmployeeLeads ? <Spinner /> : employeeLeads.length === 0 ? <EmptyState title="No leads assigned" /> : (
            <>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 mb-4">
                {[
                  { label: 'Total assigned', value: employeeLeads.length },
                  { label: 'Needs first contact', value: empNeedsContact },
                  { label: 'SLA overdue', value: empOverdue },
                  { label: 'Contact done', value: empContactDone },
                ].map((s) => (
                  <div key={s.label} className="rounded-xl border border-graphite-100 bg-graphite-50 p-3 text-center">
                    <div className="text-xl font-bold text-graphite-900 tabular-nums">{s.value}</div>
                    <div className="text-[11px] text-graphite-500 uppercase tracking-wide mt-1">{s.label}</div>
                  </div>
                ))}
              </div>
              <div className="mb-4">
                <div className="text-xs font-semibold text-graphite-600 uppercase tracking-wide mb-2">Work action</div>
                <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-2">
                  {empWorkActionCounts.map((s) => (
                    <div key={s.label} className="rounded-xl border border-graphite-100 bg-graphite-50 p-3 text-center">
                      <div className="text-xl font-bold text-graphite-900 tabular-nums">{s.value}</div>
                      <div className="text-[11px] text-graphite-500 uppercase tracking-wide mt-1">{s.label}</div>
                    </div>
                  ))}
                </div>
              </div>
              <div className="mb-4">
                <div className="text-xs font-semibold text-graphite-600 uppercase tracking-wide mb-2">Category (A+ / A / B / C)</div>
                <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-2">
                  {empReviewCounts.map((s) => (
                    <div key={s.label} className="rounded-xl border border-graphite-100 bg-graphite-50 p-3 text-center">
                      <div className="text-xl font-bold text-graphite-900 tabular-nums">{s.value}</div>
                      <div className="text-[11px] text-graphite-500 uppercase tracking-wide mt-1">{s.label}</div>
                    </div>
                  ))}
                  <div className="rounded-xl border border-graphite-100 bg-graphite-50 p-3 text-center">
                    <div className="text-xl font-bold text-graphite-900 tabular-nums">{empUnreviewed}</div>
                    <div className="text-[11px] text-graphite-500 uppercase tracking-wide mt-1">Unreviewed</div>
                  </div>
                </div>
              </div>
              <div className="overflow-x-auto -mx-5 px-5">
                <table className="w-full min-w-[1280px]">
                  <thead className="bg-graphite-50"><tr>
                    <th className="th">Enquiry</th><th className="th">Customer</th><th className="th">Contact / Email</th><th className="th text-center">Cars</th><th className="th">City</th><th className="th">Source</th><th className="th">Product</th>
                    <th className="th text-right">Lead Value</th>
                    <th className="th">Status</th><th className="th">Remarks</th><th className="th">Category</th><th className="th">Work action</th><th className="th">Quotation value</th><th className="th">Completion</th>
                  </tr></thead>
                  <tbody>{employeeLeads.map((lead) => (
                    <tr key={lead.id} className={lead.sla_state === 'COMPLETED' ? 'bg-emerald-50/80' : 'hover:bg-graphite-50'}>
                      <td className="td font-semibold"><Link className="text-brand-700" to={`/leads/${lead.id}`}>{lead.enquiry_number}</Link></td>
                      <td className="td">{lead.customer_name || '—'}</td>
                      <td className="td">
                        <div>{lead.contact_number || '—'}</div>
                        <div className="text-xs mt-0.5 break-all">{lead.email ? <a className="text-brand-700 hover:underline" href={`mailto:${lead.email}`}>{lead.email}</a> : <span className="text-graphite-400">No email</span>}</div>
                      </td>
                      <td className="td text-center">{lead.quantity_raw || '—'}</td>
                      <td className="td">{lead.city || '—'}</td><td className="td">{lead.source_name || '—'}</td><td className="td">{lead.product_name || '—'}</td>
                      <td className="td text-right tabular-nums font-semibold">{inr(lead.lead_value)}</td>
                      <td className="td"><StatusBadge value={lead.primary_employee_id && leadStatusName(lead.status_id) === 'New Lead' ? 'Assigned' : leadStatusName(lead.status_id)} /></td>
                      <td className="td max-w-[240px] truncate" title={lead.employee_remarks || ''}>{lead.employee_remarks || '—'}</td>
                      <td className="td">{lead.customer_review || '—'}</td><td className="td">{leadStatusName(lead.status_id)}</td>
                      <td className="td">{lead.quotation_value != null ? inr(lead.quotation_value) : '—'}</td>
                      <td className="td">{lead.sla_state === 'COMPLETED' ? 'Completed' : 'Pending'}</td>
                    </tr>
                  ))}</tbody>
                </table>
              </div>
            </>
          )}
        </Card>
      )}
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

/* ================= REASSIGNMENT REQUESTS (ADMIN) ================= */
export function ReassignmentsPage() {
  const [items, setItems] = useState<any[]>([]);
  const [filter, setFilter] = useState('PENDING');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [busyId, setBusyId] = useState('');
  const [note, setNote] = useState<Record<string, string>>({});
  const [okMsg, setOkMsg] = useState('');

  const load = async (status = filter) => {
    setLoading(true); setError('');
    try {
      const { data } = await api.get('/leads/reassignment-requests', { params: { status } });
      setItems(Array.isArray(data) ? data : []);
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Could not load reassignment requests');
      setItems([]);
    } finally { setLoading(false); }
  };

  useEffect(() => { load(filter); }, [filter]);

  const decide = async (id: string, action: 'accept' | 'decline', leadId?: string) => {
    setBusyId(id); setError(''); setOkMsg('');
    try {
      const { data } = await api.post(`/leads/reassignment-requests/${id}/${action}`, { note: note[id] || '' });
      setOkMsg(data?.message || (action === 'accept' ? 'Accepted — assign a new employee on the lead page.' : 'Declined — lead unchanged.'));
      await load(filter);
      if (action === 'accept' && (leadId || data?.lead_id)) {
        // keep admin on page; message points them to lead
      }
    } catch (e: any) {
      setError(e?.response?.data?.detail || `Could not ${action} request`);
    } finally { setBusyId(''); }
  };

  return (
    <div className="space-y-4">
      <PageHeader
        title="Reassignment requests"
        subtitle="Employees ask to move a lead they cannot follow. Accept, then manually assign another employee — decline leaves ownership unchanged."
      />
      <div className="flex flex-wrap gap-2">
        {['PENDING', 'ACCEPTED', 'DECLINED', 'FULFILLED'].map((s) => (
          <button
            key={s}
            type="button"
            className={`px-3 py-1.5 rounded-lg text-sm ${filter === s ? 'bg-brand-100 text-brand-900 font-semibold' : 'bg-graphite-100 text-graphite-600'}`}
            onClick={() => setFilter(s)}
          >
            {s.charAt(0) + s.slice(1).toLowerCase()}
          </button>
        ))}
      </div>
      {okMsg && <div className="bg-emerald-50 border border-emerald-200 text-emerald-800 text-sm rounded-xl px-4 py-3">{okMsg}</div>}
      {error && <div className="bg-red-50 border border-red-200 text-red-700 text-sm rounded-xl px-4 py-3">{error}</div>}
      {loading ? <div className="card p-6"><Spinner /></div>
        : items.length === 0 ? <div className="card"><EmptyState title={`No ${filter.toLowerCase()} requests`} /></div>
        : items.map((r) => (
          <div key={r.id} className="card p-4 space-y-3">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <div className="font-semibold text-graphite-900">
                  <Link className="text-brand-700 hover:underline" to={`/leads/${r.lead_id}`}>{r.enquiry_number}</Link>
                  {' · '}{r.customer_name || '—'}
                </div>
                <div className="text-sm text-graphite-600 mt-0.5">
                  Requested by <b>{r.requested_by_name}</b>
                  {r.created_at ? ` · ${fmtDT(r.created_at)}` : ''}
                </div>
                <p className="text-sm mt-2 whitespace-pre-wrap">{r.reason || '—'}</p>
              </div>
              <span className="text-xs font-semibold uppercase tracking-wide text-graphite-600 bg-graphite-100 px-2 py-1 rounded">{r.status}</span>
            </div>
            {r.status === 'PENDING' && (
              <div className="border-t border-graphite-100 pt-3 space-y-2">
                <input
                  className="input text-sm"
                  placeholder="Optional note to employee"
                  value={note[r.id] || ''}
                  onChange={(e) => setNote((cur) => ({ ...cur, [r.id]: e.target.value }))}
                />
                <div className="flex flex-wrap gap-2">
                  <button type="button" className="btn-primary" disabled={busyId === r.id} onClick={() => decide(r.id, 'accept', r.lead_id)}>
                    Accept
                  </button>
                  <button type="button" className="btn-danger" disabled={busyId === r.id} onClick={() => decide(r.id, 'decline', r.lead_id)}>
                    Decline
                  </button>
                  <Link className="btn-secondary" to={`/leads/${r.lead_id}`}>Open lead</Link>
                </div>
              </div>
            )}
            {r.status === 'ACCEPTED' && (
              <div className="border-t border-graphite-100 pt-3 flex flex-wrap gap-2 items-center">
                <p className="text-sm text-amber-800 flex-1">Accepted — manually assign another employee on the lead page.</p>
                <Link className="btn-primary" to={`/leads/${r.lead_id}`}>Assign now</Link>
              </div>
            )}
          </div>
        ))}
    </div>
  );
}

/* ================= NOTIFICATIONS ================= */
export function NotificationsPage() {
  const [items, setItems] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const { data } = await api.get('/notifications');
        const list = Array.isArray(data) ? data : [];
        if (cancelled) return;
        setItems(list);
        const unread = list.filter((n: any) => !n.is_read);
        if (unread.length) {
          await api.post('/notifications/read-all').catch(() => null);
          if (!cancelled) {
            setItems((prev) => prev.map((n) => ({ ...n, is_read: true })));
            window.dispatchEvent(new Event('crm:notifications-read'));
          }
        }
      } catch {
        if (!cancelled) setError('Could not load notifications. Check your connection.');
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, []);
  return (
    <div className="max-w-3xl space-y-4">
      <PageHeader title="Notifications" subtitle="SLA breaches, assignments, reassignment requests and follow-up reminders." />
      {loading ? <div className="card"><Spinner /></div>
      : error ? <div className="card"><EmptyState title="Could not load notifications" hint={error} /></div>
      : items.length === 0 ? <div className="card"><EmptyState title="All caught up" hint="No notifications." /></div> : items.map((n) => (
        <div key={n.id} className={`card p-4 flex gap-3 ${n.is_read ? 'opacity-80' : ''}`}>
          <div className="w-9 h-9 rounded-lg bg-red-100 text-red-600 flex items-center justify-center shrink-0">⚠</div>
          <div>
            <div className="font-semibold text-sm">{n.title}</div>
            <div className="text-sm text-graphite-600 mt-0.5">{n.body}</div>
            <div className="flex flex-wrap gap-3 mt-1 text-xs">
              {n.created_at && <span className="text-graphite-400">{fmtDT(n.created_at, 19)}</span>}
              {n.lead_id && <Link className="text-brand-700 underline" to={`/leads/${n.lead_id}`}>Open lead</Link>}
              {n.kind === 'REASSIGN_REQUEST' && <Link className="text-brand-700 underline" to="/reassignments">Review request</Link>}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
