"""Step 6 tests: explainable priority engine (pure) + priority APIs."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import UserRole
from app.main import app
from app.ml.priority.scorer import calculate_priority, level_for_score
from app.models.user import User

PASSWORD = "Step6_Test_pass"


def unique_email(prefix: str = "step6p") -> str:
    return f"{prefix}_{uuid4().hex[:10]}@example.com"


def base_kwargs(**overrides):  # type: ignore[no-untyped-def]
    now = datetime.now(UTC)
    kwargs = {
        "title": "Leaking pipe in corridor",
        "description": "Water is leaking from the corridor pipe near the classrooms.",
        "affected_people_count": 10,
        "submitted_at": now,
        "status": "SUBMITTED",
        "final_category": None,
        "predicted_category": None,
        "now": now,
    }
    kwargs.update(overrides)
    return kwargs


# ---------------- Pure engine ----------------


def test_score_range_and_levels():
    assert level_for_score(0) == "LOW"
    assert level_for_score(29) == "LOW"
    assert level_for_score(30) == "MEDIUM"
    assert level_for_score(54) == "MEDIUM"
    assert level_for_score(55) == "HIGH"
    assert level_for_score(79) == "HIGH"
    assert level_for_score(80) == "CRITICAL"
    assert level_for_score(100) == "CRITICAL"


def test_cosmetic_scores_lower_than_hazard():
    now = datetime.now(UTC)
    minor = calculate_priority(
        title="Minor paint scratch",
        description="Small cosmetic paint scratch near the staircase.",
        affected_people_count=1,
        submitted_at=now,
        status="SUBMITTED",
        now=now,
    )
    hazard = calculate_priority(
        title="Electrical panel sparking",
        description="The electrical panel is sparking and 100 students use this corridor.",
        affected_people_count=100,
        submitted_at=now,
        status="SUBMITTED",
        now=now,
    )
    assert 0 <= minor.score <= 100
    assert 0 <= hazard.score <= 100
    assert hazard.score > minor.score
    assert hazard.level in ("MEDIUM", "HIGH", "CRITICAL")
    assert minor.level in ("LOW", "MEDIUM")


def test_more_affected_never_reduces_score():
    now = datetime.now(UTC)
    scores = [
        calculate_priority(**base_kwargs(affected_people_count=n, now=now)).score
        for n in (None, 1, 5, 20, 50, 100, 600)
    ]
    assert scores == sorted(scores)
    assert scores[0] == scores[1] - 5  # None==0 contribution; 1 affected gives 5


def test_age_monotonic_and_terminal_frozen():
    now = datetime.now(UTC)
    submitted = now - timedelta(days=20)
    open_old = calculate_priority(
        **base_kwargs(submitted_at=submitted, status="SUBMITTED", now=now)
    )
    open_new = calculate_priority(**base_kwargs(submitted_at=now, status="SUBMITTED", now=now))
    assert open_old.score >= open_new.score
    age_open = next(c for c in open_old.components if c.component == "pending_age")
    assert age_open.contribution == 20
    resolved = calculate_priority(**base_kwargs(submitted_at=submitted, status="RESOLVED", now=now))
    age_resolved = next(c for c in resolved.components if c.component == "pending_age")
    assert age_resolved.contribution == 0


def test_hazard_signal_and_negation():
    now = datetime.now(UTC)
    fire = calculate_priority(
        title="Smoke from panel",
        description="There is smoke coming from the electrical panel.",
        affected_people_count=5,
        submitted_at=now,
        status="SUBMITTED",
        now=now,
    )
    negated = calculate_priority(
        title="Light not working",
        description="There is no smoke or fire, only the light is not turning on.",
        affected_people_count=5,
        submitted_at=now,
        status="SUBMITTED",
        now=now,
    )
    sev_fire = next(c for c in fire.components if c.component == "severity").contribution
    sev_neg = next(c for c in negated.components if c.component == "severity").contribution
    assert sev_fire >= 12
    assert sev_neg < sev_fire
    assert fire.score > negated.score


def test_unknown_affected_handled():
    result = calculate_priority(**base_kwargs(affected_people_count=None))
    affected = next(c for c in result.components if c.component == "affected_people")
    assert affected.contribution == 0
    assert "not provided" in affected.reason


def test_duplicate_contribution_zero():
    result = calculate_priority(**base_kwargs())
    dup = next(c for c in result.components if c.component == "duplicate_impact")
    assert dup.contribution == 0
    assert dup.raw_value == 0


def test_duplicate_contribution_mapping():
    from app.ml.priority.scorer import duplicate_contribution

    assert [duplicate_contribution(n) for n in (0, 1, 2, 3, 4, 6, 7, 10, 11, 50)] == [
        0, 2, 4, 4, 6, 6, 8, 8, 10, 10,
    ]
    now = datetime.now(UTC)
    result = calculate_priority(**base_kwargs(duplicate_count=4, now=now))
    dup = next(c for c in result.components if c.component == "duplicate_impact")
    assert dup.contribution == 6
    assert "4 additional confirmed reports" in dup.reason
    assert result.score <= 100


def test_category_capped_and_never_dominant():
    now = datetime.now(UTC)
    result = calculate_priority(**base_kwargs(predicted_category="SAFETY_SECURITY", now=now))
    cat = next(c for c in result.components if c.component == "category_context")
    assert cat.contribution <= 15
    assert cat.contribution < result.score or result.score <= 15


def test_reasons_come_from_components():
    result = calculate_priority(**base_kwargs())
    assert result.reasons
    for reason in result.reasons:
        assert reason.startswith("+ ")


# ---------------- API ----------------


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def register(ac: AsyncClient, email: str, role: str = "REPORTER"):
    return await ac.post(
        "/api/v1/auth/register",
        json={"full_name": "Step6 User", "email": email, "password": PASSWORD, "role": role},
    )


async def login(ac: AsyncClient, email: str):
    return await ac.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def make_user(ac: AsyncClient, role: str = "REPORTER") -> tuple[str, str, str]:
    email = unique_email(role.lower())
    reg = await register(ac, email, role=role)
    assert reg.status_code == 201, reg.text
    return email, reg.json()["access_token"], reg.json()["user"]["id"]


async def make_admin(ac: AsyncClient, session: AsyncSession) -> tuple[str, str]:
    email, _, _ = await make_user(ac, role="SOLVER")
    result = await session.execute(select(User).where(User.email == email.lower()))
    user = result.scalar_one()
    user.role = UserRole.ADMIN
    await session.commit()
    token = (await login(ac, email)).json()["access_token"]
    return email, token


async def delete_user(session: AsyncSession, email: str) -> None:
    result = await session.execute(select(User).where(User.email == email.lower()))
    user = result.scalar_one_or_none()
    if user is not None:
        await session.delete(user)
        await session.commit()


def hazard_payload() -> dict[str, object]:
    return {
        "title": "Electrical panel sparking near classroom",
        "description": "The electrical panel outside the classroom is sparking and students pass here daily.",
        "location_text": "Academic Block",
        "affected_people_count": 40,
    }


@pytest.mark.asyncio
async def test_priority_initial_and_history(client: AsyncClient, db_session: AsyncSession):
    email, token, _ = await make_user(client)
    try:
        created = (
            await client.post("/api/v1/problems", json=hazard_payload(), headers=bearer(token))
        ).json()
        assert created["priority_status"] == "COMPLETED"
        assert 0 <= created["priority_score"] <= 100
        assert created["priority_level"] in ("LOW", "MEDIUM", "HIGH", "CRITICAL")
        pid = created["id"]
        detail = await client.get(f"/api/v1/problems/{pid}/priority", headers=bearer(token))
        assert detail.status_code == 200, detail.text
        body = detail.json()
        assert body["score"] == created["priority_score"]
        assert body["algorithm_version"] == "campusxolve-priority-v1"
        assert body["status"] == "COMPLETED"
        # Admin recalculation appends history.
        admin_email, admin_token = await make_admin(client, db_session)
        try:
            recalc = await client.post(
                f"/api/v1/admin/problems/{pid}/priority/recalculate",
                json={"reason": "manual verification"},
                headers=bearer(admin_token),
            )
            assert recalc.status_code == 200, recalc.text
            assert recalc.json()["recalculation_reason"] == "manual verification"
            detail2 = await client.get(f"/api/v1/problems/{pid}/priority", headers=bearer(token))
            assert detail2.json()["id"] == recalc.json()["id"]
        finally:
            await delete_user(db_session, admin_email)
    finally:
        await delete_user(db_session, email)


@pytest.mark.asyncio
async def test_priority_permissions(client: AsyncClient, db_session: AsyncSession):
    email, token, _ = await make_user(client)
    stranger_email, stranger_token, _ = await make_user(client)
    try:
        pid = (
            await client.post("/api/v1/problems", json=hazard_payload(), headers=bearer(token))
        ).json()["id"]
        assert (
            await client.get(f"/api/v1/problems/{pid}/priority", headers=bearer(stranger_token))
        ).status_code == 404
        assert (
            await client.post(
                f"/api/v1/admin/problems/{pid}/priority/recalculate", headers=bearer(token)
            )
        ).status_code == 403
        assert (await client.get(f"/api/v1/problems/{pid}/priority")).status_code == 401
    finally:
        await delete_user(db_session, email)
        await delete_user(db_session, stranger_email)


@pytest.mark.asyncio
async def test_priority_detail_embeds_analysis(client: AsyncClient, db_session: AsyncSession):
    email, token, _ = await make_user(client)
    try:
        pid = (
            await client.post("/api/v1/problems", json=hazard_payload(), headers=bearer(token))
        ).json()["id"]
        detail = (await client.get(f"/api/v1/problems/{pid}", headers=bearer(token))).json()
        assert detail["priority"] is not None
        assert detail["priority"]["score"] == detail["priority_score"]
        assert detail["priority"]["reasons"]
    finally:
        await delete_user(db_session, email)
