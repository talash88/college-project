'use client';

import { useState, type FormEvent } from 'react';
import { apiClient } from '@/lib/api-client';
import { API_ENDPOINTS } from '@/lib/api-config';
import { getApiErrorMessage } from '@/lib/auth-service';
import {
  CATEGORY_LABELS,
  categoryLabel,
  type ProblemClassification,
  type ProblemDetail,
} from '@/types/api';

function confidenceBand(confidence: number | null): string {
  if (confidence == null) return 'Unknown confidence';
  if (confidence >= 0.8) return 'High confidence';
  if (confidence >= 0.6) return 'Moderate confidence';
  return 'Low confidence';
}

interface Props {
  problem: ProblemDetail;
  isAdmin: boolean;
  onChanged: () => Promise<void>;
}

export function ClassificationSection({ problem, isAdmin, onChanged }: Props) {
  const classification: ProblemClassification | null = problem.classification;
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [changing, setChanging] = useState(false);
  const [finalCategory, setFinalCategory] = useState('');
  const [reviewNote, setReviewNote] = useState('');

  const runAction = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    setError(null);
    try {
      await fn();
      await onChanged();
    } catch (err) {
      setError(getApiErrorMessage(err, 'Action failed.'));
    } finally {
      setBusy(false);
    }
  };

  const handleRerun = () =>
    runAction(() => apiClient.post(API_ENDPOINTS.adminProblems.rerunClassification(problem.id), {}));

  const handleAccept = () =>
    runAction(() =>
      apiClient.post(API_ENDPOINTS.adminProblems.reviewClassification(problem.id), { accept: true })
    );

  const handleChange = (e: FormEvent) => {
    e.preventDefault();
    if (!finalCategory) {
      setError('Choose a final category.');
      return;
    }
    runAction(() =>
      apiClient.post(API_ENDPOINTS.adminProblems.reviewClassification(problem.id), {
        accept: false,
        final_category: finalCategory,
        review_note: reviewNote.trim() || undefined,
      })
    ).then(() => {
      setChanging(false);
      setFinalCategory('');
      setReviewNote('');
    });
  };

  return (
    <div className="card p-6">
      <h2 className="text-lg font-semibold text-secondary-900 mb-2">AI Classification</h2>

      {problem.classification_status === 'NOT_RUN' || problem.classification_status === 'PROCESSING' ? (
        <p className="text-sm text-secondary-600">
          {problem.classification_status === 'PROCESSING'
            ? 'AI Classification: Analyzing…'
            : 'AI analysis has not been run yet.'}
        </p>
      ) : problem.classification_status === 'FAILED' || !classification ? (
        <p className="text-sm text-secondary-600">
          AI classification could not be completed. The report was saved successfully.
        </p>
      ) : (
        <dl className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
          <div>
            <dt className="text-secondary-500">Predicted Category</dt>
            <dd className="font-medium text-secondary-900">{categoryLabel(classification.predicted_category)}</dd>
          </div>
          <div>
            <dt className="text-secondary-500">Confidence</dt>
            <dd className="font-medium text-secondary-900">
              {classification.confidence != null ? `${(classification.confidence * 100).toFixed(1)}%` : '—'}
              <span className="ml-2 text-xs text-secondary-500">{confidenceBand(classification.confidence)}</span>
            </dd>
          </div>
          <div>
            <dt className="text-secondary-500">Status</dt>
            <dd className="font-medium text-secondary-900">
              {classification.status === 'LOW_CONFIDENCE' ? 'Needs Admin Review' : 'Completed'}
            </dd>
          </div>
          <div>
            <dt className="text-secondary-500">Model</dt>
            <dd className="font-medium text-secondary-900">
              {classification.model_name} <span className="text-secondary-500">({classification.model_version})</span>
            </dd>
          </div>
          {classification.requires_manual_review && classification.status !== 'FAILED' && (
            <div className="md:col-span-2 rounded-lg border border-yellow-200 bg-yellow-50 px-3 py-2 text-yellow-800">
              Low confidence — an admin should review this prediction.
            </div>
          )}
          {classification.final_category && (
            <>
              <div>
                <dt className="text-secondary-500">AI Prediction</dt>
                <dd className="font-medium text-secondary-900">{categoryLabel(classification.predicted_category)}</dd>
              </div>
              <div>
                <dt className="text-secondary-500">Final Category</dt>
                <dd className="font-medium text-secondary-900">{categoryLabel(classification.final_category)}</dd>
              </div>
            </>
          )}
        </dl>
      )}

      {isAdmin && classification && (
        <div className="mt-4 space-y-3 border-t border-secondary-100 pt-4">
          <div className="flex flex-wrap gap-2">
            <button type="button" className="btn-secondary px-3 py-1.5 text-sm" disabled={busy} onClick={handleRerun}>
              {busy ? 'Working…' : 'Re-run Classification'}
            </button>
            {!classification.final_category && (
              <>
                <button type="button" className="btn-secondary px-3 py-1.5 text-sm" disabled={busy} onClick={handleAccept}>
                  Accept AI Category
                </button>
                <button
                  type="button"
                  className="btn-secondary px-3 py-1.5 text-sm"
                  disabled={busy}
                  onClick={() => setChanging((v) => !v)}
                >
                  Change Category
                </button>
              </>
            )}
          </div>

          {changing && (
            <form onSubmit={handleChange} className="flex flex-col md:flex-row gap-2">
              <select
                className="input-field md:w-64"
                value={finalCategory}
                onChange={(e) => setFinalCategory(e.target.value)}
                disabled={busy}
                aria-label="Final category"
              >
                <option value="">Select final category…</option>
                {Object.entries(CATEGORY_LABELS).map(([code, label]) => (
                  <option key={code} value={code}>
                    {label}
                  </option>
                ))}
              </select>
              <input
                className="input-field md:flex-1"
                placeholder="Review note (optional)"
                value={reviewNote}
                onChange={(e) => setReviewNote(e.target.value)}
                disabled={busy}
                maxLength={1000}
              />
              <button type="submit" className="btn-primary px-4 py-2 text-sm" disabled={busy}>
                Save Review
              </button>
            </form>
          )}

          {error && (
            <div role="alert" className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
              {error}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
