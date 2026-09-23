import { useEffect, useState } from 'react';
import { Cell, Legend, Pie, PieChart, ResponsiveContainer, Tooltip } from 'recharts';
import { api } from '../services/api';
import { Card, EmptyState, PageHeader, Spinner } from '../components/ui';

const MONTH_OPTIONS = [1, 2, 3, 4, 6, 12];
const COLORS = ['#65A30D', '#6E6E6E', '#B5CC18', '#3F6212', '#A3A380', '#2F9E44', '#E8890C', '#84cc16', '#a3a380', '#4d7c0f', '#14b8a6', '#1971C2'];

function inr(n: any) {
  const v = Math.round(Number(n) || 0);
  return `₹${v.toLocaleString('en-IN', { maximumFractionDigits: 0 })}`;
}

function actionCount(side: any, name: string) {
  return side?.by_action?.find((row: any) => row.name === name)?.leads || 0;
}

function MixPie({ rows }: { rows: { name: string; value: number }[] }) {
  if (!rows.length) return <EmptyState title="No data" />;
  return (
    <div className="h-80">
      <ResponsiveContainer>
        <PieChart>
          <Pie data={rows} dataKey="value" nameKey="name" outerRadius={110} label={({ percent }) => `${(((percent ?? 0)) * 100).toFixed(0)}%`}>
            {rows.map((entry, index) => <Cell key={entry.name} fill={COLORS[index % COLORS.length]} />)}
          </Pie>
          <Tooltip /><Legend />
        </PieChart>
      </ResponsiveContainer>
    </div>
  );
}

function MixTable({ rows }: { rows: any[] }) {
  const totals = rows.reduce((sum, row) => ({
    total: sum.total + (row.total || 0),
    follow: sum.follow + (row['In Followup'] || 0),
    meeting: sum.meeting + (row.Meeting || 0),
    site: sum.site + (row['Site Visit'] || 0),
    quote: sum.quote + (row['Quotation sent'] || 0),
    notInt: sum.notInt + (row['Not Interested'] || 0),
  }), { total: 0, follow: 0, meeting: 0, site: 0, quote: 0, notInt: 0 });
  return (
    <div className="overflow-x-auto -mx-5 px-5">
      <table className="w-full min-w-[640px] text-sm text-center">
        <thead>
          <tr className="bg-[#0e7490] text-white">
            <th className="th !text-white !bg-transparent !text-center">Name</th>
            <th className="th !text-white !bg-transparent !text-center">Total Leads</th>
            <th className="th !text-white !bg-transparent !text-center">In Followup</th>
            <th className="th !text-white !bg-transparent !text-center">Meeting</th>
            <th className="th !text-white !bg-transparent !text-center">Site Visit</th>
            <th className="th !text-white !bg-transparent !text-center">Quotation sent</th>
            <th className="th !text-white !bg-transparent !text-center">Not Interested</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={row.name} className={index % 2 ? 'bg-sky-50/60' : 'bg-white'}>
              <td className="td font-medium text-center">{row.name}</td>
              <td className="td font-bold text-center">{row.total || 0}</td>
              <td className="td text-center">{row['In Followup'] || 0}</td>
              <td className="td text-center">{row.Meeting || 0}</td>
              <td className="td text-center">{row['Site Visit'] || 0}</td>
              <td className="td text-center">{row['Quotation sent'] || 0}</td>
              <td className="td text-center">{row['Not Interested'] || 0}</td>
            </tr>
          ))}
          {rows.length > 0 && (
            <tr className="bg-graphite-100 font-bold">
              <td className="td text-center">TOTAL</td>
              <td className="td text-center">{totals.total}</td>
              <td className="td text-center">{totals.follow}</td>
              <td className="td text-center">{totals.meeting}</td>
              <td className="td text-center">{totals.site}</td>
              <td className="td text-center">{totals.quote}</td>
              <td className="td text-center">{totals.notInt}</td>
            </tr>
          )}
        </tbody>
      </table>
      {rows.length === 0 && <EmptyState title="No data" />}
    </div>
  );
}

export function Comparison() {
  const [year, setYear] = useState('');
  const [months, setMonths] = useState('');
  const [category, setCategory] = useState('');
  const [workAction, setWorkAction] = useState('');
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    const ctrl = new AbortController();
    setLoading(true);
    setError('');
    const params: Record<string, string | number> = {};
    if (months) params.months = Number(months);
    else if (year) params.year = Number(year);
    if (category) params.category = category;
    if (workAction) params.work_action = workAction;
    api.get('/dashboard/comparison', { params, signal: ctrl.signal })
      .then((r) => setData(r.data))
      .catch((e: any) => {
        if (e?.code === 'ERR_CANCELED') return;
        setError(e?.response?.data?.detail || 'Could not load comparison');
      })
      .finally(() => setLoading(false));
    return () => ctrl.abort();
  }, [year, months, category, workAction]);

  const current = data?.current;
  const tiles = current ? [
    { label: 'Total Leads', value: current.leads || 0, bg: 'bg-[#1e3a5f]' },
    { label: 'Total Lead Value', value: inr(current.lead_value), bg: 'bg-[#3F6212]', isText: true },
    { label: 'In Followup', value: actionCount(current, 'In Followup'), bg: 'bg-[#c0392b]' },
    { label: 'Meeting', value: actionCount(current, 'Meeting'), bg: 'bg-[#0284c7]' },
    { label: 'Site Visit', value: actionCount(current, 'Site Visit'), bg: 'bg-[#65A30D]' },
    { label: 'Quotation Sent', value: actionCount(current, 'Quotation sent'), bg: 'bg-[#2F9E44]' },
    { label: 'Not Interested', value: actionCount(current, 'Not Interested'), bg: 'bg-[#7b241c]' },
    { label: 'Assigned', value: actionCount(current, 'Assigned'), bg: 'bg-[#0e7490]' },
    { label: 'New Lead', value: actionCount(current, 'New Lead'), bg: 'bg-[#1c2833]' },
  ] : [];
  const sourceRows = current?.by_source || [];
  const productRows = current?.by_product || [];
  const sourcePie = sourceRows.filter((row: any) => row.total > 0).map((row: any) => ({ name: row.name, value: row.total }));
  const productPie = productRows.filter((row: any) => row.total > 0).map((row: any) => ({ name: row.name, value: row.total }));

  return (
    <div className="space-y-5">
      <PageHeader
        title="Comparison"
        subtitle="Same dashboard as admin. Change a filter and the cards, tables, and pie charts update."
      />

      <div className="card p-4">
        <div className="text-[11px] font-semibold uppercase tracking-wide text-graphite-500 mb-3">Filters</div>
        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-3">
          <div>
            <label className="text-xs font-medium text-graphite-600">Year</label>
            <select className="input mt-1" value={year} onChange={(e) => { setYear(e.target.value); setMonths(''); }}>
              <option value="">This year vs last year</option>
              {(data?.years || []).map((y: number) => <option key={y} value={y}>{y}</option>)}
            </select>
          </div>
          <div>
            <label className="text-xs font-medium text-graphite-600">Recent months</label>
            <select className="input mt-1" value={months} onChange={(e) => { setMonths(e.target.value); setYear(''); }}>
              <option value="">Use the year above</option>
              {MONTH_OPTIONS.map((n) => <option key={n} value={n}>Last {n} months</option>)}
            </select>
          </div>
          <div>
            <label className="text-xs font-medium text-graphite-600">Category</label>
            <select className="input mt-1" value={category} onChange={(e) => setCategory(e.target.value)}>
              <option value="">All categories</option>
              {(data?.categories || ['A+ (Immediate)', 'A (3-6 months)', 'B (1 year)', 'C (plan stage)']).map((name: string) => (
                <option key={name} value={name}>{name}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="text-xs font-medium text-graphite-600">Work action</label>
            <select className="input mt-1" value={workAction} onChange={(e) => setWorkAction(e.target.value)}>
              <option value="">All actions</option>
              {(data?.work_actions || ['In Followup', 'Meeting', 'Quotation sent']).map((name: string) => (
                <option key={name} value={name}>{name}</option>
              ))}
            </select>
          </div>
        </div>
        {data && (
          <p className="text-xs text-graphite-500 mt-3">
            Dashboard for {data.current_label} ({current?.from} to {current?.to}), compared with {data.previous_label} ({data.previous?.from} to {data.previous?.to})
            {loading ? ' · updating…' : ''}
          </p>
        )}
      </div>

      {error && <div className="text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg px-3 py-2">{error}</div>}
      {loading && !data ? <Spinner /> : data && (
        <>
          <div className="grid lg:grid-cols-2 gap-5">
            <div className="space-y-5">
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                {tiles.map((tile) => (
                  <div key={tile.label} className={`${tile.bg} text-white rounded-lg px-3 py-3 shadow-sm`}>
                    <div className="text-[10px] uppercase tracking-wide opacity-90 font-semibold leading-tight">{tile.label}</div>
                    <div className={`${tile.isText ? 'text-sm sm:text-base' : 'text-2xl'} font-bold mt-1 tabular-nums break-all`}>{tile.value}</div>
                  </div>
                ))}
              </div>
              <Card title="Leads by Source">
                <MixTable rows={sourceRows} />
              </Card>
            </div>
            <Card title="Leads by Source">
              <MixPie rows={sourcePie} />
            </Card>
          </div>
          <div className="grid xl:grid-cols-[1.4fr_1fr] gap-5">
            <Card title="Leads by Product">
              <MixTable rows={productRows} />
            </Card>
            <Card title="Leads by Product">
              <MixPie rows={productPie} />
            </Card>
          </div>
        </>
      )}
    </div>
  );
}
