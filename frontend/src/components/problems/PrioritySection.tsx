'use client';

import { useState } from 'react';
import { apiClient } from '@/lib/api-client';
import { API_ENDPOINTS } from '@/lib/api-config';
import { getApiErrorMessage } from '@/lib/auth-service';
import type { ProblemDetail } from '@/types/api';
import { PRIORITY_STYLES as LEVEL_STYLES } from '@/lib/status-styles';

const COMPONENT_LABELS: Record<string, string> = {
  severity: 'Severity',
  affected_people: 'Affected people',
  pending_age: 'Age',
  category_context: 'Category context',
  duplicate_impact: 'Duplicate contribution',
};

interface Props {
  problem: ProblemDetail;
  isAdmin: boolean;
  onChanged: () => Promise<void>;
}

export function PrioritySection({ problem, isAdmin, onChanged }: Props) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showDetails, setShowDetails] = useState(false);
  const analysis = problem.priority;

  const handleRecalculate = async () => {
    setBusy(true);
    setError(null);
    try {
      await apiClient.post(API_ENDPOINTS.adminProblems.recalculatePriority(problem.id), {});
      await onChanged();
    } catch (err) {
      setError(getApiErrorMessage(err, 'Recalculation failed.'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="card p-6">
      <h2 className="text-lg font-semibold text-secondary-900 mb-2">Priority Analysis</h2>

      {problem.priority_status === 'NOT_RUN' || problem.priority_status === 'PROCESSING' ? (
        <p className="text-sm text-secondary-600">Priority has not been calculated yet.</p>
      ) : problem.priority_status === 'FAILED' || !analysis || analysis.score == null ? (
        <p className="text-sm text-secondary-600">
          Priority scoring could not be completed. The report was saved successfully.
        </p>
      ) : (
        <div className="space-y-3">
          <div className="flex flex-wrap items-center gap-3">
            <span
              className={`text-sm font-semibold px-3 py-1 rounded-full ${
                LEVEL_STYLES[analysis.priority_level ?? ''] ?? 'bg-secondary-100 text-secondary-700'
              }`}
            >
              {analysis.priority_level}
            </span>
            <span className="text-2xl font-bold text-secondary-900">{Math.round(analysis.score)} / 100</span>
          </div>

          <div>
            <h3 className="text-sm font-medium text-secondary-700 mb-1">Why?</h3>
            <ul className="list-disc list-inside text-sm text-secondary-600 space-y-0.5">
              {analysis.reasons.map((reason) => (
                <li key={reason}>{reason.replace(/^\+\s*\d+:\s*/, '')}</li>
              ))}
            </ul>
          </div>

          <button
            type="button"
            className="text-sm font-medium text-primary-600 hover:text-primary-700"
            onClick={() => setShowDetails((v) => !v)}
          >
            {showDetails ? 'Hide component breakdown' : 'Show component breakdown'}
          </button>

          {showDetails && (
            <dl className="grid grid-cols-1 md:grid-cols-2 gap-3 text-sm">
              {(analysis.component_details.components ?? []).map((c) => (
                <div key={c.component} className="rounded-lg border border-secondary-200 p-3">
                  <dt className="font-medium text-secondary-800">
                    {COMPONENT_LABELS[c.component] ?? c.component}
                  </dt>
                  <dd className="text-secondary-600">
                    +{c.contribution} / {c.max_contribution} — {c.reason}
                  </dd>
                </div>
              ))}
              <div className="rounded-lg border border-secondary-200 p-3">
                <dt className="font-medium text-secondary-800">Duplicate contribution</dt>
                <dd className="text-secondary-600">
                  Contribution: {analysis.duplicate_component} — confirmed duplicate reports in the
                  same cluster raise the canonical report&apos;s priority.
                </dd>
              </div>
              <div className="rounded-lg border border-secondary-200 p-3 text-xs text-secondary-500">
                Algorithm {analysis.algorithm_version}
                {analysis.calculated_at
                  ? ` · Last calculated ${new Date(analysis.calculated_at).toLocaleString()}`
                  : ''}
              </div>
            </dl>
          )}
        </div>
      )}

      {isAdmin && (
        <div className="mt-4 border-t border-secondary-100 pt-4">
          <button
            type="button"
            className="btn-secondary px-3 py-1.5 text-sm"
            disabled={busy}
            onClick={handleRecalculate}
          >
            {busy ? 'Working…' : 'Recalculate'}
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
