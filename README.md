# CampusXolve AI

**AI-Powered Campus Problem Solving**

A college-only campus problem reporting and resolution platform with AI-driven classification, team recommendation, and knowledge management.

## Overview

CampusXolve AI enables students and faculty to report campus issues, automatically classifies and prioritizes them using AI, recommends skilled student teams with faculty mentors, and tracks resolution progress through a structured workflow.

## Problem Statement

Campus complaints disappear into chats and registers: untracked, inconsistently
prioritized, assigned ad hoc, and forgotten — so the same problems recur.

## Solution

Every issue becomes a ticket: plain-language reporting → local-AI triage
(classification, priority with reasons, skills, duplicate search) → admin
review → skilled team + mentor assignment → workspace (tasks/milestones) →
mentor-reviewed solution → reporter verification → closure → searchable
knowledge. **AI assists; humans decide.**

## Key Features

- Ticketed reporting with attachments and status tracking
- DistilBERT classification with honest confidence + admin correction
- Explainable 0–100 priority scoring with reasons
- Hybrid skill extraction (no forced irrelevant skills)
- Semantic duplicate detection with admin-confirmed clustering (never auto-merge)
- Advisory team + mentor recommendations with override reasons
- Atomic assignment with workload safety; team workspace; solution revisions
- Reporter verification; in-app notifications; auto-published knowledge base
- Hybrid semantic search + related solved problems; analytics + CSV export
- Hardened auth (bcrypt, JWT rotation, RBAC/IDOR, rate limits, upload guards)

## Role Overview

| Role | Does |
|---|---|
| Reporter | Reports, comments, verifies fixes, browses knowledge |
| Solver | Team workspace: tasks, files, discussion, solutions |
| Mentor | Milestones, progress oversight, solution approve/changes |
| Admin | Intake, AI correction, duplicates, assignment, closure, analytics |

## AI/ML Features

Local-only (no external APIs): DistilBERT 12-class classifier (test acc 0.659,
weak classes honestly reported), all-MiniLM-L6-v2 embeddings (384-d, pgvector),
deterministic priority weights, heuristic recommenders — all behind
human-in-the-loop gates. Details: `docs/AI_ML_SYSTEM.md`.

## Architecture

Browser (Next.js 14) → FastAPI (`/api/v1`, 94 routes) → PostgreSQL 16 +
pgvector (38 tables, Alembic 001→012) → local AI artifacts. Docker
production-style stack available. Details: `docs/FINAL_ARCHITECTURE.md`.

## Project Workflow

Report → Classify → Prioritize → Skills → Duplicates → Recommend →
Admin review → Assign → Workspace → Solution → Mentor review → Reporter
verification → Close → Knowledge → Analytics. Full map:
`docs/COMPLETE_WORKFLOW.md`.

## Current Status: Step 17 Complete ✅

> Deployment readiness + reproducible production config + clean college demo
> environment. See `docs/STEP_17_DEPLOYMENT.md`. No external cloud deployment
> has been performed. Migration head: `012`. Backend: 266 tests green.

**Foundation Layer (Step 1):**
- Monorepo structure (backend + frontend)
- FastAPI backend with PostgreSQL + SQLAlchemy 2.0
- Next.js 14 frontend with TypeScript + Tailwind CSS
- Docker Compose for PostgreSQL
- Alembic migrations configured
- Health check endpoints
- Frontend-backend connectivity
- Professional UI shell with navigation

**Data Layer (Step 2):**
- User, StudentProfile, FacultyProfile, Skill, UserSkill models
- PostgreSQL enums for roles, departments, availability, skills, proficiency
- 46 seeded skills across 6 categories
- 7 development users with profiles and skill assignments
- Repository/Service layer with clean architecture
- Development REST APIs (read-only)
- pgvector extension enabled

**Authentication & Profiles (Step 3):**
- JWT access tokens + rotating opaque refresh tokens (HttpOnly cookie)
- Registration policy: public REPORTER/SOLVER only (ADMIN/MENTOR blocked)
- RBAC guards (`get_current_user`, `require_roles`, `require_admin`) on all APIs
- Self-service profile APIs (view/edit own profile, manage own skills)
- Frontend: /login, /register, /profile, /403, role-aware nav + dashboard
- 54 backend tests passing, Ruff/MyPy clean, frontend lint/typecheck/build green

**Problem Reporting (Step 4):**
- Problem reports with server-generated tickets (CX-YYYY-NNNNNN), SUBMITTED lifecycle
- Owner/admin RBAC with 404 IDOR protection, soft withdrawal (no hard deletes)
- Attachments (JPEG/PNG/WEBP/PDF, sniffed, capped) via swappable storage abstraction
- Activity audit trail + comments (internal admin notes hidden from reporters)
- Admin intake views with filters; frontend report form, My Reports, detail, admin table
- 74 backend tests passing, Ruff/MyPy clean, frontend lint/typecheck/build green

**AI Classification (Step 5):**
- Fine-tuned DistilBERT (distilbert-base-uncased) text classifier, local inference, no external APIs
- Honest 288-sample development dataset (12 categories x 24), validated + stratified (seed 42)
- Real held-out metrics: accuracy 0.659, macro F1 0.63, weighted F1 0.644 (weak classes reported)
- Softmax confidence with 0.60 review threshold; FAILED/LOW_CONFIDENCE never faked
- Classification audit history + admin accept/override review preserving originals
- Frontend AI section with confidence bands, admin review controls
- 83 backend tests passing, Ruff/MyPy clean, frontend lint/typecheck/build green

**Priority & Skills (Step 6):**
- Explainable weighted priority (severity 30 + affected 25 + age 20 + category 15 + duplicate 0/10), LOW/MEDIUM/HIGH/CRITICAL
- Risk lexicon with negation handling; monotonic affected/age mappings; terminal reports frozen
- Hybrid skill extraction: exact phrases + all-MiniLM-L6-v2 cosine over pgvector embeddings + category bonus
- 46 skills embedded (384-dim, idempotent); threshold 0.45, max 6, empty when nothing matches
- Audit history for both; admin recalculate/reanalyze; per-subsystem failure statuses
- 105 backend tests passing, Ruff/MyPy clean, frontend lint/typecheck/build green

**Duplicate Detection (Step 7):**
- 384-dim report embeddings (all-MiniLM-L6-v2, pgvector), idempotent via source-text hash, refreshed on edit
- Hybrid match score (0.85 semantic + 0.10 location + 0.05 category), candidate threshold 0.60, no auto-merge ever
- PENDING suggestions (owner sees own only) → admin confirm/reject → clusters (DC-NNNN), joins, merges, oldest-canonical policy
- Confirmed duplicates recount canonical priority (+2 each, history preserved); recalculation preserves the contribution
- Reporter duplicate section + canonical banner; admin review controls; /admin/duplicates list + cluster detail pages
- 122 backend tests passing (17 duplicate tests), Ruff/MyPy clean, frontend lint/typecheck/build green

**Team & Mentor Recommendations (Step 8):**
- Deterministic team combinations (sizes 2–4, top 3, no solo by default) over real Step 6 skills, proficiency, verification, availability, workload, department
- Explainable 0–100 team score (coverage 50 + proficiency 20 + availability 10 + workload 10 + verified 5 + domain 5), relevance-weighted, no double counting
- Mentor ranking via Sentence Transformer specialization similarity (35) + skill match (30) + category (15) + availability (10) + workload (10)
- Advisory only: no assignment, no workload changes; duplicate members served through canonical issue; truthful empty states
- Reporter-safe cards + admin diagnostics with recalculate; 156 backend tests passing (33 recommendation tests), Ruff/MyPy clean, frontend lint/typecheck/build green

**Admin Review & Assignment (Step 9):**
- Central transition validator: SUBMITTED → UNDER_REVIEW → APPROVED → ASSIGNED (or REJECTED with mandatory safe reason); idempotent review start; full activity audit
- Real persistent teams + assignments: accept AI recommendations or override with required reasons; recommendations never rewritten
- Transactional assign (row locks, live eligibility revalidation, +1 workloads, single commit, full rollback); idempotent retry; concurrent single-winner; reassign with exact workload math; cancel with exactly-once release
- Duplicate members rejected with canonical pointer; assigned solvers/mentors gain scoped access + real /assigned and /mentored worklists
- Admin review workspace (stepper, modals, team/mentor pickers, preview, AI-vs-final panel, history); reporter/solver dashboards
- 173 backend tests passing (17 assignment tests), Ruff/MyPy clean, frontend lint/typecheck/build green

**Team Workspace & Progress (Step 10):**
- Real collaborative workspace on ASSIGNED problems: tasks (assignees, priorities, due dates, blockers), milestones, progress updates, work/evidence files, internal discussion, activity timeline
- Central task/milestone transition validators; BLOCKED requires a blocker reason (never silently lost); DONE reopening is mentor/admin-only
- Real progress formula (tasks 70% + milestones 30%, cancelled excluded, single-kind 100% weighting, 0–100 clamped) synced to a cached `progress_percent`
- ASSIGNED → IN_PROGRESS exactly once (first task/milestone start or first update), guarded by a single WORK_STARTED event
- Strict insider permissions (active team member, assigned mentor, admin); reporter gets a safe public-progress view only; removed members lose access immediately with unfinished tasks unassigned (history preserved)
- Workspace UI (/problems/[id]/workspace) with Overview/Tasks/Milestones/Progress/Files/Discussion/Activity; reporter progress card; enriched solver/mentor/admin dashboards
- 192 backend tests passing (19 workspace tests), Ruff/MyPy clean, frontend lint/typecheck/build green

**Solution Submission & Verified Closure (Step 11):**
- Append-only solution revisions (team-only submit in IN_PROGRESS) with documented readiness gate (no BLOCKED, HIGH/CRITICAL done, milestones complete, progress ≥80%; admin override audited)
- Mentor review (approve → AWAITING_VERIFICATION + reporter notified; changes-request → stays IN_PROGRESS + team notified; comment required; history never overwritten; admin override flagged)
- Reporter verification (YES → RESOLVED + resolved_at, workloads held; NO with mandatory reason → IN_PROGRESS, assignment stays ACTIVE, workspace writable)
- Admin close (RESOLVED → CLOSED only) releasing team/mentor workloads exactly once (ACTIVE→COMPLETED lock-guarded; retry 409s); no reopen-from-CLOSED
- Real in-app notifications (central service, controlled types, atomic with Step 11 decisions, best-effort post-commit hooks for assignment/tasks, own-only APIs with IDOR tests); email/push explicitly future-only
- Frontend: header bell + /notifications, workspace Solution tab, reporter verification card, resolved/closed banners, enriched role dashboards
- 266 backend tests passing (18 new Step 15 security), Ruff/MyPy clean, frontend lint/typecheck/build green

## Quick Start

### Prerequisites
- Docker (or Colima on macOS)
- Python 3.11+
- Node.js 18+

### 1. Start PostgreSQL
```bash
# Using Docker
docker run -d --name campusxolve-postgres \
  -e POSTGRES_USER=campusxolve \
  -e POSTGRES_PASSWORD=campusxolve \
  -e POSTGRES_DB=campusxolve \
  -p 5432:5432 \
  pgvector/pgvector:pg16
```

### 2. Backend Setup
```bash
cd backend
cp .env.example .env
pip install -e ".[dev]"
python -m alembic upgrade head
# Seed data (idempotent)
python scripts/seed_skills.py
python scripts/seed_users.py
# Run server
python -m uvicorn app.main:app --reload
```
- API: http://localhost:8000
- Docs: http://localhost:8000/docs
- Health: http://localhost:8000/api/v1/health

### 3. Frontend Setup
```bash
cd frontend
cp .env.example .env.local
npm install
npm run dev
```
- App: http://localhost:3000

## Production-Style Docker Quick Start

Production-parity local stack (pgvector Postgres + non-reload backend + compiled
frontend). The dev workflow above is unchanged; this is additive.

```bash
# From the repository root. The backend image needs no secrets baked in;
# JWT_SECRET_KEY is required at runtime (backend refuses weak/defaults).
JWT_SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')" \
  docker compose -f docker-compose.prod.yml up --build
```
- App: http://localhost:3000 · API: http://localhost:8000
- First boot runs `alembic upgrade head` automatically, then starts uvicorn.
- Uploads persist in the `campusxolve-prod-uploads` volume; Hugging Face model
  cache persists in `campusxolve-prod-hfcache` (first boot needs internet once
  for the sentence-transformer download).
- The gitignored 256 MB DistilBERT weights are mounted read-only from
  `backend/ml/artifacts` (see `docs/STEP_17_DEPLOYMENT.md` for cloud options).
  Without them the app still boots; AI marks classification `FAILED` honestly.
- Reference data for a fresh production DB (explicit commands, never auto-run):
  `python scripts/seed_skills.py` then `python scripts/build_skill_embeddings.py`
  with `DATABASE_URL` pointed at the database. No dev users/demo data auto-seed.
- Recommended real cloud: frontend + backend under the same parent domain with
  managed Postgres+pgvector (refresh cookie is `SameSite=Lax`). Details,
  backups, and alternatives: `docs/STEP_17_DEPLOYMENT.md`.

## College Demo Environment

A disposable, clearly fictional dataset (10 users, 8 problems across CLOSED,
IN_PROGRESS, UNDER_REVIEW, ASSIGNED, DUPLICATE, SUBMITTED,
AWAITING_VERIFICATION + 2 Knowledge articles). Uses a separate database so the
dev DB is never polluted:

```bash
createdb campusxolve_demo
DATABASE_URL="postgresql+asyncpg://campusxolve:campusxolve@localhost:5432/campusxolve_demo" \
  python -m alembic upgrade head
DATABASE_URL="postgresql+asyncpg://campusxolve:campusxolve@localhost:5432/campusxolve_demo" \
  python scripts/seed_skills.py
DATABASE_URL="postgresql+asyncpg://campusxolve:campusxolve@localhost:5432/campusxolve_demo" \
  python scripts/build_skill_embeddings.py
python scripts/seed_demo.py   # refuses dev/test DBs without --allow-dev
# Reset (dry-run default): python scripts/reset_demo.py [--apply]
```
Demo logins (`demo_college_123`): `demo.admin`, `demo.ananya`, `demo.kabir`,
`demo.rohan`, `demo.sneha`, `demo.aditya`, `demo.ishita`, `demo.vikram`,
`demo.meera`, `demo.arjun` (all `@campusxolve.local`). Demo only — never
production credentials.

## Project Structure

```
campusxolve-ai/
├── backend/                 # FastAPI application
│   ├── app/
│   │   ├── api/v1/         # API routes (health, auth, profile, users, skills)
│   │   ├── core/           # Configuration & enums
│   │   ├── db/             # Database layer
│   │   ├── models/         # SQLAlchemy models (User, Profiles, Skill, UserSkill, RefreshToken)
│   │   ├── schemas/        # Pydantic schemas (auth, profile, users, skills)
│   │   ├── services/       # Business logic (AuthService, ProfileService, UserService, SkillService)
│   │   ├── repositories/   # Data access layer
│   │   ├── security/       # bcrypt, JWT/refresh tokens
│   │   ├── ml/             # classifier inference + embeddings
│   │   └── utils/          # Utilities
│   ├── scripts/            # seeds, smoke checks, demo seed/reset, prod entrypoint
│   ├── tests/              # 266 pytest tests (isolated test DB)
│   ├── alembic/            # migrations 001 → 012 (single head)
│   ├── pyproject.toml
│   └── alembic.ini
├── frontend/                # Next.js application
│   ├── src/
│   │   ├── app/            # App Router pages (login, register, dashboard, profile, 403)
│   │   ├── components/     # React components (Sidebar, Header, AppLayout, RequireAuth)
│   │   ├── context/        # AuthProvider + useAuth
│   │   ├── hooks/          # Custom hooks (useBackendHealth)
│   │   ├── lib/            # API client, auth service, role-aware navigation
│   │   └── types/          # TypeScript types
│   ├── package.json
│   ├── tsconfig.json
│   ├── tailwind.config.ts
│   └── next.config.js
├── docs/                    # Documentation
├── docker-compose.yml
├── .env.example
├── .gitignore
└── README.md
```

## Technology Stack

| Layer | Technologies |
|-------|--------------|
| **Backend** | FastAPI, Pydantic, SQLAlchemy 2.0, Alembic, PostgreSQL, asyncpg, pytest, bcrypt |
| **Frontend** | Next.js 14, React 18, TypeScript, Tailwind CSS, Axios |
| **Database** | PostgreSQL 16 + pgvector |
| **DevOps** | Docker Compose, Git, ESLint, Ruff, MyPy |

## API Endpoints

94 routes — full reference: [`docs/API_REFERENCE.md`](docs/API_REFERENCE.md).
Core examples below (base `/api/v1`).

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/` | API information |
| GET | `/api/v1/health` | Health check with DB & pgvector status |
| POST | `/api/v1/auth/register` | Register (Reporter/Solver only) |
| POST | `/api/v1/auth/login` | Login with email + password |
| POST | `/api/v1/auth/refresh` | Rotate refresh token |
| POST | `/api/v1/auth/logout` | Revoke refresh session |
| GET | `/api/v1/auth/me` | Current authenticated user |
| GET | `/api/v1/profile/me` | Own profile (authenticated) |
| PATCH | `/api/v1/profile/me` | Update own profile (authenticated) |
| GET/POST | `/api/v1/profile/me/skills` | Own skills / add skill (authenticated) |
| PATCH/DELETE | `/api/v1/profile/me/skills/{skill_id}` | Edit/remove own skill (authenticated) |
| GET | `/api/v1/users` | List users (admin only) |
| GET | `/api/v1/users/{user_id}` | Get user by ID (self or admin) |
| GET | `/api/v1/users/{user_id}/student-profile` | Get student profile (self or admin) |
| GET | `/api/v1/users/{user_id}/faculty-profile` | Get faculty profile (self or admin) |
| GET | `/api/v1/users/{user_id}/skills` | Get user's skills (self or admin) |
| GET | `/api/v1/skills` | List skills (authenticated) |
| GET | `/api/v1/skills/{skill_id}` | Get skill by ID (authenticated) |

## Development Commands

### Backend
```bash
cd backend
python -m ruff check .      # Lint
python -m ruff format .     # Format
python -m mypy app/         # Type check (strict)
python -m pytest tests/ -v  # Tests (isolated campusxolve_test DB, never touches dev)
python -m alembic upgrade head  # Migrations
python scripts/seed_skills.py   # Seed skills
python scripts/seed_users.py    # Seed users
python scripts/cleanup_test_pollution.py          # Dry-run: list test pollution
python scripts/cleanup_test_pollution.py --apply  # Delete test pollution
```

> Backend tests run against a separate `campusxolve_test` database that is
> recreated, migrated, and seeded on every run. Override with `TEST_DATABASE_URL`.
> The suite fails fast rather than touching the `campusxolve` dev database.

### Frontend
```bash
cd frontend   # npm commands must run from frontend/, there is no root package.json
npm run lint        # ESLint
npm run type-check  # TypeScript
npm run build       # Production build
```

## Environment Configuration

### Backend (`.env`)
```env
DATABASE_URL=postgresql+asyncpg://campusxolve:campusxolve@localhost:5432/campusxolve
FRONTEND_URL=http://localhost:3000
JWT_SECRET_KEY=your-secret-key-min-32-chars
```

### Frontend (`.env.local`)
```env
NEXT_PUBLIC_API_URL=http://localhost:8000
```

## Documentation

Build log (per step):

- [Step 1: Foundation & Architecture](docs/STEP_01_FOUNDATION.md)
- [Step 2: Database Models & Skills](docs/STEP_02_DATA_MODEL.md)
- [Step 3: Authentication & Profiles](docs/STEP_03_AUTHENTICATION.md)
- [Step 4: Problem Reporting & Management](docs/STEP_04_PROBLEM_REPORTING.md)
- [Step 5: AI Problem Classification](docs/STEP_05_AI_CLASSIFICATION.md)
- [Step 6: Priority & Skill Extraction](docs/STEP_06_PRIORITY_SKILL_EXTRACTION.md)
- [Step 7: Duplicate Detection & Clusters](docs/STEP_07_DUPLICATE_DETECTION.md)
- [Step 8: Team & Mentor Recommendations](docs/STEP_08_RECOMMENDATIONS.md)
- [Step 9: Admin Review & Assignment](docs/STEP_09_ASSIGNMENT.md)
- [Step 10: Team Workspace & Progress Tracking](docs/STEP_10_PROGRESS_TRACKING.md)
- [Step 11: Solution Verification & Notifications](docs/STEP_11_VERIFICATION_NOTIFICATIONS.md)
- [Step 12: Knowledge Repository & Semantic Search](docs/STEP_12_KNOWLEDGE_REPOSITORY.md)
- [Step 13: Real Analytics & Admin Intelligence Dashboard](docs/STEP_13_ANALYTICS.md)
- [Step 14: Production-Quality UI/UX Polish & Role Experience](docs/STEP_14_UI_UX.md)
- [Step 15: Security & Reliability Hardening](docs/STEP_15_SECURITY_RELIABILITY.md)
- [Step 16: Final E2E Audit](docs/STEP_16_FINAL_E2E_AUDIT.md)
- [Step 17: Deployment Readiness](docs/STEP_17_DEPLOYMENT.md)

Final submission package:

- [Requirement traceability](docs/FINAL_REQUIREMENT_TRACEABILITY.md) · [Project status](docs/FINAL_PROJECT_STATUS.md) · [Architecture](docs/FINAL_ARCHITECTURE.md) · [Workflow](docs/COMPLETE_WORKFLOW.md)
- [Database schema](docs/DATABASE_SCHEMA.md) · [API reference](docs/API_REFERENCE.md) · [AI/ML system](docs/AI_ML_SYSTEM.md)
- [Installation](docs/INSTALLATION.md) · [User guide](docs/USER_GUIDE.md) · [Demo accounts](docs/DEMO_ACCOUNTS.md)
- [Demo script](docs/DEMO_SCRIPT.md) · [Demo fallback](docs/DEMO_FALLBACK_PLAN.md) · [Demo checklist](docs/FINAL_DEMO_CHECKLIST.md)
- [Viva Q&A (60)](docs/VIVA_QA.md) · [Presentation content](docs/PRESENTATION_CONTENT.md) · [Abstract](docs/ABSTRACT.md) · [Problem statement & objectives](docs/PROBLEM_STATEMENT_AND_OBJECTIVES.md)
- [Testing & validation](docs/TESTING_AND_VALIDATION.md) · [Security overview](docs/SECURITY_OVERVIEW.md) · [Deployment summary](docs/DEPLOYMENT_SUMMARY.md)
- [Project structure](docs/PROJECT_STRUCTURE.md) · [Team modules](docs/TEAM_MODULES.md) · [Results & limitations](docs/RESULTS_AND_LIMITATIONS.md) · [Screenshot checklist](docs/SCREENSHOT_CHECKLIST.md) · [College report outline](docs/COLLEGE_REPORT_OUTLINE.md)

## Screens / Routes

`/login` · `/register` · `/dashboard` (role-aware) · `/problems/new` ·
`/problems` · `/problems/{id}` (+ `/workspace`) · `/assigned` · `/mentored` ·
`/admin/problems` · `/admin/duplicates` · `/admin/knowledge` · `/knowledge` ·
`/knowledge/{ref}` · `/analytics` · `/notifications` · `/profile` · `/403` · 404.

## Testing

266 pytest tests on an isolated per-run `campusxolve_test` DB (dev DB provably
untouched) + Browser Control journeys (4 roles × desktop/tablet/mobile) +
security/file/persistence audits. Details: `docs/TESTING_AND_VALIDATION.md`.

## Security

bcrypt, JWT + rotating refresh (HttpOnly `Secure`/`Lax` cookie), RBAC + IDOR
(404-masked), rate limits, security headers + request IDs, upload guards, CSV
injection guards, prod env fail-fast. Details: `docs/SECURITY_OVERVIEW.md`.

## Deployment

Prod-style Docker verified locally (images 2.97 GB / 226 MB, health-gated
compose, fresh-DB migration + E2E + persistence proof). No external hosting
performed. Details: `docs/DEPLOYMENT_SUMMARY.md`.

## Known Limitations

288-sample classifier dataset (SAFETY_SECURITY F1 0.0, INFRASTRUCTURE 0.25 —
admin review gates exist for this); single-instance rate limiter; in-app
notifications only; no SSO/MFA/S3/mobile; npm 17 known advisories. Full list:
`docs/RESULTS_AND_LIMITATIONS.md`.

## Future Scope

Real institutional dataset + calibration, SSO, email/push, S3 storage, Redis
limiter, pgvector ANN at scale, observability, mobile app.

## Roadmap

- [x] **Step 1**: Foundation & Architecture
- [x] **Step 2**: Database Models, Users, Profiles & Skills
- [x] **Step 3**: Authentication & Authorization
- [x] **Step 4**: Problem Submission & Management
- [x] **Step 5**: AI Classification (DistilBERT)
- [x] **Step 6**: Priority Scoring & Skill Extraction
- [x] **Step 7**: Duplicate Detection & Recommendations
- [x] **Step 8**: Student Team + Faculty Mentor Recommendations
- [x] **Step 9**: Admin Review, Approval & Assignment Workflow
- [x] **Step 10**: Team Workspace, Tasks, Milestones & Real Progress Tracking
- [x] **Step 11**: Solution Submission, Mentor Review, Notifications, Reporter Verification & Verified Closure
- [x] **Step 12**: Knowledge Repository, Semantic Search & Related Solved Problems
- [x] **Step 13**: Real Analytics & Admin Intelligence Dashboard
- [x] **Step 14**: Production-Quality UI/UX Polish & Role Experience
- [x] **Step 15**: Security & Reliability Hardening (rate limits, headers, bcrypt/JWT, CSV guards, audits)
- [x] **Step 16**: Final E2E Audit (browser journeys, full lifecycle, bug fixes)
- [x] **Step 17**: Deployment Readiness (Docker, prod compose, demo seed) + bcrypt fresh-install fix
- [x] **Step 18**: Final Submission Readiness (traceability, architecture, AI docs, guides, demo + viva package)

## License

MIT License - College Project# college-project
