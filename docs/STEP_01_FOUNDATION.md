# Step 1: Project Foundation & Architecture

This document records the implementation of the CampusXolve AI foundation layer.

## Architecture Overview

CampusXolve AI is a monorepo with two main applications:

```
campusxolve-ai/
├── backend/          # FastAPI application
├── frontend/         # Next.js application
├── docs/             # Documentation
├── docker-compose.yml
├── .env.example
├── .gitignore
└── README.md
```

## Technology Stack

### Backend
- **Python 3.11+**
- **FastAPI** - Modern, fast web framework
- **Pydantic v2** - Data validation and settings management
- **SQLAlchemy 2.0** - Async ORM with asyncpg driver
- **Alembic** - Database migration management
- **PostgreSQL 16** - Primary database
- **pgvector** - Vector extension (prepared for future use)
- **pytest** - Testing framework

### Frontend
- **Next.js 14** - React framework with App Router
- **TypeScript** - Strict type checking
- **Tailwind CSS** - Utility-first CSS framework
- **Axios** - HTTP client for API communication
- **ESLint** - Code linting

### Development
- **Docker Compose** - Service orchestration
- **Git** - Version control
- **Environment variables** - Configuration management

## Backend Structure

```
backend/
├── app/
│   ├── api/v1/           # API routes
│   │   └── health.py     # Health check endpoints
│   ├── core/
│   │   └── config.py     # Application settings (Pydantic Settings)
│   ├── db/
│   │   ├── session.py    # SQLAlchemy async engine & session
│   │   └── health.py     # Database health checks
│   ├── models/           # SQLAlchemy models (empty - for future)
│   ├── schemas/          # Pydantic schemas (empty - for future)
│   ├── services/         # Business logic (empty - for future)
│   ├── repositories/     # Data access (empty - for future)
│   ├── security/         # Auth utilities (empty - for future)
│   ├── ml/               # ML/AI modules (empty - for future)
│   └── utils/            # Utilities (empty - for future)
├── tests/
│   └── test_foundation.py
├── alembic/
│   ├── env.py            # Alembic environment
│   └── versions/
│       └── 001_initial.py
├── pyproject.toml
├── alembic.ini
├── .env.example
└── README.md
```

## Frontend Structure

```
frontend/
├── src/
│   ├── app/
│   │   ├── dashboard/    # Dashboard page
│   │   │   └── page.tsx
│   │   ├── globals.css   # Global styles with Tailwind
│   │   ├── layout.tsx    # Root layout
│   │   └── page.tsx      # Home page (redirects to dashboard)
│   ├── components/
│   │   └── ui/
│   │       ├── Sidebar.tsx
│   │       ├── Header.tsx
│   │       ├── AppLayout.tsx
│   │       └── index.ts
│   ├── hooks/
│   │   └── useBackendHealth.ts
│   ├── lib/
│   │   ├── api-config.ts
│   │   ├── api-client.ts
│   │   └── navigation.tsx
│   └── types/
│       └── api.ts
├── package.json
├── tsconfig.json
├── next.config.js
├── tailwind.config.ts
├── postcss.config.js
├── .eslintrc.js
├── .env.example
└── README.md
```

## Database Configuration

### PostgreSQL Connection
- **Async URL**: `postgresql+asyncpg://user:pass@host:port/db`
- **Sync URL** (for Alembic): `postgresql+psycopg2://user:pass@host:port/db`
- **Pool settings**: pool_size=5, max_overflow=10, pool_pre_ping=True

### Extensions
- **uuid-ossp** - UUID generation (enabled in initial migration)
- **vector** - pgvector for embeddings (prepared, will be enabled when pgvector image is used)

### Alembic Migrations
- **Configuration**: `backend/alembic.ini`
- **Environment**: `backend/alembic/env.py`
- **Initial migration**: Creates uuid-ossp extension
- **Command**: `alembic upgrade head`

```bash
# Run migrations
cd backend
python -m alembic upgrade head

# Create new migration
python -m alembic revision --autogenerate -m "description"
```

## Environment Variables

### Backend (.env)
```env
# Application
APP_NAME=CampusXolve AI
APP_DESCRIPTION=AI-Powered Campus Problem Solving
ENVIRONMENT=development
DEBUG=true

# API
API_PREFIX=/api/v1
API_HOST=0.0.0.0
API_PORT=8000

# Database
DATABASE_URL=postgresql+asyncpg://campusxolve:campusxolve@localhost:5432/campusxolve
DATABASE_ECHO=false

# Frontend URL (CORS)
FRONTEND_URL=http://localhost:3000

# CORS
CORS_ORIGINS=http://localhost:3000,http://localhost:3001

# JWT (prepared for future auth)
JWT_SECRET_KEY=your-super-secret-jwt-key-change-in-production-min-32-chars
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7

# Logging
LOG_LEVEL=INFO
```

### Frontend (.env.local)
```env
NEXT_PUBLIC_API_URL=http://localhost:8000
```

### Docker Compose (.env)
```env
POSTGRES_USER=campusxolve
POSTGRES_PASSWORD=campusxolve
POSTGRES_DB=campusxolve
```

## API Endpoints

### Root
```
GET /api/v1/
Response: {
  "name": "CampusXolve AI",
  "description": "AI-Powered Campus Problem Solving",
  "version": "0.1.0",
  "docs_url": "/docs"
}
```

### Health Check
```
GET /api/v1/health
Response: {
  "status": "healthy",
  "service": "CampusXolve AI API",
  "database": "connected",
  "pgvector_available": false,
  "environment": "development"
}
```
Returns 503 if database is unavailable.

## Frontend-Backend Communication

### API Client (`frontend/src/lib/api-client.ts`)
- Centralized Axios instance
- Base URL from `NEXT_PUBLIC_API_URL`
- Request/response interceptors
- Error handling for network failures

### Backend Health Hook (`frontend/src/hooks/useBackendHealth.ts`)
- Polls `/api/v1/health` on mount
- Returns connection status, loading state, error
- Provides `refetch` function for manual refresh

### Status Display
- Header shows backend connectivity indicator
- Green = connected, Yellow = loading, Red = disconnected
- Refresh button to retry connection

## UI Design System

### Color Palette
- **Primary**: Blue-gray scale (primary-50 to primary-900)
- **Secondary**: Slate scale (secondary-50 to secondary-900)

### Components
- **Sidebar** - Collapsible navigation with sections
- **Header** - Top bar with backend status indicator
- **AppLayout** - Main layout wrapper
- **Cards** - Consistent card styling
- **Buttons** - Primary/secondary variants
- **Forms** - Input fields and labels

### Navigation Structure (Prepared for Future)
| Section | Items | Status |
|---------|-------|--------|
| Core | Dashboard | ✅ Enabled |
| Problems | Report, My Reports, Assigned | 🔒 Disabled |
| Collaboration | Teams | 🔒 Disabled |
| Knowledge | Repository, Analytics | 🔒 Disabled |
| Administration | Admin | 🔒 Disabled |
| Account | Profile | 🔒 Disabled |

Disabled items show "Soon" badge and are not clickable.

## Local Development Commands

### Prerequisites
- Docker & Docker Compose (or Colima)
- Python 3.11+
- Node.js 18+
- PostgreSQL 16 (via Docker)

### Start Database
```bash
# Using Docker Compose
docker compose up -d postgres

# Or directly with Docker
docker run -d --name campusxolve-postgres \
  -e POSTGRES_USER=campusxolve \
  -e POSTGRES_PASSWORD=campusxolve \
  -e POSTGRES_DB=campusxolve \
  -p 5432:5432 \
  postgres:16-alpine
```

### Backend
```bash
cd backend
cp .env.example .env
# Edit .env if needed
pip install -e ".[dev]"
python -m alembic upgrade head
python -m uvicorn app.main:app --reload
# API at http://localhost:8000
# Docs at http://localhost:8000/docs
```

### Frontend
```bash
cd frontend
cp .env.example .env.local
npm install
npm run dev
# App at http://localhost:3000
```

### Full Stack Verification
```bash
# Terminal 1: Start database
docker compose up -d postgres

# Terminal 2: Start backend
cd backend && python -m uvicorn app.main:app --reload

# Terminal 3: Start frontend
cd frontend && npm run dev

# Verify
curl http://localhost:8000/api/v1/health
# Should return {"status": "healthy", ...}

# Open http://localhost:3000
# Should show dashboard with backend status "Connected"
```

## Quality Checks

### Backend
```bash
cd backend

# Lint
python -m ruff check .

# Format
python -m ruff format .

# Type check
python -m mypy app/

# Tests
python -m pytest tests/ -v
```

### Frontend
```bash
cd frontend

# Lint
npm run lint

# Type check
npm run type-check

# Production build
npm run build
```

## What is NOT Implemented Yet

The following features are explicitly deferred to future steps:

- ❌ Authentication (JWT, login, registration)
- ❌ User roles (Student, Faculty, Admin)
- ❌ User profiles
- ❌ Problem submission workflow
- ❌ AI/ML components (DistilBERT, Sentence-BERT, spaCy)
- ❌ Problem classification, priority scoring, skill extraction
- ❌ Duplicate detection (semantic search)
- ❌ Team/mentor recommendation algorithms
- ❌ Admin review and approval workflow
- ❌ Task and milestone management
- ❌ Progress tracking
- ❌ Notifications
- ❌ Knowledge repository search
- ❌ Analytics dashboards
- ❌ Real-time features (WebSockets)
- ❌ File uploads
- ❌ Email notifications

## Verification Results

### Backend
- ✅ All tests pass (3/3)
- ✅ Ruff linting passes
- ✅ MyPy type checking passes
- ✅ Alembic migration applies successfully
- ✅ Health endpoint returns 200 with database connected

### Frontend
- ✅ ESLint passes (no warnings/errors)
- ✅ TypeScript type checking passes
- ✅ Production build succeeds
- ✅ Dashboard displays backend connectivity status

### Database
- ✅ PostgreSQL container starts successfully
- ✅ Connection established from backend
- ✅ Alembic migration applied (uuid-ossp extension)
- ✅ pgvector prepared (extension creation deferred)

### Integration
- ✅ Frontend can reach backend health endpoint
- ✅ Backend status indicator works in UI
- ✅ CORS configured correctly
- ✅ Environment variable configuration works

## Next Step

**Step 2: Authentication & User Profiles**

The foundation is complete. Step 2 will implement:
- JWT-based authentication (access + refresh tokens)
- Role-based access control (Student, Faculty, Admin)
- User registration and login
- Protected routes on frontend
- User profile management