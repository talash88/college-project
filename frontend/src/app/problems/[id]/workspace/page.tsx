'use client';

import { useCallback, useEffect, useMemo, useState, type ChangeEvent, type FormEvent } from 'react';
import Link from 'next/link';
import { useParams } from 'next/navigation';
import { RequireAuth } from '@/components/auth/RequireAuth';
import { RelatedSolutionsSection } from '@/components/problems/RelatedSolutionsSection';
import { AppLayout } from '@/components/ui/AppLayout';
import { useAuth } from '@/context/AuthContext';
import { apiClient } from '@/lib/api-client';
import { API_ENDPOINTS } from '@/lib/api-config';
import { getApiErrorMessage } from '@/lib/auth-service';
import {
  badgeStyle,
  MILESTONE_STATUS_STYLES,
  PRIORITY_STYLES,
  REVIEW_DECISION_STYLES,
  TASK_STATUS_STYLES,
} from '@/lib/status-styles';
import type {
  ProblemActivity,
  ProblemComment,
  ProblemDetail,
  ReadinessCheck,
  SolutionSubmission,
  TaskPriority,
  TaskStatus,
  WorkspaceFile,
  WorkspaceMilestone,
  WorkspaceOverview,
  WorkspaceProgressUpdate,
  WorkspaceTask,
} from '@/types/api';

type Tab = 'overview' | 'tasks' | 'milestones' | 'progress' | 'files' | 'discussion' | 'solution' | 'knowledge' | 'activity';

const TABS: { id: Tab; label: string }[] = [
  { id: 'overview', label: 'Overview' },
  { id: 'tasks', label: 'Tasks' },
  { id: 'milestones', label: 'Milestones' },
  { id: 'progress', label: 'Progress' },
  { id: 'files', label: 'Files' },
  { id: 'discussion', label: 'Discussion' },
  { id: 'solution', label: 'Solution' },
  { id: 'knowledge', label: 'Knowledge' },
  { id: 'activity', label: 'Activity' },
];

const TASK_GROUPS: { status: TaskStatus; label: string }[] = [
  { status: 'TODO', label: 'To Do' },
  { status: 'IN_PROGRESS', label: 'In Progress' },
  { status: 'BLOCKED', label: 'Blocked' },
  { status: 'DONE', label: 'Done' },
];

/** Workspace status colors come from the central status system. Solution
 *  lifecycle states reuse the review-decision palette. */
const STATUS_STYLES: Record<string, string> = {
  ...TASK_STATUS_STYLES,
  ...MILESTONE_STATUS_STYLES,
  ...REVIEW_DECISION_STYLES,
  MENTOR_APPROVED: 'bg-green-100 text-green-800',
  REPORTER_REJECTED: 'bg-orange-100 text-orange-800',
  VERIFIED: 'bg-green-100 text-green-800',
};

function statusStyle(status: string): string {
  return badgeStyle(STATUS_STYLES, status);
}

function formatDate(value: string | null): string {
  if (!value) return '—';
  return new Date(value).toLocaleString();
}

function formatDay(value: string | null): string {
  if (!value) return '—';
  return new Date(value).toLocaleDateString();
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function initials(name: string | null): string {
  if (!name) return '?';
  return name
    .split(' ')
    .map((part) => part[0])
    .slice(0, 2)
    .join('')
    .toUpperCase();
}

const TASK_NEXT: Record<TaskStatus, { status: TaskStatus; label: string }[]> = {
  TODO: [
    { status: 'IN_PROGRESS', label: 'Start' },
    { status: 'CANCELLED', label: 'Cancel' },
  ],
  IN_PROGRESS: [
    { status: 'BLOCKED', label: 'Block' },
    { status: 'DONE', label: 'Complete' },
    { status: 'TODO', label: 'Back to To Do' },
  ],
  BLOCKED: [
    { status: 'IN_PROGRESS', label: 'Unblock' },
    { status: 'CANCELLED', label: 'Cancel' },
  ],
  DONE: [],
  CANCELLED: [],
};

function WorkspaceContent() {
  const params = useParams<{ id: string }>();
  const problemId = params.id;
  const { user } = useAuth();

  const [tab, setTab] = useState<Tab>('overview');
  const [overview, setOverview] = useState<WorkspaceOverview | null>(null);
  const [tasks, setTasks] = useState<WorkspaceTask[]>([]);
  const [milestones, setMilestones] = useState<WorkspaceMilestone[]>([]);
  const [updates, setUpdates] = useState<WorkspaceProgressUpdate[]>([]);
  const [files, setFiles] = useState<WorkspaceFile[]>([]);
  const [discussion, setDiscussion] = useState<ProblemComment[]>([]);
  const [activity, setActivity] = useState<ProblemActivity[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<{ kind: 'success' | 'error'; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  const [showCancelled, setShowCancelled] = useState(false);
  const [taskForm, setTaskForm] = useState({
    open: false,
    title: '',
    description: '',
    assignee: '',
    priority: 'MEDIUM' as TaskPriority,
    dueDate: '',
  });
  const [editingTask, setEditingTask] = useState<WorkspaceTask | null>(null);
  const [editTitle, setEditTitle] = useState('');
  const [editDescription, setEditDescription] = useState('');
  const [blockerFor, setBlockerFor] = useState<WorkspaceTask | null>(null);
  const [blockerReason, setBlockerReason] = useState('');

  const [milestoneForm, setMilestoneForm] = useState({ open: false, title: '', description: '', targetDate: '' });

  const [progressSummary, setProgressSummary] = useState('');
  const [progressDetails, setProgressDetails] = useState('');
  const [progressBlockers, setProgressBlockers] = useState('');
  const [progressNext, setProgressNext] = useState('');

  const [discussionInput, setDiscussionInput] = useState('');
  const [uploading, setUploading] = useState(false);
  const [fileDescription, setFileDescription] = useState('');

  const [solutions, setSolutions] = useState<SolutionSubmission[]>([]);
  const [readiness, setReadiness] = useState<ReadinessCheck | null>(null);
  const [solutionForm, setSolutionForm] = useState({
    open: false,
    summary: '',
    rootCause: '',
    work: '',
    testing: '',
    deployment: '',
    limitations: '',
    evidenceIds: [] as string[],
    shareEvidence: false,
    overrideReason: '',
  });
  const [reviewFor, setReviewFor] = useState<SolutionSubmission | null>(null);
  const [reviewDecision, setReviewDecision] = useState<'APPROVED' | 'CHANGES_REQUESTED'>('APPROVED');
  const [reviewComment, setReviewComment] = useState('');

  const canManageMilestones = user?.role === 'ADMIN' || user?.role === 'MENTOR';
  const canSubmitSolution = user?.role === 'SOLVER' || user?.role === 'ADMIN';
  const pendingReview = solutions.some((s) => s.status === 'SUBMITTED');

  const applyWorkspaceData = useCallback(
    (
      ws: WorkspaceOverview,
      taskList: WorkspaceTask[],
      milestoneList: WorkspaceMilestone[],
      updateList: WorkspaceProgressUpdate[],
      fileList: WorkspaceFile[],
      messages: ProblemComment[],
      detail: ProblemDetail,
      solutionList: SolutionSubmission[],
      readinessCheck: ReadinessCheck | null
    ) => {
      setOverview(ws);
      setTasks(taskList);
      setMilestones(milestoneList);
      setUpdates(updateList);
      setFiles(fileList);
      setDiscussion(messages);
      setActivity(detail.activity);
      setSolutions(solutionList);
      setReadiness(readinessCheck);
    },
    []
  );

  const fetchSolutionData = useCallback(async () => {
    try {
      const [solutionList, readinessCheck] = await Promise.all([
        apiClient.get<SolutionSubmission[]>(API_ENDPOINTS.problems.solutions(problemId)),
        apiClient.get<ReadinessCheck>(API_ENDPOINTS.problems.solutionReadiness(problemId)),
      ]);
      return { solutionList, readinessCheck };
    } catch {
      return { solutionList: [], readinessCheck: null };
    }
  }, [problemId]);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [ws, taskList, milestoneList, updateList, fileList, messages, detail, solutionData] =
        await Promise.all([
          apiClient.get<WorkspaceOverview>(API_ENDPOINTS.problems.workspace(problemId)),
          apiClient.get<WorkspaceTask[]>(API_ENDPOINTS.problems.tasks(problemId)),
          apiClient.get<WorkspaceMilestone[]>(API_ENDPOINTS.problems.milestones(problemId)),
          apiClient.get<WorkspaceProgressUpdate[]>(API_ENDPOINTS.problems.progressUpdates(problemId)),
          apiClient.get<WorkspaceFile[]>(API_ENDPOINTS.problems.workFiles(problemId)),
          apiClient.get<ProblemComment[]>(API_ENDPOINTS.problems.discussion(problemId)),
          apiClient.get<ProblemDetail>(API_ENDPOINTS.problems.detail(problemId)),
          fetchSolutionData(),
        ]);
      applyWorkspaceData(
        ws,
        taskList,
        milestoneList,
        updateList,
        fileList,
        messages,
        detail,
        solutionData.solutionList,
        solutionData.readinessCheck
      );
    } catch (err) {
      setError(getApiErrorMessage(err, 'Workspace unavailable. Only the assigned team, mentor, or an admin can open it.'));
    } finally {
      setLoading(false);
    }
  }, [problemId, fetchSolutionData, applyWorkspaceData]);

  useEffect(() => {
    load();
  }, [load]);

  const refreshLists = useCallback(async () => {
    const [ws, taskList, milestoneList, updateList, fileList, messages, detail, solutionData] =
      await Promise.all([
        apiClient.get<WorkspaceOverview>(API_ENDPOINTS.problems.workspace(problemId)),
        apiClient.get<WorkspaceTask[]>(API_ENDPOINTS.problems.tasks(problemId)),
        apiClient.get<WorkspaceMilestone[]>(API_ENDPOINTS.problems.milestones(problemId)),
        apiClient.get<WorkspaceProgressUpdate[]>(API_ENDPOINTS.problems.progressUpdates(problemId)),
        apiClient.get<WorkspaceFile[]>(API_ENDPOINTS.problems.workFiles(problemId)),
        apiClient.get<ProblemComment[]>(API_ENDPOINTS.problems.discussion(problemId)),
        apiClient.get<ProblemDetail>(API_ENDPOINTS.problems.detail(problemId)),
        fetchSolutionData(),
      ]);
    applyWorkspaceData(
      ws,
      taskList,
      milestoneList,
      updateList,
      fileList,
      messages,
      detail,
      solutionData.solutionList,
      solutionData.readinessCheck
    );
  }, [problemId, fetchSolutionData, applyWorkspaceData]);

  const groupedTasks = useMemo(() => {
    const groups = new Map<TaskStatus, WorkspaceTask[]>();
    for (const g of TASK_GROUPS) groups.set(g.status, []);
    for (const t of tasks) {
      if (t.status === 'CANCELLED' && !showCancelled) continue;
      const bucket = groups.get(t.status);
      if (bucket) bucket.push(t);
    }
    return groups;
  }, [tasks, showCancelled]);

  const cancelledTasks = useMemo(() => tasks.filter((t) => t.status === 'CANCELLED'), [tasks]);

  const notify = (kind: 'success' | 'error', text: string) => setNotice({ kind, text });

  const handleCreateTask = async (e: FormEvent) => {
    e.preventDefault();
    if (taskForm.title.trim().length < 3) {
      notify('error', 'Task title must be at least 3 characters.');
      return;
    }
    setBusy(true);
    try {
      await apiClient.post(API_ENDPOINTS.problems.tasks(problemId), {
        title: taskForm.title.trim(),
        description: taskForm.description.trim() || undefined,
        assigned_to_user_id: taskForm.assignee || undefined,
        priority: taskForm.priority,
        due_date: taskForm.dueDate ? new Date(taskForm.dueDate).toISOString() : undefined,
      });
      setTaskForm({ open: false, title: '', description: '', assignee: '', priority: 'MEDIUM', dueDate: '' });
      await refreshLists();
      notify('success', 'Task created.');
    } catch (err) {
      notify('error', getApiErrorMessage(err, 'Failed to create the task.'));
    } finally {
      setBusy(false);
    }
  };

  const handleTaskStatus = async (task: WorkspaceTask, next: TaskStatus) => {
    if (next === 'BLOCKED') {
      setBlockerFor(task);
      setBlockerReason(task.blocker_reason ?? '');
      return;
    }
    setBusy(true);
    try {
      await apiClient.patch(API_ENDPOINTS.problems.task(problemId, task.id), { status: next });
      await refreshLists();
      notify('success', `Task ${next.toLowerCase().replace('_', ' ')}.`);
    } catch (err) {
      notify('error', getApiErrorMessage(err, 'Failed to update the task.'));
    } finally {
      setBusy(false);
    }
  };

  const handleBlockConfirm = async () => {
    if (!blockerFor || blockerReason.trim() === '') {
      notify('error', 'A blocker reason is required.');
      return;
    }
    setBusy(true);
    try {
      await apiClient.patch(API_ENDPOINTS.problems.task(problemId, blockerFor.id), {
        status: 'BLOCKED',
        blocker_reason: blockerReason.trim(),
      });
      setBlockerFor(null);
      setBlockerReason('');
      await refreshLists();
      notify('success', 'Task blocked with reason.');
    } catch (err) {
      notify('error', getApiErrorMessage(err, 'Failed to block the task.'));
    } finally {
      setBusy(false);
    }
  };

  const handleReopen = async (task: WorkspaceTask) => {
    setBusy(true);
    try {
      await apiClient.patch(API_ENDPOINTS.problems.task(problemId, task.id), { status: 'IN_PROGRESS' });
      await refreshLists();
      notify('success', 'Task reopened.');
    } catch (err) {
      notify('error', getApiErrorMessage(err, 'Only the mentor or an admin can reopen a completed task.'));
    } finally {
      setBusy(false);
    }
  };

  const handleSaveTaskEdit = async (e: FormEvent) => {
    e.preventDefault();
    if (!editingTask || editTitle.trim().length < 3) {
      notify('error', 'Task title must be at least 3 characters.');
      return;
    }
    setBusy(true);
    try {
      await apiClient.patch(API_ENDPOINTS.problems.task(problemId, editingTask.id), {
        title: editTitle.trim(),
        description: editDescription.trim() || null,
      });
      setEditingTask(null);
      await refreshLists();
      notify('success', 'Task updated.');
    } catch (err) {
      notify('error', getApiErrorMessage(err, 'Failed to update the task.'));
    } finally {
      setBusy(false);
    }
  };

  const handleAssignToMe = async (task: WorkspaceTask) => {
    if (!user) return;
    setBusy(true);
    try {
      await apiClient.patch(API_ENDPOINTS.problems.task(problemId, task.id), {
        assigned_to_user_id: user.id,
      });
      await refreshLists();
      notify('success', 'Task assigned to you.');
    } catch (err) {
      notify('error', getApiErrorMessage(err, 'Failed to claim the task.'));
    } finally {
      setBusy(false);
    }
  };

  const handleCreateMilestone = async (e: FormEvent) => {
    e.preventDefault();
    if (milestoneForm.title.trim().length < 3) {
      notify('error', 'Milestone title must be at least 3 characters.');
      return;
    }
    setBusy(true);
    try {
      await apiClient.post(API_ENDPOINTS.problems.milestones(problemId), {
        title: milestoneForm.title.trim(),
        description: milestoneForm.description.trim() || undefined,
        target_date: milestoneForm.targetDate ? new Date(milestoneForm.targetDate).toISOString() : undefined,
      });
      setMilestoneForm({ open: false, title: '', description: '', targetDate: '' });
      await refreshLists();
      notify('success', 'Milestone created.');
    } catch (err) {
      notify('error', getApiErrorMessage(err, 'Failed to create the milestone.'));
    } finally {
      setBusy(false);
    }
  };

  const handleMilestoneStatus = async (id: string, next: string) => {
    setBusy(true);
    try {
      await apiClient.patch(API_ENDPOINTS.problems.milestone(problemId, id), { status: next });
      await refreshLists();
      notify('success', `Milestone ${next.toLowerCase().replace('_', ' ')}.`);
    } catch (err) {
      notify('error', getApiErrorMessage(err, 'Failed to update the milestone.'));
    } finally {
      setBusy(false);
    }
  };

  const handlePostProgress = async (e: FormEvent) => {
    e.preventDefault();
    if (progressSummary.trim().length < 5) {
      notify('error', 'Progress summary must be at least 5 characters.');
      return;
    }
    setBusy(true);
    try {
      await apiClient.post(API_ENDPOINTS.problems.progressUpdates(problemId), {
        summary: progressSummary.trim(),
        details: progressDetails.trim() || undefined,
        blockers: progressBlockers.trim() || undefined,
        next_steps: progressNext.trim() || undefined,
      });
      setProgressSummary('');
      setProgressDetails('');
      setProgressBlockers('');
      setProgressNext('');
      await refreshLists();
      notify('success', 'Progress update posted.');
    } catch (err) {
      notify('error', getApiErrorMessage(err, 'Failed to post the update.'));
    } finally {
      setBusy(false);
    }
  };

  const handleFileUpload = async (e: ChangeEvent<HTMLInputElement>) => {
    const selected = Array.from(e.target.files ?? []);
    e.target.value = '';
    if (selected.length === 0) return;
    setUploading(true);
    try {
      for (const file of selected) {
        const form = new FormData();
        form.append('file', file);
        if (fileDescription.trim()) form.append('description', fileDescription.trim());
        await apiClient.instance.post(API_ENDPOINTS.problems.workFiles(problemId), form, {
          headers: { 'Content-Type': 'multipart/form-data' },
        });
      }
      setFileDescription('');
      await refreshLists();
      notify('success', 'Work file uploaded.');
    } catch (err) {
      notify('error', getApiErrorMessage(err, 'Work file upload failed.'));
    } finally {
      setUploading(false);
    }
  };

  const handleToggleShareable = async (file: WorkspaceFile) => {
    try {
      await apiClient.patch(
        `${API_ENDPOINTS.problems.workFile(problemId, file.id)}/shareable?shareable=${!file.is_knowledge_shareable}`
      );
      await refreshLists();
      notify(
        'success',
        !file.is_knowledge_shareable
          ? 'File marked shareable for the Knowledge Repository.'
          : 'File marked private.'
      );
    } catch (err) {
      notify('error', getApiErrorMessage(err, 'Failed to update sharing.'));
    }
  };

  const handleDeleteFile = async (id: string, name: string) => {    if (!window.confirm(`Remove work file "${name}"?`)) return;
    try {
      await apiClient.delete(API_ENDPOINTS.problems.workFile(problemId, id));
      await refreshLists();
      notify('success', 'Work file removed.');
    } catch (err) {
      notify('error', getApiErrorMessage(err, 'Failed to remove the file.'));
    }
  };

  const handleDownload = async (file: WorkspaceFile) => {
    try {
      const response = await apiClient.instance.get(
        API_ENDPOINTS.problems.workFileDownload(problemId, file.id),
        { responseType: 'blob' }
      );
      const url = window.URL.createObjectURL(new Blob([response.data], { type: file.mime_type }));
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = file.original_filename;
      anchor.click();
      window.URL.revokeObjectURL(url);
    } catch (err) {
      notify('error', getApiErrorMessage(err, 'Download failed.'));
    }
  };

  const handlePostDiscussion = async (e: FormEvent) => {
    e.preventDefault();
    if (discussionInput.trim() === '') return;
    setBusy(true);
    try {
      await apiClient.post(API_ENDPOINTS.problems.discussion(problemId), {
        content: discussionInput.trim(),
      });
      setDiscussionInput('');
      await refreshLists();
    } catch (err) {
      notify('error', getApiErrorMessage(err, 'Failed to post the message.'));
    } finally {
      setBusy(false);
    }
  };

  const toggleEvidence = (id: string) => {
    setSolutionForm((f) => ({
      ...f,
      evidenceIds: f.evidenceIds.includes(id)
        ? f.evidenceIds.filter((x) => x !== id)
        : [...f.evidenceIds, id],
    }));
  };

  const handleSubmitSolution = async (e: FormEvent) => {
    e.preventDefault();
    if (solutionForm.summary.trim().length < 10) {
      notify('error', 'Solution summary must be at least 10 characters.');
      return;
    }
    if (solutionForm.rootCause.trim().length < 10) {
      notify('error', 'Root cause must be at least 10 characters.');
      return;
    }
    if (solutionForm.work.trim().length < 20) {
      notify('error', 'Work performed must be at least 20 characters.');
      return;
    }
    setBusy(true);
    try {
      await apiClient.post(API_ENDPOINTS.problems.solutions(problemId), {
        solution_summary: solutionForm.summary.trim(),
        root_cause: solutionForm.rootCause.trim(),
        work_performed: solutionForm.work.trim(),
        testing_performed: solutionForm.testing.trim() || undefined,
        deployment_notes: solutionForm.deployment.trim() || undefined,
        limitations: solutionForm.limitations.trim() || undefined,
        evidence_attachment_ids: solutionForm.evidenceIds,
        share_evidence_with_reporter: solutionForm.shareEvidence,
        override_reason: solutionForm.overrideReason.trim() || undefined,
      });
      setSolutionForm({
        open: false,
        summary: '',
        rootCause: '',
        work: '',
        testing: '',
        deployment: '',
        limitations: '',
        evidenceIds: [],
        shareEvidence: false,
        overrideReason: '',
      });
      await refreshLists();
      notify('success', 'Solution submitted for mentor review.');
    } catch (err) {
      notify('error', getApiErrorMessage(err, 'Failed to submit the solution.'));
    } finally {
      setBusy(false);
    }
  };

  const handleReviewSolution = async () => {
    if (!reviewFor) return;
    if (reviewDecision === 'CHANGES_REQUESTED' && reviewComment.trim() === '') {
      notify('error', 'A review comment is required when requesting changes.');
      return;
    }
    setBusy(true);
    try {
      await apiClient.post(API_ENDPOINTS.problems.solutionReview(problemId, reviewFor.id), {
        decision: reviewDecision,
        review_comment: reviewComment.trim() || undefined,
      });
      setReviewFor(null);
      setReviewComment('');
      setReviewDecision('APPROVED');
      await refreshLists();
      notify(
        'success',
        reviewDecision === 'APPROVED' ? 'Solution approved. The reporter was notified.' : 'Changes requested. The team was notified.'
      );
    } catch (err) {
      notify('error', getApiErrorMessage(err, 'Failed to record the review.'));
    } finally {
      setBusy(false);
    }
  };

  const progress = overview?.progress;

  return (
    <AppLayout>
      <div className="space-y-6">
        <div className="flex items-center gap-3 text-sm">
          <Link href={`/problems/${problemId}`} className="text-primary-600 hover:text-primary-700 font-medium">
            ← Report
          </Link>
          <Link href="/assigned" className="text-primary-600 hover:text-primary-700 font-medium">
            ← Assigned
          </Link>
          <Link href="/mentored" className="text-primary-600 hover:text-primary-700 font-medium">
            ← Mentored
          </Link>
        </div>

        {loading ? (
          <div className="space-y-3" aria-label="Loading workspace">
            <div className="h-28 rounded-lg bg-secondary-100 animate-pulse" />
            <div className="h-64 rounded-lg bg-secondary-100 animate-pulse" />
          </div>
        ) : error || !overview ? (
          <div className="card p-8 text-center">
            <h1 className="text-xl font-bold text-secondary-900">Workspace unavailable</h1>
            <p className="mt-1 text-sm text-secondary-600">{error ?? 'Not found.'}</p>
            <button type="button" className="btn-secondary px-4 py-2 text-sm mt-4" onClick={load}>
              Retry
            </button>
          </div>
        ) : (
          <>
            {notice && (
              <div
                role="alert"
                className={`rounded-lg border px-4 py-3 text-sm ${
                  notice.kind === 'success'
                    ? 'border-green-200 bg-green-50 text-green-800'
                    : 'border-red-200 bg-red-50 text-red-700'
                }`}
              >
                {notice.text}
              </div>
            )}

            <div className="card p-6">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-mono text-sm text-secondary-500">{overview.ticket_number}</span>
                <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-blue-100 text-blue-800">
                  {overview.status}
                </span>
                {overview.priority_level && (
                  <span
                    className={`text-xs font-medium px-2 py-0.5 rounded-full ${
                      PRIORITY_STYLES[overview.priority_level] ?? 'bg-secondary-100 text-secondary-700'
                    }`}
                  >
                    {overview.priority_level}
                  </span>
                )}
              </div>
              <h1 className="mt-2 text-2xl font-bold text-secondary-900">{overview.title}</h1>
              <div className="mt-4">
                <div className="flex items-center justify-between text-sm mb-1">
                  <span className="font-medium text-secondary-700">Overall progress</span>
                  <span className="font-bold text-secondary-900">{Math.round(progress?.percent ?? 0)}%</span>
                </div>
                <div className="h-3 rounded-full bg-secondary-100 overflow-hidden" role="progressbar" aria-valuenow={Math.round(progress?.percent ?? 0)} aria-valuemin={0} aria-valuemax={100}>
                  <div
                    className="h-full rounded-full bg-primary-600 transition-all"
                    style={{ width: `${progress?.percent ?? 0}%` }}
                  />
                </div>
                <p className="mt-1 text-xs text-secondary-500">
                  {progress?.done_tasks}/{progress?.total_tasks} tasks · {progress?.done_milestones}/
                  {progress?.total_milestones} milestones · computed from real work
                </p>
              </div>
              <div className="mt-4 flex flex-wrap gap-4 text-sm">
                <div className="flex items-center gap-2">
                  <span className="text-secondary-500">Team:</span>
                  <span className="font-medium text-secondary-900">
                    {overview.team?.display_label ?? '—'}
                  </span>
                  <span className="flex -space-x-1">
                    {(overview.team?.members ?? []).map((m, i) => (
                      <span
                        key={`${m.name}-${i}`}
                        title={`${m.name ?? 'Member'} (${m.role_in_team ?? 'Member'})`}
                        className="w-7 h-7 rounded-full bg-primary-100 text-primary-700 text-xs font-bold flex items-center justify-center border-2 border-white"
                      >
                        {initials(m.name)}
                      </span>
                    ))}
                  </span>
                </div>
                <div>
                  <span className="text-secondary-500">Mentor: </span>
                  <span className="font-medium text-secondary-900">{overview.mentor?.name ?? '—'}</span>
                </div>
              </div>
            </div>

            <div className="flex gap-2 flex-wrap" role="tablist" aria-label="Workspace sections">
              {TABS.map((t) => (
                <button
                  key={t.id}
                  role="tab"
                  aria-selected={tab === t.id}
                  type="button"
                  onClick={() => setTab(t.id)}
                  className={`px-4 py-2 text-sm font-medium rounded-lg border transition-colors ${
                    tab === t.id
                      ? 'bg-primary-600 text-white border-primary-600'
                      : 'bg-white text-secondary-700 border-secondary-200 hover:border-primary-300'
                  }`}
                >
                  {t.label}
                  {t.id === 'solution' && pendingReview && (
                    <span className="ml-1.5 inline-block w-2 h-2 rounded-full bg-amber-500" aria-label="Pending review" />
                  )}
                </button>
              ))}
            </div>

            {tab === 'overview' && (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="card p-6">
                  <h2 className="text-lg font-semibold text-secondary-900 mb-3">Assignment</h2>
                  <dl className="space-y-2 text-sm">
                    <div className="flex justify-between gap-4">
                      <dt className="text-secondary-500">Team</dt>
                      <dd className="font-medium text-secondary-900 text-right">{overview.team?.display_label ?? '—'}</dd>
                    </div>
                    <div className="flex justify-between gap-4">
                      <dt className="text-secondary-500">Mentor</dt>
                      <dd className="font-medium text-secondary-900 text-right">
                        {overview.mentor?.name ?? '—'}
                        {overview.mentor?.designation ? ` · ${overview.mentor.designation}` : ''}
                      </dd>
                    </div>
                    <div className="flex justify-between gap-4">
                      <dt className="text-secondary-500">Assigned</dt>
                      <dd className="font-medium text-secondary-900 text-right">{formatDay(overview.assigned_at)}</dd>
                    </div>
                    <div className="flex justify-between gap-4">
                      <dt className="text-secondary-500">Category</dt>
                      <dd className="font-medium text-secondary-900 text-right">{overview.predicted_category ?? '—'}</dd>
                    </div>
                    <div className="flex justify-between gap-4">
                      <dt className="text-secondary-500">Required skills</dt>
                      <dd className="font-medium text-secondary-900 text-right">
                        {overview.required_skills.length > 0 ? overview.required_skills.join(', ') : '—'}
                      </dd>
                    </div>
                  </dl>
                </div>
                <div className="card p-6">
                  <h2 className="text-lg font-semibold text-secondary-900 mb-3">Members</h2>
                  {(overview.team?.members ?? []).length === 0 ? (
                    <p className="text-sm text-secondary-600">No active members.</p>
                  ) : (
                    <ul className="space-y-2">
                      {(overview.team?.members ?? []).map((m, i) => (
                        <li key={`${m.name}-${i}`} className="flex items-center gap-3 text-sm">
                          <span className="w-8 h-8 rounded-full bg-primary-100 text-primary-700 text-xs font-bold flex items-center justify-center">
                            {initials(m.name)}
                          </span>
                          <span className="flex-1 font-medium text-secondary-800">{m.name ?? 'Member'}</span>
                          <span className="text-xs text-secondary-500">{m.role_in_team ?? 'Member'}</span>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              </div>
            )}

            {tab === 'tasks' && (
              <div className="space-y-4">
                <div className="flex flex-wrap items-center gap-3">
                  <button type="button" className="btn-primary px-4 py-2 text-sm" onClick={() => setTaskForm((f) => ({ ...f, open: !f.open }))}>
                    {taskForm.open ? 'Close' : '+ New Task'}
                  </button>
                  <label className="flex items-center gap-2 text-sm text-secondary-600">
                    <input type="checkbox" checked={showCancelled} onChange={(e) => setShowCancelled(e.target.checked)} />
                    Show cancelled ({cancelledTasks.length})
                  </label>
                </div>

                {taskForm.open && (
                  <form onSubmit={handleCreateTask} className="card p-6 space-y-3">
                    <div>
                      <label htmlFor="task-title" className="block text-sm font-medium text-secondary-700 mb-1">Title</label>
                      <input id="task-title" className="input-field" value={taskForm.title} onChange={(e) => setTaskForm({ ...taskForm, title: e.target.value })} maxLength={200} disabled={busy} />
                    </div>
                    <div>
                      <label htmlFor="task-desc" className="block text-sm font-medium text-secondary-700 mb-1">Description</label>
                      <textarea id="task-desc" rows={3} className="input-field" value={taskForm.description} onChange={(e) => setTaskForm({ ...taskForm, description: e.target.value })} maxLength={10000} disabled={busy} />
                    </div>
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                      <div>
                        <label htmlFor="task-assignee" className="block text-sm font-medium text-secondary-700 mb-1">Assignee</label>
                        <select id="task-assignee" className="input-field" value={taskForm.assignee} onChange={(e) => setTaskForm({ ...taskForm, assignee: e.target.value })} disabled={busy}>
                          <option value="">Unassigned</option>
                          {user && <option value={user.id}>Me ({user.full_name})</option>}
                          {(overview.team?.members ?? [])
                            .filter((m) => m.user_id && m.user_id !== user?.id)
                            .map((m) => (
                              <option key={m.user_id} value={m.user_id ?? ''}>
                                {m.name ?? 'Member'}
                              </option>
                            ))}
                        </select>
                        <p className="mt-1 text-xs text-secondary-500">Team members may assign to themselves; mentor/admin may assign to anyone.</p>
                      </div>
                      <div>
                        <label htmlFor="task-priority" className="block text-sm font-medium text-secondary-700 mb-1">Priority</label>
                        <select id="task-priority" className="input-field" value={taskForm.priority} onChange={(e) => setTaskForm({ ...taskForm, priority: e.target.value as TaskPriority })} disabled={busy}>
                          {['LOW', 'MEDIUM', 'HIGH', 'CRITICAL'].map((p) => (
                            <option key={p} value={p}>{p}</option>
                          ))}
                        </select>
                      </div>
                      <div>
                        <label htmlFor="task-due" className="block text-sm font-medium text-secondary-700 mb-1">Due date</label>
                        <input id="task-due" type="date" className="input-field" value={taskForm.dueDate} onChange={(e) => setTaskForm({ ...taskForm, dueDate: e.target.value })} disabled={busy} />
                      </div>
                    </div>
                    <button type="submit" className="btn-primary px-4 py-2 text-sm" disabled={busy}>
                      {busy ? 'Creating…' : 'Create Task'}
                    </button>
                  </form>
                )}

                {tasks.length === 0 ? (
                  <div className="card p-8 text-center">
                    <p className="text-sm text-secondary-600">No tasks yet. Create the first task to start real work.</p>
                  </div>
                ) : (
                  <div className="grid grid-cols-1 lg:grid-cols-4 gap-4">
                    {TASK_GROUPS.map((group) => (
                      <div key={group.status} className="rounded-lg border border-secondary-200 bg-secondary-50 p-3">
                        <h3 className="text-sm font-semibold text-secondary-800 mb-3">
                          {group.label} ({groupedTasks.get(group.status)?.length ?? 0})
                        </h3>
                        <ul className="space-y-2">
                          {(groupedTasks.get(group.status) ?? []).map((t) => (
                            <li key={t.id} className="rounded-lg border border-secondary-200 bg-white p-3 space-y-2">
                              <p className="text-sm font-medium text-secondary-900">{t.title}</p>
                              <div className="flex flex-wrap gap-1">
                                <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${statusStyle(t.status)}`}>{t.status}</span>
                                <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${PRIORITY_STYLES[t.priority]}`}>{t.priority}</span>
                                {t.is_overdue && (
                                  <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-red-100 text-red-800">Overdue</span>
                                )}
                                {t.status === 'BLOCKED' && (
                                  <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-red-100 text-red-800">Blocked</span>
                                )}
                              </div>
                              <p className="text-xs text-secondary-500">
                                {t.assignee_name ? `Assigned: ${t.assignee_name}` : 'Unassigned'}
                                {t.due_date ? ` · Due ${formatDay(t.due_date)}` : ''}
                              </p>
                              {t.status === 'BLOCKED' && t.blocker_reason && (
                                <p className="text-xs rounded border border-red-200 bg-red-50 px-2 py-1 text-red-800">
                                  Blocker: {t.blocker_reason}
                                </p>
                              )}
                              <div className="flex flex-wrap gap-1 pt-1">
                                {TASK_NEXT[t.status].map((next) => (
                                  <button
                                    key={next.status}
                                    type="button"
                                    disabled={busy}
                                    onClick={() => handleTaskStatus(t, next.status)}
                                    className="text-xs font-medium px-2 py-1 rounded border border-secondary-200 hover:border-primary-400 hover:text-primary-700"
                                  >
                                    {next.label}
                                  </button>
                                ))}
                                {t.status === 'DONE' && canManageMilestones && (
                                  <button type="button" disabled={busy} onClick={() => handleReopen(t)} className="text-xs font-medium px-2 py-1 rounded border border-secondary-200 hover:border-primary-400 hover:text-primary-700">
                                    Reopen
                                  </button>
                                )}
                                {t.assigned_to_user_id == null && (
                                  <button type="button" disabled={busy} onClick={() => handleAssignToMe(t)} className="text-xs font-medium px-2 py-1 rounded border border-secondary-200 hover:border-primary-400 hover:text-primary-700">
                                    Assign to me
                                  </button>
                                )}
                                <button
                                  type="button"
                                  onClick={() => {
                                    setEditingTask(t);
                                    setEditTitle(t.title);
                                    setEditDescription(t.description ?? '');
                                  }}
                                  className="text-xs font-medium px-2 py-1 rounded border border-secondary-200 hover:border-primary-400 hover:text-primary-700"
                                >
                                  Edit
                                </button>
                              </div>
                            </li>
                          ))}
                        </ul>
                      </div>
                    ))}
                  </div>
                )}

                {editingTask && (
                  <form onSubmit={handleSaveTaskEdit} className="card p-6 space-y-3">
                    <h3 className="font-semibold text-secondary-900">Edit task</h3>
                    <input className="input-field" value={editTitle} onChange={(e) => setEditTitle(e.target.value)} maxLength={200} disabled={busy} aria-label="Task title" />
                    <textarea rows={3} className="input-field" value={editDescription} onChange={(e) => setEditDescription(e.target.value)} maxLength={10000} disabled={busy} aria-label="Task description" />
                    <div className="flex gap-2">
                      <button type="submit" className="btn-primary px-4 py-2 text-sm" disabled={busy}>Save</button>
                      <button type="button" className="btn-secondary px-4 py-2 text-sm" onClick={() => setEditingTask(null)} disabled={busy}>Cancel</button>
                    </div>
                  </form>
                )}

                {blockerFor && (
                  <div className="card p-6 space-y-3 border-red-200">
                    <h3 className="font-semibold text-secondary-900">Block “{blockerFor.title}”</h3>
                    <label htmlFor="blocker-reason" className="block text-sm font-medium text-secondary-700">Blocker reason (required)</label>
                    <textarea id="blocker-reason" rows={3} className="input-field" value={blockerReason} onChange={(e) => setBlockerReason(e.target.value)} maxLength={1000} disabled={busy} />
                    <div className="flex gap-2">
                      <button type="button" className="btn-primary px-4 py-2 text-sm" onClick={handleBlockConfirm} disabled={busy}>Block task</button>
                      <button type="button" className="btn-secondary px-4 py-2 text-sm" onClick={() => setBlockerFor(null)} disabled={busy}>Cancel</button>
                    </div>
                  </div>
                )}
              </div>
            )}

            {tab === 'milestones' && (
              <div className="space-y-4">
                {canManageMilestones && (
                  <button type="button" className="btn-primary px-4 py-2 text-sm" onClick={() => setMilestoneForm((f) => ({ ...f, open: !f.open }))}>
                    {milestoneForm.open ? 'Close' : '+ New Milestone'}
                  </button>
                )}
                {milestoneForm.open && canManageMilestones && (
                  <form onSubmit={handleCreateMilestone} className="card p-6 space-y-3">
                    <div>
                      <label htmlFor="ms-title" className="block text-sm font-medium text-secondary-700 mb-1">Title</label>
                      <input id="ms-title" className="input-field" value={milestoneForm.title} onChange={(e) => setMilestoneForm({ ...milestoneForm, title: e.target.value })} maxLength={200} disabled={busy} />
                    </div>
                    <div>
                      <label htmlFor="ms-desc" className="block text-sm font-medium text-secondary-700 mb-1">Description</label>
                      <textarea id="ms-desc" rows={3} className="input-field" value={milestoneForm.description} onChange={(e) => setMilestoneForm({ ...milestoneForm, description: e.target.value })} disabled={busy} />
                    </div>
                    <div>
                      <label htmlFor="ms-target" className="block text-sm font-medium text-secondary-700 mb-1">Target date</label>
                      <input id="ms-target" type="date" className="input-field" value={milestoneForm.targetDate} onChange={(e) => setMilestoneForm({ ...milestoneForm, targetDate: e.target.value })} disabled={busy} />
                    </div>
                    <button type="submit" className="btn-primary px-4 py-2 text-sm" disabled={busy}>
                      {busy ? 'Creating…' : 'Create Milestone'}
                    </button>
                  </form>
                )}
                {milestones.length === 0 ? (
                  <div className="card p-8 text-center">
                    <p className="text-sm text-secondary-600">No milestones yet. Mentors define phases like Analysis, Prototype, Testing, Deployment.</p>
                  </div>
                ) : (
                  <ol className="space-y-3">
                    {milestones.map((m, index) => (
                      <li key={m.id} className="card p-4 flex gap-4">
                        <div className="flex flex-col items-center">
                          <span className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold ${m.status === 'COMPLETED' ? 'bg-green-100 text-green-800' : 'bg-primary-100 text-primary-700'}`}>
                            {m.status === 'COMPLETED' ? '✓' : index + 1}
                          </span>
                          {index < milestones.length - 1 && <span className="w-px flex-1 bg-secondary-200" aria-hidden="true" />}
                        </div>
                        <div className="flex-1 space-y-1">
                          <div className="flex flex-wrap items-center gap-2">
                            <p className="font-medium text-secondary-900">{m.title}</p>
                            <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${statusStyle(m.status)}`}>{m.status}</span>
                            {m.is_overdue && (
                              <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-red-100 text-red-800">Overdue</span>
                            )}
                          </div>
                          {m.description && <p className="text-sm text-secondary-600 whitespace-pre-wrap">{m.description}</p>}
                          <p className="text-xs text-secondary-500">
                            Target: {formatDay(m.target_date)}
                            {m.completed_at ? ` · Completed ${formatDay(m.completed_at)}` : ''}
                          </p>
                          {canManageMilestones && (
                            <div className="flex flex-wrap gap-1 pt-1">
                              {m.status === 'PLANNED' && (
                                <button type="button" disabled={busy} onClick={() => handleMilestoneStatus(m.id, 'IN_PROGRESS')} className="text-xs font-medium px-2 py-1 rounded border border-secondary-200 hover:border-primary-400 hover:text-primary-700">Start</button>
                              )}
                              {(m.status === 'PLANNED' || m.status === 'IN_PROGRESS') && (
                                <button type="button" disabled={busy} onClick={() => handleMilestoneStatus(m.id, 'COMPLETED')} className="text-xs font-medium px-2 py-1 rounded border border-secondary-200 hover:border-primary-400 hover:text-primary-700">Complete</button>
                              )}
                              {m.status === 'IN_PROGRESS' && (
                                <button type="button" disabled={busy} onClick={() => handleMilestoneStatus(m.id, 'MISSED')} className="text-xs font-medium px-2 py-1 rounded border border-secondary-200 hover:border-primary-400 hover:text-primary-700">Mark missed</button>
                              )}
                            </div>
                          )}
                        </div>
                      </li>
                    ))}
                  </ol>
                )}
              </div>
            )}

            {tab === 'progress' && (
              <div className="space-y-4">
                <div className="card p-6">
                  <div className="grid grid-cols-3 gap-3 text-center">
                    <div>
                      <p className="text-2xl font-bold text-secondary-900">{Math.round(progress?.percent ?? 0)}%</p>
                      <p className="text-xs text-secondary-500">Overall</p>
                    </div>
                    <div>
                      <p className="text-2xl font-bold text-secondary-900">{progress?.done_tasks}/{progress?.total_tasks}</p>
                      <p className="text-xs text-secondary-500">Tasks</p>
                    </div>
                    <div>
                      <p className="text-2xl font-bold text-secondary-900">{progress?.done_milestones}/{progress?.total_milestones}</p>
                      <p className="text-xs text-secondary-500">Milestones</p>
                    </div>
                  </div>
                </div>
                <form onSubmit={handlePostProgress} className="card p-6 space-y-3">
                  <h3 className="font-semibold text-secondary-900">Post a progress update</h3>
                  <div>
                    <label htmlFor="pu-summary" className="block text-sm font-medium text-secondary-700 mb-1">Summary</label>
                    <input id="pu-summary" className="input-field" value={progressSummary} onChange={(e) => setProgressSummary(e.target.value)} maxLength={1000} disabled={busy} placeholder="What moved forward?" />
                  </div>
                  <div>
                    <label htmlFor="pu-details" className="block text-sm font-medium text-secondary-700 mb-1">Details</label>
                    <textarea id="pu-details" rows={2} className="input-field" value={progressDetails} onChange={(e) => setProgressDetails(e.target.value)} disabled={busy} />
                  </div>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    <div>
                      <label htmlFor="pu-blockers" className="block text-sm font-medium text-secondary-700 mb-1">Blockers</label>
                      <textarea id="pu-blockers" rows={2} className="input-field" value={progressBlockers} onChange={(e) => setProgressBlockers(e.target.value)} disabled={busy} />
                    </div>
                    <div>
                      <label htmlFor="pu-next" className="block text-sm font-medium text-secondary-700 mb-1">Next steps</label>
                      <textarea id="pu-next" rows={2} className="input-field" value={progressNext} onChange={(e) => setProgressNext(e.target.value)} disabled={busy} />
                    </div>
                  </div>
                  <button type="submit" className="btn-primary px-4 py-2 text-sm" disabled={busy}>
                    {busy ? 'Posting…' : 'Post Update'}
                  </button>
                </form>
                {updates.length === 0 ? (
                  <div className="card p-8 text-center">
                    <p className="text-sm text-secondary-600">No progress updates yet.</p>
                  </div>
                ) : (
                  <ol className="space-y-3">
                    {updates.map((u) => (
                      <li key={u.id} className="card p-4 space-y-1">
                        <div className="flex flex-wrap items-center gap-2 text-xs text-secondary-500">
                          <span className="font-medium text-secondary-700">{u.author_name ?? 'Unknown'}</span>
                          {u.author_role && (
                            <span className="px-2 py-0.5 rounded-full bg-secondary-100 font-medium">{u.author_role}</span>
                          )}
                          <span>{formatDate(u.created_at)}</span>
                          <span className="ml-auto font-bold text-secondary-800">{Math.round(u.progress_snapshot)}%</span>
                        </div>
                        <p className="text-sm font-medium text-secondary-900">{u.summary}</p>
                        {u.details && <p className="text-sm text-secondary-600 whitespace-pre-wrap">{u.details}</p>}
                        {u.blockers && <p className="text-sm text-red-700">Blockers: {u.blockers}</p>}
                        {u.next_steps && <p className="text-sm text-secondary-600">Next: {u.next_steps}</p>}
                      </li>
                    ))}
                  </ol>
                )}
              </div>
            )}

            {tab === 'files' && (
              <div className="space-y-4">
                <div className="card p-6 space-y-3">
                  <h3 className="font-semibold text-secondary-900">Upload work evidence</h3>
                  <div>
                    <label htmlFor="wf-desc" className="block text-sm font-medium text-secondary-700 mb-1">Description</label>
                    <input id="wf-desc" className="input-field" value={fileDescription} onChange={(e) => setFileDescription(e.target.value)} maxLength={1000} disabled={uploading} placeholder="What is this file?" />
                  </div>
                  <label className="btn-secondary px-3 py-1.5 text-sm cursor-pointer inline-block">
                    {uploading ? 'Uploading…' : 'Choose files (JPEG/PNG/WEBP/PDF, ≤10 MB)'}
                    <input type="file" multiple accept="image/jpeg,image/png,image/webp,application/pdf" className="hidden" onChange={handleFileUpload} disabled={uploading} />
                  </label>
                  <p className="text-xs text-secondary-500">Internal only — never visible to the reporter.</p>
                </div>
                {files.length === 0 ? (
                  <div className="card p-8 text-center">
                    <p className="text-sm text-secondary-600">No work files yet.</p>
                  </div>
                ) : (
                  <ul className="space-y-2">
                    {files.map((f) => (
                      <li key={f.id} className="card p-3 flex items-center gap-3 text-sm">
                        <span className="flex-1 min-w-0">
                          <span className="block truncate font-medium text-secondary-800">{f.original_filename}</span>
                          <span className="text-xs text-secondary-500">
                            {formatBytes(f.size_bytes)} · {formatDate(f.created_at)}
                            {f.description ? ` · ${f.description}` : ''}
                          </span>
                        </span>
                        <button type="button" className="text-xs font-medium text-primary-600 hover:text-primary-700" onClick={() => handleDownload(f)}>
                          Download
                        </button>
                        <button
                          type="button"
                          title={f.is_knowledge_shareable ? 'Shared with Knowledge Repository — click to make private' : 'Private — click to share with Knowledge Repository'}
                          className={`text-xs font-medium ${f.is_knowledge_shareable ? 'text-green-700 hover:text-green-800' : 'text-secondary-500 hover:text-secondary-700'}`}
                          onClick={() => handleToggleShareable(f)}
                        >
                          {f.is_knowledge_shareable ? 'Shared' : 'Private'}
                        </button>
                        <button type="button" className="text-xs font-medium text-red-600 hover:text-red-700" onClick={() => handleDeleteFile(f.id, f.original_filename)}>
                          Remove
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}

            {tab === 'discussion' && (
              <div className="space-y-4">
                <div className="card p-4 bg-purple-50 border-purple-200 text-sm text-purple-900">
                  Internal team discussion — visible to the team, mentor, and admins only. Never shown to the reporter.
                </div>
                {discussion.length === 0 ? (
                  <div className="card p-8 text-center">
                    <p className="text-sm text-secondary-600">No internal messages yet.</p>
                  </div>
                ) : (
                  <ul className="space-y-3">
                    {discussion.map((c) => (
                      <li key={c.id} className="rounded-lg border border-secondary-200 p-3 bg-white">
                        <div className="flex items-center gap-2 text-xs text-secondary-500">
                          <span className="font-medium text-secondary-700">{c.author_name ?? 'Unknown'}</span>
                          <span>{formatDate(c.created_at)}</span>
                          <span className="px-2 py-0.5 rounded-full bg-purple-100 text-purple-800 font-medium">Internal</span>
                        </div>
                        <p className="mt-1 text-sm text-secondary-800 whitespace-pre-wrap">{c.content}</p>
                      </li>
                    ))}
                  </ul>
                )}
                <form onSubmit={handlePostDiscussion} className="card p-4 space-y-2">
                  <textarea rows={3} className="input-field" placeholder="Message the team…" value={discussionInput} onChange={(e) => setDiscussionInput(e.target.value)} disabled={busy} maxLength={2000} aria-label="Post an internal message" />
                  <button type="submit" className="btn-primary px-4 py-2 text-sm" disabled={busy || discussionInput.trim() === ''}>
                    {busy ? 'Posting…' : 'Post Message'}
                  </button>
                </form>
              </div>
            )}

            {tab === 'knowledge' && (
              <div className="space-y-4">
                <p className="text-sm text-secondary-600">
                  Previously solved issues related to this report — reuse earlier solutions
                  while you work. Informational only.
                </p>
                <RelatedSolutionsSection problemId={problemId} />
              </div>
            )}

            {tab === 'activity' && (
              <div className="card p-6">
                <h2 className="text-lg font-semibold text-secondary-900 mb-3">Activity Timeline</h2>                {activity.length === 0 ? (
                  <p className="text-sm text-secondary-600">No activity recorded.</p>
                ) : (
                  <ol className="space-y-3">
                    {activity.map((a) => (
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
            )}

            {tab === 'solution' && (
              <div className="space-y-4">
                {readiness && (
                  <div className="card p-6">
                    <div className="flex flex-wrap items-center gap-2 mb-2">
                      <h2 className="text-lg font-semibold text-secondary-900">Completion readiness</h2>
                      {readiness.ready ? (
                        <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-green-100 text-green-800">Ready</span>
                      ) : (
                        <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-yellow-100 text-yellow-800">Not ready</span>
                      )}
                    </div>
                    <p className="text-sm text-secondary-600">
                      {readiness.done_tasks}/{readiness.total_tasks} tasks · {readiness.done_milestones}/
                      {readiness.total_milestones} milestones · {readiness.blocked_tasks} blocked ·{' '}
                      {Math.round(readiness.progress_percent)}% progress
                    </p>
                    {!readiness.ready && (
                      <ul className="mt-2 space-y-1 text-sm text-yellow-800">
                        {readiness.reasons.map((r, i) => (
                          <li key={i}>• {r}</li>
                        ))}
                      </ul>
                    )}
                  </div>
                )}

                {canSubmitSolution && overview.status === 'IN_PROGRESS' && !pendingReview && (
                  <button
                    type="button"
                    className="btn-primary px-4 py-2 text-sm"
                    onClick={() => setSolutionForm((f) => ({ ...f, open: !f.open }))}
                  >
                    {solutionForm.open ? 'Close' : '+ Submit Solution'}
                  </button>
                )}
                {user?.role === 'MENTOR' && (
                  <p className="text-sm text-secondary-600">
                    Mentors review solutions below — only the team submits them.
                  </p>
                )}
                {pendingReview && canManageMilestones && (
                  <div className="card p-4 bg-amber-50 border-amber-200 text-sm text-amber-900" role="status">
                    A solution revision is awaiting your review.
                  </div>
                )}

                {solutionForm.open && canSubmitSolution && (
                  <form onSubmit={handleSubmitSolution} className="card p-6 space-y-3">
                    <h3 className="font-semibold text-secondary-900">
                      Submit solution{readiness && !readiness.ready ? ' (readiness failing)' : ''}
                    </h3>
                    <div>
                      <label htmlFor="sol-summary" className="block text-sm font-medium text-secondary-700 mb-1">Solution summary</label>
                      <textarea id="sol-summary" rows={3} className="input-field" value={solutionForm.summary} onChange={(e) => setSolutionForm({ ...solutionForm, summary: e.target.value })} maxLength={2000} disabled={busy} />
                    </div>
                    <div>
                      <label htmlFor="sol-cause" className="block text-sm font-medium text-secondary-700 mb-1">Root cause</label>
                      <textarea id="sol-cause" rows={2} className="input-field" value={solutionForm.rootCause} onChange={(e) => setSolutionForm({ ...solutionForm, rootCause: e.target.value })} maxLength={2000} disabled={busy} />
                    </div>
                    <div>
                      <label htmlFor="sol-work" className="block text-sm font-medium text-secondary-700 mb-1">Work performed</label>
                      <textarea id="sol-work" rows={4} className="input-field" value={solutionForm.work} onChange={(e) => setSolutionForm({ ...solutionForm, work: e.target.value })} maxLength={20000} disabled={busy} />
                    </div>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                      <div>
                        <label htmlFor="sol-testing" className="block text-sm font-medium text-secondary-700 mb-1">Testing performed</label>
                        <textarea id="sol-testing" rows={2} className="input-field" value={solutionForm.testing} onChange={(e) => setSolutionForm({ ...solutionForm, testing: e.target.value })} disabled={busy} />
                      </div>
                      <div>
                        <label htmlFor="sol-deploy" className="block text-sm font-medium text-secondary-700 mb-1">Deployment notes</label>
                        <textarea id="sol-deploy" rows={2} className="input-field" value={solutionForm.deployment} onChange={(e) => setSolutionForm({ ...solutionForm, deployment: e.target.value })} disabled={busy} />
                      </div>
                    </div>
                    <div>
                      <label htmlFor="sol-limits" className="block text-sm font-medium text-secondary-700 mb-1">Known limitations</label>
                      <textarea id="sol-limits" rows={2} className="input-field" value={solutionForm.limitations} onChange={(e) => setSolutionForm({ ...solutionForm, limitations: e.target.value })} disabled={busy} />
                    </div>
                    {files.length > 0 && (
                      <fieldset>
                        <legend className="text-sm font-medium text-secondary-700 mb-1">Final evidence (work files)</legend>
                        <ul className="space-y-1">
                          {files.map((f) => (
                            <li key={f.id}>
                              <label className="flex items-center gap-2 text-sm text-secondary-700">
                                <input
                                  type="checkbox"
                                  checked={solutionForm.evidenceIds.includes(f.id)}
                                  onChange={() => toggleEvidence(f.id)}
                                  disabled={busy}
                                />
                                {f.original_filename}
                              </label>
                            </li>
                          ))}
                        </ul>
                        <label className="mt-2 flex items-center gap-2 text-sm text-secondary-700">
                          <input
                            type="checkbox"
                            checked={solutionForm.shareEvidence}
                            onChange={(e) => setSolutionForm({ ...solutionForm, shareEvidence: e.target.checked })}
                            disabled={busy}
                          />
                          Share selected evidence with the reporter for verification
                        </label>
                      </fieldset>
                    )}
                    {user?.role === 'ADMIN' && (
                      <div>
                        <label htmlFor="sol-override" className="block text-sm font-medium text-secondary-700 mb-1">
                          Readiness override reason (admin only, audited)
                        </label>
                        <input id="sol-override" className="input-field" value={solutionForm.overrideReason} onChange={(e) => setSolutionForm({ ...solutionForm, overrideReason: e.target.value })} maxLength={1000} disabled={busy} placeholder="Required to bypass failing readiness" />
                      </div>
                    )}
                    <button type="submit" className="btn-primary px-4 py-2 text-sm" disabled={busy}>
                      {busy ? 'Submitting…' : 'Submit for Mentor Review'}
                    </button>
                  </form>
                )}

                {solutions.length === 0 ? (
                  <div className="card p-8 text-center">
                    <p className="text-sm text-secondary-600">No solution submitted yet.</p>
                  </div>
                ) : (
                  <ol className="space-y-3">
                    {solutions.map((s) => (
                      <li key={s.id} className="card p-4 space-y-2">
                        <div className="flex flex-wrap items-center gap-2">
                          <p className="font-medium text-secondary-900">Revision {s.revision_number}</p>
                          <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${statusStyle(s.status)}`}>
                            {s.status.replaceAll('_', ' ')}
                          </span>
                          <span className="text-xs text-secondary-500">
                            by {s.submitter_name ?? 'Unknown'} · {formatDate(s.submitted_at)}
                          </span>
                        </div>
                        <p className="text-sm text-secondary-800 whitespace-pre-wrap">{s.solution_summary}</p>
                        <p className="text-sm text-secondary-600"><span className="font-medium">Root cause:</span> {s.root_cause}</p>
                        <p className="text-sm text-secondary-600 whitespace-pre-wrap"><span className="font-medium">Work:</span> {s.work_performed}</p>
                        {s.testing_performed && <p className="text-sm text-secondary-600"><span className="font-medium">Testing:</span> {s.testing_performed}</p>}
                        {s.readiness_override_reason && (
                          <p className="text-xs rounded border border-amber-200 bg-amber-50 px-2 py-1 text-amber-800">
                            Readiness overridden: {s.readiness_override_reason}
                          </p>
                        )}
                        {s.reviews.length > 0 && (
                          <ul className="space-y-1 border-t border-secondary-100 pt-2">
                            {s.reviews.map((r) => (
                              <li key={r.id} className="text-sm text-secondary-700">
                                <span className={`text-xs font-medium px-2 py-0.5 rounded-full mr-2 ${r.decision === 'APPROVED' ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'}`}>
                                  {r.decision === 'APPROVED' ? 'Approved' : 'Changes requested'}
                                </span>
                                {r.mentor_name ?? 'Mentor'} · {formatDate(r.created_at)}
                                {r.is_admin_override && ' · admin override'}
                                {r.review_comment && <span className="block mt-1 text-secondary-600">{r.review_comment}</span>}
                              </li>
                            ))}
                          </ul>
                        )}
                        {s.status === 'SUBMITTED' && canManageMilestones && (
                          <button
                            type="button"
                            className="btn-secondary px-3 py-1.5 text-sm"
                            onClick={() => {
                              setReviewFor(s);
                              setReviewDecision('APPROVED');
                              setReviewComment('');
                            }}
                          >
                            Review this revision
                          </button>
                        )}
                      </li>
                    ))}
                  </ol>
                )}

                {reviewFor && (
                  <div className="card p-6 space-y-3 border-primary-300" role="dialog" aria-label="Review solution">
                    <h3 className="font-semibold text-secondary-900">Review revision {reviewFor.revision_number}</h3>
                    <div className="flex gap-2">
                      {(['APPROVED', 'CHANGES_REQUESTED'] as const).map((d) => (
                        <button
                          key={d}
                          type="button"
                          onClick={() => setReviewDecision(d)}
                          className={`px-3 py-1.5 text-sm font-medium rounded-lg border ${
                            reviewDecision === d
                              ? 'bg-primary-600 text-white border-primary-600'
                              : 'bg-white text-secondary-700 border-secondary-200'
                          }`}
                        >
                          {d === 'APPROVED' ? 'Approve Solution' : 'Request Changes'}
                        </button>
                      ))}
                    </div>
                    <div>
                      <label htmlFor="review-comment" className="block text-sm font-medium text-secondary-700 mb-1">
                        Review comment{reviewDecision === 'CHANGES_REQUESTED' ? ' (required)' : ' (optional)'}
                      </label>
                      <textarea id="review-comment" rows={3} className="input-field" value={reviewComment} onChange={(e) => setReviewComment(e.target.value)} maxLength={2000} disabled={busy} />
                    </div>
                    <div className="flex gap-2">
                      <button type="button" className="btn-primary px-4 py-2 text-sm" onClick={handleReviewSolution} disabled={busy}>
                        {busy ? 'Recording…' : 'Record Review'}
                      </button>
                      <button type="button" className="btn-secondary px-4 py-2 text-sm" onClick={() => setReviewFor(null)} disabled={busy}>
                        Cancel
                      </button>
                    </div>
                  </div>
                )}
              </div>
            )}
          </>
        )}
      </div>
    </AppLayout>
  );
}

export default function WorkspacePage() {
  return (
    <RequireAuth>
      <WorkspaceContent />
    </RequireAuth>
  );
}
