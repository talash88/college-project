'use client';

import { useCallback, useEffect, useState, type ChangeEvent, type FormEvent } from 'react';
import Link from 'next/link';
import { useParams, useRouter } from 'next/navigation';
import { RequireAuth } from '@/components/auth/RequireAuth';
import { AppLayout } from '@/components/ui/AppLayout';
import { ClassificationSection } from '@/components/problems/ClassificationSection';
import { DuplicatesSection } from '@/components/problems/DuplicatesSection';
import { AdminReviewSection } from '@/components/problems/AdminReviewSection';
import { AssignmentSummary } from '@/components/problems/AssignmentSummary';
import { MentorRecommendationsSection } from '@/components/problems/MentorRecommendationsSection';
import { PrioritySection } from '@/components/problems/PrioritySection';
import { RelatedSolutionsSection } from '@/components/problems/RelatedSolutionsSection';
import { StatusStepper } from '@/components/problems/StatusStepper';
import { TeamRecommendationsSection } from '@/components/problems/TeamRecommendationsSection';
import { RequiredSkillsSection } from '@/components/problems/RequiredSkillsSection';
import { useAuth } from '@/context/AuthContext';
import { apiClient } from '@/lib/api-client';
import { API_ENDPOINTS } from '@/lib/api-config';
import { getApiErrorMessage } from '@/lib/auth-service';
import { formatDateTime as formatDate } from '@/lib/format';
import { priorityStyle, problemStatusStyle } from '@/lib/status-styles';
import type { ProblemDetail, PublicProgress } from '@/types/api';

const TERMINAL_STATUSES = ['RESOLVED', 'CLOSED', 'REJECTED', 'DUPLICATE', 'WITHDRAWN'];
const MAX_FILE_MB = 10;

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function ProblemDetailContent() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const { user } = useAuth();
  const problemId = params.id;

  const [problem, setProblem] = useState<ProblemDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<{ kind: 'success' | 'error'; text: string } | null>(null);

  const [editing, setEditing] = useState(false);
  const [editTitle, setEditTitle] = useState('');
  const [editDescription, setEditDescription] = useState('');
  const [editLocation, setEditLocation] = useState('');
  const [editBuilding, setEditBuilding] = useState('');
  const [editArea, setEditArea] = useState('');
  const [editAffected, setEditAffected] = useState('');
  const [saving, setSaving] = useState(false);

  const [comment, setComment] = useState('');
  const [commentInternal, setCommentInternal] = useState(false);
  const [commenting, setCommenting] = useState(false);

  const [uploading, setUploading] = useState(false);
  const [publicProgress, setPublicProgress] = useState<PublicProgress | null>(null);
  const [verifying, setVerifying] = useState(false);
  const [rejectOpen, setRejectOpen] = useState(false);
  const [rejectReason, setRejectReason] = useState('');
  const [closing, setClosing] = useState(false);

  const isAdmin = user?.role === 'ADMIN';
  const isOwner = problem != null && user != null && problem.reporter_id === user.id;
  const canEdit =
    problem != null &&
    ((isOwner && problem.status === 'SUBMITTED') ||
      (isAdmin && !TERMINAL_STATUSES.includes(problem.status)));

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const detail = await apiClient.get<ProblemDetail>(API_ENDPOINTS.problems.detail(problemId));
      setProblem(detail);
      setEditTitle(detail.title);
      setEditDescription(detail.description);
      setEditLocation(detail.location_text);
      setEditBuilding(detail.building ?? '');
      setEditArea(detail.area ?? '');
      setEditAffected(detail.affected_people_count != null ? String(detail.affected_people_count) : '');
      if (
        detail.assignment != null ||
        ['ASSIGNED', 'IN_PROGRESS', 'AWAITING_VERIFICATION', 'RESOLVED', 'CLOSED'].includes(detail.status)
      ) {
        try {
          setPublicProgress(await apiClient.get<PublicProgress>(API_ENDPOINTS.problems.publicProgress(problemId)));
        } catch {
          setPublicProgress(null);
        }
      } else {
        setPublicProgress(null);
      }
    } catch (err) {
      setError(getApiErrorMessage(err, 'Report not found or you do not have access.'));
    } finally {
      setLoading(false);
    }
  }, [problemId]);

  useEffect(() => {
    load();
  }, [load]);

  const refresh = async () => {
    const detail = await apiClient.get<ProblemDetail>(API_ENDPOINTS.problems.detail(problemId));
    setProblem(detail);
    if (
      detail.assignment != null ||
      ['ASSIGNED', 'IN_PROGRESS', 'AWAITING_VERIFICATION', 'RESOLVED', 'CLOSED'].includes(detail.status)
    ) {
      try {
        setPublicProgress(await apiClient.get<PublicProgress>(API_ENDPOINTS.problems.publicProgress(problemId)));
      } catch {
        setPublicProgress(null);
      }
    } else {
      setPublicProgress(null);
    }
    return detail;
  };

  const handleVerify = async (decision: 'RESOLVED' | 'NOT_RESOLVED') => {
    if (decision === 'NOT_RESOLVED' && rejectReason.trim() === '') {
      setMessage({ kind: 'error', text: 'Please explain what is still wrong.' });
      return;
    }
    setVerifying(true);
    setMessage(null);
    try {
      await apiClient.post(API_ENDPOINTS.problems.verifications(problemId), {
        decision,
        reason: decision === 'NOT_RESOLVED' ? rejectReason.trim() : undefined,
      });
      setRejectOpen(false);
      setRejectReason('');
      await refresh();
      setMessage({
        kind: 'success',
        text:
          decision === 'RESOLVED'
            ? 'Thank you — the resolution is confirmed.'
            : 'Feedback sent. The team has been notified and work resumes.',
      });
    } catch (err) {
      setMessage({ kind: 'error', text: getApiErrorMessage(err, 'Verification failed.') });
    } finally {
      setVerifying(false);
    }
  };

  const handleClose = async () => {
    if (!window.confirm('Close this report? Team and mentor workloads will be released exactly once.')) return;
    setClosing(true);
    setMessage(null);
    try {
      await apiClient.post(API_ENDPOINTS.adminProblems.close(problemId), {});
      await refresh();
      setMessage({ kind: 'success', text: 'Report closed. Workloads released.' });
    } catch (err) {
      setMessage({ kind: 'error', text: getApiErrorMessage(err, 'Closure failed.') });
    } finally {
      setClosing(false);
    }
  };

  const handleSaveEdit = async (e: FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setMessage(null);
    try {
      const updated = await apiClient.patch<ProblemDetail>(API_ENDPOINTS.problems.detail(problemId), {
        title: editTitle.trim(),
        description: editDescription.trim(),
        location_text: editLocation.trim(),
        building: editBuilding.trim() || undefined,
        area: editArea.trim() || undefined,
        affected_people_count: editAffected.trim() === '' ? undefined : Number(editAffected),
      });
      setProblem(updated);
      setEditing(false);
      setMessage({ kind: 'success', text: 'Report updated.' });
    } catch (err) {
      setMessage({ kind: 'error', text: getApiErrorMessage(err, 'Failed to update the report.') });
    } finally {
      setSaving(false);
    }
  };

  const handleWithdraw = async () => {
    if (!window.confirm('Withdraw this report? It will remain visible as withdrawn history.')) return;
    setSaving(true);
    setMessage(null);
    try {
      const updated = await apiClient.delete<ProblemDetail>(API_ENDPOINTS.problems.detail(problemId));
      setProblem(updated);
      setEditing(false);
      setMessage({ kind: 'success', text: 'Report withdrawn.' });
    } catch (err) {
      setMessage({ kind: 'error', text: getApiErrorMessage(err, 'Failed to withdraw the report.') });
    } finally {
      setSaving(false);
    }
  };

  const handleFileUpload = async (e: ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files ?? []);
    e.target.value = '';
    if (files.length === 0) return;
    setUploading(true);
    setMessage(null);
    try {
      for (const file of files) {
        if (file.size > MAX_FILE_MB * 1024 * 1024) {
          throw new Error(`${file.name}: exceeds ${MAX_FILE_MB} MB.`);
        }
        const form = new FormData();
        form.append('file', file);
        await apiClient.instance.post(API_ENDPOINTS.problems.attachments(problemId), form, {
          headers: { 'Content-Type': 'multipart/form-data' },
        });
      }
      await refresh();
      setMessage({ kind: 'success', text: 'Attachment uploaded.' });
    } catch (err) {
      setMessage({ kind: 'error', text: getApiErrorMessage(err, 'Attachment upload failed.') });
      try {
        await refresh();
      } catch {
        // keep existing state
      }
    } finally {
      setUploading(false);
    }
  };

  const handleDeleteAttachment = async (attachmentId: string, name: string) => {
    if (!window.confirm(`Remove attachment "${name}"?`)) return;
    setMessage(null);
    try {
      await apiClient.delete(API_ENDPOINTS.problems.attachment(problemId, attachmentId));
      await refresh();
      setMessage({ kind: 'success', text: 'Attachment removed.' });
    } catch (err) {
      setMessage({ kind: 'error', text: getApiErrorMessage(err, 'Failed to remove the attachment.') });
    }
  };

  const handleAddComment = async (e: FormEvent) => {
    e.preventDefault();
    if (comment.trim() === '') return;
    setCommenting(true);
    setMessage(null);
    try {
      await apiClient.post(API_ENDPOINTS.problems.comments(problemId), {
        content: comment.trim(),
        is_internal: isAdmin && commentInternal,
      });
      setComment('');
      setCommentInternal(false);
      await refresh();
    } catch (err) {
      setMessage({ kind: 'error', text: getApiErrorMessage(err, 'Failed to post the comment.') });
    } finally {
      setCommenting(false);
    }
  };

  return (
    <AppLayout>
      <div className="space-y-6">
        <div className="flex items-center gap-3 text-sm">
          <Link href="/problems" className="text-primary-600 hover:text-primary-700 font-medium">
            ← My Reports
          </Link>
          {isAdmin && (
            <Link href="/admin/problems" className="text-primary-600 hover:text-primary-700 font-medium">
              ← Administration
            </Link>
          )}
        </div>

        {loading ? (
          <div className="card p-6 text-sm text-secondary-600">Loading report…</div>
        ) : error || !problem ? (
          <div className="card p-8 text-center">
            <h1 className="text-xl font-bold text-secondary-900">Report unavailable</h1>
            <p className="mt-1 text-sm text-secondary-600">{error ?? 'Not found.'}</p>
            <button type="button" className="btn-secondary px-4 py-2 text-sm mt-4" onClick={() => router.push('/problems')}>
              Back to My Reports
            </button>
          </div>
        ) : (
          <>
            {message && (
              <div
                role="alert"
                className={`rounded-lg border px-4 py-3 text-sm ${
                  message.kind === 'success'
                    ? 'border-green-200 bg-green-50 text-green-800'
                    : 'border-red-200 bg-red-50 text-red-700'
                }`}
              >
                {message.text}
              </div>
            )}

            <div className="card p-6">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-mono text-sm text-secondary-500">{problem.ticket_number}</span>
                <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${problemStatusStyle(problem.status)}`}>
                  {problem.status}
                </span>
                {problem.priority_level && (
                  <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${priorityStyle(problem.priority_level)}`}>
                    {problem.priority_level}
                    {problem.priority_score != null ? ` · ${Math.round(problem.priority_score)}` : ''}
                  </span>
                )}
                {(problem.classification?.final_category ?? problem.classification?.predicted_category) && (
                  <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-blue-100 text-blue-800">
                    {problem.classification?.final_category ?? problem.classification?.predicted_category}
                  </span>
                )}
                {problem.status === 'WITHDRAWN' && (
                  <span className="text-xs text-secondary-500">Withdrawn reports are kept as history.</span>
                )}
              </div>
              <div className="mt-3">
                <StatusStepper status={problem.status} />
              </div>

              {problem.status === 'REJECTED' && problem.rejection_reason && (
                <div
                  role="status"
                  className="mt-3 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm"
                >
                  <p className="font-medium text-amber-900">This report was not accepted.</p>
                  <p className="text-amber-800">Reason: {problem.rejection_reason}</p>
                </div>
              )}

              {!editing ? (
                <div className="mt-3 space-y-4">
                  <h1 className="text-2xl font-bold text-secondary-900">{problem.title}</h1>
                  <p className="text-secondary-700 whitespace-pre-wrap">{problem.description}</p>
                  <dl className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
                    <div>
                      <dt className="text-secondary-500">Location</dt>
                      <dd className="font-medium text-secondary-900">{problem.location_text}</dd>
                    </div>
                    {problem.building && (
                      <div>
                        <dt className="text-secondary-500">Building</dt>
                        <dd className="font-medium text-secondary-900">{problem.building}</dd>
                      </div>
                    )}
                    {problem.area && (
                      <div>
                        <dt className="text-secondary-500">Area</dt>
                        <dd className="font-medium text-secondary-900">{problem.area}</dd>
                      </div>
                    )}
                    <div>
                      <dt className="text-secondary-500">People affected</dt>
                      <dd className="font-medium text-secondary-900">{problem.affected_people_count ?? '—'}</dd>
                    </div>
                    <div>
                      <dt className="text-secondary-500">Reported by</dt>
                      <dd className="font-medium text-secondary-900">{problem.reporter?.full_name ?? '—'}</dd>
                    </div>
                    <div>
                      <dt className="text-secondary-500">Reported at</dt>
                      <dd className="font-medium text-secondary-900">{formatDate(problem.submitted_at)}</dd>
                    </div>
                  </dl>
                  {canEdit && (
                    <div className="flex gap-2">
                      <button type="button" className="btn-primary px-4 py-2 text-sm" onClick={() => setEditing(true)}>
                        Edit Report
                      </button>
                      <button type="button" className="btn-secondary px-4 py-2 text-sm" onClick={handleWithdraw} disabled={saving}>
                        Withdraw Report
                      </button>
                    </div>
                  )}
                </div>
              ) : (
                <form onSubmit={handleSaveEdit} className="mt-3 space-y-4" noValidate>
                  <div>
                    <label htmlFor="edit-title" className="block text-sm font-medium text-secondary-700 mb-1">Title</label>
                    <input id="edit-title" className="input-field" value={editTitle} onChange={(e) => setEditTitle(e.target.value)} disabled={saving} maxLength={200} />
                  </div>
                  <div>
                    <label htmlFor="edit-description" className="block text-sm font-medium text-secondary-700 mb-1">Description</label>
                    <textarea id="edit-description" rows={5} className="input-field" value={editDescription} onChange={(e) => setEditDescription(e.target.value)} disabled={saving} maxLength={10000} />
                  </div>
                  <div>
                    <label htmlFor="edit-location" className="block text-sm font-medium text-secondary-700 mb-1">Location</label>
                    <input id="edit-location" className="input-field" value={editLocation} onChange={(e) => setEditLocation(e.target.value)} disabled={saving} maxLength={300} />
                  </div>
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    <div>
                      <label htmlFor="edit-building" className="block text-sm font-medium text-secondary-700 mb-1">Building</label>
                      <input id="edit-building" className="input-field" value={editBuilding} onChange={(e) => setEditBuilding(e.target.value)} disabled={saving} maxLength={150} />
                    </div>
                    <div>
                      <label htmlFor="edit-area" className="block text-sm font-medium text-secondary-700 mb-1">Area</label>
                      <input id="edit-area" className="input-field" value={editArea} onChange={(e) => setEditArea(e.target.value)} disabled={saving} maxLength={150} />
                    </div>
                    <div>
                      <label htmlFor="edit-affected" className="block text-sm font-medium text-secondary-700 mb-1">People affected</label>
                      <input id="edit-affected" type="number" min={1} className="input-field" value={editAffected} onChange={(e) => setEditAffected(e.target.value)} disabled={saving} />
                    </div>
                  </div>
                  <div className="flex gap-2">
                    <button type="submit" className="btn-primary px-4 py-2 text-sm" disabled={saving}>
                      {saving ? 'Saving…' : 'Save Changes'}
                    </button>
                    <button type="button" className="btn-secondary px-4 py-2 text-sm" onClick={() => setEditing(false)} disabled={saving}>
                      Cancel
                    </button>
                  </div>
                </form>
              )}
            </div>

            <ClassificationSection
              problem={problem}
              isAdmin={isAdmin}
              onChanged={async () => {
                const detail = await apiClient.get<ProblemDetail>(
                  API_ENDPOINTS.problems.detail(problemId)
                );
                setProblem(detail);
              }}
            />

            {isAdmin ? (
              <AdminReviewSection
                problem={problem}
                onChanged={async () => {
                  const detail = await apiClient.get<ProblemDetail>(
                    API_ENDPOINTS.problems.detail(problemId)
                  );
                  setProblem(detail);
                }}
              />
            ) : (
              problem.assignment != null && <AssignmentSummary assignment={problem.assignment} />
            )}

            {(isAdmin || (problem.assignment != null && !isOwner)) &&
              (problem.status === 'ASSIGNED' || problem.status === 'IN_PROGRESS') && (
                <div className="card p-6 flex flex-wrap items-center gap-3">
                  <div className="flex-1 min-w-[200px]">
                    <h2 className="text-lg font-semibold text-secondary-900">Team Workspace</h2>
                    <p className="text-sm text-secondary-600">
                      {(problem.progress_percent ?? 0) > 0
                        ? `Real progress: ${Math.round(problem.progress_percent ?? 0)}% — tasks, milestones, files, and discussion.`
                        : 'Tasks, milestones, files, and discussion for the assigned team and mentor.'}
                    </p>
                  </div>
                  <Link href={`/problems/${problemId}/workspace`} className="btn-primary px-4 py-2 text-sm">
                    Open Workspace →
                  </Link>
                </div>
              )}

            {(problem.status === 'AWAITING_VERIFICATION' ||
              problem.status === 'RESOLVED' ||
              problem.status === 'CLOSED') && (
              <div
                role="status"
                className={`card p-6 border ${
                  problem.status === 'CLOSED'
                    ? 'border-secondary-300 bg-secondary-50'
                    : problem.status === 'RESOLVED'
                      ? 'border-green-200 bg-green-50'
                      : 'border-blue-200 bg-blue-50'
                }`}
              >
                <h2 className="text-lg font-semibold text-secondary-900">
                  {problem.status === 'CLOSED'
                    ? 'Closed'
                    : problem.status === 'RESOLVED'
                      ? 'Resolved'
                      : 'Awaiting your verification'}
                </h2>
                <p className="mt-1 text-sm text-secondary-700">
                  {problem.status === 'CLOSED' &&
                    `This report was closed${problem.closed_at ? ` on ${formatDate(problem.closed_at)}` : ''}. History is preserved read-only.`}
                  {problem.status === 'RESOLVED' &&
                    `The resolution was confirmed${problem.resolved_at ? ` on ${formatDate(problem.resolved_at)}` : ''}. An administrator will close the report and release the team.`}
                  {problem.status === 'AWAITING_VERIFICATION' &&
                    'The mentor approved a solution. Please confirm whether the campus problem is actually fixed.'}
                </p>
                {isAdmin && problem.status === 'RESOLVED' && (
                  <button
                    type="button"
                    onClick={handleClose}
                    disabled={closing}
                    className="btn-primary px-4 py-2 text-sm mt-3"
                  >
                    {closing ? 'Closing…' : 'Close Report & Release Team'}
                  </button>
                )}
              </div>
            )}

            {isOwner && problem.status === 'AWAITING_VERIFICATION' && (
              <div className="card p-6 border-primary-300">
                <h2 className="text-lg font-semibold text-secondary-900">Has this campus problem been resolved?</h2>
                {publicProgress?.solution != null ? (
                  <div className="mt-2 rounded-lg border border-secondary-200 p-3 text-sm space-y-1">
                    <p className="text-secondary-500 text-xs">
                      Approved solution · revision {publicProgress.solution.revision_number}
                    </p>
                    <p className="text-secondary-800 whitespace-pre-wrap">{publicProgress.solution.solution_summary}</p>
                    <p className="text-secondary-600 whitespace-pre-wrap">
                      <span className="font-medium">Work performed:</span> {publicProgress.solution.work_performed}
                    </p>
                    {publicProgress.solution.testing_performed && (
                      <p className="text-secondary-600">
                        <span className="font-medium">Testing:</span> {publicProgress.solution.testing_performed}
                      </p>
                    )}
                  </div>
                ) : (
                  <p className="mt-2 text-sm text-secondary-600">Loading the approved solution…</p>
                )}
                {!rejectOpen ? (
                  <div className="mt-3 flex flex-wrap gap-2">
                    <button
                      type="button"
                      onClick={() => handleVerify('RESOLVED')}
                      disabled={verifying}
                      className="btn-primary px-4 py-2 text-sm"
                    >
                      {verifying ? 'Confirming…' : 'Yes, Resolved'}
                    </button>
                    <button
                      type="button"
                      onClick={() => setRejectOpen(true)}
                      disabled={verifying}
                      className="btn-secondary px-4 py-2 text-sm"
                    >
                      No, Still Not Resolved
                    </button>
                  </div>
                ) : (
                  <div className="mt-3 space-y-2">
                    <label htmlFor="verify-reason" className="block text-sm font-medium text-secondary-700">
                      What is still wrong? (required)
                    </label>
                    <textarea
                      id="verify-reason"
                      rows={3}
                      className="input-field"
                      value={rejectReason}
                      onChange={(e) => setRejectReason(e.target.value)}
                      maxLength={2000}
                      disabled={verifying}
                      placeholder="Describe what the team should fix next…"
                    />
                    <div className="flex gap-2">
                      <button
                        type="button"
                        onClick={() => handleVerify('NOT_RESOLVED')}
                        disabled={verifying || rejectReason.trim() === ''}
                        className="btn-primary px-4 py-2 text-sm"
                      >
                        {verifying ? 'Sending…' : 'Send Feedback'}
                      </button>
                      <button
                        type="button"
                        onClick={() => {
                          setRejectOpen(false);
                          setRejectReason('');
                        }}
                        disabled={verifying}
                        className="btn-secondary px-4 py-2 text-sm"
                      >
                        Cancel
                      </button>
                    </div>
                  </div>
                )}
              </div>
            )}

            {isOwner && publicProgress != null && (
              <div className="card p-6">
                <h2 className="text-lg font-semibold text-secondary-900 mb-1">Resolution Progress</h2>
                <p className="text-sm text-secondary-600 mb-3">
                  {publicProgress.team_name ? `Being worked on by ${publicProgress.team_name}` : 'Assigned for resolution'}
                  {publicProgress.mentor_name ? ` · Mentored by ${publicProgress.mentor_name}` : ''} · Status: {publicProgress.status}
                </p>
                <div className="flex items-center justify-between text-sm mb-1">
                  <span className="font-medium text-secondary-700">Progress</span>
                  <span className="font-bold text-secondary-900">{Math.round(publicProgress.progress_percent)}%</span>
                </div>
                <div className="h-3 rounded-full bg-secondary-100 overflow-hidden" role="progressbar" aria-valuenow={Math.round(publicProgress.progress_percent)} aria-valuemin={0} aria-valuemax={100}>
                  <div className="h-full rounded-full bg-primary-600" style={{ width: `${publicProgress.progress_percent}%` }} />
                </div>
                <p className="mt-1 text-xs text-secondary-500">
                  {publicProgress.completed_tasks}/{publicProgress.total_tasks} tasks · {publicProgress.completed_milestones}/{publicProgress.total_milestones} milestones
                </p>
                {publicProgress.recent_updates.length > 0 && (
                  <ul className="mt-3 space-y-2">
                    {publicProgress.recent_updates.map((u, i) => (
                      <li key={i} className="rounded-lg border border-secondary-200 px-3 py-2 text-sm">
                        <p className="text-secondary-800">{u.summary}</p>
                        <p className="text-xs text-secondary-500">
                          {u.author_role ?? 'Team'} · {formatDate(u.created_at)} · {Math.round(u.progress_snapshot)}%
                        </p>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}

            <PrioritySection
              problem={problem}
              isAdmin={isAdmin}
              onChanged={async () => {
                const detail = await apiClient.get<ProblemDetail>(
                  API_ENDPOINTS.problems.detail(problemId)
                );
                setProblem(detail);
              }}
            />

            <RequiredSkillsSection
              problem={problem}
              isAdmin={isAdmin}
              onChanged={async () => {
                const detail = await apiClient.get<ProblemDetail>(
                  API_ENDPOINTS.problems.detail(problemId)
                );
                setProblem(detail);
              }}
            />

            <DuplicatesSection
              problem={problem}
              isAdmin={isAdmin}
              onChanged={async () => {
                const detail = await apiClient.get<ProblemDetail>(
                  API_ENDPOINTS.problems.detail(problemId)
                );
                setProblem(detail);
              }}
            />

            <RelatedSolutionsSection problemId={problemId} />

            <TeamRecommendationsSection
              problem={problem}
              isAdmin={isAdmin}
              onChanged={async () => {
                const detail = await apiClient.get<ProblemDetail>(
                  API_ENDPOINTS.problems.detail(problemId)
                );
                setProblem(detail);
              }}
            />

            <MentorRecommendationsSection
              problem={problem}
              isAdmin={isAdmin}
              onChanged={async () => {
                const detail = await apiClient.get<ProblemDetail>(
                  API_ENDPOINTS.problems.detail(problemId)
                );
                setProblem(detail);
              }}
            />

            <div className="card p-6">
              <div className="flex items-center justify-between mb-3">
                <h2 className="text-lg font-semibold text-secondary-900">Attachments ({problem.attachments.length})</h2>
                {canEdit && (
                  <label className="btn-secondary px-3 py-1.5 text-sm cursor-pointer">
                    {uploading ? 'Uploading…' : 'Add files'}
                    <input
                      type="file"
                      multiple
                      accept="image/jpeg,image/png,image/webp,application/pdf"
                      className="hidden"
                      onChange={handleFileUpload}
                      disabled={uploading}
                    />
                  </label>
                )}
              </div>
              {problem.attachments.length === 0 ? (
                <p className="text-sm text-secondary-600">No attachments.</p>
              ) : (
                <ul className="space-y-2">
                  {problem.attachments.map((a) => (
                    <li key={a.id} className="flex items-center gap-3 rounded-lg border border-secondary-200 px-3 py-2 text-sm">
                      <span className="flex-1 truncate font-medium text-secondary-800">{a.original_filename}</span>
                      <span className="text-xs text-secondary-500">{formatBytes(a.size_bytes)}</span>
                      {canEdit && (
                        <button
                          type="button"
                          className="text-xs font-medium text-red-600 hover:text-red-700"
                          onClick={() => handleDeleteAttachment(a.id, a.original_filename)}
                        >
                          Remove
                        </button>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </div>

            <div className="card p-6">
              <h2 className="text-lg font-semibold text-secondary-900 mb-3">Comments ({problem.comments.length})</h2>
              {problem.comments.length === 0 ? (
                <p className="text-sm text-secondary-600 mb-4">No comments yet.</p>
              ) : (
                <ul className="space-y-3 mb-4">
                  {problem.comments.map((c) => (
                    <li key={c.id} className="rounded-lg border border-secondary-200 p-3">
                      <div className="flex items-center gap-2 text-xs text-secondary-500">
                        <span className="font-medium text-secondary-700">{c.author_name ?? 'Unknown'}</span>
                        <span>{formatDate(c.created_at)}</span>
                        {c.is_internal && (
                          <span className="px-2 py-0.5 rounded-full bg-purple-100 text-purple-800 font-medium">
                            Internal
                          </span>
                        )}
                      </div>
                      <p className="mt-1 text-sm text-secondary-800 whitespace-pre-wrap">{c.content}</p>
                    </li>
                  ))}
                </ul>
              )}
              <form onSubmit={handleAddComment} className="space-y-2">
                <textarea
                  rows={3}
                  className="input-field"
                  placeholder="Add a comment…"
                  value={comment}
                  onChange={(e) => setComment(e.target.value)}
                  disabled={commenting}
                  maxLength={2000}
                  aria-label="Add a comment"
                />
                <div className="flex items-center gap-3">
                  <button type="submit" className="btn-primary px-4 py-2 text-sm" disabled={commenting || comment.trim() === ''}>
                    {commenting ? 'Posting…' : 'Post Comment'}
                  </button>
                  {isAdmin && (
                    <label className="flex items-center gap-2 text-sm text-secondary-600">
                      <input
                        type="checkbox"
                        checked={commentInternal}
                        onChange={(e) => setCommentInternal(e.target.checked)}
                        disabled={commenting}
                      />
                      Internal (admin only)
                    </label>
                  )}
                </div>
              </form>
            </div>

            <div className="card p-6">
              <h2 className="text-lg font-semibold text-secondary-900 mb-3">Activity Timeline</h2>
              {problem.activity.length === 0 ? (
                <p className="text-sm text-secondary-600">No activity recorded.</p>
              ) : (
                <ol className="space-y-3">
                  {problem.activity.map((a) => (
                    <li key={a.id} className="flex gap-3 text-sm">
                      <span className="mt-1 w-2 h-2 rounded-full bg-primary-500 flex-shrink-0" aria-hidden="true" />
                      <div>
                        <p className="font-medium text-secondary-800">
                          {a.event_type.replaceAll('_', ' ')}
                          {a.old_status && a.new_status ? ` (${a.old_status} → ${a.new_status})` : ''}
                        </p>
                        {a.message && <p className="text-secondary-600">{a.message}</p>}
                        <p className="text-xs text-secondary-400">{formatDate(a.created_at)}</p>
                      </div>
                    </li>
                  ))}
                </ol>
              )}
            </div>
          </>
        )}
      </div>
    </AppLayout>
  );
}

export default function ProblemDetailPage() {
  return (
    <RequireAuth>
      <ProblemDetailContent />
    </RequireAuth>
  );
}
