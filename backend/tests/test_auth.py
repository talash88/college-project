"""Step 3 tests: registration, login, JWT, refresh, logout, RBAC, profile/skills."""

from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import UserRole
from app.main import app
from app.models.user import User
from app.security.jwt import REFRESH_COOKIE_NAME, create_access_token

PASSWORD = "Step3_Test_pass"


def unique_email(prefix: str = "step3") -> str:
    return f"{prefix}_{uuid4().hex[:10]}@example.com"


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def register(ac: AsyncClient, email: str, role: str = "SOLVER", password: str = PASSWORD):
    return await ac.post(
        "/api/v1/auth/register",
        json={"full_name": "Step3 User", "email": email, "password": password, "role": role},
    )


async def login(ac: AsyncClient, email: str, password: str = PASSWORD):
    return await ac.post("/api/v1/auth/login", json={"email": email, "password": password})


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def delete_user(session: AsyncSession, email: str) -> None:
    result = await session.execute(select(User).where(User.email == email.lower()))
    user = result.scalar_one_or_none()
    if user is not None:
        await session.delete(user)
        await session.commit()


async def promote_to_admin(session: AsyncSession, email: str) -> None:
    result = await session.execute(select(User).where(User.email == email.lower()))
    user = result.scalar_one()
    user.role = UserRole.ADMIN
    await session.commit()


async def deactivate(session: AsyncSession, email: str) -> None:
    result = await session.execute(select(User).where(User.email == email.lower()))
    user = result.scalar_one()
    user.is_active = False
    await session.commit()


# ---------------- Registration ----------------


@pytest.mark.asyncio
async def test_register_success(client: AsyncClient, db_session: AsyncSession):
    email = unique_email()
    try:
        resp = await register(client, email, role="REPORTER")
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["user"]["email"] == email
        assert body["user"]["role"] == "REPORTER"
        assert body["access_token"]
        assert body["token_type"] == "bearer"
        assert REFRESH_COOKIE_NAME in resp.cookies
        # Password hash must never leak.
        assert "password" not in body["user"]
        assert "password_hash" not in str(body)
        # Stored as a hash, not plaintext.
        result = await db_session.execute(select(User).where(User.email == email))
        user = result.scalar_one()
        assert user.password_hash != PASSWORD
        assert user.password_hash.startswith("$2")
    finally:
        await delete_user(db_session, email)


@pytest.mark.asyncio
async def test_register_duplicate_email(client: AsyncClient, db_session: AsyncSession):
    email = unique_email()
    try:
        assert (await register(client, email)).status_code == 201
        dup = await register(client, email)
        assert dup.status_code == 409
    finally:
        await delete_user(db_session, email)


@pytest.mark.asyncio
async def test_register_duplicate_email_case_insensitive(
    client: AsyncClient, db_session: AsyncSession
):
    email = unique_email()
    try:
        assert (await register(client, email)).status_code == 201
        dup = await register(client, email.upper())
        assert dup.status_code == 409
    finally:
        await delete_user(db_session, email)


@pytest.mark.asyncio
async def test_register_email_normalized(client: AsyncClient, db_session: AsyncSession):
    raw = f"MiXeD_{uuid4().hex[:8]}@Example.COM"
    try:
        resp = await register(client, raw)
        assert resp.status_code == 201, resp.text
        assert resp.json()["user"]["email"] == raw.lower()
    finally:
        await delete_user(db_session, raw)


@pytest.mark.asyncio
async def test_register_invalid_role(client: AsyncClient):
    resp = await register(client, unique_email(), role="SUPERUSER")
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_register_admin_blocked(client: AsyncClient):
    resp = await register(client, unique_email(), role="ADMIN")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_register_mentor_blocked(client: AsyncClient):
    resp = await register(client, unique_email(), role="MENTOR")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_register_short_password_rejected(client: AsyncClient):
    resp = await register(client, unique_email(), password="short")
    assert resp.status_code == 422


# ---------------- Login ----------------


@pytest.mark.asyncio
async def test_login_success(client: AsyncClient, db_session: AsyncSession):
    email = unique_email()
    try:
        assert (await register(client, email)).status_code == 201
        # Fresh client so the register cookie does not interfere.
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as fresh:
            resp = await login(fresh, email)
            assert resp.status_code == 200, resp.text
            assert resp.json()["access_token"]
            assert REFRESH_COOKIE_NAME in resp.cookies
    finally:
        await delete_user(db_session, email)


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient, db_session: AsyncSession):
    email = unique_email()
    try:
        assert (await register(client, email)).status_code == 201
        resp = await login(client, email, password="Wrong_Pass_999")
        assert resp.status_code == 401
    finally:
        await delete_user(db_session, email)


@pytest.mark.asyncio
async def test_login_nonexistent_user(client: AsyncClient):
    resp = await login(client, unique_email("ghost"))
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_login_inactive_user(client: AsyncClient, db_session: AsyncSession):
    email = unique_email()
    try:
        assert (await register(client, email)).status_code == 201
        await deactivate(db_session, email)
        resp = await login(client, email)
        assert resp.status_code == 403
    finally:
        await delete_user(db_session, email)


# ---------------- JWT / me ----------------


@pytest.mark.asyncio
async def test_me_valid_token(client: AsyncClient, db_session: AsyncSession):
    email = unique_email()
    try:
        reg = await register(client, email)
        token = reg.json()["access_token"]
        resp = await client.get("/api/v1/auth/me", headers=bearer(token))
        assert resp.status_code == 200
        assert resp.json()["email"] == email
    finally:
        await delete_user(db_session, email)


@pytest.mark.asyncio
async def test_me_no_token_unauthorized(client: AsyncClient):
    resp = await client.get("/api/v1/auth/me")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_me_invalid_token_unauthorized(client: AsyncClient):
    resp = await client.get("/api/v1/auth/me", headers=bearer("not.a.real.token"))
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_me_expired_token_unauthorized(client: AsyncClient, db_session: AsyncSession):
    email = unique_email()
    try:
        reg = await register(client, email)
        user_id = reg.json()["user"]["id"]
        expired = create_access_token(UUID(user_id), UserRole.SOLVER, expires_minutes=-5)
        resp = await client.get("/api/v1/auth/me", headers=bearer(expired))
        assert resp.status_code == 401
    finally:
        await delete_user(db_session, email)


# ---------------- Refresh / logout ----------------


@pytest.mark.asyncio
async def test_refresh_valid_cookie(client: AsyncClient, db_session: AsyncSession):
    email = unique_email()
    try:
        assert (await register(client, email)).status_code == 201
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as fresh:
            assert (await login(fresh, email)).status_code == 200
            resp = await fresh.post("/api/v1/auth/refresh")
            assert resp.status_code == 200, resp.text
            assert resp.json()["access_token"]
    finally:
        await delete_user(db_session, email)


@pytest.mark.asyncio
async def test_refresh_rotation_rejects_old_token(client: AsyncClient, db_session: AsyncSession):
    email = unique_email()
    try:
        reg = await register(client, email)
        old_raw = reg.cookies[REFRESH_COOKIE_NAME]
        # Rotate via body on a cookie-less client.
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as fresh:
            first = await fresh.post("/api/v1/auth/refresh", json={"refresh_token": old_raw})
            assert first.status_code == 200, first.text
            # Old token must now be rejected (reuse detected). Use another
            # cookie-less client so the rotated cookie jar cannot mask reuse.
            async with AsyncClient(transport=transport, base_url="http://test") as retry:
                second = await retry.post("/api/v1/auth/refresh", json={"refresh_token": old_raw})
                assert second.status_code == 401
    finally:
        await delete_user(db_session, email)


@pytest.mark.asyncio
async def test_refresh_revoked_token_rejected(client: AsyncClient, db_session: AsyncSession):
    email = unique_email()
    try:
        reg = await register(client, email)
        raw = reg.cookies[REFRESH_COOKIE_NAME]
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as fresh:
            assert (
                await fresh.post("/api/v1/auth/logout", json={"refresh_token": raw})
            ).status_code == 200
            resp = await fresh.post("/api/v1/auth/refresh", json={"refresh_token": raw})
            assert resp.status_code == 401
    finally:
        await delete_user(db_session, email)


@pytest.mark.asyncio
async def test_logout_revokes_session(client: AsyncClient, db_session: AsyncSession):
    email = unique_email()
    try:
        assert (await register(client, email)).status_code == 201
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as fresh:
            login_resp = await login(fresh, email)
            assert login_resp.status_code == 200
            raw = login_resp.cookies[REFRESH_COOKIE_NAME]
            assert (await fresh.post("/api/v1/auth/logout")).status_code == 200
            # Token used at logout must no longer refresh.
            retry = await fresh.post("/api/v1/auth/refresh", json={"refresh_token": raw})
            assert retry.status_code == 401
    finally:
        await delete_user(db_session, email)


# ---------------- RBAC ----------------


@pytest.mark.asyncio
async def test_login_local_dev_domain_allowed(client: AsyncClient, db_session: AsyncSession):
    """Seeded dev users live on .local domains; login must accept them."""
    email = f"{uuid4().hex[:10]}@campusxolve.local"
    try:
        assert (await register(client, email)).status_code == 201
        resp = await login(client, email)
        assert resp.status_code == 200, resp.text
    finally:
        await delete_user(db_session, email)


@pytest.mark.asyncio
async def test_rbac_admin_can_list_users(client: AsyncClient, db_session: AsyncSession):
    email = unique_email("admin")
    try:
        reg = await register(client, email)
        assert reg.status_code == 201
        await promote_to_admin(db_session, email)
        # Re-login so the access token carries the ADMIN role.
        login_resp = await login(client, email)
        token = login_resp.json()["access_token"]
        resp = await client.get("/api/v1/users", headers=bearer(token))
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)
    finally:
        await delete_user(db_session, email)


@pytest.mark.asyncio
async def test_rbac_solver_cannot_list_users(client: AsyncClient, db_session: AsyncSession):
    email = unique_email()
    try:
        reg = await register(client, email)
        token = reg.json()["access_token"]
        resp = await client.get("/api/v1/users", headers=bearer(token))
        assert resp.status_code == 403
    finally:
        await delete_user(db_session, email)


@pytest.mark.asyncio
async def test_rbac_unauthenticated_list_users_denied(client: AsyncClient):
    resp = await client.get("/api/v1/users")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_rbac_self_or_admin_user_detail(client: AsyncClient, db_session: AsyncSession):
    email_a = unique_email("usera")
    email_b = unique_email("userb")
    try:
        reg_a = (await register(client, email_a)).json()
        reg_b = (await register(client, email_b)).json()
        # Self access allowed.
        own = await client.get(
            f"/api/v1/users/{reg_a['user']['id']}", headers=bearer(reg_a["access_token"])
        )
        assert own.status_code == 200
        # Other user's data forbidden for non-admin.
        other = await client.get(
            f"/api/v1/users/{reg_b['user']['id']}", headers=bearer(reg_a["access_token"])
        )
        assert other.status_code == 403
        # Admin allowed.
        await promote_to_admin(db_session, email_a)
        admin_token = (await login(client, email_a)).json()["access_token"]
        admin_view = await client.get(
            f"/api/v1/users/{reg_b['user']['id']}", headers=bearer(admin_token)
        )
        assert admin_view.status_code == 200
    finally:
        await delete_user(db_session, email_a)
        await delete_user(db_session, email_b)


@pytest.mark.asyncio
async def test_rbac_skills_require_auth(client: AsyncClient, db_session: AsyncSession):
    anon = await client.get("/api/v1/skills")
    assert anon.status_code == 401
    email = unique_email()
    try:
        reg = await register(client, email)
        authed = await client.get("/api/v1/skills", headers=bearer(reg.json()["access_token"]))
        assert authed.status_code == 200
        assert len(authed.json()) >= 46
    finally:
        await delete_user(db_session, email)


# ---------------- Profile ----------------


@pytest.mark.asyncio
async def test_profile_get_me(client: AsyncClient, db_session: AsyncSession):
    email = unique_email()
    try:
        reg = await register(client, email)
        token = reg.json()["access_token"]
        resp = await client.get("/api/v1/profile/me", headers=bearer(token))
        assert resp.status_code == 200
        body = resp.json()
        assert body["email"] == email
        assert body["role"] == "SOLVER"
        assert body["student_profile"] is None
    finally:
        await delete_user(db_session, email)


@pytest.mark.asyncio
async def test_profile_update_and_persist(client: AsyncClient, db_session: AsyncSession):
    email = unique_email()
    ident = f"T3{uuid4().hex[:8].upper()}"
    try:
        reg = await register(client, email)
        token = reg.json()["access_token"]
        payload = {
            "full_name": "Updated Step3 Name",
            "student_profile": {
                "student_identifier": ident,
                "department": "Computer Science & Engineering",
                "academic_year": 3,
                "semester": 5,
                "bio": "Updated bio",
                "availability_status": "LIMITED",
            },
        }
        resp = await client.patch("/api/v1/profile/me", json=payload, headers=bearer(token))
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["full_name"] == "Updated Step3 Name"
        assert body["student_profile"]["student_identifier"] == ident
        assert body["student_profile"]["availability_status"] == "LIMITED"
        # Reload: changes must persist in PostgreSQL.
        again = await client.get("/api/v1/profile/me", headers=bearer(token))
        assert again.json()["full_name"] == "Updated Step3 Name"
        assert again.json()["student_profile"]["bio"] == "Updated bio"
    finally:
        await delete_user(db_session, email)


@pytest.mark.asyncio
async def test_profile_create_minimal_fields_uses_defaults(
    client: AsyncClient, db_session: AsyncSession
):
    email = unique_email()
    ident = f"T3{uuid4().hex[:8].upper()}"
    try:
        reg = await register(client, email)
        token = reg.json()["access_token"]
        resp = await client.patch(
            "/api/v1/profile/me",
            json={
                "student_profile": {
                    "student_identifier": ident,
                    "department": "Mechanical",
                    "academic_year": 1,
                }
            },
            headers=bearer(token),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["student_profile"]["availability_status"] == "AVAILABLE"
        assert body["student_profile"]["current_workload"] == 0
    finally:
        await delete_user(db_session, email)


@pytest.mark.asyncio
async def test_profile_workload_forgery_rejected(client: AsyncClient, db_session: AsyncSession):
    email = unique_email()
    try:
        reg = await register(client, email)
        token = reg.json()["access_token"]
        resp = await client.patch(
            "/api/v1/profile/me",
            json={"student_profile": {"current_workload": 99}},
            headers=bearer(token),
        )
        assert resp.status_code == 422
    finally:
        await delete_user(db_session, email)


@pytest.mark.asyncio
async def test_profile_wrong_role_payload_rejected(client: AsyncClient, db_session: AsyncSession):
    email = unique_email()
    try:
        reg = await register(client, email)
        token = reg.json()["access_token"]
        resp = await client.patch(
            "/api/v1/profile/me",
            json={"faculty_profile": {"designation": "Prof"}},
            headers=bearer(token),
        )
        assert resp.status_code == 422
    finally:
        await delete_user(db_session, email)


async def _first_skill_id(ac: AsyncClient, token: str) -> str:
    resp = await ac.get("/api/v1/skills?limit=5", headers=bearer(token))
    assert resp.status_code == 200
    return str(resp.json()[0]["id"])


@pytest.mark.asyncio
async def test_profile_skill_crud(client: AsyncClient, db_session: AsyncSession):
    email = unique_email()
    try:
        reg = await register(client, email)
        token = reg.json()["access_token"]
        skill_id = await _first_skill_id(client, token)

        # Add.
        add = await client.post(
            "/api/v1/profile/me/skills",
            json={"skill_id": skill_id, "proficiency_level": 4, "years_experience": 2},
            headers=bearer(token),
        )
        assert add.status_code == 201, add.text
        assert add.json()["proficiency_level"] == 4
        assert add.json()["skill"]["id"] == skill_id

        # Duplicate rejected.
        dup = await client.post(
            "/api/v1/profile/me/skills",
            json={"skill_id": skill_id, "proficiency_level": 3},
            headers=bearer(token),
        )
        assert dup.status_code == 409

        # List shows it.
        listed = await client.get("/api/v1/profile/me/skills", headers=bearer(token))
        assert listed.status_code == 200
        assert any(s["skill_id"] == skill_id for s in listed.json()["skills"])

        # Edit.
        edit = await client.patch(
            f"/api/v1/profile/me/skills/{skill_id}",
            json={"proficiency_level": 5, "years_experience": 3},
            headers=bearer(token),
        )
        assert edit.status_code == 200, edit.text
        assert edit.json()["proficiency_level"] == 5

        # Delete.
        delete = await client.delete(f"/api/v1/profile/me/skills/{skill_id}", headers=bearer(token))
        assert delete.status_code == 204
        gone = await client.delete(f"/api/v1/profile/me/skills/{skill_id}", headers=bearer(token))
        assert gone.status_code == 404
    finally:
        await delete_user(db_session, email)


@pytest.mark.asyncio
async def test_profile_skill_invalid_proficiency(client: AsyncClient, db_session: AsyncSession):
    email = unique_email()
    try:
        reg = await register(client, email)
        token = reg.json()["access_token"]
        skill_id = await _first_skill_id(client, token)
        resp = await client.post(
            "/api/v1/profile/me/skills",
            json={"skill_id": skill_id, "proficiency_level": 9},
            headers=bearer(token),
        )
        assert resp.status_code == 422
    finally:
        await delete_user(db_session, email)


# ---------------- Regression: Step 1 health + pgvector ----------------


@pytest.mark.asyncio
async def test_health_reports_db_and_pgvector(client: AsyncClient):
    resp = await client.get("/api/v1/health")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "healthy"
    assert body["database"] == "connected"
    assert body["pgvector_available"] is True
