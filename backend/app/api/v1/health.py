from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.health import check_database_connection, check_pgvector_available
from app.db.session import get_db

router = APIRouter()


class HealthResponse(BaseModel):
    status: str
    service: str
    database: str
    pgvector_available: bool
    environment: str


class RootResponse(BaseModel):
    name: str
    description: str
    version: str
    docs_url: str


@router.get("/", response_model=RootResponse, tags=["Root"])
async def root() -> RootResponse:
    return RootResponse(
        name=settings.APP_NAME,
        description=settings.APP_DESCRIPTION,
        version="0.1.0",
        docs_url="/docs",
    )


@router.get("/health", response_model=HealthResponse, tags=["Health"])
async def health_check(db: AsyncSession = Depends(get_db)) -> HealthResponse:
    db_healthy = await check_database_connection(db)
    pgvector_ready = await check_pgvector_available(db)

    if not db_healthy:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database connection failed",
        )

    return HealthResponse(
        status="healthy",
        service=f"{settings.APP_NAME} API",
        database="connected" if db_healthy else "disconnected",
        pgvector_available=pgvector_ready,
        environment=settings.ENVIRONMENT,
    )
