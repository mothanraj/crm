import { Fragment, useEffect, useMemo, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { api } from '../services/api';
import { subscribeLeadUpdates } from '../services/live';
import { Card, EmptyState, PageHeader, Spinner } from '../components/ui';

const COUNT_COLOR = '#1971C2';
const VALUE_COLOR = '#65A30D';
const COUNT_SHADES = ['#1971C2', '#0e7490', '#7c3aed', '#0369a1', '#1d4ed8', '#0891b2'];
const VALUE_SHADES = ['#65A30D', '#3F6212', '#E8890C', '#15803d', '#84cc16', '#a16207'];
const COMPARE = [
  ['lead', 'Lead'],
  ['quotation', 'Quotation'],
] as const;
const PERIODS: [string, string][] = [
  ['last_24_previous', 'Compare last 24 hours to previous period'],
  ['last_24_wow', 'Compare last 24 hours week over week'],
  ['last_7_previous', 'Compare last 7 days to previous period'],
  ['last_7_yoy', 'Compare last 7 days year over year'],
  ['last_28_previous', 'Compare last 28 days to previous period'],
  ['last_28_yoy', 'Compare last 28 days year over year'],
  ['last_3m_previous', 'Compare last 3 months to previous period'],
  ['last_3m_yoy', 'Compare last 3 months year over year'],
  ['last_6m_previous', 'Compare last 6 months to previous period'],
  ['custom', 'Custom'],
];
const PROGRESS_OPTIONS = [
  'Assigned',
  'New Lead',
  'Site Visit',
  'Meeting',
  'In Followup',
  'Converted',
  'Not Interested',
  'Quotation sent',
];
const FILTER_KEYS = ['employee', 'source', 'product', 'category', 'progress', 'city', 'cars', 'customer', 'enquiry'];
const CUSTOM_DEFAULT = {
  current_from: '2026-06-24',
  current_to: '2026-09-23',
  previous_from: '2026-01-24',
  previous_to: '2026-06-23',
};

function inr(n: number | null | undefined) {
  if (n == null || Number.isNaN(Number(n))) return '—';
  return `₹${Math.round(Number(n)).toLocaleString('en-IN')}`;
}
function num(n: number | null | undefined) {
  if (n == null || Number.isNaN(Number(n))) return '—';
  return Number(n).toLocaleString('en-IN');
}
function prettyDate(iso?: string | null) {
  if (!iso) return '—';
  const [year, month, day] = iso.split('-');
  if (!year || !month || !day) return iso;
  return `${day}-${month}-${year}`;
}
function ymd(d: Date) {
  const month = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${d.getFullYear()}-${month}-${day}`;
}
function shiftDays(d: Date, n: number) {
  const next = new Date(d.getFullYear(), d.getMonth(), d.getDate());
  next.setDate(next.getDate() + n);
  return next;
}
function shiftMonths(d: Date, n: number) {
  const next = new Date(d.getFullYear(), d.getMonth(), d.getDate());
  next.setMonth(next.getMonth() + n);
  return next;
}
function shiftYears(d: Date, n: number) {
  const next = new Date(d.getFullYear(), d.getMonth(), d.getDate());
  next.setFullYear(next.getFullYear() + n);
  return next;
}
function periodRange(preset: string, today = new Date()) {
  const end = new Date(today.getFullYear(), today.getMonth(), today.getDate());
  const pack = (currentFrom: Date, currentTo: Date, previousFrom: Date, previousTo: Date) => ({
    current_from: ymd(currentFrom),
    current_to: ymd(currentTo),
    previous_from: ymd(previousFrom),
    previous_to: ymd(previousTo),
  });
  if (preset === 'last_24_previous') return pack(end, end, shiftDays(end, -1), shiftDays(end, -1));
  if (preset === 'last_24_wow') {
    const previous = shiftDays(end, -7);
    return pack(end, end, previous, previous);
  }
  const days: Record<string, [number, 'previous' | 'yoy']> = {
    last_7_previous: [7, 'previous'],
    last_7_yoy: [7, 'yoy'],
    last_28_previous: [28, 'previous'],
    last_28_yoy: [28, 'yoy'],
  };
  if (preset in days) {
    const [count, mode] = days[preset];
    const start = shiftDays(end, -(count - 1));
    if (mode === 'yoy') return pack(start, end, shiftYears(start, -1), shiftYears(end, -1));
    const previousTo = shiftDays(start, -1);
    return pack(start, end, shiftDays(previousTo, -(count - 1)), previousTo);
  }
  const months: Record<string, [number, 'previous' | 'yoy']> = {
    last_3m_previous: [3, 'previous'],
    last_3m_yoy: [3, 'yoy'],
    last_6m_previous: [6, 'previous'],
  };
  if (preset in months) {
    const [count, mode] = months[preset];
    const start = shiftMonths(end, -count);
    if (mode === 'yoy') return pack(start, end, shiftYears(start, -1), shiftYears(end, -1));
    const previousTo = shiftDays(start, -1);
    return pack(start, end, shiftMonths(previousTo, -count), previousTo);
  }
  return periodRange('last_3m_previous', today);
}

function changeText(value: number | null | undefined) {
  if (value == null || Number.isNaN(Number(value))) return '—';
  const rounded = Number(value);
  return `${rounded > 0 ? '+' : ''}${rounded.toLocaleString('en-IN')}%`;
}

export function Analytics() {
  const [params, setParams] = useSearchParams();
  const paramsRef = useRef(params);
  paramsRef.current = params;
  const [meta, setMeta] = useState<any>(null);
  const [data, setData] = useState<any>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [customer, setCustomer] = useState(params.get('customer') || '');
  const [enquiry, setEnquiry] = useState(params.get('enquiry') || '');
  const [refreshed, setRefreshed] = useState('');
  const [tick, setTick] = useState(0);
  const [compareOpen, setCompareOpen] = useState(false);
  const [yearsOpen, setYearsOpen] = useState(false);

  const requestedCompare = params.get('compare') || 'lead';
  const compareBy = requestedCompare === 'quotation' || requestedCompare === 'quotation_value' ? 'quotation' : 'lead';
  const period = PERIODS.some(([id]) => id === params.get('period')) ? (params.get('period') as string) : 'last_28_previous';
  const customSeed = CUSTOM_DEFAULT;
  const activeRange = period === 'custom'
    ? {
        current_from: params.get('current_from') || customSeed.current_from,
        current_to: params.get('current_to') || customSeed.current_to,
        previous_from: params.get('previous_from') || customSeed.previous_from,
        previous_to: params.get('previous_to') || customSeed.previous_to,
      }
    : periodRange(period);

  function update(mutate: (next: URLSearchParams) => void) {
    const next = new URLSearchParams(paramsRef.current);
    mutate(next);
    setParams(next, { replace: true });
  }
  function setOne(key: string, value: string) {
    update((next) => {
      if (!value) next.delete(key);
      else next.set(key, value);
    });
  }
  function selectPeriod(value: string) {
    update((next) => {
      next.set('period', value);
      next.delete('month');
      next.delete('from_date');
      next.delete('to_date');
      next.delete('measure');
      if (value === 'custom') {
        const seed = CUSTOM_DEFAULT;
        if (!next.get('current_from')) next.set('current_from', seed.current_from);
        if (!next.get('current_to')) next.set('current_to', seed.current_to);
        if (!next.get('previous_from')) next.set('previous_from', seed.previous_from);
        if (!next.get('previous_to')) next.set('previous_to', seed.previous_to);
      } else {
        next.delete('current_from');
        next.delete('current_to');
        next.delete('previous_from');
        next.delete('previous_to');
      }
    });
  }

  function toggleYear(value: string) {
    update((next) => {
      const current = next.getAll('year');
      const had = current.includes(value);
      next.delete('year');
      (had ? current.filter((item) => item !== value) : [...current, value]).forEach((item) => next.append('year', item));
    });
  }

  useEffect(() => { setCustomer(params.get('customer') || ''); }, [params]);
  useEffect(() => { setEnquiry(params.get('enquiry') || ''); }, [params]);
  useEffect(() => {
    const timer = setTimeout(() => {
      const current = paramsRef.current.get('customer') || '';
      if (customer === current) return;
      update((next) => { if (customer) next.set('customer', customer); else next.delete('customer'); });
    }, 400);
    return () => clearTimeout(timer);
  }, [customer]);
  useEffect(() => {
    const timer = setTimeout(() => {
      const current = paramsRef.current.get('enquiry') || '';
      if (enquiry === current) return;
      update((next) => { if (enquiry) next.set('enquiry', enquiry); else next.delete('enquiry'); });
    }, 400);
    return () => clearTimeout(timer);
  }, [enquiry]);

  const query = useMemo(() => {
    const years = params.getAll('year').filter((value) => value !== '');
    const next: Record<string, string | string[]> = {
      compare_by: compareBy,
      current_from: activeRange.current_from,
      current_to: activeRange.current_to,
      previous_from: activeRange.previous_from,
      previous_to: activeRange.previous_to,
    };
    if (years.length === 1) next.year = years[0];
    else if (years.length > 1) next.year = years;
    FILTER_KEYS.forEach((key) => {
      const values = params.getAll(key).filter((value) => value !== '');
      if (values.length === 1) next[key] = values[0];
      else if (values.length > 1) next[key] = values;
    });
    return next;
  }, [params, compareBy, activeRange.current_from, activeRange.current_to, activeRange.previous_from, activeRange.previous_to]);

  useEffect(() => {
    const ctrl = new AbortController();
    setLoading(true);
    setError('');
    Promise.all([
      api.get('/analytics/meta', { signal: ctrl.signal, timeout: 30000 }),
      api.get('/analytics/comparison', { params: query, paramsSerializer: { indexes: null }, signal: ctrl.signal, timeout: 60000 }),
    ]).then(([metaRes, comparisonRes]) => {
      setMeta(metaRes.data);
      setData(comparisonRes.data);
      setRefreshed(new Date().toLocaleTimeString());
    }).catch((err) => {
      if (err?.code === 'ERR_CANCELED' || err?.name === 'CanceledError') return;
      setError(err?.response?.data?.detail || 'Could not load the comparison');
    }).finally(() => { if (!ctrl.signal.aborted) setLoading(false); });
    return () => ctrl.abort();
  }, [query, tick]);

  useEffect(() => subscribeLeadUpdates(() => setTick((value) => value + 1)), []);

  const kpi = data?.kpi;
  const series = (data?.series || []).map((row: any) => ({
    ...row,
    label: row.current_date ? prettyDate(row.current_date) : (row.previous_date ? prettyDate(row.previous_date) : `Day ${row.day}`),
  }));
  const countLabel = data?.count_label || (compareBy === 'quotation' ? 'No. of Quotations' : 'No. of Leads');
  const valueLabel = data?.value_label || (compareBy === 'quotation' ? 'Quotation Value' : 'Lead Value');
  const yearComparison = data?.year_comparison;
  const compareYears: number[] = yearComparison?.years || [];
  const yearRows = (yearComparison?.months || []).map((row: any) => {
    const point: Record<string, string | number> = { name: String(row.name || '').slice(0, 3) };
    compareYears.forEach((year) => {
      point[`count_${year}`] = Number(row.counts?.[String(year)] || 0);
      point[`value_${year}`] = Number(row.values?.[String(year)] || 0);
    });
    return point;
  });
  const selectedYears = params.getAll('year');
  const yearChoices = useMemo(() => {
    const end = new Date().getFullYear() + 15;
    const years: number[] = [];
    for (let year = end; year >= 1990; year -= 1) years.push(year);
    return years;
  }, []);

  function selectCompare(value: string) {
    update((next) => {
      next.set('compare', value);
      next.delete('measure');
    });
  }

  function reset() {
    setCustomer('');
    setEnquiry('');
    setParams(new URLSearchParams(), { replace: true });
  }

  return (
    <div>
      <PageHeader
        title="Lead comparison"
        subtitle="Compare a period with the one before it. Lead shows the number of leads and lead value. Quotation shows the number of quotations and quotation value."
        actions={<button type="button" className="btn-primary" onClick={reset}>Reset filters</button>}
      />
      {refreshed && <p className="text-xs text-graphite-500 -mt-4 mb-4">Last updated {refreshed}. New and updated leads refresh this page automatically.</p>}
      {error && <div className="bg-red-50 border border-red-200 text-red-700 text-sm rounded-xl px-4 py-3 mb-4">{String(error)}</div>}

      <Card title="Comparison">
        <div className="flex flex-wrap items-end gap-3 mb-4">
          <label className="text-sm w-full max-w-xs">Compare by
            <select className="input mt-1" value={compareBy} onChange={(e) => selectCompare(e.target.value)}>
              {COMPARE.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select>
          </label>
          <button type="button" className="btn-secondary" onClick={() => setCompareOpen((open) => !open)}>
            Compare
          </button>
          <button type="button" className="btn-secondary" onClick={() => setYearsOpen((open) => !open)}>
            Select years
          </button>
        </div>
        {compareOpen && (
          <div className="mb-4 max-w-xl rounded-lg border border-graphite-200 bg-white p-3 space-y-2">
            {PERIODS.map(([value, label]) => (
              <label key={value} className="flex items-center gap-2 text-sm text-graphite-800">
                <input type="radio" name="compare-period" checked={period === value} onChange={() => selectPeriod(value)} />
                <span>{label}</span>
              </label>
            ))}
            {period === 'custom' && (
              <div className="pt-2 space-y-3">
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <label className="text-sm">Start date
                    <input type="date" className="input mt-1" value={activeRange.current_from} onChange={(e) => setOne('current_from', e.target.value)} />
                    <span className="block text-[11px] text-graphite-400 mt-1">YYYY-MM-DD</span>
                  </label>
                  <label className="text-sm">End date
                    <input type="date" className="input mt-1" value={activeRange.current_to} onChange={(e) => setOne('current_to', e.target.value)} />
                    <span className="block text-[11px] text-graphite-400 mt-1">YYYY-MM-DD</span>
                  </label>
                </div>
                <div className="text-sm font-semibold text-graphite-600">vs.</div>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <label className="text-sm">Start date
                    <input type="date" className="input mt-1" value={activeRange.previous_from} onChange={(e) => setOne('previous_from', e.target.value)} />
                    <span className="block text-[11px] text-graphite-400 mt-1">YYYY-MM-DD</span>
                  </label>
                  <label className="text-sm">End date
                    <input type="date" className="input mt-1" value={activeRange.previous_to} onChange={(e) => setOne('previous_to', e.target.value)} />
                    <span className="block text-[11px] text-graphite-400 mt-1">YYYY-MM-DD</span>
                  </label>
                </div>
              </div>
            )}
          </div>
        )}
        {yearsOpen && (
          <div className="mb-4 max-h-56 overflow-auto flex flex-wrap gap-2">
            {yearChoices.map((year) => (
              <label key={year} className={`inline-flex items-center gap-2 rounded-lg border px-3 py-1.5 text-sm ${selectedYears.includes(String(year)) ? 'border-brand-400 bg-brand-50' : 'border-graphite-200 bg-white'}`}>
                <input type="checkbox" checked={selectedYears.includes(String(year))} onChange={() => toggleYear(String(year))} />
                {year}
              </label>
            ))}
          </div>
        )}
        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-3">
          <label className="text-sm">Employee
            <select className="input mt-1" value={params.get('employee') || ''} onChange={(e) => setOne('employee', e.target.value)}>
              <option value="">All</option>
              {(meta?.employees || []).map((item: any) => <option key={item.id} value={item.id}>{item.name}</option>)}
            </select>
          </label>
          <label className="text-sm">Source
            <select className="input mt-1" value={params.get('source') || ''} onChange={(e) => setOne('source', e.target.value)}>
              <option value="">All</option>
              {(meta?.sources || []).map((item: any) => <option key={item.id} value={item.id}>{item.name}</option>)}
            </select>
          </label>
          <label className="text-sm">Product
            <select className="input mt-1" value={params.get('product') || ''} onChange={(e) => setOne('product', e.target.value)}>
              <option value="">All</option>
              {(meta?.products || []).map((item: any) => <option key={item.id} value={item.id}>{item.name}</option>)}
            </select>
          </label>
          <label className="text-sm">Category
            <select className="input mt-1" value={params.get('category') || ''} onChange={(e) => setOne('category', e.target.value)}>
              <option value="">All</option>
              {(meta?.categories || []).map((name: string) => <option key={name} value={name}>{name}</option>)}
            </select>
          </label>
          <label className="text-sm">Progress
            <select className="input mt-1" value={params.get('progress') || ''} onChange={(e) => setOne('progress', e.target.value)}>
              <option value="">All</option>
              {PROGRESS_OPTIONS.map((name) => <option key={name} value={name}>{name}</option>)}
            </select>
          </label>
          <label className="text-sm">City
            <select className="input mt-1" value={params.get('city') || ''} onChange={(e) => setOne('city', e.target.value)}>
              <option value="">All</option>
              {(meta?.cities || []).map((name: string) => <option key={name} value={name}>{name}</option>)}
            </select>
          </label>
          <label className="text-sm">Cars
            <select className="input mt-1" value={params.get('cars') || ''} onChange={(e) => setOne('cars', e.target.value)}>
              <option value="">All</option>
              {(meta?.cars || []).map((name: string) => <option key={name} value={name}>{name}</option>)}
            </select>
          </label>
          <label className="text-sm">Customer
            <input className="input mt-1" value={customer} placeholder="Search customer name" onChange={(e) => setCustomer(e.target.value)} />
          </label>
          <label className="text-sm">Enquiry
            <input className="input mt-1" value={enquiry} placeholder="Search enquiry number" onChange={(e) => setEnquiry(e.target.value)} />
          </label>
        </div>
      </Card>

      {loading && !data ? <Spinner /> : (
        <div className="mt-4 space-y-4">
          <Card title="Summary">
            <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-5 gap-3">
              {[
                ['Total leads', num(kpi?.leads)],
                ['Total lead value', inr(kpi?.lead_value)],
                ['Total quotation value', inr(kpi?.quotation_value)],
                ['Converted leads', num(kpi?.converted)],
                ['Follow-up leads', num(kpi?.followup)],
                ['Not interested', num(kpi?.not_interested)],
                ['Meetings', num(kpi?.meeting)],
                ['Site visits', num(kpi?.site_visit)],
                ['Quotations sent', num(kpi?.quotation_sent)],
              ].map(([label, value]) => (
                <div key={label} className="rounded-xl border border-graphite-200 px-3 py-3">
                  <div className="text-[11px] uppercase tracking-wide text-graphite-500">{label}</div>
                  <div className="text-lg font-semibold text-graphite-900 mt-1">{value}</div>
                </div>
              ))}
            </div>
            {Number(kpi?.undated) > 0 && (
              <p className="text-xs text-graphite-500 mt-3">{num(kpi.undated)} leads have no enquiry date, so they are left out of this comparison.</p>
            )}
          </Card>

          <Card title="Year comparison">
            {compareYears.length === 0 ? <EmptyState title="No enquiry years for this selection" /> : (
              <>
                <div className="h-80 mb-4">
                  <ResponsiveContainer>
                    <LineChart data={yearRows}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis dataKey="name" tick={{ fontSize: 11 }} />
                      <YAxis yAxisId="count" tick={{ fontSize: 11 }} allowDecimals={false} />
                      <YAxis yAxisId="value" orientation="right" tick={{ fontSize: 11 }} />
                      <Tooltip formatter={(value: any, name: any) => [String(name).includes('value') || String(name).includes('Value') ? inr(Number(value)) : num(Number(value)), name]} />
                      <Legend />
                      {compareYears.map((year, index) => (
                        <Line key={`count-${year}`} yAxisId="count" type="monotone" dataKey={`count_${year}`} name={`${year} ${countLabel}`} stroke={COUNT_SHADES[index % COUNT_SHADES.length]} strokeWidth={2} dot={false} />
                      ))}
                      {compareYears.map((year, index) => (
                        <Line key={`value-${year}`} yAxisId="value" type="monotone" dataKey={`value_${year}`} name={`${year} ${valueLabel}`} stroke={VALUE_SHADES[index % VALUE_SHADES.length]} strokeWidth={2} dot={false} />
                      ))}
                    </LineChart>
                  </ResponsiveContainer>
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm min-w-[640px]">
                    <thead>
                      <tr>
                        <th className="th text-left">Month</th>
                        {compareYears.map((year) => (
                          <th key={year} className="th text-right" colSpan={2}>{year}</th>
                        ))}
                      </tr>
                      <tr>
                        <th className="th" />
                        {compareYears.map((year) => (
                          <Fragment key={year}>
                            <th className="th text-right">{countLabel}</th>
                            <th className="th text-right">{valueLabel}</th>
                          </Fragment>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {(yearComparison?.months || []).map((row: any) => (
                        <tr key={row.month}>
                          <td className="td font-medium">{row.name}</td>
                          {compareYears.map((year) => (
                            <Fragment key={`${row.month}-${year}`}>
                              <td className="td text-right tabular-nums">{num(row.counts?.[String(year)])}</td>
                              <td className="td text-right tabular-nums">{inr(row.values?.[String(year)])}</td>
                            </Fragment>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </>
            )}
          </Card>

          <Card title={`${data?.compare_label || 'Lead'} comparison`}>
            <div className="overflow-x-auto mb-4">
              <table className="w-full text-sm min-w-[520px]">
                <thead>
                  <tr>
                    <th className="th text-left"> </th>
                    <th className="th text-right">Selected period</th>
                    <th className="th text-right">Compared period</th>
                    <th className="th text-right">Change</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td className="td font-medium" style={{ color: COUNT_COLOR }}>{countLabel}</td>
                    <td className="td text-right tabular-nums">{num(data?.totals?.count)}</td>
                    <td className="td text-right tabular-nums">{num(data?.totals?.previous_count)}</td>
                    <td className="td text-right tabular-nums">{changeText(data?.count_change)}</td>
                  </tr>
                  <tr>
                    <td className="td font-medium" style={{ color: VALUE_COLOR }}>{valueLabel}</td>
                    <td className="td text-right tabular-nums">{inr(data?.totals?.value)}</td>
                    <td className="td text-right tabular-nums">{inr(data?.totals?.previous_value)}</td>
                    <td className="td text-right tabular-nums">{changeText(data?.value_change)}</td>
                  </tr>
                </tbody>
              </table>
            </div>
            {series.length === 0 ? <EmptyState title="No records for the selected period" /> : (
              <div className="h-80">
                <ResponsiveContainer>
                  <LineChart data={series}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="label" tick={{ fontSize: 11 }} minTickGap={28} />
                    <YAxis yAxisId="count" tick={{ fontSize: 11 }} allowDecimals={false} />
                    <YAxis yAxisId="value" orientation="right" tick={{ fontSize: 11 }} />
                    <Tooltip
                      formatter={(value: any, name: any) => [
                        String(name).includes('Value') ? inr(Number(value)) : num(Number(value)),
                        name,
                      ]}
                      labelFormatter={(_label: any, payload: any) => {
                        const row = payload?.[0]?.payload;
                        if (!row) return '';
                        return `Day ${row.day}: ${prettyDate(row.current_date)} vs ${prettyDate(row.previous_date)}`;
                      }}
                    />
                    <Legend />
                    <Line yAxisId="count" type="monotone" dataKey="count" name={countLabel} stroke={COUNT_COLOR} strokeWidth={2} dot={false} />
                    <Line yAxisId="count" type="monotone" dataKey="previous_count" name={`${countLabel} (previous)`} stroke={COUNT_COLOR} strokeWidth={2} strokeDasharray="6 4" dot={false} />
                    <Line yAxisId="value" type="monotone" dataKey="value" name={valueLabel} stroke={VALUE_COLOR} strokeWidth={2} dot={false} />
                    <Line yAxisId="value" type="monotone" dataKey="previous_value" name={`${valueLabel} (previous)`} stroke={VALUE_COLOR} strokeWidth={2} strokeDasharray="6 4" dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            )}
          </Card>
        </div>
      )}
    </div>
  );
}
