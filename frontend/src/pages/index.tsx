import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import {
  PieChart, Pie, Cell, BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid,
  ResponsiveContainer, Legend,
} from 'recharts';
import { api } from '../services/api';
import { useDragScroll } from '../hooks/useDragScroll';
import { Card, EmptyState, PageHeader, PROGRESS_HEX, PROGRESS_TILE_BG, PROGRESS_TILE_TEXT, CATEGORY_TILE_BG, CATEGORY_TILE_TEXT, categoryTileBg, categoryTileText, SlaBadge, Spinner, StatusBadge } from '../components/ui';

export { Analytics } from './analytics';
export { CreateLead } from './createLead';

const COLORS = ['#65A30D', '#6E6E6E', '#B5CC18', '#3F6212', '#A3A380', '#2F9E44', '#E8890C', '#84cc16', '#a3a380', '#4d7c0f', '#14b8a6', '#1971C2'];

function DashboardPie({ rows }: { rows: { name: string; value: number }[] }) {
  if (!rows.length) return <EmptyState title="No data" />;
  const RADIAN = Math.PI / 180;
  return (
    <div className="w-full h-full min-h-0 flex flex-col">
      <div className="flex-1 min-h-0 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart margin={{ top: 4, right: 4, bottom: 4, left: 4 }}>
            <Pie
              data={rows}
              dataKey="value"
              nameKey="name"
              cx="50%"
              cy="50%"
              innerRadius="38%"
              outerRadius="72%"
              paddingAngle={1.5}
              labelLine={false}
              label={({ cx, cy, midAngle, innerRadius, outerRadius, percent }) => {
                if ((percent ?? 0) < 0.08) return null;
                const radius = Number(innerRadius) + (Number(outerRadius) - Number(innerRadius)) * 0.52;
                const x = Number(cx) + radius * Math.cos(-Number(midAngle) * RADIAN);
                const y = Number(cy) + radius * Math.sin(-Number(midAngle) * RADIAN);
                return (
                  <text x={x} y={y} fill="#fff" textAnchor="middle" dominantBaseline="central" fontSize={11} fontWeight={700}>
                    {`${((percent ?? 0) * 100).toFixed(0)}%`}
                  </text>
                );
              }}
            >
              {rows.map((e, i) => <Cell key={e.name} fill={COLORS[i % COLORS.length]} stroke="#fff" strokeWidth={1} />)}
            </Pie>
            <Tooltip formatter={(value: any, name: any) => [Number(value).toLocaleString('en-IN'), name]} />
          </PieChart>
        </ResponsiveContainer>
      </div>
      <ul className="mt-2 flex flex-wrap justify-center content-start gap-x-3 gap-y-1.5 px-1 shrink-0 max-h-[4.5rem] overflow-y-auto">
        {rows.map((e, i) => (
          <li key={e.name} className="inline-flex items-center gap-1.5 text-[11px] text-graphite-700 max-w-full">
            <span className="inline-block w-2.5 h-2.5 rounded-sm shrink-0" style={{ background: COLORS[i % COLORS.length] }} />
            <span className="leading-tight truncate">{e.name}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** Compact funnel table — all columns fit without horizontal scroll. */
function DashboardFunnelTable({
  labelHeader,
  rows,
  totals,
  emptyTitle,
}: {
  labelHeader: string;
  rows: Array<{ name: string; total?: number; Meeting?: number; [k: string]: any }>;
  totals: { total: number; lead_value?: number; follow: number; meeting: number; siteVisit: number; quote: number; converted: number; notInt: number };
  emptyTitle: string;
}) {
  const cell = 'td !px-0.5 sm:!px-1 !py-1 text-[10px] sm:text-[11px] text-center align-middle leading-tight break-words [overflow-wrap:anywhere] border-graphite-100 tabular-nums';
  const head = 'th !px-1 !py-1.5 !text-[8px] sm:!text-[9px] !normal-case !tracking-normal !text-white !bg-transparent text-center leading-tight font-semibold break-words [overflow-wrap:anywhere]';
  return (
    <div className="rounded-lg border border-graphite-100 overflow-hidden h-full">
      <table className="w-full table-fixed text-center">
        <colgroup>
          <col className="w-[18%]" />
          <col className="w-[9%]" />
          <col className="w-[15%]" />
          <col className="w-[10%]" />
          <col className="w-[10%]" />
          <col className="w-[10%]" />
          <col className="w-[11%]" />
          <col className="w-[8%]" />
          <col className="w-[9%]" />
        </colgroup>
        <thead>
          <tr className="bg-[#0e7490] text-white">
            <th className={head}>{labelHeader}</th>
            <th className={head}>Total Leads</th>
            <th className={head}>Total Lead Value</th>
            <th className={head}>In Followup</th>
            <th className={head}>Meeting</th>
            <th className={head}>Site Visit</th>
            <th className={head}>Quotation sent</th>
            <th className={head}>Converted</th>
            <th className={head}>Not Interested</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={r.name} className={i % 2 ? 'bg-sky-50/60' : 'bg-white'}>
              <td className={`${cell} !text-left !px-1.5 font-medium break-words`}>{r.name}</td>
              <td className={`${cell} font-bold`}>{r.total ?? 0}</td>
              <td className={`${cell} whitespace-nowrap`}>{inr(r.lead_value)}</td>
              <td className={cell}>{r['In Followup'] ?? 0}</td>
              <td className={cell}>{r.Meeting ?? 0}</td>
              <td className={cell}>{r['Site Visit'] ?? 0}</td>
              <td className={cell}>{r['Quotation sent'] ?? 0}</td>
              <td className={cell}>{r.Converted ?? r.converted ?? 0}</td>
              <td className={cell}>{(r['Not Interested'] ?? 0) + (r['Not Interested/Spam'] ?? 0)}</td>
            </tr>
          ))}
          {rows.length > 0 && (
            <tr className="bg-graphite-100 font-bold">
              <td className={`${cell} !text-left !px-1.5`}>TOTAL</td>
              <td className={cell}>{totals.total}</td>
              <td className={`${cell} whitespace-nowrap`}>{inr(totals.lead_value)}</td>
              <td className={cell}>{totals.follow}</td>
              <td className={cell}>{totals.meeting}</td>
              <td className={cell}>{totals.siteVisit}</td>
              <td className={cell}>{totals.quote}</td>
              <td className={cell}>{totals.converted}</td>
              <td className={cell}>{totals.notInt}</td>
            </tr>
          )}
        </tbody>
      </table>
      {rows.length === 0 && <EmptyState title={emptyTitle} hint="Import leads to populate the funnel." />}
    </div>
  );
}

/** Table + chart row: equal height cards, stack on small screens. */
function DashboardTableChartRow({
  title,
  labelHeader,
  rows,
  totals,
  pieRows,
  emptyTitle,
}: {
  title: string;
  labelHeader: string;
  rows: Array<{ name: string; total?: number; Meeting?: number; [k: string]: any }>;
  totals: { total: number; follow: number; meeting: number; siteVisit: number; quote: number; converted: number; notInt: number };
  pieRows: { name: string; value: number }[];
  emptyTitle: string;
}) {
  return (
    <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)] gap-4 items-stretch">
      <Card title={title} className="min-w-0 h-full !p-4 flex flex-col">
        <div className="flex-1 min-h-0 flex flex-col">
          <DashboardFunnelTable labelHeader={labelHeader} rows={rows} totals={totals} emptyTitle={emptyTitle} />
        </div>
      </Card>
      <Card title={title} className="min-w-0 h-full !p-4 flex flex-col">
        <div className="flex-1 min-h-0 flex flex-col">
          <DashboardPie rows={pieRows} />
        </div>
      </Card>
    </div>
  );
}

function leadRowColour(lead: any, status: string) {
  // Green only when Converted is finished with Done
  if (lead.sla_state === 'COMPLETED' && status === 'Converted') return 'bg-emerald-100';
  if (lead.sla_state === 'COMPLETED' && ['Not Interested', 'Not Interested/Spam'].includes(status)) return 'bg-red-100';
  return 'bg-white';
}

function fmtDT(v: any, len = 16) {
  if (!v) return '—';
  return String(v).slice(0, len).replace('T', ' ');
}

function withUpdateStamp(remarks: string) {
  const cleaned = String(remarks || '').replace(/\n?\[[^\]]*\]\s*$/u, '').trim();
  const stamp = new Date().toLocaleString('en-IN', {
    timeZone: 'Asia/Kolkata',
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    hour12: true,
  });
  return `${cleaned}\n[${stamp}]`;
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

const ESTAR_WEBMAIL = 'https://webmail.estar.in';

/** Roundcube compose on cPanel. After a fresh login, this path is kept and
 *  opened with the customer address and subject. It must not be opened during
 *  an existing webmail session: cPanel then returns HTTP 401 because the
 *  address has no /cpsess…/ token. */
function customerWebmailUrl(email?: string, enquiry?: string) {
  const to = (email || '').trim();
  const params = new URLSearchParams();
  params.set('_task', 'mail');
  params.set('_action', 'compose');
  params.set('_extwin', '1');
  if (to) params.set('_to', to);
  if (enquiry) params.set('_subject', `Regarding your enquiry ${enquiry}`);
  return `${ESTAR_WEBMAIL}/3rdparty/roundcube/index.php?${params.toString()}`;
}

function whatsappUrl(raw?: string) {
  let digits = String(raw || '').replace(/\D/g, '');
  if (!digits) return '';
  if (digits.length === 11 && digits.startsWith('0')) digits = digits.slice(1);
  if (digits.length === 10) digits = `91${digits}`;
  return `https://wa.me/${digits}`;
}

function openEstarWebmail(event: { preventDefault: () => void; stopPropagation: () => void }, email?: string, enquiry?: string) {
  event.preventDefault();
  event.stopPropagation();
  const compose = customerWebmailUrl(email, enquiry);
  const tab = window.open(`${ESTAR_WEBMAIL}/logout/`, '_blank');
  if (!tab) return;
  window.setTimeout(() => {
    if (tab.closed) return;
    try { tab.location.replace(compose); } catch { /* opened window can still be navigated */ }
  }, 1200);
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

const ODD_CAR_PRODUCTS = ['puzzle parking', 'pit puzzle parking', 'car elevator', 'car elevation', 'shuttle parking', 'asrs parking'];

function allowsOddCars(productName: string) {
  return ODD_CAR_PRODUCTS.includes(String(productName || '').trim().toLowerCase());
}

function carCountError(raw: string, productName: string) {
  const text = String(raw || '').trim();
  if (!text) return '';
  const cars = Number(text);
  if (!Number.isInteger(cars)) return 'Number of cars must be a whole number starting at 2';
  if (cars < 2) return 'Number of cars starts at 2';
  if (cars % 2 === 1 && !allowsOddCars(productName)) return 'Number of cars must be even for Two Post, Four Post, Pit Stack, and Tower. Odd numbers are only for Puzzle, Pit Puzzle, Car Elevator, Shuttle, and ASRS';
  return '';
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
  const navigate = useNavigate();
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
      // Arm the employee login notification popup (consumed once after redirect).
      try { sessionStorage.setItem('crm:login-popup', '1'); } catch { /* private mode */ }
      navigate('/dashboard', { replace: true });
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Cannot reach the server. Port 8000 is busy or the backend is stuck — run scripts\\stop-backend.ps1 then scripts\\start-backend.ps1');
    } finally { setBusy(false); }
  };
  return (
    <div className="min-h-screen grid md:grid-cols-2">
      <div className="hidden md:flex flex-col justify-between text-white p-12 relative overflow-hidden bg-gradient-to-br from-graphite-700 via-graphite-800 to-graphite-950">
        <div className="absolute -top-24 -right-24 w-96 h-96 rounded-full bg-brand-400/20 blur-3xl pointer-events-none" />
        <div className="flex items-center relative">
          <img src="/estar-logo.png" alt="E-Star" className="h-20 w-auto max-w-[260px] rounded-xl object-contain bg-white p-2 shadow-sm" />
        </div>
        <div className="relative">
          <h1 className="text-4xl font-bold leading-tight">Every lead,<br />followed up.</h1>
          <p className="text-graphite-200 mt-4 max-w-sm">Live funnel dashboard, overdue follow-ups, automatic assignment and full activity history — replacing the Excel tracker.</p>
          <div className="grid grid-cols-3 gap-4 mt-8 text-sm">
            {['Live funnel', 'Overdue', 'Reports'].map((t, i) => (
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
            <img src="/estar-logo.png" alt="E-Star" className="h-16 w-auto max-w-[220px] rounded-xl object-contain" />
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
  const [categories, setCategories] = useState<any>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const load = () => {
    setLoading(true); setError('');
    Promise.allSettled([
      api.get('/dashboard'),
      api.get('/dashboard/by-source'),
      api.get('/dashboard/by-product'),
      api.get('/dashboard/by-category'),
    ]).then(([dr, sr, pr, cr]) => {
      if (dr.status === 'fulfilled') setD(dr.value.data);
      else setError(dr.reason?.response?.data?.detail || 'Failed to load dashboard. Check backend / login again.');
      if (sr.status === 'fulfilled') setSrc(sr.value.data);
      if (pr.status === 'fulfilled') setProducts(pr.value.data);
      else setError('Could not load product data. Please refresh the dashboard.');
      if (cr.status === 'fulfilled') setCategories(cr.value.data);
      else setError('Could not load category data. Please refresh the dashboard.');
    }).finally(() => setLoading(false));
  };
  useEffect(() => { load(); }, []);
  const pie = useMemo(() => Object.entries(src || {}).map(([name, v]: any) => ({ name, value: v.total ?? 0 })).filter((x) => x.value > 0), [src]);
  const srcRows = useMemo(() => Object.entries(src || {}).map(([name, v]: any) => ({ name, ...(v as object) })).sort((a: any, b: any) => (b.total || 0) - (a.total || 0)), [src]);
  const srcTotals = useMemo(() => {
    const t = { total: 0, lead_value: 0, follow: 0, meeting: 0, siteVisit: 0, quote: 0, converted: 0, notInt: 0 };
    for (const r of srcRows as any[]) {
      t.total += r.total || 0;
      t.lead_value += r.lead_value || 0;
      t.follow += r['In Followup'] || 0;
      t.meeting += r.Meeting || 0;
      t.siteVisit += r['Site Visit'] || 0;
      t.quote += r['Quotation sent'] || 0;
      t.converted += r.Converted || r.converted || 0;
      t.notInt += (r['Not Interested'] || 0) + (r['Not Interested/Spam'] || 0);
    }
    return t;
  }, [srcRows]);
  const productRows = (products?.rows || []).map((row: any) => ({
    name: row.product,
    total: row.total,
    lead_value: row.lead_value ?? 0,
    'In Followup': row.in_followup,
    Meeting: row.meeting,
    'Site Visit': row.site_visit,
    'Quotation sent': row.quote_sent,
    Converted: row.converted ?? 0,
    'Not Interested': row.not_interested,
  }));
  const productPie = productRows.filter((row: any) => row.total > 0).map((row: any) => ({ name: row.name, value: row.total }));
  const productTotals = {
    total: products?.totals?.total ?? 0,
    lead_value: products?.totals?.lead_value ?? 0,
    follow: products?.totals?.in_followup ?? 0,
    meeting: products?.totals?.meeting ?? 0,
    siteVisit: products?.totals?.site_visit ?? 0,
    quote: products?.totals?.quote_sent ?? 0,
    converted: products?.totals?.converted ?? 0,
    notInt: products?.totals?.not_interested ?? 0,
  };
  const categoryRows = (categories?.rows || []).map((row: any) => ({
    name: row.category,
    total: row.total,
    lead_value: row.lead_value ?? 0,
    'In Followup': row.in_followup,
    Meeting: row.meeting,
    'Site Visit': row.site_visit,
    'Quotation sent': row.quote_sent,
    Converted: row.converted ?? 0,
    'Not Interested': row.not_interested,
  }));
  const categoryPie = categoryRows.filter((row: any) => row.total > 0).map((row: any) => ({ name: row.name, value: row.total }));
  const categoryTotals = {
    total: categories?.totals?.total ?? 0,
    lead_value: categories?.totals?.lead_value ?? 0,
    follow: categories?.totals?.in_followup ?? 0,
    meeting: categories?.totals?.meeting ?? 0,
    siteVisit: categories?.totals?.site_visit ?? 0,
    quote: categories?.totals?.quote_sent ?? 0,
    converted: categories?.totals?.converted ?? 0,
    notInt: categories?.totals?.not_interested ?? 0,
  };
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
    { label: 'Total Leads', value: f.total ?? d.total ?? 0, bg: 'bg-[#1e3a5f]', text: 'text-white' },
    { label: 'Pending', value: f.assigned ?? 0, bg: 'bg-[#0e7490]', text: 'text-white' },
    { label: 'In Followup', value: f.in_followup ?? 0, bg: PROGRESS_TILE_BG['In Followup'], text: PROGRESS_TILE_TEXT['In Followup'] },
    { label: 'Meeting', value: f.meeting ?? 0, bg: PROGRESS_TILE_BG.Meeting, text: PROGRESS_TILE_TEXT.Meeting },
    { label: 'Site Visit', value: f.site_visit ?? 0, bg: PROGRESS_TILE_BG['Site Visit'], text: PROGRESS_TILE_TEXT['Site Visit'] },
    { label: 'Quotation Sent', value: f.quotation_sent ?? 0, bg: PROGRESS_TILE_BG['Quotation sent'], text: PROGRESS_TILE_TEXT['Quotation sent'] },
    { label: 'Not Interested', value: f.not_interested ?? 0, bg: PROGRESS_TILE_BG['Not Interested'], text: PROGRESS_TILE_TEXT['Not Interested'] },
    { label: 'Converted', value: f.converted ?? 0, bg: PROGRESS_TILE_BG.Converted, text: PROGRESS_TILE_TEXT.Converted },
    { label: 'Overdue', value: d.sla_overdue ?? 0, bg: 'bg-[#BE185D]', text: 'text-white' },
  ];
  const categoryLabels = ['A+ (Immediate)', 'A (3-6 months)', 'B (6-9 months)', 'C (Planning Stage)'];
  const categoryCountFor = (label: string) => {
    const row = categoryRows.find((r: any) => {
      const name = String(r.name || '');
      if (label === 'B (6-9 months)') return name === 'B (6-9 months)' || name === 'B (1 year)';
      if (label === 'C (Planning Stage)') return name === 'C (Planning Stage)' || name === 'C (plan stage)' || name === 'Planning Stage';
      return name === label;
    });
    return Number(row?.total || 0);
  };
  // Category percentages use the current live lead population as the 100% base.
  const categoryBase = Math.max(1, Number(d.total ?? f.total ?? 0));
  const categoryTiles = categoryLabels.map((label) => {
    const count = categoryCountFor(label);
    const pct = Math.round((count / categoryBase) * 100);
    return {
      label,
      value: `${pct}%`,
      hint: `${count} lead${count === 1 ? '' : 's'}`,
      bg: CATEGORY_TILE_BG[label] || categoryTileBg(label),
      text: CATEGORY_TILE_TEXT[label] || categoryTileText(label),
    };
  });
  return (
    <div className="space-y-5">
      <PageHeader title="Leads Funnel — Live Dashboard" subtitle="Status cards, lead value analytics, source mix and product data from live database." />
      {d.warning && (
        <div className="bg-amber-50 border border-amber-300 text-amber-800 rounded-xl px-4 py-3 text-sm">⚠ {d.warning}</div>
      )}
      <div className="w-full">
        <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)] gap-5 lg:gap-4 items-start w-full">
          <div className="min-w-0">
            <div className="text-base sm:text-lg font-bold text-graphite-700 uppercase tracking-wide text-center leading-none mb-2">
              Status
            </div>
            <div className="rounded-xl border border-sky-200 bg-sky-50/70 p-2 sm:p-2.5 md:p-3 shadow-sm">
            <div className="grid grid-cols-3 grid-rows-3 gap-2 md:gap-3 min-h-[18rem] sm:min-h-[21rem]">
              {tiles.map((t) => (
                <div key={t.label} className={`${t.bg} ${t.text} rounded-lg px-2 py-3 sm:px-2.5 shadow-sm text-center flex flex-col items-center justify-center min-h-[5.5rem]`}>
                  <div className="text-[11px] sm:text-sm uppercase tracking-wide opacity-95 font-bold leading-tight break-words">{t.label}</div>
                  <div className="text-2xl sm:text-3xl font-bold mt-1 tabular-nums leading-none">{t.value}</div>
                </div>
              ))}
            </div>
            </div>
          </div>
          <div className="min-w-0">
            <div className="text-base sm:text-lg font-bold text-graphite-700 uppercase tracking-wide text-center leading-none mb-2">
              Category
            </div>
            <div className="rounded-xl border border-fuchsia-200 bg-fuchsia-50/60 p-2 sm:p-2.5 md:p-3 shadow-sm">
            <div className="grid grid-cols-2 grid-rows-2 gap-2 md:gap-3 min-h-[14rem] sm:min-h-[21rem]">
              {categoryTiles.map((t) => (
                <div key={t.label} className={`${t.bg} ${t.text} rounded-lg px-2 py-3 sm:px-2.5 shadow-sm text-center flex flex-col items-center justify-center min-h-[6.5rem]`}>
                  <div className="text-[11px] sm:text-sm uppercase tracking-wide opacity-95 font-bold leading-tight break-words px-0.5">{t.label}</div>
                  <div className="text-2xl sm:text-3xl font-bold mt-1 tabular-nums leading-none">{t.value}</div>
                  <div className="text-xs opacity-85 mt-1 leading-tight">{t.hint}</div>
                </div>
              ))}
            </div>
            </div>
          </div>
        </div>
      </div>

      <div className="rounded-xl border border-amber-200 bg-amber-50/70 p-2 sm:p-2.5 md:p-3 shadow-sm">
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 md:gap-3 w-full">
        {[
          { label: 'Total lead value', value: inr(d.total_lead_value ?? lv.total_lead_value ?? 0), bg: 'bg-[#1e3a5f]' },
          { label: 'Total quotation value', value: inr(d.total_quotation_value ?? 0), bg: 'bg-[#b45309]' },
          { label: 'Total converted value', value: inr(d.total_converted_lead_value ?? 0), bg: 'bg-[#15803d]' },
        ].map((t) => (
          <div key={t.label} className={`${t.bg} text-white rounded-lg px-3 py-4 shadow-sm text-center flex flex-col items-center justify-center min-h-[5.5rem]`}>
            <div className="text-xs sm:text-sm uppercase tracking-wide opacity-95 font-bold leading-tight">{t.label}</div>
            <div className="text-xl sm:text-2xl font-bold mt-1.5 tabular-nums leading-tight break-words">{t.value}</div>
          </div>
        ))}
      </div>
      </div>

      <DashboardTableChartRow
        title="Leads by Source"
        labelHeader="Source"
        rows={srcRows as any[]}
        totals={srcTotals}
        pieRows={pie}
        emptyTitle="No source data"
      />

      <DashboardTableChartRow
        title="Leads by Product"
        labelHeader="Product"
        rows={productRows as any[]}
        totals={productTotals}
        pieRows={productPie}
        emptyTitle="No product data"
      />

      <DashboardTableChartRow
        title="Leads by Category"
        labelHeader="Category"
        rows={categoryRows as any[]}
        totals={categoryTotals}
        pieRows={categoryPie}
        emptyTitle="No category data"
      />
      <Card title="Customer quotation values" className="min-w-0">
        {(d?.quoted_customers || []).length === 0 ? <EmptyState title="No quotation values recorded" /> : (
          <div className="overflow-x-auto -mx-4 px-4 sm:mx-0 sm:px-0 overflow-y-auto max-h-96">
            <table className="w-full min-w-[560px] text-xs sm:text-sm">
              <thead><tr><th className="th whitespace-nowrap">Enquiry Number</th><th className="th">Customer name</th><th className="th">Employee</th><th className="th text-right whitespace-nowrap">Quotation value</th></tr></thead>
              <tbody>{d.quoted_customers.map((lead: any) => <tr key={lead.lead_id}>
                <td className="td whitespace-nowrap"><Link className="text-brand-700 hover:underline" to={`/leads/${lead.lead_id}`}>{lead.enquiry_number}</Link></td>
                <td className="td break-words">{lead.customer_name}</td><td className="td break-words">{lead.employee || '—'}</td>
                <td className="td text-right whitespace-nowrap tabular-nums">{inr(lead.quotation_value)}</td>
              </tr>)}</tbody>
            </table>
          </div>
        )}
      </Card>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 md:gap-3">
        {[
          { label: 'Total Cars', value: Number(lv.total_cars || 0).toLocaleString('en-IN'), bg: 'bg-[#0e7490] border-[#0e7490] text-white' },
          { label: 'Valued Leads', value: lv.total_leads ?? d.total ?? 0, bg: 'bg-[#15803d] border-[#15803d] text-white' },
        ].map((k) => (
          <div key={k.label} className={`card p-4 text-center border ${k.bg}`}>
            <div className="text-2xl sm:text-3xl font-bold tabular-nums">{k.value}</div>
            <div className="text-sm sm:text-base uppercase tracking-wide mt-1 opacity-90 font-semibold">{k.label}</div>
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
  const greet = () => {
    const h = Number(new Intl.DateTimeFormat('en-IN', { timeZone: 'Asia/Kolkata', hour: 'numeric', hour12: false }).format(new Date()));
    if (h < 12) return 'Good morning';
    if (h < 17) return 'Good afternoon';
    return 'Good evening';
  };
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
        <PageHeader title={`${greet()}, ${userName}`} subtitle="Welcome back! Your assigned leads, follow-ups and overdue." />
        <div className="card p-8 text-center">
          <p className="font-medium text-graphite-700">Could not load your dashboard</p>
          <p className="text-sm text-graphite-500 mt-1">{error}</p>
          <button className="btn-primary mt-4" onClick={load}>Retry</button>
        </div>
      </div>
    );
  }
  if (!d) return <Spinner />;
  const statusName = (sid?: string) => masters?.statuses?.find((s: any) => s.id === sid)?.name ?? 'Assigned';
  const overduePending = pending.filter((l: any) => l.sla_state === 'OVERDUE').slice(0, 5);
  const recent = todos.slice(0, 5);
  const normProgress = (name: string) => name === 'New Lead' ? 'Assigned' : (name === 'Not Interested/Spam' ? 'Not Interested' : name);
  const normCategory = (name: string) => {
    const v = (name || '').trim();
    if (v === 'B (1 year)') return 'B (6-9 months)';
    if (v === 'C (plan stage)' || v === 'Planning Stage') return 'C (Planning Stage)';
    return v;
  };
  const mixRows: { status: string; category: string; count: number }[] = d.status_category || [];
  const mixCount = (progress: string, category: string) => mixRows.reduce((sum, row) => {
    if (progress && normProgress(row.status) !== progress) return sum;
    if (category && normCategory(row.category) !== category) return sum;
    return sum + (Number(row.count) || 0);
  }, 0);
  const progressTiles = [
    { label: 'In Followup', bg: PROGRESS_TILE_BG['In Followup'], text: PROGRESS_TILE_TEXT['In Followup'] },
    { label: 'Meeting', bg: PROGRESS_TILE_BG.Meeting, text: PROGRESS_TILE_TEXT.Meeting },
    { label: 'Site Visit', bg: PROGRESS_TILE_BG['Site Visit'], text: PROGRESS_TILE_TEXT['Site Visit'] },
    { label: 'Quotation sent', bg: PROGRESS_TILE_BG['Quotation sent'], text: PROGRESS_TILE_TEXT['Quotation sent'] },
    { label: 'Converted', bg: PROGRESS_TILE_BG.Converted, text: PROGRESS_TILE_TEXT.Converted },
    { label: 'Not Interested', bg: PROGRESS_TILE_BG['Not Interested'], text: PROGRESS_TILE_TEXT['Not Interested'] },
  ];
  const categoryTiles = [
    { label: 'A+ (Immediate)', bg: CATEGORY_TILE_BG['A+ (Immediate)'], text: CATEGORY_TILE_TEXT['A+ (Immediate)'] },
    { label: 'A (3-6 months)', bg: CATEGORY_TILE_BG['A (3-6 months)'], text: CATEGORY_TILE_TEXT['A (3-6 months)'] },
    { label: 'B (6-9 months)', bg: CATEGORY_TILE_BG['B (6-9 months)'], text: CATEGORY_TILE_TEXT['B (6-9 months)'] },
    { label: 'C (Planning Stage)', bg: CATEGORY_TILE_BG['C (Planning Stage)'], text: CATEGORY_TILE_TEXT['C (Planning Stage)'] },
  ];
  // Summary — mid tones, none shared with Progress or Category
  const tiles = [
    { label: 'Total leads', value: d.total ?? 0, bg: 'bg-[#2563EB]', text: 'text-white', hint: 'Assigned to me' },
    { label: 'Pending', value: d.needs_first_contact ?? 0, bg: 'bg-[#7C3AED]', text: 'text-white', hint: 'Speak to customer' },
    { label: 'Overdue', value: d.sla_overdue ?? 0, bg: 'bg-[#BE185D]', text: 'text-white', hint: 'Act now' },
    { label: 'Responded', value: d.contacted ?? 0, bg: 'bg-[#312E81]', text: 'text-white', hint: 'Customer contacted' },
  ];
  const valueTiles = [
    { label: 'Total lead value', value: inr(d.total_lead_value ?? d.lead_value?.total_lead_value ?? 0), bg: 'bg-[#1e3a5f]', text: 'text-white' },
    { label: 'Total quotation value', value: inr(d.total_quotation_value ?? 0), bg: 'bg-[#b45309]', text: 'text-white' },
    { label: 'Total converted value', value: inr(d.total_converted_lead_value ?? 0), bg: 'bg-[#15803d]', text: 'text-white' },
  ];
  return (
    <div className="space-y-5">
      <PageHeader title={`${greet()}, ${userName}`} subtitle="Welcome back! Your assigned leads, follow-ups and overdue." actions={
        <Link to="/leads" className="btn-primary">View all my leads →</Link>
      } />
      {d.warning && (
        <div className="bg-amber-50 border border-amber-300 text-amber-800 rounded-xl px-4 py-3 text-sm">⚠ {d.warning}</div>
      )}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 md:gap-3 mb-2">
        <div className="min-w-0">
          <div className="text-base sm:text-lg font-bold text-graphite-700 uppercase tracking-wide mb-2 text-center">Summary</div>
          <div className="rounded-xl border border-graphite-200 bg-graphite-50 p-2 sm:p-2.5 md:p-3 shadow-sm">
            <div className="grid grid-cols-2 gap-2 md:gap-3 auto-rows-fr">
              {tiles.map((t) => (
                <div key={t.label} className={`${t.bg} ${t.text} rounded-lg w-full h-full min-h-[6.75rem] sm:min-h-[8rem] md:min-h-[9.75rem] flex flex-col items-center justify-center text-center shadow-sm px-1.5 py-2 sm:px-2 sm:py-3`}>
                  <div className="text-sm sm:text-base uppercase tracking-wide opacity-95 font-bold leading-tight">{t.label}</div>
                  <div className="text-3xl sm:text-4xl font-bold mt-1 sm:mt-1.5 tabular-nums leading-none">{t.value}</div>
                  <div className="text-xs sm:text-sm opacity-85 mt-1 sm:mt-1.5 leading-tight px-0.5">{t.hint}</div>
                </div>
              ))}
            </div>
          </div>
        </div>
        <div className="min-w-0">
          <div className="text-base sm:text-lg font-bold text-graphite-700 uppercase tracking-wide mb-2 text-center">Category</div>
          <div className="rounded-xl border border-graphite-200 bg-graphite-50 p-2 sm:p-2.5 md:p-3 shadow-sm">
            <div className="grid grid-cols-2 gap-2 md:gap-3 auto-rows-fr">
              {categoryTiles.map((t) => (
                <div key={t.label} className={`${t.bg} ${t.text} rounded-lg w-full h-full min-h-[6.75rem] sm:min-h-[8rem] md:min-h-[9.75rem] flex flex-col items-center justify-center text-center shadow-sm px-1.5 py-2 sm:px-2 sm:py-3`}>
                  <div className="text-sm sm:text-base uppercase tracking-wide opacity-95 font-bold leading-tight break-words hyphens-auto">{t.label}</div>
                  <div className="text-3xl sm:text-4xl font-bold mt-1 sm:mt-1.5 tabular-nums leading-none">{mixCount('', t.label)}</div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
      <div className="min-w-0 mt-10 md:mt-14 pt-6 md:pt-8">
        <div className="text-base sm:text-lg font-bold text-graphite-700 uppercase tracking-wide mb-3 text-center">Lead progress</div>
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2 md:gap-3 auto-rows-fr">
          {progressTiles.map((t) => (
            <div key={t.label} className={`${t.bg} ${t.text} rounded-lg w-full h-full min-h-[5.75rem] sm:min-h-[7rem] lg:min-h-[8.25rem] px-2 py-2.5 sm:px-3 sm:py-4 shadow-sm text-center flex flex-col items-center justify-center`}>
              <div className="text-sm sm:text-base uppercase tracking-wide opacity-95 font-bold leading-tight break-words">{t.label}</div>
              <div className="text-3xl sm:text-4xl font-bold mt-1 sm:mt-1.5 tabular-nums leading-none">{mixCount(t.label, '')}</div>
            </div>
          ))}
        </div>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 md:gap-3 mt-6 md:mt-8">
        {valueTiles.map((t) => (
          <div key={t.label} className={`${t.bg} ${t.text} rounded-lg px-3 py-4 sm:py-5 shadow-sm text-center flex flex-col items-center justify-center min-h-[7.5rem] sm:min-h-[8rem]`}>
            <div className="text-base sm:text-lg uppercase tracking-wide opacity-95 font-bold leading-tight">{t.label}</div>
            <div className="text-2xl sm:text-3xl font-bold mt-2 tabular-nums leading-tight break-words">{t.value}</div>
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
        <Card title="Needs attention — overdue" action={<Link to="/leads" className="text-xs text-brand-700 font-semibold hover:underline">All my leads →</Link>}>
          {overduePending.length === 0 ? <EmptyState title="Nothing overdue" hint="All caught up." /> : (
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
                  <th className="th">Enquiry</th><th className="th">Customer</th><th className="th">Contact / Email</th><th className="th text-center">Cars</th><th className="th">Status</th><th className="th">Overdue</th>
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

const REPORT_PROGRESS_BG = PROGRESS_TILE_BG;
const REPORT_CATEGORY_BG = CATEGORY_TILE_BG;

const REPORT_MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];

function reportYears() {
  const end = new Date().getFullYear() + 5;
  const years: number[] = [];
  for (let year = end; year >= 1990; year -= 1) years.push(year);
  return years;
}

function mondayOnOrBefore(d: Date) {
  const monday = new Date(d.getFullYear(), d.getMonth(), d.getDate());
  monday.setDate(monday.getDate() - ((monday.getDay() + 6) % 7));
  return monday;
}

function reportYmd(d: Date) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

/** Add N calendar days to a YYYY-MM-DD string. */
function addDaysYmd(ymd: string, days: number) {
  if (!ymd) return '';
  const d = new Date(`${ymd}T12:00:00`);
  if (Number.isNaN(d.getTime())) return '';
  d.setDate(d.getDate() + days);
  return reportYmd(d);
}

function todayYmd() {
  return reportYmd(new Date());
}

function clampYmdToToday(ymd: string) {
  if (!ymd) return '';
  const today = todayYmd();
  return ymd > today ? today : ymd;
}

function dateInYear(iso: string, year: number) {
  const [, monthText, dayText] = iso.split('-');
  const month = Number(monthText);
  const day = Number(dayText);
  const last = new Date(year, month, 0).getDate();
  return `${year}-${String(month).padStart(2, '0')}-${String(Math.min(day, last)).padStart(2, '0')}`;
}

function ReportBlock({ title, controls, data, loading, error, onPdf, pdfBusy }: {
  title: string;
  controls: any;
  data: any;
  loading: boolean;
  error: string;
  onPdf: () => void;
  pdfBusy: boolean;
}) {
  return (
    <Card title={title} action={(
      <button type="button" className="btn-secondary" disabled={pdfBusy || loading} onClick={onPdf}>
        {pdfBusy ? 'Creating PDF…' : 'Download PDF'}
      </button>
    )}>
      <div className="mb-4">{controls}</div>
      {error ? <p className="text-sm text-red-700">{error}</p> : loading && !data ? <Spinner /> : (
        <>
          <div className="text-xs font-semibold text-graphite-600 uppercase tracking-wide mb-2">Category</div>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
            {(data?.category || []).map((row: any) => (
              <div key={row.label} className={`${REPORT_CATEGORY_BG[row.label] || 'bg-[#64748B]'} ${CATEGORY_TILE_TEXT[row.label] || 'text-white'} rounded-lg px-3 py-3 shadow-sm`}>
                <div className="text-[10px] uppercase tracking-wide opacity-90 font-semibold leading-tight">{row.label}</div>
                <div className="text-2xl font-bold mt-1 tabular-nums">{row.count ?? 0}</div>
              </div>
            ))}
          </div>
          <div className="text-xs font-semibold text-graphite-600 uppercase tracking-wide mt-4 mb-2">Progress</div>
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2">
            {(data?.progress || []).map((row: any) => (
              <div key={row.label} className={`${REPORT_PROGRESS_BG[row.label] || 'bg-[#1e3a5f]'} ${PROGRESS_TILE_TEXT[row.label] || 'text-white'} rounded-lg px-3 py-3 shadow-sm`}>
                <div className="text-[10px] uppercase tracking-wide opacity-90 font-semibold leading-tight">{row.label}</div>
                <div className="text-2xl font-bold mt-1 tabular-nums">{row.count ?? 0}</div>
              </div>
            ))}
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 mt-4">
            {[
              { label: 'Total lead value', value: inr(data?.total_lead_value ?? 0), bg: 'bg-[#1e3a5f]' },
              { label: 'Quotation value', value: inr(data?.total_quotation_value ?? 0), bg: 'bg-[#b45309]' },
              { label: 'Total converted value', value: inr(data?.converted_quotation_value ?? 0), bg: 'bg-[#15803d]' },
            ].map((t) => (
              <div key={t.label} className={`${t.bg} text-white rounded-lg px-3 py-4 shadow-sm text-center`}>
                <div className="text-xs sm:text-sm uppercase tracking-wide opacity-90 font-semibold leading-tight">{t.label}</div>
                <div className="text-xl sm:text-2xl font-bold mt-1.5 tabular-nums leading-tight break-words">{t.value}</div>
              </div>
            ))}
          </div>
          {data?.from && <p className="text-xs text-graphite-500 mt-3">Work logged from {data.from} to {data.to}.</p>}
        </>
      )}
    </Card>
  );
}

function PeriodReportPage({
  title,
  subtitle,
  pickEmployee = false,
}: {
  title: string;
  subtitle: string;
  pickEmployee?: boolean;
}) {
  const years = useMemo(reportYears, []);
  const today = new Date();
  const [employees, setEmployees] = useState<Array<{ id: string; name: string }>>([]);
  const [employeeId, setEmployeeId] = useState('');
  const [monthYear, setMonthYear] = useState(today.getFullYear());
  const [monthIndex, setMonthIndex] = useState(today.getMonth() + 1);
  const [weekYear, setWeekYear] = useState(today.getFullYear());
  const [weekFrom, setWeekFrom] = useState(() => reportYmd(today));
  const [weekTo, setWeekTo] = useState(() => addDaysYmd(reportYmd(today), 6));
  const month = `${monthYear}-${String(monthIndex).padStart(2, '0')}`;
  const [monthData, setMonthData] = useState<any>(null);
  const [weekData, setWeekData] = useState<any>(null);
  const [monthErr, setMonthErr] = useState('');
  const [weekErr, setWeekErr] = useState('');
  const [monthLoading, setMonthLoading] = useState(!pickEmployee);
  const [weekLoading, setWeekLoading] = useState(!pickEmployee);
  const [pdfBusy, setPdfBusy] = useState<'month' | 'week' | ''>('');
  const [pdfErr, setPdfErr] = useState('');
  const ready = !pickEmployee || Boolean(employeeId);
  const selectedName = employees.find((e) => e.id === employeeId)?.name || '';

  useEffect(() => {
    if (!pickEmployee) return;
    api.get('/masters').then((r) => {
      const list = (r.data?.employees || []) as Array<{ id: string; name: string }>;
      setEmployees(list);
      if (list.length && !employeeId) setEmployeeId(list[0].id);
    }).catch(() => setEmployees([]));
  }, [pickEmployee]);

  function withEmployee(params: Record<string, string>) {
    if (pickEmployee && employeeId) params.employee_id = employeeId;
    return params;
  }

  async function downloadPdf(mode: 'month' | 'week') {
    if (!ready) return;
    setPdfBusy(mode);
    setPdfErr('');
    try {
      const params: Record<string, string> = withEmployee({ mode });
      if (mode === 'month') params.month = month;
      else { params.from_date = weekFrom; params.to_date = weekTo; }
      const who = selectedName ? selectedName.replace(/[^\w.-]+/g, '-') : 'my';
      const filename = mode === 'month'
        ? `report-${who}-${month}.pdf`
        : `report-${who}-${weekFrom}-to-${weekTo}.pdf`;
      await downloadReport('/dashboard/period-report/pdf', filename, params);
    } catch (e: any) {
      setPdfErr(e?.message || 'Could not download the PDF');
    } finally {
      setPdfBusy('');
    }
  }

  useEffect(() => {
    if (!month || !ready) {
      setMonthData(null);
      setMonthLoading(false);
      return;
    }
    const ctrl = new AbortController();
    setMonthLoading(true);
    setMonthErr('');
    api.get('/dashboard/period-report', { params: withEmployee({ mode: 'month', month }), signal: ctrl.signal })
      .then((r) => setMonthData(r.data))
      .catch((e: any) => { if (!ctrl.signal.aborted) setMonthErr(e?.response?.data?.detail || 'Could not load the monthly report'); })
      .finally(() => { if (!ctrl.signal.aborted) setMonthLoading(false); });
    return () => ctrl.abort();
  }, [month, ready, employeeId]);

  useEffect(() => {
    if (!ready) {
      setWeekData(null);
      setWeekLoading(false);
      return;
    }
    if (!weekFrom || !weekTo || weekFrom > weekTo) {
      setWeekLoading(false);
      setWeekErr('From date must be on or before to date');
      return;
    }
    const ctrl = new AbortController();
    setWeekLoading(true);
    setWeekErr('');
    api.get('/dashboard/period-report', {
      params: withEmployee({ mode: 'week', from_date: weekFrom, to_date: weekTo }),
      signal: ctrl.signal,
    })
      .then((r) => setWeekData(r.data))
      .catch((e: any) => { if (!ctrl.signal.aborted) setWeekErr(e?.response?.data?.detail || 'Could not load the weekly report'); })
      .finally(() => { if (!ctrl.signal.aborted) setWeekLoading(false); });
    return () => ctrl.abort();
  }, [weekFrom, weekTo, ready, employeeId]);

  return (
    <div className="space-y-5">
      <PageHeader title={title} subtitle={subtitle} />
      {pickEmployee && (
        <Card title="Employee">
          <label className="text-sm block max-w-sm">Choose employee
            <select className="input mt-1" value={employeeId} onChange={(e) => setEmployeeId(e.target.value)}>
              {!employees.length && <option value="">No employees found</option>}
              {employees.map((emp) => (
                <option key={emp.id} value={emp.id}>{emp.name}</option>
              ))}
            </select>
          </label>
          {selectedName && (
            <p className="text-xs text-graphite-500 mt-2">Showing work history for <span className="font-medium text-graphite-700">{selectedName}</span>.</p>
          )}
        </Card>
      )}
      {pdfErr && <div className="bg-red-50 border border-red-200 text-red-700 text-sm rounded-xl px-4 py-3">{pdfErr}</div>}
      {!ready ? (
        <Card><EmptyState title="Choose an employee" hint="Pick a staff member to see their monthly and weekly report history." /></Card>
      ) : (
        <>
          <ReportBlock
            title={pickEmployee && selectedName ? `Monthly · ${selectedName}` : 'Monthly'}
            data={monthData}
            loading={monthLoading}
            error={monthErr}
            pdfBusy={pdfBusy === 'month'}
            onPdf={() => { void downloadPdf('month'); }}
            controls={(
              <div className="flex flex-wrap items-end gap-3">
                <label className="text-sm block w-[140px]">Year
                  <select className="input mt-1" value={monthYear} onChange={(e) => setMonthYear(Number(e.target.value))}>
                    {years.map((year) => <option key={year} value={year}>{year}</option>)}
                  </select>
                </label>
                <label className="text-sm block w-[180px]">Month
                  <select className="input mt-1" value={monthIndex} onChange={(e) => setMonthIndex(Number(e.target.value))}>
                    {REPORT_MONTHS.map((name, index) => <option key={name} value={index + 1}>{name}</option>)}
                  </select>
                </label>
              </div>
            )}
          />
          <ReportBlock
            title={pickEmployee && selectedName ? `Weekly · ${selectedName}` : 'Weekly'}
            data={weekData}
            loading={weekLoading}
            error={weekErr}
            pdfBusy={pdfBusy === 'week'}
            onPdf={() => { void downloadPdf('week'); }}
            controls={(
              <div className="flex flex-wrap items-end gap-3">
                <label className="text-sm block w-[140px]">Year
                  <select
                    className="input mt-1"
                    value={weekYear}
                    onChange={(e) => {
                      const year = Number(e.target.value);
                      setWeekYear(year);
                      setWeekFrom((currentFrom) => {
                        const nextFrom = clampYmdToToday(dateInYear(currentFrom, year));
                        setWeekTo(addDaysYmd(nextFrom, 6));
                        return nextFrom;
                      });
                    }}
                  >
                    {years.map((year) => <option key={year} value={year}>{year}</option>)}
                  </select>
                </label>
                <label className="text-sm block w-[180px]">Week start
                  <input
                    type="date"
                    className="input mt-1"
                    max={reportYmd(today)}
                    value={weekFrom}
                    onChange={(e) => {
                      const value = clampYmdToToday(e.target.value);
                      if (!value) return;
                      setWeekFrom(value);
                      setWeekYear(Number(value.slice(0, 4)));
                      setWeekTo(addDaysYmd(value, 6));
                    }}
                  />
                </label>
                <label className="text-sm block w-[180px]">Week end (auto +6 days)
                  <input
                    type="date"
                    className="input mt-1 bg-graphite-50"
                    value={weekTo}
                    readOnly
                    title="Automatically set to 7 days from the start date"
                  />
                </label>
              </div>
            )}
          />
        </>
      )}
    </div>
  );
}

export function EmployeeReport() {
  return (
    <PeriodReportPage
      title="My reports"
      subtitle="How many site visits, follow-ups and other progress you logged, and the category, for a month or a week."
    />
  );
}

export function ReportHistory() {
  return (
    <PeriodReportPage
      title="Employee report history"
      subtitle="Employee-wise work history — the same monthly and weekly progress report employees see for themselves."
      pickEmployee
    />
  );
}

/* ================= QUOTATION FORM (employee) — Word-like letter ================= */
function inrIndian(n: number) {
  const v = Math.round(Math.abs(n || 0));
  const s = String(v);
  if (s.length <= 3) return (n < 0 ? '-' : '') + s;
  const last3 = s.slice(-3);
  let rest = s.slice(0, -3);
  const parts: string[] = [];
  while (rest.length) {
    parts.unshift(rest.slice(-2));
    rest = rest.slice(0, -2);
  }
  return `${n < 0 ? '-' : ''}${parts.join(',')},${last3}`;
}

function arrowStep(value: string, key: string, step = 1, min = 0) {
  if (key !== 'ArrowUp' && key !== 'ArrowDown') return null;
  const raw = String(value ?? '').replace(/,/g, '').trim();
  if (!raw) return String(min);
  const current = Number(raw);
  const base = Number.isFinite(current) ? current : min;
  const next = Math.max(min, base + (key === 'ArrowUp' ? step : -step));
  const rounded = Math.round(next * 100) / 100;
  return Number.isInteger(rounded) ? String(rounded) : String(rounded);
}

function quoteDocField({
  multiline,
  className,
  readOnly,
  onKeyDown,
  onChange,
  ...rest
}: {
  multiline?: boolean;
  className?: string;
  readOnly?: boolean;
  onKeyDown?: (e: any) => void;
  onChange?: (e: any) => void;
  [key: string]: any;
}) {
  const box = useRef<HTMLTextAreaElement>(null);
  const value = rest.value;
  useLayoutEffect(() => {
    const el = box.current;
    if (!el) return;
    el.style.height = '0px';
    el.style.height = `${el.scrollHeight}px`;
  }, [value, multiline]);
  const base = readOnly
    ? 'bg-transparent border-0 border-b border-transparent px-0.5 py-0.5 w-full min-w-0 text-[15px] leading-snug cursor-default'
    : 'bg-transparent border-0 border-b border-dashed border-sky-400/80 outline-none focus:border-brand-600 focus:bg-amber-50/40 px-0.5 py-0.5 w-full min-w-0 text-[15px] leading-snug';
  const handleKeyDown = (e: any) => {
    onKeyDown?.(e);
    if (e.defaultPrevented || multiline || readOnly) return;
    const numeric = rest.inputMode === 'numeric' || rest.type === 'number';
    if (!numeric) return;
    const step = Number(rest.step) > 0 ? Number(rest.step) : 1;
    const min = rest.min === undefined || rest.min === '' ? 0 : Number(rest.min);
    const next = arrowStep(String(rest.value ?? ''), e.key, step, Number.isFinite(min) ? min : 0);
    if (next == null) return;
    e.preventDefault();
    onChange?.({ target: { value: next } });
  };
  if (multiline) {
    return (
      <textarea
        {...rest}
        ref={box}
        readOnly={readOnly}
        rows={2}
        onChange={onChange}
        onKeyDown={handleKeyDown}
        className={`${base} whitespace-pre-wrap resize-none overflow-hidden ${className || ''}`}
      />
    );
  }
  return <input {...rest} readOnly={readOnly} onChange={onChange} onKeyDown={handleKeyDown} className={`${base} ${className || ''}`} />;
}

function QuoteField(props: any) {
  return quoteDocField(props);
}

function QuotationFormModal({
  lead,
  onClose,
  onSaved,
  startInEdit = true,
}: {
  lead: any;
  onClose: () => void;
  onSaved: (leadId: string, summary: any) => void;
  startInEdit?: boolean;
}) {
  const defaultPayment =
    '1. 60% Advance along with P.O\n2. 30% Advance for Structural Erection & Procurement\n3. 10% on successful Testing & Commissioning';
  const defaultDelivery =
    '1. 2 - 3 Months from the date of receipt of Advance payment along with PO or on-site readiness condition.';
  const defaultWarranty =
    '1. After the warranty period AMC is applicable.\n2. 3 - 4% of the Total cost per unit/year will be approximately charged for AMC.';
  const defaultIntroduction =
    'E STAR Engineers Private Limited is a high-end Automated Multilevel Car/Auto/Bike Parking System, Design & Manufacturing Company in Association with International Tycoons from Japan, Germany & Korea, also a Group Company of MECHCI since 1995.';
  const [form, setForm] = useState({
    to_name: '',
    to_address: '',
    subject: '',
    introduction: defaultIntroduction,
    product_description: 'Design, Manufacture, Supply and Erection of Parking System',
    payment_terms: defaultPayment,
    delivery_period: defaultDelivery,
    post_warranty: defaultWarranty,
    unit_cost: '',
    units: '',
    extra_lines: [] as { description: string; unit_cost: string; units: string }[],
    quotation_date: new Date().toISOString().slice(0, 10),
    quotation_number: '',
    revision: 'R0',
  });
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const [ok, setOk] = useState('');
  // After Save → preview (locked). Click Edit to change again (follow-up → next Rn).
  const [editing, setEditing] = useState(true);
  const [dirty, setDirty] = useState(false);
  const [savedOnce, setSavedOnce] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true); setErr(''); setOk('');
    api.get(`/leads/${lead.id}/quotation-form`)
      .then((r) => {
        if (cancelled) return;
        const d = r.data || {};
        // issued = form was saved (Q count reserved). preview = next count shown only.
        const alreadySaved = Boolean(d.issued) && Boolean(d.id) && Boolean(d.quotation_number);
        setForm({
          to_name: d.to_name || '',
          to_address: d.to_address || '',
          subject: d.subject || '',
          introduction: d.introduction != null && d.introduction !== undefined ? d.introduction : defaultIntroduction,
          product_description: d.product_description || 'Design, Manufacture, Supply and Erection of Parking System',
          payment_terms: d.payment_terms || defaultPayment,
          delivery_period: (() => {
            const value = (d.delivery_period || '').trim();
            const unnumbered = '2 - 3 Months from the date of receipt of Advance payment along with PO or on-site readiness condition.';
            if (!value || value === unnumbered) return defaultDelivery;
            return d.delivery_period;
          })(),
          post_warranty: d.post_warranty || defaultWarranty,
          unit_cost: d.unit_cost != null ? String(d.unit_cost) : '',
          units: d.units != null ? String(d.units) : '',
          extra_lines: Array.isArray(d.extra_lines) ? d.extra_lines.map((line: any) => ({
            description: line.description || '',
            unit_cost: line.unit_cost != null ? String(line.unit_cost) : '',
            units: line.units != null ? String(line.units) : '1',
          })) : [],
          quotation_date: (d.quotation_date || '').slice(0, 10) || new Date().toISOString().slice(0, 10),
          quotation_number: d.quotation_number || '',
          revision: d.revision || 'R0',
        });
        setSavedOnce(alreadySaved);
        setEditing(Boolean(startInEdit) || !alreadySaved);
        setDirty(false);
        // Table REF only after Save — opening must not reserve / show count in the list.
        if (alreadySaved) {
          onSaved(lead.id, {
            id: d.id,
            quotation_number: d.quotation_number,
            revision: d.revision || 'R0',
            amount_excl: d.amount_excl,
            gst: d.gst,
            grand_total: d.grand_total,
            units: d.units,
            unit_cost: d.unit_cost,
          });
        }
      })
      .catch((e: any) => { if (!cancelled) setErr(e?.response?.data?.detail || 'Could not load quotation form'); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [lead.id, startInEdit]);

  const rowAmount = (cost: string, qty: string) => {
    const c = Number(cost) || 0;
    let q = Number(qty);
    if (!Number.isFinite(q) || q <= 0) q = c ? 1 : 0;
    return Math.round(c * q);
  };
  const unitCost = Number(form.unit_cost) || 0;
  const units = Number(form.units) || 0;
  const amountExcl = rowAmount(form.unit_cost, form.units) + form.extra_lines.reduce((sum, line) => sum + rowAmount(line.unit_cost, line.units), 0);
  const gst = Math.round(amountExcl * 0.18);
  const grand = amountExcl + gst;
  const dateDisp = (() => {
    try {
      const [y, m, d] = (form.quotation_date || '').split('-');
      if (y && m && d) return `${d}-${m}-${y}`;
    } catch { /* ignore */ }
    return form.quotation_date;
  })();
  const refShown = (() => {
    const number = form.quotation_number || '';
    const parts = (form.quotation_date || '').split('-');
    if (!number || parts.length < 3) return number;
    const day = parts[2];
    const month = parts[1];
    if (!day || !month) return number;
    const ddmm = `${day.padStart(2, '0')}${month.padStart(2, '0')}`;
    return number.replace(/^EEPLCP\d{4}/, `EEPLCP${ddmm}`);
  })();

  const set = (patch: Partial<typeof form>) => {
    if (!editing) return;
    setForm((cur) => ({ ...cur, ...patch }));
    setDirty(true);
  };

  const payload = () => ({
    to_name: form.to_name.trim(),
    to_address: form.to_address.trim(),
    subject: form.subject.trim(),
    introduction: form.introduction,
    product_description: form.product_description.trim(),
    payment_terms: form.payment_terms.trim(),
    delivery_period: form.delivery_period.trim(),
    post_warranty: form.post_warranty.trim(),
    unit_cost: unitCost,
    units,
    quotation_date: form.quotation_date || undefined,
    extra_lines: form.extra_lines
      .filter((line) => (line.description || '').trim() || Number(line.unit_cost))
      .map((line) => ({
        description: (line.description || '').trim(),
        unit_cost: Number(line.unit_cost) || 0,
        units: Number(line.units) > 0 ? Number(line.units) : 1,
      })),
  });

  const applySaved = (data: any) => {
    setForm((cur) => ({
      ...cur,
      quotation_number: data.quotation_number || cur.quotation_number,
      revision: data.revision || cur.revision,
      unit_cost: data.unit_cost != null ? String(data.unit_cost) : cur.unit_cost,
      units: data.units != null ? String(data.units) : cur.units,
      extra_lines: Array.isArray(data.extra_lines) ? data.extra_lines.map((line: any) => ({
        description: line.description || '',
        unit_cost: line.unit_cost != null ? String(line.unit_cost) : '',
        units: line.units != null ? String(line.units) : '1',
      })) : cur.extra_lines,
      payment_terms: data.payment_terms || cur.payment_terms,
      delivery_period: data.delivery_period || cur.delivery_period,
      post_warranty: data.post_warranty || cur.post_warranty,
      introduction: data.introduction != null ? data.introduction : cur.introduction,
    }));
    onSaved(lead.id, {
      quotation_number: data.quotation_number,
      revision: data.revision,
      grand_total: data.grand_total,
      amount_excl: data.amount_excl,
    });
    setSavedOnce(true);
    setDirty(false);
    setEditing(false);
  };

  const save = async () => {
    if (!form.to_name.trim()) { setErr('To name is required'); return false; }
    if (!(unitCost >= 0) || !(units > 0)) { setErr('Enter unit cost and number of units'); return false; }
    setBusy(true); setErr(''); setOk('');
    try {
      const { data } = await api.put(`/leads/${lead.id}/quotation-form`, payload());
      applySaved(data);
      setOk(
        `Saved ${data.quotation_number} (${data.revision}). `
        + 'First save stays R0. Edit again and save to make the next download R1, then R2.',
      );
      return true;
    } catch (e: any) {
      setErr(e?.response?.data?.detail || 'Save failed');
      return false;
    } finally { setBusy(false); }
  };

  const downloadPdfOnly = async (numberHint?: string) => {
    const res = await api.get(`/leads/${lead.id}/quotation-form/pdf`, { responseType: 'blob' });
    const url = URL.createObjectURL(res.data);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${numberHint || form.quotation_number || 'quotation'}.pdf`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 2000);
  };

  const downloadPdf = async () => {
    setBusy(true); setErr(''); setOk('');
    try {
      // If editing with changes, save first (bumps Rn for follow-up). Else download last saved as-is.
      if (editing && dirty) {
        const { data } = await api.put(`/leads/${lead.id}/quotation-form`, payload());
        applySaved(data);
        await downloadPdfOnly(data.quotation_number);
        setOk(`Saved ${data.quotation_number} (${data.revision}) and downloaded PDF. Edit again and save for the next revision.`);
      } else if (!form.quotation_number && !savedOnce) {
        const { data } = await api.put(`/leads/${lead.id}/quotation-form`, payload());
        applySaved(data);
        await downloadPdfOnly(data.quotation_number);
        setOk(`Saved ${data.quotation_number} (${data.revision}) and downloaded PDF.`);
      } else {
        await downloadPdfOnly();
        setOk(`Downloaded ${form.quotation_number} (${form.revision}). Click Edit to revise for the next follow-up.`);
      }
    } catch (e: any) {
      setErr(e?.response?.data?.detail || 'PDF download failed — save the form first');
    } finally { setBusy(false); }
  };

  const startEdit = () => {
    setEditing(true);
    setDirty(false);
    setOk('Editing — change the quote, then Save. The first saved download is R0. The next edit and save becomes R1.');
    setErr('');
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/45 flex items-center justify-center p-3 sm:p-6" onClick={onClose}>
      <div
        className="w-full max-w-4xl max-h-[94vh] flex flex-col rounded-xl overflow-hidden shadow-2xl bg-[#cfcfcf]"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between gap-3 px-4 py-2.5 bg-[#2b579a] text-white shrink-0">
          <div className="min-w-0">
            <div className="text-sm font-semibold tracking-wide">
              Quotation — {editing ? 'Editing' : 'Preview'}
            </div>
            <div className="text-[11px] text-white/80 truncate">
              {lead.enquiry_number} · REF {form.quotation_number || '…'} · {form.revision}
              {dirty ? ' · unsaved changes' : ''}
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2 shrink-0">
            {!editing ? (
              <button type="button" className="bg-amber-400 hover:bg-amber-300 text-[#1e3a5f] text-xs font-semibold px-3 py-1.5 rounded" disabled={busy} onClick={startEdit}>
                Edit
              </button>
            ) : null}
            <button type="button" className="bg-white/15 hover:bg-white/25 text-white text-xs px-3 py-1.5 rounded" disabled={busy} onClick={() => void downloadPdf()}>
              {busy ? 'Working…' : (editing && dirty ? 'Save & PDF' : 'Download PDF')}
            </button>
            {editing ? (
              <button type="button" className="bg-white text-[#2b579a] text-xs font-semibold px-3 py-1.5 rounded" disabled={busy} onClick={() => void save()}>
                {busy ? 'Saving…' : 'Save'}
              </button>
            ) : null}
            <button type="button" className="bg-white/15 hover:bg-white/25 text-white text-xs px-3 py-1.5 rounded" onClick={onClose}>Close</button>
          </div>
        </div>

        <div className="px-4 py-2 bg-[#1e4a7a] text-[11px] text-white/90 font-sans shrink-0">
          {editing
            ? 'Edit mode — first Save and PDF stays R0. Edit again, save, and the next PDF is R1.'
            : 'Preview — Download PDF keeps this revision. Click Edit, change, and Save to move R0 to R1.'}
        </div>

        <div className="flex-1 overflow-auto px-3 sm:px-8 py-5">
          {loading ? <div className="flex justify-center py-16"><Spinner /></div> : (
            <div
              className="mx-auto bg-white shadow-lg w-full max-w-[210mm] min-w-[280px] min-h-[297mm] px-4 sm:px-[14mm] pt-[10mm] pb-[8mm] text-[15px] text-slate-800 relative"
              style={{ fontFamily: '"Times New Roman", Times, Georgia, serif' }}
            >
              {err && <div className="mb-3 text-sm text-red-700 bg-red-50 border border-red-200 rounded px-3 py-2 font-sans">{err}</div>}
              {ok && <div className="mb-3 text-sm text-emerald-800 bg-emerald-50 border border-emerald-200 rounded px-3 py-2 font-sans">{ok}</div>}

              <div className="relative mb-5 pt-4">
                <div className="flex justify-center">
                  <div className="relative inline-block">
                    <div className="absolute -top-4 left-0 right-0 flex text-[10px] text-slate-700 pointer-events-none">
                      <span className="w-[38%] text-center tracking-wide">GURUKRIBA</span>
                      <span className="flex-1 text-center">Sree Laal SidthBabaji</span>
                    </div>
                    <img src="/quote-letterhead-logo.jpg" alt="E STAR Engineers" className="h-14 object-contain" onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }} />
                  </div>
                </div>
              </div>

              <div className="flex items-baseline justify-between gap-4 mb-6">
                <div className="flex items-baseline gap-2 min-w-0">
                  <span className="font-bold shrink-0">REF:</span>
                  <span className="font-semibold text-[#1e3a5f] tracking-wide">{refShown || '—'}</span>
                  {!savedOnce && refShown ? (
                    <span className="text-xs text-graphite-500 font-sans ml-1">(preview — count after Save)</span>
                  ) : null}
                </div>
                <div className="flex items-baseline gap-2 shrink-0 ml-auto">
                  <span className="font-bold">Date:</span>
                  <QuoteField readOnly={!editing}
                    type="date"
                    value={form.quotation_date}
                    onChange={(e: any) => set({ quotation_date: e.target.value })}
                    className="!w-auto font-sans text-sm"
                  />
                  <span className="text-graphite-500 text-sm font-sans">({dateDisp})</span>
                </div>
              </div>

              <div className="mb-1 font-bold">To</div>
              <QuoteField readOnly={!editing}
                multiline
                value={form.to_name}
                onChange={(e: any) => set({ to_name: e.target.value })}
                placeholder="Company / Customer name"
                className="font-bold mb-1"
              />
              <QuoteField readOnly={!editing}
                multiline
                value={form.to_address}
                onChange={(e: any) => set({ to_address: e.target.value })}
                placeholder="Address"
                className="text-[14px] mb-5 font-bold"
              />

              <p className="mb-4 font-bold">Dear Sir,</p>

              <div className="flex items-baseline gap-2 mb-4">
                <span className="font-bold shrink-0">Sub: -</span>
                <QuoteField readOnly={!editing}
                  value={form.subject}
                  onChange={(e: any) => set({ subject: e.target.value })}
                  placeholder="Offer for Parking System"
                  className="font-bold"
                />
              </div>

              <QuoteField readOnly={!editing}
                multiline
                value={form.introduction}
                onChange={(e: any) => set({ introduction: e.target.value })}
                placeholder="Paragraph after the subject"
                className="mb-6 text-justify leading-relaxed"
              />

              <table className="w-full border-collapse text-[13px] mb-6" style={{ fontFamily: 'Helvetica, Arial, sans-serif' }}>
                <thead>
                  <tr className="bg-[#1e3a5f] text-white">
                    <th className="border border-slate-400 px-2 py-2 w-14">S. No</th>
                    <th className="border border-slate-400 px-2 py-2 text-left">Description</th>
                    <th className="border border-slate-400 px-2 py-2 w-[22%]">Unit Cost (INR)</th>
                    <th className="border border-slate-400 px-2 py-2 w-[14%]">No of Units</th>
                    <th className="border border-slate-400 px-2 py-2 w-[18%]">Total Cost (INR)</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td className="border border-slate-400 px-2 py-2 text-center align-middle">1</td>
                    <td className="border border-slate-400 px-2 py-2 align-top">
                      <QuoteField readOnly={!editing}
                        multiline
                        value={form.product_description}
                        onChange={(e: any) => set({ product_description: e.target.value })}
                        className="!border-b-slate-300 min-h-[44px] text-[13px]"
                      />
                    </td>
                    <td className="border border-slate-400 px-2 py-2 text-center align-middle">
                      <QuoteField readOnly={!editing}
                        inputMode="numeric"
                        value={form.unit_cost}
                        onChange={(e: any) => set({ unit_cost: e.target.value.replace(/[^\d]/g, '') })}
                        className="text-center tabular-nums"
                      />
                    </td>
                    <td className="border border-slate-400 px-2 py-2 text-center align-middle">
                      <QuoteField readOnly={!editing}
                        inputMode="numeric"
                        value={form.units}
                        onChange={(e: any) => set({ units: e.target.value.replace(/[^\d.]/g, '') })}
                        className="text-center tabular-nums"
                      />
                    </td>
                    <td className="border border-slate-400 px-2 py-2 text-center align-middle tabular-nums font-medium">
                      {inrIndian(rowAmount(form.unit_cost, form.units))}
                    </td>
                  </tr>
                  {form.extra_lines.map((line, index) => (
                    <tr key={index}>
                      <td className="border border-slate-400 px-2 py-2 text-center align-middle">
                        <div className="flex items-center justify-center gap-1">
                          <span>{index + 2}</span>
                          {editing && (
                            <button
                              type="button"
                              className="text-slate-400 hover:text-red-600 leading-none"
                              title="Remove row"
                              onClick={() => {
                                setForm((cur) => ({ ...cur, extra_lines: cur.extra_lines.filter((_, i) => i !== index) }));
                                setDirty(true);
                              }}
                            >
                              ├ù
                            </button>
                          )}
                        </div>
                      </td>
                      <td className="border border-slate-400 px-2 py-2 align-top">
                        <QuoteField readOnly={!editing}
                          value={line.description}
                          onChange={(e: any) => {
                            const description = e.target.value;
                            setForm((cur) => ({
                              ...cur,
                              extra_lines: cur.extra_lines.map((row, i) => i === index ? { ...row, description } : row),
                            }));
                            setDirty(true);
                          }}
                          placeholder="Transport"
                          className="text-[13px]"
                        />
                      </td>
                      <td className="border border-slate-400 px-2 py-2 text-center align-middle">
                        <QuoteField readOnly={!editing}
                          inputMode="numeric"
                          value={line.unit_cost}
                          onChange={(e: any) => {
                            const unit_cost = e.target.value.replace(/[^\d]/g, '');
                            setForm((cur) => ({
                              ...cur,
                              extra_lines: cur.extra_lines.map((row, i) => i === index ? { ...row, unit_cost } : row),
                            }));
                            setDirty(true);
                          }}
                          className="text-center tabular-nums"
                        />
                      </td>
                      <td className="border border-slate-400 px-2 py-2 text-center align-middle">
                        <QuoteField readOnly={!editing}
                          inputMode="numeric"
                          value={line.units}
                          onChange={(e: any) => {
                            const unitsValue = e.target.value.replace(/[^\d.]/g, '');
                            setForm((cur) => ({
                              ...cur,
                              extra_lines: cur.extra_lines.map((row, i) => i === index ? { ...row, units: unitsValue } : row),
                            }));
                            setDirty(true);
                          }}
                          className="text-center tabular-nums"
                        />
                      </td>
                      <td className="border border-slate-400 px-2 py-2 text-center align-middle tabular-nums font-medium">
                        {inrIndian(rowAmount(line.unit_cost, line.units))}
                      </td>
                    </tr>
                  ))}
                  {editing && (
                    <tr>
                      <td className="border border-slate-400 px-2 py-1" colSpan={5}>
                        <button
                          type="button"
                          className="font-bold text-[#1e3a5f] px-1 leading-none text-lg"
                          title="Add a row"
                          onClick={() => {
                            setForm((cur) => ({
                              ...cur,
                              extra_lines: [...cur.extra_lines, { description: '', unit_cost: '', units: '1' }],
                            }));
                            setDirty(true);
                          }}
                        >
                          +
                        </button>
                      </td>
                    </tr>
                  )}
                  <tr>
                    <td className="border border-slate-400 px-2 py-2" />
                    <td className="border border-slate-400 px-2 py-2 font-bold">Total</td>
                    <td className="border border-slate-400 px-2 py-2" colSpan={2} />
                    <td className="border border-slate-400 px-2 py-2 text-center tabular-nums font-bold">{inrIndian(amountExcl)}</td>
                  </tr>
                  <tr>
                    <td className="border border-slate-400 px-2 py-2" />
                    <td className="border border-slate-400 px-2 py-2">GST 18%</td>
                    <td className="border border-slate-400 px-2 py-2" colSpan={2} />
                    <td className="border border-slate-400 px-2 py-2 text-center tabular-nums">{inrIndian(gst)}</td>
                  </tr>
                  <tr className="bg-slate-100 font-bold">
                    <td className="border border-slate-400 px-2 py-2" />
                    <td className="border border-slate-400 px-2 py-2">GRAND TOTAL (INR)</td>
                    <td className="border border-slate-400 px-2 py-2" colSpan={2} />
                    <td className="border border-slate-400 px-2 py-2 text-center tabular-nums">{inrIndian(grand)}</td>
                  </tr>
                </tbody>
              </table>

              <div className="space-y-5 text-[13.5px] leading-relaxed">
                <div>
                  <div className="font-bold mb-2">General Terms &amp; Conditions:</div>
                  <ol className="list-decimal pl-5 space-y-1">
                    <li>GST and Other Taxes as extra applicable.</li>
                    <li>This offer is valid for 15 days only.</li>
                    <li>One-year Warranty and Maintenance on the installed system.</li>
                  </ol>
                </div>
                <div>
                  <div className="font-bold mb-2">Customer Scope:</div>
                  <ol className="list-decimal pl-5 space-y-1">
                    <li>Approval from the Competent Authority. Site Clearance if required.</li>
                    <li>Civil Foundations, Civil Works and Cladding are Additional</li>
                    <li>3 Phase Power Supply. Stabilized Power &amp; dedicated Earth for installation and operation to be provided by the Client.</li>
                    <li>The Client must provide an appropriate storage area at the site.</li>
                  </ol>
                </div>

                <div className="border-t-2 border-dashed border-slate-300 pt-6 mt-8">
                  <div className="text-[10px] uppercase tracking-widest text-slate-400 font-sans mb-4">Page 2</div>
                  <div className="space-y-5">
                    <div>
                      <div className="font-bold mb-2">Payment Terms:</div>
                      <QuoteField readOnly={!editing}
                        multiline
                        value={form.payment_terms}
                        onChange={(e: any) => set({ payment_terms: e.target.value })}
                        className="min-h-[72px] text-[13.5px] whitespace-pre-wrap"
                      />
                    </div>
                    <div>
                      <div className="font-bold mb-2">Delivery Period:</div>
                      <QuoteField readOnly={!editing}
                        multiline
                        value={form.delivery_period}
                        onChange={(e: any) => set({ delivery_period: e.target.value })}
                        className="min-h-[52px] text-[13.5px] whitespace-pre-wrap"
                      />
                    </div>
                    <div>
                      <div className="font-bold mb-2">Post Warranty:</div>
                      <QuoteField readOnly={!editing}
                        multiline
                        value={form.post_warranty}
                        onChange={(e: any) => set({ post_warranty: e.target.value })}
                        className="min-h-[52px] text-[13.5px] whitespace-pre-wrap"
                      />
                    </div>
                    <div className="pt-4">
                      <p className="mb-1">Regards,</p>
                      <p className="mb-3">For, <b>ESTAR ENGINEERS PRIVATE LIMITED</b></p>
                      <img
                        src="/quote-signature.jpg"
                        alt="Signature"
                        className="h-16 w-auto object-contain mb-1"
                        onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }}
                      />
                      <p className="font-bold">JAYARAMAN K</p>
                      <p className="font-bold">Director</p>
                    </div>
                    <div className="pt-4">
                      <div className="font-bold mb-2">BANKING DETAILS:</div>
                      <p>Account Name: E STAR ENGINEERS PRIVATE LIMITED</p>
                      <p>Account Number: 8428210000009812</p>
                      <p>Bank Name: DBS Bank</p>
                      <p>Branch Name: Chennai</p>
                      <p>Any RTGS/NEFT to our IFSC code: DBSS0IN0428</p>
                    </div>
                  </div>
                </div>
              </div>

              <div className="mt-8 pt-3 border-t border-slate-100">
                <img
                  src="/quote-footer-banner.jpg"
                  alt="E STAR address"
                  className="w-full object-contain"
                  onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }}
                />
              </div>

              <p className="mt-3 text-[11px] text-slate-400 font-sans">
                {editing
                  ? 'Dashed underlines = editable. Save, then Edit again for the next follow-up (R0 → R1 → R2…). Download PDF anytime.'
                  : 'Preview mode. Click Edit to revise for a follow-up, or Download PDF for this revision.'}
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

/* ================= LEADS ================= */
const REPEATABLE_PROGRESS = new Set(['In Followup', 'Meeting', 'Site Visit', 'Quotation sent']);

function AutoGrowRemarks({
  value,
  onChange,
  className = '',
  minHeight = 120,
  ...rest
}: {
  value: string;
  onChange: (e: { target: { value: string } }) => void;
  className?: string;
  minHeight?: number;
  [key: string]: any;
}) {
  const ref = useRef<HTMLTextAreaElement>(null);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${Math.max(el.scrollHeight, minHeight)}px`;
  }, [value, minHeight]);
  return (
    <textarea
      {...rest}
      ref={ref}
      rows={3}
      value={value}
      onChange={onChange}
      className={`input text-sm resize-none overflow-hidden ${className}`}
      style={{ minHeight }}
    />
  );
}

function progressOrdinal(n: number) {
  const mod100 = n % 100;
  const mod10 = n % 10;
  const suffix = mod100 >= 11 && mod100 <= 13 ? 'th' : mod10 === 1 ? 'st' : mod10 === 2 ? 'nd' : mod10 === 3 ? 'rd' : 'th';
  return `${n}${suffix}`;
}

function shortProgressName(action: string) {
  return action === 'In Followup' ? 'Followup' : action;
}

function formatProgressOccurrence(action: string, occurrence: number) {
  if (!action || action === '—') return '—';
  if (!REPEATABLE_PROGRESS.has(action)) return action;
  const name = shortProgressName(action);
  return `${progressOrdinal(occurrence)} ${name}`;
}

function labeledProgressHistory(history: any[] | undefined) {
  const counts: Record<string, number> = {};
  return (history || []).map((entry) => {
    const action = entry.work_action || '';
    if (REPEATABLE_PROGRESS.has(action)) {
      counts[action] = (counts[action] || 0) + 1;
      return { ...entry, displayAction: formatProgressOccurrence(action, counts[action]) };
    }
    return { ...entry, displayAction: action || '—' };
  });
}

function countProgressAction(history: any[] | undefined, action: string) {
  return (history || []).filter((h) => (h.work_action || '') === action).length;
}

export function Leads() {
  const role = localStorage.getItem('role') || '';
  const tableScroll = useDragScroll<HTMLDivElement>();
  const reviewOptions = ['A+ (Immediate)', 'A (3-6 months)', 'B (6-9 months)', 'C (Planning Stage)'];
  const [items, setItems] = useState<any[]>([]);
  const [total, setTotal] = useState(0);
  const [masters, setMasters] = useState<any>(null);
  const [search, setSearch] = useState('');
  const [status, setStatus] = useState('');
  const [source, setSource] = useState('');
  const [city, setCity] = useState('');
  const [sla, setSla] = useState('');
  const [sort, setSort] = useState('');
  const [validationMessage, setValidationMessage] = useState('');
  const [conversionToConfirm, setConversionToConfirm] = useState<any>(null);
  const [page, setPage] = useState(1);
  const STATUS_FILTERS = ['Assigned', 'In Followup', 'Site Visit', 'Quotation sent', 'Converted', 'Not Interested'];
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [drafts, setDrafts] = useState<Record<string, { remarks: string; review: string; progress: string; reminderDate: string; quotationValue?: string }>>({});
  const [savingId, setSavingId] = useState<string | null>(null);
  const [expandedRows, setExpandedRows] = useState<Record<string, boolean>>({});
  const [followupForms, setFollowupForms] = useState<Record<string, Array<{ remarks: string; review: string; progress: string; reminderDate: string; quotationValue?: string }>>>({});
  const [quoteFormLead, setQuoteFormLead] = useState<any>(null);
  const size = 15;
  useEffect(() => { api.get('/masters').then((r) => setMasters(r.data)).catch(() => setError('Could not load filters.')); }, []);
  useEffect(() => {
    const ctrl = new AbortController();
    const t = setTimeout(() => {
      setLoading(true); setError('');
      api.get('/leads', {
        params: { search, status, source, city, sla, page, size, ...(sort ? { sort } : {}) },
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
  }, [search, status, source, city, sla, sort, page]);
  const nameOf = (kind: 'statuses' | 'sources' | 'employees' | 'products', id?: string) =>
    masters?.[kind]?.find((x: any) => x.id === id)?.name ?? '—';
  const actionOptions = ['In Followup', 'Meeting', 'Site Visit', 'Quotation sent', 'Converted', 'Not Interested'];
  const todayISO = new Date().toISOString().slice(0, 10);
  const reminderOf = (lead: any) => (lead.reminder_date || '').slice(0, 10);
  const draftFor = (lead: any) => drafts[lead.id] || { remarks: lead.employee_remarks || '', review: lead.customer_review || '', progress: lead.employee_remarks ? lead.status_id : '', reminderDate: '', quotationValue: lead.quotation_value ?? '0' };
  /** The three mandatory work fields (Remarks, Category, Work Action). Reminder Date is optional. */
  const workFormIncomplete = (form: { remarks: string; review: string; progress: string }, lead: any) => {
    const actionName = nameOf('statuses', form.progress);
    return !form?.remarks.trim() || !form.review || !actionOptions.includes(actionName);
  };
  /** Reminder Date unlocks only after Category, Work Action and Remarks are filled. */
  const reminderUnlocked = (form: { remarks: string; review: string; progress: string }, lead: any) => {
    const actionName = nameOf('statuses', form.progress);
    return !!form?.remarks.trim() && !!form.review && actionOptions.includes(actionName);
  };
  const isConvertedLocked = (lead: any) => lead.sla_state === 'COMPLETED' && nameOf('statuses', lead.status_id) === 'Converted';
  const isNotInterestedLocked = (lead: any) => lead.sla_state === 'COMPLETED' && ['Not Interested', 'Not Interested/Spam'].includes(nameOf('statuses', lead.status_id));
  const isOutreachLocked = (lead: any) => isConvertedLocked(lead) || isNotInterestedLocked(lead);
  /** Deep freeze: employee clicked Done (COMPLETED). Nothing in the row works until Reopen — except Reopen itself. */
  const isFrozen = (lead: any) => role === 'EMPLOYEE' && lead.sla_state === 'COMPLETED';
  const frozenMessage = () => 'This lead is completed and frozen. Click Reopen to continue.';
  /** Edit Category/Progress/Remarks for new leads, after Reopen, or when overdue (always editable until Converted). Use + for next progress. */
  const canEditWorkFields = (lead: any) => {
    if (role !== 'EMPLOYEE') return false;
    if (isConvertedLocked(lead)) return false;
    // Once a conversation has been recorded, its original progress, category,
    // and remarks stay read-only even after Reopen. New work goes into a follow-up.
    if (lead.work_history?.length) return false;
    if (isNotInterestedLocked(lead)) return false;
    if (lead.sla_state === 'OVERDUE') return true;
    return !!(expandedRows[lead.id] || !lead.employee_remarks);
  };
  const statusLabel = (lead: any) => {
    if (role === 'EMPLOYEE') {
      const draft = draftFor(lead);
      const editing = canEditWorkFields(lead);
      if (editing && draft.progress) {
        const action = nameOf('statuses', draft.progress);
        if (REPEATABLE_PROGRESS.has(action)) {
          return formatProgressOccurrence(action, countProgressAction(lead.work_history, action) + 1);
        }
        return action === 'New Lead' && lead.primary_employee_id ? 'Assigned' : action;
      }
      const labeled = labeledProgressHistory(lead.work_history);
      if (labeled.length) return labeled[labeled.length - 1].displayAction;
    }
    const selectedStatus = nameOf('statuses', lead.status_id);
    return selectedStatus === 'New Lead' && lead.primary_employee_id ? 'Assigned' : selectedStatus;
  };
  const quotationFromForm = (lead: any) => {
    const raw = lead?.quotation_form?.grand_total ?? lead?.quotation_form?.amount_excl ?? lead?.quotation_value;
    if (raw == null || String(raw).trim() === '') return '';
    const n = Math.round(Number(raw));
    return Number.isFinite(n) && n >= 0 ? String(n) : '';
  };
  /** Unlock quotation form/value only when Progress is Quotation sent. Admins always see values. */
  const isQuotationUnlocked = (lead: any) => {
    if (role !== 'EMPLOYEE') return true;
    const progressName = (statusId?: string | null) => {
      if (!statusId) return '';
      return String(masters?.statuses?.find((s: any) => s.id === statusId)?.name || '').trim().toLowerCase();
    };
    const quoteSent = (statusId?: string | null) => progressName(statusId) === 'quotation sent';
    if (quoteSent(drafts[lead.id]?.progress)) return true;
    if ((followupForms[lead.id] || []).some((f) => quoteSent(f.progress))) return true;
    if (quoteSent(lead.status_id)) return true;
    return false;
  };
  const lockedLeadMessage = (lead: any) => isConvertedLocked(lead)
    ? 'This lead is converted and cannot be edited.'
    : 'This lead is not interested and cannot be edited.';
  const canEditProductCars = (lead: any) => role === 'ADMIN' || (role === 'EMPLOYEE' && !isOutreachLocked(lead));
  const saveProductCars = async (lead: any, productId: string, carsRaw: string) => {
    if (!canEditProductCars(lead)) return;
    const productName = masters?.products?.find((p: any) => p.id === productId)?.name || prodName(lead, nameOf);
    const problem = carCountError(String(carsRaw || ''), productName);
    if (problem) { setValidationMessage(problem); return; }
    setSavingId(lead.id);
    try {
      const { data } = await api.put(`/leads/${lead.id}`, {
        product_id: productId || null,
        quantity_raw: String(carsRaw || '').trim() || '2',
      });
      setItems((current) => current.map((item) => item.id === lead.id ? { ...item, ...data } : item));
    } catch (e: any) {
      setValidationMessage(e?.response?.data?.detail || 'Could not save product and cars');
    } finally { setSavingId(null); }
  };
  const saveLead = async (lead: any, done = false, conversionConfirmed = false) => {
    if (role === 'EMPLOYEE' && isConvertedLocked(lead)) {
      setValidationMessage('Converted leads cannot be edited or reopened.');
      return;
    }
    const draft = draftFor(lead);
    const reopening = !done && lead.sla_state === 'COMPLETED';
    const actionName = nameOf('statuses', draft.progress);
    if (workFormIncomplete(draft, lead)) {
      setValidationMessage('Please fill Remarks, Category, and Work Action before saving or completing this lead.');
      return;
    }
    if (done && actionName === 'Converted' && !conversionConfirmed) {
      setConversionToConfirm(lead);
      return;
    }
    setConversionToConfirm(null);
    setSavingId(lead.id);
    try {
      const qv = actionName === 'Quotation sent' ? quotationFromForm(lead) : '';
      const rawRemarks = draft.remarks.trim() || 'Lead completed';
      const stripStamp = (s: string) => s.replace(/\n?\[[^\]]*\]\s*$/u, '').trim();
      // Reopen only restarts the SLA window. Reuse the exact saved conversation
      // so the API's completion-only path does not append it as a new activity.
      const stampedRemarks = reopening
        ? (lead.employee_remarks || rawRemarks)
        : (done && stripStamp(rawRemarks) === stripStamp(lead.employee_remarks || '')
          ? (lead.employee_remarks || rawRemarks)
          : withUpdateStamp(rawRemarks));
      // Only Done marks COMPLETED. Save / Reopen stay PENDING (restarts 3-day follow-up on backend).
      const nextSla = done ? 'COMPLETED' : 'PENDING';
      const { data } = await api.post(`/leads/${lead.id}/status`, {
        new_status_id: draft.progress || lead.status_id,
        reason: stampedRemarks,
        method: 'Call',
        customer_review: draft.review,
        quotation_value: qv || undefined,
        reminder_date: draft.reminderDate || undefined,
        sla_state: nextSla,
      });
      setItems((current) => current.map((item) => item.id === lead.id
        ? {
          ...item,
          status_id: draft.progress || item.status_id,
          employee_remarks: stampedRemarks,
          customer_review: draft.review,
          quotation_value: qv || item.quotation_value,
          reminder_date: data.reminder_date ?? item.reminder_date ?? null,
          reminder_done: data.reminder_done ?? item.reminder_done ?? false,
          sla_state: data.sla_state ?? nextSla,
          work_history: data.activity_recorded === false ? item.work_history : [...(item.work_history || []), { remarks: stampedRemarks, category: draft.review, quotation_value: qv || null, work_action: nameOf('statuses', draft.progress || item.status_id), reminder_date: draft.reminderDate || null, reminder_done: false, at: new Date().toISOString() }],
        }
        : item));
      setDrafts((current) => { const next = { ...current }; delete next[lead.id]; return next; });
      setExpandedRows((current) => ({ ...current, [lead.id]: reopening }));
      if (done) {
        setFollowupForms((current) => ({ ...current, [lead.id]: [] }));
      }
    } catch (e: any) {
      setValidationMessage(e?.response?.data?.detail || 'Could not save lead remarks');
    } finally { setSavingId(null); }
  };
  const addFollowUp = (lead: any) => {
    setFollowupForms((current) => ({
      ...current,
      [lead.id]: [...(current[lead.id] || []), { remarks: '', review: '', progress: '', reminderDate: '', quotationValue: '0' }],
    }));
  };
  const closeFollowUp = (lead: any) => {
    setFollowupForms((current) => ({ ...current, [lead.id]: (current[lead.id] || []).slice(0, -1) }));
  };
  /** Tick the live reminder done / not done: strikes it through, keeps the date. */
  const toggleLeadReminder = async (lead: any) => {
    if (savingId === lead.id) return;
    const done = !lead.reminder_done;
    setSavingId(lead.id);
    try {
      const { data } = await api.put(`/leads/${lead.id}`, { reminder_done: done });
      setItems((current) => current.map((item) => item.id === lead.id ? { ...item, reminder_done: data.reminder_done ?? done } : item));
    } catch (e: any) {
      setValidationMessage(e?.response?.data?.detail || 'Could not update reminder');
    } finally { setSavingId(null); }
  };
  /** Tick a single history entry's reminder done / not done. */
  const toggleEntryReminder = async (lead: any, entry: any) => {
    if (!entry?.id || savingId === lead.id) return;
    const done = !entry.reminder_done;
    setSavingId(lead.id);
    try {
      await api.post(`/leads/${lead.id}/activities/${entry.id}/reminder-done`, { done });
      setItems((current) => current.map((item) => item.id === lead.id
        ? { ...item, work_history: (item.work_history || []).map((h: any) => h.id === entry.id ? { ...h, reminder_done: done } : h) }
        : item));
    } catch (e: any) {
      setValidationMessage(e?.response?.data?.detail || 'Could not update reminder');
    } finally { setSavingId(null); }
  };
  const tickBtn = (done: boolean) => `inline-flex items-center justify-center w-7 h-7 rounded-md border text-sm shrink-0 ${done ? 'border-emerald-600 bg-emerald-600 text-white hover:bg-emerald-700' : 'border-emerald-300 bg-emerald-50 text-emerald-700 hover:bg-emerald-100'}`;
  const reminderTickable = (lead: any) => !(role === 'EMPLOYEE' && (isOutreachLocked(lead) || isFrozen(lead)));
  const saveFollowup = async (lead: any, index: number) => {
    const form = followupForms[lead.id]?.[index];
    const actionName = form ? nameOf('statuses', form.progress) : '';
    if (!form || workFormIncomplete(form, lead)) {
      setValidationMessage('Please fill Remarks, Category, and Work Action for this follow-up.');
      return;
    }
    setSavingId(lead.id);
    try {
      const qv = actionName === 'Quotation sent' ? quotationFromForm(lead) : '';
      const stampedRemarks = withUpdateStamp(form.remarks.trim());
      const { data } = await api.post(`/leads/${lead.id}/status`, {
        new_status_id: form.progress || lead.status_id,
        reason: stampedRemarks,
        method: 'Call',
        customer_review: form.review,
        quotation_value: qv || undefined,
        reminder_date: form.reminderDate || undefined,
      });
      setItems((current) => current.map((item) => item.id === lead.id ? { ...item, status_id: form.progress || item.status_id, employee_remarks: stampedRemarks, customer_review: form.review, quotation_value: qv || item.quotation_value, reminder_date: data.reminder_date ?? item.reminder_date ?? null, reminder_done: data.reminder_done ?? item.reminder_done ?? false, sla_state: data.sla_state ?? item.sla_state, work_history: [...(item.work_history || []), { remarks: stampedRemarks, category: form.review, quotation_value: qv || null, work_action: nameOf('statuses', form.progress || item.status_id), reminder_date: form.reminderDate || null, reminder_done: false, at: new Date().toISOString() }] } : item));
      setFollowupForms((current) => ({ ...current, [lead.id]: (current[lead.id] || []).filter((_, i) => i !== index) }));
    } catch (e: any) { setValidationMessage(e?.response?.data?.detail || 'Could not save follow-up'); }
    finally { setSavingId(null); }
  };
  return (
    <div className="min-w-0 max-w-full">
      <PageHeader title="Leads" subtitle={`${total} lead${total === 1 ? '' : 's'} found · Create Lead or Excel import · auto-assign round-robin when no employee is selected`} />
      <div className="card p-3 sm:p-4 mb-4 grid grid-cols-1 gap-2 sm:gap-3 sm:grid-cols-2 xl:grid-cols-[2fr_1fr_1fr_1fr_1fr_1fr]">
        <input className="input min-w-0 min-h-[44px] text-base sm:text-sm" placeholder="🔍 Search name, phone, enquiry…" value={search} onChange={(e) => { setSearch(e.target.value); setPage(1); }} />
        <input className="input min-w-0 min-h-[44px] text-base sm:text-sm" placeholder="City" value={city} onChange={(e) => { setCity(e.target.value); setPage(1); }} />
        <select className="input min-w-0 min-h-[44px] text-base sm:text-sm" value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }}>
          <option value="">Status</option>
          {STATUS_FILTERS.map((name) => masters?.statuses?.find((s: any) => s.name === name)).filter(Boolean).map((s: any) => (
            <option key={s.id} value={s.id}>{s.name}</option>
          ))}
        </select>
        <select className="input min-w-0 min-h-[44px] text-base sm:text-sm" value={source} onChange={(e) => { setSource(e.target.value); setPage(1); }}>
          <option value="">Sources</option>
          {masters?.sources?.map((s: any) => <option key={s.id} value={s.id}>{s.name}</option>)}
        </select>
        <select className="input min-w-0 min-h-[44px] text-base sm:text-sm" value={sla} onChange={(e) => { setSla(e.target.value); setPage(1); }}>
          <option value="">Lead status</option>
          <option value="PENDING">Pending</option>
          <option value="COMPLETED">Completed</option>
          <option value="NOT_INTERESTED">Not Interested</option>
        </select>
        <select className="input min-w-0 min-h-[44px] text-base sm:text-sm" value={sort} onChange={(e) => { setSort(e.target.value); setPage(1); }}>
          <option value="">Sort: Recent</option>
          <option value="lead_value_desc">Lead High</option>
          <option value="lead_value">Lead Low</option>
        </select>
      </div>
      {error && <div className="bg-red-50 border border-red-200 text-red-700 text-sm rounded-xl px-4 py-3 mb-4">{error}</div>}
      <div className="card min-w-0">
        {loading ? <Spinner /> : items.length === 0 ? <EmptyState title={error ? 'Could not load leads' : 'No leads match'} hint={error ? 'Check your connection and retry.' : 'Import the Excel tracker or adjust filters.'} /> : (
          <>
          {/* Admin mobile: stacked read-only cards */}
          {role !== 'EMPLOYEE' && (
            <div className="block md:hidden space-y-3 p-3">
              {items.map((l) => (
                <div
                  key={`m-${l.id}`}
                  className={`rounded-xl border border-graphite-200 p-3 shadow-sm ${leadRowColour(l, nameOf('statuses', l.status_id))}`}
                >
                  <div className="flex items-start justify-between gap-2">
                    <Link to={`/leads/${l.id}`} className="font-semibold text-brand-700 text-sm">
                      {l.enquiry_number}
                    </Link>
                    <div className="flex flex-wrap items-center justify-end gap-1.5 shrink-0">
                      <StatusBadge value={statusLabel(l)} />
                      <SlaBadge value={l.sla_state} />
                    </div>
                  </div>
                  <div className="mt-2 min-w-0">
                    <div className="font-medium text-graphite-900 break-words">{l.customer_name || '—'}</div>
                    <div className="text-sm text-graphite-700 break-words">{l.company_name || '—'}</div>
                    <div className="text-sm text-graphite-600">{l.city || '—'}</div>
                  </div>
                  <div className="mt-2 text-sm text-graphite-800 break-words">
                    <div>{l.contact_number || '—'}</div>
                    <div className="text-xs text-graphite-600 break-words [overflow-wrap:anywhere]">
                      {l.email || <span className="text-graphite-400">No email</span>}
                    </div>
                  </div>
                  <dl className="mt-3 grid grid-cols-2 gap-x-3 gap-y-2 text-xs">
                    <div className="min-w-0">
                      <dt className="text-graphite-500 uppercase tracking-wide font-semibold">Product</dt>
                      <dd className="text-graphite-900 mt-0.5 break-words">{prodName(l, nameOf)}</dd>
                    </div>
                    <div className="min-w-0">
                      <dt className="text-graphite-500 uppercase tracking-wide font-semibold">Cars</dt>
                      <dd className="text-graphite-900 mt-0.5">{l.quantity_raw || '—'}</dd>
                    </div>
                    <div className="min-w-0">
                      <dt className="text-graphite-500 uppercase tracking-wide font-semibold">Category</dt>
                      <dd className="text-graphite-900 mt-0.5 break-words">{l.customer_review || '—'}</dd>
                    </div>
                    <div className="min-w-0">
                      <dt className="text-graphite-500 uppercase tracking-wide font-semibold">Source</dt>
                      <dd className="text-graphite-900 mt-0.5 break-words">{l.source_name || nameOf('sources', l.source_id)}</dd>
                    </div>
                    <div className="min-w-0">
                      <dt className="text-graphite-500 uppercase tracking-wide font-semibold">Employee</dt>
                      <dd className="text-graphite-900 mt-0.5 break-words">
                        {l.primary_employee_id ? nameOf('employees', l.primary_employee_id) : <span className="text-amber-700 font-medium">Pending</span>}
                      </dd>
                    </div>
                    <div className="min-w-0">
                      <dt className="text-graphite-500 uppercase tracking-wide font-semibold">Lead value</dt>
                      <dd className="text-graphite-900 mt-0.5 font-semibold tabular-nums">{inr(l.lead_value)}</dd>
                    </div>
                    <div className="min-w-0">
                      <dt className="text-graphite-500 uppercase tracking-wide font-semibold">Reminder Date</dt>
                      <dd className="text-graphite-900 mt-0.5 tabular-nums inline-flex items-center gap-1.5">
                        <span className={l.reminder_done ? 'reminder-done' : ''}>{(l.reminder_date || '').slice(0, 10) || '—'}</span>
                        {l.reminder_date && reminderTickable(l) && (
                          <button type="button" title={l.reminder_done ? 'Mark reminder not done' : 'Mark reminder done'} aria-label={l.reminder_done ? 'Mark reminder not done' : 'Mark reminder done'} disabled={savingId === l.id} onClick={() => toggleLeadReminder(l)} className={tickBtn(!!l.reminder_done)}>✓</button>
                        )}
                      </dd>
                    </div>
                    <div className="min-w-0 col-span-2">
                      <dt className="text-graphite-500 uppercase tracking-wide font-semibold">Quotation value</dt>
                      <dd className="text-graphite-900 mt-0.5 font-semibold tabular-nums">
                        {l.quotation_value != null && l.quotation_value !== '' ? inr(l.quotation_value) : '—'}
                      </dd>
                    </div>
                  </dl>
                </div>
              ))}
            </div>
          )}
          {/* Employee mobile: stacked editable cards with desktop work actions */}
          {role === 'EMPLOYEE' && (
            <div className="block md:hidden space-y-3 p-3">
              {items.map((l) => {
                const draft = draftFor(l);
                const editing = canEditWorkFields(l) && !isFrozen(l);
                const locked = isOutreachLocked(l);
                const frozen = isFrozen(l);
                return (
                  <div
                    key={`m-${l.id}`}
                    className={`rounded-xl border border-graphite-200 p-3 shadow-sm ${leadRowColour(l, nameOf('statuses', l.status_id))} ${frozen ? 'opacity-80' : ''}`}
                    onClickCapture={(event) => {
                      const target = event.target as HTMLElement;
                      if (target.closest?.('[data-reopen]')) return;
                      if (frozen && target.closest?.('button, select, textarea, input, a')) {
                        event.preventDefault(); event.stopPropagation();
                        setValidationMessage(frozenMessage());
                      }
                    }}
                  >
                    <div className="flex items-start justify-between gap-2">
                      {frozen ? (
                        <span className="font-semibold text-brand-700 text-sm break-words min-w-0">{l.enquiry_number}</span>
                      ) : (
                        <Link to={`/leads/${l.id}`} className="font-semibold text-brand-700 text-sm break-words min-w-0">
                          {l.enquiry_number}
                        </Link>
                      )}
                      <div className="flex flex-wrap items-center justify-end gap-1.5 shrink-0">
                        <StatusBadge value={statusLabel(l)} />
                        <SlaBadge value={l.sla_state} />
                      </div>
                    </div>
                    <div className="mt-2 min-w-0">
                      <div className="font-medium text-graphite-900 break-words">{l.customer_name || '—'}</div>
                      <div className="text-sm text-graphite-700 break-words">{l.company_name || '—'}</div>
                      <div className="text-sm text-graphite-600 break-words">{l.city || '—'}</div>
                    </div>
                    <div className="mt-2 text-sm text-graphite-800 break-words">
                      <div className="flex items-center gap-1.5 flex-wrap">
                        <span className="break-words">{l.contact_number || '—'}</span>
                        {l.contact_number && !frozen && whatsappUrl(l.contact_number) && (
                          <a
                            href={whatsappUrl(l.contact_number)}
                            target="_blank"
                            rel="noopener noreferrer"
                            title="Open WhatsApp"
                            className="inline-flex text-[#25D366] hover:text-[#128C7E] min-w-[44px] min-h-[44px] items-center justify-center"
                            onClick={(e) => {
                              e.stopPropagation();
                              if (isOutreachLocked(l)) {
                                e.preventDefault();
                                setValidationMessage(lockedLeadMessage(l));
                              }
                            }}
                          >
                            <svg viewBox="0 0 24 24" className="w-5 h-5" aria-hidden="true">
                              <path fill="currentColor" d="M20.5 3.5A11 11 0 0 0 2.1 17.8L1 23l5.3-1.1A11 11 0 0 0 12 23a11 11 0 0 0 8.5-19.5zM12 21a9 9 0 0 1-4.6-1.3l-.3-.2-3.1.7.7-3-.2-.3A9 9 0 1 1 12 21zm5-6.7c-.3-.1-1.6-.8-1.8-.9s-.4-.1-.6.1-.7.9-.8 1-.3.2-.6.1a7.4 7.4 0 0 1-2.2-1.4 8.2 8.2 0 0 1-1.5-1.9c-.2-.3 0-.4.1-.6l.4-.5.2-.3a.5.5 0 0 0 0-.5c-.1-.1-.6-1.4-.8-1.9s-.4-.4-.6-.4h-.5a1 1 0 0 0-.7.3 3 3 0 0 0-.9 2.2 5.2 5.2 0 0 0 1.1 2.8 11.8 11.8 0 0 0 4.4 4 14 14 0 0 0 1.5.5 3.6 3.6 0 0 0 1.6.1 2.7 2.7 0 0 0 1.8-1.2 2.2 2.2 0 0 0 .2-1.2c-.1-.1-.3-.2-.6-.3z" />
                            </svg>
                          </a>
                        )}
                      </div>
                      <div className="text-xs text-graphite-600 break-words [overflow-wrap:anywhere] mt-1">
                        {l.email && !frozen
                          ? <button type="button" className="text-brand-700 hover:underline text-left text-xs break-words [overflow-wrap:anywhere] min-h-[44px] py-2" onClick={(e) => { if (isOutreachLocked(l)) { e.preventDefault(); e.stopPropagation(); setValidationMessage(lockedLeadMessage(l)); return; } openEstarWebmail(e, l.email, l.enquiry_number); }}>{l.email}</button>
                          : <span className="text-graphite-400">{l.email || 'No email'}</span>}
                      </div>
                    </div>
                    <div className="mt-3 grid grid-cols-2 gap-2">
                      <div className="min-w-0">
                        <div className="text-graphite-500 uppercase tracking-wide font-semibold text-[11px]">Cars</div>
                        {canEditProductCars(l) && !frozen ? (
                          <input
                            className="input text-base sm:text-sm mt-1 min-h-[44px] text-center w-full"
                            type="number"
                            min="2"
                            disabled={savingId === l.id}
                            value={l.quantity_raw || ''}
                            placeholder="2"
                            onChange={(e) => setItems((current) => current.map((item) => item.id === l.id ? { ...item, quantity_raw: e.target.value } : item))}
                            onBlur={(e) => saveProductCars(l, l.product_id || '', e.target.value)}
                          />
                        ) : (<div className="text-sm text-graphite-900 mt-1">{l.quantity_raw || '—'}</div>)}
                      </div>
                      <div className="min-w-0">
                        <div className="text-graphite-500 uppercase tracking-wide font-semibold text-[11px]">Lead value</div>
                        <div className="text-sm text-graphite-900 mt-1 font-semibold tabular-nums">{inr(l.lead_value)}</div>
                      </div>
                    </div>
                    <div className="mt-2 min-w-0">
                        <div className="text-graphite-500 uppercase tracking-wide font-semibold text-[11px]">Product</div>
                      {canEditProductCars(l) && !frozen ? (
                        <select
                          className="input text-base sm:text-sm mt-1 min-h-[44px] w-full"
                          disabled={savingId === l.id}
                          value={l.product_id || ''}
                          onChange={(e) => saveProductCars(l, e.target.value, l.quantity_raw || '')}
                        >
                          <option value="">Select product…</option>
                          {(masters?.products || []).map((p: any) => <option key={p.id} value={p.id}>{p.name}</option>)}
                        </select>
                      ) : (<div className="text-sm text-graphite-900 mt-1 break-words">{prodName(l, nameOf)}</div>)}
                    </div>
                    <div className="mt-3 flex items-center justify-between gap-2">
                      <span className="text-graphite-500 uppercase tracking-wide font-semibold text-[11px]">Work details</span>
                      {!locked && !frozen && l.employee_remarks && (
                        <button
                          type="button"
                          className="btn-secondary !px-3 !py-1 text-xs min-h-[36px]"
                          onClick={() => setExpandedRows((current) => ({ ...current, [l.id]: !current[l.id] }))}
                        >
                          {expandedRows[l.id] ? 'Cancel' : 'Edit'}
                        </button>
                      )}
                    </div>
                    <div className="mt-2 space-y-2">
                      <div>
                        <div className="text-graphite-500 uppercase tracking-wide font-semibold text-[11px]">Category</div>
                        {editing ? (
                          <select className="input text-base sm:text-sm mt-1 min-h-[44px] w-full" disabled={locked} value={draft.review}
                            onChange={(e) => setDrafts((current) => ({ ...current, [l.id]: { ...draftFor(l), review: e.target.value } }))}>
                            <option value="">Select category…</option>
                            {reviewOptions.map((option) => <option key={option} value={option}>{option}</option>)}
                          </select>
                        ) : (<div className="text-sm text-graphite-900 mt-1 break-words">{l.work_history?.length ? l.work_history.map((entry: any, index: number) => <div key={`m-category-${index}`}><b>{index + 1}.</b> {entry.category || '—'}</div>) : (l.customer_review || '—')}</div>)}
                      </div>
                      <div>
                        <div className="flex items-center justify-between gap-2">
                          <div className="text-graphite-500 uppercase tracking-wide font-semibold text-[11px]">Work action</div>
                          <button type="button" className="btn-secondary !px-3 !py-1 text-base font-bold min-w-[44px] min-h-[44px]" disabled={locked || frozen} onClick={() => ((followupForms[l.id] || []).length ? closeFollowUp(l) : addFollowUp(l))} title={(followupForms[l.id] || []).length ? 'Close unsaved follow-up' : 'Add follow-up'}>{(followupForms[l.id] || []).length ? '×' : '+'}</button>
                        </div>
                        {editing ? (
                          <select className="input text-base sm:text-sm mt-1 min-h-[44px] w-full" disabled={locked} value={draft.progress}
                            onChange={(e) => setDrafts((current) => ({ ...current, [l.id]: { ...draftFor(l), progress: e.target.value } }))}>
                            <option value="">Select progress…</option>
                            {actionOptions.map((option) => {
                              const match = masters?.statuses?.find((s: any) => s.name.toLowerCase() === option.toLowerCase());
                              return <option key={option} value={match?.id || l.status_id}>{option}</option>;
                            })}
                          </select>
                        ) : (<div className="text-sm text-graphite-900 mt-1 break-words">{l.work_history?.length ? labeledProgressHistory(l.work_history).map((entry: any, index: number) => <div key={`m-action-${index}`}><b>{index + 1}.</b> {entry.displayAction}</div>) : nameOf('statuses', l.status_id)}</div>)}
                        {!frozen && (followupForms[l.id] || []).map((form, index) => (
                          <div key={`m-follow-${index}`} className="mt-2 space-y-2 rounded-lg border border-graphite-200 p-2">
                            <select className="input text-base sm:text-sm min-h-[44px] w-full" value={form.review} onChange={(e) => setFollowupForms((current) => ({ ...current, [l.id]: current[l.id].map((item, i) => i === index ? { ...item, review: e.target.value } : item) }))}><option value="">Select category…</option>{reviewOptions.map((option) => <option key={option} value={option}>{option}</option>)}</select>
                            <select className="input text-base sm:text-sm min-h-[44px] w-full" value={form.progress} onChange={(e) => setFollowupForms((current) => ({ ...current, [l.id]: current[l.id].map((item, i) => i === index ? { ...item, progress: e.target.value } : item) }))}>
                              <option value="">Select progress…</option>
                              {actionOptions.map((option) => {
                                const match = masters?.statuses?.find((s: any) => s.name.toLowerCase() === option.toLowerCase());
                                return <option key={option} value={match?.id || l.status_id}>{option}</option>;
                              })}
                            </select>
                            <AutoGrowRemarks
                              placeholder={`Follow-up ${(l.work_history?.length || 1) + index + 1} remarks…`}
                              value={form.remarks}
                              onChange={(e) => setFollowupForms((current) => ({ ...current, [l.id]: current[l.id].map((item, i) => i === index ? { ...item, remarks: e.target.value } : item) }))}
                            />
                            <input
                              type="date"
                              aria-label="Reminder date"
                              title={reminderUnlocked(form, l) ? 'Optional reminder date' : 'Fill Category, Work Action and Remarks first'}
                              className="input text-base sm:text-sm min-h-[44px] w-full"
                              min={todayISO}
                              disabled={!reminderUnlocked(form, l)}
                              value={form.reminderDate}
                              onChange={(e) => setFollowupForms((current) => ({ ...current, [l.id]: current[l.id].map((item, i) => i === index ? { ...item, reminderDate: e.target.value } : item) }))}
                            />
                            <button type="button" className="btn-primary !px-3 !py-2 text-sm w-full min-h-[44px]" disabled={savingId === l.id || workFormIncomplete(form, l)} onClick={() => saveFollowup(l, index)}>{savingId === l.id ? 'Saving…' : `Save follow-up ${(l.work_history?.length || 1) + index + 1}`}</button>
                          </div>
                        ))}
                      </div>
                      <div>
                        <div className="text-graphite-500 uppercase tracking-wide font-semibold text-[11px]">Remarks</div>
                        {editing ? (
                          <>
                            <AutoGrowRemarks
                              disabled={locked}
                              placeholder="Enter customer conversation remarks…"
                              value={draft.remarks}
                              onChange={(e) => setDrafts((current) => ({ ...current, [l.id]: { ...draftFor(l), remarks: e.target.value } }))}
                            />
                            <div className="mt-2">
                              <div className="text-graphite-500 uppercase tracking-wide font-semibold text-[11px]">Reminder Date</div>
                              <input
                                type="date"
                                aria-label="Reminder date (optional)"
                                title={reminderUnlocked(draft, l) ? 'Optional reminder date' : 'Fill Category, Work Action and Remarks first'}
                                className="input text-base sm:text-sm mt-1 min-h-[44px] w-full min-w-0"
                                min={todayISO}
                                disabled={locked || !reminderUnlocked(draft, l)}
                                value={draft.reminderDate}
                                onChange={(e) => setDrafts((current) => ({ ...current, [l.id]: { ...draftFor(l), reminderDate: e.target.value } }))}
                              />
                            </div>
                            <button type="button" className="btn-primary !px-3 !py-2 text-sm mt-2 w-full min-h-[44px]" disabled={savingId === l.id || workFormIncomplete(draft, l)} onClick={() => saveLead(l)}>{savingId === l.id ? 'Saving…' : 'Save'}</button>
                          </>
                        ) : (<div className="text-sm text-graphite-900 mt-1 break-words whitespace-pre-wrap">{l.work_history?.length ? l.work_history.map((entry: any, index: number) => <div key={`m-remark-${index}`}><b>{index + 1}.</b> {entry.remarks}{entry.reminder_date ? <span className="mt-0.5 block text-xs text-graphite-500 tabular-nums inline-flex items-center gap-1"><span className={entry.reminder_done ? 'reminder-done' : ''}>Reminder: {String(entry.reminder_date).slice(0, 10)}</span>{entry.id && reminderTickable(l) && (<button type="button" title={entry.reminder_done ? 'Mark reminder not done' : 'Mark reminder done'} aria-label={entry.reminder_done ? 'Mark reminder not done' : 'Mark reminder done'} disabled={savingId === l.id} onClick={() => toggleEntryReminder(l, entry)} className={`${tickBtn(!!entry.reminder_done)} !w-6 !h-6 !text-xs`}>✓</button>)}</span> : null}</div>) : (<span className="inline-flex items-center gap-1.5 flex-wrap">{l.employee_remarks || '—'}{l.reminder_date ? (<><span className={`text-xs text-graphite-500 ${l.reminder_done ? 'reminder-done' : ''}`}>Reminder: {String(l.reminder_date).slice(0, 10)}</span>{reminderTickable(l) && (<button type="button" title={l.reminder_done ? 'Mark reminder not done' : 'Mark reminder done'} aria-label={l.reminder_done ? 'Mark reminder not done' : 'Mark reminder done'} disabled={savingId === l.id} onClick={() => toggleLeadReminder(l)} className={tickBtn(!!l.reminder_done)}>✓</button>)}</>) : null}</span>)}</div>)}
                      </div>
                    </div>
                    <div className="mt-3 flex flex-wrap gap-2">
                      {isConvertedLocked(l) ? (
                        <span className="text-xs font-semibold text-emerald-700">✓ Done</span>
                      ) : (
                        <button type="button" data-reopen={l.sla_state === 'COMPLETED' ? '' : undefined} className={`btn-secondary !px-4 !py-2 text-sm min-h-[44px] flex-1 ${l.sla_state === 'COMPLETED' ? '!bg-amber-100 !text-amber-900 !border-amber-300' : '!bg-blue-600 !text-white !border-blue-600'}`}
                          disabled={savingId === l.id}
                          onClick={() => saveLead(l, l.sla_state !== 'COMPLETED')}>
                          {savingId === l.id ? 'Saving…' : l.sla_state === 'COMPLETED' ? 'Reopen' : 'Done'}
                        </button>
                      )}
                      {isQuotationUnlocked(l) && !frozen ? (
                        <>
                          <button
                            type="button"
                            className="btn-primary !px-4 !py-2 text-sm min-h-[44px] flex-1"
                            onClick={(e) => {
                              if (isOutreachLocked(l)) { e.preventDefault(); e.stopPropagation(); setValidationMessage(lockedLeadMessage(l)); return; }
                              setQuoteFormLead(l);
                            }}
                          >
                            {l.quotation_form?.quotation_number ? 'Edit quote' : 'Quote form'}
                          </button>
                          {isQuotationUnlocked(l) && l.quotation_value != null && l.quotation_value !== '' && (
                            <span className="inline-flex items-center rounded-md border border-amber-200 bg-amber-50 px-2 py-1 text-xs font-semibold tabular-nums text-amber-900">
                              {inr(l.quotation_value)}
                            </span>
                          )}
                        </>
                      ) : null}
                    </div>
                    <div className="mt-2 text-xs text-graphite-500 break-words">
                      <span>Source: {l.source_name || nameOf('sources', l.source_id)}</span>
                      {l.sla_deadline && <span className="ml-2">· Due: {fmtDT(l.sla_deadline)}</span>}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
          <div ref={tableScroll.ref} className={`relative isolate w-full overflow-x-auto drag-scroll hidden md:block ${tableScroll.dragging ? 'is-dragging' : ''}`}>
            <div className="text-[11px] text-graphite-400 mb-1 hidden md:block select-none" aria-hidden="true">⇔ Drag to see more columns</div>
            <table className={`w-full table-fixed border-separate border-spacing-0 text-sm [&_td]:border-graphite-100 [&_td]:break-words ${role === 'EMPLOYEE' ? 'min-w-[2270px]' : 'min-w-[2290px]'}`}>
              <thead className="bg-graphite-50"><tr>
                <th className="th whitespace-nowrap align-top w-[144px] sm:w-[160px] !px-2 sm:!px-4 !text-[10px] sm:!text-xs sticky left-0 z-20 bg-graphite-50">Enquiry Number</th>
                <th className="th whitespace-nowrap align-top w-[200px] sm:w-[240px] !px-2 sm:!px-4 !text-[10px] sm:!text-xs sticky left-[144px] sm:left-[160px] z-20 bg-graphite-50 shadow-[4px_0_8px_-4px_rgba(0,0,0,0.15)]">Customer details</th>
                <th className="th whitespace-nowrap align-top w-[260px] sm:w-[280px]">Contact / Email</th>
                <th className="th whitespace-nowrap align-top w-[110px] text-center">Cars</th>
                <th className="th whitespace-nowrap align-top w-[200px]">Product</th>
                <th className="th whitespace-nowrap align-top w-[210px]">Category</th>
                <th className="th whitespace-nowrap align-top w-[210px]">Progress</th>
                <th className="th whitespace-nowrap align-top w-[280px]">Remarks</th>
                <th className="th whitespace-nowrap align-top w-[190px]">Reminder Date</th>
                <th className="th whitespace-nowrap align-top w-[140px]">Source</th>
                <th className="th whitespace-nowrap align-top w-[170px] text-center">Current status</th>
                <th className="th whitespace-nowrap align-top w-[160px] text-center">Lead status</th>
                {role !== 'EMPLOYEE' && <th className="th whitespace-nowrap align-top w-[170px]">Employee</th>}
                <th className="th whitespace-nowrap align-top w-[130px] text-right">Lead Value</th>
                {role === 'EMPLOYEE' && <th className="th whitespace-nowrap align-top w-[120px] text-center">Quotation form</th>}
                <th className="th text-right whitespace-nowrap align-top w-[180px]">Quotation value</th>
              </tr></thead>
              <tbody>
                {items.map((l) => (
                  <tr key={l.id} className={`${leadRowColour(l, nameOf('statuses', l.status_id))} ${isFrozen(l) ? 'opacity-80' : ''}`}
                    onClickCapture={(event) => {
                      const target = event.target as HTMLElement;
                      if (target.closest?.('[data-reopen]')) return;
                      if (role === 'EMPLOYEE' && isFrozen(l) && target.closest?.('button, select, textarea, input, a, [data-webmail], [data-quote-pdf], [data-whatsapp]')) {
                        event.preventDefault(); event.stopPropagation();
                        setValidationMessage(frozenMessage());
                        return;
                      }
                      if (role === 'EMPLOYEE' && isOutreachLocked(l) && target.closest?.('button, select, textarea, [data-webmail], [data-quote-pdf], [data-whatsapp]')) {
                        event.preventDefault(); event.stopPropagation();
                        setValidationMessage(lockedLeadMessage(l));
                      }
                    }}>

                    <td className={`td align-top !px-2 sm:!px-4 sticky left-0 z-10 font-semibold text-brand-700 whitespace-nowrap ${leadRowColour(l, nameOf('statuses', l.status_id))}`}>{isFrozen(l) ? <span>{l.enquiry_number}</span> : <Link to={`/leads/${l.id}`}>{l.enquiry_number}</Link>}</td>
                    <td className={`td align-top !px-2 sm:!px-4 sticky left-[144px] sm:left-[160px] z-10 shadow-[4px_0_8px_-4px_rgba(0,0,0,0.15)] ${leadRowColour(l, nameOf('statuses', l.status_id))}`}>
                      <div className="text-base font-semibold text-graphite-900">{l.customer_name || '—'}</div>
                      <div className="text-base text-graphite-700 mt-1.5">{l.company_name || '—'}</div>
                      <div className="text-base text-graphite-600 mt-1.5">{l.city || '—'}</div>
                    </td>
                    <td className="td align-top min-w-[260px]">
                      <div className="whitespace-nowrap flex items-center gap-1.5 text-base text-graphite-900">
                        <span>{l.contact_number || '—'}</span>
                        {role === 'EMPLOYEE' && !isFrozen(l) && l.contact_number && whatsappUrl(l.contact_number) && (
                          <a
                            data-whatsapp
                            href={whatsappUrl(l.contact_number)}
                            target="_blank"
                            rel="noopener noreferrer"
                            title="Open WhatsApp"
                            className="inline-flex text-[#25D366] hover:text-[#128C7E]"
                            onClick={(e) => {
                              e.stopPropagation();
                              if (isOutreachLocked(l)) {
                                e.preventDefault();
                                setValidationMessage(lockedLeadMessage(l));
                              }
                            }}
                          >
                            <svg viewBox="0 0 24 24" className="w-4 h-4" aria-hidden="true">
                              <path fill="currentColor" d="M20.5 3.5A11 11 0 0 0 2.1 17.8L1 23l5.3-1.1A11 11 0 0 0 12 23a11 11 0 0 0 8.5-19.5zM12 21a9 9 0 0 1-4.6-1.3l-.3-.2-3.1.7.7-3-.2-.3A9 9 0 1 1 12 21zm5-6.7c-.3-.1-1.6-.8-1.8-.9s-.4-.1-.6.1-.7.9-.8 1-.3.2-.6.1a7.4 7.4 0 0 1-2.2-1.4 8.2 8.2 0 0 1-1.5-1.9c-.2-.3 0-.4.1-.6l.4-.5.2-.3a.5.5 0 0 0 0-.5c-.1-.1-.6-1.4-.8-1.9s-.4-.4-.6-.4h-.5a1 1 0 0 0-.7.3 3 3 0 0 0-.9 2.2 5.2 5.2 0 0 0 1.1 2.8 11.8 11.8 0 0 0 4.4 4 14 14 0 0 0 1.5.5 3.6 3.6 0 0 0 1.6.1 2.7 2.7 0 0 0 1.8-1.2 2.2 2.2 0 0 0 .2-1.2c-.1-.1-.3-.2-.6-.3z" />
                            </svg>
                          </a>
                        )}
                      </div>
                      <div className="text-sm mt-1.5 break-words [overflow-wrap:anywhere]">
                        {l.email && role === 'EMPLOYEE' && !isFrozen(l)
                          ? <button type="button" data-webmail className="text-brand-700 hover:underline text-left text-sm break-words [overflow-wrap:anywhere]" onClick={(e) => { if (isOutreachLocked(l)) { e.preventDefault(); e.stopPropagation(); setValidationMessage(lockedLeadMessage(l)); return; } openEstarWebmail(e, l.email, l.enquiry_number); }}>{l.email}</button>
                          : l.email
                            ? <span className="break-words [overflow-wrap:anywhere]">{l.email}</span>
                            : <span className="text-graphite-400">No email</span>}
                      </div>
                    </td>
                    <td className="td align-top text-center whitespace-nowrap" onClick={(e) => e.stopPropagation()}>
                      {canEditProductCars(l) && !isFrozen(l) ? (
                        <input
                          className="input text-xs text-center w-full max-w-[5.5rem]"
                          type="number"
                          min="2"
                          step={allowsOddCars(prodName(l, nameOf)) ? 1 : 2}
                          disabled={savingId === l.id}
                          value={l.quantity_raw || ''}
                          placeholder="2"
                          title="Starts at 2. Odd or even for Puzzle, Pit Puzzle, Car Elevator, Shuttle, and ASRS. Even only for Two Post, Four Post, Pit Stack, and Tower."
                          onChange={(e) => setItems((current) => current.map((item) => item.id === l.id ? { ...item, quantity_raw: e.target.value } : item))}
                          onKeyDown={(e) => {
                            const step = allowsOddCars(prodName(l, nameOf)) ? 1 : 2;
                            const next = arrowStep(e.currentTarget.value, e.key, step, 2);
                            if (next == null) return;
                            e.preventDefault();
                            setItems((current) => current.map((item) => item.id === l.id ? { ...item, quantity_raw: next } : item));
                          }}
                          onBlur={(e) => saveProductCars(l, l.product_id || '', e.target.value)}
                        />
                      ) : (l.quantity_raw || '—')}
                    </td>
                    <td className="td align-top" onClick={(e) => e.stopPropagation()}>
                      {canEditProductCars(l) && !isFrozen(l) ? (
                        <select
                          className="input text-xs w-full max-w-[12rem]"
                          disabled={savingId === l.id}
                          value={l.product_id || ''}
                          onChange={(e) => saveProductCars(l, e.target.value, l.quantity_raw || '')}
                        >
                          <option value="">Select product…</option>
                          {(masters?.products || []).map((p: any) => <option key={p.id} value={p.id}>{p.name}</option>)}
                        </select>
                      ) : prodName(l, nameOf)}
                    </td>
                    <td className="td align-top">
                      {canEditWorkFields(l) && !isFrozen(l) ? (
                        <select className="input text-xs" disabled={isOutreachLocked(l)} value={draftFor(l).review}
                          onChange={(e) => setDrafts((current) => ({ ...current, [l.id]: { ...draftFor(l), review: e.target.value } }))}>
                          <option value="">Select category…</option>
                          {reviewOptions.map((option) => <option key={option} value={option}>{option}</option>)}
                        </select>
                      ) : (<div className="space-y-2 pr-1 text-sm leading-5">{l.work_history?.length ? l.work_history.map((entry: any, index: number) => <div key={`category-${index}`} className="text-sm"><b>{index + 1}.</b> {entry.category || '—'}</div>) : (l.customer_review || '—')}</div>)}
                      {canEditWorkFields(l) && !isFrozen(l) && (isOutreachLocked(l)
                        ? <span className="inline-block mt-1 text-xs font-semibold text-emerald-700">{isConvertedLocked(l) ? '✓ Converted — cannot be edited' : '✓ Not interested — click Reopen for email and quotation'}</span>
                        : <button type="button" className="btn-primary !px-2 !py-1 text-xs mt-1" disabled={savingId === l.id || workFormIncomplete(draftFor(l), l)} onClick={() => saveLead(l)}>{savingId === l.id ? 'Saving…' : 'Save'}</button>)}
                      {role === 'EMPLOYEE' && !isFrozen(l) && (followupForms[l.id] || []).map((form, index) => <div key={`category-${index}`} className="mt-2"><select className="input text-xs" value={form.review} onChange={(e) => setFollowupForms((current) => ({ ...current, [l.id]: current[l.id].map((item, i) => i === index ? { ...item, review: e.target.value } : item) }))}><option value="">Select category…</option>{reviewOptions.map((option) => <option key={option} value={option}>{option}</option>)}</select><button type="button" className="btn-primary !px-2 !py-1 text-xs mt-1" disabled={savingId === l.id || workFormIncomplete(form, l)} onClick={() => saveFollowup(l, index)}>{savingId === l.id ? 'Saving…' : `Save follow-up ${(l.work_history?.length || 1) + index + 1}`}</button></div>)}
                    </td>
                    <td className="td align-top">
                      {canEditWorkFields(l) && !isFrozen(l) ? (
                        <select className="input text-xs" disabled={isOutreachLocked(l)} value={draftFor(l).progress}
                          onChange={(e) => setDrafts((current) => ({ ...current, [l.id]: { ...draftFor(l), progress: e.target.value } }))}>
                          <option value="">Select progress…</option>
                          {actionOptions.map((option) => {
                            const match = masters?.statuses?.find((s: any) => s.name.toLowerCase() === option.toLowerCase());
                            return <option key={option} value={match?.id || l.status_id}>{option}</option>;
                          })}
                        </select>
                      ) : (<div className="space-y-2 pr-1 text-sm leading-5">{l.work_history?.length ? labeledProgressHistory(l.work_history).map((entry: any, index: number) => <div key={`action-${index}`} className="text-sm"><b>{index + 1}.</b> {entry.displayAction}</div>) : nameOf('statuses', l.status_id)}</div>)}
                      {role === 'EMPLOYEE' && !isFrozen(l) && (followupForms[l.id] || []).map((form, index) => (
                        <div key={`progress-${index}`}>
                          <select className="input text-xs mt-2" value={form.progress} onChange={(e) => setFollowupForms((current) => ({ ...current, [l.id]: current[l.id].map((item, i) => i === index ? { ...item, progress: e.target.value } : item) }))}>
                            <option value="">Select progress…</option>
                            {actionOptions.map((option) => {
                              const match = masters?.statuses?.find((s: any) => s.name.toLowerCase() === option.toLowerCase());
                              return <option key={option} value={match?.id || l.status_id}>{option}</option>;
                            })}
                          </select>
                        </div>
                      ))}
                      {role === 'EMPLOYEE' && !isFrozen(l) && <button type="button" className="btn-secondary !px-2 !py-1 text-base font-bold ml-2" disabled={isOutreachLocked(l)} onClick={() => (followupForms[l.id]?.length ? closeFollowUp(l) : addFollowUp(l))} title={followupForms[l.id]?.length ? 'Close unsaved follow-up' : 'Add follow-up'}>{followupForms[l.id]?.length ? '×' : '+'}</button>}
                    </td>
                    <td className="td align-top">
                      {canEditWorkFields(l) && !isFrozen(l) ? (
                        <AutoGrowRemarks
                          disabled={isOutreachLocked(l)}
                          placeholder="Enter customer conversation remarks…"
                          value={draftFor(l).remarks}
                          onChange={(e) => setDrafts((current) => ({ ...current, [l.id]: { ...draftFor(l), remarks: e.target.value } }))}
                        />
                      ) : (<div className="space-y-2 pr-1 text-sm leading-5">{l.work_history?.length ? l.work_history.map((entry: any, index: number) => <div key={`remark-${index}`} className="text-sm whitespace-pre-wrap"><b>{index + 1}.</b> {entry.remarks}</div>) : <span className="block whitespace-pre-wrap" title={l.employee_remarks || ''}>{l.employee_remarks || '—'}</span>}</div>)}
                      {role === 'EMPLOYEE' && !isFrozen(l) && (followupForms[l.id] || []).map((form, index) => (
                        <AutoGrowRemarks
                          key={`remark-${index}`}
                          className="mt-2"
                          placeholder={`Follow-up ${(l.work_history?.length || 1) + index + 1} remarks…`}
                          value={form.remarks}
                          onChange={(e) => setFollowupForms((current) => ({ ...current, [l.id]: current[l.id].map((item, i) => i === index ? { ...item, remarks: e.target.value } : item) }))}
                        />
                      ))}
                    </td>
                    <td className="td align-top" onClick={(e) => e.stopPropagation()}>
                      {canEditWorkFields(l) && !isFrozen(l) ? (
                        <div className="min-w-0">
                          <input
                            type="date"
                            aria-label="Reminder date (optional)"
                            title={reminderUnlocked(draftFor(l), l) ? 'Optional reminder date' : 'Fill Category, Work Action and Remarks first'}
                            className="input text-xs w-full min-w-0"
                            min={todayISO}
                            disabled={isOutreachLocked(l) || savingId === l.id || !reminderUnlocked(draftFor(l), l)}
                            value={draftFor(l).reminderDate}
                            onChange={(e) => setDrafts((current) => ({ ...current, [l.id]: { ...draftFor(l), reminderDate: e.target.value } }))}
                          />
                        </div>
                      ) : (
                        <div className="min-w-0">
                          <div className="inline-flex items-center gap-1.5">
                            <span className={`text-sm tabular-nums ${l.reminder_done ? 'reminder-done' : ''}`}>{reminderOf(l) || '—'}</span>
                            {reminderOf(l) && reminderTickable(l) && (
                              <button
                                type="button"
                                title={l.reminder_done ? 'Mark reminder not done' : 'Mark reminder done'}
                                aria-label={l.reminder_done ? 'Mark reminder not done' : 'Mark reminder done'}
                                disabled={savingId === l.id}
                                onClick={(e) => { e.stopPropagation(); toggleLeadReminder(l); }}
                                className={tickBtn(!!l.reminder_done)}
                              >
                                ✓
                              </button>
                            )}
                          </div>
                          {l.work_history?.length ? (
                            <div className="mt-1 space-y-1 text-[11px] text-graphite-500">
                              {l.work_history.map((entry: any, index: number) => entry.reminder_date ? (
                                <div key={`remhist-${entry.id || index}`} className="tabular-nums inline-flex items-center gap-1">
                                  <span className={entry.reminder_done ? 'reminder-done' : ''}>{index + 1}. Reminder: {String(entry.reminder_date).slice(0, 10)}</span>
                                  {entry.id && reminderTickable(l) && (
                                    <button
                                      type="button"
                                      title={entry.reminder_done ? 'Mark reminder not done' : 'Mark reminder done'}
                                      aria-label={entry.reminder_done ? 'Mark reminder not done' : 'Mark reminder done'}
                                      disabled={savingId === l.id}
                                      onClick={(e) => { e.stopPropagation(); toggleEntryReminder(l, entry); }}
                                      className={`${tickBtn(!!entry.reminder_done)} !w-6 !h-6 !text-xs`}
                                    >
                                      ✓
                                    </button>
                                  )}
                                </div>
                              ) : null)}
                            </div>
                          ) : null}
                        </div>
                      )}
                      {role === 'EMPLOYEE' && !isFrozen(l) && (followupForms[l.id] || []).map((form, index) => (
                        <input
                          key={`remdate-${index}`}
                          type="date"
                          aria-label={`Follow-up ${index + 2} reminder date (optional)`}
                          title={reminderUnlocked(form, l) ? 'Optional reminder date' : 'Fill Category, Work Action and Remarks first'}
                          className="input text-xs w-full min-w-0 mt-2"
                          min={todayISO}
                          disabled={!reminderUnlocked(form, l)}
                          value={form.reminderDate}
                          onChange={(e) => setFollowupForms((current) => ({ ...current, [l.id]: current[l.id].map((item, i) => i === index ? { ...item, reminderDate: e.target.value } : item) }))}
                        />
                      ))}
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
                            <button type="button" data-reopen={l.sla_state === 'COMPLETED' ? '' : undefined} className={`btn-secondary !px-3 !py-1 text-xs ${l.sla_state === 'COMPLETED' ? '!bg-amber-100 !text-amber-900 !border-amber-300 hover:!bg-amber-200' : '!bg-blue-600 !text-white !border-blue-600 hover:!bg-blue-700'}`}
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
                      {role === 'EMPLOYEE' && (
                      <td className="td align-top text-center">
                        {isQuotationUnlocked(l) && !isFrozen(l) ? (
                          <>
                            <div className="flex flex-col items-center gap-1">
                              <button
                                type="button"
                                className="btn-primary !px-2 !py-1 text-xs"
                                onClick={(e) => {
                                  if (isOutreachLocked(l)) { e.preventDefault(); e.stopPropagation(); setValidationMessage(lockedLeadMessage(l)); return; }
                                  setQuoteFormLead(l);
                                }}
                                title={l.quotation_form?.quotation_number ? `Edit ${l.quotation_form.quotation_number}` : 'Open quotation form'}
                              >
                                {l.quotation_form?.quotation_number ? 'Edit' : 'Open form'}
                              </button>
                              {l.quotation_form?.quotation_number && (
                                <button
                                  type="button"
                                  data-quote-pdf
                                  className="btn-secondary !px-2 !py-1 text-[10px]"
                                  title={`Download ${l.quotation_form.quotation_number} PDF`}
                                  onClick={async (e) => {
                                    e.preventDefault();
                                    e.stopPropagation();
                                    if (isOutreachLocked(l)) { setValidationMessage(lockedLeadMessage(l)); return; }
                                    try {
                                      const res = await api.get(`/leads/${l.id}/quotation-form/pdf`, { responseType: 'blob' });
                                      const url = URL.createObjectURL(res.data);
                                      const a = document.createElement('a');
                                      a.href = url;
                                      a.download = `${l.quotation_form.quotation_number}.pdf`;
                                      document.body.appendChild(a);
                                      a.click();
                                      a.remove();
                                      setTimeout(() => URL.revokeObjectURL(url), 2000);
                                    } catch {
                                      if (!isOutreachLocked(l)) setQuoteFormLead(l);
                                    }
                                  }}
                                >
                                  PDF
                                </button>
                              )}
                            </div>
                            {l.quotation_form?.quotation_number ? (
                              <div className="text-[10px] text-graphite-600 mt-1 font-mono break-all max-w-[9rem] mx-auto" title={l.quotation_form.quotation_number}>
                                {l.quotation_form.quotation_number}
                                {l.quotation_form.revision ? ` · ${l.quotation_form.revision}` : ''}
                              </div>
                            ) : (
                              <div className="text-[10px] text-graphite-400 mt-1">Save form for REF</div>
                            )}
                          </>
                        ) : (
                          <span className="text-graphite-400">—</span>
                        )}
                      </td>
                    )}
                    <td className="td align-top text-right whitespace-nowrap">
                      {(() => {
                        if (!isQuotationUnlocked(l)) return <span className="text-graphite-400">—</span>;
                        const history = (l.quotation_value_history || []).filter((h: any) => h?.quotation_value != null && h.quotation_value !== '');
                        const rows = history.length
                          ? history
                          : (l.quotation_value != null && l.quotation_value !== ''
                            ? [{ revision: l.quotation_form?.revision || 'R0', quotation_value: l.quotation_value }]
                            : []);
                        if (!rows.length) return <span className="text-graphite-400">—</span>;
                        return (
                          <div className="inline-flex flex-col items-end gap-1 max-w-full">
                            {rows.map((h: any, idx: number) => (
                              <span
                                key={`${h.revision || 'R'}-${idx}`}
                                className="inline-flex items-center gap-1.5 max-w-full overflow-x-auto rounded-md border border-amber-200 bg-amber-50 px-2 py-0.5 text-xs font-semibold tabular-nums text-amber-900"
                                title={h.at ? `Saved ${h.at}` : undefined}
                              >
                                <span className="font-bold text-amber-700/80">{h.revision || `R${idx}`}</span>
                                <span>{inr(h.quotation_value).replace(/^₹/, '')}</span>
                              </span>
                            ))}
                          </div>
                        );
                      })()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          </>
        )}
        <div className="flex flex-col sm:flex-row sm:flex-wrap items-stretch sm:items-center justify-between gap-2 px-3 sm:px-4 py-3 border-t border-graphite-100 text-sm">
          <span className="text-graphite-500 text-center sm:text-left">Page {page} of {Math.max(1, Math.ceil(total / size))}</span>
          <div className="flex gap-2">
            <button className="btn-secondary !px-4 !py-2 min-h-[44px] flex-1 sm:flex-none" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>← Prev</button>
            <button className="btn-secondary !px-4 !py-2 min-h-[44px] flex-1 sm:flex-none" disabled={page * size >= total} onClick={() => setPage((p) => p + 1)}>Next →</button>
          </div>
        </div>
      </div>
      {quoteFormLead && (
        <QuotationFormModal
          lead={quoteFormLead}
          onClose={() => setQuoteFormLead(null)}
          onSaved={(leadId, summary) => {
            setItems((current) => current.map((item) => {
              if (item.id !== leadId) return item;
              const nextVal = summary.grand_total != null
                ? String(summary.grand_total)
                : summary.amount_excl != null
                  ? String(summary.amount_excl)
                  : item.quotation_value;
              const rev = String(summary.revision || 'R0').toUpperCase();
              const prevHist = Array.isArray(item.quotation_value_history) ? item.quotation_value_history : [];
              let quotation_value_history = prevHist;
              if (nextVal != null && nextVal !== '') {
                const exists = prevHist.some((h: any) => String(h.revision || '').toUpperCase() === rev);
                quotation_value_history = exists
                  ? prevHist.map((h: any) =>
                    String(h.revision || '').toUpperCase() === rev
                      ? { ...h, revision: rev, quotation_value: nextVal, at: new Date().toISOString() }
                      : h)
                  : [...prevHist, { revision: rev, quotation_value: nextVal, at: new Date().toISOString() }];
              }
              return {
                ...item,
                quotation_form: summary,
                quotation_value: nextVal,
                quotation_value_history,
              };
            }));
          }}
        />
      )}
      {conversionToConfirm && (
        <div className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-4 pb-[env(safe-area-inset-bottom)]" onClick={() => setConversionToConfirm(null)}>
          <div role="dialog" aria-modal="true" aria-labelledby="confirm-conversion-title" className="card w-full max-w-md max-h-[90dvh] overflow-y-auto p-4 sm:p-6" onClick={(e) => e.stopPropagation()} onKeyDown={(e) => { if (e.key === 'Escape') setConversionToConfirm(null); }}>
            <h3 id="confirm-conversion-title" className="text-lg font-semibold text-graphite-900">Complete converted lead?</h3>
            <p className="text-sm text-graphite-600 mt-2">Once completed, this converted lead cannot be edited or reopened. Select Cancel to recheck the details, or OK to complete it.</p>
            <div className="flex justify-end gap-2 mt-5">
              <button type="button" className="btn-secondary min-h-[44px]" autoFocus onClick={() => setConversionToConfirm(null)}>Cancel</button>
              <button type="button" className="btn-primary min-h-[44px]" onClick={() => saveLead(conversionToConfirm, true, true)}>OK</button>
            </div>
          </div>
        </div>
      )}
      {validationMessage && (
        <div className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-4 pb-[env(safe-area-inset-bottom)]" onClick={() => setValidationMessage('')}>
          <div className="card w-full max-w-md max-h-[90dvh] overflow-y-auto p-4 sm:p-6" onClick={(e) => e.stopPropagation()}>
            <h3 className="text-lg font-semibold text-graphite-900">{validationMessage.includes('cannot be edited') ? 'Cannot edit this lead' : validationMessage.toLowerCase().includes('car') ? 'Check the car count' : 'Complete the lead details'}</h3>
            <p className="text-sm text-graphite-600 mt-2 break-words">{validationMessage}</p>
            <div className="flex justify-end mt-5"><button type="button" className="btn-primary min-h-[44px] px-6" onClick={() => setValidationMessage('')}>OK</button></div>
          </div>
        </div>
      )}
    </div>
  );
}

/* ================= EMPLOYEE LEADS ================= */
export function EmployeeLeads() {
  const tableScroll = useDragScroll<HTMLDivElement>();
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
  const reviewOptions = ['A+ (Immediate)', 'A (3-6 months)', 'B (6-9 months)', 'C (Planning Stage)'];
  const workActionOptions = ['In Followup', 'Meeting', 'Site Visit', 'Quotation sent', 'Converted', 'Not Interested'];
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
    value: items.filter((l) => {
      const v = (l.customer_review || '').trim();
      if (label === 'B (6-9 months)') return v === 'B (6-9 months)' || v === 'B (1 year)';
      if (label === 'C (Planning Stage)') return v === 'C (Planning Stage)' || v === 'C (plan stage)' || v === 'Planning Stage';
      return v === label;
    }).length,
  }));
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
              { label: 'Total leads', value: total, bg: 'bg-[#1e3a5f]' },
              { label: 'Pending', value: needsContact, bg: 'bg-[#c0392b]' },
              { label: 'Overdue', value: overdue, bg: 'bg-[#7b241c]' },
              { label: 'Responded', value: done, bg: 'bg-[#2F9E44]' },
            ].map((s) => (
              <div key={s.label} className={`${s.bg} text-white rounded-lg px-3 py-3 text-center shadow-sm`}>
                <div className="text-2xl font-bold tabular-nums">{s.value}</div>
                <div className="text-xs uppercase tracking-wide opacity-90 font-semibold mt-1">{s.label}</div>
              </div>
            ))}
          </div>
          <div className="mb-4">
            <div className="text-sm font-semibold text-graphite-600 uppercase tracking-wide mb-2">Category (A+ / A / B / C)</div>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
              {reviewCounts.map((s) => {
                const bg = categoryTileBg(s.label);
                const text = categoryTileText(s.label);
                return (
                  <div key={s.label} className={`${bg} ${text} rounded-lg px-3 py-4 text-center shadow-sm`}>
                    <div className="text-3xl font-bold tabular-nums">{s.value}</div>
                    <div className="text-sm uppercase tracking-wide opacity-95 font-semibold mt-1.5 leading-tight">{s.label}</div>
                  </div>
                );
              })}
            </div>
          </div>
          <div className="mb-4">
            <div className="text-sm font-semibold text-graphite-600 uppercase tracking-wide mb-2">Work action</div>
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2">
              {workActionCounts.map((s) => {
                const bg = PROGRESS_TILE_BG[s.label] || (s.label === 'Assigned' ? 'bg-[#0e7490]' : 'bg-[#1e3a5f]');
                const text = PROGRESS_TILE_TEXT[s.label] || 'text-white';
                return (
                  <div key={s.label} className={`${bg} ${text} rounded-lg px-3 py-4 text-center shadow-sm`}>
                    <div className="text-3xl font-bold tabular-nums">{s.value}</div>
                    <div className="text-sm uppercase tracking-wide opacity-95 font-semibold mt-1.5 leading-tight">{s.label}</div>
                  </div>
                );
              })}
            </div>
          </div>
          <div className="card overflow-hidden">
            <div ref={tableScroll.ref} className={`overflow-x-auto drag-scroll ${tableScroll.dragging ? 'is-dragging' : ''}`}>
              <div className="text-[11px] text-graphite-400 px-4 pt-2 select-none" aria-hidden="true">⇔ Drag to see more columns</div>
              <table className="w-full min-w-[1280px]">
                <thead className="bg-graphite-50"><tr>
                  <th className="th">Enquiry</th><th className="th">Customer details</th>
                  <th className="th min-w-[260px] w-[280px]">Contact / Email</th><th className="th text-center">Cars</th><th className="th text-right">Lead Value</th><th className="th">Source</th>
                  <th className="th">Product</th><th className="th">Status</th><th className="th">Overdue</th>
                  <th className="th">Due date</th>
                  <th className="th">First contact</th><th className="th">Enquiry date</th>
                </tr></thead>
                <tbody>
                  {items.map((l) => (
                    <tr key={l.id} className={leadRowColour(l, nameOf('statuses', l.status_id))}>
                      <td className="td font-semibold text-brand-700 whitespace-nowrap"><Link to={`/leads/${l.id}`}>{l.enquiry_number}</Link></td>
                      <td className="td">
                        <div className="font-medium text-graphite-900">{l.customer_name || '—'}</div>
                        <div className="text-sm text-graphite-700 mt-1.5">{l.company_name || '—'}</div>
                        <div className="text-sm text-graphite-600 mt-1.5">{l.city || '—'}</div>
                      </td>
                      <td className="td min-w-[260px] w-[280px]">
                        <div className="whitespace-nowrap">{l.contact_number || '—'}{l.alternate_contact ? <span className="block text-xs text-graphite-400">alt: {l.alternate_contact}</span> : null}</div>
                        <div className="text-xs mt-1.5 break-words [overflow-wrap:anywhere]">{l.email ? <a className="text-brand-700 hover:underline" href={`mailto:${l.email}`}>{l.email}</a> : <span className="text-graphite-400">No email</span>}</div>
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
  const [reminderDate, setReminderDate] = useState('');
  const todayISO = new Date().toISOString().slice(0, 10);
  const [assignEmp, setAssignEmp] = useState('');
  const [reassignReason, setReassignReason] = useState('');
  const [productId, setProductId] = useState('');
  const [cars, setCars] = useState('');
  const [busy, setBusy] = useState(false);
  const [pricingBusy, setPricingBusy] = useState(false);
  const [detailsBusy, setDetailsBusy] = useState(false);
  const [details, setDetails] = useState({
    enquiry_number: '',
    enquiry_date: '',
    customer_name: '',
    company_name: '',
    contact_number: '',
    city: '',
    quantity_raw: '',
    source_id: '',
    product_id: '',
    email: '',
  });
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
      setDetails({
        enquiry_number: l.enquiry_number || '',
        enquiry_date: (l.enquiry_date || '').slice(0, 10),
        customer_name: l.customer_name || '',
        company_name: l.company_name || '',
        contact_number: l.contact_number || '',
        city: l.city || '',
        quantity_raw: l.quantity_raw || (l.quantity_num != null ? String(l.quantity_num) : ''),
        source_id: l.source_id || '',
        product_id: l.product_id || '',
        email: l.email || '',
      });
    }
  }, [l?.status_id, l?.id, l?.product_id, l?.quantity_raw, l?.quantity_num, l?.updated_at, l?.enquiry_number, l?.enquiry_date, l?.customer_name, l?.company_name, l?.contact_number, l?.city, l?.source_id, l?.email]);
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
  const convertedLocked = role === 'EMPLOYEE' && l.sla_state === 'COMPLETED' && nameOf('statuses', l.status_id) === 'Converted';
  const notInterestedLocked = role === 'EMPLOYEE' && l.sla_state === 'COMPLETED' && ['Not Interested', 'Not Interested/Spam'].includes(nameOf('statuses', l.status_id));
  const leadLocked = convertedLocked || notInterestedLocked;
  /** Deep freeze: employee clicked Done (COMPLETED). Everything stays dead until Reopen — except Reopen itself. */
  const frozen = role === 'EMPLOYEE' && l.sla_state === 'COMPLETED';
  const selectedProduct = masters?.products?.find((p: any) => p.id === productId);
  const preview = previewLeadValue(selectedProduct?.price_per_car ?? l.price_per_car, String(cars || '').trim() || '2');
  const needsContact = !l.first_contact_at && !!l.primary_employee_id;
  const canUpdateProgress = !leadLocked && !frozen && (role === 'ADMIN' || (role === 'EMPLOYEE' && !!l.primary_employee_id));
  const canEditPricing = !leadLocked && !frozen && (role === 'ADMIN' || (role === 'EMPLOYEE' && l.primary_employee_id));
  const rr = l.reassignment_request;
  const canRequestReassign = !leadLocked && !frozen && role === 'EMPLOYEE' && !!l.primary_employee_id && !rr;
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
    if (leadLocked || frozen) return;
    if (!progressId) { setErr('Select work progress'); return; }
    if (!remarks.trim()) { setErr('Enter remarks about the conversation'); return; }
    if (!reminderDate) { setErr('Select a reminder date'); return; }
    setBusy(true); setErr(''); setOkMsg('');
    try {
      await api.post(`/leads/${id}/status`, {
        new_status_id: progressId,
        reason: remarks.trim(),
        method,
        reminder_date: reminderDate || undefined,
      });
      setRemarks('');
      setOkMsg('Work progress saved');
      reload();
    } catch (e: any) {
      setErr(e?.response?.data?.detail || 'Could not save work progress');
    } finally { setBusy(false); }
  };
  /** Reopen a frozen (Done) lead from the detail page: same path as the list Reopen button. */
  const reopenDetailLead = async () => {
    if (busy || leadLocked || !frozen) return;
    if (!l.employee_remarks?.trim()) { setErr('No saved conversation to reopen with.'); return; }
    setBusy(true); setErr(''); setOkMsg('');
    try {
      await api.post(`/leads/${id}/status`, {
        new_status_id: l.status_id,
        reason: l.employee_remarks,
        method: 'Call',
        customer_review: l.customer_review || '',
        sla_state: 'PENDING',
      });
      setOkMsg('Lead reopened — back to normal.');
      await reload();
    } catch (e: any) {
      setErr(e?.response?.data?.detail || 'Could not reopen lead');
    } finally { setBusy(false); }
  };
  /** Tick the live reminder done / not done on the detail page: strikes it, keeps the date. */
  const toggleDetailReminder = async () => {
    if (busy || leadLocked || frozen || !l?.reminder_date) return;
    setBusy(true); setErr('');
    try {
      await api.put(`/leads/${id}`, { reminder_done: !l.reminder_done });
      await reload();
    } catch (e: any) {
      setErr(e?.response?.data?.detail || 'Could not update reminder');
    } finally { setBusy(false); }
  };
  /** Tick a single timeline entry's reminder done / not done. */
  const toggleDetailEntryReminder = async (entry: any) => {
    if (busy || leadLocked || frozen || !entry?.id) return;
    setBusy(true); setErr('');
    try {
      await api.post(`/leads/${id}/activities/${entry.id}/reminder-done`, { done: !entry.reminder_done });
      await reload();
    } catch (e: any) {
      setErr(e?.response?.data?.detail || 'Could not update reminder');
    } finally { setBusy(false); }
  };
  const doAssign = async () => {    if (!assignEmp) return;
    setBusy(true); setErr(''); setOkMsg('');
    try {
      const employeeName = masters?.employees?.find((emp: any) => emp.id === assignEmp)?.name || 'This employee';
      const customerName = l.customer_name || 'this customer';
      await api.post(`/leads/${id}/assign`, { employee_id: assignEmp, role: 'PRIMARY', manual: true });
      setL((current: any) => current ? { ...current, primary_employee_id: assignEmp, pending_assignment: false } : current);
      setOkMsg(`${employeeName} is assigned to this customer ${customerName}.`);
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
    if (!canEditPricing || leadLocked) return;
    setPricingBusy(true); setErr(''); setOkMsg('');
    const productName = selectedProduct?.name || '';
    const problem = carCountError(cars, productName);
    if (problem) { setErr(problem); setPricingBusy(false); return; }
    try {
      const { data } = await api.put(`/leads/${id}`, {
        product_id: productId || null,
        quantity_raw: String(cars || '').trim() || '2',
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
  const saveDetails = async () => {
    if (role !== 'ADMIN' || detailsBusy) return;
    setDetailsBusy(true); setErr(''); setOkMsg('');
    try {
      const { data } = await api.put(`/leads/${id}`, {
        enquiry_date: details.enquiry_date || null,
        customer_name: details.customer_name.trim(),
        company_name: details.company_name.trim(),
        contact_number: details.contact_number.trim(),
        city: details.city.trim(),
        email: details.email.trim(),
        source_id: details.source_id || null,
        product_id: details.product_id || null,
        quantity_raw: details.quantity_raw.trim(),
      });
      setL(data);
      setOkMsg('Lead details saved');
    } catch (e: any) {
      setErr(e?.response?.data?.detail || 'Could not save lead details');
    } finally { setDetailsBusy(false); }
  };
  return (
    <div className="space-y-5">
      <div className="card p-4 sm:p-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <div className="flex items-center gap-3 flex-wrap">
              <h1 className="text-xl sm:text-2xl font-bold text-graphite-900 break-words">{l.enquiry_number}</h1>
              {l.legacy_enquiry_no != null && <span className="text-sm text-graphite-500">Excel #{l.legacy_enquiry_no}</span>}
              <StatusBadge value={nameOf('statuses', l.status_id)} />
              {role === 'EMPLOYEE' ? <SlaBadge value={l.sla_state} /> : <SlaBadge value={l.pending_assignment ? 'PENDING' : l.sla_state} />}
              {l.pending_assignment && <span className="text-xs font-medium text-amber-700 bg-amber-50 ring-1 ring-amber-200 px-2 py-0.5 rounded-full">Unassigned</span>}
              {needsContact && <span className="text-xs font-medium text-sky-800 bg-sky-50 ring-1 ring-sky-200 px-2 py-0.5 rounded-full">Speak to customer</span>}
            </div>
            <p className="text-graphite-600 mt-1 text-lg">{l.customer_name || '—'} {l.company_name && <span className="text-graphite-400">· {l.company_name}</span>}</p>
            <div className="flex flex-wrap gap-x-5 gap-y-1 mt-2 text-sm">
              <span>📞 {l.contact_number ? (frozen ? <span className="font-semibold">{l.contact_number}</span> : <a className="text-brand-700 font-semibold hover:underline" href={`tel:${String(l.contact_number).replace(/\s/g, '')}`}>{l.contact_number}</a>) : '—'}{l.alternate_contact ? <span className="text-graphite-400"> (alt: {l.alternate_contact})</span> : null}</span>
              <span>✉️ {l.email ? ((leadLocked || frozen) ? <span className="font-semibold">{l.email}</span> : <a className="text-brand-700 font-semibold hover:underline" href={`mailto:${l.email}`}>{l.email}</a>) : <span className="text-graphite-400">No email</span>}</span>
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
      {frozen && !convertedLocked && (
        <div className="rounded-xl border border-amber-300 bg-amber-50 px-4 py-3 flex flex-wrap items-center justify-between gap-3">
          <p className="text-sm text-amber-900">This lead is completed and frozen — links, buttons and dropdowns are locked until you reopen it.</p>
          <button type="button" className="btn-secondary !bg-amber-100 !text-amber-900 !border-amber-300 hover:!bg-amber-200 min-h-[44px]" disabled={busy} onClick={reopenDetailLead}>
            {busy ? 'Working…' : 'Reopen'}
          </button>
        </div>
      )}
      {role === 'ADMIN' && (
        <Card title="Edit lead details">
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
            <div>
              <label className="text-xs font-medium text-graphite-600">Enq no</label>
              <input
                className="input mt-1 bg-graphite-50 text-graphite-500"
                value={details.enquiry_number}
                readOnly
                disabled
                title="Enquiry number is auto-assigned and cannot be changed"
              />
            </div>
            <div>
              <label className="text-xs font-medium text-graphite-600">Date Received</label>
              <input className="input mt-1" type="date" value={details.enquiry_date} onChange={(e) => setDetails((cur) => ({ ...cur, enquiry_date: e.target.value }))} />
            </div>
            <div>
              <label className="text-xs font-medium text-graphite-600">Lead Name / Full Name</label>
              <input className="input mt-1" value={details.customer_name} onChange={(e) => setDetails((cur) => ({ ...cur, customer_name: e.target.value }))} />
            </div>
            <div>
              <label className="text-xs font-medium text-graphite-600">Company / Organisation</label>
              <input className="input mt-1" value={details.company_name} onChange={(e) => setDetails((cur) => ({ ...cur, company_name: e.target.value }))} />
            </div>
            <div>
              <label className="text-xs font-medium text-graphite-600">Contact No.</label>
              <input className="input mt-1" value={details.contact_number} onChange={(e) => setDetails((cur) => ({ ...cur, contact_number: e.target.value }))} />
            </div>
            <div>
              <label className="text-xs font-medium text-graphite-600">City</label>
              <input className="input mt-1" value={details.city} onChange={(e) => setDetails((cur) => ({ ...cur, city: e.target.value }))} />
            </div>
            <div>
              <label className="text-xs font-medium text-graphite-600">No. of Cars</label>
              <input className="input mt-1" type="number" min="1" step="1" value={details.quantity_raw} onChange={(e) => setDetails((cur) => ({ ...cur, quantity_raw: e.target.value }))} onKeyDown={(e) => { const next = arrowStep(e.currentTarget.value, e.key, 1, 1); if (next == null) return; e.preventDefault(); setDetails((cur) => ({ ...cur, quantity_raw: next })); }} />
            </div>
            <div>
              <label className="text-xs font-medium text-graphite-600">Lead Source</label>
              <select className="input mt-1" value={details.source_id} onChange={(e) => setDetails((cur) => ({ ...cur, source_id: e.target.value }))}>
                <option value="">Select source…</option>
                {(masters?.sources || []).map((s: any) => <option key={s.id} value={s.id}>{s.name}</option>)}
              </select>
            </div>
            <div>
              <label className="text-xs font-medium text-graphite-600">Product / Type</label>
              <select className="input mt-1" value={details.product_id} onChange={(e) => setDetails((cur) => ({ ...cur, product_id: e.target.value }))}>
                <option value="">Select product…</option>
                {(masters?.products || []).map((p: any) => <option key={p.id} value={p.id}>{p.name}</option>)}
              </select>
            </div>
            <div>
              <label className="text-xs font-medium text-graphite-600">Email</label>
              <input className="input mt-1" type="email" value={details.email} onChange={(e) => setDetails((cur) => ({ ...cur, email: e.target.value }))} />
            </div>
          </div>
          <p className="text-xs text-graphite-500 mt-3">Saving product and number of cars also recalculates Lead Value.</p>
          <button type="button" className="btn-primary mt-3" disabled={detailsBusy} onClick={saveDetails}>
            {detailsBusy ? 'Saving…' : 'Save lead details'}
          </button>
        </Card>
      )}
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
            <input className="input mt-1" type="number" min="2" step={allowsOddCars(selectedProduct?.name || '') ? 1 : 2} disabled={!canEditPricing} value={cars} onChange={(e) => setCars(e.target.value)} onKeyDown={(e) => { const next = arrowStep(e.currentTarget.value, e.key, allowsOddCars(selectedProduct?.name || '') ? 1 : 2, 2); if (next == null) return; e.preventDefault(); setCars(next); }} placeholder="2" />
            <p className="text-[11px] text-graphite-500 mt-1">Starts at 2. Blank saves as 2. Odd or even: Puzzle Parking, Pit Puzzle Parking, Car Elevator, Shuttle Parking, ASRS Parking. Even only: Two Post, Four Post, Pit Stack, Tower.</p>
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

      {role === 'ADMIN' && (
        <Card title="Assign to employee">
          {rr?.status === 'ACCEPTED' && (
            <p className="text-sm text-amber-800 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2 mb-3">
              Reassignment accepted for <b>{rr.requested_by_name}</b>. Choose a new employee below — ownership stays unchanged until you assign.
              {rr.reason ? <span className="block text-xs mt-1 text-amber-700">Reason: {rr.reason}</span> : null}
            </p>
          )}
          <p className="text-xs text-graphite-500 mb-3">
            Current employee: {l.primary_employee_id ? nameOf('employees', l.primary_employee_id) : 'Not assigned'}
          </p>
          <div className="max-h-64 overflow-y-auto border border-graphite-100 rounded-lg">
            {(masters?.employees || []).length === 0 ? (
              <p className="text-sm text-graphite-500 p-3">No employees to assign.</p>
            ) : (masters.employees as any[]).map((emp: any) => (
              <label key={emp.id} className={`flex items-center gap-2 px-3 py-2 text-sm cursor-pointer border-b border-graphite-50 last:border-0 ${assignEmp === emp.id ? 'bg-brand-50' : 'hover:bg-graphite-50'}`}>
                <input type="radio" name="assign-employee" checked={assignEmp === emp.id} onChange={() => setAssignEmp(emp.id)} />
                <span>{emp.name}</span>
                {emp.id === l.primary_employee_id && <span className="text-[10px] text-graphite-400">current</span>}
              </label>
            ))}
          </div>
          <button type="button" className="btn-primary mt-4" disabled={!assignEmp || busy || assignEmp === l.primary_employee_id} onClick={doAssign}>
            {busy ? 'Assigning…' : 'Assign to employee'}
          </button>
          {l.primary_employee_id && (
            <p className="mt-3 text-sm text-emerald-800 bg-emerald-50 border border-emerald-200 rounded-lg px-3 py-2">
              {nameOf('employees', l.primary_employee_id)} is assigned to this customer {l.customer_name || '—'}.
            </p>
          )}
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
          {convertedLocked && (
            <Card title="Converted">
              <p className="text-sm text-emerald-800">This converted lead cannot be edited or reopened, and webmail cannot be opened from it.</p>
            </Card>
          )}
          {notInterestedLocked && (
            <Card title="Not interested">
              <p className="text-sm text-amber-900">This lead is locked. Click Reopen on the leads page to edit it and open webmail and the quotation form.</p>
            </Card>
          )}
          {canUpdateProgress && (
            <Card title="Update work progress">
              <p className="text-xs text-graphite-500 mb-3">
                {needsContact
                  ? ((l.source_name || nameOf('sources', l.source_id)) === 'Direct Call'
                    ? 'Direct Call is urgent. Update work progress within 24 hours.'
                    : 'After you speak to the assigned customer, set progress and add remarks. This also clears an overdue contact.')
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
                <div>
                  <label className="text-xs font-medium text-graphite-600">Reminder Date</label>
                  <input
                    type="date"
                    className="input mt-1"
                    min={todayISO}
                    disabled={!progressId || !remarks.trim()}
                    title={progressId && remarks.trim() ? 'Optional reminder date' : 'Fill Work progress and Remarks first'}
                    value={reminderDate}
                    onChange={(e) => setReminderDate(e.target.value)}
                  />
                </div>
                <button onClick={saveProgress} disabled={busy || !progressId || !remarks.trim() || !reminderDate} className="btn-primary w-full">
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
              {l.reminder_date && (
                <p className="text-xs text-graphite-500 mt-2 tabular-nums inline-flex items-center gap-1.5">
                  <span className={l.reminder_done ? 'reminder-done' : ''}>Reminder: {String(l.reminder_date).slice(0, 10)}</span>
                  {!leadLocked && !frozen && (
                    <button type="button" title={l.reminder_done ? 'Mark reminder not done' : 'Mark reminder done'} aria-label={l.reminder_done ? 'Mark reminder not done' : 'Mark reminder done'} disabled={busy} onClick={toggleDetailReminder} className={`inline-flex items-center justify-center w-7 h-7 rounded-md border text-sm shrink-0 ${l.reminder_done ? 'border-emerald-600 bg-emerald-600 text-white hover:bg-emerald-700' : 'border-emerald-300 bg-emerald-50 text-emerald-700 hover:bg-emerald-100'}`}>✓</button>
                  )}
                </p>
              )}
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
                    {a.reminder_date && (
                      <p className="text-xs text-graphite-500 mt-1 tabular-nums inline-flex items-center gap-1.5">
                        <span className={a.reminder_done ? 'reminder-done' : ''}>Reminder: {String(a.reminder_date).slice(0, 10)}</span>
                        {!leadLocked && !frozen && a.id && (
                          <button type="button" title={a.reminder_done ? 'Mark reminder not done' : 'Mark reminder done'} aria-label={a.reminder_done ? 'Mark reminder not done' : 'Mark reminder done'} disabled={busy} onClick={() => toggleDetailEntryReminder(a)} className={`inline-flex items-center justify-center w-6 h-6 rounded-md border text-xs shrink-0 ${a.reminder_done ? 'border-emerald-600 bg-emerald-600 text-white hover:bg-emerald-700' : 'border-emerald-300 bg-emerald-50 text-emerald-700 hover:bg-emerald-100'}`}>✓</button>
                        )}
                      </p>
                    )}
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
  const [createdLeads, setCreatedLeads] = useState<Array<{ lead_id?: string; enquiry_number: string; customer_name: string }>>([]);
  const errMsg = (e: any) => {
    if (e?.code === 'ECONNABORTED') return 'The import took too long for the page to wait. Refresh Leads — the rows may already be saved.';
    const detail = e?.response?.data?.detail;
    if (typeof detail === 'string' && detail) return detail;
    if (!e?.response) return 'Upload failed. Is the backend running?';
    return 'Upload failed. Is the backend running?';
  };

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
    setBusy(true); setDone(null); setCreatedLeads([]); setError(''); setOkMsg(''); setErrors([]);
    try {
      const fd = new FormData();
      fd.append('file', file);
      if (withSheet) fd.append('sheet', withSheet);
      const { data } = await api.post('/import/excel', fd, { timeout: 180000 });
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
  const [importProgress, setImportProgress] = useState('');
  const confirm = async () => {
    if (!res?.batch_id || confirming) return;
    setConfirming(true); setError(''); setOkMsg(''); setImportProgress('Starting import…');
    const batchId = res.batch_id;
    try {
      const { data: started } = await api.post(`/import/${batchId}/confirm`, null, { timeout: 60000 });
      let data = started;
      // Large Excel files import in the background so Render's HTTP limit cannot abort them.
      if (started?.status === 'IMPORTING') {
        for (let i = 0; i < 900; i += 1) {
          await new Promise((resolve) => setTimeout(resolve, 2000));
          const { data: status } = await api.get(`/import/${batchId}/status`, { timeout: 30000 });
          data = status;
          setImportProgress(`Importing… ${status.imported || 0} / ${status.total || res.total || '?'} saved`);
          if (status.status === 'DONE' || status.status === 'FAILED') break;
        }
      }
      if (data?.status === 'FAILED') {
        setError(data.error_message || 'Import failed — re-upload the Excel file');
        loadBatches();
        return;
      }
      if (data?.status === 'IMPORTING') {
        setError('Import is still running on the server. Refresh Leads in a minute, or check Recent import batches.');
        loadBatches();
        return;
      }
      setDone(data);
      setCreatedLeads(Array.isArray(data.created_leads) ? data.created_leads : []);
      setErrors(data.errors || []);
      setRes(null);
      setImportProgress('');
      loadBatches();
      if ((data.errors || []).length) setTab(data.errors.some((x: any) => x.reason === 'DUPLICATE') ? 'duplicates' : 'invalid');
    } catch (e: any) { setError(errMsg(e)); } finally { setConfirming(false); setImportProgress(''); }
  };

  const pickFile = (f: File | null) => {
    setFile(f); setSheets([]); setSheet(''); setRes(null); setDone(null); setCreatedLeads([]); setErrors([]); setError(''); setOkMsg('');
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
      const enq = data.enquiry_number || '—';
      const name = data.customer_name || '—';
      setOkMsg(`Added as ${enq} — ${name}${data.assigned ? ' (assigned)' : ' (pending assignment)'}`);
      setCreatedLeads((prev) => [
        { lead_id: data.lead_id, enquiry_number: enq, customer_name: name },
        ...prev,
      ]);
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
        subtitle="Columns: Enq no (ignored — auto-assigned), Received date, Name, Company (optional), Contact no, Email, City, No. of cars, Lead source, Product/type. Admin can view duplicates/invalid and Add to leads or Delete."
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
              {confirming ? (importProgress || 'Importing…') : `4 · Confirm import (${res.valid} leads)`}{!confirming && (res.duplicates || res.invalid) ? ` · keep ${res.duplicates + res.invalid} for review` : ''}
            </button>
            {confirming && importProgress && (
              <p className="text-sm text-graphite-600 mt-2">{importProgress}. Keep this tab open.</p>
            )}
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

      {(done || createdLeads.length > 0) && (
        <div className="bg-[#2F9E44]/10 border border-[#2F9E44]/40 rounded-xl p-5 text-sm space-y-3">
          {done && (
            <div>
              <b>Import complete:</b> {done.imported} imported · {done.assigned ?? 0} assigned · {done.pending ?? 0} pending · {done.duplicates} duplicates · {done.invalid} invalid.
            </div>
          )}
          {createdLeads.length > 0 && (
            <div>
              <div className="font-semibold text-emerald-900 mb-2">
                Assigned enquiry numbers ({createdLeads.length})
              </div>
              <div className="overflow-x-auto rounded-lg border border-emerald-200 bg-white">
                <table className="w-full min-w-[420px] text-sm">
                  <thead className="bg-emerald-50">
                    <tr>
                      <th className="th text-left">#</th>
                      <th className="th text-left">Enquiry no</th>
                      <th className="th text-left">Lead name</th>
                      <th className="th text-right">Open</th>
                    </tr>
                  </thead>
                  <tbody>
                    {createdLeads.map((row, i) => (
                      <tr key={`${row.enquiry_number}-${row.lead_id || i}`} className={i % 2 ? 'bg-emerald-50/40' : 'bg-white'}>
                        <td className="td">{i + 1}</td>
                        <td className="td font-semibold tabular-nums text-emerald-900">{row.enquiry_number}</td>
                        <td className="td">{row.customer_name || '—'}</td>
                        <td className="td text-right">
                          {row.lead_id ? (
                            <Link className="text-brand-700 hover:underline font-medium" to={`/leads/${row.lead_id}`}>
                              View
                            </Link>
                          ) : '—'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}

      {showReview && (
        <Card title="Admin review — Add to leads or Delete" action={
          <button type="button" className="btn-secondary !px-3 !py-1.5 text-sm" onClick={() => { setErrors([]); setEditId(null); }}>
            Close
          </button>
        }>
          <p className="text-sm text-graphite-500 mb-3">
            View skipped rows below. <b>Correct</b> fields if needed, then <b>Add to leads</b>. Enquiry numbers from Excel are ignored — the system assigns the next number. <b>Delete</b> removes it from this list.
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
                      <span className="text-[10px] uppercase tracking-wide text-graphite-400 mr-2">{b.source === 'sheets' ? 'Legacy' : 'Excel'}</span>
                      {b.source === 'sheets' ? (b.sheet_name || 'Legacy sync') : b.file_name}
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
                <label className="text-xs font-medium text-graphite-600">Enquiry no (ignored)</label>
                <input
                  className="input mt-1 bg-graphite-50 text-graphite-500"
                  value={editForm.enq}
                  readOnly
                  disabled
                  title="Excel enquiry numbers are ignored — system assigns the next number"
                />
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
  const rows = barRows(data);
  return (
    <Card title={title} action={onDownload && (
      <button type="button" className="btn-secondary !px-3 !py-1 text-xs" onClick={onDownload}>
        Download Excel
      </button>
    )}>
      {rows.length === 0 ? <EmptyState title="No data" /> : (
        <div className="h-80">
          <ResponsiveContainer>
            <BarChart data={rows} margin={{ top: 8, right: 12, left: 8, bottom: 72 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
              <XAxis
                dataKey={x}
                type="category"
                interval={0}
                angle={-28}
                textAnchor="end"
                height={70}
                tick={{ fontSize: 10 }}
              />
              <YAxis type="number" allowDecimals={false} tick={{ fontSize: 11 }} />
              <Tooltip />
              <Bar dataKey={y} fill="#65A30D" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </Card>
  );
}

type ReportFilter = {
  mode: 'custom' | 'week' | 'month' | 'year';
  month: string;
  week: string;
  year: string;
  fromDate: string;
  toDate: string;
};

export function Reports() {
  const today = new Date();
  const defaultMonth = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}`;
  const defaultWeek = today.toISOString().slice(0, 10);
  const defaultYear = String(today.getFullYear());
  const emptyFilter = (): ReportFilter => ({
    mode: 'custom', month: defaultMonth, week: defaultWeek, year: defaultYear, fromDate: '', toDate: '',
  });

  type ReportId = 'dashboard_history' | 'source' | 'product' | 'category' | 'lead_value' | 'quotation' | 'employee' | 'monthly' | 'detailed';
  const REPORT_MENU: Array<{ id: ReportId; title: string; description: string; accent: string }> = [
    { id: 'dashboard_history', title: 'Dashboard History Report', description: 'Dashboard tiles + source/product/category tables & charts with full progress and category history counts.', accent: 'bg-[#0f766e]' },
    { id: 'source', title: 'Lead Source Report', description: 'Leads by source with progress history (follow-up, meeting, site visit, quotation, converted) and chart.', accent: 'bg-[#1e3a5f]' },
    { id: 'product', title: 'Product Wise Report', description: 'Leads by product with progress history counts including converted.', accent: 'bg-[#0f766e]' },
    { id: 'category', title: 'Category Wise Report', description: 'A+ (Immediate), A (3-6 months), B (6-9 months), C (Planning Stage) funnel table plus chart.', accent: 'bg-[#0e7490]' },
    { id: 'lead_value', title: 'Lead Value Report', description: 'Total lead value by product, source and period with charts.', accent: 'bg-[#3F6212]' },
    { id: 'quotation', title: 'Quotation Report', description: 'Only Quotation sent leads — order value, GST and grand total.', accent: 'bg-[#b45309]' },
    { id: 'employee', title: 'Employee Workload Report', description: 'Assigned lead count per employee.', accent: 'bg-[#334155]' },
    { id: 'monthly', title: 'Monthly Lead Volume', description: 'Pick a month range, view the chart and table, then download Excel or PDF.', accent: 'bg-[#4338ca]' },
    { id: 'detailed', title: 'Detailed Lead Report', description: 'Full lead-page details — filter by week, month, or custom date range; view table and download Excel/PDF.', accent: 'bg-[#0f172a]' },
  ];

  const [activeReport, setActiveReport] = useState<ReportId | null>(null);

  const [lvFilter, setLvFilter] = useState<ReportFilter>(emptyFilter);
  const [quoteFilter, setQuoteFilter] = useState<ReportFilter>(emptyFilter);
  const [sourceFilter, setSourceFilter] = useState<ReportFilter>(emptyFilter);
  const [productFilter, setProductFilter] = useState<ReportFilter>(emptyFilter);
  const [categoryFilter, setCategoryFilter] = useState<ReportFilter>(emptyFilter);
  const [dashHistFilter, setDashHistFilter] = useState<ReportFilter>(() => ({
    ...emptyFilter(),
    mode: 'month',
    month: defaultMonth,
    year: defaultYear,
  }));
  const [monthlyFilter, setMonthlyFilter] = useState({ fromMonth: defaultMonth, toMonth: defaultMonth });
  const [detailedFilter, setDetailedFilter] = useState<ReportFilter>(() => ({
    ...emptyFilter(),
    mode: 'month',
    month: defaultMonth,
  }));

  const [leadValueReport, setLeadValueReport] = useState<any>(null);
  const [quotationReport, setQuotationReport] = useState<any>(null);
  const [details, setDetails] = useState<any>(null);
  const [productDetails, setProductDetails] = useState<any>(null);
  const [prod, setProd] = useState<any[]>([]);
  const [categoryDetails, setCategoryDetails] = useState<any>(null);
  const [catRows, setCatRows] = useState<any[]>([]);
  const [dashHistory, setDashHistory] = useState<any>(null);
  const [emp, setEmp] = useState<any[]>([]);
  const [monthlyRows, setMonthlyRows] = useState<any[]>([]);
  const [detailedReport, setDetailedReport] = useState<any>(null);

  const [lvBusy, setLvBusy] = useState(false);
  const [quoteBusy, setQuoteBusy] = useState(false);
  const [sourceBusy, setSourceBusy] = useState(false);
  const [productBusy, setProductBusy] = useState(false);
  const [categoryBusy, setCategoryBusy] = useState(false);
  const [dashHistBusy, setDashHistBusy] = useState(false);
  const [pdfBusy, setPdfBusy] = useState(false);
  const [empBusy, setEmpBusy] = useState(false);
  const [monthlyBusy, setMonthlyBusy] = useState(false);
  const [detailedBusy, setDetailedBusy] = useState(false);

  const [lvErr, setLvErr] = useState('');
  const [quoteErr, setQuoteErr] = useState('');
  const [sourceErr, setSourceErr] = useState('');
  const [productErr, setProductErr] = useState('');
  const [categoryErr, setCategoryErr] = useState('');
  const [dashHistErr, setDashHistErr] = useState('');
  const [empErr, setEmpErr] = useState('');
  const [monthlyErr, setMonthlyErr] = useState('');
  const [detailedErr, setDetailedErr] = useState('');

  const apiErr = (e: any, fallback: string) => {
    const d = e?.response?.data?.detail;
    if (typeof d === 'string' && d.trim()) return d;
    if (Array.isArray(d) && d.length) {
      return d.map((x: any) => x?.msg || JSON.stringify(x)).join('; ');
    }
    if (e?.response?.status === 401) return 'Session expired — please log in again';
    if (e?.response?.status === 403) return 'Reports require an admin role';
    if (e?.message === 'Network Error') return 'Cannot reach the server. Is the backend running?';
    return fallback;
  };

  const toParams = (f: ReportFilter): Record<string, string> => {
    if (f.mode === 'month') return { mode: 'month', month: f.month || defaultMonth };
    if (f.mode === 'year') return { mode: 'year', year: f.year || defaultYear };
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
    if (f.mode === 'year' && !/^\d{4}$/.test(f.year || '')) {
      return 'Select a valid year.';
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

  const loadCategory = async (f: ReportFilter = categoryFilter) => {
    const v = validate(f);
    if (v) { setCategoryErr(v); return; }
    setCategoryBusy(true); setCategoryErr('');
    try {
      const params = toParams(f);
      const [detailsRes, barRes] = await Promise.all([
        api.get('/reports/category-details', { params }),
        api.get('/reports/category-wise', { params }),
      ]);
      setCategoryDetails(detailsRes.data);
      setCatRows(Array.isArray(barRes.data) ? barRes.data : []);
    } catch (e: any) {
      setCategoryErr(apiErr(e, 'Category report failed'));
    } finally { setCategoryBusy(false); }
  };

  const loadDashHistory = async (f: ReportFilter = dashHistFilter) => {
    const v = validate(f);
    if (v) { setDashHistErr(v); return; }
    setDashHistBusy(true); setDashHistErr('');
    try {
      const { data } = await api.get('/reports/dashboard-history', { params: toParams(f) });
      setDashHistory(data);
    } catch (e: any) {
      setDashHistErr(apiErr(e, 'Dashboard history report failed'));
    } finally { setDashHistBusy(false); }
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

  const loadDetailed = async (f: ReportFilter = detailedFilter) => {
    const problem = validate(f);
    if (problem) { setDetailedErr(problem); return; }
    setDetailedBusy(true); setDetailedErr('');
    try {
      const { data } = await api.get('/reports/detailed-leads', { params: toParams(f) });
      setDetailedReport(data);
    } catch (e: any) {
      setDetailedErr(apiErr(e, 'Detailed lead report failed'));
    } finally { setDetailedBusy(false); }
  };

  useEffect(() => {
    if (!activeReport) return;
    if (activeReport === 'lead_value') void loadLeadValue();
    if (activeReport === 'quotation') void loadQuotations();
    if (activeReport === 'source') void loadSource();
    if (activeReport === 'product') void loadProduct();
    if (activeReport === 'category') void loadCategory();
    if (activeReport === 'dashboard_history') void loadDashHistory();
    if (activeReport === 'employee') void loadEmployees();
    if (activeReport === 'monthly') void loadMonthly();
    if (activeReport === 'detailed') void loadDetailed();
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
    kind: 'source' | 'product' | 'category' | 'lead_value' | 'quotation' | 'monthly' | 'detailed' | 'dashboard_history',
    f: ReportFilter | { fromMonth: string; toMonth: string },
    setErr: (s: string) => void,
  ) => {
    setPdfBusy(true); setErr('');
    const names = {
      source: 'lead-source-report.pdf',
      product: 'product-wise-report.pdf',
      category: 'category-wise-report.pdf',
      lead_value: 'lead-value-report.pdf',
      quotation: 'quotation-report.pdf',
      monthly: 'monthly-lead-volume.pdf',
      detailed: 'detailed-lead-report.pdf',
      dashboard_history: 'dashboard-history-report.pdf',
    };
    try {
      const params = kind === 'monthly'
        ? { ...monthlyParams(f as { fromMonth: string; toMonth: string }), report_type: kind }
        : { ...toParams(f as ReportFilter), report_type: kind };
      if (kind === 'monthly') {
        const mf = f as { fromMonth: string; toMonth: string };
        if (mf.fromMonth && mf.toMonth && mf.fromMonth > mf.toMonth) {
          setErr('From month must be on or before To month.');
          setPdfBusy(false);
          return;
        }
      } else {
        const v = validate(f as ReportFilter);
        if (v) { setErr(v); setPdfBusy(false); return; }
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

  const filterYearOptions = useMemo(() => {
    const current = new Date().getFullYear();
    const years: string[] = [];
    for (let y = current; y >= 2020; y -= 1) years.push(String(y));
    return years;
  }, []);

  const filterBar = (
    f: ReportFilter,
    setF: (next: ReportFilter) => void,
    busy: boolean,
    onApply: () => void,
    onExcel: () => void,
    excelDisabled: boolean,
    onPdf?: () => void,
  ) => {
    const today = new Date().toISOString().slice(0, 10);
    return (
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
          <option value="month">Monthly (with year)</option>
          <option value="year">Year wise</option>
        </select>
      </div>
      {f.mode === 'month' ? (
        <div>
          <label className="text-xs font-medium text-graphite-600">Select Month</label>
          <input type="month" className="input mt-1" max={today.slice(0, 7)} value={f.month} onChange={(e) => setF({ ...f, month: e.target.value, year: (e.target.value || '').slice(0, 4) || f.year })} />
        </div>
      ) : f.mode === 'year' ? (
        <div>
          <label className="text-xs font-medium text-graphite-600">Select Year</label>
          <select
            className="input mt-1"
            value={f.year || defaultYear}
            onChange={(e) => setF({ ...f, year: e.target.value })}
          >
            {filterYearOptions.map((year) => (
              <option key={year} value={year}>{year}</option>
            ))}
          </select>
        </div>
      ) : f.mode === 'week' ? (
        <>
          <div>
            <label className="text-xs font-medium text-graphite-600">Week start date</label>
            <input
              type="date"
              className="input mt-1"
              max={today}
              value={f.week}
              onChange={(e) => {
                const start = e.target.value > today ? today : e.target.value;
                setF({ ...f, week: start });
              }}
            />
          </div>
          <div>
            <label className="text-xs font-medium text-graphite-600">Week end (auto +6 days)</label>
            <input
              type="date"
              className="input mt-1 bg-graphite-50"
              value={f.week ? addDaysYmd(f.week, 6) : ''}
              readOnly
              title="Automatically set to 7 days from the start date"
            />
          </div>
        </>
      ) : (
        <>
          <div>
            <label className="text-xs font-medium text-graphite-600">From Date</label>
            <input type="date" className="input mt-1" max={today} value={f.fromDate} onChange={(e) => setF({ ...f, fromDate: e.target.value > today ? today : e.target.value })} />
          </div>
          <div>
            <label className="text-xs font-medium text-graphite-600">To Date</label>
            <input
              type="date"
              className="input mt-1"
              max={today}
              value={f.toDate}
              onChange={(e) => {
                const next = e.target.value > today ? today : e.target.value;
                setF({ ...f, toDate: next });
              }}
            />
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
  };

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

      {activeReport === 'dashboard_history' && (() => {
        const t = dashHistory?.tiles || {};
        const mapRows = (rows: any[], nameKey: string) => (rows || []).map((row: any) => ({
          name: row[nameKey],
          total: row.total,
          lead_value: row.lead_value ?? 0,
          'In Followup': row.in_followup,
          Meeting: row.meeting,
          'Site Visit': row.site_visit,
          'Quotation sent': row.quote_sent,
          Converted: row.converted ?? 0,
          'Not Interested': row.not_interested,
        }));
        const mapTotals = (totals: any) => ({
          total: totals?.total ?? 0,
          lead_value: totals?.lead_value ?? 0,
          follow: totals?.in_followup ?? 0,
          meeting: totals?.meeting ?? 0,
          siteVisit: totals?.site_visit ?? 0,
          quote: totals?.quote_sent ?? 0,
          converted: totals?.converted ?? 0,
          notInt: totals?.not_interested ?? 0,
        });
        const srcRowsH = mapRows(dashHistory?.by_source?.rows, 'source');
        const prodRowsH = mapRows(dashHistory?.by_product?.rows, 'product');
        const catRowsH = mapRows(dashHistory?.by_category?.rows, 'category');
        const histCountTiles = [
          { label: 'Total Leads', value: t.total_leads ?? 0, bg: 'bg-[#1e3a5f]', text: 'text-white' },
          { label: 'In Followup', value: t.in_followup ?? 0, bg: PROGRESS_TILE_BG['In Followup'], text: PROGRESS_TILE_TEXT['In Followup'] },
          { label: 'Meeting', value: t.meeting ?? 0, bg: PROGRESS_TILE_BG.Meeting, text: PROGRESS_TILE_TEXT.Meeting },
          { label: 'Site Visit', value: t.site_visit ?? 0, bg: PROGRESS_TILE_BG['Site Visit'], text: PROGRESS_TILE_TEXT['Site Visit'] },
          { label: 'Quotation Sent', value: t.quote_sent ?? 0, bg: PROGRESS_TILE_BG['Quotation sent'], text: PROGRESS_TILE_TEXT['Quotation sent'] },
          { label: 'Converted', value: t.converted ?? 0, bg: PROGRESS_TILE_BG.Converted, text: PROGRESS_TILE_TEXT.Converted },
          { label: 'Not Interested', value: t.not_interested ?? 0, bg: PROGRESS_TILE_BG['Not Interested'], text: PROGRESS_TILE_TEXT['Not Interested'] },
          { label: 'No. of Cars', value: t.total_cars ?? 0, bg: 'bg-[#0369a1]', text: 'text-white' },
        ];
        const histValueTiles = [
          { label: 'Total Lead Value', value: inr(t.total_lead_value), bg: 'bg-[#3F6212]', text: 'text-white' },
          { label: 'Total Quotation Value', value: inr(t.total_quotation_value), bg: 'bg-[#b45309]', text: 'text-white' },
          { label: 'Total Converted Value', value: inr(t.converted_lead_value), bg: 'bg-[#166534]', text: 'text-white' },
        ];
        return (
          <div className="space-y-5">
            <div className="card overflow-hidden">
              <div className="bg-[#0f766e] text-white px-5 py-3 font-semibold tracking-wide">DASHBOARD HISTORY REPORT</div>
              <div className="p-5 space-y-4">
                {filterBar(
                  dashHistFilter, setDashHistFilter, dashHistBusy, () => loadDashHistory(dashHistFilter),
                  () => dl('/reports/dashboard-history/export', 'dashboard-history.xlsx', toParams(dashHistFilter), setDashHistErr),
                  !dashHistory,
                  () => void downloadPdf('dashboard_history', dashHistFilter, setDashHistErr),
                )}
                {dashHistErr && <div className="text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg px-3 py-2">{dashHistErr}</div>}
                {dashHistBusy && !dashHistory ? <Spinner /> : (
                  <>
                    <p className="text-xs text-graphite-500">
                      Progress tiles count every history event (each follow-up, site visit, etc.). Pending / Converted are lead counts.
                      {dashHistory?.effective_from || dashHistory?.effective_to
                        ? ` Period: ${dashHistory?.effective_from || 'All'} → ${dashHistory?.effective_to || 'All'}.`
                        : ''}
                    </p>
                    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 xl:grid-cols-8 gap-2">
                      {histCountTiles.map((tile) => (
                        <div key={tile.label} className={`${tile.bg} ${tile.text} rounded-lg px-2.5 py-2.5 shadow-sm text-center`}>
                          <div className="text-[11px] sm:text-xs uppercase tracking-wide opacity-95 font-semibold leading-tight">{tile.label}</div>
                          <div className="text-xl sm:text-2xl font-bold mt-1 tabular-nums">{tile.value}</div>
                        </div>
                      ))}
                    </div>
                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                      {histValueTiles.map((tile) => (
                        <div key={tile.label} className={`${tile.bg} ${tile.text} rounded-lg px-3 py-3 shadow-sm text-center`}>
                          <div className="text-xs uppercase tracking-wide opacity-95 font-semibold leading-tight">{tile.label}</div>
                          <div className="text-base sm:text-lg font-bold mt-1 tabular-nums leading-tight">{tile.value}</div>
                        </div>
                      ))}
                    </div>
                  </>
                )}
              </div>
            </div>
            {dashHistory && (
              <>
                <DashboardTableChartRow
                  title="Leads by Source"
                  labelHeader="Source"
                  rows={srcRowsH}
                  totals={mapTotals(dashHistory?.by_source?.totals)}
                  pieRows={srcRowsH.filter((r) => r.total > 0).map((r) => ({ name: r.name, value: r.total }))}
                  emptyTitle="No source data in this range"
                />
                <DashboardTableChartRow
                  title="Leads by Product"
                  labelHeader="Product"
                  rows={prodRowsH}
                  totals={mapTotals(dashHistory?.by_product?.totals)}
                  pieRows={prodRowsH.filter((r) => r.total > 0).map((r) => ({ name: r.name, value: r.total }))}
                  emptyTitle="No product data in this range"
                />
                <DashboardTableChartRow
                  title="Leads by Category"
                  labelHeader="Category"
                  rows={catRowsH}
                  totals={mapTotals(dashHistory?.by_category?.totals)}
                  pieRows={catRowsH.filter((r) => r.total > 0).map((r) => ({ name: r.name, value: r.total }))}
                  emptyTitle="No category data in this range"
                />
              </>
            )}
          </div>
        );
      })()}

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
              <table className="w-full min-w-[1280px] text-sm text-center table-fixed">
                <colgroup>
                  <col className="w-[3.5%]" />
                  <col className="w-[15%]" />
                  <col className="w-[8%]" />
                  <col className="w-[11%]" />
                  <col className="w-[11%]" />
                  <col className="w-[7%]" />
                  <col className="w-[9%]" />
                  <col className="w-[7%]" />
                  <col className="w-[9%]" />
                  <col className="w-[7.5%]" />
                  <col className="w-[12%]" />
                </colgroup>
                <thead>
                  <tr className="bg-amber-300 text-graphite-900">
                    <th className="th !bg-transparent !text-center underline">S.No</th>
                    <th className="th !bg-transparent !text-center !px-1">REF</th>
                    <th className="th !bg-transparent !text-center">Date</th>
                    <th className="th !bg-transparent !text-center">Enquiry No</th>
                    <th className="th !bg-transparent !text-center">Customer Name</th>
                    <th className="th !bg-transparent !text-center">State</th>
                    <th className="th !bg-transparent !text-center">Parking Type</th>
                    <th className="th !bg-transparent !text-center">No. of Units/Cars</th>
                    <th className="th !bg-transparent !text-center">Order Value (Excl GST)</th>
                    <th className="th !bg-transparent !text-center">GST</th>
                    <th className="th !bg-transparent !text-center !px-2">Grand Total</th>
                  </tr>
                </thead>
                <tbody>
                  {(quotationReport?.rows || []).map((r: any, i: number) => (
                    <tr key={`${r.ref || r.enquiry_number}-${i}`} className={i % 2 ? 'bg-amber-50/50' : 'bg-white'}>
                      <td className="td text-center">{r.sno ?? i + 1}</td>
                      <td className="td text-center font-mono text-xs whitespace-nowrap !px-1">{r.ref || '—'}</td>
                      <td className="td text-center whitespace-nowrap">{r.date || '—'}</td>
                      <td className="td text-center font-medium whitespace-nowrap px-1">{r.enquiry_number || '—'}</td>
                      <td className="td text-center">{r.customer_name || '—'}</td>
                      <td className="td text-center">{r.state || '—'}</td>
                      <td className="td text-center">{r.parking_type || '—'}</td>
                      <td className="td text-center">{r.units ?? '—'}</td>
                      <td className="td text-center tabular-nums font-medium">{inr(r.order_value_excl_gst)}</td>
                      <td className="td text-center tabular-nums">{inr(r.gst)}</td>
                      <td className="td text-center tabular-nums font-semibold !px-2 whitespace-nowrap">{inr(r.grand_total)}</td>
                    </tr>
                  ))}
                  {quotationReport?.totals && (quotationReport.rows || []).length > 0 && (
                    <tr className="bg-graphite-100 font-bold">
                      <td className="td text-center" colSpan={7}>TOTAL</td>
                      <td className="td text-center" />
                      <td className="td text-center tabular-nums">{inr(quotationReport.totals.order_value_excl_gst)}</td>
                      <td className="td text-center tabular-nums">{inr(quotationReport.totals.gst)}</td>
                      <td className="td text-center tabular-nums">{inr(quotationReport.totals.grand_total)}</td>
                    </tr>
                  )}
                </tbody>
              </table>
              {quotationReport && !(quotationReport.rows || []).length && (
                <EmptyState title="No saved quotations in this range" hint="Only Quotation sent leads with a saved quotation form (REF) appear here." />
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
              <table className="w-full table-fixed text-xs text-center">
                <thead>
                  <tr className="bg-[#1e3a5f] text-white">
                    <th className="th !text-white !bg-transparent !text-center">Lead Source</th>
                    <th className="th !text-white !bg-transparent !text-center">Total Leads</th>
                    <th className="th !text-white !bg-transparent !text-center">Total Lead Value</th>
                    <th className="th !text-white !bg-transparent !text-center">In Followup</th>
                    <th className="th !text-white !bg-transparent !text-center">Meeting</th>
                    <th className="th !text-white !bg-transparent !text-center">Site Visit</th>
                    <th className="th !text-white !bg-transparent !text-center">Quotation sent</th>
                    <th className="th !text-white !bg-transparent !text-center">Converted</th>
                    <th className="th !text-white !bg-transparent !text-center">Not Interested</th>
                  </tr>
                </thead>
                <tbody>
                  {(details?.rows || []).map((r: any, i: number) => (
                    <tr key={r.source} className={i % 2 ? 'bg-sky-50/70' : 'bg-white'}>
                      <td className="td font-medium text-center">{r.source}</td>
                      <td className="td font-bold text-center">{r.total}</td>
                      <td className="td text-center tabular-nums">{inr(r.lead_value)}</td>
                      <td className="td text-center">{r.in_followup}</td>
                      <td className="td text-center">{r.meeting}</td>
                      <td className="td text-center">{r.site_visit}</td>
                      <td className="td text-center">{r.quote_sent}</td>
                      <td className="td text-center">{r.converted ?? 0}</td>
                      <td className="td text-center">{r.not_interested}</td>
                    </tr>
                  ))}
                  {details?.totals && (
                    <tr className="bg-graphite-100 font-bold">
                      <td className="td text-center">TOTAL</td>
                      <td className="td text-center">{details.totals.total}</td>
                      <td className="td text-center tabular-nums">{inr(details.totals.lead_value)}</td>
                      <td className="td text-center">{details.totals.in_followup}</td>
                      <td className="td text-center">{details.totals.meeting}</td>
                      <td className="td text-center">{details.totals.site_visit}</td>
                      <td className="td text-center">{details.totals.quote_sent}</td>
                      <td className="td text-center">{details.totals.converted ?? 0}</td>
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
                      <Bar dataKey="in_followup" fill={PROGRESS_HEX['In Followup']} name="In Followup" radius={[4, 4, 0, 0]} />
                      <Bar dataKey="meeting" fill={PROGRESS_HEX.Meeting} name="Meeting" radius={[4, 4, 0, 0]} />
                      <Bar dataKey="site_visit" fill={PROGRESS_HEX['Site Visit']} name="Site Visit" radius={[4, 4, 0, 0]} />
                      <Bar dataKey="quote_sent" fill={PROGRESS_HEX['Quotation sent']} name="Quotation sent" radius={[4, 4, 0, 0]} />
                      <Bar dataKey="converted" fill={PROGRESS_HEX.Converted} name="Converted" radius={[4, 4, 0, 0]} />
                      <Bar dataKey="not_interested" fill={PROGRESS_HEX['Not Interested']} name="Not Interested" radius={[4, 4, 0, 0]} />
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
                <table className="w-full table-fixed text-xs text-center">
                  <thead><tr className="bg-[#0f766e] text-white">
                    {['Product', 'Total Leads', 'Total Lead Value', 'In Followup', 'Meeting', 'Site Visit', 'Quotation sent', 'Converted', 'Not Interested'].map((header) => <th key={header} className="th !text-white !bg-transparent !text-center">{header}</th>)}
                  </tr></thead>
                  <tbody>
                    {(productDetails?.rows || []).map((row: any, i: number) => (
                      <tr key={row.product} className={i % 2 ? 'bg-teal-50/70' : 'bg-white'}>
                        <td className="td font-medium text-center">{row.product}</td>
                        <td className="td font-bold text-center">{row.total}</td>
                        <td className="td text-center tabular-nums">{inr(row.lead_value)}</td>
                        <td className="td text-center">{row.in_followup}</td>
                        <td className="td text-center">{row.meeting}</td>
                        <td className="td text-center">{row.site_visit}</td>
                        <td className="td text-center">{row.quote_sent}</td>
                        <td className="td text-center">{row.converted ?? 0}</td>
                        <td className="td text-center">{row.not_interested}</td>
                      </tr>
                    ))}
                    {productDetails?.totals && (
                      <tr className="bg-graphite-100 font-bold">
                        <td className="td text-center">TOTAL</td>
                        <td className="td text-center">{productDetails.totals.total}</td>
                        <td className="td text-center tabular-nums">{inr(productDetails.totals.lead_value)}</td>
                        <td className="td text-center">{productDetails.totals.in_followup}</td>
                        <td className="td text-center">{productDetails.totals.meeting}</td>
                        <td className="td text-center">{productDetails.totals.site_visit}</td>
                        <td className="td text-center">{productDetails.totals.quote_sent}</td>
                        <td className="td text-center">{productDetails.totals.converted ?? 0}</td>
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

      {activeReport === 'category' && (
        <div className="space-y-4">
          <div className="card overflow-hidden">
            <div className="bg-[#0e7490] text-white px-5 py-3 font-semibold tracking-wide">CATEGORY WISE REPORT</div>
            <div className="p-5 space-y-4">
              {filterBar(
                categoryFilter, setCategoryFilter, categoryBusy, () => loadCategory(categoryFilter),
                () => dl('/reports/category-details/export', 'category-wise-details.xlsx', toParams(categoryFilter), setCategoryErr),
                !categoryDetails,
                () => downloadPdf('category', categoryFilter, setCategoryErr),
              )}
              {categoryErr && <div className="text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg px-3 py-2">{categoryErr}</div>}
              <div className="overflow-x-auto">
                <table className="w-full table-fixed text-xs text-center">
                  <thead><tr className="bg-[#0e7490] text-white">
                    {['Category', 'Total Leads', 'Total Lead Value', 'In Followup', 'Meeting', 'Site Visit', 'Quotation sent', 'Converted', 'Not Interested'].map((header) => <th key={header} className="th !text-white !bg-transparent !text-center">{header}</th>)}
                  </tr></thead>
                  <tbody>
                    {(categoryDetails?.rows || []).map((row: any, i: number) => (
                      <tr key={row.category} className={i % 2 ? 'bg-cyan-50/70' : 'bg-white'}>
                        <td className="td font-medium text-center">{row.category}</td>
                        <td className="td font-bold text-center">{row.total}</td>
                        <td className="td text-center tabular-nums">{inr(row.lead_value)}</td>
                        <td className="td text-center">{row.in_followup}</td>
                        <td className="td text-center">{row.meeting}</td>
                        <td className="td text-center">{row.site_visit}</td>
                        <td className="td text-center">{row.quote_sent}</td>
                        <td className="td text-center">{row.converted ?? 0}</td>
                        <td className="td text-center">{row.not_interested}</td>
                      </tr>
                    ))}
                    {categoryDetails?.totals && (
                      <tr className="bg-graphite-100 font-bold">
                        <td className="td text-center">TOTAL</td>
                        <td className="td text-center">{categoryDetails.totals.total}</td>
                        <td className="td text-center tabular-nums">{inr(categoryDetails.totals.lead_value)}</td>
                        <td className="td text-center">{categoryDetails.totals.in_followup}</td>
                        <td className="td text-center">{categoryDetails.totals.meeting}</td>
                        <td className="td text-center">{categoryDetails.totals.site_visit}</td>
                        <td className="td text-center">{categoryDetails.totals.quote_sent}</td>
                        <td className="td text-center">{categoryDetails.totals.converted ?? 0}</td>
                        <td className="td text-center">{categoryDetails.totals.not_interested}</td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
          <BarCard
            title="Category-wise leads"
            data={catRows}
            x="category"
            y="leads"
            onDownload={() => dl('/reports/category-wise/export', 'category-wise-report.xlsx', toParams(categoryFilter), setCategoryErr)}
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
                      <Bar dataKey="in_followup" fill={PROGRESS_HEX['In Followup']} name="In Followup" radius={[4, 4, 0, 0]} />
                      <Bar dataKey="meeting" fill={PROGRESS_HEX.Meeting} name="Meeting" radius={[4, 4, 0, 0]} />
                      <Bar dataKey="site_visit" fill={PROGRESS_HEX['Site Visit']} name="Site Visit" radius={[4, 4, 0, 0]} />
                      <Bar dataKey="quotation_sent" fill={PROGRESS_HEX['Quotation sent']} name="Quotation sent" radius={[4, 4, 0, 0]} />
                      <Bar dataKey="not_interested" fill={PROGRESS_HEX['Not Interested']} name="Not Interested" radius={[4, 4, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full table-fixed text-xs text-center">
                    <thead>
                      <tr className="bg-[#4338ca] text-white">
                        {['Month', 'Total Leads', 'Total Lead Value', 'In Followup', 'Meeting', 'Site Visit', 'Quotation sent', 'Not Interested', 'Sources', 'Products'].map((h) => (
                          <th key={h} className="th !text-white !bg-transparent !text-center">{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {monthlyRows.map((row: any, i: number) => (
                        <tr key={row.month_key || row.month} className={i % 2 ? 'bg-indigo-50/60' : 'bg-white'}>
                          <td className="td font-medium text-center">{row.month}</td>
                          <td className="td font-bold text-center">{row.leads}</td>
                          <td className="td text-center whitespace-nowrap">{inr(row.lead_value)}</td>
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

      {activeReport === 'detailed' && (
        <div className="card overflow-hidden">
          <div className="bg-[#0f172a] text-white px-5 py-3 font-semibold tracking-wide">DETAILED LEAD REPORT</div>
          <div className="p-5 space-y-4">
            {filterBar(
              detailedFilter, setDetailedFilter, detailedBusy, () => loadDetailed(detailedFilter),
              () => {
                const p = toParams(detailedFilter);
                const name = detailedFilter.mode === 'month'
                  ? `detailed-leads-${detailedFilter.month}.xlsx`
                  : detailedFilter.mode === 'week'
                    ? `detailed-leads-week-${detailedFilter.week}.xlsx`
                    : `detailed-leads-${detailedFilter.fromDate || 'all'}_to_${detailedFilter.toDate || 'all'}.xlsx`;
                return dl('/reports/detailed-leads/export', name, p, setDetailedErr);
              },
              !detailedReport,
              () => void downloadPdf('detailed', detailedFilter, setDetailedErr),
            )}
            {detailedErr && <div className="text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg px-3 py-2">{detailedErr}</div>}
            {detailedReport && (
              <div className="text-sm text-graphite-700 flex flex-wrap gap-6">
                <span><b>From:</b> {detailedReport.effective_from || detailedReport.from_month || 'All'}</span>
                <span><b>To:</b> {detailedReport.effective_to || detailedReport.to_month || 'All'}</span>
                <span><b>Mode:</b> {detailedReport.mode || detailedFilter.mode}</span>
                <span><b>Leads:</b> {detailedReport.count ?? (detailedReport.rows || []).length}</span>
              </div>
            )}
            {detailedBusy && !detailedReport ? <Spinner /> : !(detailedReport?.rows || []).length ? (
              <EmptyState title="No leads in this range" hint="Pick Weekly, Monthly, or a custom date range and Apply." />
            ) : (
              <div className="overflow-x-auto">
                <table className="text-sm border-collapse table-auto">
                  <thead>
                    <tr className="bg-[#0f172a] text-white">
                      {[
                        { label: 'Enquiry', cls: '!text-center' },
                        { label: 'Date', cls: '!text-center' },
                        { label: 'Customer', cls: '!text-left' },
                        { label: 'Company', cls: '!text-left' },
                        { label: 'City', cls: '!text-center' },
                        { label: 'Contact', cls: '!text-center' },
                        { label: 'Cars', cls: '!text-center' },
                        { label: 'Product', cls: '!text-left' },
                        { label: 'Source', cls: '!text-center' },
                        { label: 'Current status', cls: '!text-center' },
                        { label: 'Progress', cls: '!text-left' },
                        { label: 'Category', cls: '!text-left' },
                        { label: 'Remarks', cls: '!text-left' },
                        { label: 'Employee', cls: '!text-center' },
                        { label: 'Lead Value', cls: '!text-right' },
                        { label: 'Quotation', cls: '!text-right' },
                      ].map((h) => (
                        <th key={h.label} className={`th !text-white !bg-transparent !px-3 !py-2.5 whitespace-nowrap align-bottom ${h.cls}`}>{h.label}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {(detailedReport.rows || []).map((row: any, i: number) => {
                      const historyLines = (value: any) => {
                        const text = String(value ?? '').trim();
                        if (!text || text === '—') return [] as string[];
                        return text.split('\n').map((line) => line.trim()).filter(Boolean);
                      };
                      const progressLines = historyLines(row.progress);
                      const categoryLines = historyLines(row.category);
                      const remarkLines = historyLines(row.remarks);
                      const steps = Math.max(progressLines.length, categoryLines.length, remarkLines.length, 1);
                      const step = (lines: string[], index: number) => (
                        <div key={index} className="h-6 leading-6 whitespace-nowrap">
                          {lines[index] || (index === 0 && !lines.length ? '—' : '\u00a0')}
                        </div>
                      );
                      const cell = 'td !px-3 !py-2 align-top whitespace-nowrap';
                      return (
                        <tr key={`${row.enquiry_number}-${i}`} className={i % 2 ? 'bg-slate-50' : 'bg-white'}>
                          <td className={`${cell} !text-center font-medium`}>{row.enquiry_number}</td>
                          <td className={`${cell} !text-center`}>{row.enquiry_date}</td>
                          <td className={`${cell} !text-left`}>{row.customer_name}</td>
                          <td className={`${cell} !text-left`}>{row.company_name}</td>
                          <td className={`${cell} !text-center`}>{row.city}</td>
                          <td className={`${cell} !text-center`}>{row.contact_number}</td>
                          <td className={`${cell} !text-center`}>{row.cars}</td>
                          <td className={`${cell} !text-left`}>{row.product}</td>
                          <td className={`${cell} !text-center`}>{row.source}</td>
                          <td className={`${cell} !text-center`}>{row.status}</td>
                          <td className={`${cell} !text-left`}>{Array.from({ length: steps }, (_, index) => step(progressLines, index))}</td>
                          <td className={`${cell} !text-left`}>{Array.from({ length: steps }, (_, index) => step(categoryLines, index))}</td>
                          <td className={`${cell} !text-left`}>{Array.from({ length: steps }, (_, index) => step(remarkLines, index))}</td>
                          <td className={`${cell} !text-center capitalize`}>{row.employee}</td>
                          <td className={`${cell} !text-right !tabular-nums font-semibold`}>{inr(row.lead_value)}</td>
                          <td className={`${cell} !text-right !tabular-nums`}>{inr(row.quotation_value)}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
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
  const reviewOptions = ['A+ (Immediate)', 'A (3-6 months)', 'B (6-9 months)', 'C (Planning Stage)'];
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
    value: employeeLeads.filter((l) => {
      const v = (l.customer_review || '').trim();
      if (label === 'B (6-9 months)') return v === 'B (6-9 months)' || v === 'B (1 year)';
      if (label === 'C (Planning Stage)') return v === 'C (Planning Stage)' || v === 'C (plan stage)' || v === 'Planning Stage';
      return v === label;
    }).length,
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
                  { label: 'Overdue', value: empOverdue },
                  { label: 'Responded', value: empContactDone },
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
                  {empWorkActionCounts.map((s) => {
                    const bg = PROGRESS_TILE_BG[s.label] || (s.label === 'Assigned' ? 'bg-[#0e7490]' : 'bg-[#1e3a5f]');
                    const text = PROGRESS_TILE_TEXT[s.label] || 'text-white';
                    return (
                      <div key={s.label} className={`${bg} ${text} rounded-lg px-3 py-3 text-center shadow-sm`}>
                        <div className="text-xl font-bold tabular-nums">{s.value}</div>
                        <div className="text-[11px] uppercase tracking-wide opacity-90 font-semibold mt-1">{s.label}</div>
                      </div>
                    );
                  })}
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
      <PageHeader title="Notifications" subtitle="Overdue, assignments, reassignment requests and follow-up reminders." />
      {loading ? <div className="card"><Spinner /></div>
      : error ? <div className="card"><EmptyState title="Could not load notifications" hint={error} /></div>
      : items.length === 0 ? <div className="card"><EmptyState title="All caught up" hint="No notifications." /></div> : items.map((n) => (
        <div key={n.id} className={`card p-4 flex gap-3 ${n.is_read ? 'opacity-80' : ''}`}>
          <div className="w-9 h-9 rounded-lg bg-red-100 text-red-600 flex items-center justify-center shrink-0">⚠</div>
          <div>
            <div className="font-semibold text-sm">{String(n.title || '').replace(/\bSLAs?\b/gi, 'Overdue')}</div>
            <div className="text-sm text-graphite-600 mt-0.5">{String(n.body || '').replace(/\bSLAs?\b/gi, 'overdue')}</div>
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
