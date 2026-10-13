import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../services/api';
import { Card, EmptyState, PageHeader, Spinner, fmtDMY } from '../components/ui';

function todayLocalISO(): string {
  const d = new Date();
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

function fmtStamp(iso: string | null | undefined): string {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  return d.toLocaleString('en-IN', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    hour12: true,
  });
}

const DOT_COLOR: Record<string, string> = {
  'New leads': '#2563EB',
  'In Followup': '#E8890C',
  Meeting: '#38BDF8',
  'Site Visit': '#0D9488',
  'Quotation sent': '#EAB308',
  Converted: '#16A34A',
};

const TILE_ORDER = ['New leads', 'In Followup', 'Quotation sent', 'Meeting', 'Site Visit', 'Converted'];

const TILE_KEY: Record<string, string> = {
  'New leads': 'new_leads',
  'In Followup': 'followup',
  Meeting: 'meeting',
  'Site Visit': 'site_visit',
  'Quotation sent': 'quotation',
  Converted: 'converted',
};

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

export function EmployeeDailyReport() {
  const today = todayLocalISO();
  const [day, setDay] = useState(today);
  const [stats, setStats] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [remarks, setRemarks] = useState<any[]>([]);
  const [remarksLoading, setRemarksLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [draft, setDraft] = useState('');
  const [saving, setSaving] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editText, setEditText] = useState('');
  const [formError, setFormError] = useState('');
  const [editingTile, setEditingTile] = useState<string | null>(null);
  const [tileValue, setTileValue] = useState('');
  const [tileBusy, setTileBusy] = useState(false);
  const [tileError, setTileError] = useState('');
  const [noteEditing, setNoteEditing] = useState<string | null>(null);
  const [noteText, setNoteText] = useState('');
  const [noteBusy, setNoteBusy] = useState(false);
  const [noteError, setNoteError] = useState('');
  const [pdfBusy, setPdfBusy] = useState(false);

  const clampDay = (v: string) => {
    if (!v) return v;
    return v > today ? today : v;
  };

  const load = (d: string) => {
    if (!d) return;
    setLoading(true);
    setError('');
    setRemarksLoading(true);
    const statsP = api.get('/dashboard/daily-report', { params: { day: d } }).then(
      (r) => setStats(r.data),
      (e: any) => setError(e?.response?.data?.detail || 'Could not load the daily report'),
    );
    const remarksP = api.get('/dashboard/daily-remarks', { params: { day: d } }).then(
      (r) => setRemarks(Array.isArray(r.data?.remarks) ? r.data.remarks : []),
      () => setRemarks([]),
    );
    Promise.allSettled([statsP, remarksP]).finally(() => {
      setLoading(false);
      setRemarksLoading(false);
    });
  };

  useEffect(() => { load(day); }, [day]);

  const countFor = (label: string) => {
    if (label === 'New leads') return Number(stats?.new_leads_count ?? 0);
    const row = (stats?.progress || []).find((r: any) => r.label === label);
    return Number(row?.count ?? 0);
  };

  const overrides: Record<string, number> = stats?.overrides || {};
  const effectiveFor = (label: string) => {
    const key = TILE_KEY[label];
    const v = overrides[key];
    return v == null ? countFor(label) : Number(v);
  };
  const isEdited = (label: string) => overrides[TILE_KEY[label]] != null;

  const saveTile = async (label: string) => {
    const key = TILE_KEY[label];
    const n = Number(tileValue);
    if (!Number.isInteger(n) || n < 0) {
      setTileError('Enter a whole number 0 or above.');
      return;
    }
    setTileBusy(true);
    setTileError('');
    try {
      const { data } = await api.put('/dashboard/daily-tiles', { day, tile: key, count: n });
      setStats((cur: any) => (cur ? { ...cur, overrides: { ...(cur.overrides || {}), [data.tile]: data.count } } : cur));
      setEditingTile(null);
      setTileValue('');
    } catch (e: any) {
      setTileError(e?.response?.data?.detail || 'Could not save the count');
    } finally {
      setTileBusy(false);
    }
  };

  const revertTile = async (label: string) => {
    const key = TILE_KEY[label];
    setTileBusy(true);
    setTileError('');
    try {
      await api.delete('/dashboard/daily-tiles', { params: { day, tile: key } });
      setStats((cur: any) => {
        if (!cur) return cur;
        const next = { ...(cur.overrides || {}) };
        delete next[key];
        return { ...cur, overrides: next };
      });
      setEditingTile(null);
      setTileValue('');
    } catch (e: any) {
      setTileError(e?.response?.data?.detail || 'Could not revert the count');
    } finally {
      setTileBusy(false);
    }
  };

  const onPdf = async () => {
    setPdfBusy(true);
    setError('');
    try {
      await downloadBlob('/dashboard/daily-report/pdf', `daily-report-${day}.pdf`, { day });
    } catch (e: any) {
      setError(e?.message || 'PDF download failed');
    } finally {
      setPdfBusy(false);
    }
  };

  const saveRemark = async () => {
    const text = draft.trim();
    if (!text) {
      setFormError('Type what you did before saving.');
      return;
    }
    setSaving(true);
    setFormError('');
    try {
      const { data } = await api.post('/dashboard/daily-remarks', { day, remarks: text });
      setRemarks((cur) => [data, ...cur]);
      setDraft('');
      setShowForm(false);
    } catch (e: any) {
      setFormError(e?.response?.data?.detail || 'Could not save the remark');
    } finally {
      setSaving(false);
    }
  };

  const saveEdit = async (id: string) => {
    const text = editText.trim();
    if (!text) {
      setFormError('Remark cannot be empty.');
      return;
    }
    setSaving(true);
    setFormError('');
    try {
      const { data } = await api.put(`/dashboard/daily-remarks/${id}`, { remarks: text });
      setRemarks((cur) => cur.map((r) => (r.id === id ? data : r)));
      setEditingId(null);
      setEditText('');
    } catch (e: any) {
      setFormError(e?.response?.data?.detail || 'Could not update the remark');
    } finally {
      setSaving(false);
    }
  };

  const deleteRemark = async (id: string) => {
    if (!window.confirm('Delete this remark?')) return;
    setSaving(true);
    try {
      await api.delete(`/dashboard/daily-remarks/${id}`);
      setRemarks((cur) => cur.filter((r) => r.id !== id));
    } catch (e: any) {
      setFormError(e?.response?.data?.detail || 'Could not delete the remark');
    } finally {
      setSaving(false);
    }
  };

  const newLeads = Array.isArray(stats?.new_leads) ? stats.new_leads : [];
  const generalRemarks = remarks.filter((r: any) => !r.tile);
  const tileNoteFor = (label: string) => remarks.find((r: any) => r.tile === TILE_KEY[label]);

  const saveTileNote = async (label: string) => {
    const text = noteText.trim();
    if (!text) {
      setNoteError('Type a note before saving.');
      return;
    }
    const key = TILE_KEY[label];
    const existing = remarks.find((r: any) => r.tile === key);
    setNoteBusy(true);
    setNoteError('');
    try {
      if (existing) {
        const { data } = await api.put(`/dashboard/daily-remarks/${existing.id}`, { remarks: text });
        setRemarks((cur) => cur.map((r) => (r.id === existing.id ? data : r)));
      } else {
        const { data } = await api.post('/dashboard/daily-remarks', { day, remarks: text, tile: key });
        setRemarks((cur) => [data, ...cur]);
      }
      setNoteEditing(null);
      setNoteText('');
    } catch (e: any) {
      setNoteError(e?.response?.data?.detail || 'Could not save the note');
    } finally {
      setNoteBusy(false);
    }
  };

  const deleteTileNote = async (label: string) => {
    const key = TILE_KEY[label];
    const existing = remarks.find((r: any) => r.tile === key);
    if (!existing) {
      setNoteEditing(null);
      setNoteText('');
      return;
    }
    setNoteBusy(true);
    setNoteError('');
    try {
      await api.delete(`/dashboard/daily-remarks/${existing.id}`);
      setRemarks((cur) => cur.filter((r) => r.id !== existing.id));
      setNoteEditing(null);
      setNoteText('');
    } catch (e: any) {
      setNoteError(e?.response?.data?.detail || 'Could not delete the note');
    } finally {
      setNoteBusy(false);
    }
  };

  return (
    <div className="space-y-5">
      <PageHeader
        title="Daily Report"
        subtitle="Pick a date to see that day's new leads and logged work, plus your own remarks."
        actions={(
          <button type="button" className="btn-secondary w-full sm:w-auto" disabled={pdfBusy || !stats} onClick={onPdf}>
            {pdfBusy ? 'Creating PDF…' : 'Download PDF'}
          </button>
        )}
      />

      <Card title="Choose date">
        <label className="text-sm block w-full sm:max-w-[220px]">Date
          <input
            type="date"
            className="input mt-1"
            value={day}
            max={today}
            onChange={(e) => setDay(clampDay(e.target.value))}
          />
        </label>
        <p className="text-xs text-graphite-500 mt-2">
          Showing {fmtDMY(day)}. Future dates are not allowed.
        </p>
      </Card>

      {error && <div className="bg-red-50 border border-red-200 text-red-700 text-sm rounded-xl px-4 py-3">{error}</div>}

      {loading && !stats ? <Spinner /> : stats && (
        <>
          <Card title={`Today's activity — ${fmtDMY(day)}`}>
            <ul className="divide-y divide-graphite-100 -my-1">
              {TILE_ORDER.map((label) => (
                <li key={label} className="py-3 first:pt-1 last:pb-1 min-h-[3rem]">
                  <div className="grid grid-cols-[minmax(0,1fr)_3rem_4rem_5rem] items-center gap-2 sm:gap-3">
                    <div className="flex items-center gap-2.5 min-w-0">
                      <span
                        aria-hidden
                        className="w-2.5 h-2.5 rounded-full shrink-0 ring-1 ring-black/10"
                        style={{ backgroundColor: DOT_COLOR[label] }}
                      />
                      <div className="min-w-0">
                        <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5">
                          <span className="text-sm font-semibold text-graphite-800">{label}</span>
                          {isEdited(label) && (
                            <span className="text-[10px] font-bold uppercase tracking-wide text-amber-700 bg-amber-50 ring-1 ring-amber-200 rounded-full px-2 py-px">edited</span>
                          )}
                        </div>
                        {noteEditing !== label && tileNoteFor(label) && (
                          <p className="text-xs text-graphite-500 mt-0.5 line-clamp-2 break-words">{tileNoteFor(label)?.remarks}</p>
                        )}
                      </div>
                    </div>
                    <div className="text-xl font-bold tabular-nums text-graphite-900 text-center">{effectiveFor(label)}</div>
                    <button
                      type="button"
                      title={`Edit ${label} count`}
                      aria-label={`Edit ${label} count`}
                      className="btn-secondary !px-0 !py-1.5 !min-h-0 text-xs w-16 inline-flex justify-center text-center"
                      onClick={() => { setEditingTile(editingTile === label ? null : label); setTileValue(String(effectiveFor(label))); setTileError(''); }}
                    >
                      Edit
                    </button>
                    <button
                      type="button"
                      title={tileNoteFor(label) ? `Edit ${label} note` : `Add a note for ${label}`}
                      aria-label={tileNoteFor(label) ? `Edit ${label} note` : `Add ${label} note`}
                      className="btn-secondary !px-0 !py-1.5 !min-h-0 text-xs w-20 inline-flex justify-center text-center"
                      onClick={() => { setNoteEditing(noteEditing === label ? null : label); setNoteText(tileNoteFor(label)?.remarks || ''); setNoteError(''); }}
                    >
                      {tileNoteFor(label) ? 'Note' : '+ Note'}
                    </button>
                  </div>
                  {editingTile === label && (
                    <div className="mt-2 flex flex-col sm:flex-row sm:items-center gap-2 sm:pl-5">
                      <input
                        type="number"
                        min={0}
                        step={1}
                        inputMode="numeric"
                        aria-label={`${label} count`}
                        className="input !py-1.5 !min-h-0 max-w-[140px] tabular-nums"
                        value={tileValue}
                        autoFocus
                        onChange={(e) => setTileValue(e.target.value)}
                      />
                      <div className="flex gap-1.5">
                        <button type="button" className="btn-primary !px-3 !py-1.5 !min-h-0 text-xs" disabled={tileBusy} onClick={() => saveTile(label)}>
                          {tileBusy ? '…' : 'Save'}
                        </button>
                        {isEdited(label) && (
                          <button type="button" className="btn-secondary !px-3 !py-1.5 !min-h-0 text-xs" disabled={tileBusy} onClick={() => revertTile(label)}>
                            Revert
                          </button>
                        )}
                        <button type="button" className="btn-secondary !px-3 !py-1.5 !min-h-0 text-xs" disabled={tileBusy} onClick={() => { setEditingTile(null); setTileValue(''); }}>
                          Cancel
                        </button>
                      </div>
                    </div>
                  )}
                  {noteEditing === label && (
                    <div className="mt-2 sm:pl-5">
                      <textarea
                        className="input !py-1.5 !text-sm min-h-[60px] max-w-[520px]"
                        value={noteText}
                        maxLength={2000}
                        autoFocus
                        placeholder={`Note for ${label} (optional)`}
                        aria-label={`${label} note`}
                        onChange={(e) => setNoteText(e.target.value)}
                      />
                      {noteError && <p className="text-xs text-red-700 mt-1">{noteError}</p>}
                      <div className="flex gap-1.5 mt-1.5">
                        <button type="button" className="btn-primary !px-3 !py-1.5 !min-h-0 text-xs" disabled={noteBusy} onClick={() => saveTileNote(label)}>
                          {noteBusy ? '…' : 'Save note'}
                        </button>
                        {tileNoteFor(label) && (
                          <button type="button" className="btn-secondary !px-3 !py-1.5 !min-h-0 text-xs" disabled={noteBusy} onClick={() => deleteTileNote(label)}>
                            Delete
                          </button>
                        )}
                        <button type="button" className="btn-secondary !px-3 !py-1.5 !min-h-0 text-xs" disabled={noteBusy} onClick={() => { setNoteEditing(null); setNoteText(''); }}>
                          Cancel
                        </button>
                      </div>
                    </div>
                  )}
                </li>
              ))}
            </ul>
            {tileError && <p className="text-sm text-red-700 mt-2">{tileError}</p>}

            <div className="mt-4 border-t border-graphite-100 pt-3">
              <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
                <h3 className="text-sm font-semibold text-graphite-800">Others ({generalRemarks.length})</h3>
                <button
                  type="button"
                  className="btn-primary !px-0 !py-1.5 !min-h-0 text-xs w-20 inline-flex justify-center text-center"
                  onClick={() => { setShowForm((s) => !s); setFormError(''); }}
                  aria-label="Add remark"
                >
                  {showForm ? '− Close' : '+ Add'}
                </button>
              </div>
              {showForm && (
                <div className="rounded-xl border border-graphite-200 p-3 mb-3 bg-graphite-50">
                  <label className="text-sm block">What did you do?
                    <textarea
                      className="input mt-1 min-h-[90px]"
                      placeholder="e.g. Called 5 customers, sent 2 quotations, visited 1 site…"
                      value={draft}
                      maxLength={2000}
                      onChange={(e) => setDraft(e.target.value)}
                    />
                  </label>
                  {formError && <p className="text-sm text-red-700 mt-2">{formError}</p>}
                  <div className="flex flex-col sm:flex-row gap-2 mt-3">
                    <button type="button" className="btn-primary w-full sm:w-auto" disabled={saving} onClick={saveRemark}>
                      {saving ? 'Saving…' : 'Save remark'}
                    </button>
                    <button type="button" className="btn-secondary w-full sm:w-auto" disabled={saving} onClick={() => { setShowForm(false); setDraft(''); }}>
                      Cancel
                    </button>
                  </div>
                </div>
              )}
              {remarksLoading ? <Spinner /> : generalRemarks.length === 0 ? (
                <EmptyState title="Nothing else noted this day" hint="Tap + Add above to note down anything else." />
              ) : (
                <ul className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-2">
                  {generalRemarks.map((r: any) => (
                    <li key={r.id} className="rounded-lg border border-graphite-200 bg-graphite-50 px-3 py-2.5 shadow-sm min-w-0">
                      {editingId === r.id ? (
                        <div>
                          <textarea
                            className="input min-h-[80px]"
                            value={editText}
                            maxLength={2000}
                            onChange={(e) => setEditText(e.target.value)}
                          />
                          <div className="flex flex-col sm:flex-row gap-2 mt-2">
                            <button type="button" className="btn-primary w-full sm:w-auto" disabled={saving} onClick={() => saveEdit(r.id)}>
                              {saving ? 'Saving…' : 'Update'}
                            </button>
                            <button type="button" className="btn-secondary w-full sm:w-auto" disabled={saving} onClick={() => { setEditingId(null); setEditText(''); }}>
                              Cancel
                            </button>
                          </div>
                        </div>
                      ) : (
                        <>
                          <p className="text-sm text-graphite-900 whitespace-pre-wrap break-words">{r.remarks}</p>
                          <div className="flex flex-wrap items-center justify-between gap-2 mt-1.5">
                            <span className="text-xs text-graphite-400 tabular-nums">{fmtStamp(r.created_at)}</span>
                            <span className="flex gap-2">
                              <button
                                type="button"
                                className="btn-secondary !px-3 !py-1.5 !min-h-0 text-xs"
                                disabled={saving}
                                onClick={() => { setEditingId(r.id); setEditText(r.remarks || ''); setShowForm(false); }}
                              >
                                Edit
                              </button>
                              <button
                                type="button"
                                className="btn-secondary !px-3 !py-1.5 !min-h-0 text-xs !text-red-700 !border-red-200"
                                disabled={saving}
                                onClick={() => deleteRemark(r.id)}
                              >
                                Delete
                              </button>
                            </span>
                          </div>
                        </>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </Card>

          <Card title={`New leads — ${fmtDMY(day)} (${newLeads.length})`}>
            {newLeads.length === 0 ? (
              <EmptyState title="No new leads this day" hint="Leads assigned to you on this date will appear here." />
            ) : (
              <div className="drag-scroll overflow-x-auto -mx-4 px-4 sm:mx-0 sm:px-0">
                <table className="w-full min-w-[520px] sm:min-w-0 text-sm">
                  <thead className="bg-graphite-50">
                    <tr>
                      <th className="th whitespace-nowrap">Enquiry</th>
                      <th className="th">Customer</th>
                      <th className="th">Company / City</th>
                    </tr>
                  </thead>
                  <tbody>
                    {newLeads.map((l: any) => (
                      <tr key={l.id} className="hover:bg-brand-50/50">
                        <td className="td font-semibold text-brand-700 whitespace-nowrap">
                          <Link to={`/leads/${l.id}`}>{l.enquiry_number}</Link>
                        </td>
                        <td className="td break-words">{l.customer_name || '—'}</td>
                        <td className="td break-words">
                          {[l.company_name, l.city].filter(Boolean).join(' · ') || '—'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        </>
      )}
    </div>
  );
}
