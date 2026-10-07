'use client';

import { Suspense, useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { RequireAuth } from '@/components/auth/RequireAuth';
import { AppLayout } from '@/components/ui/AppLayout';
import { apiClient } from '@/lib/api-client';
import { API_ENDPOINTS } from '@/lib/api-config';
import { getApiErrorMessage } from '@/lib/auth-service';
import type { ProblemListResponse, ProblemStatus } from '@/types/api';
import { problemStatusStyle } from '@/lib/status-styles';

const PAGE_SIZE = 10;
const STATUSES: Array<'' | ProblemStatus> = [
  '',
  'SUBMITTED',
  'UNDER_REVIEW',
  'APPROVED',
  'ASSIGNED',
  'IN_PROGRESS',
  'AWAITING_VERIFICATION',
  'RESOLVED',
  'CLOSED',
  'REJECTED',
  'DUPLICATE',
  'WITHDRAWN',
];

function statusBadge(status: ProblemStatus): string {
  return problemStatusStyle(status);
}

function formatDate(value: string): string {
  return new Date(value).toLocaleString();
}

function MyReportsContent() {
  const searchParams = useSearchParams();
  const [data, setData] = useState<ProblemListResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [appliedSearch, setAppliedSearch] = useState('');
  const [status, setStatus] = useState<'' | ProblemStatus>('');
  const [page, setPage] = useState(0);

  useEffect(() => {
    const initial = searchParams.get('status') as '' | ProblemStatus | null;
    if (initial && STATUSES.includes(initial)) {
      setStatus(initial);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({
        skip: String(page * PAGE_SIZE),
        limit: String(PAGE_SIZE),
      });
      if (status) params.set('status', status);
      if (appliedSearch.trim()) params.set('q', appliedSearch.trim());
      const result = await apiClient.get<ProblemListResponse>(`${API_ENDPOINTS.problems.mine}?${params}`);
      setData(result);
    } catch (err) {
      setError(getApiErrorMessage(err, 'Failed to load your reports.'));
    } finally {
      setLoading(false);
    }
  }, [page, status, appliedSearch]);

  useEffect(() => {
    load();
  }, [load]);

  const totalPages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1;

  return (
    <AppLayout>
      <div className="space-y-6">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="text-2xl lg:text-3xl font-bold text-secondary-900">My Reports</h1>
            <p className="mt-1 text-secondary-600">Every problem you have reported.</p>
          </div>
          <Link href="/problems/new" className="btn-primary px-4 py-2 text-sm">
            Report a Problem
          </Link>
        </div>

        <div className="card p-4 flex flex-col md:flex-row gap-3">
          <input
            className="input-field md:flex-1"
            placeholder="Search ticket, title or description…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                setPage(0);
                setAppliedSearch(search);
              }
            }}
            aria-label="Search reports"
          />
          <select
            className="input-field md:w-56"
            value={status}
            onChange={(e) => {
              setPage(0);
              setStatus(e.target.value as '' | ProblemStatus);
            }}
            aria-label="Filter by status"
          >
            {STATUSES.map((s) => (
              <option key={s || 'all'} value={s}>
                {s === '' ? 'All statuses' : s}
              </option>
            ))}
          </select>
          <button
            type="button"
            className="btn-secondary px-4 py-2 text-sm"
            onClick={() => {
              setPage(0);
              setAppliedSearch(search);
            }}
          >
            Search
          </button>
        </div>

        {error && (
          <div role="alert" className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            {error}
          </div>
        )}

        {loading ? (
          <div className="card p-6 text-sm text-secondary-600">Loading reports…</div>
        ) : !data || data.total === 0 ? (
          <div className="card p-8 text-center">
            <h2 className="text-lg font-semibold text-secondary-900">You have not reported any campus problems yet.</h2>
            <p className="mt-1 text-sm text-secondary-600">Seen something broken on campus? Tell us about it.</p>
            <Link href="/problems/new" className="btn-primary px-4 py-2 text-sm mt-4 inline-block">
              Report a Problem
            </Link>
          </div>
        ) : (
          <>
            <ul className="space-y-3">
              {data.items.map((p) => (
                <li key={p.id}>
                  <Link
                    href={`/problems/${p.id}`}
                    className="card p-4 block hover:border-primary-300 transition-colors"
                  >
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-mono text-xs text-secondary-500">{p.ticket_number}</span>
                      <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${statusBadge(p.status)}`}>
                        {p.status}
                      </span>
                      <span className="ml-auto text-xs text-secondary-400">{formatDate(p.created_at)}</span>
                    </div>
                    <h3 className="mt-1 font-semibold text-secondary-900">{p.title}</h3>
                    <p className="text-sm text-secondary-600">
                      {p.location_text}
                      {p.affected_people_count != null ? ` · ${p.affected_people_count} affected` : ''}
                    </p>
                  </Link>
                </li>
              ))}
            </ul>

            <div className="flex items-center justify-between text-sm text-secondary-600">
              <span>
                Showing {data.items.length} of {data.total}
              </span>
              <div className="flex gap-2">
                <button
                  type="button"
                  className="btn-secondary px-3 py-1.5 text-sm"
                  disabled={page === 0}
                  onClick={() => setPage((v) => Math.max(0, v - 1))}
                >
                  Previous
                </button>
                <span className="px-2 py-1.5">
                  Page {page + 1} of {totalPages}
                </span>
                <button
                  type="button"
                  className="btn-secondary px-3 py-1.5 text-sm"
                  disabled={page + 1 >= totalPages}
                  onClick={() => setPage((v) => v + 1)}
                >
                  Next
                </button>
              </div>
            </div>
          </>
        )}
      </div>
    </AppLayout>
  );
}

export default function MyReportsPage() {
  return (
    <RequireAuth>
      <Suspense fallback={<div className="min-h-screen flex items-center justify-center">Loading…</div>}>
        <MyReportsContent />
      </Suspense>
    </RequireAuth>
  );
}
