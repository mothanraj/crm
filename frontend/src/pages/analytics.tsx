import { useEffect, useMemo, useState } from 'react';
import {
  Bar, BarChart, CartesianGrid, Cell, Legend, Line, LineChart, Pie, PieChart,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';
import { api } from '../services/api';
import {
  CATEGORY_HEX, Card, EmptyState, PageHeader, PROGRESS_HEX, Spinner,
} from '../components/ui';

const METRICS = [
  ['leads', 'No. of Leads', false],
  ['lead_value', 'Lead Value', true],
  ['quotations', 'No. of Quotations', false],
  ['quotation_value', 'Quotation Value', true],
] as const;

const DIMENSIONS = [
  ['category', 'Category'],
  ['product', 'Product'],
  ['progress', 'Progress'],
  ['source', 'Source'],
] as const;

const GRANULARITIES = [
  ['day', 'Day'],
  ['week', 'Week'],
  ['month', 'Month'],
  ['year', 'Year'],
] as const;

const RANGE_PRESETS = [
  ['7d', 'Last 7 days'],
  ['28d', 'Last 28 days'],
  ['90d', 'Last 90 days'],
  ['month', 'This month'],
  ['custom', 'Custom'],
] as const;

const CHART_COLORS = ['#1971C2', '#65A30D', '#E8890C', '#7C3AED', '#0e7490', '#DC2626', '#BE185D', '#0284C7', '#475569', '#16A34A'];

type DimKind = 'category' | 'product' | 'progress' | 'source';

function inr(n: number | null | undefined) {
  if (n == null || Number.isNaN(Number(n))) return '—';
  return `₹${Math.round(Number(n)).toLocaleString('en-IN')}`;
}

function num(n: number | null | undefined) {
  if (n == null || Number.isNaN(Number(n))) return '—';
  return Number(n).toLocaleString('en-IN');
}

function prettyDate(value?: string | null) {
  if (!value) return '—';
  const [year, month, day] = value.slice(0, 10).split('-').map(Number);
  if (!year || !month || !day) return value;
  return new Date(year, month - 1, day).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' });
}

function isoDaysAgo(days: number) {
  const d = new Date();
  d.setDate(d.getDate() - days);
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

function todayIso() {
  return isoDaysAgo(0);
}

function monthStartIso() {
  const d = new Date();
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-01`;
}

function rangeForPreset(preset: string): { from: string; to: string } {
  if (preset === '7d') return { from: isoDaysAgo(6), to: todayIso() };
  if (preset === '28d') return { from: isoDaysAgo(27), to: todayIso() };
  if (preset === '90d') return { from: isoDaysAgo(89), to: todayIso() };
  if (preset === 'month') return { from: monthStartIso(), to: todayIso() };
  return { from: isoDaysAgo(27), to: todayIso() };
}

function previousRange(from: string, to: string): { from: string; to: string } {
  const start = new Date(`${from}T00:00:00`);
  const end = new Date(`${to}T00:00:00`);
  const length = Math.round((end.getTime() - start.getTime()) / 86400000);
  const prevEnd = new Date(start);
  prevEnd.setDate(prevEnd.getDate() - 1);
  const prevStart = new Date(prevEnd);
  prevStart.setDate(prevStart.getDate() - length);
  const pad = (n: number) => String(n).padStart(2, '0');
  const fmt = (d: Date) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  return { from: fmt(prevStart), to: fmt(prevEnd) };
}

function changeLabel(change: number | null | undefined) {
  if (change == null) return { text: '—', tone: 'text-graphite-400' };
  const sign = change > 0 ? '+' : '';
  const tone = change > 0 ? 'text-emerald-700' : change < 0 ? 'text-red-700' : 'text-graphite-500';
  return { text: `${sign}${change}%`, tone };
}

function dimColor(name: string, kind: DimKind, index: number) {
  if (kind === 'progress') return PROGRESS_HEX[name] || PROGRESS_HEX['Not Interested/Spam'] || CHART_COLORS[index % CHART_COLORS.length];
  if (kind === 'category') {
    if (name.startsWith('A+')) return CATEGORY_HEX['A+ (Immediate)'];
    if (name.startsWith('A ')) return CATEGORY_HEX['A (3-6 months)'];
    if (name.startsWith('B ')) return CATEGORY_HEX['B (1 year)'];
    if (name.startsWith('C ')) return CATEGORY_HEX['C (Planning Stage)'];
    return CATEGORY_HEX[name] || CHART_COLORS[index % CHART_COLORS.length];
  }
  return CHART_COLORS[index % CHART_COLORS.length];
}

function BreakdownPanel({
  title,
  rows,
  kind,
  money,
  selected,
  onSelect,
}: {
  title: string;
  rows: Array<{ name: string; value: number; pct?: number | null }>;
  kind: DimKind;
  money: boolean;
  selected: string;
  onSelect: (name: string) => void;
}) {
  const fmt = (v: number) => (money ? inr(v) : num(v));
  if (!rows.length) {
    return (
      <Card title={title}>
        <EmptyState title={`No ${kind} data`} hint="Matching leads will appear here." />
      </Card>
    );
  }
  return (
    <Card title={title}>
      <div className="h-56 mb-3">
        <ResponsiveContainer>
          <PieChart>
            <Pie data={rows} dataKey="value" nameKey="name" innerRadius={48} outerRadius={80} paddingAngle={2}>
              {rows.map((row, index) => (
                <Cell
                  key={row.name}
                  fill={dimColor(row.name, kind, index)}
                  stroke={selected === row.name ? '#111827' : '#fff'}
                  strokeWidth={selected === row.name ? 2 : 1}
                  style={{ cursor: 'pointer' }}
                  onClick={() => onSelect(selected === row.name ? '' : row.name)}
                />
              ))}
            </Pie>
            <Tooltip formatter={(value: any, name: any) => [fmt(Number(value)), name]} />
          </PieChart>
        </ResponsiveContainer>
      </div>
      <div className="space-y-1.5 max-h-56 overflow-auto pr-1">
        {rows.map((row, index) => {
          const active = selected === row.name;
          return (
            <button
              key={row.name}
              type="button"
              onClick={() => onSelect(active ? '' : row.name)}
              className={`w-full flex items-center gap-2 rounded-lg px-2 py-1.5 text-left text-sm transition ${active ? 'bg-graphite-100 ring-1 ring-graphite-300' : 'hover:bg-graphite-50'}`}
            >
              <span className="w-2.5 h-2.5 rounded-full shrink-0" style={{ background: dimColor(row.name, kind, index) }} />
              <span className="flex-1 truncate text-graphite-800">{row.name}</span>
              <span className="tabular-nums text-graphite-900 font-medium">{fmt(row.value)}</span>
              <span className="w-12 text-right text-xs text-graphite-500 tabular-nums">{row.pct == null ? '—' : `${row.pct}%`}</span>
            </button>
          );
        })}
      </div>
    </Card>
  );
}

function chipClass(active: boolean) {
  return `px-3 py-1.5 rounded-lg text-sm font-medium transition ${active ? 'bg-graphite-800 text-white' : 'bg-graphite-100 text-graphite-700 hover:bg-graphite-200'}`;
}

export function Analytics() {
  const [preset, setPreset] = useState('28d');
  const initial = rangeForPreset('28d');
  const [fromDate, setFromDate] = useState(initial.from);
  const [toDate, setToDate] = useState(initial.to);
  const [metric, setMetric] = useState('leads');
  const [granularity, setGranularity] = useState('day');
  const [dimType, setDimType] = useState<DimKind | ''>('');
  const [dimValue, setDimValue] = useState('');
  const [dimOptions, setDimOptions] = useState<string[]>([]);
  const [dimOptionsLoading, setDimOptionsLoading] = useState(false);

  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const [compareOpen, setCompareOpen] = useState(false);
  const [aFrom, setAFrom] = useState(initial.from);
  const [aTo, setATo] = useState(initial.to);
  const prev = previousRange(initial.from, initial.to);
  const [bFrom, setBFrom] = useState(prev.from);
  const [bTo, setBTo] = useState(prev.to);
  const [periodData, setPeriodData] = useState<any>(null);
  const [periodLoading, setPeriodLoading] = useState(false);
  const [periodError, setPeriodError] = useState('');

  useEffect(() => {
    if (preset === 'custom') return;
    const next = rangeForPreset(preset);
    setFromDate(next.from);
    setToDate(next.to);
  }, [preset]);

  useEffect(() => {
    if (!dimType) {
      setDimOptions([]);
      return;
    }
    const ctrl = new AbortController();
    setDimOptionsLoading(true);
    api.get('/analytics/filter-options', { params: { type: dimType }, signal: ctrl.signal })
      .then((res) => setDimOptions(res.data?.values || []))
      .catch((err) => {
        if (err?.code === 'ERR_CANCELED' || err?.name === 'CanceledError') return;
        setDimOptions([]);
      })
      .finally(() => { if (!ctrl.signal.aborted) setDimOptionsLoading(false); });
    return () => ctrl.abort();
  }, [dimType]);

  const filterReady = !dimType || Boolean(dimValue);

  const overviewParams = useMemo(() => {
    if (!filterReady) return null;
    const next: Record<string, string> = {
      metric,
      from_date: fromDate,
      to_date: toDate,
      granularity,
    };
    if (dimType && dimValue) {
      next.filter_type = dimType;
      next.filter_value = dimValue;
    }
    return next;
  }, [metric, fromDate, toDate, granularity, dimType, dimValue, filterReady]);

  useEffect(() => {
    if (!overviewParams) {
      setLoading(false);
      return;
    }
    if (!fromDate || !toDate || fromDate > toDate) {
      setError('From date must be on or before to date');
      setLoading(false);
      return;
    }
    const ctrl = new AbortController();
    setLoading(true);
    setError('');
    api.get('/analytics/overview', { params: overviewParams, signal: ctrl.signal, timeout: 60000 })
      .then((res) => setData(res.data))
      .catch((err) => {
        if (err?.code === 'ERR_CANCELED' || err?.name === 'CanceledError') return;
        setData(null);
        setError(err?.response?.data?.detail || 'Could not load analytics');
      })
      .finally(() => { if (!ctrl.signal.aborted) setLoading(false); });
    return () => ctrl.abort();
  }, [overviewParams, fromDate, toDate]);

  useEffect(() => {
    if (!compareOpen || !filterReady) {
      setPeriodData(null);
      return;
    }
    if (!aFrom || !aTo || !bFrom || !bTo || aFrom > aTo || bFrom > bTo) {
      setPeriodError('Each period needs a valid from / to date');
      return;
    }
    const ctrl = new AbortController();
    setPeriodLoading(true);
    setPeriodError('');
    const params: Record<string, string> = {
      metric,
      a_from: aFrom,
      a_to: aTo,
      b_from: bFrom,
      b_to: bTo,
    };
    if (dimType && dimValue) {
      params.filter_type = dimType;
      params.filter_value = dimValue;
    }
    api.get('/analytics/period-compare', { params, signal: ctrl.signal, timeout: 60000 })
      .then((res) => setPeriodData(res.data))
      .catch((err) => {
        if (err?.code === 'ERR_CANCELED' || err?.name === 'CanceledError') return;
        setPeriodData(null);
        setPeriodError(err?.response?.data?.detail || 'Could not load comparison');
      })
      .finally(() => { if (!ctrl.signal.aborted) setPeriodLoading(false); });
    return () => ctrl.abort();
  }, [compareOpen, metric, dimType, dimValue, filterReady, aFrom, aTo, bFrom, bTo]);

  const money = Boolean(data?.money);
  const selectedMetric = METRICS.find(([id]) => id === metric);
  const formatValue = (value: number) => (money ? inr(value) : num(value));
  const scopeLabel = dimType && dimValue
    ? `${DIMENSIONS.find(([id]) => id === dimType)?.[1] || dimType}: ${dimValue}`
    : 'All leads';

  function selectDimension(next: DimKind) {
    if (dimType === next) {
      setDimType('');
      setDimValue('');
      return;
    }
    setDimType(next);
    setDimValue('');
  }

  function applyDimValueFromChart(kind: DimKind, name: string) {
    if (!name) {
      if (dimType === kind) {
        setDimType('');
        setDimValue('');
      }
      return;
    }
    setDimType(kind);
    setDimValue(name);
  }

  function applyCompareFromOverview() {
    setAFrom(fromDate);
    setATo(toDate);
    const prior = previousRange(fromDate, toDate);
    setBFrom(prior.from);
    setBTo(prior.to);
    setCompareOpen(true);
  }

  const selectedFor = (kind: DimKind) => (dimType === kind ? dimValue : '');

  return (
    <div className="space-y-4">
      <PageHeader
        title="Analytics"
        subtitle="Pick a metric and optional filter, then compare date ranges on the chart."
        actions={(
          <button type="button" className="btn-secondary" onClick={applyCompareFromOverview} disabled={!filterReady}>
            {compareOpen ? 'Refresh comparison' : 'Compare periods'}
          </button>
        )}
      />

      <Card>
        <div className="space-y-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-graphite-500 mb-2">Metric</p>
            <div className="flex flex-wrap gap-1.5">
              {METRICS.map(([id, label]) => (
                <button key={id} type="button" onClick={() => setMetric(id)} className={chipClass(metric === id)}>
                  {label}
                </button>
              ))}
            </div>
          </div>

          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-graphite-500 mb-2">Filter</p>
            <div className="flex flex-wrap items-center gap-1.5">
              {DIMENSIONS.map(([id, label]) => (
                <button key={id} type="button" onClick={() => selectDimension(id)} className={chipClass(dimType === id)}>
                  {label}
                </button>
              ))}
              {dimType && (
                <label className="text-sm ml-1 min-w-[12rem]">
                  <span className="sr-only">{DIMENSIONS.find(([id]) => id === dimType)?.[1]} value</span>
                  <select
                    className="input !py-1.5"
                    value={dimValue}
                    disabled={dimOptionsLoading}
                    onChange={(e) => setDimValue(e.target.value)}
                  >
                    <option value="">{dimOptionsLoading ? 'Loading…' : `Select ${DIMENSIONS.find(([id]) => id === dimType)?.[1]?.toLowerCase()}`}</option>
                    {dimOptions.map((value) => (
                      <option key={value} value={value}>{value}</option>
                    ))}
                  </select>
                </label>
              )}
              {(dimType || dimValue) && (
                <button
                  type="button"
                  className="btn-secondary !py-1.5"
                  onClick={() => { setDimType(''); setDimValue(''); }}
                >
                  Clear filter
                </button>
              )}
            </div>
            {dimType && !dimValue && (
              <p className="text-xs text-amber-700 mt-2">Choose a {DIMENSIONS.find(([id]) => id === dimType)?.[1]?.toLowerCase()} value to load the charts.</p>
            )}
          </div>

          <div className="flex flex-wrap items-end gap-3">
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-graphite-500 mb-2">Time</p>
              <div className="flex flex-wrap gap-1.5">
                {GRANULARITIES.map(([id, label]) => (
                  <button key={id} type="button" onClick={() => setGranularity(id)} className={chipClass(granularity === id)}>
                    {label}
                  </button>
                ))}
              </div>
            </div>
            <div className="flex flex-wrap gap-1.5">
              {RANGE_PRESETS.map(([id, label]) => (
                <button key={id} type="button" onClick={() => setPreset(id)} className={chipClass(preset === id)}>
                  {label}
                </button>
              ))}
            </div>
            <label className="text-sm">From
              <input
                className="input mt-1"
                type="date"
                value={fromDate}
                onChange={(e) => { setPreset('custom'); setFromDate(e.target.value); }}
              />
            </label>
            <label className="text-sm">To
              <input
                className="input mt-1"
                type="date"
                value={toDate}
                onChange={(e) => { setPreset('custom'); setToDate(e.target.value); }}
              />
            </label>
          </div>
        </div>
        <p className="text-xs text-graphite-500 mt-3">
          {prettyDate(fromDate)} – {prettyDate(toDate)}
          {data?.previous_from ? ` · vs previous ${prettyDate(data.previous_from)} – ${prettyDate(data.previous_to)}` : ''}
          {` · ${scopeLabel}`}
          {` · ${granularity}-wise`}
        </p>
      </Card>

      {error && <div className="bg-red-50 border border-red-200 text-red-700 text-sm rounded-xl px-4 py-3">{String(error)}</div>}

      {!filterReady ? (
        <Card>
          <EmptyState
            title={`Select a ${DIMENSIONS.find(([id]) => id === dimType)?.[1]?.toLowerCase()} value`}
            hint="The value filter appears next to Category, Product, Progress, or Source."
          />
        </Card>
      ) : loading && !data ? <Spinner /> : data ? (
        <>
          <div className="grid grid-cols-2 xl:grid-cols-4 gap-3">
            {METRICS.map(([id, label, isMoney]) => {
              const value = data.kpi?.[id];
              const change = changeLabel(data.kpi_change?.[id]);
              const active = metric === id;
              return (
                <button
                  key={id}
                  type="button"
                  onClick={() => setMetric(id)}
                  className={`rounded-xl border bg-white p-4 text-left transition ${active ? 'border-brand-600 ring-1 ring-brand-600 shadow-sm' : 'border-graphite-200 hover:border-graphite-300'}`}
                >
                  <div className="text-[11px] font-semibold uppercase tracking-wide text-graphite-500">{label}</div>
                  <div className="text-2xl font-bold text-graphite-900 mt-1 tabular-nums">
                    {isMoney ? inr(value) : num(value)}
                  </div>
                  <div className={`text-xs mt-1 font-medium ${change.tone}`}>
                    {change.text} vs previous period
                  </div>
                </button>
              );
            })}
          </div>

          <Card title={`${selectedMetric?.[1] || 'Metric'} · ${scopeLabel}`}>
            {!data.series?.length ? (
              <EmptyState title="No trend for this selection" hint="Try a wider date range or clear the filter." />
            ) : (
              <div className="h-80">
                <ResponsiveContainer>
                  <LineChart data={data.series}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                    <XAxis dataKey="label" tick={{ fontSize: 11 }} minTickGap={28} />
                    <YAxis tick={{ fontSize: 11 }} allowDecimals={money} width={56} />
                    <Tooltip formatter={(value: any) => [formatValue(Number(value)), selectedMetric?.[1] || 'Value']} />
                    <Line type="monotone" dataKey="value" name={selectedMetric?.[1] || 'Value'} stroke="#1971C2" strokeWidth={2.5} dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            )}
          </Card>

          <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
            <BreakdownPanel
              title="Progress"
              rows={data.by_progress || []}
              kind="progress"
              money={money}
              selected={selectedFor('progress')}
              onSelect={(name) => applyDimValueFromChart('progress', name)}
            />
            <BreakdownPanel
              title="Category"
              rows={data.by_category || []}
              kind="category"
              money={money}
              selected={selectedFor('category')}
              onSelect={(name) => applyDimValueFromChart('category', name)}
            />
            <BreakdownPanel
              title="Product"
              rows={data.by_product || []}
              kind="product"
              money={money}
              selected={selectedFor('product')}
              onSelect={(name) => applyDimValueFromChart('product', name)}
            />
            <BreakdownPanel
              title="Source"
              rows={data.by_source || []}
              kind="source"
              money={money}
              selected={selectedFor('source')}
              onSelect={(name) => applyDimValueFromChart('source', name)}
            />
          </div>

          <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
            <Card title="Progress ranking">
              {(data.by_progress || []).length === 0 ? <EmptyState title="No progress rows" /> : (
                <div className="h-72">
                  <ResponsiveContainer>
                    <BarChart data={data.by_progress} layout="vertical" margin={{ left: 8, right: 16 }}>
                      <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                      <XAxis type="number" tick={{ fontSize: 11 }} allowDecimals={money} />
                      <YAxis type="category" dataKey="name" width={110} tick={{ fontSize: 11 }} />
                      <Tooltip formatter={(value: any) => [formatValue(Number(value)), selectedMetric?.[1] || 'Value']} />
                      <Bar dataKey="value" radius={[0, 4, 4, 0]}>
                        {(data.by_progress || []).map((row: any, index: number) => (
                          <Cell
                            key={row.name}
                            fill={dimColor(row.name, 'progress', index)}
                            cursor="pointer"
                            onClick={() => applyDimValueFromChart('progress', selectedFor('progress') === row.name ? '' : row.name)}
                          />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              )}
            </Card>
            <Card title="Category ranking">
              {(data.by_category || []).length === 0 ? <EmptyState title="No category rows" /> : (
                <div className="h-72">
                  <ResponsiveContainer>
                    <BarChart data={data.by_category} layout="vertical" margin={{ left: 8, right: 16 }}>
                      <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                      <XAxis type="number" tick={{ fontSize: 11 }} allowDecimals={money} />
                      <YAxis type="category" dataKey="name" width={120} tick={{ fontSize: 11 }} />
                      <Tooltip formatter={(value: any) => [formatValue(Number(value)), selectedMetric?.[1] || 'Value']} />
                      <Bar dataKey="value" radius={[0, 4, 4, 0]}>
                        {(data.by_category || []).map((row: any, index: number) => (
                          <Cell
                            key={row.name}
                            fill={dimColor(row.name, 'category', index)}
                            cursor="pointer"
                            onClick={() => applyDimValueFromChart('category', selectedFor('category') === row.name ? '' : row.name)}
                          />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              )}
            </Card>
          </div>
        </>
      ) : null}

      {compareOpen && filterReady && (
        <Card title="Period comparison" action={<button type="button" className="text-xs text-graphite-500 hover:text-graphite-800" onClick={() => setCompareOpen(false)}>Hide</button>}>
          <p className="text-xs text-graphite-500 mb-3">
            Comparing <span className="font-medium text-graphite-700">{selectedMetric?.[1]}</span>
            {' · '}
            <span className="font-medium text-graphite-700">{scopeLabel}</span>
          </p>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
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

          {periodError && <p className="text-sm text-red-700 mb-3">{periodError}</p>}
          {periodLoading && !periodData ? <Spinner /> : periodData ? (
            <>
              <p className="text-xs text-graphite-500 mb-3">
                {prettyDate(periodData.period_a?.from)} – {prettyDate(periodData.period_a?.to)}
                {' vs '}
                {prettyDate(periodData.period_b?.from)} – {prettyDate(periodData.period_b?.to)}
                {periodData.aligned ? ' · aligned day-by-day' : ''}
              </p>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-4">
                {[
                  ['Period A', periodData.money ? inr(periodData.period_a?.total) : num(periodData.period_a?.total)],
                  ['Period B', periodData.money ? inr(periodData.period_b?.total) : num(periodData.period_b?.total)],
                  ['Change (A vs B)', periodData.change == null ? '—' : `${periodData.change > 0 ? '+' : ''}${periodData.change}%`],
                ].map(([label, value]) => (
                  <div key={label} className="rounded-xl border border-graphite-200 px-3 py-3">
                    <div className="text-[11px] uppercase tracking-wide text-graphite-500">{label}</div>
                    <div className="text-lg font-semibold text-graphite-900 mt-1 tabular-nums">{value}</div>
                  </div>
                ))}
              </div>
              {(periodData.series || []).length > 0 && (
                <div className="h-80 mb-4">
                  <ResponsiveContainer>
                    <LineChart data={periodData.series}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis dataKey="label" tick={{ fontSize: 11 }} minTickGap={24} />
                      <YAxis tick={{ fontSize: 11 }} allowDecimals={Boolean(periodData.money)} />
                      <Tooltip
                        formatter={(value: any, name: any) => [
                          periodData.money ? inr(Number(value)) : num(Number(value)),
                          name === 'period_a' ? 'Period A' : 'Period B',
                        ]}
                      />
                      <Legend formatter={(value) => (value === 'period_a' ? 'Period A' : 'Period B')} />
                      <Line type="monotone" dataKey="period_a" name="period_a" stroke="#1971C2" strokeWidth={2} dot={false} />
                      <Line type="monotone" dataKey="period_b" name="period_b" stroke="#65A30D" strokeWidth={2} dot={false} />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              )}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="rounded-xl border border-graphite-200 p-3">
                  <p className="text-xs font-semibold uppercase tracking-wide text-graphite-500 mb-2">Period A · Progress</p>
                  <ul className="space-y-1 text-sm">
                    {(periodData.period_a?.by_progress || []).slice(0, 8).map((row: any) => (
                      <li key={`a-p-${row.name}`} className="flex justify-between gap-2">
                        <span className="truncate">{row.name}</span>
                        <span className="tabular-nums">{periodData.money ? inr(row.value) : num(row.value)}</span>
                      </li>
                    ))}
                    {!(periodData.period_a?.by_progress || []).length && <li className="text-graphite-500">No rows</li>}
                  </ul>
                </div>
                <div className="rounded-xl border border-graphite-200 p-3">
                  <p className="text-xs font-semibold uppercase tracking-wide text-graphite-500 mb-2">Period B · Progress</p>
                  <ul className="space-y-1 text-sm">
                    {(periodData.period_b?.by_progress || []).slice(0, 8).map((row: any) => (
                      <li key={`b-p-${row.name}`} className="flex justify-between gap-2">
                        <span className="truncate">{row.name}</span>
                        <span className="tabular-nums">{periodData.money ? inr(row.value) : num(row.value)}</span>
                      </li>
                    ))}
                    {!(periodData.period_b?.by_progress || []).length && <li className="text-graphite-500">No rows</li>}
                  </ul>
                </div>
                <div className="rounded-xl border border-graphite-200 p-3">
                  <p className="text-xs font-semibold uppercase tracking-wide text-graphite-500 mb-2">Period A · Category</p>
                  <ul className="space-y-1 text-sm">
                    {(periodData.period_a?.by_category || []).slice(0, 8).map((row: any) => (
                      <li key={`a-c-${row.name}`} className="flex justify-between gap-2">
                        <span className="truncate">{row.name}</span>
                        <span className="tabular-nums">{periodData.money ? inr(row.value) : num(row.value)}</span>
                      </li>
                    ))}
                    {!(periodData.period_a?.by_category || []).length && <li className="text-graphite-500">No rows</li>}
                  </ul>
                </div>
                <div className="rounded-xl border border-graphite-200 p-3">
                  <p className="text-xs font-semibold uppercase tracking-wide text-graphite-500 mb-2">Period B · Category</p>
                  <ul className="space-y-1 text-sm">
                    {(periodData.period_b?.by_category || []).slice(0, 8).map((row: any) => (
                      <li key={`b-c-${row.name}`} className="flex justify-between gap-2">
                        <span className="truncate">{row.name}</span>
                        <span className="tabular-nums">{periodData.money ? inr(row.value) : num(row.value)}</span>
                      </li>
                    ))}
                    {!(periodData.period_b?.by_category || []).length && <li className="text-graphite-500">No rows</li>}
                  </ul>
                </div>
              </div>
            </>
          ) : null}
        </Card>
      )}
    </div>
  );
}
