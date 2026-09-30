import { useEffect, useMemo, useState } from 'react';
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { api } from '../services/api';
import { Card, EmptyState, PageHeader, Spinner } from '../components/ui';

const FILTER_TYPES = [
  ['category', 'Category'],
  ['product', 'Product'],
  ['source', 'Source'],
  ['progress', 'Progress'],
] as const;

const METRICS = [
  ['leads', 'No. of Leads', false],
  ['lead_value', 'Lead Value', true],
  ['quotations', 'No. of Quotations', false],
  ['quotation_value', 'Quotation Value', true],
] as const;

const GRANULARITIES = [
  ['day', 'Date-wise'],
  ['week', 'Week-wise'],
  ['month', 'Month-wise'],
  ['year', 'Year-wise'],
] as const;

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

export function Analytics() {
  const [filterType, setFilterType] = useState('');
  const [filterValue, setFilterValue] = useState('');
  const [filterValues, setFilterValues] = useState<string[]>([]);
  const [valuesLoading, setValuesLoading] = useState(false);
  const [metric, setMetric] = useState<string>('leads');
  const [granularity, setGranularity] = useState<string>('month');
  const [year, setYear] = useState<string>(String(new Date().getFullYear()));
  const [fromDate, setFromDate] = useState('');
  const [toDate, setToDate] = useState('');

  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const [aFrom, setAFrom] = useState(isoDaysAgo(27));
  const [aTo, setATo] = useState(todayIso());
  const [bFrom, setBFrom] = useState(isoDaysAgo(55));
  const [bTo, setBTo] = useState(isoDaysAgo(28));
  const [periodData, setPeriodData] = useState<any>(null);
  const [periodLoading, setPeriodLoading] = useState(false);
  const [periodError, setPeriodError] = useState('');

  useEffect(() => {
    if (!filterType) {
      setFilterValues([]);
      setFilterValue('');
      return;
    }
    const ctrl = new AbortController();
    setValuesLoading(true);
    setFilterValue('');
    api.get('/analytics/filter-options', { params: { type: filterType }, signal: ctrl.signal })
      .then((res) => setFilterValues(res.data?.values || []))
      .catch((err) => {
        if (err?.code === 'ERR_CANCELED' || err?.name === 'CanceledError') return;
        setFilterValues([]);
        setError(err?.response?.data?.detail || 'Could not load filter values');
      })
      .finally(() => { if (!ctrl.signal.aborted) setValuesLoading(false); });
    return () => ctrl.abort();
  }, [filterType]);

  const needsValue = Boolean(filterType);
  const ready = !needsValue || Boolean(filterValue);

  const dashQuery = useMemo(() => {
    const next: Record<string, string | number> = { metric, granularity };
    if (filterType) next.filter_type = filterType;
    if (filterValue) next.filter_value = filterValue;
    if (granularity === 'month' && year) next.year = Number(year);
    if ((granularity === 'day' || granularity === 'week') && fromDate && toDate) {
      next.from_date = fromDate;
      next.to_date = toDate;
    }
    return next;
  }, [filterType, filterValue, metric, granularity, year, fromDate, toDate]);

  useEffect(() => {
    if (granularity !== 'day' && granularity !== 'week') return;
    if (fromDate && toDate) return;
    setFromDate(isoDaysAgo(89));
    setToDate(todayIso());
  }, [granularity, fromDate, toDate]);

  useEffect(() => {
    if (!ready) {
      setData(null);
      setLoading(false);
      return;
    }
    const ctrl = new AbortController();
    setLoading(true);
    setError('');
    api.get('/analytics/dashboard', { params: dashQuery, signal: ctrl.signal, timeout: 60000 })
      .then((res) => setData(res.data))
      .catch((err) => {
        if (err?.code === 'ERR_CANCELED' || err?.name === 'CanceledError') return;
        setData(null);
        setError(err?.response?.data?.detail || 'Could not load analytics');
      })
      .finally(() => { if (!ctrl.signal.aborted) setLoading(false); });
    return () => ctrl.abort();
  }, [dashQuery, ready]);

  useEffect(() => {
    if (!ready || !aFrom || !aTo || !bFrom || !bTo) {
      setPeriodData(null);
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
    if (filterType) params.filter_type = filterType;
    if (filterValue) params.filter_value = filterValue;
    api.get('/analytics/period-compare', { params, signal: ctrl.signal, timeout: 60000 })
      .then((res) => setPeriodData(res.data))
      .catch((err) => {
        if (err?.code === 'ERR_CANCELED' || err?.name === 'CanceledError') return;
        setPeriodData(null);
        setPeriodError(err?.response?.data?.detail || 'Could not load period comparison');
      })
      .finally(() => { if (!ctrl.signal.aborted) setPeriodLoading(false); });
    return () => ctrl.abort();
  }, [ready, filterType, filterValue, metric, aFrom, aTo, bFrom, bTo]);

  const money = Boolean(data?.money);
  const formatValue = (value: number) => (money ? inr(value) : num(value));
  const yearChoices = data?.data_years?.length ? data.data_years : data?.years || [];
  const selectedMetric = METRICS.find(([id]) => id === metric);
  const scopeLabel = filterType && filterValue
    ? `${FILTER_TYPES.find(([id]) => id === filterType)?.[1] || filterType}: ${filterValue}`
    : 'All leads';

  return (
    <div>
      <PageHeader
        title="Analytics"
        subtitle="Filter by category, product, source, or progress. Pick a metric and time grain."
      />

      <Card title="Filters" className="mb-4">
        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-3">
          <label className="text-sm">Filter type
            <select
              className="input mt-1"
              value={filterType}
              onChange={(e) => setFilterType(e.target.value)}
            >
              <option value="">All leads</option>
              {FILTER_TYPES.map(([id, label]) => (
                <option key={id} value={id}>{label}</option>
              ))}
            </select>
          </label>

          <label className="text-sm">Filter value
            <select
              className="input mt-1"
              value={filterValue}
              disabled={!filterType || valuesLoading}
              onChange={(e) => setFilterValue(e.target.value)}
            >
              <option value="">{!filterType ? 'Select a filter type first' : valuesLoading ? 'Loading…' : 'Choose one'}</option>
              {filterValues.map((value) => (
                <option key={value} value={value}>{value}</option>
              ))}
            </select>
          </label>

          <label className="text-sm">Time analysis
            <select className="input mt-1" value={granularity} onChange={(e) => setGranularity(e.target.value)}>
              {GRANULARITIES.map(([id, label]) => (
                <option key={id} value={id}>{label}</option>
              ))}
            </select>
          </label>

          {granularity === 'month' ? (
            <label className="text-sm">Year
              <select className="input mt-1" value={year} onChange={(e) => setYear(e.target.value)}>
                {(yearChoices.length ? yearChoices : [new Date().getFullYear()]).map((item: number) => (
                  <option key={item} value={item}>{item}</option>
                ))}
              </select>
            </label>
          ) : granularity === 'year' ? (
            <div className="text-sm text-graphite-500 flex items-end pb-2">One bar/point per enquiry year in the data.</div>
          ) : (
            <div className="grid grid-cols-2 gap-2">
              <label className="text-sm">From
                <input className="input mt-1" type="date" value={fromDate} onChange={(e) => setFromDate(e.target.value)} />
              </label>
              <label className="text-sm">To
                <input className="input mt-1" type="date" value={toDate} onChange={(e) => setToDate(e.target.value)} />
              </label>
            </div>
          )}
        </div>
        <p className="text-xs text-graphite-500 mt-3">
          Showing <span className="font-medium text-graphite-700">{scopeLabel}</span>
          {' · '}
          {selectedMetric?.[1] || 'No. of Leads'}
          {' · '}
          {GRANULARITIES.find(([id]) => id === granularity)?.[1]}
          {year && granularity === 'month' ? ` · ${year}` : ''}
        </p>
      </Card>

      {error && <div className="bg-red-50 border border-red-200 text-red-700 text-sm rounded-xl px-4 py-3 mb-4">{String(error)}</div>}

      {!ready ? (
        <Card>
          <EmptyState title="Choose a filter value" hint="Pick Category, Product, Source, or Progress, then select one value from the database." />
        </Card>
      ) : loading && !data ? (
        <Spinner />
      ) : (
        <div className="space-y-4">
          <div className="grid grid-cols-2 xl:grid-cols-4 gap-3">
            {METRICS.map(([id, label, isMoney]) => {
              const value = data?.kpi?.[id];
              const active = metric === id;
              return (
                <button
                  key={id}
                  type="button"
                  onClick={() => setMetric(id)}
                  className={`card p-5 text-left transition ring-1 ${active ? 'ring-brand-600 bg-brand-50/40' : 'ring-transparent hover:ring-graphite-200'}`}
                >
                  <div className="text-xs font-medium uppercase tracking-wider text-graphite-500">{label}</div>
                  <div className="text-2xl font-bold text-graphite-900 mt-1">
                    {isMoney ? inr(value) : num(value)}
                  </div>
                  {active && <div className="text-xs text-brand-700 mt-1">Selected for chart</div>}
                </button>
              );
            })}
          </div>

          <Card title={`${selectedMetric?.[1] || 'Metric'} · ${GRANULARITIES.find(([id]) => id === granularity)?.[1]}`}>
            {!data?.series?.length ? (
              <EmptyState title="No records for this selection" hint="Try another filter value, year, or date range." />
            ) : (
              <div className="h-80">
                <ResponsiveContainer>
                  <LineChart data={data.series}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="label" tick={{ fontSize: 11 }} minTickGap={24} />
                    <YAxis tick={{ fontSize: 11 }} allowDecimals={money} />
                    <Tooltip formatter={(value: any) => [formatValue(Number(value)), selectedMetric?.[1] || 'Value']} />
                    <Legend />
                    <Line type="monotone" dataKey="value" name={selectedMetric?.[1] || 'Value'} stroke="#1971C2" strokeWidth={2} dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            )}
            {data?.series?.length > 0 && (
              <div className="overflow-x-auto mt-4">
                <table className="w-full text-sm min-w-[360px]">
                  <thead>
                    <tr>
                      <th className="th text-left">Period</th>
                      <th className="th text-right">{selectedMetric?.[1]}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.series.map((row: any) => (
                      <tr key={row.key}>
                        <td className="td">{row.label}</td>
                        <td className="td text-right tabular-nums">{formatValue(Number(row.value || 0))}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>

          <Card title="Date range vs date range">
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
                  {periodData.aligned ? ' · aligned day-by-day' : ' · different lengths'}
                </p>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-4">
                  {[
                    ['Period A', periodData.money ? inr(periodData.period_a?.total) : num(periodData.period_a?.total)],
                    ['Period B', periodData.money ? inr(periodData.period_b?.total) : num(periodData.period_b?.total)],
                    ['Change (A vs B)', periodData.change == null ? '—' : `${periodData.change > 0 ? '+' : ''}${periodData.change}%`],
                  ].map(([label, value]) => (
                    <div key={label} className="rounded-xl border border-graphite-200 px-3 py-3">
                      <div className="text-[11px] uppercase tracking-wide text-graphite-500">{label}</div>
                      <div className="text-lg font-semibold text-graphite-900 mt-1">{value}</div>
                    </div>
                  ))}
                </div>
                {(periodData.series || []).length > 0 && (
                  <div className="h-80">
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
              </>
            ) : null}
          </Card>
        </div>
      )}
    </div>
  );
}
