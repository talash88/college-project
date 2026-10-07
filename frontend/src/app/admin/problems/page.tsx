'use client';

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { RequireAuth } from '@/components/auth/RequireAuth';
import { AppLayout } from '@/components/ui/AppLayout';
import { apiClient } from '@/lib/api-client';
import { API_ENDPOINTS } from '@/lib/api-config';
import { getApiErrorMessage } from '@/lib/auth-service';
import { problemStatusStyle } from '@/lib/status-styles';
import type { AdminProblemListResponse, ProblemStatus } from '@/types/api';

const PAGE_SIZE = 15;
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

function AdminProblemsContent() {
  const searchParams = useSearchParams();
  const [data, setData] = useState<AdminProblemListResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [appliedSearch, setAppliedSearch] = useState('');
  const initialStatus = searchParams.get('status') as '' | ProblemStatus | null;
  const [status, setStatus] = useState<'' | ProblemStatus>(
    initialStatus && (STATUSES as string[]).includes(initialStatus) ? initialStatus : 'SUBMITTED'
  );
  const [page, setPage] = useState(0);

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
      const result = await apiClient.get<AdminProblemListResponse>(
        `${API_ENDPOINTS.adminProblems.base}?${params}`
      );
      setData(result);
    } catch (err) {
      setError(getApiErrorMessage(err, 'Failed to load reports.'));
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
        <div>
          <h1 className="text-2xl lg:text-3xl font-bold text-secondary-900">Administration — Problem Intake</h1>
          <p className="mt-1 text-secondary-600">Incoming reports. Team assignment and AI review arrive in later steps.</p>
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
            <h2 className="text-lg font-semibold text-secondary-900">No reports match.</h2>
            <p className="mt-1 text-sm text-secondary-600">Try a different search or status filter.</p>
          </div>
        ) : (
          <>
            <div className="card overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-secondary-500 border-b border-secondary-200">
                    <th className="px-4 py-3 font-medium">Ticket</th>
                    <th className="px-4 py-3 font-medium">Title</th>
                    <th className="px-4 py-3 font-medium">Reporter</th>
                    <th className="px-4 py-3 font-medium">Status</th>
                    <th className="px-4 py-3 font-medium">Reported</th>
                  </tr>
                </thead>
                <tbody>
                  {data.items.map((p) => (
                    <tr key={p.id} className="border-b border-secondary-100 last:border-0 hover:bg-secondary-50">
                      <td className="px-4 py-3 font-mono text-xs text-secondary-500 whitespace-nowrap">
                        {p.ticket_number}
                      </td>
                      <td className="px-4 py-3">
                        <Link href={`/problems/${p.id}`} className="font-medium text-primary-700 hover:text-primary-800">
                          {p.title}
                        </Link>
                        <p className="text-xs text-secondary-500">{p.location_text}</p>
                      </td>
                      <td className="px-4 py-3 whitespace-nowrap">
                        {p.reporter_name ?? '—'}
                        <p className="text-xs text-secondary-500">{p.reporter_email ?? ''}</p>
                      </td>
                      <td className="px-4 py-3 whitespace-nowrap">
                        <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${problemStatusStyle(p.status)}`}>
                          {p.status}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-xs text-secondary-500 whitespace-nowrap">
                        {new Date(p.created_at).toLocaleString()}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

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

export default function AdminProblemsPage() {
  return (
    <RequireAuth roles={['ADMIN']}>
      <AdminProblemsContent />
    </RequireAuth>
  );
}
