'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { apiClient } from '@/lib/api-client';
import { API_ENDPOINTS } from '@/lib/api-config';
import { getApiErrorMessage } from '@/lib/auth-service';
import type {
  AssignmentDetail,
  EligibleSolver,
  MentorRecommendations,
  ProblemDetail,
  TeamOption,
  TeamRecommendations,
} from '@/types/api';
import { StatusStepper } from '@/components/problems/StatusStepper';

interface Props {
  problem: ProblemDetail;
  onChanged: () => Promise<void>;
}

function Modal({
  title,
  children,
  onClose,
}: {
  title: string;
  children: React.ReactNode;
  onClose: () => void;
}) {
  const panelRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', onKey);
    panelRef.current
      ?.querySelector<HTMLElement>('textarea, input, select, button:not([aria-label="Close dialog"])')
      ?.focus();
    return () => document.removeEventListener('keydown', onKey);
  }, [onClose]);
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      role="dialog"
      aria-modal="true"
      aria-label={title}
      onClick={onClose}
    >
      <div
        ref={panelRef}
        className="w-full max-w-lg rounded-xl bg-white p-6 shadow-xl max-h-[90vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold text-secondary-900">{title}</h3>
          <button
            type="button"
            className="text-secondary-500 hover:text-secondary-700 text-xl leading-none px-2"
            onClick={onClose}
            aria-label="Close dialog"
          >
            ×
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

function initials(name: string | null): string {
  if (!name) return '??';
  const parts = name.trim().split(/\s+/);
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

export function AdminReviewSection({ problem, onChanged }: Props) {
  const [detail, setDetail] = useState<AssignmentDetail | null>(null);
  const [teams, setTeams] = useState<TeamRecommendations | null>(null);
  const [mentors, setMentors] = useState<MentorRecommendations | null>(null);
  const [eligible, setEligible] = useState<EligibleSolver[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  // Assignment picker state
  const [selectedOptionId, setSelectedOptionId] = useState<string | null>(null);
  const [customMembers, setCustomMembers] = useState<string[]>([]);
  const [customMode, setCustomMode] = useState(false);
  const [solverSearch, setSolverSearch] = useState('');
  const [teamName, setTeamName] = useState('');
  const [teamReason, setTeamReason] = useState('');
  const [selectedMentorRowId, setSelectedMentorRowId] = useState<string | null>(null);
  const [mentorReason, setMentorReason] = useState('');
  const [showPreview, setShowPreview] = useState(false);
  const [modal, setModal] = useState<null | 'reject' | 'reassign' | 'cancel'>(null);
  const [reasonInput, setReasonInput] = useState('');
  const [returnTo, setReturnTo] = useState<'APPROVED' | 'UNDER_REVIEW'>('APPROVED');
  const [reassignMembers, setReassignMembers] = useState<string[]>([]);
  const [reassignMentor, setReassignMentor] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [a, t, m, e] = await Promise.all([
        apiClient.get<AssignmentDetail>(API_ENDPOINTS.adminProblems.assignment(problem.id)),
        apiClient.get<TeamRecommendations>(API_ENDPOINTS.problems.teamRecommendations(problem.id)),
        apiClient.get<MentorRecommendations>(
          API_ENDPOINTS.problems.mentorRecommendations(problem.id)
        ),
        apiClient.get<EligibleSolver[]>(API_ENDPOINTS.adminProblems.eligibleSolvers),
      ]);
      setDetail(a);
      setTeams(t);
      setMentors(m);
      setEligible(e);
    } catch (err) {
      setError(getApiErrorMessage(err, 'Could not load review workspace.'));
    } finally {
      setLoading(false);
    }
  }, [problem.id]);

  useEffect(() => {
    load();
  }, [load]);

  const refresh = async () => {
    await load();
    await onChanged();
  };

  const runAction = async (key: string, fn: () => Promise<void>, success: string) => {
    setBusy(key);
    setError(null);
    setNotice(null);
    try {
      await fn();
      await refresh();
      setNotice(success);
    } catch (err) {
      setError(getApiErrorMessage(err, 'Action failed.'));
    } finally {
      setBusy(null);
    }
  };

  const selectedOption: TeamOption | null = useMemo(
    () => teams?.options.find((o) => o.id === selectedOptionId) ?? null,
    [teams, selectedOptionId]
  );

  const effectiveMembers: string[] = useMemo(() => {
    if (customMode) return customMembers;
    if (selectedOption) return selectedOption.members.map((m) => m.user_id).filter((id): id is string => id != null);
    return [];
  }, [customMode, customMembers, selectedOption]);

  const teamNeedsReason = customMode || selectedOption == null;
  const selectedMentor = useMemo(
    () => mentors?.mentors.find((m) => m.id === selectedMentorRowId) ?? null,
    [mentors, selectedMentorRowId]
  );
  const canPreview =
    effectiveMembers.length >= 2 &&
    effectiveMembers.length <= 4 &&
    selectedMentor != null &&
    (!teamNeedsReason || teamReason.trim() !== '');

  const eligibleById = useMemo(() => {
    const map = new Map<string, EligibleSolver>();
    for (const s of eligible ?? []) map.set(s.user_id, s);
    return map;
  }, [eligible]);

  const filteredSolvers = useMemo(() => {
    const q = solverSearch.trim().toLowerCase();
    return (eligible ?? []).filter(
      (s) =>
        !effectiveMembers.includes(s.user_id) &&
        (q === '' ||
          s.name.toLowerCase().includes(q) ||
          s.skills.some((sk) => String(sk.name).toLowerCase().includes(q)))
    );
  }, [eligible, effectiveMembers, solverSearch]);

  const toggleCustomMember = (id: string) => {
    setCustomMembers((prev) =>
      prev.includes(id) ? prev.filter((m) => m !== id) : [...prev, id]
    );
  };

  const confirmAssignment = async () => {
    if (!selectedMentor?.mentor_user_id) return;
    await runAction('assign', async () => {
      const resp = await apiClient.post<{ idempotent_replay?: boolean }>(
        API_ENDPOINTS.adminProblems.assign(problem.id),
        {
          solver_user_ids: effectiveMembers,
          mentor_user_id: selectedMentor.mentor_user_id,
          team_recommendation_id: customMode ? null : selectedOption?.id ?? null,
          mentor_recommendation_id: selectedMentor.id,
          team_name: teamName.trim() || null,
          team_override_reason: teamNeedsReason ? teamReason.trim() : null,
          mentor_override_reason: mentorReason.trim() || null,
        }
      );
      void resp;
      setShowPreview(false);
      setCustomMode(false);
      setCustomMembers([]);
      setSelectedOptionId(null);
      setSelectedMentorRowId(null);
      setTeamReason('');
      setMentorReason('');
      setTeamName('');
    }, 'Assignment complete — team and mentor assigned.');
  };

  const active = detail?.active ?? null;
  const recommendedOption = active?.source_team_recommendation_id
    ? (teams?.options.find((o) => o.id === active.source_team_recommendation_id) ?? null)
    : null;

  return (
    <div className="card p-6 space-y-5">
      <div>
        <h2 className="text-lg font-semibold text-secondary-900 mb-3">Admin Review Workspace</h2>
        <StatusStepper status={problem.status} />
      </div>

      {loading ? (
        <div className="space-y-2" aria-label="Loading review workspace">
          <div className="h-4 rounded bg-secondary-100 animate-pulse w-1/3" />
          <div className="h-24 rounded-lg bg-secondary-100 animate-pulse" />
        </div>
      ) : (
        <>
          {notice && (
            <div role="status" className="rounded-lg border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-800">
              {notice}
            </div>
          )}
          {error && (
            <div role="alert" className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
              {error}
            </div>
          )}

          {/* State actions */}
          {problem.status === 'SUBMITTED' && (
            <button
              type="button"
              className="btn-primary px-4 py-2 text-sm"
              disabled={busy != null}
              onClick={() =>
                runAction('review', async () => {
                  await apiClient.post(API_ENDPOINTS.adminProblems.startReview(problem.id), {});
                }, 'Review started.')
              }
            >
              {busy === 'review' ? 'Working…' : 'Start Review'}
            </button>
          )}

          {problem.status === 'UNDER_REVIEW' && (
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                className="btn-primary px-4 py-2 text-sm"
                disabled={busy != null}
                onClick={() =>
                  runAction('approve', async () => {
                    await apiClient.post(API_ENDPOINTS.adminProblems.approve(problem.id), {});
                  }, 'Report approved.')
                }
              >
                {busy === 'approve' ? 'Working…' : 'Approve'}
              </button>
              <button
                type="button"
                className="btn-secondary px-4 py-2 text-sm"
                disabled={busy != null}
                onClick={() => {
                  setReasonInput('');
                  setModal('reject');
                }}
              >
                Reject
              </button>
            </div>
          )}

          {problem.status === 'APPROVED' && !active && (
            <div className="space-y-4">
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  className="btn-secondary px-4 py-2 text-sm"
                  disabled={busy != null}
                  onClick={() => {
                    setReasonInput('');
                    setModal('reject');
                  }}
                >
                  Reject
                </button>
              </div>

              {/* Team selection */}
              <div>
                <h3 className="text-sm font-semibold text-secondary-900 mb-2">1. Select team</h3>
                {teams && teams.options.length > 0 ? (
                  <ul className="space-y-2">
                    {teams.options.map((o, i) => {
                      const chosen = selectedOptionId === o.id && !customMode;
                      return (
                        <li
                          key={o.id}
                          className={`rounded-lg border p-3 text-sm ${
                            chosen ? 'border-primary-400 bg-primary-50/50' : 'border-secondary-200'
                          }`}
                        >
                          <label className="flex items-start gap-2 cursor-pointer">
                            <input
                              type="radio"
                              name="team-option"
                              checked={chosen}
                              onChange={() => {
                                setSelectedOptionId(o.id);
                                setCustomMode(false);
                              }}
                              className="mt-1"
                            />
                            <span className="flex-1">
                              <span className="font-medium text-secondary-900">
                                Option {i + 1} · score {Math.round(o.score)} · coverage{' '}
                                {Math.round(o.coverage_percent)}%
                              </span>
                              <span className="block text-secondary-600">
                                {o.members.map((m) => m.name).join(', ')}
                              </span>
                              {o.missing_skills.length > 0 && (
                                <span className="block text-xs text-secondary-500">
                                  Missing: {o.missing_skills.join(', ')}
                                </span>
                              )}
                            </span>
                          </label>
                        </li>
                      );
                    })}
                  </ul>
                ) : (
                  <p className="text-sm text-secondary-600">
                    No AI team options ({teams?.status ?? 'not run'}). Compose the team manually —
                    an override reason is required.
                  </p>
                )}
                <label className="mt-2 flex items-center gap-2 text-sm text-secondary-700 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={customMode}
                    onChange={(e) => {
                      setCustomMode(e.target.checked);
                      if (e.target.checked) setSelectedOptionId(null);
                    }}
                  />
                  Edit / compose custom team
                </label>
                {customMode && (
                  <div className="mt-2 rounded-lg border border-secondary-200 p-3 space-y-2">
                    {customMembers.length > 0 && (
                      <div className="flex flex-wrap gap-1.5">
                        {customMembers.map((id) => (
                          <button
                            key={id}
                            type="button"
                            className="text-xs px-2 py-1 rounded-full bg-primary-100 text-primary-800 hover:bg-primary-200"
                            onClick={() => toggleCustomMember(id)}
                            title="Remove"
                          >
                            {eligibleById.get(id)?.name ?? id} ×
                          </button>
                        ))}
                      </div>
                    )}
                    <input
                      className="input-field text-sm"
                      placeholder="Search solvers by name or skill…"
                      value={solverSearch}
                      onChange={(e) => setSolverSearch(e.target.value)}
                      aria-label="Search eligible solvers"
                    />
                    <ul className="max-h-48 overflow-y-auto divide-y divide-secondary-100 text-sm">
                      {filteredSolvers.slice(0, 20).map((s) => (
                        <li key={s.user_id}>
                          <button
                            type="button"
                            className="w-full text-left py-1.5 hover:bg-secondary-50 px-1 rounded disabled:opacity-40"
                            disabled={customMembers.length >= 4}
                            onClick={() => toggleCustomMember(s.user_id)}
                          >
                            <span className="font-medium text-secondary-800">{s.name}</span>{' '}
                            <span className="text-xs text-secondary-500">
                              {s.availability} · {s.current_workload}/{s.max_workload} ·{' '}
                              {s.skills.map((sk) => String(sk.name)).slice(0, 4).join(', ')}
                            </span>
                          </button>
                        </li>
                      ))}
                      {filteredSolvers.length === 0 && (
                        <li className="py-2 text-secondary-500 text-xs">No matching solvers.</li>
                      )}
                    </ul>
                    {(customMembers.length < 2 || customMembers.length > 4) && (
                      <p className="text-xs text-amber-700">
                        Select 2–4 solvers (currently {customMembers.length}).
                      </p>
                    )}
                  </div>
                )}
                <input
                  className="input-field text-sm mt-2"
                  placeholder="Team name (optional)"
                  value={teamName}
                  onChange={(e) => setTeamName(e.target.value)}
                  maxLength={100}
                  aria-label="Team name"
                />
                {teamNeedsReason && (
                  <textarea
                    className="input-field text-sm mt-2"
                    rows={2}
                    placeholder="Team override reason (required — why this team instead of the recommendation?)"
                    value={teamReason}
                    onChange={(e) => setTeamReason(e.target.value)}
                    maxLength={1000}
                    aria-label="Team override reason"
                  />
                )}
              </div>

              {/* Mentor selection */}
              <div>
                <h3 className="text-sm font-semibold text-secondary-900 mb-2">2. Select mentor</h3>
                {mentors && mentors.mentors.length > 0 ? (
                  <ul className="space-y-2">
                    {mentors.mentors.map((m, i) => {
                      const chosen = selectedMentorRowId === m.id;
                      return (
                        <li
                          key={m.id}
                          className={`rounded-lg border p-3 text-sm ${
                            chosen ? 'border-primary-400 bg-primary-50/50' : 'border-secondary-200'
                          }`}
                        >
                          <label className="flex items-start gap-2 cursor-pointer">
                            <input
                              type="radio"
                              name="mentor-option"
                              checked={chosen}
                              onChange={() => setSelectedMentorRowId(m.id)}
                              className="mt-1"
                            />
                            <span className="flex items-center gap-2 flex-1 min-w-0">
                              <span
                                className="w-8 h-8 rounded-full bg-primary-100 text-primary-700 font-semibold text-xs flex items-center justify-center flex-shrink-0"
                                aria-hidden="true"
                              >
                                {initials(m.name)}
                              </span>
                              <span className="min-w-0">
                                <span className="font-medium text-secondary-900 block truncate">
                                  {i === 0 ? `${m.name} (top ranked)` : m.name}
                                </span>
                                <span className="block text-xs text-secondary-500 truncate">
                                  {[m.designation, m.specialization].filter(Boolean).join(' · ')} ·
                                  score {Math.round(m.score)}
                                </span>
                              </span>
                            </span>
                          </label>
                        </li>
                      );
                    })}
                  </ul>
                ) : (
                  <p className="text-sm text-secondary-600">No mentor candidates available.</p>
                )}
                {selectedMentor == null && (
                  <p className="text-xs text-secondary-500 mt-1">Select a mentor to continue.</p>
                )}
                {selectedMentor != null && (
                  <p className="text-xs text-secondary-500 mt-1">
                    Selecting a ranked mentor accepts that evaluation. Add an optional note below
                    if needed.
                  </p>
                )}
                <textarea
                  className="input-field text-sm mt-2"
                  rows={2}
                  placeholder="Mentor note (optional when accepting a ranked evaluation)"
                  value={mentorReason}
                  onChange={(e) => setMentorReason(e.target.value)}
                  maxLength={1000}
                  aria-label="Mentor note"
                />
              </div>

              {/* Preview + confirm */}
              <div>
                <button
                  type="button"
                  className="btn-primary px-4 py-2 text-sm"
                  disabled={!canPreview || busy != null}
                  onClick={() => setShowPreview(true)}
                >
                  Preview Assignment
                </button>
                {!canPreview && (
                  <p className="text-xs text-secondary-500 mt-1">
                    Select a team (2–4 solvers), a mentor, and any required override reasons.
                  </p>
                )}
              </div>
            </div>
          )}

          {/* Active assignment */}
          {active && (
            <div className="rounded-xl border border-green-200 bg-green-50/50 p-4 space-y-3">
              <h3 className="font-semibold text-secondary-900">
                Assignment Complete — {active.team.display_label}
              </h3>
              <div className="text-sm space-y-1">
                <p>
                  <span className="text-secondary-500">Team: </span>
                  <span className="font-medium text-secondary-900">
                    {active.team.members.filter((m) => m.is_active).map((m) => m.name).join(', ')}
                  </span>
                </p>
                <p>
                  <span className="text-secondary-500">Mentor: </span>
                  <span className="font-medium text-secondary-900">
                    {active.mentor.name}
                    {active.mentor.designation ? ` (${active.mentor.designation})` : ''}
                  </span>
                </p>
                <p className="text-secondary-600">
                  AI recommended:{' '}
                  {recommendedOption
                    ? `${recommendedOption.members.map((m) => m.name).join(' + ')} (Option, score ${Math.round(recommendedOption.score)})`
                    : 'no cited team option (manual composition)'}
                </p>
                <p className="text-secondary-600">
                  Final assigned:{' '}
                  {active.team.members.filter((m) => m.is_active).map((m) => m.name).join(' + ')}
                  {active.team_was_overridden ? ' — overridden' : ' — as recommended'}
                </p>
                {active.team_was_overridden && active.team_override_reason && (
                  <p className="text-secondary-600">Reason: {active.team_override_reason}</p>
                )}
                {active.mentor_was_overridden && active.mentor_override_reason && (
                  <p className="text-secondary-600">
                    Mentor override reason: {active.mentor_override_reason}
                  </p>
                )}
              </div>
              {(detail?.history.length ?? 0) > 1 && (
                <div className="text-xs text-secondary-500">
                  <p className="font-medium text-secondary-700 mb-1">Assignment history</p>
                  <ul className="space-y-0.5">
                    {detail?.history.map((h) => (
                      <li key={h.id}>
                        {h.status} · {h.member_count} member(s) · {h.mentor_name ?? '—'} ·{' '}
                        {new Date(h.assigned_at).toLocaleString()}
                        {h.unassignment_reason ? ` · ${h.unassignment_reason}` : ''}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  className="btn-secondary px-3 py-1.5 text-sm"
                  disabled={busy != null}
                  onClick={() => {
                    setReassignMembers(
                      active.team.members.filter((m) => m.is_active).map((m) => m.user_id).filter((id): id is string => id != null)
                    );
                    setReassignMentor(active.mentor.user_id);
                    setReasonInput('');
                    setModal('reassign');
                  }}
                >
                  Reassign
                </button>
                <button
                  type="button"
                  className="btn-secondary px-3 py-1.5 text-sm"
                  disabled={busy != null}
                  onClick={() => {
                    setReasonInput('');
                    setReturnTo('APPROVED');
                    setModal('cancel');
                  }}
                >
                  Cancel Assignment
                </button>
              </div>
            </div>
          )}

          {problem.status === 'REJECTED' && (
            <p className="text-sm text-secondary-600">
              Rejected{problem.rejection_reason ? `: ${problem.rejection_reason}` : '.'} This
              decision is preserved in the activity timeline.
            </p>
          )}
        </>
      )}

      {/* Reject modal */}
      {modal === 'reject' && (
        <Modal title="Reject report" onClose={() => setModal(null)}>
          <div className="space-y-3">
            <p className="text-sm text-secondary-600">
              The reporter will see this reason. It cannot be empty.
            </p>
            <textarea
              className="input-field text-sm"
              rows={3}
              value={reasonInput}
              onChange={(e) => setReasonInput(e.target.value)}
              maxLength={1000}
              placeholder="Rejection reason (required)"
              aria-label="Rejection reason"
            />
            <div className="flex gap-2">
              <button
                type="button"
                className="btn-danger px-4 py-2 text-sm"
                disabled={busy != null || reasonInput.trim() === ''}
                onClick={() => {
                  setModal(null);
                  void runAction('reject', async () => {
                    await apiClient.post(API_ENDPOINTS.adminProblems.reject(problem.id), {
                      reason: reasonInput.trim(),
                    });
                  }, 'Report rejected.');
                }}
              >
                {busy === 'reject' ? 'Working…' : 'Confirm Reject'}
              </button>
              <button type="button" className="btn-secondary px-4 py-2 text-sm" onClick={() => setModal(null)}>
                Cancel
              </button>
            </div>
          </div>
        </Modal>
      )}

      {/* Preview modal */}
      {showPreview && selectedMentor && (
        <Modal title="Confirm Assignment" onClose={() => setShowPreview(false)}>
          <div className="space-y-3 text-sm">
            <div>
              <p className="font-medium text-secondary-900">{problem.ticket_number}</p>
              <p className="text-secondary-600">{problem.title}</p>
            </div>
            <div>
              <p className="font-medium text-secondary-700">Team ({effectiveMembers.length})</p>
              <ul className="list-disc list-inside text-secondary-600">
                {effectiveMembers.map((id) => (
                  <li key={id}>{eligibleById.get(id)?.name ?? id}</li>
                ))}
              </ul>
              {selectedOption && !customMode && (
                <p className="text-xs text-secondary-500 mt-1">
                  Skills covered: {selectedOption.coverage_percent}% · Missing:{' '}
                  {selectedOption.missing_skills.join(', ') || 'none'}
                </p>
              )}
              {teamName.trim() && <p className="text-xs text-secondary-500">Team name: {teamName.trim()}</p>}
              {teamNeedsReason && <p className="text-xs text-secondary-600">Override: {teamReason.trim()}</p>}
            </div>
            <div>
              <p className="font-medium text-secondary-700">Mentor</p>
              <p className="text-secondary-600">
                {selectedMentor.name} · {selectedMentor.specialization} · score{' '}
                {Math.round(selectedMentor.score)}
              </p>
              {mentorReason.trim() && <p className="text-xs text-secondary-600">Note: {mentorReason.trim()}</p>}
            </div>
            <p className="text-xs text-secondary-500">
              AI recommendation used: {selectedOption && !customMode ? `team Option (score ${Math.round(selectedOption.score)})` : 'none (manual team)'}
              {' · '}mentor ranked evaluation. Workloads increment by 1 for every selected member
              and the mentor, atomically.
            </p>
            <div className="flex gap-2">
              <button
                type="button"
                className="btn-primary px-4 py-2 text-sm"
                disabled={busy != null}
                onClick={() => void confirmAssignment()}
              >
                {busy === 'assign' ? 'Assigning…' : 'Confirm Assignment'}
              </button>
              <button type="button" className="btn-secondary px-4 py-2 text-sm" onClick={() => setShowPreview(false)}>
                Back
              </button>
            </div>
          </div>
        </Modal>
      )}

      {/* Reassign modal */}
      {modal === 'reassign' && active && (
        <Modal title="Reassign team / mentor" onClose={() => setModal(null)}>
          <ReassignForm
            eligible={eligible ?? []}
            mentors={mentors?.mentors ?? []}
            members={reassignMembers}
            setMembers={setReassignMembers}
            mentorId={reassignMentor}
            setMentorId={setReassignMentor}
            reason={reasonInput}
            setReason={setReasonInput}
            busy={busy != null}
            onSubmit={() => {
              setModal(null);
              void runAction('reassign', async () => {
                await apiClient.post(API_ENDPOINTS.adminProblems.reassign(problem.id), {
                  solver_user_ids: reassignMembers,
                  mentor_user_id: reassignMentor,
                  reason: reasonInput.trim(),
                });
              }, 'Reassignment complete.');
            }}
          />
        </Modal>
      )}

      {/* Cancel modal */}
      {modal === 'cancel' && (
        <Modal title="Cancel assignment" onClose={() => setModal(null)}>
          <div className="space-y-3 text-sm">
            <p className="text-secondary-600">
              Workloads are released exactly once. The report returns to an earlier state.
            </p>
            <textarea
              className="input-field"
              rows={3}
              value={reasonInput}
              onChange={(e) => setReasonInput(e.target.value)}
              maxLength={1000}
              placeholder="Cancellation reason (required)"
              aria-label="Cancellation reason"
            />
            <fieldset>
              <legend className="font-medium text-secondary-700 mb-1">Return report to</legend>
              <label className="flex items-center gap-2 text-secondary-700">
                <input
                  type="radio"
                  name="return-to"
                  checked={returnTo === 'APPROVED'}
                  onChange={() => setReturnTo('APPROVED')}
                />
                Approved (awaiting assignment)
              </label>
              <label className="flex items-center gap-2 text-secondary-700">
                <input
                  type="radio"
                  name="return-to"
                  checked={returnTo === 'UNDER_REVIEW'}
                  onChange={() => setReturnTo('UNDER_REVIEW')}
                />
                Under review
              </label>
            </fieldset>
            <div className="flex gap-2">
              <button
                type="button"
                className="btn-primary px-4 py-2 text-sm"
                disabled={busy != null || reasonInput.trim() === ''}
                onClick={() => {
                  setModal(null);
                  void runAction('cancel', async () => {
                    await apiClient.post(API_ENDPOINTS.adminProblems.cancelAssignment(problem.id), {
                      reason: reasonInput.trim(),
                      return_to: returnTo,
                    });
                  }, 'Assignment cancelled.');
                }}
              >
                {busy === 'cancel' ? 'Working…' : 'Confirm Cancel'}
              </button>
              <button type="button" className="btn-secondary px-4 py-2 text-sm" onClick={() => setModal(null)}>
                Back
              </button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}

function ReassignForm({
  eligible,
  mentors,
  members,
  setMembers,
  mentorId,
  setMentorId,
  reason,
  setReason,
  busy,
  onSubmit,
}: {
  eligible: EligibleSolver[];
  mentors: Array<{ id: string; mentor_user_id: string | null; name: string | null; score: number }>;
  members: string[];
  setMembers: (_ids: string[]) => void;
  mentorId: string | null;
  setMentorId: (_id: string | null) => void;
  reason: string;
  setReason: (_v: string) => void;
  busy: boolean;
  onSubmit: () => void;
}) {
  const [q, setQ] = useState('');
  const byId = new Map(eligible.map((s) => [s.user_id, s]));
  const filtered = eligible.filter(
    (s) =>
      !members.includes(s.user_id) &&
      (q.trim() === '' || s.name.toLowerCase().includes(q.trim().toLowerCase()))
  );
  const valid = members.length >= 2 && members.length <= 4 && mentorId != null && reason.trim() !== '';
  return (
    <div className="space-y-3 text-sm">
      <div>
        <p className="font-medium text-secondary-700 mb-1">Team ({members.length})</p>
        <div className="flex flex-wrap gap-1.5 mb-2">
          {members.map((id) => (
            <button
              key={id}
              type="button"
              className="text-xs px-2 py-1 rounded-full bg-primary-100 text-primary-800 hover:bg-primary-200"
              onClick={() => setMembers(members.filter((m) => m !== id))}
              title="Remove"
            >
              {byId.get(id)?.name ?? id} ×
            </button>
          ))}
        </div>
        <input
          className="input-field text-sm"
          placeholder="Search solvers to add…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          aria-label="Search solvers"
        />
        <ul className="max-h-40 overflow-y-auto divide-y divide-secondary-100 mt-1">
          {filtered.slice(0, 15).map((s) => (
            <li key={s.user_id}>
              <button
                type="button"
                className="w-full text-left py-1.5 hover:bg-secondary-50 px-1 rounded disabled:opacity-40"
                disabled={members.length >= 4}
                onClick={() => setMembers([...members, s.user_id])}
              >
                <span className="font-medium text-secondary-800">{s.name}</span>{' '}
                <span className="text-xs text-secondary-500">
                  {s.availability} · {s.current_workload}/{s.max_workload}
                </span>
              </button>
            </li>
          ))}
        </ul>
      </div>
      <div>
        <p className="font-medium text-secondary-700 mb-1">Mentor</p>
        <ul className="space-y-1">
          {mentors.map((m) => (
            <li key={m.id}>
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="radio"
                  name="reassign-mentor"
                  checked={mentorId === m.mentor_user_id}
                  onChange={() => setMentorId(m.mentor_user_id)}
                />
                <span className="font-medium text-secondary-800">{m.name}</span>
                <span className="text-xs text-secondary-500">score {Math.round(m.score)}</span>
              </label>
            </li>
          ))}
        </ul>
      </div>
      <textarea
        className="input-field"
        rows={2}
        value={reason}
        onChange={(e) => setReason(e.target.value)}
        maxLength={1000}
        placeholder="Reassignment reason (required)"
        aria-label="Reassignment reason"
      />
      <div className="flex gap-2">
        <button
          type="button"
          className="btn-primary px-4 py-2 text-sm"
          disabled={!valid || busy}
          onClick={onSubmit}
        >
          Confirm Reassign
        </button>
      </div>
      {!valid && (
        <p className="text-xs text-secondary-500">
          Select 2–4 solvers, a mentor, and a reason to continue.
        </p>
      )}
    </div>
  );
}
