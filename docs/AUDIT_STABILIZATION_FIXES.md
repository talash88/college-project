# Audit Stabilization Fixes (Steps 1–11 freeze)

Stabilization pass after the current-state audit. No new product features
(Knowledge Repository / Semantic Search / Analytics / Deployment are untouched).
Migration head is still **011** — no new migrations were required.

## 1. Findings: verified vs disproven

| # | Audit finding | Verdict |
|---|---|---|
| H1 | Dark-mode input text white-on-white | ✅ Verified (computed `rgb(248,250,252)` on white in dark OS mode). Fixed. |
| H2 | pytest pollutes shared dev DB | ✅ Verified (+127 users + empty clusters in one audit run). Fixed via isolated test DB. |
| H3 | Default JWT secret in `backend/.env` | ✅ Verified. Rotated + production guard added. |
| M4 | `admin_workflow_router` registered twice | ✅ Verified (`app/main.py:81,86`). Fixed, 80 paths before/after. |
| M5 | Team options 1/2/3 identical | ❌ **Disproven.** DB shows the 3 options differ in the 4th member (same 68.67 score); `search_teams` already dedupes by member set. Identical-looking UI was test data (all members named "W10 SOLVER"). No code change. |
| M6 | `DUPLICATE_STRONG_THRESHOLD` unused | ✅ Verified (only referenced in config). Now used as diagnostic label (Option A). |
| M7 | No vector ANN index | ✅ Verified, intentionally deferred (exact scan is fine at college scale). |
| M8 | Report success stays on `/problems/new` | ✅ Verified, acceptable as-is: the success panel already shows ticket + AI result + View Report + My Reports. No change. |
| L9 | favicon 404 | ✅ Verified. Fixed with `src/app/icon.svg`. |
| L10 | `confirm_deleted_rows` SAWarnings | ✅ Verified (13 warnings). Root-caused and fixed (no suppression). |
| L11 | Incomplete router re-exports | ✅ Verified. Completed in `app/api/v1/__init__.py`. |
| L12 | Test-data pollution / ugly names | ✅ Verified. Cleaned with safe script (below). |

## 2. Input contrast: root cause and fix

Root cause: `globals.css` flips `--foreground-rgb` to near-white under
`prefers-color-scheme: dark`, while `.input-field` set a light border but **no
text color and no background** — inputs inherited near-white text on white
cards. Fix is at the design-system level (one place, all controls inherit it):

- `.input-field` now forces `bg-white text-secondary-900`,
  `placeholder:text-secondary-400`, plus `color-scheme: light` so native
  widgets (number spinners, date pickers, select dropdowns) stay light.
- Base layer: `select option` dark-on-white; webkit-autofill keeps dark text
  instead of the pale-yellow wash.
- Verified in dark OS mode via computed styles on Login, Report Problem
  (title/description/location), admin status filter (select), problem comment
  box, and typed-text entry. Light mode is identical by construction.

## 3. Test database isolation

- New `campusxolve_test` database. `TEST_DATABASE_URL` env wins; otherwise the
  database name of `DATABASE_URL` is replaced with `campusxolve_test`.
- `tests/conftest.py` resolves the URL **before any app import**, points the
  whole pytest process at it, then per run: `DROP + CREATE` (hermetic),
  `alembic upgrade head`, and seeds reference data the suite was written
  against: skill taxonomy (46) + embeddings (46) + the 7 official dev accounts.
- Fail-fast guard: if the resolved test URL names the dev database
  (`campusxolve`), collection aborts with `RuntimeError` instead of polluting.
  Verified: forced `TEST_DATABASE_URL=.../campusxolve` fails at conftest.
- `ENVIRONMENT` now also accepts `test` (conftest sets it); production keeps
  its strict JWT rule (below).

## 4. Dev pollution cleanup

Script: `backend/scripts/cleanup_test_pollution.py` (dry-run by default,
`--apply` deletes). Classification before deleting:

- BEFORE: 883 users (875 `@example.com`), 57 duplicate clusters (all empty),
  3 problems, 1 assignment, 6 team recommendations.
- Preserved: 7 `@campusxolve.local` seeds, 1 genuine Gmail account, 11
  demo-referenced `@example.com` users (reporters/team/mentors of the kept
  WiFi problems), all 3 problems, the assignment, all recommendations.
- Deleted 864 unreferenced test users (ORM deletes so cascades fire) + 57
  orphan clusters (verified: 0 members, 0 canonicals).
- AFTER: 19 users, 0 clusters, problems/assignments/recommendations intact.
- Proof pytest no longer touches dev: full suite run with
  `users/problems/clusters/notifications/skills` counted before and after —
  identical (19 / 3 / 0 / 0 / 71).
- Note: `storage/problem-attachments/` holds one PNG with no DB row (orphan
  from an old test run). Left in place; harmless.

## 5. Router fix

Removed the second `include_router(admin_workflow_router)` in `app/main.py`.
OpenAPI paths: 80 before → 80 after. No route lost.

## 6. Strong-threshold decision (Option A: meaningful diagnostics)

`DUPLICATE_STRONG_THRESHOLD` (0.82) now labels every duplicate candidate:
`match_strength = STRONG if final_match_score >= threshold else POSSIBLE`,
returned on `DuplicateCandidateResponse` and shown in the UI as a
"Strong match"/"Possible match" badge with a tooltip. Admin confirmation of
every suggestion remains mandatory; scoring and confirmation logic unchanged.

## 7. JWT secret policy

- `backend/.env` (gitignored) rotated to a fresh 64-char secret. Existing
  sessions re-authenticate transparently via the refresh-cookie flow (verified:
  browser session survived the restart).
- `Settings` refuses to boot with `ENVIRONMENT=production` unless
  `JWT_SECRET_KEY` is non-default and ≥ 32 chars (tested: default/short
  rejected, strong accepted).
- `.env.example` documents the rule + generation command + `TEST_DATABASE_URL`.
- Seed passwords remain development-only.

## 8. SQLAlchemy warnings: root cause and fix

13 `SAWarning: DELETE ... expected to delete 1 row(s); 0 were matched` in
verification-test cleanup. Traced with SQL echo: the cleanup flush deleted
`problem_assignments` **before** `problem_solution_submissions`, so the DB-level
`ON DELETE CASCADE` on `submission.assignment_id` removed submissions (+ their
reviews) first; the ORM's own DELETEs then matched 0 rows. Genuine missing
ORM edge — fixed by adding the bidirectional
`ProblemAssignment.solution_submissions ↔ ProblemSolutionSubmission.assignment`
relationship (`cascade="all, delete-orphan"`), which orders the flush
reviews → submissions → assignment. No schema/migration change (ORM only);
app code never deletes assignment rows (reassign/cancel only retire status),
so runtime behavior is unchanged. Result: full suite runs with **zero
warnings** (no suppression added).

Related test hygiene: `test_models.py::test_relationships` committed a
throwaway skill (now cleaned up in `finally`); `test_skill_creation` likewise;
`test_user_seed_idempotency` now exercises the real `seed_users()` twice and
re-seeds in `finally` so later tests keep their reference accounts.

## 9. Recommendation-option dedupe

Disproven (see table): `search_teams` already dedupes by member set; the
observed cards differed in the 4th member. No change; behavior already matches
the required "1–3 unique options" rule.

## 10. Favicon

Added `frontend/src/app/icon.svg` (project-colors graduation-cap mark). Next.js
serves it as `/icon.svg` (verified 200); no more favicon 404.

## 11. Exact quality results (after fixes)

- `python3 -m pytest tests/ -q`: **212 passed, 0 failed, 0 warnings** (~170s,
  hermetic `campusxolve_test`, dev DB drift: none).
- `python3 -m ruff check .`: **All checks passed.**
- `python3 -m mypy app/`: **no issues in 111 files.**
- `python3 -m alembic current` / `heads`: **011 (head)**, single head.
- `npm run lint`: **clean.** `npm run type-check`: **clean.**
  `npm run build`: **16/16 pages, includes `/icon.svg`.**
- Health: `healthy`, DB `connected`, pgvector `true`, 80 API paths.
- Browser (real Chrome, dark OS mode): admin/reporter/solver/mentor logins,
  report form contrast, admin filter contrast, comment contrast, Strong-match
  badge, workspace, notifications, 403 RBAC, 390px no-overflow — all verified.

## 12. Regression: Steps 1–11

Login (4 roles) · report creation (live AI: classification/priority/skills) ·
admin review queue · AI sections · duplicate analysis + confirm/reject UI ·
recommendations · assignment summary + reassign/cancel controls · workspace
(8 tabs) · solution readiness gate · notifications APIs · health/pgvector —
all 200s (auth-correct 401/403/404s where expected). Full lifecycle below the
UI remains covered by the 212-test suite on the isolated DB.

## 13. Remaining technical debt (not started)

Knowledge Repository, semantic knowledge search, related solved problems,
Analytics, deployment packaging (no Dockerfiles yet) — explicitly out of
scope for this pass. Smaller notes: no vector ANN index (fine at this scale);
dev-only system-health panel (correctly gated); `.next` prod-build cache
collides with `next dev` (delete `.next` and restart dev after building).

## 14. Step 12 status

**Step 12 (Knowledge/Analytics) has NOT started.** No routes, models, or pages
for it were added; `/knowledge` and `/analytics` still 404 by design.
