# Step 9 — Admin Review, Approval & Real Assignment Workflow

**Status: Complete. Real transactional workflow: review → approve → assign
(team + mentor + workloads in one atomic commit). AI stays advisory; the admin
decides; every override is auditable.**

An administrator reviews each report with all AI analyses, moves it through
`SUBMITTED → UNDER_REVIEW → APPROVED → ASSIGNED` (or `REJECTED` with a
mandatory safe reason), then assigns a real persistent team and mentor.
Assignment revalidates every person against live data, increments workloads
exactly once inside the same transaction, and rolls everything back on any
failure. Reporters see a safe summary; assigned solvers/mentors gain scoped
access; both get real worklists.

Steps 1–8 untouched in behavior: migrations `001`–`008` unmodified (chain
`001 → … → 009` verified), all prior engines and tests intact. Two
relationship declarations gained explicit `foreign_keys` (required once
`problems` grew `reviewed_by`/`approved_by` FKs to users).

## 1. Migration 009 state

- Revision `009`, down-revision `008`, head. `alembic upgrade head` clean.
- New tables: `problem_teams` (one active team per problem — partial unique
  index), `problem_team_members` (no duplicate active membership per team —
  partial unique index; history via `is_active`/`removed_at`), `problem_assignments`
  (one ACTIVE per problem — partial unique index; status check; indexes on
  problem/team/mentor).
- `problems`: `reviewed_by/at`, `approved_by/at`, `rejection_reason` (+FKs).
- New `problem_event_type` values: `REVIEW_STARTED`, `PROBLEM_APPROVED`,
  `PROBLEM_REJECTED`, `TEAM_CREATED`, `TEAM_ASSIGNED`, `MENTOR_ASSIGNED`,
  `ASSIGNMENT_CREATED`, `ASSIGNMENT_UPDATED`, `ASSIGNMENT_CANCELLED`.

## 2. Status workflow (central validator, no direct mutation)

| Action | From → To | Notes |
|---|---|---|
| Start Review | SUBMITTED → UNDER_REVIEW | idempotent repeat |
| Approve | UNDER_REVIEW → APPROVED | assigns nobody |
| Reject | SUBMITTED/UNDER_REVIEW/APPROVED → REJECTED | reason mandatory (≤1000), shown to reporter |
| Assign | APPROVED → ASSIGNED | only via assignment transaction |
| Cancel | ASSIGNED → APPROVED (or UNDER_REVIEW) | reason mandatory, workloads released once |
| Reassign | ASSIGNED → ASSIGNED | new ACTIVE row, old → REASSIGNED |

Anything else → 409 with allowed states. Audit fields + activity events on
every transition (actor + timestamps).

## 3. Team & assignment models

`ProblemTeam` (per-problem, named or generated label) + `ProblemTeamMember`
(solver-only enforced in service, `role_in_team` optional, soft removal) +
`ProblemAssignment` (team + mentor + `source_*_recommendation_id` provenance +
`team/mentor_was_overridden` + reasons + ACTIVE/COMPLETED/CANCELLED/REASSIGNED +
unassignment audit). Recommendations are never rewritten. Workload columns
keep their `current ≤ max` constraints; increments respect them.

## 4. Assignment transaction (all-or-nothing)

Lock problem (`FOR UPDATE`) → reject duplicate members (canonical message) →
idempotency check → APPROVED gate → size rules (2–4; solo only if configured +
explicit reason) → recommendation-reference checks (override ⇒ reason required)
→ live revalidation of every solver/mentor with locked profile rows → create
team + members + assignment → +1 workload each → status ASSIGNED → activity →
single commit. Any failure → full rollback (proven: 0 assignments, 0 teams,
status unchanged, workloads untouched).

Concurrency: row lock serializes admins; the partial-unique backstop converts
races into replay-or-conflict. Idempotent retry of the identical payload
returns the existing assignment (200 + flag) with zero extra increments.
Reassign swaps atomically (removed −1 floored at 0, added +1, stayers
untouched); cancel releases exactly once (double cancel → 409).

## 5. Eligibility revalidation (live, never stale)

Each solver at assignment time: SOLVER, active, profile, not UNAVAILABLE,
sane data, `current < max`. Each mentor: MENTOR, active, profile, not
UNAVAILABLE, sane data, `current < max`. Violations → 422 naming the person
and cause; nothing persisted.

## 6. RBAC & views

- Review/approve/reject/assign/reassign/cancel/eligible-solvers: ADMIN only
  (others 403; strangers 404; anonymous 401).
- Assigned active members + assigned mentor may view the problem (internal
  comments still hidden); access revoked on removal; recommendations alone
  grant nothing.
- `GET /problems/assigned/me`, `GET /problems/mentored/me`: strictly scoped.
- Reporter detail: assignment summary (names, roles, mentor
  name/designation/specialization) — no IDs, emails, identifiers, workloads,
  or override reasons. Admin detail: everything.

## 7. Real E2E smoke (live API, measured, unaltered)

Network report → IT_NETWORK, {Computer Networking .99, Linux .99} → AI team
67.97 {Alex Chen, Jordan Kim, Priya Sharma} + AI mentor Torres 69.05.
BEFORE: solvers 0/3, 0/3, 1/3; mentor 0/5. Start Review → Approve → Assign
(201, both `overridden=false`). AFTER: 1/3, 1/3, 2/3; mentor 1/5. Status
ASSIGNED; reporter sees names; `assigned/me` + `mentored/me` list the ticket.
Override report: AI team → different final team, AI mentor → other mentor,
reasons stored, recommendation rows byte-identical. Failure report: maxed
member → 422, assignments=0, teams=0, status stays APPROVED.

## 8. Frontend

Problem detail: status stepper (Submitted→Review→Approved→Assigned, terminal
badges), rejection banner, reporter assignment summary, and — for admins — a
full review workspace: state actions, reject modal (reason required, no
`alert()`), team option select + custom solver picker (search, chips, 2–4
guard, override reason), mentor ranked select, preview modal, confirm,
AI-vs-final panel with reasons, history, reassign/cancel modals.
New `/assigned` + `/mentored` worklists, role nav items, dashboard panels
(reporter workflow counts; solver/mentor counts; admin review queue with
status deep-links). `lint`, `type-check`, `build` green.

## 9. Tests & quality

- `pytest tests/`: **173 passed** (17 new workflow/assignment tests: transitions,
  idempotent review, rejection, RBAC, rec-accept, manual overrides + reason
  enforcement, member/mentor rejections, rollback zeros, duplicate-report
  rejection, idempotent replay, concurrent single-winner, reassign math,
  cancel release, access/IDOR, worklists, safe views).
- `ruff check .` clean, `mypy app/` clean (95 files), `alembic upgrade head`
  at `009`, frontend lint/typecheck/build green. Steps 1–8 suites all green.

## 10. Bugs found by testing (fixed)

1. SQLAlchemy ambiguous FKs after adding reviewer/approver/mentor FKs
   (`foreign_keys` declared on both sides).
2. Idempotent retry hit the APPROVED gate on ASSIGNED problems — replay check
   moved before the status gate (real ordering bug, not test-only).
3. `eligible-solvers` route shadowed by admin `/{problem_id}` — workflow
   router registered first.
4. Async lazy-loads (`MissingGreenlet`) in builders/tests — nested eager loads.
5. Test-harness issues: outsider-in-pool, re-login, seed workload hermetics
   (snapshot/restore fixture), post-cancel re-approve.

## 11. Limitations

- No task/milestone system, no notifications, no reporter closure (later steps).
- `COMPLETED` assignment status reserved for a future verification flow.
- Solo teams require `TEAM_ALLOW_SOLO=true` plus explicit reason (default off).
- Reassign replaces the whole team set (no single-member patch endpoint).
- Smoke/test runs leave seed workloads touched mid-run; fixtures and scripts
  reset them (repo baselines documented in scripts).

## 12. Not started (Step 10+)

Task/milestone tracking, notifications, reporter closure/verification, and any
Step 10 work have NOT started. No fake Assign buttons remain — the disabled
"next step" placeholders from Step 8 are now real flows.

## Reproduce

```bash
cd backend
python -m alembic upgrade head
python -m pytest tests/ -v
python -m ruff check . && python -m mypy app/
python scripts/smoke_assignment.py
cd ../frontend
npm run lint && npm run type-check && npm run build
```
