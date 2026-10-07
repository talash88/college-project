import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_root_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "CampusXolve AI"
        assert data["description"] == "AI-Powered Campus Problem Solving"
        assert "version" in data
        assert "docs_url" in data


@pytest.mark.asyncio
async def test_health_endpoint_structure():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/health")
        # May be 200 or 503 depending on database availability
        assert response.status_code in (200, 503)
        if response.status_code == 200:
            data = response.json()
            assert "status" in data
            assert "service" in data
            assert "database" in data
            assert "pgvector_available" in data
            assert "environment" in data
            assert data["status"] == "healthy"
            assert data["service"] == "CampusXolve AI API"


@pytest.mark.asyncio
async def test_application_imports():
    from app.api.v1.health import router as health_router
    from app.core.config import settings
    from app.main import app

    assert app is not None
    assert settings.APP_NAME == "CampusXolve AI"
    assert health_router is not None
