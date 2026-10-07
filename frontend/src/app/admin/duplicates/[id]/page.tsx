'use client';

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { useParams } from 'next/navigation';
import { RequireAuth } from '@/components/auth/RequireAuth';
import { AppLayout } from '@/components/ui/AppLayout';
import { apiClient } from '@/lib/api-client';
import { API_ENDPOINTS } from '@/lib/api-config';
import { getApiErrorMessage } from '@/lib/auth-service';
import type { DuplicateCluster, ProblemDetail } from '@/types/api';

const DUPLICATE_EVENTS = new Set([
  'DUPLICATE_ANALYSIS_COMPLETED',
  'DUPLICATE_CONFIRMED',
  'DUPLICATE_REJECTED',
  'JOINED_DUPLICATE_CLUSTER',
  'DUPLICATE_CLUSTER_MERGED',
  'STATUS_CHANGED',
]);

function formatDate(value: string): string {
  return new Date(value).toLocaleString();
}

function AdminClusterDetailContent() {
  const params = useParams<{ id: string }>();
  const clusterId = params.id;

  const [cluster, setCluster] = useState<DuplicateCluster | null>(null);
  const [history, setHistory] = useState<
    Array<{ id: string; event: string; message: string | null; at: string }>
  >([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await apiClient.get<DuplicateCluster>(
        API_ENDPOINTS.adminDuplicates.clusterDetail(clusterId)
      );
      setCluster(result);
      // Decision history: duplicate-related activity on the canonical report.
      if (result.canonical_problem_id) {
        try {
          const detail = await apiClient.get<ProblemDetail>(
            API_ENDPOINTS.adminProblems.detail(result.canonical_problem_id)
          );
          setHistory(
            detail.activity
              .filter((a) => DUPLICATE_EVENTS.has(a.event_type))
              .map((a) => ({
                id: a.id,
                event: a.event_type,
                message: a.message,
                at: a.created_at,
              }))
          );
        } catch {
          setHistory([]);
        }
      }
    } catch (err) {
      setError(getApiErrorMessage(err, 'Cluster not found or you do not have access.'));
    } finally {
      setLoading(false);
    }
  }, [clusterId]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <AppLayout>
      <div className="space-y-6">
        <div className="text-sm">
          <Link href="/admin/duplicates" className="text-primary-600 hover:text-primary-700 font-medium">
            ← Duplicate Clusters
          </Link>
        </div>

        {loading ? (
          <div className="card p-6 text-sm text-secondary-600">Loading cluster…</div>
        ) : error || !cluster ? (
          <div className="card p-8 text-center">
            <h1 className="text-xl font-bold text-secondary-900">Cluster unavailable</h1>
            <p className="mt-1 text-sm text-secondary-600">{error ?? 'Not found.'}</p>
          </div>
        ) : (
          <>
            <div>
              <h1 className="text-2xl lg:text-3xl font-bold text-secondary-900 font-mono">
                {cluster.cluster_number}
              </h1>
              <p className="mt-1 text-secondary-600">
                {cluster.members.length} member{cluster.members.length === 1 ? '' : 's'} · created{' '}
                {formatDate(cluster.created_at)}
              </p>
            </div>

            <div className="card p-6">
              <h2 className="text-lg font-semibold text-secondary-900 mb-3">Canonical Issue</h2>
              {cluster.canonical ? (
                <div className="text-sm space-y-1">
                  <p>
                    <span className="font-mono text-secondary-500">
                      {cluster.canonical.ticket_number}
                    </span>{' '}
                    <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-blue-100 text-blue-800">
                      {cluster.canonical.status}
                    </span>
                  </p>
                  <p className="font-medium text-secondary-900">{cluster.canonical.title}</p>
                  <p className="text-secondary-600">Location: {cluster.canonical.location_text}</p>
                  {cluster.canonical_problem_id && (
                    <Link
                      href={`/problems/${cluster.canonical_problem_id}`}
                      className="inline-block font-medium text-primary-700 hover:text-primary-800"
                    >
                      Open canonical report →
                    </Link>
                  )}
                </div>
              ) : (
                <p className="text-sm text-secondary-600">No canonical report set.</p>
              )}
            </div>

            <div className="card p-6">
              <h2 className="text-lg font-semibold text-secondary-900 mb-3">
                Members ({cluster.members.length})
              </h2>
              {cluster.members.length === 0 ? (
                <p className="text-sm text-secondary-600">No members.</p>
              ) : (
                <ul className="space-y-2">
                  {cluster.members.map((m) => (
                    <li
                      key={m.problem_id}
                      className="flex flex-wrap items-center gap-2 rounded-lg border border-secondary-200 px-3 py-2 text-sm"
                    >
                      <Link
                        href={`/problems/${m.problem_id}`}
                        className="font-mono text-primary-700 hover:text-primary-800"
                      >
                        {m.ticket_number}
                      </Link>
                      <span className="flex-1 min-w-[12rem] truncate text-secondary-800">
                        {m.title}
                      </span>
                      <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-blue-100 text-blue-800">
                        {m.status}
                      </span>
                      {m.is_canonical && (
                        <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-green-100 text-green-800">
                          Canonical
                        </span>
                      )}
                      {m.reporter_name && (
                        <span className="text-xs text-secondary-500">{m.reporter_name}</span>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </div>

            <div className="card p-6">
              <h2 className="text-lg font-semibold text-secondary-900 mb-3">Decision History</h2>
              {history.length === 0 ? (
                <p className="text-sm text-secondary-600">
                  No duplicate decisions recorded on the canonical report yet.
                </p>
              ) : (
                <ol className="space-y-3">
                  {history.map((h) => (
                    <li key={h.id} className="flex gap-3 text-sm">
                      <span
                        className="mt-1 w-2 h-2 rounded-full bg-primary-500 flex-shrink-0"
                        aria-hidden="true"
                      />
                      <div>
                        <p className="font-medium text-secondary-800">
                          {h.event.replaceAll('_', ' ')}
                        </p>
                        {h.message && <p className="text-secondary-600">{h.message}</p>}
                        <p className="text-xs text-secondary-400">{formatDate(h.at)}</p>
                      </div>
                    </li>
                  ))}
                </ol>
              )}
            </div>
          </>
        )}
      </div>
    </AppLayout>
  );
}

export default function AdminClusterDetailPage() {
  return (
    <RequireAuth>
      <AdminClusterDetailContent />
    </RequireAuth>
  );
}
