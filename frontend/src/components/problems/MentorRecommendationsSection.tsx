'use client';

import { useCallback, useEffect, useState } from 'react';
import { apiClient } from '@/lib/api-client';
import { API_ENDPOINTS } from '@/lib/api-config';
import { getApiErrorMessage } from '@/lib/auth-service';
import type {
  MentorCandidate,
  MentorRecommendations,
  ProblemDetail,
} from '@/types/api';

interface Props {
  problem: ProblemDetail;
  isAdmin: boolean;
  onChanged: () => Promise<void>;
}

function initials(name: string | null): string {
  if (!name) return '??';
  const parts = name.trim().split(/\s+/);
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

function AvailabilityBadge({ status }: { status: string | null }) {
  if (!status) return null;
  const styles =
    status === 'AVAILABLE'
      ? 'bg-green-100 text-green-800'
      : 'bg-yellow-100 text-yellow-800';
  return (
    <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${styles}`}>
      {status === 'AVAILABLE' ? 'Available' : 'Limited'}
    </span>
  );
}

function ScoreBar({ value }: { value: number }) {
  const pct = Math.max(0, Math.min(100, value));
  return (
    <div
      className="h-2 rounded-full bg-secondary-100 overflow-hidden"
      role="progressbar"
      aria-valuenow={Math.round(pct)}
      aria-valuemin={0}
      aria-valuemax={100}
    >
      <div className="h-full rounded-full bg-primary-500" style={{ width: `${pct}%` }} />
    </div>
  );
}

function MentorCard({
  mentor,
  rank,
  isAdmin,
}: {
  mentor: MentorCandidate;
  rank: number;
  isAdmin: boolean;
}) {
  const [expanded, setExpanded] = useState(rank === 0);
  return (
    <li
      className={`rounded-xl border p-4 ${
        rank === 0 ? 'border-primary-300 bg-primary-50/50' : 'border-secondary-200'
      }`}
    >
      <div className="flex items-center gap-3">
        <span
          className="w-10 h-10 rounded-full bg-primary-100 text-primary-700 font-semibold text-sm flex items-center justify-center flex-shrink-0"
          aria-hidden="true"
        >
          {initials(mentor.name)}
        </span>
        <div className="flex-1 min-w-0">
          <p className="font-medium text-secondary-900 truncate">
            {mentor.name ?? 'Faculty mentor'}
            {rank === 0 && (
              <span className="ml-2 text-xs font-medium px-2 py-0.5 rounded-full bg-primary-600 text-white">
                Top recommendation
              </span>
            )}
          </p>
          <p className="text-xs text-secondary-500 truncate">
            {[mentor.designation, mentor.specialization].filter(Boolean).join(' · ') || '—'}
          </p>
        </div>
        <div className="text-right flex-shrink-0">
          <p className="text-lg font-bold text-secondary-900">{Math.round(mentor.score)}</p>
          <p className="text-xs text-secondary-500">/ 100</p>
        </div>
      </div>

      <div className="mt-2">
        <ScoreBar value={mentor.score} />
      </div>

      <div className="mt-2 flex flex-wrap items-center gap-2 text-xs">
        <AvailabilityBadge status={mentor.availability} />
        {isAdmin && mentor.current_workload != null && mentor.max_workload != null && (
          <span className="text-secondary-500">
            Workload {mentor.current_workload}/{mentor.max_workload}
          </span>
        )}
        {isAdmin && (
          <span className="text-secondary-500">
            Semantic {Math.round(mentor.semantic_similarity * 100)}%
          </span>
        )}
      </div>

      {mentor.matched_skills.length > 0 && (
        <div className="flex flex-wrap gap-1.5 mt-2">
          {mentor.matched_skills
            .filter((s) => s.match_kind !== 'NONE')
            .map((s) => (
              <span
                key={s.name}
                className="text-xs px-2 py-0.5 rounded-full bg-secondary-100 text-secondary-700"
                title={s.proficiency_label ?? undefined}
              >
                {s.name}
                {s.proficiency_label ? ` · ${s.proficiency_label}` : ''}
              </span>
            ))}
        </div>
      )}

      <button
        type="button"
        className="mt-2 text-xs font-medium text-primary-600 hover:text-primary-700"
        onClick={() => setExpanded((v) => !v)}
        aria-expanded={expanded}
      >
        {expanded ? 'Hide why' : 'Why recommended?'}
      </button>
      {expanded && (
        <div className="mt-1.5 text-xs text-secondary-600 space-y-1.5">
          <ul className="list-disc list-inside space-y-0.5">
            {mentor.specialization && <li>Specialization: {mentor.specialization}</li>}
            {mentor.matched_skills.filter((s) => s.match_kind !== 'NONE').length > 0 && (
              <li>
                Skill match:{' '}
                {mentor.matched_skills
                  .filter((s) => s.match_kind !== 'NONE')
                  .map((s) => `${s.name}${s.proficiency_label ? ` (${s.proficiency_label})` : ''}`)
                  .join(', ')}
              </li>
            )}
            <li>Skill-match score {Math.round(mentor.skill_match_score)} / 30</li>
            <li>Specialization similarity {Math.round(mentor.specialization_score)} / 35</li>
          </ul>
          {isAdmin && (
            <dl className="grid grid-cols-2 md:grid-cols-3 gap-2">
              {[
                { label: 'Category', value: mentor.category_score, max: 15 },
                { label: 'Availability', value: mentor.availability_score, max: 10 },
                { label: 'Workload', value: mentor.workload_score, max: 10 },
              ].map((c) => (
                <div key={c.label} className="rounded-lg border border-secondary-200 bg-white p-2">
                  <dt className="font-medium text-secondary-800">
                    {c.label}: {c.value} / {c.max}
                  </dt>
                  <dd className="mt-1">
                    <ScoreBar value={(c.value / c.max) * 100} />
                  </dd>
                </div>
              ))}
            </dl>
          )}
        </div>
      )}
    </li>
  );
}

export function MentorRecommendationsSection({ problem, isAdmin, onChanged }: Props) {
  const [data, setData] = useState<MentorRecommendations | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await apiClient.get<MentorRecommendations>(
        API_ENDPOINTS.problems.mentorRecommendations(problem.id)
      );
      setData(result);
    } catch (err) {
      setError(getApiErrorMessage(err, 'Could not load mentor recommendations.'));
    } finally {
      setLoading(false);
    }
  }, [problem.id]);

  useEffect(() => {
    load();
  }, [load]);

  const handleRecalculate = async () => {
    setBusy(true);
    setError(null);
    try {
      const result = await apiClient.post<MentorRecommendations>(
        API_ENDPOINTS.adminProblems.recalculateMentor(problem.id),
        {}
      );
      setData(result);
      await onChanged();
    } catch (err) {
      setError(getApiErrorMessage(err, 'Recalculation failed.'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="card p-6">
      <h2 className="text-lg font-semibold text-secondary-900 mb-2">Recommended Faculty Mentor</h2>

      {loading ? (
        <div className="space-y-3" aria-label="Loading mentor recommendations">
          <div className="h-4 rounded bg-secondary-100 animate-pulse w-1/2" />
          <div className="h-24 rounded-lg bg-secondary-100 animate-pulse" />
        </div>
      ) : error && !data ? (
        <div className="space-y-2">
          <p className="text-sm text-secondary-600" role="alert">{error}</p>
          <button type="button" className="btn-secondary px-3 py-1.5 text-sm" onClick={load}>
            Retry
          </button>
        </div>
      ) : data?.canonical ? (
        <p className="text-sm text-secondary-600">
          Recommendation handled through canonical issue{' '}
          <span className="font-mono font-medium">{data.canonical.ticket_number}</span>.
        </p>
      ) : data && data.mentors.length > 0 ? (
        <div className="space-y-4">
          <ol className="space-y-3">
            {data.mentors.map((m, i) => (
              <MentorCard key={m.id} mentor={m} rank={i} isAdmin={isAdmin} />
            ))}
          </ol>
          <p className="text-xs text-secondary-500">
            Advisory recommendations only — scores are not probabilities. Assignment happens in the
            next step.
          </p>
        </div>
      ) : (
        <p className="text-sm text-secondary-600" role="status">
          {data?.status === 'NO_ELIGIBLE_CANDIDATES'
            ? 'No eligible mentors found for a confident recommendation.'
            : data?.status === 'INSUFFICIENT_DATA'
              ? 'Insufficient skill requirements for confident recommendation.'
              : data?.status === 'FAILED'
                ? 'Mentor recommendation could not be completed. The report itself is unaffected.'
                : 'Mentor recommendation has not run yet.'}
        </p>
      )}

      {isAdmin && (
        <div className="mt-4 border-t border-secondary-100 pt-4 space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              className="btn-secondary px-3 py-1.5 text-sm"
              disabled={busy}
              onClick={handleRecalculate}
            >
              {busy ? 'Working…' : 'Recalculate mentor'}
            </button>
            <span
              className="text-xs font-medium px-2 py-1 rounded bg-secondary-100 text-secondary-500 cursor-not-allowed"
              title="Mentor assignment arrives in Step 9"
            >
              Assign mentor (next step)
            </span>
          </div>
          {error && data && (
            <div
              role="alert"
              className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700"
            >
              {error}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
