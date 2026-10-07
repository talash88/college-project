'use client';

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { apiClient } from '@/lib/api-client';
import { API_ENDPOINTS } from '@/lib/api-config';
import { getApiErrorMessage } from '@/lib/auth-service';
import type {
  DuplicateCandidate,
  OwnerDuplicatesResponse,
  ProblemDetail,
} from '@/types/api';
import { DUPLICATE_DECISION_STYLES, problemStatusStyle } from '@/lib/status-styles';

interface Props {
  problem: ProblemDetail;
  isAdmin: boolean;
  onChanged: () => Promise<void>;
}

function formatScore(value: number): string {
  return `${Math.round(value * 100)}%`;
}

function statusBadge(status: string): string {
  // Duplicate decisions use the decision palette; problem statuses (e.g. the
  // counterpart's APPROVED/ASSIGNED state) use the central problem colors.
  if (status in DUPLICATE_DECISION_STYLES) {
    return DUPLICATE_DECISION_STYLES[status];
  }
  return problemStatusStyle(status);
}

export function DuplicatesSection({ problem, isAdmin, onChanged }: Props) {
  const [data, setData] = useState<OwnerDuplicatesResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [notes, setNotes] = useState<Record<string, string>>({});

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await apiClient.get<OwnerDuplicatesResponse>(
        API_ENDPOINTS.problems.duplicates(problem.id)
      );
      setData(result);
    } catch (err) {
      setError(getApiErrorMessage(err, 'Could not load similar-report information.'));
    } finally {
      setLoading(false);
    }
  }, [problem.id]);

  useEffect(() => {
    load();
  }, [load]);

  const canonical = problem.canonical ?? data?.canonical ?? null;
  const isConfirmedDuplicate = problem.status === 'DUPLICATE' && canonical != null;
  const analysisStatus = data?.analysis_status ?? problem.duplicate_status;
  const candidates = data?.candidates ?? [];

  const handleReview = async (candidate: DuplicateCandidate, action: 'confirm' | 'reject') => {
    setBusy(candidate.id);
    setError(null);
    try {
      const endpoint =
        action === 'confirm'
          ? API_ENDPOINTS.adminDuplicates.confirm(candidate.id)
          : API_ENDPOINTS.adminDuplicates.reject(candidate.id);
      await apiClient.post(endpoint, { review_note: notes[candidate.id]?.trim() || null });
      await load();
      await onChanged();
    } catch (err) {
      setError(
        getApiErrorMessage(err, action === 'confirm' ? 'Confirmation failed.' : 'Rejection failed.')
      );
    } finally {
      setBusy(null);
    }
  };

  const handleReanalyze = async () => {
    setBusy('reanalyze');
    setError(null);
    try {
      const result = await apiClient.post<OwnerDuplicatesResponse>(
        API_ENDPOINTS.adminDuplicates.reanalyze(problem.id),
        {}
      );
      setData(result);
      await onChanged();
    } catch (err) {
      setError(getApiErrorMessage(err, 'Re-analysis failed.'));
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="card p-6">
      <h2 className="text-lg font-semibold text-secondary-900 mb-2">Similar Reports</h2>

      {loading ? (
        <p className="text-sm text-secondary-600">Checking for similar reports…</p>
      ) : error && !data ? (
        <p className="text-sm text-secondary-600">{error}</p>
      ) : (
        <div className="space-y-4">
          {isConfirmedDuplicate && canonical && (
            <div
              role="status"
              className="rounded-lg border border-purple-200 bg-purple-50 px-4 py-3 text-sm"
            >
              <p className="font-medium text-purple-900">
                This report has been linked to an existing campus issue.
              </p>
              <dl className="mt-2 grid grid-cols-1 md:grid-cols-2 gap-2 text-purple-800">
                <div>
                  <dt className="text-xs uppercase tracking-wide text-purple-500">Canonical ticket</dt>
                  <dd className="font-mono font-medium">{canonical.ticket_number}</dd>
                </div>
                <div>
                  <dt className="text-xs uppercase tracking-wide text-purple-500">Canonical status</dt>
                  <dd className="font-medium">{canonical.status}</dd>
                </div>
                <div className="md:col-span-2">
                  <dt className="text-xs uppercase tracking-wide text-purple-500">Canonical title</dt>
                  <dd className="font-medium">{canonical.title}</dd>
                </div>
                <div className="md:col-span-2">
                  <dt className="text-xs uppercase tracking-wide text-purple-500">Location</dt>
                  <dd>{canonical.location_text}</dd>
                </div>
              </dl>
              {isAdmin && (
                <Link
                  href={`/problems/${canonical.id}`}
                  className="mt-2 inline-block text-sm font-medium text-purple-700 hover:text-purple-800"
                >
                  Open canonical report →
                </Link>
              )}
            </div>
          )}

          {!isConfirmedDuplicate && (
            <p className="text-sm text-secondary-600" role="status">
              {analysisStatus === 'POSSIBLE_DUPLICATES' && candidates.length > 0
                ? 'Possible similar issue found — an administrator reviews every suggestion before anything is linked.'
                : analysisStatus === 'FAILED'
                  ? 'Similarity analysis failed. Your report was saved successfully; an administrator can re-run the check.'
                  : analysisStatus === 'NOT_RUN' ||
                      analysisStatus === 'PROCESSING' ||
                      analysisStatus === 'COMPLETED'
                    ? 'Analyzing similar reports…'
                    : 'No similar issue found.'}
            </p>
          )}

          {candidates.length > 0 && (
            <ul className="space-y-3">
              {candidates.map((c) => (
                <li
                  key={c.id}
                  className="rounded-lg border border-secondary-200 p-4 text-sm space-y-2"
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-mono text-xs text-secondary-500">
                      {c.candidate?.ticket_number ?? '—'}
                    </span>
                    <span
                      className={`text-xs font-medium px-2 py-0.5 rounded-full ${statusBadge(
                        c.candidate?.status ?? ''
                      )}`}
                    >
                      {c.candidate?.status ?? 'Unknown'}
                    </span>
                    <span
                      className={`text-xs font-medium px-2 py-0.5 rounded-full ${statusBadge(
                        c.decision_status
                      )}`}
                    >
                      {c.decision_status}
                    </span>
                    <span
                      title="Diagnostic signal strength — every suggestion still needs admin review"
                      className={`text-xs font-medium px-2 py-0.5 rounded-full ${
                        c.match_strength === 'STRONG'
                          ? 'bg-amber-100 text-amber-800'
                          : 'bg-secondary-100 text-secondary-600'
                      }`}
                    >
                      {c.match_strength === 'STRONG' ? 'Strong match' : 'Possible match'}
                    </span>
                  </div>
                  <p className="font-medium text-secondary-900">
                    {isAdmin && c.candidate ? (
                      <Link
                        href={`/problems/${c.candidate.id}`}
                        className="text-primary-700 hover:text-primary-800"
                      >
                        {c.candidate.title}
                      </Link>
                    ) : (
                      (c.candidate?.title ?? 'Similar report')
                    )}
                  </p>
                  <dl className="grid grid-cols-2 md:grid-cols-4 gap-2 text-xs text-secondary-600">
                    <div>
                      <dt>Semantic similarity</dt>
                      <dd className="font-semibold text-secondary-900">
                        {formatScore(c.semantic_similarity)}
                      </dd>
                    </div>
                    <div>
                      <dt>Final match score</dt>
                      <dd className="font-semibold text-secondary-900">
                        {formatScore(c.final_match_score)}
                      </dd>
                    </div>
                    {isAdmin && (
                      <>
                        <div>
                          <dt>Location support</dt>
                          <dd className="font-semibold text-secondary-900">
                            {c.location_score == null ? '—' : formatScore(c.location_score)}
                          </dd>
                        </div>
                        <div>
                          <dt>Category support</dt>
                          <dd className="font-semibold text-secondary-900">
                            {c.category_support_score == null
                              ? '—'
                              : formatScore(c.category_support_score)}
                          </dd>
                        </div>
                      </>
                    )}
                  </dl>
                  {isAdmin && (
                    <div className="space-y-2 border-t border-secondary-100 pt-3">
                      {c.review_note && (
                        <p className="text-xs text-secondary-500">
                          Review note: {c.review_note}
                        </p>
                      )}
                      {c.decision_status === 'PENDING' ? (
                        <>
                          <input
                            className="input-field text-sm"
                            placeholder="Review note (optional)"
                            value={notes[c.id] ?? ''}
                            onChange={(e) =>
                              setNotes((prev) => ({ ...prev, [c.id]: e.target.value }))
                            }
                            disabled={busy != null}
                            maxLength={1000}
                            aria-label={`Review note for ${c.candidate?.ticket_number ?? 'candidate'}`}
                          />
                          <div className="flex flex-wrap gap-2">
                            <button
                              type="button"
                              className="btn-primary px-3 py-1.5 text-sm"
                              disabled={busy != null}
                              onClick={() => handleReview(c, 'confirm')}
                            >
                              {busy === c.id ? 'Working…' : 'Confirm Duplicate'}
                            </button>
                            <button
                              type="button"
                              className="btn-secondary px-3 py-1.5 text-sm"
                              disabled={busy != null}
                              onClick={() => handleReview(c, 'reject')}
                            >
                              Reject Match
                            </button>
                          </div>
                        </>
                      ) : (
                        <p className="text-xs text-secondary-500">
                          Decided: {c.decision_status}
                          {c.reviewed_at
                            ? ` · ${new Date(c.reviewed_at).toLocaleString()}`
                            : ''}
                        </p>
                      )}
                    </div>
                  )}
                </li>
              ))}
            </ul>
          )}

          {isAdmin && (
            <div className="border-t border-secondary-100 pt-4">
              <button
                type="button"
                className="btn-secondary px-3 py-1.5 text-sm"
                disabled={busy != null}
                onClick={handleReanalyze}
              >
                {busy === 'reanalyze' ? 'Working…' : 'Re-analyze'}
              </button>
              {error && (
                <div
                  role="alert"
                  className="mt-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700"
                >
                  {error}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
