# Step 3 — Complete Authentication + Profile System

**Status: Complete**

Step 3 adds real JWT authentication with rotating refresh sessions, role-based
access control, self-service profiles backed by PostgreSQL, and a visibly
functional frontend (login / register / profile / 403, role-aware navigation).

Steps 1–2 are untouched in behavior: migrations `001`/`002` were not modified,
and all Step 1/2 tests still pass.

## 1. Backend authentication

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| POST | `/api/v1/auth/register` | public | Register REPORTER/SOLVER, returns user + tokens, sets refresh cookie |
| POST | `/api/v1/auth/login` | public | Email + password login, returns tokens, sets refresh cookie |
| POST | `/api/v1/auth/refresh` | cookie or body | Rotate refresh token, returns new pair + new cookie |
| POST | `/api/v1/auth/logout` | cookie or body | Revoke refresh session, clear cookie (idempotent) |
| GET | `/api/v1/auth/me` | Bearer | Current user with embedded profiles |

### JWT / refresh design

- **Access token**: HS256 JWT, 30 min expiry (`ACCESS_TOKEN_EXPIRE_MINUTES`),
  claims `sub` (user id), `role`, `typ="access"`, `iat`, `exp`, `jti`.
- **Refresh token**: opaque 256-bit value (`secrets.token_urlsafe(48)`), 7-day
  expiry. Only its SHA-256 hash is stored in the new `refresh_tokens` table;
  raw values are never persisted and never logged.
- **Rotation**: every `/refresh` revokes the presented token and issues a new
  pair. Reuse of a revoked token is rejected with 401.
- **Transport**: refresh token travels in a `cx_refresh` HttpOnly cookie
  (`SameSite=Lax`, `Secure` in production, `Path=/api/v1/auth`). JSON body
  `{"refresh_token": ...}` is also accepted for non-browser clients and tests.
- **Secrets**: `JWT_SECRET_KEY` comes from the environment; the server logs a
  warning if the default key is used in production. Passwords are bcrypt-hashed
  (existing `hash_password`/`verify_password`); hashes are never returned.
- Safe errors: bad credentials always return generic `401 Invalid email or
  password`; disabled accounts return `403 Account is inactive`.

### Registration policy

- Public registration allows **REPORTER** and **SOLVER** only.
- `ADMIN` / `MENTOR` registration attempts → **403**; unknown roles → **422**.
- Duplicate email (case-insensitive) → **409**. Emails are normalized
  (strip + lowercase). Password minimum 8 characters.
- `CampusEmail` type validates address shape while allowing `.local`
  development domains (pydantic `EmailStr` rejects `.local`, which would lock
  out all seeded dev users).

## 2. Database

New migration **`003_authentication`** (revises `002`, does not touch
`001`/`002`):

- `refresh_tokens` table: `id`, `user_id` (FK → users, CASCADE),
  `token_hash` (unique), `expires_at`, `revoked_at`, `created_at`, plus
  indexes on `user_id` and `expires_at`.
- `User.refresh_tokens` relationship (`all, delete-orphan`).

## 3. RBAC

Guards in `app/api/v1/deps.py`:

- `get_current_user` — Bearer access token → user; missing/invalid/expired
  token or inactive account → **401**.
- `require_roles(...)` — wrong role → **403**. `require_admin` = ADMIN-only.

Step 2 APIs are now protected (previously open):

- `GET /users` → admin only (normal users cannot list all users).
- `GET /users/{id}`, `/student-profile`, `/faculty-profile`, `/skills` (user
  scoped) → self or admin.
- `GET /skills`, `GET /skills/{id}` (catalog) → any authenticated user.

## 4. Profile APIs (all require auth)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/profile/me` | Own user + role profiles |
| PATCH | `/api/v1/profile/me` | Edit name; create-or-update own role profile |
| GET | `/api/v1/profile/me/skills` | Own skills with embedded skill details |
| POST | `/api/v1/profile/me/skills` | Add skill (real `skills` row, proficiency 1–5, optional years) → 201; duplicate → 409 |
| PATCH | `/api/v1/profile/me/skills/{id}` | Edit proficiency/years; missing → 404 |
| DELETE | `/api/v1/profile/me/skills/{id}` | Remove; missing → 404 |

- Wrong-role payloads (e.g. faculty profile for a SOLVER) → 422.
- `current_workload` is not part of the self-service schemas (`extra="forbid"`,
  attempts fail with 422) — workload stays under future assignment control.

## 5. Frontend (visible changes)

New pages: **`/login`**, **`/register`**, **`/profile`**, **`/403`**.

- Login: email/password, show/hide password, loading + validation states,
  invalid-credentials error, real backend request, `?next=` redirect support.
- Register: full name, email, password + confirm, Reporter/Solver picker, real
  registration, duplicate-email handling.
- Profile: real data from PostgreSQL, real editing (name, identifiers,
  department, year/semester or designation/specialization, bio, availability),
  full skill management (list, proficiency, years, add/edit/remove). No mocks.
- Auth layer: `AuthProvider` + `useAuth()` (`src/context/AuthContext.tsx`),
  auth service + typed API client (`src/lib/`), access token in memory only,
  refresh via HttpOnly cookie, session restore on load, single-flight
  auto-refresh with exactly-one retry and no refresh loops, expiry event that
  signs the user out.
- Protected routes: `RequireAuth` redirects `/dashboard` and `/profile` to
  `/login` when unauthenticated, to `/403` on wrong role; logged-in users
  visiting `/login` go to `/dashboard`.
- Header shows real name + role, Profile link, Logout (no more static Guest).
- Sidebar is role-aware per spec; future modules remain visible-but-disabled
  ("Soon"). Profile is enabled for every role.
- Dashboard is a clean role-aware welcome (`Welcome, <name>` / `Role: <role>`
  + next-phase notice). System-health cards moved to a development-only section.

## 6. Backend/database offline root cause

The browser showed "Backend Offline / Database Disconnected" because **no
backend was running and PostgreSQL was stopped** (Colima was down; the
`campusxolve-postgres` container existed but was not started). No code hid the
error. Two real config/code issues were also found and fixed:

1. `CORS_ORIGINS` comma-separated value in `.env` crashed startup under
   pydantic-settings (`.env.example` now documents the JSON-array format).
2. Pydantic `EmailStr` rejected `.local` domains, blocking all seeded logins
   (replaced with the `CampusEmail` type for auth/user schemas).

Health now reports `healthy / connected / pgvector_available: true`.

### Startup commands

```bash
colima start   # macOS Docker runtime (skip on Linux)
docker start campusxolve-postgres   # or: docker compose up -d postgres

cd backend
cp .env.example .env   # first time only
python3 -m alembic upgrade head
python3 scripts/seed_skills.py
python3 scripts/seed_users.py
python3 -m uvicorn app.main:app --reload   # :8000

cd frontend
cp .env.example .env.local   # first time only
npm install
npm run dev                  # :3000
```

## 7. Verification

- Seeded logins verified for all roles: `admin@…` (ADMIN), `reporter@…`
  (REPORTER), `solver1@…` (SOLVER), `mentor1@…` (MENTOR).
- `python3 -m pytest tests/ -v`: **54 passed** (20 Step 1/2 + 34 Step 3).
- `python3 -m ruff check .`: clean. `python3 -m mypy app/`: clean (strict).
- `npm run lint`, `npm run type-check`, `npm run build`: all pass.
- Manual E2E via live server: register → login → profile edit → skill
  add/duplicate/edit/delete → refresh → logout, plus RBAC 401/403 matrix.
  Browser-driven clicking was not possible in this environment (no browser);
  pages were verified to render real content and the production build succeeds.

## 8. Explicitly NOT started (Step 4+)

Problem submission, AI classification (DistilBERT/Sentence-BERT), priority
scoring, skill extraction, duplicate detection, team/mentor recommendation,
admin approval, tasks/milestones, notifications, knowledge repository logic,
analytics — none of these were implemented.
