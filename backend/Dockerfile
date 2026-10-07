# Step 17: production image for the FastAPI backend.
#
# Build from the repository root so the context is predictable:
#   docker build -f backend/Dockerfile -t campusxolve-backend:prod .
#
# Notes:
# - CPU-only torch is installed from the PyTorch CPU index to keep the
#   image small (default PyPI torch wheels bundle CUDA).
# - The 256 MB DistilBERT weights (ml/artifacts/**/model.safetensors) are
#   gitignored and excluded from the build context on purpose; see
#   docs/STEP_17_DEPLOYMENT.md "Model artifacts" for the supported ways to
#   provide them (mounted volume for local prod, training step for cloud).
#   The app boots and serves honestly without them (AI marks FAILED, reports
#   still save); it never silently fakes classification.
# - Hugging Face downloads (sentence-transformers) go to $HF_HOME; mount a
#   persistent volume there in compose so first-boot downloads are cached.
FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/app/.cache/huggingface \
    SENTENCE_TRANSFORMERS_HOME=/app/.cache/huggingface \
    ENVIRONMENT=production

# psycopg/asyncpg health probe needs the postgres client; curl is used by
# platform health checks. Keep the layer minimal.
RUN apt-get update \
    && apt-get install -y --no-install-recommends postgresql-client curl \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --shell /bin/bash appuser
WORKDIR /app

# Deterministic production install: project deps only (no dev extras).
COPY backend/pyproject.toml ./pyproject.toml
RUN pip install --upgrade pip \
    && pip install --extra-index-url https://download.pytorch.org/whl/cpu "torch>=2.0.0" \
    && pip install . \
    && pip install "sqlalchemy[asyncio]>=2.0.0" \
    && pip check

# Runtime files only: application, migrations, tracked ML metadata/config,
# and the production startup script. Tests, stubs, caches stay out.
COPY --chown=appuser:appuser backend/app ./app
COPY --chown=appuser:appuser backend/alembic ./alembic
COPY --chown=appuser:appuser backend/alembic.ini ./alembic.ini
COPY --chown=appuser:appuser backend/ml ./ml
COPY --chown=appuser:appuser backend/scripts/start_production.sh ./scripts/start_production.sh
RUN chmod +x ./scripts/start_production.sh \
    && mkdir -p storage/problem-attachments .cache/huggingface \
    && chown -R appuser:appuser storage .cache

USER appuser
EXPOSE 8000

# DB wait + `alembic upgrade head` + exec uvicorn (no --reload, exec keeps PID 1).
ENTRYPOINT ["./scripts/start_production.sh"]
