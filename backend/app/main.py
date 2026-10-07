import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.admin import candidates_router as admin_candidates_router
from app.api.v1.admin import clusters_router as admin_clusters_router
from app.api.v1.admin import recommendations_router as admin_recommendations_router
from app.api.v1.admin import router as admin_router
from app.api.v1.admin import workflow_router as admin_workflow_router
from app.api.v1.analytics import router as analytics_router
from app.api.v1.auth import router as auth_router
from app.api.v1.development import router as development_router
from app.api.v1.development import skill_router
from app.api.v1.health import router as health_router
from app.api.v1.knowledge import admin_router as knowledge_admin_router
from app.api.v1.knowledge import router as knowledge_router
from app.api.v1.notifications import router as notifications_router
from app.api.v1.problems import router as problems_router
from app.api.v1.profile import router as profile_router
from app.api.v1.solutions import router as solutions_router
from app.api.v1.workspace import router as workspace_router
from app.core.config import settings
from app.db.session import close_db
from app.middleware import REQUEST_ID_HEADER, RateLimitMiddleware, SecurityHeadersMiddleware

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    logger.info(f"Starting {settings.APP_NAME} API in {settings.ENVIRONMENT} mode")
    if settings.ENVIRONMENT == "production" and settings.JWT_SECRET_KEY.startswith(
        "your-super-secret"
    ):
        logger.warning("JWT_SECRET_KEY is still the default value in production!")
    # Best-effort pre-warm of the Step 5 problem classifier (lazy-loads on
    # first classification anyway; a missing artifact only disables AI).
    try:
        from app.ml.classification.inference import get_classifier
        from app.services.classification_service import resolve_artifact_dir

        get_classifier(resolve_artifact_dir())
        logger.info("Problem classifier pre-warmed")
    except Exception as exc:
        logger.warning("Problem classifier unavailable at startup: %s", exc)
    yield
    logger.info(f"Shutting down {settings.APP_NAME} API")
    await close_db()


app = FastAPI(
    title=settings.APP_NAME,
    description=settings.APP_DESCRIPTION,
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url=f"{settings.API_PREFIX}/openapi.json",
    lifespan=lifespan,
)

# Added in reverse execution order: CORS runs outermost, then security
# headers (assigns the request ID), then rate limiting, then routing.
app.add_middleware(
    RateLimitMiddleware,
    enabled=settings.RATE_LIMIT_ENABLED and settings.ENVIRONMENT != "test",
    default_per_minute=settings.RATE_LIMIT_DEFAULT_PER_MINUTE,
    auth_per_minute=settings.RATE_LIMIT_AUTH_PER_MINUTE,
    upload_per_minute=settings.RATE_LIMIT_UPLOAD_PER_MINUTE,
    ai_per_minute=settings.RATE_LIMIT_AI_PER_MINUTE,
    search_per_minute=settings.RATE_LIMIT_SEARCH_PER_MINUTE,
)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=settings.cors_allow_methods(),
    allow_headers=settings.cors_allow_headers(),
)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Last-resort 500 envelope: safe message outside, traceback in server logs only."""
    request_id = getattr(request.state, "request_id", "unknown")
    logger.exception("unhandled error request_id=%s path=%s", request_id, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
        headers={REQUEST_ID_HEADER: request_id},
    )

app.include_router(health_router, prefix=settings.API_PREFIX)
app.include_router(auth_router, prefix=settings.API_PREFIX)
app.include_router(profile_router, prefix=settings.API_PREFIX)
app.include_router(problems_router, prefix=settings.API_PREFIX)
app.include_router(workspace_router, prefix=settings.API_PREFIX)
app.include_router(solutions_router, prefix=settings.API_PREFIX)
app.include_router(notifications_router, prefix=settings.API_PREFIX)
app.include_router(knowledge_router, prefix=settings.API_PREFIX)
app.include_router(knowledge_admin_router, prefix=settings.API_PREFIX)
# Workflow router first: its GET /admin/problems/eligible-solvers must win
# over admin_router's GET /{problem_id} (UUID validation would 422 otherwise).
app.include_router(admin_workflow_router, prefix=settings.API_PREFIX)
app.include_router(admin_router, prefix=settings.API_PREFIX)
app.include_router(admin_candidates_router, prefix=settings.API_PREFIX)
app.include_router(admin_clusters_router, prefix=settings.API_PREFIX)
app.include_router(admin_recommendations_router, prefix=settings.API_PREFIX)
app.include_router(analytics_router, prefix=settings.API_PREFIX)
app.include_router(development_router, prefix=settings.API_PREFIX)
app.include_router(skill_router, prefix=settings.API_PREFIX)
