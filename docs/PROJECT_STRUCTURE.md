# Project Structure

```
campusxolve-ai/
├── backend/                 # FastAPI service
│   ├── app/
│   │   ├── api/v1/          # route modules (auth, problems, workspace,
│   │   │                    # solutions, admin, knowledge, analytics, health…)
│   │   ├── core/            # settings (prod fail-fast) + enums
│   │   ├── db/              # async engine/session, Base
│   │   ├── models/          # 30+ SQLAlchemy models (see DATABASE_SCHEMA.md)
│   │   ├── schemas/         # Pydantic v2 request/response contracts
│   │   ├── repositories/    # SQL-only data access
│   │   ├── services/        # business rules + AI orchestration
│   │   ├── ml/              # classifier inference, embeddings
│   │   ├── security/        # bcrypt, JWT, refresh tokens
│   │   ├── middleware/      # request ID, rate limit, security headers
│   │   ├── storage/         # local-disk adapter (swappable)
│   │   └── utils/           # shared helpers
│   ├── alembic/versions/    # 001 → 012 (single head)
│   ├── ml/artifacts/        # classifier weights (gitignored) + tracked configs
│   ├── ml/data/             # labelled dataset (288)
│   ├── scripts/             # seeds, smoke checks, demo seed/reset, prod entrypoint
│   ├── tests/               # 266 pytest tests (isolated test DB)
│   ├── Dockerfile / .dockerignore / pyproject.toml / alembic.ini
├── frontend/                # Next.js 14 + React 18 + TS + Tailwind
│   ├── src/app/             # 22 routes (login, dashboard, problems, admin…,
│   │                        # workspace, knowledge, analytics, 403/404)
│   │── src/components/      # role views, AI panels, workspace, charts
│   │── src/lib/             # axios client, endpoints, auth service
│   ├── Dockerfile / .dockerignore / package.json
├── docs/                    # step logs + final submission package (this folder)
├── docker-compose.yml       # dev postgres · docker-compose.prod.yml (prod stack)
└── README.md
```
