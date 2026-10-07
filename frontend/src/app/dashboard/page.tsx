'use client';

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { RequireAuth } from '@/components/auth/RequireAuth';
import { AppLayout } from '@/components/ui/AppLayout';
import { useAuth } from '@/context/AuthContext';
import { useBackendHealth } from '@/hooks/useBackendHealth';
import { apiClient } from '@/lib/api-client';
import { API_ENDPOINTS } from '@/lib/api-config';
import { getApiErrorMessage } from '@/lib/auth-service';
import { problemStatusStyle } from '@/lib/status-styles';
import type {
  AdminKnowledgeEntry,
  AdminProblemListResponse,
  AssignedProblem,
  ProblemListResponse,
  ProblemStats,
  SolutionSubmission,
} from '@/types/api';

const ROLE_DESCRIPTIONS: Record<string, string> = {
  REPORTER: 'Report campus problems and track their resolution.',
  SOLVER: 'Get matched to problems that fit your skills.',
  MENTOR: 'Guide student teams solving campus problems.',
  ADMIN: 'Manage users, problems, and platform workflows.',
};

function DashboardContent() {
  const { user } = useAuth();
  const { connected, loading, data } = useBackendHealth();
  const isDev = process.env.NODE_ENV === 'development';
  const [stats, setStats] = useState<ProblemStats | null>(null);
  const [recent, setRecent] = useState<ProblemListResponse | null>(null);
  const [statsError, setStatsError] = useState<string | null>(null);
  const [assignedItems, setAssignedItems] = useState<AssignedProblem[] | null>(null);
  const [mentoredItems, setMentoredItems] = useState<AssignedProblem[] | null>(null);
  const [solutionFlags, setSolutionFlags] = useState<Record<string, string>>({});
  const [unreadCount, setUnreadCount] = useState<number | null>(null);
  const [knowledgeCounts, setKnowledgeCounts] = useState<{
    published: number;
    failed: number;
    archived: number;
  } | null>(null);
  const [adminCounts, setAdminCounts] = useState<{
    pendingReview: number;
    awaitingAssignment: number;
    assigned: number;
    inProgress: number;
    awaitingVerification: number;
    resolvedAwaitingClosure: number;
  } | null>(null);

  const loadStats = useCallback(async () => {
    try {
      const [fetchedStats, fetchedRecent] = await Promise.all([
        apiClient.get<ProblemStats>(API_ENDPOINTS.problems.myStats),
        apiClient.get<ProblemListResponse>(`${API_ENDPOINTS.problems.mine}?limit=5`),
      ]);
      setStats(fetchedStats);
      setRecent(fetchedRecent);
    } catch (err) {
      setStatsError(getApiErrorMessage(err, 'Could not load report statistics.'));
    }
  }, []);

  useEffect(() => {
    loadStats();
  }, [loadStats]);

  useEffect(() => {
    apiClient
      .get<{ unread_count: number }>(API_ENDPOINTS.notifications.unreadCount)
      .then((res) => setUnreadCount(res.unread_count))
      .catch(() => setUnreadCount(null));
  }, []);

  useEffect(() => {
    if (user?.role === 'SOLVER') {
      apiClient
        .get<AssignedProblem[]>(API_ENDPOINTS.problems.assignedMine)
        .then((items) => {
          setAssignedItems(items);
          flagLatestSolutions(items.map((p) => p.id));
        })
        .catch(() => setAssignedItems(null));
    } else if (user?.role === 'MENTOR') {
      apiClient
        .get<AssignedProblem[]>(API_ENDPOINTS.problems.mentoredMine)
        .then((items) => {
          setMentoredItems(items);
          flagLatestSolutions(items.map((p) => p.id));
        })
        .catch(() => setMentoredItems(null));
    } else if (user?.role === 'ADMIN') {
      apiClient
        .get<AdminKnowledgeEntry[]>(API_ENDPOINTS.adminKnowledge.base)
        .then((entries) => {
          const counts = { published: 0, failed: 0, archived: 0 };
          for (const e of entries) {
            if (e.publication_status === 'PUBLISHED') counts.published += 1;
            else if (e.publication_status === 'FAILED') counts.failed += 1;
            else if (e.publication_status === 'ARCHIVED') counts.archived += 1;
          }
          setKnowledgeCounts(counts);
        })
        .catch(() => setKnowledgeCounts(null));
      Promise.all(
        (['SUBMITTED', 'APPROVED', 'ASSIGNED', 'IN_PROGRESS', 'AWAITING_VERIFICATION', 'RESOLVED'] as const).map(
          (status) =>
            apiClient.get<AdminProblemListResponse>(
              `${API_ENDPOINTS.adminProblems.base}?status=${status}&limit=1`
            )
        )
      )
        .then(([submitted, approved, assigned, inProgress, awaitingVerification, resolved]) =>
          setAdminCounts({
            pendingReview: submitted.total,
            awaitingAssignment: approved.total,
            assigned: assigned.total,
            inProgress: inProgress.total,
            awaitingVerification: awaitingVerification.total,
            resolvedAwaitingClosure: resolved.total,
          })
        )
        .catch(() => setAdminCounts(null));
    }
  }, [user?.role]);

  const flagLatestSolutions = (problemIds: string[]) => {
    // Real per-problem latest-solution status for revision/review badges.
    Promise.allSettled(
      problemIds.map((id) =>
        apiClient.get<SolutionSubmission>(API_ENDPOINTS.problems.latestSolution(id))
      )
    ).then((results) => {
      const flags: Record<string, string> = {};
      results.forEach((r, i) => {
        if (r.status === 'fulfilled') flags[problemIds[i]] = r.value.status;
      });
      setSolutionFlags(flags);
    });
  };

  const submitted = stats?.by_status.SUBMITTED ?? 0;
  const underReview = stats?.by_status.UNDER_REVIEW ?? 0;
  const approved = stats?.by_status.APPROVED ?? 0;
  const assigned = stats?.by_status.ASSIGNED ?? 0;
  const awaitingVerification = stats?.by_status.AWAITING_VERIFICATION ?? 0;
  const resolved = stats?.by_status.RESOLVED ?? 0;

  return (
    <AppLayout>
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl lg:text-3xl font-bold text-secondary-900">
            Welcome, {user?.full_name ?? 'User'}
          </h1>
          <p className="mt-1 text-secondary-600">
            Role: <span className="font-medium text-secondary-800">{user?.role}</span>
            {user?.role && ROLE_DESCRIPTIONS[user.role] ? ` — ${ROLE_DESCRIPTIONS[user.role]}` : ''}
          </p>
        </div>

        {unreadCount != null && unreadCount > 0 && (
          <Link
            href="/notifications"
            className="card p-4 flex items-center gap-3 hover:border-primary-300 transition-colors"
            aria-label={`${unreadCount} unread notifications`}
          >
            <span className="w-2.5 h-2.5 rounded-full bg-primary-600 flex-shrink-0" aria-hidden="true" />
            <p className="text-sm text-secondary-800">
              You have <span className="font-semibold">{unreadCount} unread notification{unreadCount === 1 ? '' : 's'}</span>
              {' '}— view updates on your reports, reviews, and assignments →
            </p>
          </Link>
        )}

        <div className="card p-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-secondary-900">My Reports</h2>
            <Link href="/problems/new" className="btn-primary px-4 py-2 text-sm">
              Report a Problem
            </Link>
          </div>          {statsError ? (
            <p className="text-sm text-red-600">{statsError}</p>
          ) : stats == null ? (
            <p className="text-sm text-secondary-600">Loading your reports…</p>
          ) : stats.total === 0 ? (
            <div>
              <p className="text-sm text-secondary-600">You have not reported any campus problems yet.</p>
              <Link href="/problems/new" className="text-sm font-medium text-primary-600 hover:text-primary-700">
                Report your first problem →
              </Link>
            </div>
          ) : (
            <>
              <div className="grid grid-cols-2 md:grid-cols-3 gap-3 mb-4">
                <StatCard label="Submitted" value={submitted} href="/problems?status=SUBMITTED" />
                <StatCard label="Under Review" value={underReview} href="/problems?status=UNDER_REVIEW" />
                <StatCard label="Approved" value={approved} href="/problems?status=APPROVED" />
                <StatCard label="Assigned" value={assigned} href="/problems?status=ASSIGNED" />
                <StatCard label="Awaiting Verification" value={awaitingVerification} href="/problems?status=AWAITING_VERIFICATION" />
                <StatCard label="Recently Resolved" value={resolved} href="/problems?status=RESOLVED" />
              </div>
              {recent != null && recent.items.length > 0 && (
                <ul className="divide-y divide-secondary-100 border-t border-secondary-100">
                  {recent.items.map((p) => (
                    <li key={p.id} className="py-2 flex items-center gap-3 text-sm">
                      <span className="font-mono text-xs text-secondary-400">{p.ticket_number}</span>
                      <Link href={`/problems/${p.id}`} className="flex-1 truncate font-medium text-secondary-800 hover:text-primary-700">
                        {p.title}
                      </Link>
                      <span className={`text-xs font-medium px-2 py-0.5 rounded-full whitespace-nowrap ${problemStatusStyle(p.status)}`}>
                        {p.status}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
              <Link href="/problems" className="text-sm font-medium text-primary-600 hover:text-primary-700">
                View all reports →
              </Link>
            </>
          )}
        </div>

        {user?.role === 'SOLVER' && (
          <div className="card p-6">
            <div className="flex items-center justify-between mb-3">
              <div>
                <h2 className="text-lg font-semibold text-secondary-900">Assigned Problems</h2>
                <p className="text-sm text-secondary-600">
                  {assignedItems == null ? 'Loading…' : `${assignedItems.length} active assignment${assignedItems.length === 1 ? '' : 's'}`}
                </p>
              </div>
              <Link href="/assigned" className="btn-secondary px-4 py-2 text-sm">
                Open worklist →
              </Link>
            </div>
            {assignedItems != null && assignedItems.length > 0 && (
              <ul className="divide-y divide-secondary-100 border-t border-secondary-100">
                {assignedItems.slice(0, 5).map((p) => (
                  <li key={p.id} className="py-2 flex items-center gap-3 text-sm">
                    <span className="font-mono text-xs text-secondary-400">{p.ticket_number}</span>
                    <Link href={`/problems/${p.id}/workspace`} className="flex-1 truncate font-medium text-secondary-800 hover:text-primary-700">
                      {p.title}
                    </Link>
                    {(solutionFlags[p.id] === 'CHANGES_REQUESTED' || solutionFlags[p.id] === 'REPORTER_REJECTED') && (
                      <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-red-100 text-red-800">
                        Needs revision
                      </span>
                    )}
                    {(solutionFlags[p.id] === 'MENTOR_APPROVED' || solutionFlags[p.id] === 'VERIFIED') && (
                      <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-green-100 text-green-800">
                        Completed
                      </span>
                    )}
                    <span className={`text-xs font-medium px-2 py-0.5 rounded-full whitespace-nowrap ${problemStatusStyle(p.status)}`}>{p.status}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}

        {user?.role === 'MENTOR' && (
          <div className="card p-6">
            <div className="flex items-center justify-between mb-3">
              <div>
                <h2 className="text-lg font-semibold text-secondary-900">Mentored Problems</h2>
                <p className="text-sm text-secondary-600">
                  {mentoredItems == null ? 'Loading…' : `${mentoredItems.length} active mentee report${mentoredItems.length === 1 ? '' : 's'}`}
                </p>
              </div>
              <Link href="/mentored" className="btn-secondary px-4 py-2 text-sm">
                Open worklist →
              </Link>
            </div>
            {mentoredItems != null && mentoredItems.length > 0 && (
              <ul className="divide-y divide-secondary-100 border-t border-secondary-100">
                {mentoredItems.slice(0, 5).map((p) => (
                  <li key={p.id} className="py-2 flex items-center gap-3 text-sm">
                    <span className="font-mono text-xs text-secondary-400">{p.ticket_number}</span>
                    <Link href={`/problems/${p.id}/workspace`} className="flex-1 truncate font-medium text-secondary-800 hover:text-primary-700">
                      {p.title}
                    </Link>
                    {solutionFlags[p.id] === 'SUBMITTED' && (
                      <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-amber-100 text-amber-800">
                        Pending review
                      </span>
                    )}
                    <span className={`text-xs font-medium px-2 py-0.5 rounded-full whitespace-nowrap ${problemStatusStyle(p.status)}`}>{p.status}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}

        {user?.role === 'ADMIN' && (
          <div className="card p-6">
            <h2 className="text-lg font-semibold text-secondary-900 mb-1">Review Queue</h2>            {adminCounts == null ? (
              <p className="text-sm text-secondary-600">Loading queue…</p>
            ) : (
              <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                <StatCard label="Pending Review" value={adminCounts.pendingReview} href="/admin/problems?status=SUBMITTED" />
                <StatCard label="Awaiting Assignment" value={adminCounts.awaitingAssignment} href="/admin/problems?status=APPROVED" />
                <StatCard label="Recently Assigned" value={adminCounts.assigned} href="/admin/problems?status=ASSIGNED" />
                <StatCard label="In Progress" value={adminCounts.inProgress} href="/admin/problems?status=IN_PROGRESS" />
                <StatCard label="Awaiting Reporter Verification" value={adminCounts.awaitingVerification} href="/admin/problems?status=AWAITING_VERIFICATION" />
                <StatCard label="Resolved Awaiting Closure" value={adminCounts.resolvedAwaitingClosure} href="/admin/problems?status=RESOLVED" />
              </div>
            )}
            <div className="mt-4 grid grid-cols-1 sm:grid-cols-2 gap-3">
              <Link href="/admin/knowledge" className="rounded-lg border border-secondary-200 p-3 hover:border-primary-300 transition-colors">
                <p className="text-sm font-medium text-secondary-900">Knowledge Repository</p>
                <p className="text-xs text-secondary-500">
                  {knowledgeCounts == null
                    ? 'Loading publication state…'
                    : `${knowledgeCounts.published} published · ${knowledgeCounts.failed} failed · ${knowledgeCounts.archived} archived`}
                </p>
              </Link>
              <Link href="/analytics" className="rounded-lg border border-secondary-200 p-3 hover:border-primary-300 transition-colors">
                <p className="text-sm font-medium text-secondary-900">Analytics</p>
                <p className="text-xs text-secondary-500">Operational intelligence, trends, and AI health →</p>
              </Link>
            </div>
          </div>
        )}

        <div className="card p-6">
          <h2 className="text-lg font-semibold text-secondary-900 mb-2">What happens next</h2>
          <p className="text-sm text-secondary-600">
            Reports move through Submitted → Under Review → Approved → Assigned → In Progress.
            Teams submit solutions for mentor review; approved solutions await reporter verification,
            and verified reports are closed by an administrator. Every decision is recorded in the
            activity timeline.
          </p>
        </div>

        {isDev && (
          <div className="card p-6">
            <h2 className="text-sm font-semibold text-secondary-500 uppercase tracking-wider mb-4">
              System health (development only)
            </h2>
            <dl className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
              <div>
                <dt className="text-secondary-500">Backend</dt>
                <dd className="font-medium text-secondary-900">
                  {loading ? 'Checking…' : connected ? 'Connected' : 'Offline'}
                </dd>
              </div>
              <div>
                <dt className="text-secondary-500">Database</dt>
                <dd className="font-medium text-secondary-900">{data?.database ?? 'unknown'}</dd>
              </div>
              <div>
                <dt className="text-secondary-500">pgvector</dt>
                <dd className="font-medium text-secondary-900">
                  {data ? (data.pgvector_available ? 'Enabled' : 'Not installed') : 'unknown'}
                </dd>
              </div>
              <div>
                <dt className="text-secondary-500">Environment</dt>
                <dd className="font-medium text-secondary-900">{data?.environment ?? 'development'}</dd>
              </div>
            </dl>
          </div>
        )}
      </div>
    </AppLayout>
  );
}

function StatCard({ label, value, href }: { label: string; value: number; href: string }) {
  return (
    <Link href={href} className="rounded-lg border border-secondary-200 p-3 hover:border-primary-300 transition-colors">
      <p className="text-2xl font-bold text-secondary-900">{value}</p>
      <p className="text-xs text-secondary-500">{label}</p>
    </Link>
  );
}

export default function DashboardPage() {
  return (
    <RequireAuth>
      <DashboardContent />
    </RequireAuth>
  );
}
