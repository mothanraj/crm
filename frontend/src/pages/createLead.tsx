import { FormEvent, ReactNode, useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { api } from '../services/api';
import { PageHeader } from '../components/ui';

const PRODUCTS = [
  'Two Post Stack Parking',
  'Four Post Stack Parking',
  'Pit Stack Parking',
  'Puzzle Parking',
  'Pit Puzzle Parking',
  'Tower Parking',
  'Shuttle Parking',
  'Car Elevator',
  'ASRS Parking',
] as const;

const SOURCES = [
  'Google Ads',
  'SEO',
  'Direct Call',
  'Facebook/Instagram',
  'India Mart',
  'Referral',
  'WhatsApp',
  'Email Campaign',
  'Email Enquiry',
  'Others',
  'Expo/Stall',
] as const;

const PREFERRED_EMPLOYEES = ['abinaya', 'estarengineers', 'karthick', 'mothanraj', 'ramkumar'];

const EMAIL_RE = /^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$/;

function digitsOnly(raw: string): string {
  let d = (raw || '').replace(/\D/g, '');
  if (d.startsWith('00')) d = d.slice(2);
  if (d.length === 12 && d.startsWith('91') && '6789'.includes(d[2])) d = d.slice(2);
  else if (d.length === 11 && d.startsWith('0') && '6789'.includes(d[1])) d = d.slice(1);
  return d;
}

function isValidPhone(raw: string): boolean {
  return /^[6-9]\d{9}$/.test(digitsOnly(raw));
}

/** Any whole number ≥ 2 for these; even ≥ 2 for stack / tower products. Blank allowed. */
const ODD_OK_PRODUCTS = new Set([
  'Puzzle Parking',
  'Pit Puzzle Parking',
  'Shuttle Parking',
  'Car Elevator',
  'ASRS Parking',
]);

function validateCars(raw: string, product: string): string | null {
  const text = (raw || '').trim();
  if (!text) return null;
  if (!/^\d+$/.test(text)) return 'You have entered wrong No. of Cars — numbers only, whole number ≥ 2';
  const n = Number(text);
  if (!Number.isInteger(n) || n < 2) return 'You have entered wrong No. of Cars — whole number starting at 2';
  if (!product || ODD_OK_PRODUCTS.has(product)) return null;
  if (n % 2 !== 0) {
    return 'You have entered wrong No. of Cars — even numbers only for Tower / Two Post / Four Post / Pit Stack Parking';
  }
  return null;
}

type FormState = {
  enquiry_date: string;
  customer_name: string;
  company_name: string;
  contact_number: string;
  city: string;
  number_of_cars: string;
  source_name: string;
  product_name: string;
  email: string;
  primary_employee_id: string;
};

const emptyForm = (): FormState => ({
  enquiry_date: new Date().toISOString().slice(0, 10),
  customer_name: '',
  company_name: '',
  contact_number: '',
  city: '',
  number_of_cars: '',
  source_name: '',
  product_name: '',
  email: '',
  primary_employee_id: '',
});

function sortEmployees(list: Array<{ id: string; name: string }>) {
  const rank = (name: string) => {
    const n = name.trim().toLowerCase().replace(/[\s._-]+/g, '');
    const idx = PREFERRED_EMPLOYEES.findIndex((p) => n === p || n.includes(p) || p.includes(n));
    return idx === -1 ? 1000 : idx;
  };
  return [...list].sort((a, b) => {
    const ra = rank(a.name);
    const rb = rank(b.name);
    if (ra !== rb) return ra - rb;
    return a.name.localeCompare(b.name);
  });
}

export function CreateLead() {
  const navigate = useNavigate();
  const [form, setForm] = useState<FormState>(emptyForm);
  const [employees, setEmployees] = useState<Array<{ id: string; name: string }>>([]);
  const [empLoadError, setEmpLoadError] = useState('');
  const [busy, setBusy] = useState(false);
  const [popup, setPopup] = useState<{ title: string; points: string[]; ok?: boolean } | null>(null);
  const [createdLead, setCreatedLead] = useState<{
    id: string;
    enquiry_number: string;
    customer_name: string;
    assigned_to: string;
  } | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setEmpLoadError('');
      const normalize = (rows: any[]): Array<{ id: string; name: string }> =>
        (rows || [])
          .filter((e: any) => e && e.is_active !== false && String(e.role || 'EMPLOYEE').toUpperCase() !== 'ADMIN')
          .map((e: any) => ({ id: String(e.id), name: String(e.name || '').trim() }))
          .filter((e) => e.id && e.name);

      // Load both sources; use whichever returns people (masters is what other pages use).
      const settled = await Promise.allSettled([
        api.get('/masters'),
        api.get('/employees'),
      ]);
      if (cancelled) return;

      let list: Array<{ id: string; name: string }> = [];
      for (const result of settled) {
        if (result.status !== 'fulfilled') continue;
        const data = result.value.data;
        const fromMasters = normalize(data?.employees || []);
        const fromEmployees = normalize(Array.isArray(data) ? data : []);
        const merged = [...fromMasters, ...fromEmployees];
        if (merged.length > list.length) list = merged;
      }
      // Dedupe by id
      const byId = new Map(list.map((e) => [e.id, e]));
      list = sortEmployees([...byId.values()]);
      setEmployees(list);
      if (!list.length) {
        const apiDown = settled.every((r) => r.status === 'rejected');
        setEmpLoadError(
          apiDown
            ? 'Could not reach the server to load employees. Check the backend is running.'
            : 'No employees found. Add them under Employees, or leave blank for round-robin.',
        );
      }
    })();
    return () => { cancelled = true; };
  }, []);

  const set = (key: keyof FormState, value: string) => {
    setForm((f) => ({ ...f, [key]: value }));
  };

  const collectErrors = (f: FormState): string[] => {
    const errors: string[] = [];
    const phone = f.contact_number.trim();
    const email = f.email.trim();

    if (phone && !isValidPhone(phone)) {
      errors.push('You have entered wrong Contact No. — 10-digit Indian mobile starting with 6–9');
    }
    if (email && !EMAIL_RE.test(email)) {
      errors.push('You have entered wrong Email');
    }
    if (!phone && !email) {
      errors.push('Enter a phone number or an email (either one is enough)');
    }
    if (f.source_name && !(SOURCES as readonly string[]).includes(f.source_name)) {
      errors.push('You have entered wrong Lead Source');
    }
    if (f.product_name && !(PRODUCTS as readonly string[]).includes(f.product_name)) {
      errors.push('You have entered wrong Product / Type');
    }
    const carErr = validateCars(f.number_of_cars, f.product_name);
    if (carErr) errors.push(carErr);
    if (f.primary_employee_id && !employees.some((e) => e.id === f.primary_employee_id)) {
      errors.push('You have entered wrong Select employee');
    }
    return errors;
  };

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    const errors = collectErrors(form);
    if (errors.length) {
      setPopup({
        title: 'You have entered wrong details',
        points: errors,
      });
      return;
    }
    setBusy(true);
    try {
      const payload: Record<string, string | null> = {
        enquiry_date: form.enquiry_date || null,
        customer_name: form.customer_name.trim(),
        company_name: form.company_name.trim(),
        contact_number: form.contact_number.trim(),
        city: form.city.trim(),
        number_of_cars: form.number_of_cars.trim(),
        source_name: form.source_name,
        product_name: form.product_name,
        email: form.email.trim(),
        primary_employee_id: form.primary_employee_id || null,
      };
      const { data } = await api.post('/leads', payload);
      const empName = employees.find((emp) => emp.id === data?.primary_employee_id)?.name
        || (data?.primary_employee_id ? 'selected employee' : 'round-robin');
      const enq = String(data?.enquiry_number || '').trim() || '—';
      const leadName = String(data?.customer_name || form.customer_name || '').trim() || '—';
      setForm(emptyForm());
      setCreatedLead({
        id: String(data?.id || ''),
        enquiry_number: enq,
        customer_name: leadName,
        assigned_to: empName,
      });
      setPopup({
        title: 'Lead created',
        points: [
          `Enquiry no: ${enq}`,
          `Lead name: ${leadName}`,
          `Assigned to: ${empName}`,
        ],
        ok: true,
      });
    } catch (err: any) {
      const d = err?.response?.data?.detail;
      const points = typeof d === 'string'
        ? d.split(/\s*·\s*|\n+/).map((s: string) => s.trim()).filter(Boolean)
        : ['Could not create lead'];
      setPopup({
        title: 'You have entered wrong details',
        points,
      });
    } finally {
      setBusy(false);
    }
  };

  const field = (label: string, children: ReactNode, hint?: string) => (
    <label className="block min-w-0">
      <span className="text-xs font-semibold text-graphite-600 uppercase tracking-wide">{label}</span>
      <div className="mt-1">{children}</div>
      {hint && <div className="text-[11px] text-graphite-400 mt-1">{hint}</div>}
    </label>
  );

  return (
    <div className="space-y-4">
      <PageHeader
        title="Create Lead"
        subtitle="Phone or email alone is enough. Other fields are optional — wrong filled values show a popup. Enquiry number is assigned automatically after save."
        actions={<Link to="/leads" className="btn-secondary text-sm">Back to Leads</Link>}
      />

      {createdLead && (
        <div className="rounded-xl border border-emerald-300 bg-emerald-50 px-4 py-4 sm:px-5">
          <div className="text-sm font-semibold uppercase tracking-wide text-emerald-800">Lead created — assigned enquiry number</div>
          <div className="mt-2 grid sm:grid-cols-2 gap-2">
            <div className="rounded-lg bg-white/80 border border-emerald-200 px-3 py-2">
              <div className="text-[11px] uppercase tracking-wide text-emerald-700/80 font-semibold">Enquiry no</div>
              <div className="text-xl font-bold text-emerald-900 tabular-nums mt-0.5">{createdLead.enquiry_number}</div>
            </div>
            <div className="rounded-lg bg-white/80 border border-emerald-200 px-3 py-2">
              <div className="text-[11px] uppercase tracking-wide text-emerald-700/80 font-semibold">Lead name</div>
              <div className="text-xl font-bold text-emerald-900 mt-0.5 break-words">{createdLead.customer_name}</div>
            </div>
          </div>
          <p className="text-sm text-emerald-800 mt-2">Assigned to {createdLead.assigned_to}.</p>
          <div className="flex flex-wrap gap-2 mt-3">
            {createdLead.id && (
              <button type="button" className="btn-primary text-sm" onClick={() => navigate(`/leads/${createdLead.id}`)}>
                Open this lead
              </button>
            )}
            <button type="button" className="btn-secondary text-sm" onClick={() => setCreatedLead(null)}>
              Create another
            </button>
          </div>
        </div>
      )}

      <form onSubmit={onSubmit} className="card p-4 sm:p-6 space-y-4" noValidate>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {field('Enq no', (
            <input
              className="input w-full bg-graphite-50 text-graphite-500"
              value="Auto-assigned"
              readOnly
              disabled
              title="Enquiry number is assigned automatically"
            />
          ), 'Assigned automatically when the lead is saved')}
          {field('Date Received', (
            <input type="date" className="input w-full" value={form.enquiry_date} onChange={(e) => set('enquiry_date', e.target.value)} />
          ))}
          {field('Lead Name / Full Name', (
            <input className="input w-full" value={form.customer_name} onChange={(e) => set('customer_name', e.target.value)} />
          ))}
          {field('Company / Organisation', (
            <input className="input w-full" value={form.company_name} onChange={(e) => set('company_name', e.target.value)} />
          ))}
          {field('Contact No.', (
            <input
              className="input w-full"
              inputMode="tel"
              value={form.contact_number}
              onChange={(e) => set('contact_number', e.target.value)}
            />
          ))}
          {field('City', (
            <input className="input w-full" value={form.city} onChange={(e) => set('city', e.target.value)} />
          ))}
          {field('No. of Cars', (
            <input
              className="input w-full"
              inputMode="numeric"
              value={form.number_of_cars}
              onChange={(e) => set('number_of_cars', e.target.value.replace(/\D/g, ''))}
            />
          ))}
          {field('Lead Source', (
            <select className="input w-full" value={form.source_name} onChange={(e) => set('source_name', e.target.value)}>
              <option value="">Select source</option>
              {SOURCES.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          ))}
          {field('Product / Type', (
            <select className="input w-full" value={form.product_name} onChange={(e) => set('product_name', e.target.value)}>
              <option value="">Select product</option>
              {PRODUCTS.map((p) => <option key={p} value={p}>{p}</option>)}
            </select>
          ))}
          {field('Email', (
            <input
              type="email"
              className="input w-full"
              value={form.email}
              onChange={(e) => set('email', e.target.value)}
            />
          ))}
          {field('Select employee', (
            <select className="input w-full" value={form.primary_employee_id} onChange={(e) => set('primary_employee_id', e.target.value)}>
              <option value="">Auto assign (round-robin)</option>
              {employees.map((emp) => (
                <option key={emp.id} value={emp.id}>{emp.name}</option>
              ))}
            </select>
          ), empLoadError || 'Leave blank to auto-assign by round-robin')}
        </div>

        <div className="flex flex-wrap gap-3 pt-2">
          <button type="submit" className="btn-primary" disabled={busy}>
            {busy ? 'Creating…' : 'Create Lead'}
          </button>
          <button type="button" className="btn-secondary" disabled={busy} onClick={() => setForm(emptyForm())}>
            Clear
          </button>
        </div>
      </form>

      {popup && (
        <div className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-4" onClick={() => setPopup(null)}>
          <div className="bg-white rounded-xl shadow-xl max-w-md w-full p-5" onClick={(e) => e.stopPropagation()}>
            <h3 className={`text-lg font-semibold ${popup.ok ? 'text-emerald-800' : 'text-red-700'}`}>{popup.title}</h3>
            <ul className="mt-3 space-y-2 list-none">
              {popup.points.map((point, i) => (
                <li
                  key={`${i}-${point}`}
                  className={`flex gap-2 text-sm font-medium ${popup.ok ? 'text-emerald-800' : 'text-red-600'}`}
                >
                  <span className="shrink-0">{i + 1}.</span>
                  <span>{point}</span>
                </li>
              ))}
            </ul>
            <div className="flex justify-end mt-5">
              <button type="button" className="btn-primary" onClick={() => setPopup(null)}>OK</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
