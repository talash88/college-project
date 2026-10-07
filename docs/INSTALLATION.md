# Installation (fresh machine)

## Requirements
- Docker (or Colima on macOS) — for PostgreSQL (pgvector image) and the
  production-style stack
- Python 3.11+ (use `python3` on macOS) · Node.js 18+ · `psql`-via-container
  for DB utilities · ~3 GB free for Docker images · internet on first
  backend boot (sentence-transformer download, cached afterwards)

## Method A — manual developer setup
```bash
# 1. PostgreSQL with pgvector
docker run -d --name campusxolve-postgres \
  -e POSTGRES_USER=campusxolve -e POSTGRES_PASSWORD=campusxolve \
  -e POSTGRES_DB=campusxolve -p 5432:5432 pgvector/pgvector:pg16

# 2. Backend (from backend/)
cd backend && cp .env.example .env
pip install -e ".[dev]"
python3 -m alembic upgrade head
python3 scripts/seed_skills.py
python3 scripts/build_skill_embeddings.py   # needs internet once (~90 MB)
python3 scripts/seed_users.py              # 7 dev accounts (dev only)
python3 -m uvicorn app.main:app --reload   # http://localhost:8000

# 3. Frontend — IMPORTANT: npm commands run inside frontend/, NOT repo root
cd frontend && cp .env.example .env.local
npm install
npm run dev                                # http://localhost:3000
```

## Method B — production-style Docker (recommended for demos)
```bash
# From repository root:
JWT_SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')" \
  docker compose -f docker-compose.prod.yml up --build
# App http://localhost:3000 · API http://localhost:8000
# Migrations run automatically; uploads + model cache persist in volumes.
# Reference data (explicit, once): seed_skills.py + build_skill_embeddings.py
# with DATABASE_URL pointed at the database. No dev users are seeded.
```

## macOS/Linux notes
- macOS: start Colima (`colima start`) before any `docker` command; always use
  `python3` (system `python` may not exist).
- Linux: ensure the user is in the `docker` group or use sudo; `python3`/`pip3`.
- Windows: not verified — use WSL2 + Docker Desktop (unverified path).

## Models
- DistilBERT weights (`backend/ml/artifacts/problem_classifier/
  model.safetensors`, 256 MB) are gitignored. If absent: copy from a release
  artifact/volume, or retrain via `python3 scripts/train_classifier.py`
  (needs the labelled dataset + GPU/CPU time). Without weights the app boots
  and AI marks classification `FAILED` honestly.
- Sentence-transformers downloads to `$HF_HOME` (default
  `~/.cache/huggingface`, or `/app/.cache/huggingface` in Docker); mount/persist it.

## Verify
`GET /api/v1/health` → `{"status":"healthy","database":"connected",
"pgvector_available":true}`. Then register a REPORTER at `/register`.
