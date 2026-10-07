# STEP 16 — Complete End-to-End Product Audit + Bug Fixing + Demo Readiness

Date: 2026-10-07. Method: real browser (Browser Control relay, desktop 1440 / tablet 768 / mobile 390)
plus live-API lifecycle driving. No DB state was forced; no migrations; no retraining; no weight changes.

## 1. Baseline (pre-audit, all verified)

- Alembic head: `012`. PostgreSQL healthy, pgvector available.
- Backend: `266 passed`, 0 warnings · Ruff clean · MyPy clean (120 files).
- Frontend: ESLint clean · `tsc --noEmit` clean · `next build` clean (22 routes).
- Health: `{"status":"healthy","database":"connected","pgvector_available":true}`.
- Dev DB before: users 19 · problems 6 · knowledge_entries 3 · duplicate_clusters 0 ·
  problem_assignments 4 · problem_solution_submissions 3 · notifications 36.

## 2. Full E2E scenario (prefix `E2E FINAL AUDIT -`, driven UI + API, then cleaned)

| Stage | Evidence |
|---|---|
| Report via UI | Ticket **CX-2026-003581**; empty-submit validation shown ("Title must be at least 5 characters") |
| AI classification | IT_NETWORK, conf **0.3717** → honest "Needs Admin Review"; admin review accept → final IT_NETWORK (200) |
| Priority | MEDIUM **38/100** (severity 8: "outage" signal; affected 20: 65 people; age 0; category 8 capped) |
| Required skills | Computer Networking 0.99 (HYBRID), Hardware Troubleshooting 0.95, Problem Solving 0.95 |
| Duplicates (reporter view) | 2 real semantic candidates (73–74%) + related KB-000001 (57%); admin-only confirm |
| Team rec | Option 1 score 33.19: Alex Chen, Jordan Kim, Priya Sharma, W10 SOLVER |
| Mentor rec | Prof. Michael Torres 46.16 (Computer Networks / Systems — semantically relevant) |
| Assign | 201, `team_was_overridden=false`; workloads +1 each (solver1 0→1, solver2 0→1, solver3 1→2, W10 0→1, mentor2 0→1); status ASSIGNED |
| Workspace | tasks create/start/BLOCKED(reason kept)/unblock/DONE; mentor milestone + COMPLETED; work-file 201; progress **100%** (2/2 tasks, 1/1 milestones); reporter workspace **403**, safe public-progress visible |
| Solution lifecycle | rev1 SUBMITTED → CHANGES_REQUESTED (IN_PROGRESS) → rev2 → APPROVED (AWAITING_VERIFICATION) → reporter NOT_RESOLVED (IN_PROGRESS) → rev3 → APPROVED → reporter RESOLVED (resolved_at set) |
| Workloads | unchanged at RESOLVED; released exactly once at CLOSE (all →0 except solver3 →1 pre-existing); retry close **409**, no double release |
| Knowledge | auto-published on close; snapshot correct; no reporter email leak; duplicate member created no article |
| Notifications | delivered: TEAM_ASSIGNED, TASK_BLOCKED, SOLUTION_SUBMITTED, CHANGES_REQUESTED, REPORTER_VERIFICATION_REQUIRED, REPORTER_REJECTED_RESOLUTION, PROBLEM_RESOLVED, PROBLEM_CLOSED, MENTOR_ASSIGNED; unread counts + mark-read + mark-all-read verified; cross-user patch → 404 |
| Analytics | overview matched DB exactly (14 problems incl. probes; status counts identical; knowledge 4; clusters 1) |

Duplicate E2E: paraphrase report CX-2026-003582 → STRONG candidate (semantic **0.8968**, final **0.9123**)
against CX-2026-003581. Admin confirm → cluster **DC-0206** (canonical 3581). Member status DUPLICATE;
approve/assign on member → 409. Canonical priority carries `duplicate_component: 2.0`.
Note: discussion POST with wrong field (`body` instead of `content`) → 422 is correct schema validation,
not a bug; discussion on CLOSED problem → 409 is correct.

## 3. AI subsystem audits (no retraining)

- Classification probes (6 unseen texts): IT_NETWORK ✓ (0.20), ELECTRICAL ✓ (0.20),
  SAFETY_SECURITY ✓ (0.23), LIBRARY ✓ (0.43), TRANSPORT ✓ (0.53), Infrastructure/plaster → ACADEMIC ✗ (0.24).
  5/6 correct; ALL low-confidence → honest "needs admin review". Manual correction verified (200).
  Known limitation: weak classes (infrastructure) misclassify at low confidence — by design, admin corrects.
- Priority: components/reasons truthful; safety probe scored LOW 18 (severity caught only "broken";
  category capped at 12/15 by design). Conservative-by-design; weights unchanged per scope.
- Skills: network → Computer Networking 0.99; electrical → Electrical Maintenance 0.99;
  safety/library/transport probes → empty (allowed). No forced irrelevant software skills.
- Duplicates: true paraphrase 0.897 STRONG; distinct incumbents surface as POSSIBLE (0.67–0.74);
  admin confirmation mandatory; no auto-merge (member stayed independent until confirmed).
- Recommendations: unavailable/max-workload excluded (assign with maxed member → 422 + zero partial rows);
  mentor ranking semantically relevant; no workload change at recommendation stage.
  Display note: several stale `W10 SOLVER` dev users share one display name — options differ by user_id.

## 4. RBAC matrix (measured status codes)

| Action | Anon | Reporter | Solver | Mentor | Admin |
|---|---|---|---|---|---|
| Analytics dashboard | 401 | 403 | 403 | 403 | 200 |
| Analytics CSV export | — | 403 | — | — | 200 |
| Duplicate confirm | 401 | 403 | 403 | 403 | 200/409(replay) |
| Classification review | 401 | 403 | 403 | 403 | 200 |
| Assignment | 401 | 403 | 403 | 403 | 201/422-validation |
| Workspace modify (member) | 401 | 403/422-state | 201 | 201-member-only | — |
| Mentor review (own problem) | 401 | 403 | 404/409-state | 201 | 409-state |
| Reporter verification | 401 | 200/409-state | 403 | 404 | 403 |
| Close problem | 401 | 403 | 403 | 403 | 200/409(replay) |
| Problem read (own/team) | 401 | 200 | 200 | 200 | 200 |
| Unrelated mentor problem read/workspace | 401 | — | — | 404/404 | 200 |
| Reporter workspace access | — | 403 | — | — | — |

IDOR sweep: cross-user notification patch → 404; cross-user attachment list → 404;
unrelated-mentor access → 404 (existence hidden); anon → 401 everywhere. No IDOR found.

## 5. Auth / sessions / files / security

- Bad password → 401; invalid token → 401; `/auth/me` → 200. Logout → refresh 401 → clean redirect
  to `/login?next=…`; no infinite loops (single-flight refresh excludes auth endpoints).
- Browser reload restores session via HttpOnly refresh cookie (observed).
- Files: `.exe` mislabeled → 415; 11 MB PNG → 413; `../../etc/passwd.png` → sanitized to `passwd.png`, 201.
  Storage audit: 0 DB rows missing files; 13 pre-existing orphan disk files (prior smoke runs; left untouched).
- CSV: correct headers, no sensitive fields, reporter 403; `=2+2…` title exported as `'=2+2…` (injection-safe).

## 6. Browser / UX findings

- 25+ routes across 4 roles: zero console errors (only React DevTools/Fast-Refresh noise + expected
  post-logout refresh 401). RBAC redirects verified (reporter → /analytics ⇒ 403 page; anon ⇒ login).
- Tablet 768 / mobile 390: no horizontal overflow; headings render. Long 191-char title: no overflow.
- Backend-offline: dashboard → clean redirect to login (no crash). Observation (LOW, not fixed):
  login page shows no distinct "backend unreachable" banner.
- Double-fetch of every problem-detail API call in dev is React StrictMode (`reactStrictMode: true`) —
  dev-only, production unaffected. API medians 4–22 ms.

## 7. Bugs found and fixed

| # | Severity | Bug | Root cause | Fix |
|---|---|---|---|---|
| 1 | LOW | React duplicate-key warning (`W10 SOLVER`) in team recommendations | Safe views null `user_id`; `key={m.user_id ?? m.name}` collides on identical display names | Index-suffixed keys in `TeamRecommendationsSection.tsx:168` |
| 2 | LOW (latent) | Same collision pattern in assignment summary | `key={m.name ?? 'member'}` | Index-suffixed key in `AssignmentSummary.tsx:29` |

Both verified: warning gone on re-render; ESLint + tsc + prod build clean after fix.
No CRITICAL/HIGH/MEDIUM bugs found. No migration required.

## 8. Performance (measured, dev, 3 samples each)

health 6–10 ms · problem list 8–9 ms · problem detail 11–13 ms · analytics dashboard 4–5 ms ·
knowledge search 9–10 ms · related-solutions 21–22 ms.
Vectors: 17 problem + 4 knowledge + 46 skill embeddings — exact scan is correct;
no HNSW/IVFFlat (documented decision, revisit only with measured slowness at scale).

## 9. Cleanup (exact)

Deleted 11 `E2E FINAL AUDIT…` problems (3581, 3582, 3583–3591 minus gaps, incl. `=CMD`/`=2+2` probes),
cluster DC-0206 (cascaded members/candidates), auto-published KB article for 3581 (FK cascade),
2 attachment files from disk. Notifications referencing them cascaded via DB FK.
Dev DB after: users 19 · problems 6 · knowledge 3 · clusters 0 · assignments 4 · solutions 3 ·
notifications 36 — identical to pre-audit. Seed accounts, demo data, ML artifacts untouched.
13 pre-existing orphan disk files + duplicate-named W10 dev users left as-found (documented, out of scope).

## 10. Quality gates (post-fix, final)

pytest **266 passed** · Ruff clean · MyPy clean · Alembic `012` · ESLint clean · tsc clean ·
`next build` clean · pip-audit clean · npm audit 17 (2 mod/14 high/1 crit — identical to Step-15
documented set: Next.js/PostCSS/minimatch advisories, no new introductions).
Test-pollution check: dev counts identical before/after full suite.

## 11. Demo readiness

Dev DB is suitable for college demo as-is (seeded roles + 6 real problems + 3 KB articles + history).
No mass fake dataset created. Optional Step-17 work: curated demo seed script, prod build deploy,
refresh of stale W10 duplicate-named users. Step 17 has NOT started.
