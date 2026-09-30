import { useEffect, useMemo, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { api } from '../services/api';
import { subscribeLeadUpdates } from '../services/live';
import { Card, EmptyState, PageHeader, Spinner } from '../components/ui';

const COMPARE = [
  ['leads', 'No. of leads'],
  ['lead_value', 'Lead value'],
  ['quotations', 'No. of quotations'],
  ['quotation_value', 'Quotation'],
  ['category', 'Category'],
  ['product', 'Product'],
  ['source', 'Source'],
  ['progress', 'Progress'],
] as const;
const COMPARE_IDS = new Set<string>(COMPARE.map(([value]) => value));
const LINE_COLORS = ['#1971C2', '#65A30D', '#7c3aed', '#E8890C', '#0e7490', '#c0392b', '#0369a1', '#3F6212', '#db2777', '#0891b2', '#1d4ed8', '#a16207'];
const PICK_LABELS: Record<string, string> = {
  category: 'Category',
  product: 'Product',
  source: 'Source',
  progress: 'Progress',
};
const PROGRESS_OPTIONS = [
  'In Followup',
  'Site Visit',
  'Meeting',
  'Quotation sent',
  'Converted',
  'Not Interested',
];
const RANGE_OPTIONS = [
  ['24h_prev', 'Compare last 24 hours to previous period'],
  ['24h_wow', 'Compare last 24 hours week over week'],
  ['7d_prev', 'Compare last 7 days to previous period'],
  ['7d_yoy', 'Compare last 7 days year over year'],
  ['28d_prev', 'Compare last 28 days to previous period'],
  ['28d_yoy', 'Compare last 28 days year over year'],
  ['3m_prev', 'Compare last 3 months to previous period'],
  ['3m_yoy', 'Compare last 3 months year over year'],
  ['6m_prev', 'Compare last 6 months to previous period'],
  ['custom', 'Custom'],
] as const;

function inr(n: number | null | undefined) {
  if (n == null || Number.isNaN(Number(n))) return '—';
  return `₹${Math.round(Number(n)).toLocaleString('en-IN')}`;
}
function num(n: number | null | undefined) {
  if (n == null || Number.isNaN(Number(n))) return '—';
  return Number(n).toLocaleString('en-IN');
}
function isoDate(day: Date) {
  const pad = (value: number) => String(value).padStart(2, '0');
  return `${day.getFullYear()}-${pad(day.getMonth() + 1)}-${pad(day.getDate())}`;
}
function defaultCustomRange() {
  const end = new Date();
  const start = new Date();
  start.setDate(end.getDate() - 27);
  const previousEnd = new Date(start);
  previousEnd.setDate(start.getDate() - 1);
  const previousStart = new Date(previousEnd);
  previousStart.setDate(previousEnd.getDate() - 27);
  return { cf: isoDate(start), ct: isoDate(end), pf: isoDate(previousStart), pt: isoDate(previousEnd) };
}
function prettyDate(value?: string | null) {
  if (!value) return '—';
  const [year, month, day] = value.slice(0, 10).split('-').map(Number);
  if (!year || !month || !day) return value;
  return new Date(year, month - 1, day).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' });
}
export function Analytics() {
  const [params, setParams] = useSearchParams();
  const paramsRef = useRef(params);
  paramsRef.current = params;
  const [data, setData] = useState<any>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [downloading, setDownloading] = useState(false);
  const [refreshed, setRefreshed] = useState('');
  const [tick, setTick] = useState(0);
  // Years stay in component state only — never URL — so a refresh never pre-checks them.
  const [selectedYears, setSelectedYears] = useState<string[]>([]);
  const [yearsOpen, setYearsOpen] = useState(false);
  const [rangeOpen, setRangeOpen] = useState(false);
  const [rangeData, setRangeData] = useState<any>(null);
  const [rangeError, setRangeError] = useState('');
  const [rangeLoading, setRangeLoading] = useState(false);
  const [draftRange, setDraftRange] = useState(params.get('range') || '7d_prev');
  const [draftError, setDraftError] = useState('');
  const [draftDates, setDraftDates] = useState({
    cf: params.get('cf') || '',
    ct: params.get('ct') || '',
    pf: params.get('pf') || '',
    pt: params.get('pt') || '',
  });
  const filtersRef = useRef<HTMLDivElement>(null);

  const requestedCompare = params.get('compare') || 'leads';
  const compareAlias = requestedCompare === 'lead' ? 'leads' : requestedCompare === 'quotation' ? 'quotations' : requestedCompare;
  const compareBy = COMPARE_IDS.has(compareAlias) ? compareAlias : 'leads';

  function update(mutate: (next: URLSearchParams) => void) {
    const next = new URLSearchParams(paramsRef.current);
    mutate(next);
    next.delete('year');
    setParams(next, { replace: true });
  }
  function setOne(key: string, value: string) {
    update((next) => {
      if (!value) next.delete(key);
      else next.set(key, value);
    });
  }
  function toggleYear(value: string) {
    setSelectedYears((current) => (
      current.includes(value) ? current.filter((item) => item !== value) : [...current, value].sort()
    ));
  }

  useEffect(() => subscribeLeadUpdates(() => setTick((value) => value + 1)), []);

  // Strip any leftover year=… from older builds so the address bar stays clean.
  useEffect(() => {
    if (paramsRef.current.getAll('year').length === 0) return;
    update((next) => { next.delete('year'); });
  }, []);

  useEffect(() => {
    if (!yearsOpen && !rangeOpen) return;
    const onPointerDown = (event: MouseEvent) => {
      if (!filtersRef.current || filtersRef.current.contains(event.target as Node)) return;
      // Native date pickers sit outside the panel DOM; keep Custom open while a date field is focused.
      const active = document.activeElement;
      if (
        rangeOpen
        && active instanceof HTMLInputElement
        && active.type === 'date'
        && filtersRef.current.contains(active)
      ) {
        return;
      }
      setYearsOpen(false);
      setRangeOpen(false);
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setYearsOpen(false);
        setRangeOpen(false);
      }
    };
    document.addEventListener('mousedown', onPointerDown);
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('mousedown', onPointerDown);
      document.removeEventListener('keydown', onKeyDown);
    };
  }, [yearsOpen, rangeOpen]);

  const yearKey = selectedYears.join(',');
  const query = useMemo(() => {
    const next: Record<string, string | string[]> = { compare_by: compareBy };
    if (selectedYears.length === 1) next.year = selectedYears[0];
    else if (selectedYears.length > 1) next.year = selectedYears;
    return next;
  }, [yearKey, compareBy, selectedYears]);

  useEffect(() => {
    if (selectedYears.length === 0) {
      setData(null);
      setLoading(false);
      setError('');
      return;
    }
    const ctrl = new AbortController();
    setLoading(true);
    setError('');
    api.get('/analytics/comparison', { params: query, paramsSerializer: { indexes: null }, signal: ctrl.signal, timeout: 60000 }).then((comparisonRes) => {
      setData(comparisonRes.data);
      setRefreshed(new Date().toLocaleTimeString());
    }).catch((err) => {
      if (err?.code === 'ERR_CANCELED' || err?.name === 'CanceledError') return;
      setError(err?.response?.data?.detail || 'Could not load the comparison');
    }).finally(() => { if (!ctrl.signal.aborted) setLoading(false); });
    return () => ctrl.abort();
  }, [query, tick, selectedYears.length]);

  const picked = params.get('item') || '';
  const rangePreset = params.get('range') || '';
  const rangeDates = [params.get('cf') || '', params.get('ct') || '', params.get('pf') || '', params.get('pt') || ''].join('|');
  useEffect(() => {
    if (!rangePreset) {
      setRangeData(null);
      setRangeError('');
      setRangeLoading(false);
      return;
    }
    const ctrl = new AbortController();
    setRangeLoading(true);
    setRangeError('');
    const [cf, ct, pf, pt] = rangeDates.split('|');
    const next: Record<string, string> = { compare_by: compareBy, preset: rangePreset };
    if (picked) next.item = picked;
    if (rangePreset === 'custom') {
      next.current_from = cf;
      next.current_to = ct;
      next.previous_from = pf;
      next.previous_to = pt;
    }
    api.get('/analytics/range-comparison', { params: next, signal: ctrl.signal, timeout: 60000 }).then((res) => {
      setRangeData(res.data);
    }).catch((err) => {
      if (err?.code === 'ERR_CANCELED' || err?.name === 'CanceledError') return;
      setRangeData(null);
      setRangeError(err?.response?.data?.detail || 'Could not load this comparison');
    }).finally(() => { if (!ctrl.signal.aborted) setRangeLoading(false); });
    return () => ctrl.abort();
  }, [rangePreset, rangeDates, compareBy, picked, tick]);

  const kpi = data?.kpi;
  // Chart and table only use years the user checked. Nothing is pre-selected.
  const compareYears: Array<number | string> = selectedYears.length
    ? selectedYears.map((year) => Number(year)).filter((year) => !Number.isNaN(year))
    : [];
  const breakdown: any[] = (() => {
    const rows = data?.compare_by === compareBy ? (data?.details || []) : [];
    if (compareBy !== 'progress') return rows;
    const allowed = new Set(PROGRESS_OPTIONS);
    const byName = new Map(rows.map((row: any) => [row.name, row]));
    return PROGRESS_OPTIONS.map((name) => byName.get(name) || { name, values: {} }).filter((row: any) => allowed.has(row.name));
  })();
  const pickLabel = PICK_LABELS[compareBy] || '';
  const focus = pickLabel ? breakdown.find((row) => row.name === picked) : null;
  const chartLines: { key: string; name: string }[] = compareYears.map((year) => ({ key: String(year), name: String(year) }));
  const chartPoints = selectedYears.length
    ? (data?.months || []).map((month: any) => {
      const point: Record<string, string | number> = { name: String(month.name || '').slice(0, 3) };
      const match = focus ? (data?.by_month || []).find((row: any) => row.month === month.month) : null;
      const item = match ? (match.items || []).find((row: any) => row.name === focus.name) : null;
      compareYears.forEach((year) => {
        point[String(year)] = Number((focus ? item?.values : month.values)?.[String(year)] || 0);
      });
      return point;
    })
    : [];
  const money = Boolean(data?.money);
  const formatCell = (value: number) => (money ? inr(value) : num(value));
  const yearChoices = useMemo(() => {
    const years: number[] = [];
    for (let year = 1900; year <= 2100; year += 1) years.push(year);
    return years;
  }, []);

  function selectCompare(value: string) {
    update((next) => {
      next.set('compare', value);
      next.delete('measure');
      next.delete('item');
    });
  }

  function openRange() {
    const current = paramsRef.current.get('range') || '7d_prev';
    setDraftRange(current);
    setDraftDates({
      cf: paramsRef.current.get('cf') || '',
      ct: paramsRef.current.get('ct') || '',
      pf: paramsRef.current.get('pf') || '',
      pt: paramsRef.current.get('pt') || '',
    });
    setYearsOpen(false);
    setRangeOpen((open) => !open);
  }

  function chooseRange(value: string) {
    setDraftRange(value);
    if (value === 'custom') {
      setDraftDates((current) => (current.cf && current.ct && current.pf && current.pt ? current : defaultCustomRange()));
    }
  }

  function applyRange() {
    if (draftRange === 'custom' && (!draftDates.cf || !draftDates.ct || !draftDates.pf || !draftDates.pt || draftDates.cf > draftDates.ct || draftDates.pf > draftDates.pt)) {
      setDraftError('Each range needs a start date on or before its end date');
      return;
    }
    update((next) => {
      next.set('range', draftRange);
      if (draftRange === 'custom') {
        next.set('cf', draftDates.cf);
        next.set('ct', draftDates.ct);
        next.set('pf', draftDates.pf);
        next.set('pt', draftDates.pt);
      } else {
        next.delete('cf');
        next.delete('ct');
        next.delete('pf');
        next.delete('pt');
      }
    });
    setDraftError('');
    setRangeError('');
    setRangeOpen(false);
  }

  function clearRange() {
    update((next) => {
      next.delete('range');
      next.delete('cf');
      next.delete('ct');
      next.delete('pf');
      next.delete('pt');
    });
    setRangeData(null);
    setRangeOpen(false);
  }

  async function downloadPdf() {
    setDownloading(true);
    setError('');
    try {
      const pdfParams: Record<string, string | string[]> = { compare_by: compareBy };
      const years = yearKey ? yearKey.split(',') : [];
      if (years.length === 1) pdfParams.year = years[0];
      else if (years.length > 1) pdfParams.year = years;
      // With a type chosen: that type only. With none: every type on its own pages.
      if (focus) pdfParams.item = focus.name;
      const res = await api.get('/analytics/comparison/pdf', {
        responseType: 'blob',
        params: pdfParams,
        paramsSerializer: { indexes: null },
        timeout: 120000,
      });
      const ctype = String(res.headers?.['content-type'] ?? '');
      if (ctype.includes('application/json')) {
        const text = await (res.data as Blob).text();
        let detail = 'Download failed';
        try { detail = JSON.parse(text)?.detail || detail; } catch { /* keep default */ }
        throw new Error(detail);
      }
      const slug = String(focus?.name || (pickLabel ? `all-${compareBy}` : compareBy)).replace(/[^\w.-]+/g, '-');
      const url = URL.createObjectURL(res.data);
      try {
        const a = document.createElement('a');
        a.href = url;
        a.download = `comparison-${slug}.pdf`;
        document.body.appendChild(a);
        a.click();
        a.remove();
      } finally {
        setTimeout(() => URL.revokeObjectURL(url), 2000);
      }
    } catch (err: any) {
      let detail = err?.message || 'Could not download the PDF';
      const blob = err?.response?.data;
      if (blob instanceof Blob) {
        try {
          const text = await blob.text();
          detail = JSON.parse(text)?.detail || detail;
        } catch { /* keep default */ }
      }
      setError(String(detail));
    } finally {
      setDownloading(false);
    }
  }

  return (
    <div>
      <PageHeader
        title="Lead comparison"
        subtitle="Compare the same months across years. January stays January. Only the year changes."
        actions={(
          <button type="button" className="btn-primary" disabled={downloading || selectedYears.length === 0} onClick={downloadPdf}>
            {downloading ? 'Downloading…' : 'Download PDF'}
          </button>
        )}
      />
      {refreshed && <p className="text-xs text-graphite-500 -mt-4 mb-4">Last updated {refreshed}. New and updated leads refresh this page automatically.</p>}
      {error && <div className="bg-red-50 border border-red-200 text-red-700 text-sm rounded-xl px-4 py-3 mb-4">{String(error)}</div>}

      <Card title="Comparison" className={yearsOpen || rangeOpen ? 'relative z-30' : ''}>
        <div ref={filtersRef} className="flex flex-wrap items-end gap-3 mb-4">
          <label className="text-sm w-full max-w-xs">Compare by
            <select className="input mt-1" value={compareBy} onChange={(e) => { setYearsOpen(false); setRangeOpen(false); selectCompare(e.target.value); }}>
              {COMPARE.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select>
          </label>
          {pickLabel && (
            <label className="text-sm w-full max-w-xs">{pickLabel}
              <select className="input mt-1" value={picked} onChange={(e) => { setYearsOpen(false); setRangeOpen(false); setOne('item', e.target.value); }}>
                <option value="">Choose one</option>
                {breakdown.map((row) => <option key={row.name} value={row.name}>{row.name}</option>)}
              </select>
            </label>
          )}
          <div className="relative text-sm w-full max-w-xs">
            <span className="block">Years</span>
            <button type="button" className="input mt-1 text-left" onClick={() => { setRangeOpen(false); setYearsOpen((open) => !open); }}>
              {selectedYears.length ? selectedYears.join(', ') : 'Select years'}
            </button>
            {yearsOpen && (
              <div className="absolute z-20 mt-1 max-h-56 w-full overflow-auto rounded-lg border border-graphite-200 bg-white shadow-lg">
                {yearChoices.map((year) => (
                  <label key={year} className="flex items-center gap-2 px-3 py-1.5 text-sm hover:bg-graphite-50">
                    <input type="checkbox" checked={selectedYears.includes(String(year))} onChange={() => toggleYear(String(year))} />
                    {year}
                  </label>
                ))}
              </div>
            )}
          </div>
          <div className="relative text-sm w-full max-w-xs">
            <span className="block">Compare</span>
            <button type="button" className="input mt-1 text-left truncate" onClick={openRange}>
              {RANGE_OPTIONS.find(([value]) => value === rangePreset)?.[1] || 'Choose a period'}
            </button>
            {rangeOpen && (
              <div
                className="absolute z-30 mt-1 w-[22rem] max-h-[28rem] overflow-auto rounded-lg border border-graphite-200 bg-white p-3 shadow-lg"
                onMouseDown={(event) => event.stopPropagation()}
              >
                <div className="space-y-1.5">
                  {RANGE_OPTIONS.map(([value, label]) => (
                    <label key={value} className="flex items-start gap-2 text-sm text-graphite-800">
                      <input className="mt-1" type="radio" name="range" checked={draftRange === value} onChange={() => chooseRange(value)} />
                      <span>{label}</span>
                    </label>
                  ))}
                </div>
                {draftRange === 'custom' && (
                  <div className="mt-3 space-y-2 border-t border-graphite-100 pt-3">
                    <p className="text-xs font-medium text-graphite-700">This period</p>
                    <div className="grid grid-cols-2 gap-2">
                      <label className="text-xs">Start date
                        <input className="input mt-1" type="date" value={draftDates.cf} onChange={(e) => setDraftDates((current) => ({ ...current, cf: e.target.value }))} />
                      </label>
                      <label className="text-xs">End date
                        <input className="input mt-1" type="date" value={draftDates.ct} onChange={(e) => setDraftDates((current) => ({ ...current, ct: e.target.value }))} />
                      </label>
                    </div>
                    <p className="text-xs font-medium text-graphite-700 pt-1">Compared period</p>
                    <div className="grid grid-cols-2 gap-2">
                      <label className="text-xs">Start date
                        <input className="input mt-1" type="date" value={draftDates.pf} onChange={(e) => setDraftDates((current) => ({ ...current, pf: e.target.value }))} />
                      </label>
                      <label className="text-xs">End date
                        <input className="input mt-1" type="date" value={draftDates.pt} onChange={(e) => setDraftDates((current) => ({ ...current, pt: e.target.value }))} />
                      </label>
                    </div>
                  </div>
                )}
                <div className="mt-3 flex justify-end gap-2">
                  <button type="button" className="btn-secondary" onClick={() => { setDraftError(''); setRangeOpen(false); }}>Cancel</button>
                  <button type="button" className="btn-primary" onClick={applyRange}>Apply</button>
                </div>
                {draftError && <p className="mt-2 text-xs text-red-700">{draftError}</p>}
              </div>
            )}
          </div>
        </div>
      </Card>

      <div className="mt-4 space-y-4">
        {selectedYears.length === 0 ? (
          <Card title="Comparison">
            <EmptyState title="Select years" hint="Open Years and tick one or more years for the month-by-year chart. Period compare below does not need years." />
          </Card>
        ) : loading && !data ? <Spinner /> : (
          <>
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
                <p className="text-xs text-graphite-500 mt-3">{num(kpi.undated)} leads have no enquiry date. Those are counted on the day they were added.</p>
              )}
            </Card>

            <Card title={data?.compare_label || 'Comparison'}>
              {compareYears.length === 0 ? <EmptyState title="No enquiry years for this selection" hint="Choose one or more years that have leads." /> : (
                <>
                  <p className="text-xs text-graphite-500 mb-3">
                    {pickLabel && !focus
                      ? `Choose one ${pickLabel.toLowerCase()}. Only that one is compared across the selected years.`
                      : focus
                        ? `${focus.name}. Twelve months, with the count for each selected year on the right.`
                        : 'Twelve months. The count for each selected year is on the right.'}
                  </p>
                  {pickLabel && !focus ? <EmptyState title={`Choose one ${pickLabel.toLowerCase()}`} hint="The comparison shows only the one you pick." /> : chartPoints.length === 0 ? <EmptyState title="No records for the selected years" /> : (
                    <div className="h-80 mb-4">
                      <ResponsiveContainer>
                        <LineChart data={chartPoints}>
                          <CartesianGrid strokeDasharray="3 3" />
                          <XAxis dataKey="name" tick={{ fontSize: 11 }} />
                          <YAxis tick={{ fontSize: 11 }} allowDecimals={money} />
                          <Tooltip formatter={(value: any, name: any) => [formatCell(Number(value)), name]} />
                          <Legend />
                          {chartLines.map((line, index) => (
                            <Line key={line.key} type="monotone" dataKey={line.key} name={line.name} stroke={LINE_COLORS[index % LINE_COLORS.length]} strokeWidth={2} dot={false} />
                          ))}
                        </LineChart>
                      </ResponsiveContainer>
                    </div>
                  )}
                  {pickLabel && focus ? (
                    <div className="overflow-x-auto">
                      <table className="w-full text-sm min-w-[480px]">
                        <thead>
                          <tr>
                            <th className="th text-left">Month</th>
                            {compareYears.map((year) => (
                              <th key={year} className="th text-right">{year}</th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {(data?.months || []).map((month: any) => {
                            const match = (data?.by_month || []).find((row: any) => row.month === month.month);
                            const item = (match?.items || []).find((row: any) => row.name === focus.name);
                            return (
                              <tr key={month.month}>
                                <td className="td font-medium">{month.name}</td>
                                {compareYears.map((year) => (
                                  <td key={`${month.month}-${year}`} className="td text-right tabular-nums">{formatCell(Number(item?.values?.[String(year)] || 0))}</td>
                                ))}
                              </tr>
                            );
                          })}
                          <tr>
                            <td className="td font-semibold">Total</td>
                            {compareYears.map((year) => (
                              <td key={`total-${year}`} className="td text-right tabular-nums font-semibold">{formatCell(Number(focus.values?.[String(year)] || 0))}</td>
                            ))}
                          </tr>
                        </tbody>
                      </table>
                    </div>
                  ) : pickLabel ? null : (
                    <div className="overflow-x-auto">
                      <table className="w-full text-sm min-w-[480px]">
                        <thead>
                          <tr>
                            <th className="th text-left">Month</th>
                            {compareYears.map((year) => (
                              <th key={year} className="th text-right">{year}</th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {(data?.months || []).map((row: any) => (
                            <tr key={row.month}>
                              <td className="td font-medium">{row.name}</td>
                              {compareYears.map((year) => (
                                <td key={`${row.month}-${year}`} className="td text-right tabular-nums">{formatCell(Number(row.values?.[String(year)] || 0))}</td>
                              ))}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </>
              )}
            </Card>
          </>
        )}

        {(rangePreset || rangeLoading || rangeError) && (
          <Card title="Period comparison" action={<button type="button" className="text-xs text-graphite-500 hover:text-graphite-800" onClick={clearRange}>Remove</button>}>
            {rangeLoading && !rangeData ? <Spinner /> : rangeError ? (
              <p className="text-sm text-red-700">{rangeError}</p>
            ) : rangeData ? (
              <>
                <p className="text-sm text-graphite-700">{rangeData.preset_label}{rangeData.item ? ` · ${rangeData.item}` : ''}</p>
                <p className="text-xs text-graphite-500 mt-1 mb-3">
                  {prettyDate(rangeData.current?.from)} – {prettyDate(rangeData.current?.to)}
                  {' vs '}
                  {prettyDate(rangeData.previous?.from)} – {prettyDate(rangeData.previous?.to)}
                </p>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-4">
                  {[
                    ['This period', rangeData.money ? inr(rangeData.current_total) : num(rangeData.current_total)],
                    ['Compared period', rangeData.money ? inr(rangeData.previous_total) : num(rangeData.previous_total)],
                    ['Change', rangeData.change == null ? '—' : `${rangeData.change > 0 ? '+' : ''}${rangeData.change}%`],
                  ].map(([label, value]) => (
                    <div key={label} className="rounded-xl border border-graphite-200 px-3 py-3">
                      <div className="text-[11px] uppercase tracking-wide text-graphite-500">{label}</div>
                      <div className="text-lg font-semibold text-graphite-900 mt-1">{value}</div>
                    </div>
                  ))}
                </div>
                {(rangeData.series || []).length > 0 && (
                  <div className="h-80">
                    <ResponsiveContainer>
                      <LineChart data={(rangeData.series || []).map((row: any) => ({
                        name: prettyDate(row.current_date),
                        current: Number(row.current || 0),
                        previous: Number(row.previous || 0),
                      }))}>
                        <CartesianGrid strokeDasharray="3 3" />
                        <XAxis dataKey="name" tick={{ fontSize: 11 }} minTickGap={24} />
                        <YAxis tick={{ fontSize: 11 }} allowDecimals={Boolean(rangeData.money)} />
                        <Tooltip formatter={(value: any, name: any) => [rangeData.money ? inr(Number(value)) : num(Number(value)), name === 'current' ? 'This period' : 'Compared period']} />
                        <Legend formatter={(value) => (value === 'current' ? 'This period' : 'Compared period')} />
                        <Line type="monotone" dataKey="current" name="current" stroke={LINE_COLORS[0]} strokeWidth={2} dot={false} />
                        <Line type="monotone" dataKey="previous" name="previous" stroke={LINE_COLORS[1]} strokeWidth={2} dot={false} />
                      </LineChart>
                    </ResponsiveContainer>
                  </div>
                )}
              </>
            ) : null}
          </Card>
        )}
      </div>
    </div>
  );
}
