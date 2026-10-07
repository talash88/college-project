'use client';

import { useCallback, useEffect, useState } from 'react';
import { apiClient } from '@/lib/api-client';
import { API_ENDPOINTS } from '@/lib/api-config';
import { getApiErrorMessage } from '@/lib/auth-service';
import type { ProblemDetail, TeamMember, TeamOption, TeamRecommendations } from '@/types/api';

interface Props {
  problem: ProblemDetail;
  isAdmin: boolean;
  onChanged: () => Promise<void>;
}

function initials(name: string): string {
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

function ScoreBar({ value, tone }: { value: number; tone: 'primary' | 'green' }) {
  const pct = Math.max(0, Math.min(100, value));
  const fill = tone === 'green' ? 'bg-green-500' : 'bg-primary-500';
  return (
    <div
      className="h-2 rounded-full bg-secondary-100 overflow-hidden"
      role="progressbar"
      aria-valuenow={Math.round(pct)}
      aria-valuemin={0}
      aria-valuemax={100}
    >
      <div className={`h-full rounded-full ${fill}`} style={{ width: `${pct}%` }} />
    </div>
  );
}

function MemberCard({ member, isAdmin }: { member: TeamMember; isAdmin: boolean }) {
  const [expanded, setExpanded] = useState(false);
  return (
    <li className="rounded-lg border border-secondary-200 p-3">
      <div className="flex items-center gap-3">
        <span
          className="w-9 h-9 rounded-full bg-primary-100 text-primary-700 font-semibold text-sm flex items-center justify-center flex-shrink-0"
          aria-hidden="true"
        >
          {initials(member.name)}
        </span>
        <div className="flex-1 min-w-0">
          <p className="font-medium text-secondary-900 truncate">{member.name}</p>
          <div className="flex flex-wrap items-center gap-2 mt-0.5">
            <AvailabilityBadge status={member.availability} />
            {isAdmin && member.current_workload != null && member.max_workload != null && (
              <span className="text-xs text-secondary-500">
                Workload {member.current_workload}/{member.max_workload}
              </span>
            )}
            {isAdmin && member.individual_score != null && (
              <span className="text-xs text-secondary-500">
                Solo score {Math.round(member.individual_score)}
              </span>
            )}
          </div>
        </div>
      </div>
      {member.covered_skills.length > 0 && (
        <div className="flex flex-wrap gap-1.5 mt-2">
          {member.covered_skills.map((s) => (
            <span
              key={s.name}
              className="text-xs px-2 py-0.5 rounded-full bg-secondary-100 text-secondary-700"
              title={s.proficiency_label ?? undefined}
            >
              {s.name}
              {s.proficiency_label ? ` · ${s.proficiency_label}` : ''}
              {s.verified ? ' ✓' : ''}
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
        <ul className="mt-1.5 space-y-1 text-xs text-secondary-600 list-disc list-inside">
          {member.covered_skills.map((s) => (
            <li key={s.name}>
              {s.proficiency_label ?? 'Skilled'} in {s.name}
              {s.relevance != null && s.relevance >= 0.7 ? ' (high-relevance requirement)' : ''}
              {s.verified ? ' (verified)' : ''}
            </li>
          ))}
          {member.high_relevance_covered.length > 0 && (
            <li>Covers {member.high_relevance_covered.length} high-relevance requirement(s)</li>
          )}
          {member.covered_skills.length === 0 && <li>Supports team balance and capacity</li>}
        </ul>
      )}
    </li>
  );
}

function OptionCard({
  option,
  index,
  isAdmin,
}: {
  option: TeamOption;
  index: number;
  isAdmin: boolean;
}) {
  const [showBreakdown, setShowBreakdown] = useState(index === 0);
  const components = [
    { label: 'Skill coverage', value: option.skill_coverage_score, max: 50 },
    { label: 'Proficiency', value: option.proficiency_score, max: 20 },
    { label: 'Availability', value: option.availability_score, max: 10 },
    { label: 'Workload balance', value: option.workload_score, max: 10 },
    { label: 'Verified skills', value: option.verified_skill_score, max: 5 },
    { label: 'Domain context', value: option.domain_score, max: 5 },
  ];
  return (
    <li
      className={`rounded-xl border p-4 ${
        index === 0 ? 'border-primary-300 bg-primary-50/50' : 'border-secondary-200'
      }`}
    >
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="font-semibold text-secondary-900">Option {index + 1}</h3>
        {index === 0 && (
          <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-primary-600 text-white">
            Top recommendation
          </span>
        )}
        <span className="ml-auto text-sm text-secondary-600">
          Overall score <strong className="text-secondary-900">{Math.round(option.score)}</strong> / 100
        </span>
      </div>
      <div className="mt-2">
        <ScoreBar value={option.score} tone={index === 0 ? 'primary' : 'green'} />
      </div>
      <div className="mt-2 text-sm">
        <span className="text-secondary-600">Skill coverage </span>
        <strong className="text-secondary-900">{Math.round(option.coverage_percent)}%</strong>
      </div>
      <div className="mt-1">
        <ScoreBar value={option.coverage_percent} tone="green" />
      </div>

      <ul className="mt-3 space-y-2">
        {option.members.map((m, mi) => (
          <MemberCard key={m.user_id ?? `${m.name}-${mi}`} member={m} isAdmin={isAdmin} />
        ))}
      </ul>

      {option.missing_skills.length > 0 && (
        <p className="mt-2 text-xs text-secondary-600">
          Missing: {option.missing_skills.join(', ')}
        </p>
      )}

      {isAdmin && (
        <div className="mt-2">
          <button
            type="button"
            className="text-xs font-medium text-primary-600 hover:text-primary-700"
            onClick={() => setShowBreakdown((v) => !v)}
          >
            {showBreakdown ? 'Hide score breakdown' : 'Show score breakdown'}
          </button>
          {showBreakdown && (
            <dl className="mt-2 grid grid-cols-1 md:grid-cols-2 gap-2 text-xs">
              {components.map((c) => (
                <div key={c.label} className="rounded-lg border border-secondary-200 bg-white p-2">
                  <dt className="font-medium text-secondary-800">
                    {c.label}: {c.value} / {c.max}
                  </dt>
                  <dd className="mt-1">
                    <ScoreBar value={(c.value / c.max) * 100} tone="primary" />
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

export function TeamRecommendationsSection({ problem, isAdmin, onChanged }: Props) {
  const [data, setData] = useState<TeamRecommendations | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await apiClient.get<TeamRecommendations>(
        API_ENDPOINTS.problems.teamRecommendations(problem.id)
      );
      setData(result);
    } catch (err) {
      setError(getApiErrorMessage(err, 'Could not load team recommendations.'));
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
      const result = await apiClient.post<TeamRecommendations>(
        API_ENDPOINTS.adminProblems.recalculateTeam(problem.id),
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
      <h2 className="text-lg font-semibold text-secondary-900 mb-2">Recommended Student Team</h2>

      {loading ? (
        <div className="space-y-3" aria-label="Loading team recommendations">
          <div className="h-4 rounded bg-secondary-100 animate-pulse w-2/3" />
          <div className="h-20 rounded-lg bg-secondary-100 animate-pulse" />
          <div className="h-20 rounded-lg bg-secondary-100 animate-pulse" />
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
      ) : data && data.options.length > 0 ? (
        <div className="space-y-4">
          <ol className="space-y-3">
            {data.options.map((o, i) => (
              <OptionCard key={o.id} option={o} index={i} isAdmin={isAdmin} />
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
            ? 'No eligible solvers found for a confident recommendation.'
            : data?.status === 'INSUFFICIENT_DATA'
              ? 'Insufficient skill requirements for confident recommendation.'
              : data?.status === 'FAILED'
                ? 'Team recommendation could not be completed. The report itself is unaffected.'
                : 'Team recommendation has not run yet.'}
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
              {busy ? 'Working…' : 'Recalculate team'}
            </button>
            <span
              className="text-xs font-medium px-2 py-1 rounded bg-secondary-100 text-secondary-500 cursor-not-allowed"
              title="Team assignment arrives in Step 9"
            >
              Assign team (next step)
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
