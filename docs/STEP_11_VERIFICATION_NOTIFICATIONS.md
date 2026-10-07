# Step 11: Solution Submission + Mentor Review + Notifications + Reporter Verification + Verified Closure

**Status: complete.** Backend: 212 tests passing (20 new: 14 verification + 6 notifications).
Ruff/MyPy clean. Frontend: ESLint, type-check, production build green
(incl. `/notifications` route). Alembic head: `011`.

## 1. Pre-existing Step 11 work

None. The audit found no migration 011, no solution/review/verification/
notification models, services, routes, or UI — only incidental word matches
(`is_verified` skill flags, the `AWAITING_VERIFICATION` status string in
filters) and the Step 10 workspace it builds on. Everything below is new,
reusing Steps 1–10 architecture untouched (one additive visibility extension
in `ProblemService`/`WorkspaceService`, two best-effort notification hooks).

## 2. Migration 011 (`011_notifications_verification`, new head)

- Appends 8 event labels (`SOLUTION_SUBMITTED`, `MENTOR_CHANGES_REQUESTED`,
  `MENTOR_SOLUTION_APPROVED`, `REPORTER_VERIFICATION_REQUESTED`,
  `REPORTER_CONFIRMED_RESOLUTION`, `REPORTER_REJECTED_RESOLUTION`,
  `PROBLEM_RESOLVED`, `PROBLEM_CLOSED`) to `problem_event_type`
  (missing-only, downgrade-safe pattern from 007–010).
- New tables: `problem_solution_submissions`, `mentor_solution_reviews`,
  `problem_resolution_verifications`, `notifications`.
- Audit FKs (`submitted_by`, `mentor_user_id`, `reporter_user_id`) are
  **nullable + `SET NULL`**, matching Step 9's `reviewed_by`/`approved_by`
  pattern — a live smoke run proved `NOT NULL + SET NULL` breaks user
  cleanup, so this was corrected before release. Never rewrites 001–010.

## 3. Solution submission design

`ProblemSolutionSubmission`: `revision_number` (append-only; resubmission =
new row), `solution_summary`/`root_cause`/`work_performed` (+ optional
testing/deployment/limitations), `evidence_attachment_ids` (JSON list of
same-problem work-attachment UUIDs, validated), `share_evidence_with_reporter`
flag, `readiness_override_reason`, status
(`SUBMITTED → CHANGES_REQUESTED / MENTOR_APPROVED → REPORTER_REJECTED / VERIFIED`).

- Only **active team members**, problem must be **IN_PROGRESS**, assignment ACTIVE.
- Reporter / unrelated solver / removed member / other mentor → 403/404.
- Mentors never submit (403); **admin** may submit, and only an admin may pass
  `override_reason` to bypass readiness (audited in activity + stored on row).

## 4. Completion readiness (documented policy)

Enforced on submit unless admin-overridden. Ready requires **all** of:
no `BLOCKED` active tasks; every non-cancelled `HIGH`/`CRITICAL` task `DONE`;
every non-cancelled milestone `COMPLETED`; live progress ≥ **80%**.
We deliberately do NOT demand blind 100% (`LOW`/`MEDIUM` tasks may stay open).
`GET /solution/readiness` exposes the same check with reasons for the UI.

## 5. Solution evidence

Reuses the Step 4/10 secure upload path — no second upload system.
Submissions link existing work files; `share_evidence_with_reporter=True`
flips `is_reporter_visible` on exactly those files. Reporter download goes
through a dedicated endpoint that re-checks approval + linkage.

## 6. Mentor review

`MentorSolutionReview` rows (append-only, never overwritten): decision
`APPROVED`/`CHANGES_REQUESTED`, comment **required** for changes.
Only the **current assigned mentor**; admin override allowed with mandatory
comment, flagged `is_admin_override` and audited.

- Approve → submission `MENTOR_APPROVED`, problem `IN_PROGRESS →
  AWAITING_VERIFICATION`, reporter notified.
- Request changes → submission `CHANGES_REQUESTED`, problem **stays**
  `IN_PROGRESS`, team notified; team submits a new revision.

## 7. Reporter verification

`ProblemResolutionVerification` rows (append-only). Only the **original
reporter**, only in `AWAITING_VERIFICATION`, only against a `MENTOR_APPROVED`
latest revision.

- YES → submission `VERIFIED`, problem → `RESOLVED` + `resolved_at`; team and
  mentor notified. **Workloads stay allocated.**
- NO (reason mandatory) → submission `REPORTER_REJECTED`, problem →
  `IN_PROGRESS`; assignment stays `ACTIVE`, workloads stay, workspace stays
  writable — no new assignment. Team + mentor notified with the reason.

## 8. Closure policy (documented)

**Reporter verifies → `RESOLVED`; admin finalizes → `CLOSED`.** No auto-close:
the explicit admin step keeps the lifecycle auditable
(`POST /admin/problems/{id}/close`, `RESOLVED → CLOSED` only).
No reopen-from-`CLOSED` (left for future admin policy; documented).

## 9. Workload release strategy (documented)

Released **exactly once, at `CLOSED` only** — never at submit, review, or
verify. `close_problem` locks the assignment row, flips `ACTIVE → COMPLETED`,
and decrements each active solver and the mentor with a `max(0, …)` floor.
A retried close lands on `CLOSED` and is rejected with 409 **before** any
decrement, so double release is impossible. Same-transaction commit covers
status + workloads + notifications + activity (no half-states).

## 10. Status transitions (central map in `SolutionService`)

`mentor_approve`: `IN_PROGRESS → AWAITING_VERIFICATION`;
`mentor_request_changes`: `IN_PROGRESS → IN_PROGRESS`;
`reporter_confirm`: `AWAITING_VERIFICATION → RESOLVED`;
`reporter_reject`: `AWAITING_VERIFICATION → IN_PROGRESS`;
`admin_close`: `RESOLVED → CLOSED`. Anything else → 409.

## 11. Notifications

- Model: `Notification` (recipient, controlled `NotificationType`, safe
  title/message, optional problem link, related entity, `read_at`).
  Only safe display content is stored — never internals, files, or workloads.
- `NotificationService` is the single creation point (`notify_user/team/
  mentor/reporter`); `NotificationProvider` protocol reserves the seam for
  future email/push, which are **not** faked or claimed.
- Transactional strategy: Step 11 core flows commit state + notifications
  **atomically** (failure rolls everything back). Hooks into older flows
  (assignment create → `TEAM_ASSIGNED`/`MENTOR_ASSIGNED`; task create with
  assignee → `TASK_ASSIGNED`; task blocked → `TASK_BLOCKED` to team+mentor)
  are best-effort **post-commit** so they can never break Steps 9–10.
- No retroactive backfill of historical notifications (deliberate).
- APIs (own-notifications-only, IDOR-tested): `GET /notifications`
  (pagination + `unread_only`), `GET /notifications/unread-count`,
  `PATCH /notifications/{id}/read`, `POST /notifications/read-all`.

## 12. Access control summary

| Actor | Submit | Review | Verify | Close | Workspace after close |
|---|---|---|---|---|---|
| Active team member | ✅ | ❌ | ❌ | ❌ | read history |
| Assigned mentor | ❌ | ✅ | ❌ | ❌ | read history |
| Reporter (owner) | ❌ | ❌ | ✅ | ❌ | safe view only |
| Admin | ✅ override-only | ✅ override (comment req.) | ❌ | ✅ | full |
| Others | ❌ | ❌ | ❌ | ❌ | denied |

Reporter sees: safe solution summary/work/testing/limitations, explicitly
shared evidence metadata, team/mentor names, counts — verified by field-audit
tests asserting internals never leak.

## 13. Frontend

- Header `NotificationBell` (unread badge, dropdown, 30s poll + refetch on
  open, marks read on open) + sidebar Notifications item + `/notifications`
  page (loading/empty/error/unread/read, pagination, mark one/all read).
- Workspace **Solution** tab: readiness card with reasons, submit form
  (incl. evidence picker + share flag + admin override field), revision
  history with reviews, mentor review dialog (no `alert()`), pending-review
  badge on the tab.
- Report detail: reporter verification card (YES / NO-with-required-reason +
  safe solution summary), `AWAITING_VERIFICATION`/`RESOLVED`/`CLOSED` banners,
  admin close button on `RESOLVED`.
- Dashboards (all real): reporter adds Awaiting Verification + Recently
  Resolved; solver shows Needs-revision/Completed badges from live latest
  solutions; mentor shows Pending-review badges; admin adds Awaiting Reporter
  Verification + Resolved Awaiting Closure.

## 14. Tests

`tests/test_verification.py` (14): readiness gate, submit success + double-
submit 409, all submit permission denials, admin override audit, approve flow
+ reporter notification, changes-request comment rule + revision 2 + team
notification, review permissions (other mentor, member, admin override rule),
confirm → `RESOLVED` + `resolved_at` + workloads held + notifications, reject
→ reason rule → `IN_PROGRESS` + assignment `ACTIVE` + workloads held +
workspace writable + `REPORTER_REJECTED`, verification permissions + double-
verify 409, close → workloads exactly once + retry 409 + `closed_at` +
`PROBLEM_CLOSED`, post-close read-only-but-readable, safe-view field audit,
verification history.
`tests/test_notifications.py` (6): assignment/task/blocked hooks, full
lifecycle type sweep, changes + rejection sweep, list/unread/read/read-all,
IDOR (read/mark/list isolation, outsider zero state).

## 15. Real E2E (`scripts/smoke_verification.py`, live HTTP, measured)

`SUBMITTED → IN_PROGRESS` work (2/2 DONE) → rev1 `SUBMITTED` (mentor unread
1→2) → changes requested (stays `IN_PROGRESS`) → rev2 → approved →
`AWAITING_VERIFICATION` → reporter NO → `IN_PROGRESS` → rev3 → approved →
reporter YES → `RESOLVED` (workloads held at 1/3, 1/3, 1/5) → admin close →
`CLOSED`, workloads 1→0 exactly once, retry close 409, `PROBLEM_CLOSED` to all
three parties, reporter unread 3→2 after marking one read. **SMOKE OK.**

## 16. Genuine limitations

- No reopen-from-`CLOSED`; no reporter-visible evidence toggle after submit;
  no email/push (abstraction only); no per-revision diff view; no deadline/
  SLA escalation; knowledge repository / semantic solution search / analytics
  remain future steps. Step 12 has NOT started.
