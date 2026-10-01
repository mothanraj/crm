import { useEffect, useMemo, useState } from 'react';
import {
  Bar, BarChart, CartesianGrid, Cell, Line, LineChart,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';
import { api } from '../services/api';
import { Card, EmptyState, PageHeader, Spinner } from '../components/ui';

const METRIC_IDS = new Set(['leads', 'lead_value', 'quotations', 'quotation_value']);

const FILTER_OPTIONS = [
  { id: 'leads', label: 'No. of Leads', kind: 'metric' as const },
  { id: 'lead_value', label: 'Lead Value', kind: 'metric' as const },
  { id: 'quotations', label: 'No. of Quotation', kind: 'metric' as const },
  { id: 'quotation_value', label: 'Quotation Value', kind: 'metric' as const },
  {
    id: 'category',
    label: 'Category',
    kind: 'dimension' as const,
    values: ['A+ (Immediate)', 'A (3-6 months)', 'B (1 year)', 'C (Planning Stage)'],
  },
  {
    id: 'product',
    label: 'Product',
    kind: 'dimension' as const,
    values: [
      'Two Post Stack Parking',
      'Four Post Stack Parking',
      'Pit Stack Parking',
      'Puzzle Parking',
      'Pit Puzzle Parking',
      'Tower Parking',
      'Shuttle Parking',
      'Car Elevator',
      'ASRS Parking',
    ],
  },
  {
    id: 'progress',
    label: 'Progress',
    kind: 'dimension' as const,
    values: ['In Followup', 'Meeting', 'Site Visit', 'Not Interested', 'Converted'],
  },
  {
    id: 'source',
    label: 'Source',
    kind: 'dimension' as const,
    values: [
      'SEO',
      'Facebook/Instagram',
      'Google Ads',
      'India Mart',
      'Direct Call',
      'Referral',
      'WhatsApp',
      'Email Campaign',
      'Email Enquiry',
      'Others',
      'Expo/Stall',
    ],
  },
] as const;

const COMPARE_MODES = [
  { id: 'year', label: 'Year wise' },
  { id: 'month', label: 'Month wise' },
  { id: 'date', label: 'Date wise' },
  { id: 'period', label: 'From date–to date vs From date–to date' },
] as const;

const MONTHS = [
  { id: 1, label: 'Jan' }, { id: 2, label: 'Feb' }, { id: 3, label: 'Mar' },
  { id: 4, label: 'Apr' }, { id: 5, label: 'May' }, { id: 6, label: 'Jun' },
  { id: 7, label: 'Jul' }, { id: 8, label: 'Aug' }, { id: 9, label: 'Sep' },
  { id: 10, label: 'Oct' }, { id: 11, label: 'Nov' }, { id: 12, label: 'Dec' },
];

const CHART_COLORS = ['#1971C2', '#65A30D', '#E8890C', '#7C3AED', '#0e7490', '#DC2626'];

function inr(n: number | null | undefined) {
  if (n == null || Number.isNaN(Number(n))) return '—';
  return `₹${Math.round(Number(n)).toLocaleString('en-IN')}`;
}

function num(n: number | null | undefined) {
  if (n == null || Number.isNaN(Number(n))) return '—';
  return Number(n).toLocaleString('en-IN');
}

function todayIso() {
  const d = new Date();
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

function daysAgoIso(days: number) {
  const d = new Date();
  d.setDate(d.getDate() - days);
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

function chip(active: boolean) {
  return `px-3 py-1.5 rounded-lg text-sm font-medium transition ${
    active ? 'bg-graphite-800 text-white' : 'bg-graphite-100 text-graphite-700 hover:bg-graphite-200'
  }`;
}

async function downloadBlob(path: string, filename: string, params: Record<string, string>) {
  const res = await api.get(path, { responseType: 'blob', params, timeout: 120000 });
  const ctype = String(res.headers?.['content-type'] ?? '');
  if (ctype.includes('application/json')) {
    const text = await (res.data as Blob).text();
    let detail = 'Download failed';
    try { detail = JSON.parse(text)?.detail || detail; } catch { /* keep */ }
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

function MiniCharts({
  title,
  series,
  money,
  metricLabel,
  color = '#1971C2',
}: {
  title: string;
  series: Array<{ label: string; value: number }>;
  money: boolean;
  metricLabel: string;
  color?: string;
}) {
  const fmt = (v: number) => (money ? inr(v) : num(v));
  return (
    <div className="rounded-xl border border-graphite-200 p-3 space-y-3">
      <div>
        <p className="text-sm font-semibold text-graphite-900">{title}</p>
      </div>
      {!series.length ? (
        <EmptyState title="No data" hint="Nothing in this date range." />
      ) : (
        <div className="grid grid-cols-1 gap-3">
          <div className="h-56">
            <ResponsiveContainer>
              <LineChart data={series}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                <XAxis dataKey="label" tick={{ fontSize: 10 }} minTickGap={16} />
                <YAxis tick={{ fontSize: 10 }} allowDecimals={money} width={48} />
                <Tooltip formatter={(value: any) => [fmt(Number(value)), metricLabel]} />
                <Line type="monotone" dataKey="value" stroke={color} strokeWidth={2.5} dot={{ r: 2 }} />
              </LineChart>
            </ResponsiveContainer>
          </div>
          <div className="h-48">
            <ResponsiveContainer>
              <BarChart data={series}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                <XAxis dataKey="label" tick={{ fontSize: 10 }} minTickGap={16} />
                <YAxis tick={{ fontSize: 10 }} allowDecimals={money} width={48} />
                <Tooltip formatter={(value: any) => [fmt(Number(value)), metricLabel]} />
                <Bar dataKey="value" fill={color} radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}
    </div>
  );
}

export function Analytics() {
  const currentYear = new Date().getFullYear();
  const yearChoices = useMemo(
    () => Array.from({ length: 12 }, (_, i) => currentYear - i),
    [currentYear],
  );

  const [primary, setPrimary] = useState('leads');
  const [dimValue, setDimValue] = useState('');
  const [mode, setMode] = useState('year');

  const [years, setYears] = useState<number[]>([currentYear, currentYear - 1]);
  const [monthYear, setMonthYear] = useState(currentYear);
  const [months, setMonths] = useState<number[]>([1, 2, 3]);
  const [fromDate, setFromDate] = useState(daysAgoIso(29));
  const [toDate, setToDate] = useState(todayIso());
  const [aFrom, setAFrom] = useState(daysAgoIso(29));
  const [aTo, setATo] = useState(todayIso());
  const [bFrom, setBFrom] = useState(daysAgoIso(59));
  const [bTo, setBTo] = useState(daysAgoIso(30));

  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [pdfBusy, setPdfBusy] = useState(false);

  const selected = FILTER_OPTIONS.find((o) => o.id === primary);
  const isDimension = selected?.kind === 'dimension';
  const metric = METRIC_IDS.has(primary) ? primary : 'leads';
  const metricLabel = FILTER_OPTIONS.find((o) => o.id === metric)?.label || 'No. of Leads';
  const ready = !isDimension || Boolean(dimValue);

  useEffect(() => {
    setDimValue('');
  }, [primary]);

  const compareParams = useMemo(() => {
    if (!ready) return null;
    const params: Record<string, string> = { metric, mode };
    if (isDimension && dimValue) {
      params.type = primary;
      params.value = dimValue;
    }
    if (mode === 'year') {
      if (!years.length) return null;
      params.years = years.join(',');
    } else if (mode === 'month') {
      if (!months.length) return null;
      params.year = String(monthYear);
      params.months = months.join(',');
    } else if (mode === 'date') {
      if (!fromDate || !toDate || fromDate > toDate) return null;
      params.from_date = fromDate;
      params.to_date = toDate;
    } else if (mode === 'period') {
      if (!aFrom || !aTo || !bFrom || !bTo || aFrom > aTo || bFrom > bTo) return null;
      params.a_from = aFrom;
      params.a_to = aTo;
      params.b_from = bFrom;
      params.b_to = bTo;
    }
    return params;
  }, [ready, metric, mode, isDimension, primary, dimValue, years, monthYear, months, fromDate, toDate, aFrom, aTo, bFrom, bTo]);

  useEffect(() => {
    if (!compareParams) {
      setData(null);
      setLoading(false);
      return;
    }
    const ctrl = new AbortController();
    setLoading(true);
    setError('');
    api.get('/analytics/compare', { params: compareParams, signal: ctrl.signal, timeout: 60000 })
      .then((res) => setData(res.data))
      .catch((err) => {
        if (err?.code === 'ERR_CANCELED' || err?.name === 'CanceledError') return;
        setData(null);
        setError(err?.response?.data?.detail || 'Could not load comparison');
      })
      .finally(() => { if (!ctrl.signal.aborted) setLoading(false); });
    return () => ctrl.abort();
  }, [compareParams]);

  function toggleYear(y: number) {
    setYears((prev) => (prev.includes(y) ? prev.filter((x) => x !== y) : [...prev, y].sort((a, b) => a - b)));
  }

  function toggleMonth(m: number) {
    setMonths((prev) => (prev.includes(m) ? prev.filter((x) => x !== m) : [...prev, m].sort((a, b) => a - b)));
  }

  async function onPdf() {
    if (!compareParams) return;
    setPdfBusy(true);
    setError('');
    try {
      const label = dimValue || primary;
      const safe = label.replace(/[^a-zA-Z0-9_-]+/g, '-').slice(0, 40);
      await downloadBlob('/analytics/compare/pdf', `analytics-${safe}-${mode}.pdf`, compareParams);
    } catch (err: any) {
      setError(err?.message || 'PDF download failed');
    } finally {
      setPdfBusy(false);
    }
  }

  const money = Boolean(data?.money);
  const fmt = (v: number) => (money ? inr(v) : num(v));
  const periodMode = mode === 'period' && data?.mode === 'period';
  const series = data?.series || [];
  const scopeLabel = data?.filter_value
    ? `${data.dimension_label}: ${data.filter_value}`
    : (selected?.label || 'All leads');

  return (
    <div className="space-y-4">
      <PageHeader
        title="Analytics"
        subtitle="One filter for metric or dimension, then choose how to compare."
        actions={(
          <button type="button" className="btn-secondary" disabled={!data || pdfBusy} onClick={onPdf}>
            {pdfBusy ? 'Creating PDF…' : 'Download PDF'}
          </button>
        )}
      />

      <Card>
        <div className="space-y-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-graphite-500 mb-2">Filter</p>
            <div className="flex flex-wrap items-end gap-2">
              <label className="text-sm min-w-[16rem]">
                <span className="text-graphite-500 text-xs">Choose</span>
                <select className="input mt-1" value={primary} onChange={(e) => setPrimary(e.target.value)}>
                  {FILTER_OPTIONS.map((o) => (
                    <option key={o.id} value={o.id}>{o.label}</option>
                  ))}
                </select>
              </label>
              {isDimension && selected && 'values' in selected && (
                <label className="text-sm min-w-[14rem]">
                  <span className="text-graphite-500 text-xs">{selected.label} value</span>
                  <select className="input mt-1" value={dimValue} onChange={(e) => setDimValue(e.target.value)}>
                    <option value="">{`Select ${selected.label.toLowerCase()}`}</option>
                    {selected.values.map((v) => (
                      <option key={v} value={v}>{v}</option>
                    ))}
                  </select>
                </label>
              )}
            </div>
          </div>

          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-graphite-500 mb-2">Compare</p>
            <select className="input max-w-xl" value={mode} onChange={(e) => setMode(e.target.value)}>
              {COMPARE_MODES.map((m) => <option key={m.id} value={m.id}>{m.label}</option>)}
            </select>
          </div>

          {mode === 'year' && (
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-graphite-500 mb-2">Years (multiple)</p>
              <div className="flex flex-wrap gap-1.5">
                {yearChoices.map((y) => (
                  <button key={y} type="button" className={chip(years.includes(y))} onClick={() => toggleYear(y)}>
                    {y}
                  </button>
                ))}
              </div>
            </div>
          )}

          {mode === 'month' && (
            <div className="flex flex-wrap items-start gap-4">
              <div>
                <p className="text-xs font-semibold uppercase tracking-wide text-graphite-500 mb-2">Year (one only)</p>
                <select className="input" value={monthYear} onChange={(e) => setMonthYear(Number(e.target.value))}>
                  {yearChoices.map((y) => <option key={y} value={y}>{y}</option>)}
                </select>
              </div>
              <div>
                <p className="text-xs font-semibold uppercase tracking-wide text-graphite-500 mb-2">Months (multiple)</p>
                <div className="flex flex-wrap gap-1.5">
                  {MONTHS.map((m) => (
                    <button key={m.id} type="button" className={chip(months.includes(m.id))} onClick={() => toggleMonth(m.id)}>
                      {m.label}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          )}

          {mode === 'date' && (
            <div className="flex flex-wrap gap-3">
              <label className="text-sm">From
                <input className="input mt-1" type="date" value={fromDate} onChange={(e) => setFromDate(e.target.value)} />
              </label>
              <label className="text-sm">To
                <input className="input mt-1" type="date" value={toDate} onChange={(e) => setToDate(e.target.value)} />
              </label>
            </div>
          )}

          {mode === 'period' && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <div className="rounded-xl border border-graphite-200 p-3">
                <p className="text-xs font-semibold uppercase tracking-wide text-graphite-500 mb-2">Period A</p>
                <div className="grid grid-cols-2 gap-2">
                  <label className="text-sm">From
                    <input className="input mt-1" type="date" value={aFrom} onChange={(e) => setAFrom(e.target.value)} />
                  </label>
                  <label className="text-sm">To
                    <input className="input mt-1" type="date" value={aTo} onChange={(e) => setATo(e.target.value)} />
                  </label>
                </div>
              </div>
              <div className="rounded-xl border border-graphite-200 p-3">
                <p className="text-xs font-semibold uppercase tracking-wide text-graphite-500 mb-2">Period B</p>
                <div className="grid grid-cols-2 gap-2">
                  <label className="text-sm">From
                    <input className="input mt-1" type="date" value={bFrom} onChange={(e) => setBFrom(e.target.value)} />
                  </label>
                  <label className="text-sm">To
                    <input className="input mt-1" type="date" value={bTo} onChange={(e) => setBTo(e.target.value)} />
                  </label>
                </div>
              </div>
            </div>
          )}
        </div>
      </Card>

      {error && <div className="bg-red-50 border border-red-200 text-red-700 text-sm rounded-xl px-4 py-3">{String(error)}</div>}

      {!ready ? (
        <Card>
          <EmptyState
            title={`Select a ${selected?.label?.toLowerCase()} value`}
            hint="The second menu appears next to the filter when Category, Product, Progress, or Source is chosen."
          />
        </Card>
      ) : !compareParams ? (
        <Card>
          <EmptyState title="Finish compare options" hint="Select years, months, or date ranges for the chosen compare mode." />
        </Card>
      ) : loading && !data ? (
        <Spinner />
      ) : data ? (
        <>
          <Card title={`${metricLabel} · ${scopeLabel}`}>
            <p className="text-xs text-graphite-500 mb-3">
              {COMPARE_MODES.find((m) => m.id === mode)?.label}
              {mode === 'year' ? ` · ${years.join(', ')}` : ''}
              {mode === 'month' ? ` · ${monthYear} · ${months.map((m) => MONTHS[m - 1].label).join(', ')}` : ''}
              {mode === 'date' ? ` · ${fromDate} to ${toDate}` : ''}
              {periodMode && data.change != null ? ` · Change ${data.change > 0 ? '+' : ''}${data.change}%` : ''}
            </p>

            {periodMode ? (
              <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
                <MiniCharts
                  title={`Period A · ${data.period_a?.from} – ${data.period_a?.to} · Total ${fmt(data.period_a?.total)}`}
                  series={data.period_a?.series || []}
                  money={money}
                  metricLabel={metricLabel}
                  color="#1971C2"
                />
                <MiniCharts
                  title={`Period B · ${data.period_b?.from} – ${data.period_b?.to} · Total ${fmt(data.period_b?.total)}`}
                  series={data.period_b?.series || []}
                  money={money}
                  metricLabel={metricLabel}
                  color="#65A30D"
                />
              </div>
            ) : !series.length ? (
              <EmptyState title="No data for this selection" hint="Try other years, months, or dates." />
            ) : (
              <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
                <div className="h-80">
                  <ResponsiveContainer>
                    <LineChart data={series}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                      <XAxis dataKey="label" tick={{ fontSize: 11 }} minTickGap={20} />
                      <YAxis tick={{ fontSize: 11 }} allowDecimals={money} width={56} />
                      <Tooltip formatter={(value: any) => [fmt(Number(value)), metricLabel]} />
                      <Line type="monotone" dataKey="value" stroke="#1971C2" strokeWidth={2.5} dot={{ r: 3 }} />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
                <div className="h-80">
                  <ResponsiveContainer>
                    <BarChart data={series}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                      <XAxis dataKey="label" tick={{ fontSize: 11 }} minTickGap={20} />
                      <YAxis tick={{ fontSize: 11 }} allowDecimals={money} width={56} />
                      <Tooltip formatter={(value: any) => [fmt(Number(value)), metricLabel]} />
                      <Bar dataKey="value" radius={[4, 4, 0, 0]}>
                        {series.map((_: any, index: number) => (
                          <Cell key={index} fill={CHART_COLORS[index % CHART_COLORS.length]} />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </div>
            )}
          </Card>

          <Card title="Comparison data">
            {periodMode ? (
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                <div className="rounded-xl border border-graphite-200 px-3 py-3">
                  <div className="text-[11px] uppercase tracking-wide text-graphite-500">Period A</div>
                  <div className="text-lg font-semibold tabular-nums mt-1">{fmt(data.period_a?.total)}</div>
                  <div className="text-xs text-graphite-500 mt-1">{data.period_a?.from} – {data.period_a?.to}</div>
                </div>
                <div className="rounded-xl border border-graphite-200 px-3 py-3">
                  <div className="text-[11px] uppercase tracking-wide text-graphite-500">Period B</div>
                  <div className="text-lg font-semibold tabular-nums mt-1">{fmt(data.period_b?.total)}</div>
                  <div className="text-xs text-graphite-500 mt-1">{data.period_b?.from} – {data.period_b?.to}</div>
                </div>
                <div className="rounded-xl border border-graphite-200 px-3 py-3">
                  <div className="text-[11px] uppercase tracking-wide text-graphite-500">Change (A vs B)</div>
                  <div className="text-lg font-semibold tabular-nums mt-1">
                    {data.change == null ? '—' : `${data.change > 0 ? '+' : ''}${data.change}%`}
                  </div>
                </div>
              </div>
            ) : (
              <div className="overflow-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left text-graphite-500 border-b border-graphite-200">
                      <th className="py-2 pr-3 font-medium">{data.x_title || 'Label'}</th>
                      <th className="py-2 font-medium text-right">{metricLabel}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(data.rows || series).map((row: any) => (
                      <tr key={row.key} className="border-b border-graphite-100">
                        <td className="py-2 pr-3 text-graphite-800">{row.label}</td>
                        <td className="py-2 text-right tabular-nums font-medium">{fmt(row.value)}</td>
                      </tr>
                    ))}
                    <tr>
                      <td className="py-2 pr-3 font-semibold">Total</td>
                      <td className="py-2 text-right tabular-nums font-semibold">{fmt(data.total)}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        </>
      ) : null}
    </div>
  );
}
