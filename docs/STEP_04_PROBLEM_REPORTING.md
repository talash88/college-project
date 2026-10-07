# Step 4 — Complete Campus Problem Reporting & Management System

**Status: Complete**

Step 4 adds the full report lifecycle foundation: problem model with
database-backed ticket numbers, controlled status lifecycle, reporter
ownership, attachments, activity audit trail, comments, admin intake views,
and working frontend routes. **No AI is implemented** — AI columns exist as
nullable placeholders and the UI states "AI analysis has not been run yet."

Steps 1–3 are untouched in behavior: migrations `001`–`003` were not
modified, and all 54 pre-existing tests still pass.

## 1. Database design (migration `004_problem_reporting`)

New tables (downgrade drops them in reverse order):

| Table | Purpose | Key constraints |
|---|---|---|
| `problems` | Report: ticket, title, description, reporter, location, affected count, status, nullable AI placeholders, submitted/resolved/closed timestamps | unique ticket, reporter/status/created indexes, title ≥ 5, description ≥ 20, affected ≥ 1 |
| `ticket_counters` | Per-year counter row (`year` PK, `last_number`) for safe ticket generation | PK on year |
| `problem_attachments` | File metadata (never raw bytes): original/stored names, MIME, size, uploader | unique stored name, problem index, size > 0 |
| `problem_activities` | Audit trail: event type, actor (nullable/system), old/new status, message | problem/created indexes |
| `problem_comments` | Discussion: author, content, `is_internal`, timestamps | problem index, content non-empty |

Native Postgres enums `problem_status` / `problem_event_type` match the
SQLAlchemy model types (a `VARCHAR` column would break `status ==` filters:
`operator does not exist: character varying = problem_status` — found and
fixed during testing). Verified chain: `001 → 002 → 003 → 004`.

## 2. Ticket-number strategy

Format `CX-YYYY-NNNNNN` (e.g. `CX-2026-000100`). Generated **server-side only**
(frontend input ignored/never accepted):

1. `SELECT … FOR UPDATE` the year's `ticket_counters` row (inserted on first use).
2. Increment, flush, format — all inside the same transaction as the problem insert.
3. Row locking serializes concurrent reporters (no `count()+1` race); a 10-way
   concurrent-create test asserts 10 unique tickets. Unique constraint is the
   final backstop.

## 3. Status model

`SUBMITTED → UNDER_REVIEW → APPROVED → ASSIGNED → IN_PROGRESS →
AWAITING_VERIFICATION → RESOLVED → CLOSED`, plus `REJECTED`, `DUPLICATE`,
`WITHDRAWN`. New reports start at `SUBMITTED`. Step 4 performs no other
transitions; the enum and activity schema already support future phases.
Terminal set (`RESOLVED, CLOSED, REJECTED, DUPLICATE, WITHDRAWN`) blocks
owner edits/withdrawals and admin overrides.

## 4. Ownership & withdrawal design

- Reporter is always the JWT user; spoofed `reporter_id` is ignored (proven by test).
- Detail/edit/delete of another user's report returns **404** (no existence oracle).
- Owner may edit/withdraw only while `SUBMITTED`; otherwise **409**.
- Admin may edit/withdraw any non-terminal report.
- **Withdrawal, not hard delete**: `DELETE /problems/{id}` sets `WITHDRAWN`,
  preserving full history (activity, comments, attachments metadata).

## 5. Problem APIs

| Method | Endpoint | Auth | Notes |
|---|---|---|---|
| POST | `/api/v1/problems` | any user | Validated, trimmed; 201 + ticket |
| GET | `/api/v1/problems/me` | owner | Pagination, `status`, `q` (ticket/title/description), `sort` |
| GET | `/api/v1/problems/me/stats` | owner | Real per-status counts for dashboard |
| GET | `/api/v1/problems/{id}` | owner/admin | Full detail; internal comments only for admin |
| PATCH | `/api/v1/problems/{id}` | owner(SUBMITTED)/admin | Editable fields only; `status`, ticket, AI, `reporter_id` → 422 |
| DELETE | `/api/v1/problems/{id}` | owner(SUBMITTED)/admin | Soft withdraw → `WITHDRAWN` |
| POST | `/api/v1/problems/{id}/attachments` | modifiable | Multipart JPEG/PNG/WEBP/PDF, 201 metadata |
| GET | `/api/v1/problems/{id}/attachments` | visible | Metadata only (no internal paths) |
| DELETE | `/api/v1/problems/{id}/attachments/{aid}` | modifiable | Removes file + record + logs event |
| GET/POST | `/api/v1/problems/{id}/comments` (+ `/activity`) | visible | Internal filtered for reporters |
| GET | `/api/v1/admin/problems`(+`/{id}`) | admin | Pagination, status, reporter, date range, affected range, search |

## 6. Attachments & file security

- Storage abstraction: `AttachmentStorage` protocol + `LocalAttachmentStorage`
  (`backend/storage/problem-attachments/`), swappable for S3/Cloudinary.
- Stored names are server UUIDs + validated extension; frontend names are
  sanitized for display only; resolved paths are confined to the storage root.
- Validation: allowlist MIME, **magic-byte sniffing** (declared type must match
  content), 10 MB cap (413), empty file (422), ≤ 5 files per report (409),
  executables/spoofed types → 415. Responses never expose storage paths.
- DB failure after file write rolls back and deletes the file.

## 7. Activity & comments

Every mutation logs an event (`SUBMITTED, EDITED, STATUS_CHANGED,
ATTACHMENT_ADDED, ATTACHMENT_REMOVED, COMMENT_ADDED`) with actor and
old/new status — no faked entries. Comments are plain persisted discussion:
reporters see/add public comments on own reports (internal flag forced off),
admins see/add internal ones. No chat/WebSockets.

## 8. Architecture

`ProblemRepository` (+ ticket/attachment/activity/comment repos) →
`ProblemService` / `AttachmentService` (raise `AuthError(status, detail)`) →
thin routers (`problems.py`, `admin.py`) mapping to HTTP. New errors reuse the
Step 3 `AuthError` convention.

## 9. Frontend

| Route | Description |
|---|---|
| `/problems/new` | Report form (title, description, location, building, area, affected count, uploads with progress). Success shows **ticket number** + View/My Reports links |
| `/problems` | My Reports: ticket/status/location/date, search, status filter, pagination, empty state |
| `/problems/[id]` | Detail, edit/withdraw (only when allowed), attachments, comments (+internal), activity timeline, "AI analysis has not been run yet" |
| `/admin/problems` | Admin table (ticket, title, reporter, status, date) + filters → detail |
| `/dashboard` | Real stats (Total/Submitted/In Progress/Resolved) + 5 recent reports, no fake numbers |

Sidebar enables Report Problem + My Reports for all roles, Administration for
admins; future modules stay disabled. `RequireAuth` protects routes
(unauthenticated → login; non-admin → `/403`).

## 10. Security decisions

- 404 (not 403) for cross-user access — verified by IDOR tests.
- No AI values anywhere: columns stay NULL, UI shows the not-run notice.
- Uploads: type sniffing, size caps, name sanitization, traversal-proof storage.

## 11. Tests (`tests/test_problems.py`, 20 tests)

Creation/auth/tickets (incl. 10-way concurrency), validation matrix,
protected-field rejection, IDOR (view/edit/delete/comment/attach),
admin view, edit rules, withdraw lifecycle, listing/pagination/filter/search,
stats, attachment happy path + 6 security cases + ownership/limits, comments
visibility, admin filters, Step 1–3 regression. Full suite: **74 passed**.

## 12. Manual verification (live servers)

Reporter: register → submit → ticket `CX-2026-000100` → My Reports →
detail → edit persists → PNG upload → comment → activity
`[SUBMITTED, EDITED, ATTACHMENT_ADDED, COMMENT_ADDED]` → withdraw →
edit-after-withdraw 409. Second reporter: direct URL → 404, attach → 404.
Admin: login → intake list shows report with reporter email → detail opens.
Frontend pages serve 200; content confirmed in built bundles (protected pages
render client-side after auth, so interactive clicking needs a real browser).

## 13. Explicitly NOT started (Step 5+)

DistilBERT/Sentence-BERT, auto category, priority scoring, skill extraction,
duplicate detection, team/mentor recommendation, AI approval, assignment,
tasks, notifications, verification, knowledge base, analytics.
