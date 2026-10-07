'use client';

import Link from 'next/link';
import { useCallback, useEffect, useState } from 'react';
import { HorizontalBars, TrendChart } from '@/components/analytics/charts';
import { RequireAuth } from '@/components/auth/RequireAuth';
import { AppLayout } from '@/components/ui/AppLayout';
import { apiClient } from '@/lib/api-client';
import { API_ENDPOINTS } from '@/lib/api-config';
import { getApiErrorMessage } from '@/lib/auth-service';
import type { AnalyticsDashboard, AnalyticsTrends } from '@/types/api';

type Preset = '7d' | '30d' | '90d' | '1y' | 'all';

const PRESETS: { id: Preset; label: string }[] = [
  { id: '7d', label: 'Last 7 days' },
  { id: '30d', label: 'Last 30 days' },
  { id: '90d', label: 'Last 90 days' },
  { id: '1y', label: 'Last year' },
  { id: 'all', label: 'All time' },
];

const CATEGORIES = [
  '',
  'ACADEMIC',
  'CLEANLINESS_SANITATION',
  'ELECTRICAL',
  'HOSTEL',
  'INFRASTRUCTURE',
  'IT_NETWORK',
  'LABORATORY',
  'LIBRARY',
  'OTHER',
  'SAFETY_SECURITY',
  'TRANSPORT',
  'WATER_SANITATION',
  'UNCLASSIFIED',
];

function formatDuration(seconds: number | null): string {
  if (seconds == null) return '—';
  if (seconds < 3600) return `${Math.round(seconds / 60)} min`;
  const hours = seconds / 3600;
  if (hours < 48) return `${Math.round(hours)} hr`;
  return `${(hours / 24).toFixed(1)} days`;
}

function formatRate(rate: number | null): string {
  if (rate == null) return '—';
  return `${(rate * 100).toFixed(1)}%`;
}

function KpiCard({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="card p-4 md:p-5">
      <p className="text-xs font-medium uppercase tracking-wide text-secondary-500">{label}</p>
      <p className="mt-1 text-2xl lg:text-3xl font-bold text-secondary-900 tabular-nums">{value}</p>
      {hint && <p className="mt-1 text-xs text-secondary-500">{hint}</p>}
    </div>
  );
}

function Section({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="card p-5 md:p-6">
      <h2 className="text-lg font-semibold text-secondary-900">{title}</h2>
      {subtitle && <p className="mt-0.5 text-sm text-secondary-600">{subtitle}</p>}
      <div className="mt-4">{children}</div>
    </section>
  );
}

function AnalyticsContent() {
  const [data, setData] = useState<AnalyticsDashboard | null>(null);
  const [trends, setTrends] = useState<AnalyticsTrends | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [preset, setPreset] = useState<Preset>('all');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [category, setCategory] = useState('');
  const [location, setLocation] = useState('');
  const [applied, setApplied] = useState({ preset: 'all' as Preset, dateFrom: '', dateTo: '', category: '', location: '' });
  const [downloading, setDownloading] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      if (applied.dateFrom || applied.dateTo) {
        if (applied.dateFrom) params.set('date_from', new Date(`${applied.dateFrom}T00:00:00Z`).toISOString());
        if (applied.dateTo) params.set('date_to', new Date(`${applied.dateTo}T23:59:59Z`).toISOString());
      } else if (applied.preset !== 'all') {
        params.set('preset', applied.preset);
      }
      if (applied.category) params.set('category', applied.category);
      if (applied.location.trim()) params.set('location', applied.location.trim());
      const query = params.toString();
      const [dash, trend] = await Promise.all([
        apiClient.get<AnalyticsDashboard>(
          `${API_ENDPOINTS.adminAnalytics.dashboard}${query ? `?${query}` : ''}`
        ),
        apiClient.get<AnalyticsTrends>(
          `${API_ENDPOINTS.adminAnalytics.trends}${query ? `?${query}` : ''}`
        ),
      ]);
      setData(dash);
      setTrends(trend);
    } catch (err) {
      setError(getApiErrorMessage(err, 'Failed to load analytics.'));
    } finally {
      setLoading(false);
    }
  }, [applied]);

  useEffect(() => {
    load();
  }, [load]);

  const apply = () => {
    setApplied({ preset, dateFrom, dateTo, category, location });
  };

  const downloadCsv = async (kind: 'problems' | 'skills') => {
    setDownloading(kind);
    try {
      const params = new URLSearchParams();
      if (applied.dateFrom || applied.dateTo) {
        if (applied.dateFrom) params.set('date_from', new Date(`${applied.dateFrom}T00:00:00Z`).toISOString());
        if (applied.dateTo) params.set('date_to', new Date(`${applied.dateTo}T23:59:59Z`).toISOString());
      } else if (applied.preset !== 'all') {
        params.set('preset', applied.preset);
      }
      if (applied.category) params.set('category', applied.category);
      if (applied.location.trim()) params.set('location', applied.location.trim());
      const query = params.toString();
      const url =
        kind === 'problems'
          ? `${API_ENDPOINTS.adminAnalytics.exportProblems}${query ? `?${query}` : ''}`
          : API_ENDPOINTS.adminAnalytics.exportSkills;
      const response = await apiClient.instance.get(url, { responseType: 'blob' });
      const objectUrl = window.URL.createObjectURL(new Blob([response.data], { type: 'text/csv' }));
      const anchor = document.createElement('a');
      anchor.href = objectUrl;
      anchor.download = kind === 'problems' ? 'problems.csv' : 'skill-demand.csv';
      anchor.click();
      window.URL.revokeObjectURL(objectUrl);
    } catch (err) {
      setError(getApiErrorMessage(err, 'CSV export failed.'));
    } finally {
      setDownloading(null);
    }
  };

  return (
    <AppLayout>
      <div className="space-y-6">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="text-2xl lg:text-3xl font-bold text-secondary-900">Campus Analytics</h1>
            <p className="mt-1 text-secondary-600">
              Real-time operational insights from CampusXolve.
            </p>
          </div>
          <div className="flex gap-2">
            <button
              type="button"
              className="btn-secondary px-3 py-2 text-sm"
              disabled={downloading !== null}
              onClick={() => downloadCsv('problems')}
            >
              {downloading === 'problems' ? 'Exporting…' : 'Export problems CSV'}
            </button>
            <button
              type="button"
              className="btn-secondary px-3 py-2 text-sm"
              disabled={downloading !== null}
              onClick={() => downloadCsv('skills')}
            >
              {downloading === 'skills' ? 'Exporting…' : 'Export skills CSV'}
            </button>
          </div>
        </div>

        <div className="card p-4 md:p-5">
          <div className="flex flex-wrap gap-2" role="group" aria-label="Date range presets">
            {PRESETS.map((p) => (
              <button
                key={p.id}
                type="button"
                onClick={() => {
                  setPreset(p.id);
                  setDateFrom('');
                  setDateTo('');
                  setApplied((prev) => ({ ...prev, preset: p.id, dateFrom: '', dateTo: '' }));
                }}
                className={`px-3 py-1.5 text-sm rounded-lg border transition-colors ${
                  preset === p.id && !dateFrom && !dateTo
                    ? 'bg-primary-600 text-white border-primary-600'
                    : 'bg-white text-secondary-700 border-secondary-200 hover:border-primary-300'
                }`}
              >
                {p.label}
              </button>
            ))}
          </div>
          <div className="mt-3 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
            <label className="block">
              <span className="label">From</span>
              <input
                type="date"
                className="input-field"
                value={dateFrom}
                onChange={(e) => setDateFrom(e.target.value)}
                aria-label="Custom start date"
              />
            </label>
            <label className="block">
              <span className="label">To</span>
              <input
                type="date"
                className="input-field"
                value={dateTo}
                onChange={(e) => setDateTo(e.target.value)}
                aria-label="Custom end date"
              />
            </label>
            <label className="block">
              <span className="label">Category</span>
              <select
                className="input-field"
                value={category}
                onChange={(e) => setCategory(e.target.value)}
                aria-label="Filter by category"
              >
                {CATEGORIES.map((c) => (
                  <option key={c} value={c}>
                    {c === '' ? 'All categories' : c}
                  </option>
                ))}
              </select>
            </label>
            <label className="block">
              <span className="label">Location</span>
              <input
                className="input-field"
                placeholder="e.g. Library"
                value={location}
                onChange={(e) => setLocation(e.target.value)}
                aria-label="Filter by location"
              />
            </label>
          </div>
          <div className="mt-3">
            <button type="button" className="btn-primary px-4 py-2 text-sm" onClick={apply}>
              Apply filters
            </button>
          </div>
        </div>

        {loading ? (
          <div className="card p-6 text-sm text-secondary-600">Loading analytics…</div>
        ) : error ? (
          <div className="card p-6 text-sm text-red-700" role="alert">
            {error}
          </div>
        ) : !data ? (
          <div className="card p-6 text-sm text-secondary-600">No analytics data available.</div>
        ) : (
          <>
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 md:gap-4">
              <KpiCard label="Total problems" value={String(data.overview.total_problems)} />
              <KpiCard
                label="Open problems"
                value={String(data.overview.open_problems)}
                hint="Submitted → awaiting verification"
              />
              <KpiCard
                label="High / critical"
                value={`${data.overview.high_priority + data.overview.critical_priority}`}
                hint={`${data.overview.critical_priority} critical`}
              />
              <KpiCard label="Resolved" value={String(data.overview.resolved_problems)} hint="Resolved + closed" />
              <KpiCard
                label="Avg resolution time"
                value={formatDuration(data.resolution.average_seconds)}
                hint={data.resolution.count > 0 ? `Across ${data.resolution.count} resolved` : 'No resolved reports yet'}
              />
              <KpiCard label="Active assignments" value={String(data.overview.active_assignments)} />
              <KpiCard label="Duplicate clusters" value={String(data.overview.duplicate_clusters)} />
              <KpiCard label="Knowledge entries" value={String(data.overview.published_knowledge)} />
            </div>

            <Section
              title="Reported vs resolved"
              subtitle={`By ${trends?.granularity ?? 'day'} · descriptive counts, not a forecast`}
            >
              {trends && trends.buckets.length > 0 ? (
                <TrendChart buckets={trends.buckets} />
              ) : (
                <p className="text-sm text-secondary-500">No trend data in range.</p>
              )}
            </Section>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 md:gap-6">
              <Section title="Problems by category" subtitle="Final category when reviewed, else AI category">
                <HorizontalBars
                  ariaLabel="Problems by category"
                  data={data.categories.items.map((c) => ({ label: c.category, value: c.count }))}
                  formatValue={(v) => String(v)}
                />
              </Section>
              <Section title="Priority distribution" subtitle="Explainable Priority Engine levels">
                <HorizontalBars
                  ariaLabel="Priority distribution"
                  data={['LOW', 'MEDIUM', 'HIGH', 'CRITICAL'].map((level) => ({
                    label: level,
                    value: data.priorities.counts[level] ?? 0,
                  }))}
                />
                <p className="mt-2 text-xs text-secondary-500">
                  Average score:{' '}
                  {data.priorities.average_score != null ? data.priorities.average_score : '—'}
                </p>
              </Section>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 md:gap-6">
              <Section title="Location hotspots" subtitle="Campus locations only · grouped case-insensitively">
                {data.locations && data.locations.items.length > 0 ? (
                  <ul className="space-y-3">
                    {data.locations.items.slice(0, 8).map((loc) => (
                      <li key={loc.location} className="rounded-lg border border-secondary-200 p-3">
                        <div className="flex flex-wrap items-baseline justify-between gap-2">
                          <p className="font-medium text-secondary-900">{loc.location}</p>
                          <p className="text-sm text-secondary-600 tabular-nums">
                            {loc.count} reports · {loc.open_count} open · {loc.resolved_count} resolved
                          </p>
                        </div>
                        {loc.common_categories.length > 0 && (
                          <p className="mt-1 text-xs text-secondary-500">
                            Common: {loc.common_categories.join(', ')}
                          </p>
                        )}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-sm text-secondary-500">No location data in range.</p>
                )}
              </Section>
              <Section title="Top required skills" subtitle="Distinct problems per skill · latest analysis only">
                <HorizontalBars
                  ariaLabel="Top required skills"
                  data={data.skill_demand.items.slice(0, 8).map((s) => ({ label: s.name, value: s.problems }))}
                />
              </Section>
            </div>

            <Section title="Resolution performance" subtitle="Genuine submitted → resolved durations only">
              {data.resolution.count > 0 ? (
                <dl className="grid grid-cols-2 md:grid-cols-5 gap-3 text-sm">
                  {[
                    ['Average', data.resolution.average_seconds],
                    ['Median', data.resolution.median_seconds],
                    ['Minimum', data.resolution.min_seconds],
                    ['Maximum', data.resolution.max_seconds],
                    ['P90', data.resolution.p90_seconds],
                  ].map(([label, seconds]) => (
                    <div key={label as string} className="rounded-lg bg-secondary-50 p-3">
                      <dt className="text-xs text-secondary-500">{label}</dt>
                      <dd className="font-semibold text-secondary-900 tabular-nums">
                        {formatDuration(seconds as number | null)}
                      </dd>
                    </div>
                  ))}
                </dl>
              ) : (
                <p className="text-sm text-secondary-500">No resolved reports in range yet.</p>
              )}
              <p className="mt-2 text-xs text-secondary-500">
                Reporter confirmations: {data.verification.resolved_confirmations} · Rejections:{' '}
                {data.verification.not_resolved_responses} · Reopen rate:{' '}
                {formatRate(data.verification.reopen_rate)} · Avg revisions:{' '}
                {data.verification.average_revisions ?? '—'} · Resolved on first submission:{' '}
                {data.verification.resolved_on_first_submission}
              </p>
            </Section>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 md:gap-6">
              <Section title="High / critical open issues" subtitle="Oldest most-urgent first">
                {data.priorities.high_critical_open.length > 0 ? (
                  <ul className="space-y-2">
                    {data.priorities.high_critical_open.map((p) => (
                      <li key={p.problem_id} className="rounded-lg border border-secondary-200 p-3 text-sm">
                        <Link
                          href={`/problems/${p.problem_id}`}
                          className="font-medium text-primary-700 hover:text-primary-800"
                        >
                          {p.title}
                        </Link>
                        <p className="mt-0.5 text-xs text-secondary-500">
                          {p.ticket_number} · {p.priority_level} ({p.priority_score ?? '—'}) · {p.status}
                        </p>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-sm text-secondary-500">No high or critical open issues.</p>
                )}
              </Section>
              <Section title="Duplicates" subtitle="Confirmed consolidations only">
                <dl className="grid grid-cols-2 gap-3 text-sm">
                  <div className="rounded-lg bg-secondary-50 p-3">
                    <dt className="text-xs text-secondary-500">Confirmed duplicate reports</dt>
                    <dd className="font-semibold text-secondary-900 tabular-nums">
                      {data.duplicates.confirmed_duplicate_problems}
                    </dd>
                  </div>
                  <div className="rounded-lg bg-secondary-50 p-3">
                    <dt className="text-xs text-secondary-500">Active clusters</dt>
                    <dd className="font-semibold text-secondary-900 tabular-nums">
                      {data.duplicates.active_clusters}
                    </dd>
                  </div>
                  <div className="rounded-lg bg-secondary-50 p-3">
                    <dt className="text-xs text-secondary-500">Avg reports / cluster</dt>
                    <dd className="font-semibold text-secondary-900 tabular-nums">
                      {data.duplicates.average_reports_per_cluster}
                    </dd>
                  </div>
                  <div className="rounded-lg bg-secondary-50 p-3">
                    <dt className="text-xs text-secondary-500">Largest cluster</dt>
                    <dd className="font-semibold text-secondary-900 tabular-nums">
                      {data.duplicates.largest_cluster_size}
                    </dd>
                  </div>
                  <div className="rounded-lg bg-secondary-50 p-3">
                    <dt className="text-xs text-secondary-500">Pending review</dt>
                    <dd className="font-semibold text-secondary-900 tabular-nums">
                      {data.duplicates.pending_candidates}{' '}
                      <Link href="/admin/duplicates" className="text-primary-700 hover:text-primary-800 font-normal">
                        Review →
                      </Link>
                    </dd>
                  </div>
                  <div className="rounded-lg bg-secondary-50 p-3">
                    <dt className="text-xs text-secondary-500">Confirmation rate</dt>
                    <dd className="font-semibold text-secondary-900 tabular-nums">
                      {formatRate(data.duplicates.confirmation_rate)}
                    </dd>
                  </div>
                </dl>
                <p className="mt-2 text-xs text-secondary-500">
                  Duplicate reduction ratio: {formatRate(data.duplicates.duplicate_reduction_ratio)} of
                  all reports confirmed duplicate · Avoided independent assignments:{' '}
                  {data.duplicates.avoided_assignments} (confirmed members never assigned)
                </p>
              </Section>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 md:gap-6">
              <Section title="Solver workload" subtitle="Operational capacity only — never a performance ranking">
                <p className="text-sm text-secondary-700">
                  Utilization:{' '}
                  <span className="font-semibold tabular-nums">
                    {formatRate(data.workloads.solvers.utilization)}
                  </span>{' '}
                  ({data.workloads.solvers.total_used}/{data.workloads.solvers.total_capacity} slots)
                </p>
                <div className="mt-2 space-y-1 text-sm">
                  {Object.entries(data.workloads.solvers.by_availability).map(([status, row]) => (
                    <p key={status} className="text-secondary-700">
                      {status}: <span className="font-medium tabular-nums">{row.count}</span> solvers
                    </p>
                  ))}
                </div>
                {data.workloads.busiest_solvers.length > 0 && (
                  <div className="mt-3 overflow-x-auto">
                    <table className="min-w-full text-sm">
                      <thead>
                        <tr className="border-b border-secondary-200 text-left text-xs uppercase tracking-wide text-secondary-500">
                          <th className="py-2 pr-4">Solver</th>
                          <th className="py-2">Load</th>
                        </tr>
                      </thead>
                      <tbody>
                        {data.workloads.busiest_solvers.map((s, i) => (
                          <tr key={`${s.name}-${i}`} className="border-b border-secondary-100 last:border-0">
                            <td className="py-2 pr-4 font-medium text-secondary-900">{s.name}</td>
                            <td className="py-2 tabular-nums text-secondary-700">
                              {s.current_workload}/{s.max_workload}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </Section>
              <Section title="Mentor workload" subtitle="Operational capacity only">
                <p className="text-sm text-secondary-700">
                  Utilization:{' '}
                  <span className="font-semibold tabular-nums">
                    {formatRate(data.workloads.mentors.utilization)}
                  </span>{' '}
                  ({data.workloads.mentors.total_used}/{data.workloads.mentors.total_capacity} slots)
                </p>
                <div className="mt-2 space-y-1 text-sm">
                  {Object.entries(data.workloads.mentors.by_availability).map(([status, row]) => (
                    <p key={status} className="text-secondary-700">
                      {status}: <span className="font-medium tabular-nums">{row.count}</span> mentors
                    </p>
                  ))}
                </div>
                {data.workloads.busiest_mentors.length > 0 && (
                  <div className="mt-3 overflow-x-auto">
                    <table className="min-w-full text-sm">
                      <thead>
                        <tr className="border-b border-secondary-200 text-left text-xs uppercase tracking-wide text-secondary-500">
                          <th className="py-2 pr-4">Mentor</th>
                          <th className="py-2">Load</th>
                        </tr>
                      </thead>
                      <tbody>
                        {data.workloads.busiest_mentors.map((s, i) => (
                          <tr key={`${s.name}-${i}`} className="border-b border-secondary-100 last:border-0">
                            <td className="py-2 pr-4 font-medium text-secondary-900">{s.name}</td>
                            <td className="py-2 tabular-nums text-secondary-700">
                              {s.current_workload}/{s.max_workload}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </Section>
            </div>

            <Section title="Assignments & AI recommendation handling" subtitle="Accepted = used unchanged · overridden = admin composed manually">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-sm">
                <div className="rounded-lg bg-secondary-50 p-3">
                  <p className="text-xs text-secondary-500">Assignments by status</p>
                  {Object.entries(data.assignments.counts).map(([status, count]) => (
                    <p key={status} className="text-secondary-700 tabular-nums">
                      {status}: <span className="font-medium">{count}</span>
                    </p>
                  ))}
                </div>
                <div className="rounded-lg bg-secondary-50 p-3">
                  <p className="text-xs text-secondary-500">Recommendation handling</p>
                  <p className="text-secondary-700 tabular-nums">
                    Team accepted: {data.assignments.team_accepted_count} · overridden:{' '}
                    {data.assignments.team_override_count} ({formatRate(data.assignments.team_override_rate)})
                  </p>
                  <p className="text-secondary-700 tabular-nums">
                    Mentor accepted: {data.assignments.mentor_accepted_count} · overridden:{' '}
                    {data.assignments.mentor_override_count} ({formatRate(data.assignments.mentor_override_rate)})
                  </p>
                </div>
              </div>
            </Section>

            <Section
              title="AI / analysis health"
              subtitle="Admin only · stored offline evaluation kept separate from live operations"
            >
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-sm">
                <div className="rounded-lg bg-secondary-50 p-3">
                  <p className="text-xs text-secondary-500">Classifier (development evaluation)</p>
                  {data.classification.model_quality.available ? (
                    <>
                      <p className="font-medium text-secondary-900">
                        {data.classification.model_quality.model_version}
                      </p>
                      <p className="text-secondary-700">
                        Development test accuracy:{' '}
                        <span className="font-semibold tabular-nums">
                          {data.classification.model_quality.test_accuracy != null
                            ? `${(data.classification.model_quality.test_accuracy * 100).toFixed(2)}%`
                            : '—'}
                        </span>
                      </p>
                      <p className="text-secondary-700">
                        Macro F1:{' '}
                        <span className="font-semibold tabular-nums">
                          {data.classification.model_quality.macro_f1 ?? '—'}
                        </span>{' '}
                        · Weighted F1:{' '}
                        <span className="font-semibold tabular-nums">
                          {data.classification.model_quality.weighted_f1 ?? '—'}
                        </span>
                      </p>
                      <p className="mt-1 text-xs text-secondary-500" title="Measured on a held-out development set, not live production traffic">
                        Development Evaluation Dataset — not production accuracy. Base:{' '}
                        {data.classification.model_quality.base_model} · test samples:{' '}
                        {data.classification.model_quality.test_samples} · threshold:{' '}
                        {data.classification.model_quality.confidence_threshold}
                      </p>
                    </>
                  ) : (
                    <p className="text-secondary-600">Evaluation artifacts unavailable.</p>
                  )}
                </div>
                <div className="rounded-lg bg-secondary-50 p-3">
                  <p className="text-xs text-secondary-500">Live operations</p>
                  <p className="text-secondary-700 tabular-nums">
                    Classifications: {data.classification.total} · low-confidence:{' '}
                    {data.classification.low_confidence} ({formatRate(data.classification.low_confidence_rate)}) ·
                    failed: {data.classification.failed}
                  </p>
                  <p className="text-secondary-700 tabular-nums">
                    Admin-reviewed: {data.classification.reviewed} · category overrides:{' '}
                    {data.classification.override_count} ({formatRate(data.classification.override_rate)})
                  </p>
                  <p className="text-secondary-700 tabular-nums">
                    Duplicate candidates pending: {data.duplicates.pending_candidates}
                  </p>
                </div>
              </div>
              {data.classification.model_quality.available &&
                (data.classification.model_quality.per_class_f1 ?? []).length > 0 && (
                  <div className="mt-3">
                    <p className="text-sm font-medium text-secondary-900">
                      Development model classes needing improvement (weakest first)
                    </p>
                    <div className="mt-1 flex flex-wrap gap-1.5">
                      {(data.classification.model_quality.per_class_f1 ?? [])
                        .slice(0, 4)
                        .map((c) => (
                          <span
                            key={c.label}
                            title={`Development F1 ${c.f1}`}
                            className="text-xs px-2 py-0.5 rounded-full bg-amber-100 text-amber-800"
                          >
                            {c.label} · F1 {c.f1}
                          </span>
                        ))}
                    </div>
                  </div>
                )}
            </Section>

            <Section title="Operations watch" subtitle="Blocked and overdue work across all reports">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-sm">
                <div>
                  <p className="font-medium text-secondary-900">
                    Blocked tasks ({data.operations.blocked_tasks.length})
                  </p>
                  {data.operations.blocked_tasks.length > 0 ? (
                    <ul className="mt-1 space-y-1">
                      {data.operations.blocked_tasks.map((t) => (
                        <li key={t.id}>
                          <Link
                            href={`/problems/${t.problem_id}/workspace`}
                            className="text-primary-700 hover:text-primary-800"
                          >
                            {t.title}
                          </Link>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="text-secondary-500">None.</p>
                  )}
                  <p className="mt-2 font-medium text-secondary-900">
                    Overdue tasks ({data.operations.overdue_tasks.length})
                  </p>
                  {data.operations.overdue_tasks.length > 0 ? (
                    <ul className="mt-1 space-y-1">
                      {data.operations.overdue_tasks.map((t) => (
                        <li key={t.id}>
                          <Link
                            href={`/problems/${t.problem_id}/workspace`}
                            className="text-primary-700 hover:text-primary-800"
                          >
                            {t.title}
                          </Link>{' '}
                          <span className="text-xs text-secondary-500">
                            due {t.due_date ? new Date(t.due_date).toLocaleDateString() : '—'}
                          </span>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="text-secondary-500">None.</p>
                  )}
                </div>
                <div>
                  <p className="font-medium text-secondary-900">
                    Overdue milestones ({data.operations.overdue_milestones.length})
                  </p>
                  {data.operations.overdue_milestones.length > 0 ? (
                    <ul className="mt-1 space-y-1">
                      {data.operations.overdue_milestones.map((t) => (
                        <li key={t.id}>
                          <Link
                            href={`/problems/${t.problem_id}/workspace`}
                            className="text-primary-700 hover:text-primary-800"
                          >
                            {t.title}
                          </Link>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="text-secondary-500">None.</p>
                  )}
                  <p className="mt-2 font-medium text-secondary-900">
                    Upcoming milestones, 7 days ({data.operations.upcoming_milestones.length})
                  </p>
                  {data.operations.upcoming_milestones.length > 0 ? (
                    <ul className="mt-1 space-y-1">
                      {data.operations.upcoming_milestones.map((t) => (
                        <li key={t.id}>
                          <Link
                            href={`/problems/${t.problem_id}/workspace`}
                            className="text-primary-700 hover:text-primary-800"
                          >
                            {t.title}
                          </Link>{' '}
                          <span className="text-xs text-secondary-500">
                            {t.target_date ? new Date(t.target_date).toLocaleDateString() : '—'}
                          </span>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="text-secondary-500">None.</p>
                  )}
                </div>
              </div>
            </Section>

            <Section title="Knowledge repository" subtitle="Published institutional memory">
              <p className="text-sm text-secondary-700 tabular-nums">
                Published: {data.knowledge.published} · Archived: {data.knowledge.archived} ·
                Failed: {data.knowledge.failed}
              </p>
              {data.knowledge.top_categories.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {data.knowledge.top_categories.map((c) => (
                    <span
                      key={c.category}
                      className="text-xs px-2 py-0.5 rounded-full bg-primary-50 text-primary-700"
                    >
                      {c.category} · {c.count}
                    </span>
                  ))}
                </div>
              )}
            </Section>
          </>
        )}
      </div>
    </AppLayout>
  );
}

export default function AnalyticsPage() {
  return (
    <RequireAuth roles={['ADMIN']}>
      <AnalyticsContent />
    </RequireAuth>
  );
}
