'use client';

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { RequireAuth } from '@/components/auth/RequireAuth';
import { AppLayout } from '@/components/ui/AppLayout';
import { apiClient } from '@/lib/api-client';
import { API_ENDPOINTS } from '@/lib/api-config';
import { getApiErrorMessage } from '@/lib/auth-service';
import type { DuplicateCluster } from '@/types/api';

function formatDate(value: string): string {
  return new Date(value).toLocaleString();
}

function AdminDuplicatesContent() {
  const [clusters, setClusters] = useState<DuplicateCluster[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await apiClient.get<DuplicateCluster[]>(API_ENDPOINTS.adminDuplicates.clusters);
      setClusters(result);
    } catch (err) {
      setError(getApiErrorMessage(err, 'Failed to load duplicate clusters.'));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const live = (clusters ?? []).filter((c) => c.members.length > 0);

  return (
    <AppLayout>
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl lg:text-3xl font-bold text-secondary-900">
            Administration — Duplicate Clusters
          </h1>
          <p className="mt-1 text-secondary-600">
            Admin-confirmed groups of duplicate reports. Suggestions are reviewed on each report;
            clusters only ever grow through explicit confirmation.
          </p>
        </div>

        {loading ? (
          <div className="card p-6 text-sm text-secondary-600">Loading clusters…</div>
        ) : error ? (
          <div className="card p-6 text-sm text-red-700" role="alert">
            {error}
          </div>
        ) : live.length === 0 ? (
          <div className="card p-6 text-sm text-secondary-600">No duplicate clusters yet.</div>
        ) : (
          <div className="card overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead>
                <tr className="border-b border-secondary-200 text-left text-xs uppercase tracking-wide text-secondary-500">
                  <th className="px-4 py-3">Cluster</th>
                  <th className="px-4 py-3">Canonical ticket</th>
                  <th className="px-4 py-3">Members</th>
                  <th className="px-4 py-3">Canonical status</th>
                  <th className="px-4 py-3">Created</th>
                </tr>
              </thead>
              <tbody>
                {live.map((c) => (
                  <tr key={c.id} className="border-b border-secondary-100 last:border-0">
                    <td className="px-4 py-3">
                      <Link
                        href={`/admin/duplicates/${c.id}`}
                        className="font-mono font-medium text-primary-700 hover:text-primary-800"
                      >
                        {c.cluster_number}
                      </Link>
                    </td>
                    <td className="px-4 py-3 font-mono">{c.canonical?.ticket_number ?? '—'}</td>
                    <td className="px-4 py-3">{c.members.length}</td>
                    <td className="px-4 py-3">{c.canonical?.status ?? '—'}</td>
                    <td className="px-4 py-3 text-secondary-600">{formatDate(c.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </AppLayout>
  );
}

export default function AdminDuplicatesPage() {
  return (
    <RequireAuth>
      <AdminDuplicatesContent />
    </RequireAuth>
  );
}
