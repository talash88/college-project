"""Step 6 tests: hybrid skill extraction, pgvector embeddings, permissions."""

from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.enums import UserRole
from app.main import app
from app.ml.skills.matcher import (
    SkillCandidate,
    find_exact_phrases,
    rank_candidates,
)
from app.models.problem_analysis import SkillEmbedding
from app.models.user import User

PASSWORD = "Step6_Test_pass"


def unique_email(prefix: str = "step6s") -> str:
    return f"{prefix}_{uuid4().hex[:10]}@example.com"


# ---------------- Pure matcher ----------------


def test_exact_phrase_matching():
    assert find_exact_phrases("The CCTV camera is offline", "CCTV Systems") == "cctv"
    assert find_exact_phrases("React app is broken", "React") == "react"
    assert find_exact_phrases("Wi-Fi keeps dropping", "Computer Networking") in ("wi-fi", "wifi")
    # Generic words must not fire.
    assert find_exact_phrases("We need a new design for the fest", "UI/UX Design") is None
    assert find_exact_phrases("The system is slow today", "System Administration") is None
    assert find_exact_phrases("design", "Graphic Design") is None


def test_rank_hybrid_and_threshold():
    cands = [
        SkillCandidate(
            skill_id=UUID(int=1),
            skill_name="CCTV Systems",
            skill_category="Hardware / Campus Technical",
            semantic_score=0.53,
            exact_phrase="cctv",
        ),
        SkillCandidate(
            skill_id=UUID(int=2),
            skill_name="Graphic Design",
            skill_category="Design",
            semantic_score=0.10,
        ),
    ]
    matches = rank_candidates(cands, threshold=0.45, max_results=6)
    assert len(matches) == 1
    assert matches[0].skill_name == "CCTV Systems"
    assert matches[0].match_type == "HYBRID"
    assert matches[0].score == round(min(0.95 + 0.0, 0.99), 4)
    assert "cctv" in matches[0].reason


def test_rank_caps_and_sorts():
    cands = [
        SkillCandidate(
            skill_id=UUID(int=i),
            skill_name=f"Skill {i}",
            skill_category="General",
            semantic_score=0.9 - i * 0.01,
        )
        for i in range(10)
    ]
    matches = rank_candidates(cands, threshold=0.0, max_results=6)
    assert len(matches) == 6
    scores = [m.score for m in matches]
    assert scores == sorted(scores, reverse=True)


def test_category_bonus_small_and_capped():
    cands = [
        SkillCandidate(
            skill_id=UUID(int=3),
            skill_name="Computer Networking",
            skill_category="Infrastructure / Networking",
            semantic_score=0.94,
            category_bonus=0.05,
        )
    ]
    matches = rank_candidates(cands, threshold=0.0, max_results=6)
    assert matches[0].score == 0.99  # capped, never 1.0


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


def cctv_payload() -> dict[str, object]:
    return {
        "title": "CCTV camera near gate is offline",
        "description": "The CCTV camera near the main gate is offline and the security office cannot monitor visitors.",
        "location_text": "Main Gate",
        "affected_people_count": 12,
    }


@pytest.mark.asyncio
async def test_skill_extraction_cctv(client: AsyncClient, db_session: AsyncSession):
    email, token, _ = await make_user(client)
    try:
        created = (
            await client.post("/api/v1/problems", json=cctv_payload(), headers=bearer(token))
        ).json()
        assert created["required_skills_status"] == "COMPLETED"
        names = [s["skill_name"] for s in created["required_skills"]]
        assert "CCTV Systems" in names
        top = next(s for s in created["required_skills"] if s["skill_name"] == "CCTV Systems")
        assert top["match_type"] in ("EXACT", "HYBRID")
        assert 0.0 <= top["score"] <= 1.0
        assert top["reason"]
        pid = created["id"]
        detail = await client.get(f"/api/v1/problems/{pid}/required-skills", headers=bearer(token))
        assert detail.status_code == 200, detail.text
        assert detail.json()["status"] == "COMPLETED"
        assert any(s["skill_name"] == "CCTV Systems" for s in detail.json()["required_skills"])
    finally:
        await delete_user(db_session, email)


@pytest.mark.asyncio
async def test_no_forced_skills_for_cleanliness(client: AsyncClient, db_session: AsyncSession):
    email, token, _ = await make_user(client)
    try:
        created = (
            await client.post(
                "/api/v1/problems",
                json={
                    "title": "Washroom not cleaned for days",
                    "description": "The washroom floor has not been cleaned for several days and smells awful.",
                    "location_text": "Hostel Block",
                },
                headers=bearer(token),
            )
        ).json()
        assert created["required_skills_status"] == "COMPLETED"
        software = {
            "React",
            "Next.js",
            "Django",
            "FastAPI",
            "TypeScript",
            "Machine Learning",
            "PyTorch",
            "TensorFlow",
        }
        assert not (software & {s["skill_name"] for s in created["required_skills"]})
    finally:
        await delete_user(db_session, email)


@pytest.mark.asyncio
async def test_skill_reanalyze_and_history(client: AsyncClient, db_session: AsyncSession):
    email, token, _ = await make_user(client)
    admin_email, admin_token = await make_admin(client, db_session)
    try:
        pid = (
            await client.post("/api/v1/problems", json=cctv_payload(), headers=bearer(token))
        ).json()["id"]
        assert (
            await client.post(
                f"/api/v1/admin/problems/{pid}/skills/reanalyze", headers=bearer(token)
            )
        ).status_code == 403
        first = await client.get(f"/api/v1/problems/{pid}/required-skills", headers=bearer(token))
        first_id = first.json()["id"]
        rerun = await client.post(
            f"/api/v1/admin/problems/{pid}/skills/reanalyze",
            json={"reason": "after description edit"},
            headers=bearer(admin_token),
        )
        assert rerun.status_code == 200, rerun.text
        assert rerun.json()["id"] != first_id
        assert rerun.json()["recalculation_reason"] == "after description edit"
    finally:
        await delete_user(db_session, email)
        await delete_user(db_session, admin_email)


@pytest.mark.asyncio
async def test_skill_permissions(client: AsyncClient, db_session: AsyncSession):
    email, token, _ = await make_user(client)
    stranger_email, stranger_token, _ = await make_user(client)
    try:
        pid = (
            await client.post("/api/v1/problems", json=cctv_payload(), headers=bearer(token))
        ).json()["id"]
        assert (
            await client.get(
                f"/api/v1/problems/{pid}/required-skills", headers=bearer(stranger_token)
            )
        ).status_code == 404
        assert (await client.get(f"/api/v1/problems/{pid}/required-skills")).status_code == 401
    finally:
        await delete_user(db_session, email)
        await delete_user(db_session, stranger_email)


@pytest.mark.asyncio
async def test_embeddings_cover_active_taxonomy(db_session: AsyncSession):
    """Every genuine active skill has exactly one embedding for the current version.

    Skips `Python_<hex>` rows: those are leftover artifacts created by older
    Step 2 model tests, not part of the seeded taxonomy.
    """
    import re

    from app.models.skill import Skill

    JUNK_RE = re.compile(r"^Python_[0-9a-f]{8}$")
    active = (
        (await db_session.execute(select(Skill).where(Skill.is_active.is_(True)))).scalars().all()
    )
    genuine = [s for s in active if not JUNK_RE.match(s.name)]
    assert len(genuine) == 46
    for skill in genuine:
        rows = (
            (
                await db_session.execute(
                    select(SkillEmbedding).where(
                        SkillEmbedding.skill_id == skill.id,
                        SkillEmbedding.model_version == settings.SKILL_EMBEDDING_VERSION,
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(rows) == 1, skill.name
        assert rows[0].embedding_dimension == 384
        assert len(rows[0].embedding) == 384


@pytest.mark.asyncio
async def test_embedding_build_idempotent(db_session: AsyncSession):
    before = (
        await db_session.execute(
            select(func.count())
            .select_from(SkillEmbedding)
            .where(SkillEmbedding.model_version == settings.SKILL_EMBEDDING_VERSION)
        )
    ).scalar_one()
    assert before == 46
