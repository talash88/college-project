# Step 15 — Security + Reliability Hardening

Hardening only. No new product features, no AI changes, no migrations (head
stays **012**), no deployment. All findings below were verified against the
current code, not assumed.

## 1. Threat model (concise)

Actors: unauthenticated internet user · normal campus user · malicious
authenticated user (IDOR/probing) · solver or mentor reaching beyond their
assignment · stolen browser session · misconfigured deployment.

Assets: accounts/sessions, problem reports, private work files, solutions,
internal notes, student/faculty PII, admin actions. Out of scope: nation-state
attackers, physical host compromise, email-channel attacks (no email flow).

## 2. Authentication

Pre-existing and kept: bcrypt hashing, JWT claims
(sub/role/typ/iat/exp/jti, 30-min access), opaque refresh tokens stored as
SHA-256 only, rotation on every refresh, reuse rejected, revoked stays
revoked, inactive users rejected, generic login errors, HttpOnly cookies.
Verified by 34 auth tests + new regression tests.

Changed in Step 15: **python-jose → PyJWT** (`PyJWT>=2.8.0` in pyproject).
Reason: pip-audit flagged CVE-2026-85394 against python-jose 3.5.0 with no
available fix. Our usage (explicit `algorithms=[HS256]`, symmetric secret)
was not practically exploitable, but the library is unmaintained, so the
auth-critical path now uses the maintained implementation. All 34 auth tests
pass unchanged (behavior parity proven).

## 3. Cookie security

Refresh cookie `cx_refresh`: HttpOnly, `Secure` in production only
(localhost-compatible dev), `SameSite=Lax`, scoped to `/api/v1/auth`, expiry
matches refresh lifetime. No wildcard domains. Tested: flags asserted on the
login response; browser shows no JS-visible cookies and no tokens in storage.

## 4. CORS

Environment-aware: development keeps localhost origins with broad
methods/headers (documented convenience); production restricts methods to
`GET/POST/PATCH/PUT/DELETE/OPTIONS` and headers to
`Authorization/Content-Type/Accept/X-Request-ID`, and **refuses to boot**
with `*` origins or a non-http(s) `FRONTEND_URL` (fail fast, tested).

## 5. CSRF decision

Refresh/logout ride the `SameSite=Lax` cookie. Threat: cross-site POST from
an attacker's page does NOT carry Lax cookies (only top-level GET
navigations do), so forged state-changing requests arrive unauthenticated.
SameSite=Lax is sufficient here; no custom CSRF middleware was added
(deliberately — a bolt-on token scheme would add more risk than it removes).
Documented; revisit if the cookie ever becomes `SameSite=None`.

## 6. Rate limiting

New `RateLimitMiddleware` (in-memory sliding window per client IP, no Redis):
auth 20/min, uploads 30/min, AI-heavy POSTs 60/min, semantic search 120/min,
default 600/min. Exceeded → `429 JSON + Retry-After`. X-Forwarded-For is
deliberately untrusted. Auto-disabled under `ENVIRONMENT=test` so the suite
stays deterministic; single-process scope documented (multi-replica prod
would need a shared store). Verified live (20×401 then 429s) and by
deterministic unit tests (buckets, isolation, window slide).

## 7. Security headers + request IDs

`SecurityHeadersMiddleware`: `X-Content-Type-Options: nosniff`,
`Referrer-Policy: same-origin`, minimal `Permissions-Policy`,
`X-Frame-Options: DENY`, plus per-request `X-Request-ID` (also on 429/500).
No full CSP: it would risk breaking Next.js inline scripts and Swagger UI;
documented instead of shipped broken. No `dangerouslySetInnerHTML` anywhere
in the frontend (React text rendering only).

## 8. RBAC audit (result)

Public by design: `/`, `/health`, `/auth/register|login|refresh|logout`,
docs assets. Everything else requires `get_current_user`; all
`/admin/*`, analytics, knowledge-admin, duplicate confirm, classification
review, assignment, closure paths require `require_admin`; reporters/
solvers/mentors additionally pass service-level ownership checks
(visibility, assignment membership, recipient scoping). No route relies on
frontend hiding alone. Sensitive-action tests (close, assign, confirm)
assert 403s across roles in the existing suite.

## 9. IDOR audit (result)

Pattern everywhere: scoped lookup + 404 (never 403) so existence is not
revealed — notifications, attachments, work files, solutions, knowledge
evidence, related-solutions (visibility check first). New regression tests:
cross-user attachment list/delete, cross-user notification read, forced
internal comment stays public + invisible to reporters.

## 10. Mass assignment (result)

All PATCH schemas use `extra="forbid"` allowlists. Users cannot set role,
`is_active`, `current_workload`, status, ticket, reporter, or AI fields.
Workloads: only `max_workload` is self-editable (documented, low impact).
New tests post `status/ticket_number/reporter_id/priority_*` and role/is_active
payloads and assert 422 + unchanged rows.

## 11. Uploads/downloads

Already hardened and re-verified: 10 MB streaming cap (413), MIME allowlist
(415), magic-byte sniff mismatch rejection, UUID server filenames,
traversal-safe storage root, per-report count caps, DB rollback deletes
orphan bytes. Downloads are authenticated, problem-scoped, traversal-checked;
knowledge evidence additionally requires the live shareable flag.
New `scripts/audit_storage.py` (dry-run default; `--cleanup-orphans` removes
only unreferenced disk files): found 23 orphan test PNGs, 0 broken links;
orphans removed, the 1 live evidence file kept.

## 12. XSS / SQL injection

XSS: no `dangerouslySetInnerHTML`; user content renders as text. SQL: all
queries are parameterized SQLAlchemy (including analytics aggregations,
ILIKE filters, pgvector distance, CSV filters); no string-interpolated SQL
found. Raw SQL is limited to DDL/enum introspection in migrations/scripts.

## 13. CSV injection

Analytics exports now prefix `'` on string cells starting with `= + - @`
(after whitespace) or containing tab/CR; numbers and ordinary text untouched.
Tested by parsing the exported CSV (naive comma-split would misread quoted
cells — the test uses the `csv` module).

## 14. Logging

No passwords, tokens, secrets, or Authorization headers in logs (audited).
Safe fields only (paths, statuses, tickets, request IDs). `DATABASE_ECHO`
defaults off; production must not enable SQL echo or dev reload (documented,
not enforced in code since deployment is a later step).

## 15. Error handling

New last-resort `Exception` handler: safe `{"detail": "Internal server
error"}` + request ID outside, full traceback in server logs only. Tested by
fault injection (simulated disaster string containing a fake path/secret —
response leaks nothing). `AuthError`/`HTTPException` paths untouched
(verified: no API code raises bare `AuthError` past converters).

## 16. Validation / pagination limits

Field max-lengths throughout schemas (title 200, description 10k, comments
2k, passwords 8–128, search strings capped); oversized bodies 422 (tested).
Cross-problem lists already capped (`le=100/50/20`); per-problem sub-lists
(tasks/comments/activity/…) are inherently single-problem scoped and small —
documented as acceptable, no cap churn. Page-size abuse (`limit=1000000`)
422s (tested for problems + knowledge).

## 17. Transactions / concurrency (reviewed, no rewrite)

Ticket counter: row-locked per-year counter with lost-race retry (safe).
Close/release: ACTIVE→COMPLETED transition under lock, exactly-once tested.
Knowledge publish: unique `problem_id`, idempotent retry (tested).
Assignment: single-ACTIVE invariant + workload tests. Duplicate clusters:
canonical-oldest, admin-confirmed only. No partial-state evidence found; no
flows rewritten.

## 18. AI failure isolation (proven)

Report creation wraps each AI subsystem independently; new test kills all six
(classifier, priority, skills, duplicates, team, mentor) simultaneously and
the report still creates with a valid ticket. Pre-existing coverage for
classifier/duplicates/knowledge-semantic fallback retained.

## 19. Model artifacts

DistilBERT loads via transformers `safetensors` (no pickle), JSON label map,
missing-artifact error disables AI without breaking reports. No changes;
overstating avoided.

## 20. Environment validation

Production fail-fast: unsafe/short JWT secret, wildcard CORS with
credentials, malformed FRONTEND_URL (all tested). Dev stays convenient.
Database URL intentionally not forced (localhost prod proxies exist).

## 21. Seed safety

Seeds run only via explicit scripts (`__main__` guards); app startup never
seeds (tested by inspecting lifespan). Documented development/demo-only.

## 22. Test DB isolation (re-verified)

Guard extracted to `tests/db_guard.py` (side-effect free, directly tested).
Full suite: dev counts identical before/after
(users 19, problems 6, knowledge 3, clusters 0).

## 23. Constraints / indexes

Workload non-negativity/validity, proficiency 1–5, unique user-skills,
single active semantics, one-knowledge-per-problem, score bounds — all
present in models. Status/reporter/date/assignment/notification/knowledge
indexes present. No vector ANN index (exact scan correct at this scale).
No corrective migration: head stays **012**.

## 24. Backup guide

PostgreSQL: `pg_dump -U campusxolve -d campusxolve -F c -f backup.dump`
(`pg_restore -C -d postgres`). Uploads: copy
`backend/storage/problem-attachments/`. Model artifacts: retain
`backend/ml/artifacts/` + `ml/data/` (retraining needs the dataset + script
`scripts/train_classifier.py`). Never restore over the live dev DB without a
fresh dump first.

## 25. Health

Unchanged safe shape (status/database/pgvector/environment). No extra
liveness/readiness endpoints (deployment step decides).

## 26. Frontend auth UX

Verified: expired/revoked session → silent refresh → login redirect, no
loops (auth endpoints excluded from retry), no stale protected data (RequireAuth
gates), session-expired event clears state. Errors show safe messages via
`getApiErrorMessage` (no Axios/SQL/path leaks). No tokens in storage
(browser-verified). Backend-down → clean login redirect (screenshot-verified).

## 27. Dependency audit

- npm: 17 advisories (2 moderate, 14 high, 1 critical) — all in
  build/devDependencies (Next.js/eslint/tailwind/postcss chains); fixes
  require breaking majors. Left untouched per policy; deployment step should
  revisit (notably Next.js cache-poisoning/image-DoS advisories, mitigated
  today by no remote images and local-only serving).
- Python (pip-audit, installed read-only for this audit): 10 findings in 5
  packages. Fixed safely: **python-jose 3.5.0 (CVE-2026-85394, no fix
  available) replaced by PyJWT 2.15.1** (auth suite green, behavior parity);
  ecdsa removed as orphaned; anyio→4.14.2, urllib3→2.8.0, werkzeug→3.1.9
  patch upgrades. Re-audit: **clean**. Our CVE exposure was nil in practice
  (explicit HS256 + symmetric secret), documented honestly.

## 28. Browser security smoke (real Chrome)

No tokens in storage · HttpOnly refresh invisible to JS · reporter → admin
route = 403 page · invalid upload rejected with safe 415 · logout → login,
no stale data · backend-down → clean login redirect. Screenshots captured.

## 29. Known limitations (not claimed otherwise)

Single-process rate limiter (no shared state) · no WAF/bot defense · no
MFA/SSO/password-reset (out of scope) · npm devDeps advisories pending
breaking upgrades · localhost dev uses Secure-off cookies by necessity ·
perfect security not claimed.
