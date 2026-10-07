'use client';

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { AppLayout } from '@/components/ui/AppLayout';
import { EmptyState, ErrorState, LoadingSkeleton } from '@/components/ui/Feedback';
import { apiClient } from '@/lib/api-client';
import { getApiErrorMessage } from '@/lib/auth-service';
import { formatDate } from '@/lib/format';
import { priorityStyle, problemStatusStyle } from '@/lib/status-styles';
import type { AssignedProblem } from '@/types/api';

export function WorklistPage({
  title,
  subtitle,
  emptyText,
  endpoint,
}: {
  title: string;
  subtitle: string;
  emptyText: string;
  endpoint: string;
}) {
  const [items, setItems] = useState<AssignedProblem[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      setItems(await apiClient.get<AssignedProblem[]>(endpoint));
    } catch (err) {
      setError(getApiErrorMessage(err, 'Could not load problems.'));
    }
  }, [endpoint]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <AppLayout>
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl lg:text-3xl font-bold text-secondary-900">{title}</h1>
          <p className="mt-1 text-secondary-600">{subtitle}</p>
        </div>

        {error ? (
          <ErrorState message={error} onRetry={load} />
        ) : items == null ? (
          <LoadingSkeleton lines={2} label="Loading problems" />
        ) : items.length === 0 ? (
          <EmptyState title="Nothing here yet" message={emptyText} />
        ) : (
          <ul className="space-y-3">
            {items.map((p) => (
              <li key={p.id} className="card p-4 hover:border-primary-300 transition-colors">
                <Link href={`/problems/${p.id}`} className="block space-y-1.5">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-mono text-xs text-secondary-500">{p.ticket_number}</span>
                    <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${problemStatusStyle(p.status)}`}>
                      {p.status}
                    </span>
                    {p.priority_level && (
                      <span
                        className={`text-xs font-medium px-2 py-0.5 rounded-full ${priorityStyle(p.priority_level)}`}
                      >
                        {p.priority_level}
                        {p.priority_score != null ? ` · ${Math.round(p.priority_score)}` : ''}
                      </span>
                    )}
                  </div>
                  <p className="font-medium text-secondary-900">{p.title}</p>
                  <p className="text-xs text-secondary-500">
                    {p.location_text}
                    {p.team_member_names.length > 0 ? ` · Team: ${p.team_member_names.join(', ')}` : ''}
                    {p.mentor_name ? ` · Mentor: ${p.mentor_name}` : ''}
                    {p.assigned_at ? ` · Assigned ${formatDate(p.assigned_at)}` : ''}
                  </p>
                </Link>
                {(p.status === 'ASSIGNED' || p.status === 'IN_PROGRESS') && (
                  <Link
                    href={`/problems/${p.id}/workspace`}
                    className="mt-2 inline-block text-xs font-medium text-primary-600 hover:text-primary-700"
                  >
                    Open team workspace →
                  </Link>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
    </AppLayout>
  );
}
