'use client';

import Link from 'next/link';
import { useParams } from 'next/navigation';
import { useEffect, useState } from 'react';
import { RequireAuth } from '@/components/auth/RequireAuth';
import { AppLayout } from '@/components/ui/AppLayout';
import { apiClient } from '@/lib/api-client';
import { API_ENDPOINTS } from '@/lib/api-config';
import { getApiErrorMessage } from '@/lib/auth-service';
import type { KnowledgeEntryDetail } from '@/types/api';

function formatScore(value: number): string {
  return `${Math.round(value * 100)}%`;
}

function formatDate(value: string | null): string {
  if (!value) return '—';
  return new Date(value).toLocaleString();
}

function formatDuration(minutes: number | null): string {
  if (minutes == null) return '—';
  if (minutes < 60) return `${minutes} min`;
  const hours = Math.floor(minutes / 60);
  if (hours < 48) return `${hours} hr`;
  return `${Math.floor(hours / 24)} days`;
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="card p-5 md:p-6">
      <h2 className="text-lg font-semibold text-secondary-900">{title}</h2>
      <div className="mt-2 text-sm text-secondary-700 whitespace-pre-wrap">{children}</div>
    </section>
  );
}

function KnowledgeDetailContent({ refId }: { refId: string }) {
  const [data, setData] = useState<KnowledgeEntryDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [downloading, setDownloading] = useState<string | null>(null);

  const handleEvidenceDownload = async (file: {
    file_id: string;
    original_filename: string;
    mime_type: string;
  }) => {
    setDownloading(file.file_id);
    try {
      const response = await apiClient.instance.get(
        API_ENDPOINTS.knowledge.evidenceDownload(refId, file.file_id),
        { responseType: 'blob' }
      );
      const url = window.URL.createObjectURL(new Blob([response.data], { type: file.mime_type }));
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = file.original_filename;
      anchor.click();
      window.URL.revokeObjectURL(url);
    } catch {
      setError('Evidence download failed.');
    } finally {
      setDownloading(null);
    }
  };

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const result = await apiClient.get<KnowledgeEntryDetail>(
          API_ENDPOINTS.knowledge.detail(refId)
        );
        if (!cancelled) setData(result);
      } catch (err) {
        if (!cancelled) setError(getApiErrorMessage(err, 'Failed to load this article.'));
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [refId]);

  if (loading) {
    return (
      <AppLayout>
        <div className="card p-6 text-sm text-secondary-600">Loading article…</div>
      </AppLayout>
    );
  }

  if (error || !data) {
    return (
      <AppLayout>
        <div className="card p-6">
          <p className="text-sm text-red-700" role="alert">
            {error ?? 'Article not found.'}
          </p>
          <Link href="/knowledge" className="mt-3 inline-block text-primary-700 hover:text-primary-800 text-sm">
            ← Back to Knowledge Repository
          </Link>
        </div>
      </AppLayout>
    );
  }

  return (
    <AppLayout>
      <div className="space-y-5">
        <Link href="/knowledge" className="text-sm text-primary-700 hover:text-primary-800">
          ← Knowledge Repository
        </Link>
        <div>
          <div className="flex flex-wrap items-center gap-2 text-xs">
            <span className="font-mono text-secondary-500">{data.public_id}</span>
            {data.final_category && (
              <span className="font-medium px-2 py-0.5 rounded-full bg-blue-100 text-blue-800">
                {data.final_category}
              </span>
            )}
            {data.location_summary && (
              <span className="text-secondary-500">{data.location_summary}</span>
            )}
          </div>
          <h1 className="mt-2 text-2xl lg:text-3xl font-bold text-secondary-900">{data.title}</h1>
          <p className="mt-1 text-sm text-secondary-500">
            Published {formatDate(data.published_at)} · Resolution took{' '}
            {formatDuration(data.resolution_duration_minutes)}
          </p>
        </div>

        <Section title="Problem">{data.problem_summary}</Section>
        {data.root_cause && <Section title="Root Cause">{data.root_cause}</Section>}
        <Section title="Verified Solution">{data.solution_summary}</Section>
        <Section title="Work Performed">{data.work_performed}</Section>
        {data.testing_performed && (
          <Section title="Testing / Validation">{data.testing_performed}</Section>
        )}
        {data.deployment_notes && (
          <Section title="Deployment Notes">{data.deployment_notes}</Section>
        )}
        {data.known_limitations && (
          <Section title="Known Limitations">{data.known_limitations}</Section>
        )}

        {data.skills.length > 0 && (
          <section className="card p-5 md:p-6">
            <h2 className="text-lg font-semibold text-secondary-900">Required Skills</h2>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {data.skills.map((s) => (
                <span
                  key={s.skill_id}
                  className="text-xs px-2 py-0.5 rounded-full bg-primary-50 text-primary-700"
                >
                  {s.name}
                </span>
              ))}
            </div>
          </section>
        )}

        <section className="card p-5 md:p-6">
          <h2 className="text-lg font-semibold text-secondary-900">Resolution Information</h2>
          <dl className="mt-2 grid grid-cols-1 sm:grid-cols-2 gap-2 text-sm">
            <div>
              <dt className="text-secondary-500">Solved by</dt>
              <dd className="font-medium text-secondary-900">
                {data.team_names.length > 0 ? data.team_names.join(', ') : '—'}
              </dd>
            </div>
            <div>
              <dt className="text-secondary-500">Mentored by</dt>
              <dd className="font-medium text-secondary-900">
                {data.mentor_name ?? '—'}
                {data.mentor_designation ? ` · ${data.mentor_designation}` : ''}
              </dd>
            </div>
          </dl>
        </section>

        {data.evidence_files.length > 0 && (
          <section className="card p-5 md:p-6">
            <h2 className="text-lg font-semibold text-secondary-900">Safe Evidence</h2>
            <ul className="mt-2 space-y-2 text-sm">
              {data.evidence_files.map((f) => (
                <li key={f.file_id}>
                  <button
                    type="button"
                    onClick={() => handleEvidenceDownload(f)}
                    disabled={downloading === f.file_id}
                    className="text-primary-700 hover:text-primary-800 disabled:opacity-50"
                  >
                    {downloading === f.file_id ? 'Downloading…' : f.original_filename}
                  </button>{' '}
                  <span className="text-secondary-500">
                    ({f.mime_type}, {Math.round(f.size_bytes / 1024)} KB)
                  </span>
                </li>
              ))}
            </ul>
          </section>
        )}

        {data.related.length > 0 && (
          <section className="card p-5 md:p-6">
            <h2 className="text-lg font-semibold text-secondary-900">Related Knowledge</h2>
            <ul className="mt-2 space-y-3">
              {data.related.map((r) => (
                <li key={r.entry.id} className="rounded-lg border border-secondary-200 p-3">
                  <Link
                    href={`/knowledge/${r.entry.public_id}`}
                    className="font-medium text-primary-700 hover:text-primary-800 text-sm"
                  >
                    {r.entry.title}
                  </Link>
                  <p className="text-xs text-secondary-500">
                    {r.entry.public_id} · {formatScore(r.semantic_similarity)} similar
                  </p>
                </li>
              ))}
            </ul>
          </section>
        )}
      </div>
    </AppLayout>
  );
}

export default function KnowledgeDetailPage() {
  const params = useParams<{ id: string }>();
  const refId = params.id;
  return (
    <RequireAuth>
      <KnowledgeDetailContent refId={refId} />
    </RequireAuth>
  );
}
