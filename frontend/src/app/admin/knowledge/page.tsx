'use client';

import Link from 'next/link';
import { useCallback, useEffect, useState } from 'react';
import { RequireAuth } from '@/components/auth/RequireAuth';
import { AppLayout } from '@/components/ui/AppLayout';
import { apiClient } from '@/lib/api-client';
import { API_ENDPOINTS } from '@/lib/api-config';
import { getApiErrorMessage } from '@/lib/auth-service';
import type { AdminKnowledgeEntry } from '@/types/api';

const STATUSES = ['', 'PUBLISHED', 'FAILED', 'ARCHIVED'] as const;

function formatDate(value: string | null): string {
  if (!value) return '—';
  return new Date(value).toLocaleString();
}

function AdminKnowledgeContent() {
  const [entries, setEntries] = useState<AdminKnowledgeEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<(typeof STATUSES)[number]>('');
  const [busy, setBusy] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      if (status) params.set('publication_status', status);
      const query = params.toString();
      const result = await apiClient.get<AdminKnowledgeEntry[]>(
        `${API_ENDPOINTS.adminKnowledge.base}${query ? `?${query}` : ''}`
      );
      setEntries(result);
    } catch (err) {
      setError(getApiErrorMessage(err, 'Failed to load knowledge entries.'));
    } finally {
      setLoading(false);
    }
  }, [status]);

  useEffect(() => {
    load();
  }, [load]);

  const act = async (id: string, action: 'retry' | 'archive' | 'unarchive', label: string) => {
    setBusy(id);
    setNotice(null);
    try {
      if (action === 'retry') {
        await apiClient.post(API_ENDPOINTS.adminKnowledge.retry(id));
      } else if (action === 'archive') {
        await apiClient.patch(API_ENDPOINTS.adminKnowledge.archive(id));
      } else {
        await apiClient.patch(API_ENDPOINTS.adminKnowledge.unarchive(id));
      }
      setNotice(`${label} done.`);
      await load();
    } catch (err) {
      setNotice(getApiErrorMessage(err, `${label} failed.`));
    } finally {
      setBusy(null);
    }
  };

  return (
    <AppLayout>
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl lg:text-3xl font-bold text-secondary-900">
            Knowledge Administration
          </h1>
          <p className="mt-1 text-secondary-600">
            Published articles, failed publications, and archived entries. Retry failures or
            archive outdated articles — the source reports are never deleted.
          </p>
        </div>

        <div className="card p-4 md:p-6 flex flex-col sm:flex-row gap-3 sm:items-end">
          <label className="block sm:w-64">
            <span className="label">Publication status</span>
            <select
              className="input-field"
              value={status}
              onChange={(e) => setStatus(e.target.value as (typeof STATUSES)[number])}
              aria-label="Filter by publication status"
            >
              <option value="">All statuses</option>
              {STATUSES.filter(Boolean).map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </label>
          {notice && (
            <p className="text-sm text-secondary-700" role="status">
              {notice}
            </p>
          )}
        </div>

        {loading ? (
          <div className="card p-6 text-sm text-secondary-600">Loading entries…</div>
        ) : error ? (
          <div className="card p-6 text-sm text-red-700" role="alert">
            {error}
          </div>
        ) : entries.length === 0 ? (
          <div className="card p-6 text-sm text-secondary-600">
            No knowledge entries yet. Articles appear here automatically when verified
            reports are closed.
          </div>
        ) : (
          <div className="card overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead>
                <tr className="border-b border-secondary-200 text-left text-xs uppercase tracking-wide text-secondary-500">
                  <th className="px-4 py-3">Article</th>
                  <th className="px-4 py-3">Ticket</th>
                  <th className="px-4 py-3">Status</th>
                  <th className="px-4 py-3">Published</th>
                  <th className="px-4 py-3">Actions</th>
                </tr>
              </thead>
              <tbody>
                {entries.map((e) => (
                  <tr key={e.id} className="border-b border-secondary-100 last:border-0">
                    <td className="px-4 py-3">
                      <Link
                        href={`/knowledge/${e.public_id}`}
                        className="font-medium text-primary-700 hover:text-primary-800"
                      >
                        {e.title}
                      </Link>
                      <p className="font-mono text-xs text-secondary-500">{e.public_id}</p>
                      {e.failure_reason && (
                        <p className="text-xs text-red-700">Failed: {e.failure_reason}</p>
                      )}
                    </td>
                    <td className="px-4 py-3 font-mono text-xs">{e.problem_ticket ?? '—'}</td>
                    <td className="px-4 py-3">
                      <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-secondary-100 text-secondary-700">
                        {e.publication_status}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-secondary-600">{formatDate(e.published_at)}</td>
                    <td className="px-4 py-3">
                      <div className="flex flex-wrap gap-2">
                        {e.publication_status === 'FAILED' && (
                          <button
                            type="button"
                            className="btn-secondary px-3 py-1 text-xs"
                            disabled={busy === e.id}
                            onClick={() => act(e.id, 'retry', 'Retry')}
                          >
                            Retry
                          </button>
                        )}
                        {e.publication_status === 'ARCHIVED' ? (
                          <button
                            type="button"
                            className="btn-secondary px-3 py-1 text-xs"
                            disabled={busy === e.id}
                            onClick={() => act(e.id, 'unarchive', 'Unarchive')}
                          >
                            Unarchive
                          </button>
                        ) : (
                          e.publication_status === 'PUBLISHED' && (
                            <button
                              type="button"
                              className="btn-secondary px-3 py-1 text-xs"
                              disabled={busy === e.id}
                              onClick={() => act(e.id, 'archive', 'Archive')}
                            >
                              Archive
                            </button>
                          )
                        )}
                      </div>
                    </td>
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

export default function AdminKnowledgePage() {
  return (
    <RequireAuth roles={['ADMIN']}>
      <AdminKnowledgeContent />
    </RequireAuth>
  );
}
