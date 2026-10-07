# Step 10: Team Workspace — Tasks, Milestones & Real Progress Tracking

**Status: Complete.** Backend: 192 tests passing (19 new). Ruff/MyPy clean.
Frontend: ESLint, type-check, production build green.

## 1. What already existed before this step

- `ProblemEventType` already contained `WORK_STARTED`, `TASK_*`, `MILESTONE_*`,
  `PROGRESS_UPDATED`, `WORK_FILE_*` labels (code only, **not** in the DB enum).
- `ProblemComment.is_internal` already supported internal notes (admin-only writes).
- Step 4 storage abstraction (`sanitize_filename`, `sniff_mime`,
  `LocalAttachmentStorage`) was reusable as-is.
- `/assigned` and `/mentored` worklists already existed.
- **Regression found and fixed:** `ProblemEventType` was missing `SUBMITTED`
  (present in DB migration 004, used by `ProblemService`), which broke the
  whole suite. Re-added; no migration needed.

No task/milestone/progress models, APIs, or workspace UI existed.

## 2. What was built now

### Migration `010_tasks_progress` (new, head)

- Appends 15 workspace event labels to the `problem_event_type` enum
  (downgrade-safe, missing-only pattern from 007–009).
- New tables: `problem_tasks`, `problem_milestones`,
  `problem_progress_updates`, `problem_work_attachments`
  (all `CASCADE` on problem delete; assignee/uploader use `SET NULL` so
  authorship survives reassignment).
- New cached column `problems.progress_percent` (0–100 check constraint).

### Models (`app/models/workspace.py`)

- `ProblemTask`: title/description, assignee (nullable), creator, status
  (`TODO/IN_PROGRESS/BLOCKED/DONE/CANCELLED`), priority
  (`LOW/MEDIUM/HIGH/CRITICAL`), due date, order index, blocker reason,
  started/completed timestamps.
- `ProblemMilestone`: title/description, target date, status
  (`PLANNED/IN_PROGRESS/COMPLETED/MISSED/CANCELLED`), order index,
  completed timestamp.
- `ProblemProgressUpdate`: summary/details/blockers/next steps plus a
  server-computed `progress_snapshot` (client can never supply progress).
- `ProblemWorkAttachment`: optional task link, storage key, MIME, size,
  description, `is_reporter_visible` (always `False`).

### Transitions

- Tasks: `TASK_TRANSITIONS` allow-list in `app/core/enums.py`.
  `TODO→IN_PROGRESS/CANCELLED`, `IN_PROGRESS→BLOCKED/DONE/TODO/CANCELLED`,
  `BLOCKED→IN_PROGRESS/CANCELLED`. `BLOCKED` requires `blocker_reason`;
  the reason is kept (never auto-cleared). `DONE` reopening is
  mentor/admin-only via an explicit privileged path.
- Milestones: `MILESTONE_TRANSITIONS` allow-list; terminal states
  (`COMPLETED/MISSED/CANCELLED`) cannot be left.

### Real progress formula (`compute_progress`)

- Tasks 70% + milestones 30%; cancelled items excluded.
- Only tasks → 100% task weight; only milestones → 100% milestone weight;
  neither → 0%. Clamped 0–100, rounded to 2 decimals.
- Synced to `problems.progress_percent` on every task/milestone/progress
  change; the cache is never the source of truth.

### `ASSIGNED → IN_PROGRESS`

- Fires exactly once on first task start, first milestone start, or first
  progress update, guarded by the existing `WORK_STARTED` activity event.

### Permissions

- Insider = active team member, assigned mentor, or admin. Writes additionally
  require an ACTIVE assignment and `ASSIGNED`/`IN_PROGRESS` status.
- Members: create unassigned/self-assigned tasks, edit/transition own tasks,
  claim unassigned tasks. No peer assignment.
- Mentor/admin: assign to any active member, edit/transition any task,
  reopen DONE tasks, full milestone authority, file delete.
- Milestones: mentor/admin only (members read-only).
- Progress updates: member/mentor/admin post; reporter read-only safe view.
- Files: member/mentor/admin upload; uploader/mentor/admin delete.
- Discussion reuses `ProblemComment(is_internal=True)`; workspace service
  allows member/mentor posts (Step 4 admin-only rule preserved elsewhere).
- Reporter: `GET /public-progress` only (counts, names, safe summaries).
  No workspace, files, discussion, or internals (verified by tests + smoke).
- Removed members lose access immediately (404); their unfinished tasks are
  unassigned with `TASK_REASSIGNED` activity (hooked into
  `AssignmentService._reassign_inner`). Authorship/history preserved.
- Cancelled assignment: history readable by admin; all new work blocked
  (409/404); nothing deleted.

### APIs (`app/api/v1/workspace.py`, mounted in `main.py`)

- `GET /problems/{id}/workspace` (overview: ticket, status, priority,
  category, skills, team, mentor, assignment date, real progress).
- Tasks: `GET/POST /tasks`, `PATCH /tasks/{id}`, `DELETE /tasks/{id}` (cancel).
- Milestones: `GET/POST /milestones`, `PATCH /milestones/{id}`.
- Progress: `GET/POST /progress-updates`.
- Files: `GET/POST /work-files`, `DELETE /work-files/{id}`,
  `GET /work-files/{id}/download`.
- Discussion: `GET/POST /discussion` (internal only).
- `GET /problems/{id}/public-progress` (reporter-safe).
- `ProblemResponse` now includes `progress_percent`.

### Frontend

- `/problems/[id]/workspace`: header with progress bar, tabs for Overview,
  Tasks (grouped To Do/In Progress/Blocked/Done board + create/edit,
  blocker dialog, overdue/blocked markers), Milestones (timeline),
  Progress (counts + update timeline), Files (upload/download/delete),
  Discussion (internal, role-labelled), Activity.
- Report detail page: workspace entry card for team/mentor/admin plus a
  reporter-safe Resolution Progress card.
- `/assigned` + `/mentored` worklists link to each workspace; solver/mentor
  dashboards list work items with workspace links; admin queue adds the
  In Progress count.

## 3. Tests

`tests/test_workspace.py` — 19 tests: task create/permissions/assignee
validation (non-team, mentor, reporter, peer), transitions + blocker rule,
mentor-only reopen, cancel, cross-problem IDOR, milestone permissions/flow,
70/30 formula + edge cases (tasks-only, cancelled excluded, neither),
snapshot + single WORK_STARTED, file flow + validations (MIME, mismatch,
oversize, auth), full access matrix, internal discussion isolation,
reassignment unassignment + access loss/gain, cancellation preservation,
reporter safe-view field audit, dashboard worklists.

## 4. Real E2E smoke (`scripts/smoke_workspace.py`, live HTTP)

Measured on a real assignment (Smoke Crew: solver1+solver2, mentor1):

- Initial: **0%**
- First task start → status `IN_PROGRESS`, one `WORK_STARTED`
- Block with reason preserved
- 1/2 tasks done, 0/2 milestones done → **35.0%**
- 2/2 tasks done, 1/2 milestones done → **85.0%**
- Reporter safe view shows 85.0% + team/mentor names; internals
  (blocker text, filenames, discussion) absent; workspace → 403.

## 5. Limitations / not in this step

- No solution submission, mentor final review, reporter verification,
  notifications, closure, knowledge repository, or analytics (Step 11+).
- Work-file cap is 20 per report; no full-text search over workspace.
- Overdue is derived at read time (no scheduled `MISSED` transitions).
- Step 11 (`AWAITING_VERIFICATION`/`RESOLVED`/`CLOSED`) has NOT started.
