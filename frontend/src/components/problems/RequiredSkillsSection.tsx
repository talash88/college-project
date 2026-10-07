'use client';

import { useState } from 'react';
import { apiClient } from '@/lib/api-client';
import { API_ENDPOINTS } from '@/lib/api-config';
import { getApiErrorMessage } from '@/lib/auth-service';
import type { ProblemDetail } from '@/types/api';

const MATCH_STYLES: Record<string, string> = {
  EXACT: 'bg-green-100 text-green-800',
  HYBRID: 'bg-blue-100 text-blue-800',
  SEMANTIC: 'bg-secondary-100 text-secondary-700',
};

interface Props {
  problem: ProblemDetail;
  isAdmin: boolean;
  onChanged: () => Promise<void>;
}

export function RequiredSkillsSection({ problem, isAdmin, onChanged }: Props) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const skills = problem.required_skills ?? [];

  const handleReanalyze = async () => {
    setBusy(true);
    setError(null);
    try {
      await apiClient.post(API_ENDPOINTS.adminProblems.reanalyzeSkills(problem.id), {});
      await onChanged();
    } catch (err) {
      setError(getApiErrorMessage(err, 'Re-analysis failed.'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="card p-6">
      <h2 className="text-lg font-semibold text-secondary-900 mb-2">Required Skills</h2>

      {problem.required_skills_status === 'NOT_RUN' ||
      problem.required_skills_status === 'PROCESSING' ? (
        <p className="text-sm text-secondary-600">Skill analysis has not been run yet.</p>
      ) : problem.required_skills_status === 'FAILED' ? (
        <p className="text-sm text-secondary-600">
          Skill extraction could not be completed. The report was saved successfully.
        </p>
      ) : skills.length === 0 ? (
        <p className="text-sm text-secondary-600">
          No sufficiently relevant required skills were detected.
        </p>
      ) : (
        <ul className="space-y-2">
          {skills.map((s) => (
            <li
              key={s.id}
              className="flex flex-wrap items-center gap-2 rounded-lg border border-secondary-200 px-3 py-2"
            >
              <div className="flex-1 min-w-[10rem]">
                <p className="text-sm font-medium text-secondary-900">{s.skill_name ?? s.skill_id}</p>
                {s.skill_category && <p className="text-xs text-secondary-500">{s.skill_category}</p>}
              </div>
              <span className="text-sm font-semibold text-secondary-800">
                {(s.score * 100).toFixed(0)}%
              </span>
              <span
                className={`text-xs font-medium px-2 py-0.5 rounded-full ${
                  MATCH_STYLES[s.match_type] ?? 'bg-secondary-100 text-secondary-700'
                }`}
              >
                {s.match_type}
              </span>
              {s.reason && <p className="w-full text-xs text-secondary-500">{s.reason}</p>}
            </li>
          ))}
        </ul>
      )}

      {isAdmin && (
        <div className="mt-4 border-t border-secondary-100 pt-4">
          <button
            type="button"
            className="btn-secondary px-3 py-1.5 text-sm"
            disabled={busy}
            onClick={handleReanalyze}
          >
            {busy ? 'Working…' : 'Re-analyze'}
          </button>
          {error && (
            <div role="alert" className="mt-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
              {error}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
