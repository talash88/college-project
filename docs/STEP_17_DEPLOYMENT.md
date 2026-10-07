# STEP 17 — Deployment Readiness + Reproducible Production Config + Demo Environment

Date: 2026-10-07. No product features, workflows, thresholds, or UI changed for
deployment (two exceptions, both fixes, §9). Migration head stays `012`.
No external deployment was performed (no credentials/permission provided).

## 1. Architecture (supported)

```
Browser ──HTTPS──> Frontend (Next.js standalone, port 3000)
                        │  NEXT_PUBLIC_API_URL (same-origin or explicit backend URL)
                        ▼
                   Backend (FastAPI/uvicorn, port 8000, ENVIRONMENT=production)
                        ├── Postgres 16 + pgvector (migrations: alembic upgrade head)
                        ├── storage/problem-attachments (persistent volume locally;
                        │   S3-compatible object storage recommended for real cloud)
                        └── local ML artifacts (DistilBERT weights + HF cache volume)
```

Primary recommended cloud path: **frontend + backend under the same parent
domain** (same-site), one managed Postgres with pgvector, one backend instance.
Rationale: the refresh cookie is `SameSite=Lax` (HttpOnly, `Secure` in prod),
so split-site hosting (e.g. Vercel + Render on different sites) will NOT send
the refresh cookie and sessions break after the 30-min access token expires.
Same-site (subdomains of one domain, or Docker-hosted together) works with
zero code changes. Cross-site would require `SameSite=None; Secure` + HTTPS
everywhere — deliberately NOT enabled, to keep localhost working and avoid
weakening CSRF posture. Alternatives documented; only one primary path.

- Rate limiter is single-process memory: fine for single-instance college demo,
  not coordinated across replicas (no Redis added — out of scope).
- No `TrustedHost`/forwarded-header trust beyond uvicorn `--proxy-headers`
  with `--forwarded-allow-ips` default `127.0.0.1` (local proxy only).
- No OpenAI/LLM APIs anywhere; all AI is local.

## 2. Files added / changed

| Path | Change |
|---|---|
| `backend/Dockerfile` | NEW. python:3.11-slim, non-root `appuser`, CPU torch, `pip install .` (no dev), `sqlalchemy[asyncio]`, copies app/alembic/tracked ml/start script; entrypoint = `start_production.sh` |
| `backend/.dockerignore` | NEW. Excludes secrets, tests, caches, storage contents, gitignored `model.safetensors` |
| `backend/scripts/start_production.sh` | NEW. Derives pg probe from `DATABASE_URL`, waits (60×2s), `alembic upgrade head` once, `exec uvicorn` (no reload, 1 worker, proxy-headers, allow-ips default localhost) |
| `frontend/Dockerfile` | NEW. Multi-stage node:20-alpine (`deps → builder → runner`), `npm ci`, build with `NEXT_PUBLIC_API_URL` arg, standalone server as non-root |
| `frontend/.dockerignore` | NEW |
| `docker-compose.prod.yml` | NEW. postgres (pgvector, healthcheck, `pgdata`) + backend (healthcheck on `/api/v1/health`, named volumes for uploads + HF cache, read-only weights mount, `JWT_SECRET_KEY` required with no default) + frontend (build arg). Dev `docker-compose.yml` untouched |
| `backend/pyproject.toml` | FIX: added missing `python-multipart` dep; replaced dead `passlib[bcrypt]` with `bcrypt` (§9) |
| `backend/app/services/security.py` | FIX: direct bcrypt (`$2b$` compatible — legacy hashes verify); explicit 72-byte rejection |
| `backend/tests/test_models.py` | FIX: flaky `CS2021{rand1000}`/`FAC{rand1000}` identifiers → uuid-hex (unique-constraint flake) |
| `backend/.env.example` | Documented storage/AI/threshold/rate-limit vars (full env contract) |
| `backend/scripts/seed_demo.py` | NEW. Curated fictional demo seed (§7) |
| `backend/scripts/reset_demo.py` | NEW. Marker-scoped demo reset, dry-run default (§7) |
| `README.md` | Production + demo sections |
| `docs/STEP_17_DEPLOYMENT.md` | This file |

## 3. Environment contract

Backend (authoritative): `DATABASE_URL`, `FRONTEND_URL` (explicit http(s) URL in
prod), `CORS_ORIGINS` (JSON array; `*` forbidden in prod), `ENVIRONMENT`,
`JWT_SECRET_KEY` (≥32 chars, non-default — enforced), `JWT_ALGORITHM`,
`ACCESS_TOKEN_EXPIRE_MINUTES`, `REFRESH_TOKEN_EXPIRE_DAYS`, `STORAGE_DIR`,
`MAX_ATTACHMENT_SIZE_MB`, `MAX_ATTACHMENTS_PER_PROBLEM`, `CLASSIFICATION_MODEL_DIR`,
`CLASSIFICATION_CONFIDENCE_THRESHOLD`, `SKILL_EMBEDDING_MODEL`,
`PRIORITY_*`, `DUPLICATE_*`, `TEAM_*/MENTOR_*/KNOWLEDGE_*`, `RATE_LIMIT_*`,
`LOG_LEVEL`, `API_HOST/PORT`, `FORWARDED_ALLOW_IPS`. Frontend: only
`NEXT_PUBLIC_API_URL` (build-time). No backend secrets in `NEXT_PUBLIC_*`;
only `localhost:8000` occurrences are the env fallback default and one
user-facing "backend unreachable" hint.

Fail-fast verified live: short/default JWT secret, default placeholder, and
`*` CORS all refuse `Settings()` in production. Missing `DATABASE_URL` cannot
be detected (has a localhost default) — prod compose always sets it explicitly.

## 4. Database / migrations / pgvector

Deploy order: database available → `alembic upgrade head` (entrypoint) →
uvicorn. No `create_all()` anywhere in the deploy path. Fresh DB proof:
`campusxolve_fresh` migrated `001→012` from scratch, `vector` extension present
via migration `002`, 38 tables, head `012`.

## 5. Model artifacts (deployment strategy: local files + documented training)

- DistilBERT weights `ml/artifacts/problem_classifier/model.safetensors`
  (256 MB) are gitignored by design; tokenizer/config/metrics are tracked.
  Local prod: mounted read-only into the container (compose does this).
  Cloud/fresh: run `scripts/train_classifier.py` (documented) or ship the file
  as a release artifact / volume — never silently missing: without weights the
  app still boots and reports honestly mark classification `FAILED`.
- Sentence-transformers `all-MiniLM-L6-v2` (~90 MB + 418 MB local HF cache)
  downloads on first AI use; needs internet on first boot — persisted via the
  `backend-hfcache` volume (`HF_HOME`), never re-downloaded per restart.
- Skill embeddings: built by `scripts/build_skill_embeddings.py` (46 skills,
  384-dim, 8.8 s measured); production deploy runs `seed_skills.py` +
  `build_skill_embeddings.py` once against the prod DB (explicit commands, NOT
  auto-seed — the taxonomy is reference data; users/demo data never auto-seed).

## 6. Storage

Local disk adapter retained for local/demo; uploads live in
`storage/problem-attachments` → `backend-uploads` named volume in prod compose
(restart persistence PROVEN: file + DB row survived `docker restart`).
Orphan audit (`scripts/audit_storage.py`): 0 DB rows missing files; ~18
pre-existing orphan disk files from old smoke runs — left untouched (dry-run
only). Real cloud: S3-compatible object storage recommended; ephemeral
container filesystems must NOT be relied on (documented, not implemented —
abstraction is swappable).

## 7. Demo environment (`campusxolve_demo`, disposable)

Build: `createdb campusxolve_demo` → `alembic upgrade head` →
`seed_skills.py` → `build_skill_embeddings.py` → `seed_demo.py`
(spawns temp uvicorn on :8001, drives real APIs, shuts down).
Credentials (demo-only): `demo.admin / demo.ananya|kabir / demo.rohan|sneha|
aditya|ishita|vikram / demo.meera|arjun @campusxolve.local`, password
`demo_college_123`. Content: 10 fictional users + 8 problems
(CLOSED×2 → KB-000013/14, IN_PROGRESS, UNDER_REVIEW, ASSIGNED, DUPLICATE
confirmed cluster, SUBMITTED, AWAITING_VERIFICATION), AI outputs left honest
(3 problems show INSUFFICIENT_DATA + curated override — itself demoable).
Reset: `reset_demo.py` (dry-run default; deletes `demo.*` users + cascaded
graph + demo-linked cluster shells + ticket counters). Verified reset→seed
cycle is clean (tickets restart at 000001, single populated cluster).
W10 decision: 11 stale identically-named dev users are REFERENCED by existing
dev problems/teams — left untouched; the fresh demo DB contains none of them.

## 8. Verification performed (all real, local)

- Images built: `campusxolve-backend:prod` **2.97 GB** (torch CPU dominates),
  `campusxolve-frontend:prod` **226 MB**. No "should build" claims.
- Prod stack (`docker compose -f docker-compose.prod.yml up`): postgres
  healthy → migrations → backend healthy (`environment: production`,
  pgvector true) → frontend 200. Cold boot ~60–90 s (model prewarm); warm
  restart healthy in ~5 s.
- Prod E2E: register 201, ADMIN-register 403, ticket CX-2026-000001 with
  LIBRARY @0.285 honest low-conf, skills [], knowledge empty (fresh DB), me
  200. Prod UI in real browser: login → "Welcome, Prod Smoke" → My Reports,
  zero console errors, no dev overlays. Routes: /login 200, /403 200,
  /nonexistent 404, chunks + icon.svg 200.
- Sessions: login sets `cx_refresh` (HttpOnly, `Secure`, `SameSite=Lax`,
  Path=/api/v1/auth). Refresh over plain http correctly NOT sent (Secure —
  needs HTTPS in real prod, assumed); logout revokes (refresh→401).
- Persistence: upload + DB row survived backend restart. Backup:
  `pg_dump --schema-only` and table dump verified read-only against demo DB.
- 403/404/backend-offline remain user-safe (Step-16 evidence).

## 9. Bugs fixed in Step 17 (all found by container/fresh-env proof)

1. **HIGH — auth 500 on fresh installs**: `passlib[bcrypt]` (unmaintained)
   fatals against bcrypt ≥ 4.1/5.x ("password cannot be longer than 72
   bytes" even for short passwords). Fixed: direct `bcrypt` in
   `security.py` (same `$2b$` format; legacy dev/test hashes verified to
   still pass; >72-byte explicitly rejected). Full suite re-run: 266 pass.
2. **HIGH — `python-multipart` used but never declared** (uploads 500 in any
   clean env). Added to `pyproject.toml`.
3. **MEDIUM — image missing `greenlet`** (`sqlalchemy[asyncio]`): pinned in
   Dockerfile. (Transitively present in dev, absent in `pip install .`.)
4. **MEDIUM — flaky `test_relationships`**: 1000-value random
   `student_identifier` collided with committed rows (unique constraint).
   Widened to uuid-hex.
5. **LOW — empty duplicate-cluster shells**: deleting a canonical problem
   `SET NULL`s the cluster row, leaving hollows (analytics correctly ignores
   them). `reset_demo.py` removes demo-linked shells; product behavior
   unchanged (out of scope to migrate).

## 10. Limitations / non-goals

No external cloud deploy performed (stated truthfully). Multi-replica needs an
external migration job + Redis-backed limiter (documented, not built). S3
storage not implemented. `SameSite=None` cross-site mode not enabled (by
decision). Backend image is large (2.97 GB) — torch CPU; acceptable, not
further optimized. Step 18 (viva/report/demo-script package) NOT started.
