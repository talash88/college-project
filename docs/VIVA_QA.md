# Viva Q&A (60 questions; Short answer for memory, Detail for depth)

## Project
1. **Why this project?** S: Campus complaints get lost in chats/registers with
   no tracking. D: The platform gives every issue a ticket, an owner team, a
   mentor, a verifiable resolution, and a searchable memory.
2. **What problem does it solve?** S: Untracked, unprioritized campus issues.
   D: Reporting → AI triage → skilled teams → verified closure → knowledge.
3. **Why is AI required?** S: Manual triage is slow and inconsistent. D:
   Classification, priority reasons, skill matching, and duplicate search over
   free text need language understanding; humans still decide.
4. **Who are the users?** S: Reporters, solvers, mentors, admins. D: Role-based
   access with separate dashboards and workspaces.

## Architecture
5. **Architecture?** S: Next.js frontend, FastAPI backend, Postgres+pgvector.
   D: App Router UI → REST `/api/v1` → services → repositories → SQLAlchemy →
   Postgres; Docker for prod-style deploys.
6. **Data flow of one report?** S: Form → API → AI pipeline → DB → role views.
   D: Middleware (ID, rate limit, CORS, JWT, RBAC) → ProblemService runs
   classifier/priority/skills/embeddings/recommenders → rows + audit history.
7. **Why FastAPI?** S: Async, typed, auto docs. D: Pydantic validation,
   async SQLAlchemy for concurrent AI/DB work, OpenAPI for the API reference.
8. **Why Next.js?** S: React + routing + prod builds. D: App Router,
   standalone Docker output, client-side role guards backed by server RBAC.
9. **Why PostgreSQL?** S: Relational + vector in one DB. D: Enums, JSONB
   reasons, CASCADE deletes, pgvector extension — no second database.
10. **Layering?** S: api → services → repositories → models. D: Routes parse/
    guard; services hold rules+AI; repositories touch SQL; models define schema.

## Frontend / Backend / Database
11. **Auth flow in UI?** S: Login stores access token in memory, refresh in
    HttpOnly cookie. D: Axios attaches Bearer; 401 triggers single-flight
    refresh; failure dispatches session-expired → login.
12. **How does the backend know your role?** S: JWT claims + DB lookup. D:
    `get_current_user` decodes and loads the user; `require_roles`/
    `require_admin` guard routers.
13. **Key tables?** S: users, problems, AI analyses, teams, tasks, solutions,
    notifications, knowledge. D: 38 tables; see `DATABASE_SCHEMA.md` + ER.
14. **Migrations?** S: Alembic 001→012, single head. D: Fresh-DB proof done;
    prod entrypoint runs `upgrade head` before serving; no `create_all`.
15. **Tickets?** S: `CX-YYYY-NNNNNN` from `ticket_counters`. D:
    Server-generated, unique, yearly counter.

## Authentication / Security
16. **JWT auth?** S: Short access token + long rotating refresh. D: 30-min
    Bearer in memory; 7-day opaque refresh hashed in DB, HttpOnly cookie.
17. **Refresh rotation?** S: Each refresh issues a new token, old revoked. D:
    Reuse after logout → 401 (proven on prod stack).
18. **RBAC?** S: Four roles, server-enforced. D: Dependency guards per router;
    measured 401/403/404 matrix in Step 16.
19. **IDOR prevention?** S: Never 403-leak existence — 404. D: Ownership/team/
    mentor checks return 404 for invisible objects (unrelated mentor → 404).
20. **Upload safety?** S: Sniffed MIME, 10 MB/5-file caps, safe names. D: 415/
    413 rejections; `../../etc/passwd.png` stored as `passwd.png`; traversal
    impossible.
21. **Rate limiting?** S: In-memory sliding window per route class. D:
    Auth 20/min, uploads 30, AI 60, search 120, default 600; off in tests;
    single-instance only (documented).
22. **CORS/cookies in prod?** S: Explicit origins, credentials on. D: `*`
    forbidden in prod; `Secure`+`Lax` cookie ⇒ same-domain hosting recommended.
23. **CSV injection?** S: Leading `=+-@` cells get a `'` prefix. D: Proven
    with `=2+2…` probe in export.

## AI/ML general
24. **What is an embedding?** S: Text as a number vector capturing meaning. D:
    384-d MiniLM vectors; similar meanings → nearby vectors.
25. **Cosine similarity?** S: Angle between vectors, −1…1. D: Used for skills,
    duplicates, mentor specialization, knowledge search.
26. **What is pgvector?** S: Postgres extension for vector search. D: Stores
    384-d columns, cosine queries, extension enabled by migration 002.
27. **What if AI fails?** S: Honest `FAILED`, report still saves. D: Missing
    weights → prewarm warns; UI shows failure states; tests cover it.
28. **Human-in-the-loop?** S: AI advises, humans decide. D: Admin corrects
    categories, confirms duplicates, assigns; mentor approves; reporter verifies.

## DistilBERT
29. **Why DistilBERT?** S: Small, fast, CPU-friendly, fine-tunable. D: 66M
    params vs BERT-base; local inference, no API cost/latency/privacy issues.
30. **Why not ChatGPT API?** S: Cost, privacy, offline, determinism. D:
    External APIs leak student data, cost per call, and can't run in a
    college demo without internet; local model is auditable.
31. **Dataset?** S: 288 labelled complaints, 12×24. D: 201/43/44 stratified
    split, seed 42, `ml/data/problem_classification_v1.jsonl`.
32. **Accuracy?** S: 0.659 test accuracy — development data, not production
    claims. D: Macro F1 0.63, weighted 0.644; weak: SAFETY_SECURITY 0.0,
    INFRASTRUCTURE 0.25 — hence mandatory admin review.
33. **Why is Safety weak?** S: Tiny data + overlapping wording. D: 24 samples
    can't separate "sparks" (electrical) from "following at night" (safety)
    reliably; threshold sends all to humans.
34. **Confidence?** S: Softmax max; <0.60 needs review. D: Live probes scored
    0.2–0.5 and were flagged honestly.

## Sentence Transformers / MiniLM
35. **Sentence-BERT/MiniLM?** S: Sentence embeddings from transformers. D:
    `all-MiniLM-L6-v2`, 384 dimensions, cosine semantics for skills/
    duplicates/mentors/knowledge.
36. **Why no irrelevant skills forced?** S: Threshold + top-6 cap. D: Cosine
    <0.45 and no exact match → empty list, downstream shows INSUFFICIENT_DATA.

## Priority / Duplicates / Recommendations
37. **Priority score?** S: Weighted explainable 0–100. D: Severity 30 +
    affected 25 + age 20 + category 15 (capped) + duplicates 10; bands
    29/54/79; negation handled; reasons stored.
38. **Duplicate detection?** S: 0.85 semantic + 0.10 location + 0.05 category.
    D: Candidate ≥0.60, STRONG ≥0.82; paraphrase proven 0.897; admin confirms.
39. **Why admin approval for duplicates?** S: Merging is destructive. D: Wrong
    merges hide real incidents; human confirms, record preserved on reject.
40. **Canonical issue?** S: Oldest confirmed report. D: Members link to it,
    get DUPLICATE status, can't be assigned; canonical gains priority points.
41. **Team recommendation?** S: Best *combination*, not top individuals. D:
    Coverage 50 + proficiency 20 + availability/workload 10+10 + verified 5 +
    domain 5 over eligible solvers; 3 options; advisory + override reasons.
42. **Mentor recommendation?** S: Specialization semantics + skills. D:
    Specialization 35 + skills 30 + category 15 + availability/workload 10+10.
43. **Knowledge search?** S: Keyword + semantic hybrid. D: Closed problems →
    snapshots (no reporter identity) + embeddings; hybrid 0.75/0.25, min 0.35.

## Testing / Deployment / Limitations / Future
44. **Testing approach?** S: 266 pytest + browser + audits. D: Isolated test
    DB (recreated per run), RBAC/IDOR/AI/concurrency/storage suites, Browser
    Control journeys, pip/npm audits. No Selenium/Cypress.
45. **Dev DB untouched by tests?** S: Yes, proven by counts. D: 19/6/3/0/36
    before and after the suite.
46. **Deployment?** S: Docker prod stack verified locally. D: Two images
    (2.97 GB / 226 MB), health-gated compose, fresh-DB migration proof, prod
    E2E + persistence proof. No external deploy (no access given) — stated.
47. **Limitations?** S: Small dataset, weak classes, single-instance. D: 288
    samples, 2 weak classes, in-memory limiter, no ANN index (fine at scale
    tested), in-app notifications only, no SSO/MFA/S3/mobile.
48. **Future improvements?** S: Bigger dataset, calibration, SSO, S3, ANN. D:
    Institutional data collection, multilingual model, Redis limiter,
    pgvector HNSW at scale, observability, mobile app.
49. **Your module?** S: See `docs/TEAM_MODULES.md`. D: NLP/classification,
    priority/duplicates, skills/recommendations, resolution/tracking/knowledge.
50. **What would you do with 3 more months?** S: Data + hardening. D: Collect
    real labelled reports, calibrate confidence, add SSO + S3 + Redis limiter,
    HNSW index, load-test, observability.
51. **Why bcrypt directly (not passlib)?** S: passlib is dead and breaks on
    new bcrypt. D: Step-17 container proved 500s on fresh installs; direct
    bcrypt keeps `$2b$` compatibility (old hashes still verify).
52. **Migrations vs create_all?** S: Migrations only. D: Versioned, reviewable,
    prod entrypoint runs them; `create_all` can't evolve data.
53. **How are workloads safe?** S: Atomic + idempotent. D: One transaction,
    +1 once, held at RESOLVED, released once at CLOSE, retry 409.
54. **Empty states/UX?** S: Skeletons, empty art, safe errors. D: Offline →
    clean login redirect; 403/404 pages; zero console errors across roles.
55. **Rate-limit across replicas?** S: Not coordinated. D: Documented single-
    instance limit; Redis would be the fix.
56. **Vector scale decision?** S: 67 vectors → exact scan. D: ANN (HNSW) only
    justified with measured slowness at large scale.
57. **Why not auto-merge duplicates?** S: Safety (see 39). D: Members keep
    independent history until a human confirms.
58. **Analytics trust?** S: Verified against DB. D: Step-16 compared every
    count; CSV injection-safe.
59. **What breaks without internet?** S: Only first-time model download. D:
    HF cache persisted; everything else local.
60. **One-line summary?** S: "AI-assisted, human-decided campus issue
    resolution with a searchable memory." D: Report → AI triage → team →
    verified fix → knowledge.
