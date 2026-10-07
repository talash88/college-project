"""Step 15 tests: security hardening regressions (only missing coverage)."""

import sys
from pathlib import Path
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

sys.path.insert(0, str(Path(__file__).parent))

from test_knowledge import (  # noqa: E402  # noqa: E402
    bearer,
    delete_user,
)

from app.main import app  # noqa: E402
from app.models.user import User  # noqa: E402

PASSWORD = "Step15_Test_pass"


def unique_email(prefix: str = "s15") -> str:
    return f"{prefix}_{uuid4().hex[:10]}@example.com"


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def register(ac: AsyncClient, email: str, role: str = "REPORTER") -> dict:
    resp = await ac.post(
        "/api/v1/auth/register",
        json={"full_name": "S15 User", "email": email, "password": PASSWORD, "role": role},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


# ---------------- mass assignment ----------------


@pytest.mark.asyncio
async def test_role_escalation_via_profile_rejected(client: AsyncClient, db_session: AsyncSession):
    email = unique_email()
    reg = await register(client, email)
    try:
        resp = await client.patch(
            "/api/v1/profile/me",
            json={"role": "ADMIN", "is_active": False},
            headers=bearer(reg["access_token"]),
        )
        assert resp.status_code == 422, resp.text
        result = await db_session.execute(select(User).where(User.email == email.lower()))
        assert result.scalar_one().role == "REPORTER"
    finally:
        await delete_user(db_session, email)


@pytest.mark.asyncio
async def test_problem_privileged_fields_rejected(client: AsyncClient, db_session: AsyncSession):
    email = unique_email()
    reg = await register(client, email)
    try:
        created = await client.post(
            "/api/v1/problems",
            json={
                "title": "S15 mass assignment probe report",
                "description": "A sufficiently long description for the s15 probe report here.",
                "location_text": "S15 Hall",
            },
            headers=bearer(reg["access_token"]),
        )
        assert created.status_code == 201, created.text
        pid = created.json()["id"]
        for payload in (
            {"status": "CLOSED"},
            {"ticket_number": "CX-2099-000001"},
            {"reporter_id": str(uuid4())},
            {"priority_score": 100},
            {"priority_level": "CRITICAL"},
        ):
            resp = await client.patch(
                f"/api/v1/problems/{pid}", json=payload, headers=bearer(reg["access_token"])
            )
            assert resp.status_code == 422, (payload, resp.text)
    finally:
        await delete_user(db_session, email)


# ---------------- IDOR ----------------


@pytest.mark.asyncio
async def test_cross_user_attachment_download_hidden(
    client: AsyncClient, db_session: AsyncSession
):
    owner = await register(client, unique_email("s15a"))
    stranger = await register(client, unique_email("s15b"))
    png = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\x0f"
        b"\x00\x01\x01\x01\x00\x1b\xb4\x0e\x9c\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    try:
        created = await client.post(
            "/api/v1/problems",
            json={
                "title": "S15 attachment probe report",
                "description": "A sufficiently long description for the attachment probe here.",
                "location_text": "S15 Hall",
            },
            headers=bearer(owner["access_token"]),
        )
        pid = created.json()["id"]
        up = await client.post(
            f"/api/v1/problems/{pid}/attachments",
            files={"file": ("shot.png", png, "image/png")},
            headers=bearer(owner["access_token"]),
        )
        assert up.status_code == 201, up.text
        aid = up.json()["id"]
        # Stranger cannot even list the other reporter's attachments (404, not
        # 403: existence is not revealed), nor delete them.
        assert (
            await client.get(
                f"/api/v1/problems/{pid}/attachments",
                headers=bearer(stranger["access_token"]),
            )
        ).status_code == 404
        assert (
            await client.delete(
                f"/api/v1/problems/{pid}/attachments/{aid}",
                headers=bearer(stranger["access_token"]),
            )
        ).status_code in (403, 404)
    finally:
        await delete_user(db_session, owner["user"]["email"])
        await delete_user(db_session, stranger["user"]["email"])


@pytest.mark.asyncio
async def test_cross_user_notification_read_hidden(
    client: AsyncClient, db_session: AsyncSession
):
    owner = await register(client, unique_email("s15a"))
    stranger = await register(client, unique_email("s15b"))
    try:
        mine = await client.get("/api/v1/notifications", headers=bearer(owner["access_token"]))
        assert mine.status_code == 200
        # A random UUID that is not ours must 404, never leak or mutate.
        assert (
            await client.patch(
                f"/api/v1/notifications/{uuid4()}/read",
                headers=bearer(stranger["access_token"]),
            )
        ).status_code == 404
    finally:
        await delete_user(db_session, owner["user"]["email"])
        await delete_user(db_session, stranger["user"]["email"])


@pytest.mark.asyncio
async def test_reporter_cannot_read_internal_comments(
    client: AsyncClient, db_session: AsyncSession
):
    owner = await register(client, unique_email("s15a"))
    try:
        created = await client.post(
            "/api/v1/problems",
            json={
                "title": "S15 internal comment probe",
                "description": "A sufficiently long description for the internal probe here.",
                "location_text": "S15 Hall",
            },
            headers=bearer(owner["access_token"]),
        )
        pid = created.json()["id"]
        # Reporter tries to force an internal comment (must stay public).
        forced = await client.post(
            f"/api/v1/problems/{pid}/comments",
            json={"content": "Trying to hide this", "is_internal": True},
            headers=bearer(owner["access_token"]),
        )
        assert forced.status_code == 201, forced.text
        assert forced.json()["is_internal"] is False
        listed = await client.get(
            f"/api/v1/problems/{pid}/comments", headers=bearer(owner["access_token"])
        )
        assert all(c["is_internal"] is False for c in listed.json())
    finally:
        await delete_user(db_session, owner["user"]["email"])


# ---------------- validation / pagination caps ----------------


@pytest.mark.asyncio
async def test_oversized_description_rejected(client: AsyncClient, db_session: AsyncSession):
    email = unique_email()
    reg = await register(client, email)
    try:
        resp = await client.post(
            "/api/v1/problems",
            json={
                "title": "S15 oversized probe",
                "description": "x" * 200_000,
                "location_text": "S15 Hall",
            },
            headers=bearer(reg["access_token"]),
        )
        assert resp.status_code == 422, resp.status_code
    finally:
        await delete_user(db_session, email)


@pytest.mark.asyncio
async def test_page_size_cap_enforced(client: AsyncClient, db_session: AsyncSession):
    email = unique_email()
    reg = await register(client, email)
    try:
        resp = await client.get(
            "/api/v1/problems/me", params={"limit": 1000000}, headers=bearer(reg["access_token"])
        )
        assert resp.status_code == 422, resp.status_code
        resp = await client.get(
            "/api/v1/knowledge", params={"page_size": 1000000}, headers=bearer(reg["access_token"])
        )
        assert resp.status_code == 422, resp.status_code
    finally:
        await delete_user(db_session, email)


# ---------------- CSV injection ----------------


@pytest.mark.asyncio
async def test_csv_formula_injection_neutralized(
    client: AsyncClient, db_session: AsyncSession
):
    from test_knowledge import make_admin

    admin_email, admin_tok = await make_admin(client, db_session)
    rep = await register(client, unique_email("k13rep"))
    payload = {
        "title": "=HYPERLINK(\"http://evil.example\",\"Click\")",
        "description": "A sufficiently long description for the csv injection probe here.",
        "location_text": "S15 Hall",
    }
    try:
        created = await client.post(
            "/api/v1/problems", json=payload, headers=bearer(rep["access_token"])
        )
        assert created.status_code == 201, created.text
        resp = await client.get(
            "/api/v1/admin/analytics/export/problems.csv", headers=bearer(admin_tok)
        )
        assert resp.status_code == 200, resp.text
        import csv as csv_module
        import io as io_module

        parsed = list(csv_module.DictReader(io_module.StringIO(resp.text)))
        evil = [row for row in parsed if "HYPERLINK" in row["title"]]
        assert evil, "expected the malicious title in the export"
        assert evil[0]["title"].startswith("'="), evil[0]["title"][:60]
        # Ordinary text passes through uncorrupted.
        assert "'=HYPERLINK" in resp.text
    finally:
        await delete_user(db_session, rep["user"]["email"])
        await delete_user(db_session, admin_email)


# ---------------- cookies / headers / request id / errors ----------------


@pytest.mark.asyncio
async def test_refresh_cookie_flags(client: AsyncClient, db_session: AsyncSession):
    email = unique_email()
    await register(client, email)
    try:
        resp = await client.post(
            "/api/v1/auth/login", json={"email": email, "password": PASSWORD}
        )
        assert resp.status_code == 200
        cookie = resp.headers.get("set-cookie", "")
        assert "cx_refresh=" in cookie
        assert "HttpOnly" in cookie
        assert "SameSite=Lax" in cookie or "samesite=lax" in cookie.lower()
        assert "Path=/api/v1/auth" in cookie
    finally:
        await delete_user(db_session, email)


@pytest.mark.asyncio
async def test_security_headers_and_request_id(client: AsyncClient):
    resp = await client.get("/api/v1/health")
    assert resp.status_code == 200
    assert resp.headers.get("x-content-type-options") == "nosniff"
    assert resp.headers.get("x-frame-options") == "DENY"
    assert "referrer-policy" in resp.headers
    assert "permissions-policy" in resp.headers
    assert resp.headers.get("x-request-id"), "request id missing"


@pytest.mark.asyncio
async def test_unhandled_error_envelope_hides_internals(
    client: AsyncClient, db_session: AsyncSession, monkeypatch
):
    email = unique_email()
    reg = await register(client, email)
    try:
        import app.services.analytics_service as analytics_mod

        async def _boom(self, **kwargs):
            raise RuntimeError("simulated DB disaster at /tmp/secret/path")

        monkeypatch.setattr(analytics_mod.AnalyticsService, "dashboard", _boom)
        resp = await client.get(
            "/api/v1/admin/analytics/dashboard", headers=bearer(reg["access_token"])
        )
        # Reporter is not admin: RBAC fires before the boom.
        assert resp.status_code == 403
        from test_knowledge import make_admin

        admin_email, admin_tok = await make_admin(client, db_session)
        try:
            # raise_app_exceptions=False so the 500 envelope is returned, not raised.
            from httpx import ASGITransport as _Transport

            transport = _Transport(app=app, raise_app_exceptions=False)
            async with AsyncClient(transport=transport, base_url="http://test") as raw:
                resp = await raw.get(
                    "/api/v1/admin/analytics/dashboard", headers=bearer(admin_tok)
                )
                assert resp.status_code == 500, resp.status_code
                assert resp.json() == {"detail": "Internal server error"}
                assert "secret" not in resp.text
                assert "Traceback" not in resp.text
                assert resp.headers.get("x-request-id"), "request id missing on 500"
        finally:
            await delete_user(db_session, admin_email)
    finally:
        await delete_user(db_session, email)


# ---------------- AI failure isolation ----------------


@pytest.mark.asyncio
async def test_ai_subsystem_failures_never_lose_report(
    client: AsyncClient, db_session: AsyncSession, monkeypatch
):
    """Each AI subsystem explodes => report still created and retrievable."""
    import app.services.classification_service as cs_mod
    import app.services.duplicate_service as dup_mod
    import app.services.mentor_recommendation_service as mr_mod
    import app.services.priority_service as pr_mod
    import app.services.skill_extraction_service as sk_mod
    import app.services.team_recommendation_service as tr_mod

    async def _boom(self, *args, **kwargs):
        raise RuntimeError("simulated AI outage")

    monkeypatch.setattr(cs_mod.ProblemClassificationService, "classify", _boom)
    monkeypatch.setattr(pr_mod.PriorityService, "analyze", _boom)
    monkeypatch.setattr(sk_mod.RequiredSkillService, "analyze", _boom)
    monkeypatch.setattr(dup_mod.DuplicateService, "analyze", _boom)
    monkeypatch.setattr(tr_mod.TeamRecommendationService, "analyze", _boom)
    monkeypatch.setattr(mr_mod.MentorRecommendationService, "analyze", _boom)

    email = unique_email()
    reg = await register(client, email)
    try:
        created = await client.post(
            "/api/v1/problems",
            json={
                "title": "S15 AI outage probe report",
                "description": "A sufficiently long description for the AI outage probe here.",
                "location_text": "S15 Hall",
            },
            headers=bearer(reg["access_token"]),
        )
        assert created.status_code == 201, created.text
        pid = created.json()["id"]
        detail = await client.get(
            f"/api/v1/problems/{pid}", headers=bearer(reg["access_token"])
        )
        assert detail.status_code == 200, detail.text
        assert detail.json()["ticket_number"].startswith("CX-")
    finally:
        await delete_user(db_session, email)


# ---------------- seed safety ----------------


def test_seed_scripts_require_explicit_invocation():
    """Importing app or seed modules must never create accounts by itself."""
    import inspect

    import app.main as main_mod

    lifespan_source = inspect.getsource(main_mod.lifespan)
    assert "seed" not in lifespan_source.lower()
    app_source = inspect.getsource(main_mod)
    assert "seed_users" not in app_source
    assert "seed_skills" not in app_source


# ---------------- rate limiting (unit-level, deterministic) ----------------


def test_rate_limiter_buckets_and_retry_after():
    from app.middleware.security import RateLimitMiddleware

    middleware = RateLimitMiddleware(
        app=None, enabled=True, default_per_minute=600, auth_per_minute=3,
        upload_per_minute=30, ai_per_minute=60, search_per_minute=120,
    )
    now = 1000.0
    for _ in range(3):
        allowed, _ = middleware._allowed(("1.2.3.4", "auth"), 3, now)
        assert allowed is True
    allowed, retry_after = middleware._allowed(("1.2.3.4", "auth"), 3, now)
    assert allowed is False
    assert retry_after > 0
    # Separate client unaffected.
    allowed, _ = middleware._allowed(("5.6.7.8", "auth"), 3, now)
    assert allowed is True
    # Window slides: after 61s the bucket is empty again.
    allowed, _ = middleware._allowed(("1.2.3.4", "auth"), 3, now + 61.0)
    assert allowed is True
    # Bucket routing.
    assert middleware._bucket("/api/v1/auth/login", "POST") == ("auth", 3)
    assert middleware._bucket("/api/v1/problems/x/attachments", "POST")[0] == "upload"
    assert middleware._bucket("/api/v1/knowledge", "GET")[0] == "search"
    assert middleware._bucket("/api/v1/problems/me", "GET")[0] == "default"


# ---------------- environment / test-db guards ----------------


def test_production_refuses_default_secret():
    from pydantic import ValidationError

    from app.core.config import Settings

    for bad in (
        "your-super-secret-jwt-key-change-in-production",
        "short",
        "change-me",
    ):
        try:
            Settings(ENVIRONMENT="production", JWT_SECRET_KEY=bad)
        except ValidationError:
            continue
        raise AssertionError(f"production accepted unsafe secret: {bad!r}")
    ok = Settings(ENVIRONMENT="production", JWT_SECRET_KEY="a" * 32)
    assert ok.ENVIRONMENT == "production"


def test_production_rejects_wildcard_cors_and_bad_frontend():
    from pydantic import ValidationError

    from app.core.config import Settings

    try:
        Settings(
            ENVIRONMENT="production",
            JWT_SECRET_KEY="b" * 32,
            CORS_ORIGINS=["*"],
        )
    except ValidationError:
        pass
    else:
        raise AssertionError("production accepted wildcard CORS origins")
    try:
        Settings(
            ENVIRONMENT="production", JWT_SECRET_KEY="b" * 32, FRONTEND_URL="not-a-url"
        )
    except ValidationError:
        pass
    else:
        raise AssertionError("production accepted malformed FRONTEND_URL")


def test_testdb_guard_refuses_dev_database():
    from tests.db_guard import resolve_test_database_url

    try:
        resolve_test_database_url(
            explicit="postgresql+asyncpg://campusxolve:campusxolve@localhost:5432/campusxolve"
        )
    except RuntimeError:
        return
    raise AssertionError("fail-fast guard did not trigger for the dev database")


def test_cors_policy_modes():
    from app.core.config import Settings

    dev = Settings(ENVIRONMENT="development")
    assert dev.cors_allow_methods() == ["*"]
    prod = Settings(
        ENVIRONMENT="production",
        JWT_SECRET_KEY="c" * 32,
        FRONTEND_URL="https://app.example.edu",
        CORS_ORIGINS=["https://app.example.edu"],
    )
    assert "*" not in prod.cors_allow_methods()
    assert "*" not in prod.cors_allow_headers()
    assert "Authorization" in prod.cors_allow_headers()
