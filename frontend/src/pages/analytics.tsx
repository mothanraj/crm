import { useEffect, useMemo, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { api } from '../services/api';
import { subscribeLeadUpdates } from '../services/live';
import { Card, EmptyState, PageHeader, Spinner } from '../components/ui';

const COLORS = ['#65A30D', '#1971C2', '#E8890C', '#3F6212', '#6E6E6E', '#2F9E44', '#B5CC18', '#0e7490', '#A3A380', '#84cc16'];
const COMPARE = [
  ['lead_value', 'Lead Value'],
  ['quotation_value', 'Quotation Value'],
] as const;
const MEASURES: Record<string, [string, string][]> = {
  lead_value: [['leads', 'No. of Leads'], ['lead_value', 'Total Lead Value']],
  quotation_value: [['quotations', 'No. of Quotations'], ['quotation_value', 'Total Quotation Value']],
};
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
const QUARTERS: [string, number[]][] = [
  ['Q1', [1, 2, 3]],
  ['Q2', [4, 5, 6]],
  ['Q3', [7, 8, 9]],
  ['Q4', [10, 11, 12]],
];
const FILTER_KEYS = ['year', 'month', 'from_date', 'to_date', 'employee', 'source', 'product', 'category', 'progress', 'city', 'cars', 'customer', 'enquiry'];

function inr(n: number | null | undefined) {
  if (n == null || Number.isNaN(Number(n))) return '—';
  return `₹${Math.round(Number(n)).toLocaleString('en-IN')}`;
}
function num(n: number | null | undefined) {
  if (n == null || Number.isNaN(Number(n))) return '—';
  return Number(n).toLocaleString('en-IN');
}
function show(money: boolean, value: number | null | undefined) {
  return money ? inr(value) : num(value);
}
function prettyDate(iso: string) {
  const [year, month, day] = iso.split('-');
  if (!year || !month || !day) return iso;
  return `${day}-${month}-${year}`;
}
function sameNumbers(left: number[], right: number[]) {
  return left.length === right.length && left.every((value, index) => value === right[index]);
}

function CheckGroup({ label, options, selected, onToggle }: {
  label: string;
  options: { value: string; label: string }[];
  selected: string[];
  onToggle: (value: string) => void;
}) {
  return (
    <fieldset className="min-w-0">
      <legend className="text-[11px] font-semibold uppercase tracking-wide text-graphite-500 mb-1">{label}</legend>
      <div className="max-h-36 overflow-auto rounded-lg border border-graphite-200 bg-white p-2 space-y-1">
        {options.length === 0 && <div className="text-xs text-graphite-400">None in the database</div>}
        {options.map((option) => (
          <label key={option.value} className="flex items-center gap-2 text-sm text-graphite-800">
            <input type="checkbox" checked={selected.includes(option.value)} onChange={() => onToggle(option.value)} />
            <span className="truncate">{option.label}</span>
          </label>
        ))}
      </div>
    </fieldset>
  );
}

function ComparisonTable({ rowHeader, columns, rows, totalLabel, totals, money }: {
  rowHeader: string;
  columns: number[];
  rows: { key: string; label: string; values: Record<string, number> }[];
  totalLabel?: string;
  totals?: Record<string, number>;
  money: boolean;
}) {
  if (!columns.length) return <EmptyState title="No enquiry dates for this selection" hint="Leads without an enquiry date stay in the summary totals only." />;
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm min-w-[640px]">
        <thead>
          <tr>
            <th className="th text-left">{rowHeader}</th>
            {columns.map((year) => <th key={year} className="th text-right">{year}</th>)}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.key}>
              <td className="td font-medium">{row.label}</td>
              {columns.map((year) => <td key={year} className="td text-right tabular-nums">{show(money, row.values?.[String(year)] || 0)}</td>)}
            </tr>
          ))}
          {totals && (
            <tr className="bg-graphite-50 font-semibold">
              <td className="td">{totalLabel || 'Total'}</td>
              {columns.map((year) => <td key={year} className="td text-right tabular-nums">{show(money, totals[String(year)] || 0)}</td>)}
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
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

  const requestedCompare = params.get('compare') || 'lead_value';
  const compareBy = requestedCompare in MEASURES ? requestedCompare : 'lead_value';
  const measureOptions = MEASURES[compareBy] || MEASURES.lead_value;
  const measure = measureOptions.some(([key]) => key === params.get('measure')) ? (params.get('measure') as string) : measureOptions[0][0];

  function update(mutate: (next: URLSearchParams) => void) {
    const next = new URLSearchParams(paramsRef.current);
    mutate(next);
    setParams(next, { replace: true });
  }
  function toggle(key: string, value: string) {
    update((next) => {
      const current = next.getAll(key);
      const had = current.includes(value);
      next.delete(key);
      (had ? current.filter((item) => item !== value) : [...current, value]).forEach((item) => next.append(key, item));
    });
  }
  function setOne(key: string, value: string) {
    update((next) => {
      if (!value) next.delete(key);
      else next.set(key, value);
    });
  }
  function setMonths(values: number[]) {
    update((next) => {
      next.delete('month');
      values.forEach((value) => next.append('month', String(value)));
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
    const next: Record<string, string | string[]> = { compare_by: compareBy, measure };
    FILTER_KEYS.forEach((key) => {
      const values = params.getAll(key).filter((value) => value !== '');
      if (values.length === 1) next[key] = values[0];
      else if (values.length > 1) next[key] = values;
    });
    return next;
  }, [params, compareBy, measure]);

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

  const years: number[] = data?.years || [];
  const money = Boolean(data?.money);
  const selectedMonths = params.getAll('month').map(Number).filter((value) => value >= 1 && value <= 12).sort((a, b) => a - b);
  const monthOptions = (meta?.months || []).map((item: any) => ({ value: String(item.value), label: item.label }));
  const yearOptions = (meta?.years || []).map((year: number) => ({ value: String(year), label: String(year) }));
  const kpi = data?.kpi;
  const monthRows = (data?.months || []).map((row: any) => ({ key: String(row.month), label: row.name, values: row.values || {} }));
  const detailRows = (data?.details || []).map((row: any) => ({ key: row.name, label: row.name, values: row.values || {} }));
  const chartSource = data?.detail_label ? detailRows : monthRows;
  const chartRows = chartSource
    .map((row: { label: string; values: Record<string, number> }) => ({
      name: row.label.length > 18 ? `${row.label.slice(0, 16)}…` : row.label,
      total: years.reduce((sum, year) => sum + Number(row.values[String(year)] || 0), 0),
      ...Object.fromEntries(years.map((year) => [String(year), Number(row.values[String(year)] || 0)])),
    }))
    .filter((row: { total: number }) => row.total > 0)
    .slice(0, 12);

  const extra = [
    params.get('employee') && `Employee ${meta?.employees?.find((item: any) => item.id === params.get('employee'))?.name || ''}`,
    params.get('source') && `Source ${meta?.sources?.find((item: any) => item.id === params.get('source'))?.name || ''}`,
    params.get('product') && `Product ${meta?.products?.find((item: any) => item.id === params.get('product'))?.name || ''}`,
    params.get('category') && `Category ${params.get('category')}`,
    params.get('progress') && `Progress ${params.get('progress')}`,
    params.get('city') && `City ${params.get('city')}`,
    params.get('cars') && `Cars ${params.get('cars')}`,
    params.get('customer') && `Customer ${params.get('customer')}`,
    params.get('enquiry') && `Enquiry ${params.get('enquiry')}`,
  ].filter(Boolean);
  const scope = [
    data?.compare_label && `Compare by ${data.compare_label}`,
    data?.measure_label,
    params.getAll('year').length ? `Years ${[...params.getAll('year')].sort().join(', ')}` : 'All years',
    selectedMonths.length ? `Months ${selectedMonths.map((month) => meta?.months?.find((item: any) => item.value === month)?.label || month).join(', ')}` : 'All months',
    params.get('from_date') && `From ${prettyDate(params.get('from_date') || '')}`,
    params.get('to_date') && `To ${prettyDate(params.get('to_date') || '')}`,
    ...extra,
  ].filter(Boolean).join(' · ');

  function selectCompare(value: string) {
    update((next) => {
      next.set('compare', value);
      const allowed = (MEASURES[value] || MEASURES.lead_value).map(([key]) => key);
      if (!allowed.includes(next.get('measure') || '')) next.set('measure', allowed[0]);
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
        subtitle="Compare years and groups of months from the live lead records. Each lead is counted once."
        actions={<button type="button" className="btn-primary" onClick={reset}>Reset filters</button>}
      />
      {refreshed && <p className="text-xs text-graphite-500 -mt-4 mb-4">Last updated {refreshed}. New and updated leads refresh this page automatically.</p>}
      {error && <div className="bg-red-50 border border-red-200 text-red-700 text-sm rounded-xl px-4 py-3 mb-4">{String(error)}</div>}

      <Card title="Comparison">
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-3 mb-4">
          <label className="text-sm">Compare by
            <select className="input mt-1" value={compareBy} onChange={(e) => selectCompare(e.target.value)}>
              {COMPARE.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select>
          </label>
          <label className="text-sm">Measure
            <select className="input mt-1" value={measure} onChange={(e) => setOne('measure', e.target.value)}>
              {measureOptions.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select>
          </label>
          <label className="text-sm">From date
            <input type="date" className="input mt-1" value={params.get('from_date') || ''} onChange={(e) => setOne('from_date', e.target.value)} />
          </label>
          <label className="text-sm">To date
            <input type="date" className="input mt-1" value={params.get('to_date') || ''} onChange={(e) => setOne('to_date', e.target.value)} />
          </label>
        </div>
        <div className="flex flex-wrap gap-2 mb-4">
          <button type="button" className={`btn-secondary !py-1 ${selectedMonths.length === 0 ? '!bg-brand-50 !border-brand-400' : ''}`} onClick={() => setMonths([])}>All months</button>
          {QUARTERS.map(([label, values]) => (
            <button key={label} type="button" className={`btn-secondary !py-1 ${sameNumbers(selectedMonths, values) ? '!bg-brand-50 !border-brand-400' : ''}`} onClick={() => setMonths(values)}>{label}</button>
          ))}
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-4">
          <CheckGroup label="Select years" options={yearOptions} selected={params.getAll('year')} onToggle={(value) => toggle('year', value)} />
          <CheckGroup label="Select months" options={monthOptions} selected={params.getAll('month')} onToggle={(value) => toggle('month', value)} />
        </div>
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
        {scope && <p className="text-sm text-graphite-600 mt-4">{scope}. The date range, years, and months all apply together.</p>}
        {compareBy === 'quotation_value' && (
          <p className="text-xs text-graphite-500 mt-2">A missing quotation is left out. A saved ₹0 is included. This uses the quotation stored on the lead, not a sum of quotation revisions.</p>
        )}
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
              <p className="text-xs text-graphite-500 mt-3">{num(kpi.undated)} leads have no enquiry date. They are included in these totals and omitted from the year columns.</p>
            )}
          </Card>

          <Card title="Year comparison">
            <ComparisonTable
              rowHeader="Month"
              columns={years}
              rows={monthRows}
              totalLabel={data?.period_label || 'Total'}
              totals={data?.selected_total}
              money={money}
            />
          </Card>

          <Card title="Visual comparison">
            {chartRows.length === 0 ? <EmptyState title="No records for the selected period" /> : (
              <div className="h-80">
                <ResponsiveContainer>
                  <BarChart data={chartRows}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="name" tick={{ fontSize: 11 }} interval={0} angle={-28} height={70} textAnchor="end" />
                    <YAxis tick={{ fontSize: 11 }} />
                    <Tooltip formatter={(value: any, name: any) => [show(money, Number(value)), name]} />
                    <Legend />
                    {years.map((year, index) => (
                      <Bar key={year} dataKey={String(year)} name={String(year)} fill={COLORS[index % COLORS.length]} />
                    ))}
                  </BarChart>
                </ResponsiveContainer>
              </div>
            )}
            {chartSource.length > 12 && chartRows.length > 0 && (
              <p className="text-xs text-graphite-500 mt-2">The chart shows the 12 largest rows. The table lists every row.</p>
            )}
          </Card>

          {data?.detail_label && (
            <Card title="Detailed results">
              <ComparisonTable rowHeader={data.detail_label} columns={years} rows={detailRows} money={money} />
            </Card>
          )}
        </div>
      )}
    </div>
  );
}
