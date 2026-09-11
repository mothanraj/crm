import React from 'react';

/* ---------- status / sla color maps (single source of truth for badges) ---------- */
const STATUS_STYLES: Record<string, string> = {
  'New Lead': 'bg-sky-100 text-sky-800 ring-sky-200',
  'Assigned': 'bg-blue-100 text-blue-800 ring-blue-200',
  'In Followup': 'bg-amber-100 text-amber-800 ring-amber-200',
  'A - Prospect': 'bg-violet-100 text-violet-800 ring-violet-200',
  'A+ - Immediate': 'bg-fuchsia-100 text-fuchsia-800 ring-fuchsia-200',
  'RNR / Not reachable': 'bg-orange-100 text-orange-800 ring-orange-200',
  'Not Interested': 'bg-graphite-200 text-graphite-700 ring-graphite-300',
  'Not Interested/Spam': 'bg-red-100 text-red-800 ring-red-200',
  'Site Visit': 'bg-lime-100 text-lime-800 ring-lime-200',
  'Quotation sent': 'bg-emerald-100 text-emerald-800 ring-emerald-200',
  Converted: 'bg-[#2F9E44]/10 text-[#237A35] ring-[#2F9E44]/30',
  Duplicate: 'bg-graphite-100 text-graphite-500 ring-graphite-200',
  Investor: 'bg-teal-100 text-teal-800 ring-teal-200',
  'Channel Partner': 'bg-indigo-100 text-indigo-800 ring-indigo-200',
  'Approval Client': 'bg-cyan-100 text-cyan-800 ring-cyan-200',
};

const SLA_STYLES: Record<string, string> = {
  PENDING: 'bg-[#1971C2]/10 text-[#155E9E] ring-[#1971C2]/30',
  COMPLETED: 'bg-[#2F9E44]/10 text-[#237A35] ring-[#2F9E44]/30',
  OVERDUE: 'bg-[#E03131]/10 text-[#B32727] ring-[#E03131]/30',
};

export function StatusBadge({ value }: { value: string }) {
  const cls = STATUS_STYLES[value] ?? 'bg-graphite-100 text-graphite-600 ring-graphite-200';
  return <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ring-1 ${cls}`}>{value || '—'}</span>;
}

export function SlaBadge({ value }: { value: string }) {
  const cls = SLA_STYLES[value] ?? 'bg-graphite-100 text-graphite-600 ring-graphite-200';
  const dot = value === 'OVERDUE' ? 'bg-[#E03131]' : value === 'COMPLETED' ? 'bg-[#2F9E44]' : 'bg-[#1971C2]';
  return (
    <span className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium ring-1 ${cls}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${dot}`} />
      {value || '—'}
    </span>
  );
}

export function Card({ title, action, children, className = '' }: { title?: string; action?: React.ReactNode; children: React.ReactNode; className?: string }) {
  return (
    <section className={`card p-5 ${className}`}>
      {(title || action) && (
        <div className="flex items-center justify-between mb-4">
          {title && <h2 className="text-sm font-semibold uppercase tracking-wide text-graphite-500">{title}</h2>}
          {action}
        </div>
      )}
      {children}
    </section>
  );
}

export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: string; actions?: React.ReactNode }) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 mb-6">
      <div>
        <h1 className="text-2xl font-bold text-graphite-900">{title}</h1>
        {subtitle && <p className="text-sm text-graphite-500 mt-1">{subtitle}</p>}
      </div>
      {actions && <div className="flex gap-2">{actions}</div>}
    </div>
  );
}

export function Spinner() {
  return (
    <div className="flex items-center justify-center p-12" role="status" aria-label="Loading">
      <div className="w-8 h-8 border-[3px] border-graphite-200 border-t-brand-600 rounded-full animate-spin" />
    </div>
  );
}

export function EmptyState({ title, hint }: { title: string; hint?: string }) {
  return (
    <div className="text-center py-12 px-4">
      <div className="mx-auto w-12 h-12 rounded-full bg-graphite-100 flex items-center justify-center text-graphite-400 text-xl">∅</div>
      <p className="mt-3 font-medium text-graphite-700">{title}</p>
      {hint && <p className="text-sm text-graphite-500 mt-1">{hint}</p>}
    </div>
  );
}

export function KpiCard({ label, value, sub, tone = 'slate', icon }: { label: string; value: React.ReactNode; sub?: string; tone?: 'slate' | 'red' | 'green' | 'amber' | 'blue'; icon?: string }) {
  const tones: Record<string, string> = {
    slate: 'bg-graphite-100 text-graphite-500', red: 'bg-red-100 text-[#E03131]',
    green: 'bg-brand-50 text-brand-700', amber: 'bg-amber-100 text-[#E8890C]',
    blue: 'bg-brand-400 text-signalink',
  };
  return (
    <div className="card p-5 flex items-start gap-4">
      {icon && <div className={`w-10 h-10 rounded-lg flex items-center justify-center text-lg ${tones[tone]}`}>{icon}</div>}
      <div className="min-w-0">
        <div className="text-xs font-medium uppercase tracking-wider text-graphite-500">{label}</div>
        <div className="text-2xl font-bold text-graphite-900 mt-1">{value}</div>
        {sub && <div className="text-xs text-graphite-400 mt-0.5">{sub}</div>}
      </div>
    </div>
  );
}
