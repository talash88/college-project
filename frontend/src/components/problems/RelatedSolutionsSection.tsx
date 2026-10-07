'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { apiClient } from '@/lib/api-client';
import { API_ENDPOINTS } from '@/lib/api-config';
import type { RelatedSolutionsResponse } from '@/types/api';

function formatScore(value: number): string {
  return `${Math.round(value * 100)}%`;
}

function formatDate(value: string | null): string {
  if (!value) return '—';
  return new Date(value).toLocaleDateString();
}

export function RelatedSolutionsSection({ problemId }: { problemId: string }) {
  const [data, setData] = useState<RelatedSolutionsResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const result = await apiClient.get<RelatedSolutionsResponse>(
          API_ENDPOINTS.problems.relatedSolutions(problemId)
        );
        if (!cancelled) setData(result);
      } catch {
        if (!cancelled) setData({ items: [], semantic_available: false });
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [problemId]);

  if (loading) {
    return (
      <div className="card p-6">
        <h2 className="text-lg font-semibold text-secondary-900">Related previously solved issues</h2>
        <p className="mt-2 text-sm text-secondary-600">Looking up solved issues…</p>
      </div>
    );
  }

  if (!data || data.items.length === 0) {
    return null;
  }

  return (
    <div className="card p-6">
      <h2 className="text-lg font-semibold text-secondary-900">Related previously solved issues</h2>
      <p className="mt-1 text-sm text-secondary-600">
        Informational assistance from the Knowledge Repository — these are not duplicates
        and change nothing about this report.
      </p>
      <ul className="mt-4 space-y-3">
        {data.items.map((item) => (
          <li key={item.entry.id} className="rounded-lg border border-secondary-200 p-4">
            <div className="flex flex-wrap items-center gap-2 text-xs">
              <span className="font-mono text-secondary-500">{item.entry.public_id}</span>
              {item.entry.final_category && (
                <span className="font-medium px-2 py-0.5 rounded-full bg-blue-100 text-blue-800">
                  {item.entry.final_category}
                </span>
              )}
              <span className="font-medium px-2 py-0.5 rounded-full bg-secondary-100 text-secondary-600">
                {formatScore(item.semantic_similarity)} similar
              </span>
            </div>
            <Link
              href={`/knowledge/${item.entry.public_id}`}
              className="mt-1 block font-medium text-primary-700 hover:text-primary-800"
            >
              {item.entry.title}
            </Link>
            <p className="mt-1 text-sm text-secondary-600">{item.entry.problem_preview}</p>
            <p className="mt-1 text-xs text-secondary-500">
              Resolved {formatDate(item.entry.published_at)}
            </p>
          </li>
        ))}
      </ul>
    </div>
  );
}
