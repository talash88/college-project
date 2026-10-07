"""Step 5 tests: real DistilBERT classification, RBAC, review, failure safety."""

from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.enums import UserRole
from app.main import app
from app.ml.classification.inference import reset_classifier_singleton
from app.models.user import User

PASSWORD = "Step5_Test_pass"
TAXONOMY = {
    "IT_NETWORK",
    "ELECTRICAL",
    "INFRASTRUCTURE",
    "CLEANLINESS_SANITATION",
    "SAFETY_SECURITY",
    "LABORATORY",
    "LIBRARY",
    "ACADEMIC",
    "HOSTEL",
    "TRANSPORT",
    "WATER_SANITATION",
    "OTHER",
}


def unique_email(prefix: str = "step5") -> str:
    return f"{prefix}_{uuid4().hex[:10]}@example.com"


def wifi_payload() -> dict[str, object]:
    return {
        "title": "Campus WiFi keeps disconnecting in the computer centre",
        "description": "The wireless network in the main computer centre drops every ten minutes, "
        "and students cannot submit their online lab assignments on time.",
        "location_text": "Computer Centre, First Floor",
    }


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture(autouse=True)
async def _isolated_classifier():
    """Reset the process-wide model singleton around each test."""
    reset_classifier_singleton()
    yield
    reset_classifier_singleton()


async def register(ac: AsyncClient, email: str, role: str = "REPORTER"):
    return await ac.post(
        "/api/v1/auth/register",
        json={"full_name": "Step5 User", "email": email, "password": PASSWORD, "role": role},
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


# ---------------- Auto-classification ----------------


@pytest.mark.asyncio
async def test_auto_classification_on_create(client: AsyncClient, db_session: AsyncSession):
    email, token, _ = await make_user(client)
    try:
        resp = await client.post("/api/v1/problems", json=wifi_payload(), headers=bearer(token))
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["classification_status"] in ("COMPLETED", "LOW_CONFIDENCE")
        classification = body["classification"]
        assert classification is not None
        assert classification["predicted_category"] in TAXONOMY
        assert 0.0 <= classification["confidence"] <= 1.0
        assert classification["model_version"] == "campusxolve-problem-classifier-v1"
        assert classification["classified_at"] is not None
        # Latest-result cache mirrors the audit row.
        assert body["predicted_category"] == classification["predicted_category"]
    finally:
        await delete_user(db_session, email)


@pytest.mark.asyncio
async def test_owner_can_view_classification(client: AsyncClient, db_session: AsyncSession):
    email, token, _ = await make_user(client)
    try:
        pid = (
            await client.post("/api/v1/problems", json=wifi_payload(), headers=bearer(token))
        ).json()["id"]
        resp = await client.get(f"/api/v1/problems/{pid}/classification", headers=bearer(token))
        assert resp.status_code == 200, resp.text
        assert resp.json()["predicted_category"] in TAXONOMY
        history = await client.get(f"/api/v1/problems/{pid}/classifications", headers=bearer(token))
        assert history.status_code == 200
        assert len(history.json()) == 1
    finally:
        await delete_user(db_session, email)


@pytest.mark.asyncio
async def test_stranger_cannot_view_classification(client: AsyncClient, db_session: AsyncSession):
    email, token, _ = await make_user(client)
    stranger_email, stranger_token, _ = await make_user(client)
    try:
        pid = (
            await client.post("/api/v1/problems", json=wifi_payload(), headers=bearer(token))
        ).json()["id"]
        assert (
            await client.get(
                f"/api/v1/problems/{pid}/classification", headers=bearer(stranger_token)
            )
        ).status_code == 404
        assert (
            await client.get("/api/v1/problems/00000000-0000-0000-0000-000000000000/classification")
        ).status_code == 401
    finally:
        await delete_user(db_session, email)
        await delete_user(db_session, stranger_email)


@pytest.mark.asyncio
async def test_low_confidence_flagged_for_review(
    client: AsyncClient, db_session: AsyncSession, monkeypatch
):
    monkeypatch.setattr(settings, "CLASSIFICATION_CONFIDENCE_THRESHOLD", 1.0)
    email, token, _ = await make_user(client)
    try:
        body = (
            await client.post("/api/v1/problems", json=wifi_payload(), headers=bearer(token))
        ).json()
        assert body["classification_status"] == "LOW_CONFIDENCE"
        assert body["classification"]["requires_manual_review"] is True
    finally:
        await delete_user(db_session, email)


@pytest.mark.asyncio
async def test_model_failure_keeps_problem(
    client: AsyncClient, db_session: AsyncSession, monkeypatch
):
    monkeypatch.setattr(settings, "CLASSIFICATION_MODEL_DIR", "ml/artifacts/does-not-exist")
    email, token, _ = await make_user(client)
    try:
        resp = await client.post("/api/v1/problems", json=wifi_payload(), headers=bearer(token))
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["status"] == "SUBMITTED"
        assert body["classification_status"] == "FAILED"
        assert body["predicted_category"] is None
        assert body["classification"]["predicted_category"] is None
        assert body["classification"]["requires_manual_review"] is True
    finally:
        await delete_user(db_session, email)


# ---------------- Admin rerun + review ----------------


@pytest.mark.asyncio
async def test_admin_rerun_appends_history(client: AsyncClient, db_session: AsyncSession):
    email, token, _ = await make_user(client)
    admin_email, admin_token = await make_admin(client, db_session)
    try:
        pid = (
            await client.post("/api/v1/problems", json=wifi_payload(), headers=bearer(token))
        ).json()["id"]
        # Reporter cannot rerun.
        assert (
            await client.post(
                f"/api/v1/admin/problems/{pid}/classification/run", headers=bearer(token)
            )
        ).status_code == 403
        rerun = await client.post(
            f"/api/v1/admin/problems/{pid}/classification/run", headers=bearer(admin_token)
        )
        assert rerun.status_code == 200, rerun.text
        history = (
            await client.get(f"/api/v1/problems/{pid}/classifications", headers=bearer(admin_token))
        ).json()
        assert len(history) == 2
    finally:
        await delete_user(db_session, email)
        await delete_user(db_session, admin_email)


@pytest.mark.asyncio
async def test_admin_accept_preserves_prediction(client: AsyncClient, db_session: AsyncSession):
    email, token, _ = await make_user(client)
    admin_email, admin_token = await make_admin(client, db_session)
    try:
        pid = (
            await client.post("/api/v1/problems", json=wifi_payload(), headers=bearer(token))
        ).json()["id"]
        # Reporter cannot review.
        assert (
            await client.post(
                f"/api/v1/admin/problems/{pid}/classification/review",
                json={"accept": True},
                headers=bearer(token),
            )
        ).status_code == 403
        review = await client.post(
            f"/api/v1/admin/problems/{pid}/classification/review",
            json={"accept": True, "review_note": "Looks correct"},
            headers=bearer(admin_token),
        )
        assert review.status_code == 200, review.text
        body = review.json()
        predicted = body["predicted_category"]
        assert predicted in TAXONOMY
        assert body["final_category"] == predicted
        assert body["review_note"] == "Looks correct"
        assert body["reviewed_by"] is not None
        assert body["reviewed_at"] is not None
        assert body["requires_manual_review"] is False
    finally:
        await delete_user(db_session, email)
        await delete_user(db_session, admin_email)


@pytest.mark.asyncio
async def test_admin_override_keeps_original(client: AsyncClient, db_session: AsyncSession):
    email, token, _ = await make_user(client)
    admin_email, admin_token = await make_admin(client, db_session)
    try:
        pid = (
            await client.post("/api/v1/problems", json=wifi_payload(), headers=bearer(token))
        ).json()["id"]
        original = (
            await client.get(f"/api/v1/problems/{pid}/classification", headers=bearer(admin_token))
        ).json()["predicted_category"]
        review = await client.post(
            f"/api/v1/admin/problems/{pid}/classification/review",
            json={
                "accept": False,
                "final_category": "INFRASTRUCTURE",
                "review_note": "Reassigning",
            },
            headers=bearer(admin_token),
        )
        assert review.status_code == 200, review.text
        body = review.json()
        assert body["predicted_category"] == original
        assert body["final_category"] == "INFRASTRUCTURE"
        # Invalid category rejected.
        bad = await client.post(
            f"/api/v1/admin/problems/{pid}/classification/review",
            json={"accept": False, "final_category": "PLUMBING"},
            headers=bearer(admin_token),
        )
        assert bad.status_code == 422
    finally:
        await delete_user(db_session, email)
        await delete_user(db_session, admin_email)


@pytest.mark.asyncio
async def test_review_failed_classification_rejected(
    client: AsyncClient, db_session: AsyncSession, monkeypatch
):
    monkeypatch.setattr(settings, "CLASSIFICATION_MODEL_DIR", "ml/artifacts/does-not-exist")
    email, token, _ = await make_user(client)
    admin_email, admin_token = await make_admin(client, db_session)
    try:
        pid = (
            await client.post("/api/v1/problems", json=wifi_payload(), headers=bearer(token))
        ).json()["id"]
        review = await client.post(
            f"/api/v1/admin/problems/{pid}/classification/review",
            json={"accept": True},
            headers=bearer(admin_token),
        )
        assert review.status_code == 409
    finally:
        await delete_user(db_session, email)
        await delete_user(db_session, admin_email)
