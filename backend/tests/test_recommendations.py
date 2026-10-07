"""Step 8 tests: team combinations, mentor ranking, eligibility, pipeline, APIs.

Pure math tests are fully deterministic (no DB). API tests run the real
pipeline (Step 6 extraction, real embeddings) against seeded + created users.
"""

from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import String, cast, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.enums import (
    AvailabilityStatus,
    Department,
    ProficiencyLevel,
    UserRole,
)
from app.main import app
from app.ml.recommendations.mentor_scoring import (
    MentorInput,
    MentorSkillInput,
    category_overlap,
    score_mentor,
)
from app.ml.recommendations.scoring import (
    RequiredSkillInput,
    SolverInput,
    SolverSkillInput,
    availability_factor,
    domain_factor,
    proficiency_factor,
    score_team,
    spare_fraction,
)
from app.ml.recommendations.team_search import search_teams
from app.models.faculty_profile import FacultyProfile
from app.models.recommendation import MentorRecommendation, TeamRecommendation
from app.models.skill import Skill
from app.models.student_profile import StudentProfile
from app.models.user import User
from app.models.user_skill import UserSkill

PASSWORD = "Step8_Test_pass"


def unique_email(prefix: str = "step8") -> str:
    return f"{prefix}_{uuid4().hex[:10]}@example.com"


# ---------------- Pure team math ----------------


def req(skill_id: str, name: str, relevance: float, category: str | None = None):
    return RequiredSkillInput(skill_id=skill_id, name=name, relevance=relevance, category=category)


def solver(
    name: str,
    skills: list[tuple[str, int, bool, str | None]],
    availability: str = "AVAILABLE",
    current: int = 0,
    maximum: int = 3,
    department: str | None = None,
) -> SolverInput:
    return SolverInput(
        user_id=f"user-{name}",
        name=name,
        availability=availability,
        current_workload=current,
        max_workload=maximum,
        department=department,
        academic_year=3,
        skills=tuple(
            SolverSkillInput(
                skill_id=sid, name=sid, proficiency=p, is_verified=v, category=c
            )
            for sid, p, v, c in skills
        ),
    )


def test_weights_sum_to_100():
    assert 50.0 + 20.0 + 10.0 + 10.0 + 5.0 + 5.0 == 100.0
    assert 35.0 + 30.0 + 15.0 + 10.0 + 10.0 == 100.0


def test_proficiency_mapping():
    assert proficiency_factor(1) == 0.20
    assert proficiency_factor(2) == 0.40
    assert proficiency_factor(3) == 0.60
    assert proficiency_factor(4) == 0.80
    assert proficiency_factor(5) == 1.00


def test_availability_and_workload_mapping():
    assert availability_factor("AVAILABLE") == 1.0
    assert availability_factor("LIMITED") == 0.5
    assert spare_fraction(0, 3) == 1.0
    assert spare_fraction(2, 3) < spare_fraction(0, 3)
    assert spare_fraction(1, 3) == pytest.approx(2 / 3)


def test_complementary_team_beats_redundant_team():
    required = [req("a", "SkillA", 0.9), req("b", "SkillB", 0.9)]
    s1 = solver("s1", [("a", 5, True, None)])
    s2 = solver("s2", [("b", 5, True, None)])
    s3 = solver("s3", [("a", 5, True, None)])
    complementary = score_team((s1, s2), tuple(required), None)
    redundant = score_team((s1, s3), tuple(required), None)
    assert complementary.coverage_percent == 100.0
    assert redundant.coverage_percent == 50.0
    assert complementary.total > redundant.total


def test_no_double_counting():
    required = [req("a", "SkillA", 1.0)]
    team = (
        solver("s1", [("a", 5, True, None)]),
        solver("s2", [("a", 5, True, None)]),
    )
    score = score_team(team, tuple(required), None)
    assert score.coverage_percent == 100.0
    assert score.coverage == 50.0  # capped, not doubled


def test_relevance_weighting_matters_more():
    required = [req("high", "High", 0.95), req("low", "Low", 0.30)]
    covers_high = score_team((solver("s", [("high", 4, False, None)]),), tuple(required), None)
    covers_low = score_team((solver("s", [("low", 4, False, None)]),), tuple(required), None)
    assert covers_high.coverage > covers_low.coverage


def test_higher_proficiency_improves_result():
    required = [req("a", "SkillA", 0.8)]
    expert = score_team((solver("s", [("a", 5, False, None)]),), tuple(required), None)
    beginner = score_team((solver("s", [("a", 1, False, None)]),), tuple(required), None)
    assert expert.total > beginner.total
    assert expert.proficiency > beginner.proficiency


def test_verified_small_bonus_not_requirement():
    required = [req("a", "SkillA", 0.8)]
    verified = score_team((solver("s", [("a", 4, True, None)]),), tuple(required), None)
    unverified = score_team((solver("s", [("a", 4, False, None)]),), tuple(required), None)
    assert verified.total > unverified.total
    assert verified.total - unverified.total <= 5.0  # small bonus only
    assert unverified.coverage > 0  # unverified still valuable


def test_limited_availability_penalized():
    required = [req("a", "SkillA", 0.8)]
    full = score_team((solver("s", [("a", 4, False, None)], availability="AVAILABLE"),), tuple(required), None)
    limited = score_team((solver("s", [("a", 4, False, None)], availability="LIMITED"),), tuple(required), None)
    assert full.availability > limited.availability
    assert full.total > limited.total


def test_spare_capacity_preferred():
    required = [req("a", "SkillA", 0.8)]
    free = score_team((solver("s", [("a", 4, False, None)], current=0),), tuple(required), None)
    busy = score_team((solver("s", [("a", 4, False, None)], current=2),), tuple(required), None)
    assert free.workload > busy.workload
    assert free.total > busy.total


def test_domain_never_punishes_unmapped_category():
    required = [req("a", "SkillA", 0.8)]
    score = score_team(
        (solver("s", [("a", 4, False, None)], department="Civil"),), tuple(required), "LIBRARY"
    )
    assert score.domain == 5.0  # neutral full marks
    assert domain_factor("Civil", "WATER_SANITATION") == 1.0
    assert domain_factor("Computer Science & Engineering", "WATER_SANITATION") == 0.5


def test_search_respects_size_bounds_and_orders_options():
    required = [req("a", "SkillA", 0.9), req("b", "SkillB", 0.9)]
    solvers = [
        solver("s1", [("a", 5, True, None)]),
        solver("s2", [("b", 5, True, None)]),
        solver("s3", [("a", 3, False, None)]),
        solver("s4", [("b", 3, False, None)]),
    ]
    options = search_teams(solvers, required, None, min_size=2, max_size=3, num_options=3)
    assert 1 <= len(options) <= 3
    assert all(2 <= len(o.members) <= 3 for o in options)
    totals = [o.score.total for o in options]
    assert totals == sorted(totals, reverse=True)
    # Best option covers both skills.
    assert options[0].score.coverage_percent == 100.0


def test_search_deterministic_and_tie_broken():
    required = [req("a", "SkillA", 0.9)]
    solvers = [solver(f"s{i}", [("a", 4, False, None)]) for i in range(5)]
    first = search_teams(solvers, required, None, min_size=2, max_size=2, num_options=3)
    second = search_teams(list(reversed(solvers)), required, None, min_size=2, max_size=2, num_options=3)
    assert [o.score.total for o in first] == [o.score.total for o in second]
    assert [[m.user_id for m in o.members] for o in first] == [
        [m.user_id for m in o.members] for o in second
    ]


def test_solo_only_when_allowed():
    required = [req("a", "SkillA", 0.9)]
    solvers = [solver("s1", [("a", 5, True, None)])]
    assert search_teams(solvers, required, None, min_size=2, max_size=4) == []
    solo = search_teams(
        solvers, required, None, min_size=2, max_size=4, allow_solo=True, num_options=3
    )
    assert len(solo) == 1
    assert len(solo[0].members) == 1


# ---------------- Pure mentor math ----------------


def mentor(
    name: str,
    skills: list[tuple[str, int]],
    specialization: str = "General",
    availability: str = "AVAILABLE",
    current: int = 0,
    maximum: int = 5,
    department: str | None = None,
) -> MentorInput:
    return MentorInput(
        user_id=f"mentor-{name}",
        name=name,
        availability=availability,
        current_workload=current,
        max_workload=maximum,
        department=department,
        designation="Professor",
        specialization=specialization,
        skills=tuple(
            MentorSkillInput(skill_id=sid, name=sid, proficiency=p, is_verified=True, category=None)
            for sid, p in skills
        ),
    )


def test_category_overlap_tolerant_and_zero_safe():
    assert category_overlap("IT_NETWORK", "Computer Networks / Systems", None) > 0
    assert category_overlap("IT_NETWORK", "Artificial Intelligence / Machine Learning", None) == 0
    assert category_overlap(None, "Networks", None) == 0
    assert category_overlap("IT_NETWORK", None, None) == 0


def test_mentor_weights_and_skill_match():
    required = (req("net", "Computer Networking", 0.99), req("linux", "Linux", 0.9))
    net_mentor = mentor("net", [("net", 5), ("linux", 5)], specialization="Computer Networks")
    ml_mentor = mentor("ml", [("ml", 5)], specialization="Machine Learning")
    net_score = score_mentor(net_mentor, required, "IT_NETWORK", 0.3)
    ml_score = score_mentor(ml_mentor, required, "IT_NETWORK", 0.3)
    assert net_score.total > ml_score.total
    assert net_score.skill == 30.0
    assert ml_score.skill == 0.0
    assert net_score.specialization == round(0.3 * 35.0, 2)
    assert net_score.semantic_similarity == 0.3


def test_mentor_limited_and_workload_penalty():
    required = (req("a", "SkillA", 0.9),)
    free = score_mentor(
        mentor("m", [("a", 4)], availability="AVAILABLE", current=0), required, None, 0.5
    )
    limited = score_mentor(
        mentor("m", [("a", 4)], availability="LIMITED", current=4), required, None, 0.5
    )
    assert free.availability > limited.availability
    assert free.workload > limited.workload
    assert free.total > limited.total


# ---------------- API fixtures ----------------


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture(autouse=True)
async def _clean_model_residue(db_session: AsyncSession):
    """Remove committed orphans from test_models (rel_* users) so the solver
    pool is exactly seeds + users created by each test."""
    await db_session.execute(delete(UserSkill).where(UserSkill.user_id.in_(
        select(User.id).where(User.email.startswith("rel_"))
    )))
    await db_session.execute(delete(StudentProfile).where(StudentProfile.user_id.in_(
        select(User.id).where(User.email.startswith("rel_"))
    )))
    await db_session.execute(delete(User).where(User.email.startswith("rel_")))
    await db_session.commit()
    yield


async def register(ac: AsyncClient, email: str, role: str = "REPORTER"):
    return await ac.post(
        "/api/v1/auth/register",
        json={"full_name": f"Step8 {role}", "email": email, "password": PASSWORD, "role": role},
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


async def skill_id(session: AsyncSession, name: str):
    result = await session.execute(select(Skill).where(Skill.name == name))
    skill = result.scalar_one()
    return skill.id


async def make_solver(
    ac: AsyncClient,
    session: AsyncSession,
    *,
    skills: list[tuple[str, ProficiencyLevel]],
    availability: AvailabilityStatus = AvailabilityStatus.AVAILABLE,
    current: int = 0,
    maximum: int = 3,
    active: bool = True,
) -> tuple[str, str, str]:
    email, token, user_id = await make_user(ac, role="SOLVER")
    result = await session.execute(select(User).where(User.email == email.lower()))
    user = result.scalar_one()
    user.is_active = active
    session.add(
        StudentProfile(
            user_id=user.id,
            student_identifier=f"ST8{uuid4().hex[:8]}",
            department=Department.COMPUTER_SCIENCE_ENGINEERING,
            academic_year=3,
            availability_status=availability,
            current_workload=current,
            max_workload=maximum,
        )
    )
    for name, level in skills:
        session.add(
            UserSkill(
                user_id=user.id,
                skill_id=await skill_id(session, name),
                proficiency_level=level.value,
                is_verified=False,
            )
        )
    await session.commit()
    return email, token, user_id


async def make_mentor(
    ac: AsyncClient,
    session: AsyncSession,
    *,
    skills: list[tuple[str, ProficiencyLevel]],
    specialization: str,
    availability: AvailabilityStatus = AvailabilityStatus.AVAILABLE,
    current: int = 0,
    maximum: int = 5,
    active: bool = True,
) -> tuple[str, str, str]:
    email, token, user_id = await make_user(ac, role="SOLVER")
    result = await session.execute(select(User).where(User.email == email.lower()))
    user = result.scalar_one()
    user.role = UserRole.MENTOR
    user.is_active = active
    session.add(
        FacultyProfile(
            user_id=user.id,
            employee_identifier=f"FAC8{uuid4().hex[:8]}",
            department=Department.COMPUTER_SCIENCE_ENGINEERING,
            designation="Assistant Professor",
            specialization=specialization,
            availability_status=availability,
            current_workload=current,
            max_workload=maximum,
        )
    )
    for name, level in skills:
        session.add(
            UserSkill(
                user_id=user.id,
                skill_id=await skill_id(session, name),
                proficiency_level=level.value,
                is_verified=True,
            )
        )
    await session.commit()
    return email, token, user_id


NETWORK_PAYLOAD = {
    "title": "Campus WiFi network keeps disconnecting in the computer lab",
    "description": "Students cannot access the internet in the computer lab because the WiFi "
    "network and Linux lab systems keep disconnecting during practical hours. "
    "The network switch may need inspection.",
    "location_text": "Computer Lab",
}

WEB_PAYLOAD = {
    "title": "College portal webpage layout is broken on mobile",
    "description": "The student portal webpage built with React has broken layout and navigation "
    "buttons do not respond on mobile browsers. The user interface needs fixing "
    "for admissions pages.",
    "location_text": "Main Building",
}

ML_PAYLOAD = {
    "title": "Attendance prediction needs machine learning model",
    "description": "We want a machine learning model using Python that predicts student attendance "
    "from past records. Natural language processing of feedback forms could help "
    "understand leave reasons.",
    "location_text": "CSE Block",
}

EMPTY_PAYLOAD = {
    "title": "Pigeons nesting on library windowsills chirp loudly at dawn",
    "description": "Pigeons have built nests on the library windowsills and chirp loudly every "
    "morning, disturbing readers. Please relocate the nests humanely.",
    "location_text": "Central Library",
}


async def create(ac: AsyncClient, token: str, payload: dict[str, object]) -> dict[str, object]:
    resp = await ac.post("/api/v1/problems", json=payload, headers=bearer(token))
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert isinstance(body, dict)
    return body


# ---------------- API: team ----------------


@pytest.mark.asyncio
async def test_pipeline_recommends_team_and_mentor(client: AsyncClient, db_session: AsyncSession):
    email, token, _ = await make_user(client)
    try:
        body = await create(client, token, NETWORK_PAYLOAD)
        assert body["team_recommendation_status"] == "COMPLETED"
        assert body["mentor_recommendation_status"] == "COMPLETED"
        assert body["status"] == "SUBMITTED"  # pipeline never breaks reporting
        teams = (await client.get(f"/api/v1/problems/{body['id']}/team-recommendations", headers=bearer(token))).json()
        assert teams["status"] == "COMPLETED"
        assert 1 <= len(teams["options"]) <= 3
        totals = [o["score"] for o in teams["options"]]
        assert totals == sorted(totals, reverse=True)
        assert all(2 <= o["team_size"] <= 4 for o in teams["options"])
        first = teams["options"][0]
        assert 0 <= first["score"] <= 100
        assert first["coverage_percent"] >= 0
        assert first["members"]
        mentors = (await client.get(f"/api/v1/problems/{body['id']}/mentor-recommendations", headers=bearer(token))).json()
        assert mentors["status"] == "COMPLETED"
        assert len(mentors["mentors"]) >= 1
        mtotals = [m["score"] for m in mentors["mentors"]]
        assert mtotals == sorted(mtotals, reverse=True)
    finally:
        await delete_user(db_session, email)


@pytest.mark.asyncio
async def test_network_problem_team_covers_linux(client: AsyncClient, db_session: AsyncSession):
    email, token, _ = await make_user(client)
    try:
        body = await create(client, token, NETWORK_PAYLOAD)
        teams = (await client.get(f"/api/v1/problems/{body['id']}/team-recommendations", headers=bearer(token))).json()
        covered = {s["name"] for o in teams["options"] for m in o["members"] for s in m["covered_skills"]}
        assert "Linux" in covered
        assert "Computer Networking" in teams["options"][0]["missing_skills"]
    finally:
        await delete_user(db_session, email)


@pytest.mark.asyncio
async def test_unavailable_solver_excluded(client: AsyncClient, db_session: AsyncSession):
    ghost_email, _, _ = await make_solver(
        client, db_session,
        skills=[("Linux", ProficiencyLevel.EXPERT)],
        availability=AvailabilityStatus.UNAVAILABLE,
    )
    email, token, _ = await make_user(client)
    try:
        body = await create(client, token, NETWORK_PAYLOAD)
        teams = (await client.get(f"/api/v1/problems/{body['id']}/team-recommendations", headers=bearer(token))).json()
        names = [m["name"] for o in teams["options"] for m in o["members"]]
        ghost_name = (await db_session.execute(select(User).where(User.email == ghost_email.lower()))).scalar_one().full_name
        assert ghost_name not in names
    finally:
        await delete_user(db_session, email)
        await delete_user(db_session, ghost_email)


@pytest.mark.asyncio
async def test_maxed_workload_solver_excluded(client: AsyncClient, db_session: AsyncSession):
    full_email, _, _ = await make_solver(
        client, db_session,
        skills=[("Linux", ProficiencyLevel.EXPERT)],
        current=3,
        maximum=3,
    )
    email, token, _ = await make_user(client)
    try:
        body = await create(client, token, NETWORK_PAYLOAD)
        teams = (await client.get(f"/api/v1/problems/{body['id']}/team-recommendations", headers=bearer(token))).json()
        names = [m["name"] for o in teams["options"] for m in o["members"]]
        full_name = (await db_session.execute(select(User).where(User.email == full_email.lower()))).scalar_one().full_name
        assert full_name not in names
    finally:
        await delete_user(db_session, email)
        await delete_user(db_session, full_email)


@pytest.mark.asyncio
async def test_no_eligible_solvers_truthful(client: AsyncClient, db_session: AsyncSession):
    # Park every solver as unavailable, then restore.
    solver_ids = (await db_session.execute(select(User).options(selectinload(User.student_profile)).where(cast(User.role, String) == "SOLVER"))).scalars().all()
    solver_ids = list(solver_ids)
    previous: dict[str, str] = {}
    users = []
    for user in solver_ids:
        profile = user.student_profile
        if profile is not None:
            previous[str(user.id)] = profile.availability_status.value
            users.append(user)
    email, token, _ = await make_user(client)
    try:
        for user in users:
            user.student_profile.availability_status = AvailabilityStatus.UNAVAILABLE
        await db_session.commit()
        body = await create(client, token, NETWORK_PAYLOAD)
        assert body["team_recommendation_status"] == "NO_ELIGIBLE_CANDIDATES"
        teams = (await client.get(f"/api/v1/problems/{body['id']}/team-recommendations", headers=bearer(token))).json()
        assert teams["status"] == "NO_ELIGIBLE_CANDIDATES"
        assert teams["options"] == []
        assert teams["message"]
    finally:
        for user in users:
            user.student_profile.availability_status = AvailabilityStatus(previous[str(user.id)])
        await db_session.commit()
        await delete_user(db_session, email)


@pytest.mark.asyncio
async def test_no_required_skills_truthful(client: AsyncClient, db_session: AsyncSession):
    email, token, _ = await make_user(client)
    try:
        body = await create(client, token, EMPTY_PAYLOAD)
        assert body["team_recommendation_status"] == "INSUFFICIENT_DATA"
        assert body["mentor_recommendation_status"] == "INSUFFICIENT_DATA"
        teams = (await client.get(f"/api/v1/problems/{body['id']}/team-recommendations", headers=bearer(token))).json()
        assert teams["options"] == []
        assert "Insufficient skill requirements" in (teams["message"] or "")
    finally:
        await delete_user(db_session, email)


@pytest.mark.asyncio
async def test_duplicate_member_no_independent_recommendation(
    client: AsyncClient, db_session: AsyncSession
):
    email_a, token_a, _ = await make_user(client)
    email_b, token_b, _ = await make_user(client)
    admin_email, admin_token = await make_admin(client, db_session)
    try:
        a_body = await create(client, token_a, NETWORK_PAYLOAD)
        b_body = await create(client, token_b, NETWORK_PAYLOAD)
        a_teams = (await client.get(f"/api/v1/problems/{a_body['id']}/team-recommendations", headers=bearer(token_a))).json()
        assert a_teams["status"] == "COMPLETED"
        assert a_teams["options"]
        cand = next(
            c
            for c in (
                await client.get(f"/api/v1/problems/{b_body['id']}/duplicates", headers=bearer(token_b))
            ).json()["candidates"]
            if c["candidate"]["id"] == a_body["id"]
        )
        confirm = await client.post(
            f"/api/v1/admin/duplicate-candidates/{cand['id']}/confirm",
            json={},
            headers=bearer(admin_token),
        )
        assert confirm.status_code == 200, confirm.text
        b_teams = (await client.get(f"/api/v1/problems/{b_body['id']}/team-recommendations", headers=bearer(token_b))).json()
        assert b_teams["options"] == []
        assert b_teams["canonical"]["ticket_number"] == a_body["ticket_number"]
        assert "canonical issue" in (b_teams["message"] or "")
        b_mentors = (await client.get(f"/api/v1/problems/{b_body['id']}/mentor-recommendations", headers=bearer(token_b))).json()
        assert b_mentors["mentors"] == []
        assert b_mentors["canonical"]["ticket_number"] == a_body["ticket_number"]
    finally:
        await delete_user(db_session, email_a)
        await delete_user(db_session, email_b)
        await delete_user(db_session, admin_email)


@pytest.mark.asyncio
async def test_owner_safe_view_hides_private_fields(client: AsyncClient, db_session: AsyncSession):
    email, token, _ = await make_user(client)
    try:
        body = await create(client, token, ML_PAYLOAD)
        teams = (await client.get(f"/api/v1/problems/{body['id']}/team-recommendations", headers=bearer(token))).json()
        assert teams["options"]
        flat_team = str(teams)
        assert "@example.com" not in flat_team
        assert "password" not in flat_team.lower()
        for option in teams["options"]:
            for member in option["members"]:
                assert member["user_id"] is None
                assert member["current_workload"] is None
                assert member["max_workload"] is None
                assert member["name"]
        mentors = (await client.get(f"/api/v1/problems/{body['id']}/mentor-recommendations", headers=bearer(token))).json()
        assert mentors["mentors"]
        for mentor in mentors["mentors"]:
            assert mentor["mentor_user_id"] is None
            assert mentor["current_workload"] is None
            assert mentor["name"]
            assert mentor["specialization"]
    finally:
        await delete_user(db_session, email)


@pytest.mark.asyncio
async def test_admin_full_view_and_recalc_history(client: AsyncClient, db_session: AsyncSession):
    email, token, _ = await make_user(client)
    admin_email, admin_token = await make_admin(client, db_session)
    try:
        body = await create(client, token, ML_PAYLOAD)
        admin_teams = (
            await client.get(
                f"/api/v1/problems/{body['id']}/team-recommendations", headers=bearer(admin_token)
            )
        ).json()
        assert admin_teams["options"]
        assert admin_teams["options"][0]["members"][0]["user_id"] is not None
        assert admin_teams["options"][0]["members"][0]["current_workload"] is not None
        recalc = await client.post(
            f"/api/v1/admin/problems/{body['id']}/recommendations/team/recalculate",
            json={"reason": "Step 8 test"},
            headers=bearer(admin_token),
        )
        assert recalc.status_code == 200, recalc.text
        assert recalc.json()["options"]
        history = (
            await client.get(
                f"/api/v1/problems/{body['id']}/team-recommendations/history",
                headers=bearer(admin_token),
            )
        ).json()
        assert len(history) == 2
        assert history[0]["options"] >= 1
        mrecalc = await client.post(
            f"/api/v1/admin/problems/{body['id']}/recommendations/mentor/recalculate",
            json={},
            headers=bearer(admin_token),
        )
        assert mrecalc.status_code == 200, mrecalc.text
        mhistory = (
            await client.get(
                f"/api/v1/problems/{body['id']}/mentor-recommendations/history",
                headers=bearer(admin_token),
            )
        ).json()
        assert len(mhistory) == 2
        # Deterministic: recalculation reproduces the same ranking.
        first = [m["score"] for m in mrecalc.json()["mentors"]]
        again = (
            await client.get(
                f"/api/v1/problems/{body['id']}/mentor-recommendations", headers=bearer(admin_token)
            )
        ).json()["mentors"]
        assert [m["score"] for m in again] == first
    finally:
        await delete_user(db_session, email)
        await delete_user(db_session, admin_email)


@pytest.mark.asyncio
async def test_recommendation_permissions(client: AsyncClient, db_session: AsyncSession):
    email, token, _ = await make_user(client)
    stranger_email, stranger_token, _ = await make_user(client)
    try:
        body = await create(client, token, ML_PAYLOAD)
        assert (await client.get(f"/api/v1/problems/{body['id']}/team-recommendations")).status_code == 401
        assert (
            await client.get(
                f"/api/v1/problems/{body['id']}/team-recommendations", headers=bearer(stranger_token)
            )
        ).status_code == 404
        assert (
            await client.get(
                f"/api/v1/problems/{body['id']}/mentor-recommendations", headers=bearer(stranger_token)
            )
        ).status_code == 404
        assert (
            await client.post(
                f"/api/v1/admin/problems/{body['id']}/recommendations/team/recalculate",
                json={},
                headers=bearer(token),
            )
        ).status_code == 403
        assert (
            await client.post(
                f"/api/v1/admin/problems/{body['id']}/recommendations/mentor/recalculate",
                json={},
                headers=bearer(token),
            )
        ).status_code == 403
    finally:
        await delete_user(db_session, email)
        await delete_user(db_session, stranger_email)


@pytest.mark.asyncio
async def test_workloads_never_incremented(client: AsyncClient, db_session: AsyncSession):
    async def workloads() -> dict[str, int]:
        result = await db_session.execute(
            select(User.email, StudentProfile.current_workload)
            .join(StudentProfile, StudentProfile.user_id == User.id)
            .where(cast(User.role, String) == "SOLVER")
        )
        return {row[0]: row[1] for row in result.all()}

    before = await workloads()
    email, token, _ = await make_user(client)
    admin_email, admin_token = await make_admin(client, db_session)
    try:
        body = await create(client, token, ML_PAYLOAD)
        assert (
            await client.post(
                f"/api/v1/admin/problems/{body['id']}/recommendations/team/recalculate",
                json={},
                headers=bearer(admin_token),
            )
        ).status_code == 200
        assert (
            await client.post(
                f"/api/v1/admin/problems/{body['id']}/recommendations/mentor/recalculate",
                json={},
                headers=bearer(admin_token),
            )
        ).status_code == 200
        db_session.expire_all()
        assert await workloads() == before
    finally:
        await delete_user(db_session, email)
        await delete_user(db_session, admin_email)


# ---------------- API: mentor ----------------


@pytest.mark.asyncio
async def test_network_problem_prefers_network_mentor(client: AsyncClient, db_session: AsyncSession):
    email, token, _ = await make_user(client)
    try:
        body = await create(client, token, NETWORK_PAYLOAD)
        mentors = (await client.get(f"/api/v1/problems/{body['id']}/mentor-recommendations", headers=bearer(token))).json()
        ranked = mentors["mentors"]
        assert len(ranked) >= 2
        top = ranked[0]
        assert "network" in (top["specialization"] or "").lower()
        assert top["skill_match_score"] == 30.0
        assert 0.0 <= top["semantic_similarity"] <= 1.0
        assert top["specialization_score"] == round(top["semantic_similarity"] * 35.0, 2)
    finally:
        await delete_user(db_session, email)


@pytest.mark.asyncio
async def test_ml_problem_prefers_ai_mentor(client: AsyncClient, db_session: AsyncSession):
    email, token, _ = await make_user(client)
    try:
        body = await create(client, token, ML_PAYLOAD)
        mentors = (await client.get(f"/api/v1/problems/{body['id']}/mentor-recommendations", headers=bearer(token))).json()
        ranked = mentors["mentors"]
        assert len(ranked) >= 2
        top = ranked[0]
        spec = (top["specialization"] or "").lower()
        assert "machine learning" in spec or "artificial intelligence" in spec
        assert top["skill_match_score"] == 30.0
    finally:
        await delete_user(db_session, email)


@pytest.mark.asyncio
async def test_unavailable_and_maxed_mentors_excluded(
    client: AsyncClient, db_session: AsyncSession
):
    ghost_email, _, _ = await make_mentor(
        client,
        db_session,
        skills=[("Linux", ProficiencyLevel.EXPERT)],
        specialization="Computer Networks",
        availability=AvailabilityStatus.UNAVAILABLE,
    )
    full_email, _, _ = await make_mentor(
        client,
        db_session,
        skills=[("Linux", ProficiencyLevel.EXPERT)],
        specialization="Computer Networks",
        current=5,
        maximum=5,
    )
    email, token, _ = await make_user(client)
    try:
        body = await create(client, token, NETWORK_PAYLOAD)
        mentors = (await client.get(f"/api/v1/problems/{body['id']}/mentor-recommendations", headers=bearer(token))).json()
        names = [m["name"] for m in mentors["mentors"]]
        for gone in (ghost_email, full_email):
            user = (await db_session.execute(select(User).where(User.email == gone.lower()))).scalar_one()
            assert user.full_name not in names
    finally:
        await delete_user(db_session, email)
        await delete_user(db_session, ghost_email)
        await delete_user(db_session, full_email)


@pytest.mark.asyncio
async def test_no_eligible_mentors_truthful(client: AsyncClient, db_session: AsyncSession):
    mentors = (await db_session.execute(select(User).options(selectinload(User.faculty_profile)).where(cast(User.role, String) == "MENTOR"))).scalars().all()
    mentors = list(mentors)
    previous: dict[str, str] = {}
    for user in mentors:
        if user.faculty_profile is not None:
            previous[str(user.id)] = user.faculty_profile.availability_status.value
    email, token, _ = await make_user(client)
    try:
        for user in mentors:
            if user.faculty_profile is not None:
                user.faculty_profile.availability_status = AvailabilityStatus.UNAVAILABLE
        await db_session.commit()
        body = await create(client, token, NETWORK_PAYLOAD)
        assert body["mentor_recommendation_status"] == "NO_ELIGIBLE_CANDIDATES"
        mentors_resp = (await client.get(f"/api/v1/problems/{body['id']}/mentor-recommendations", headers=bearer(token))).json()
        assert mentors_resp["mentors"] == []
    finally:
        for user in mentors:
            if user.faculty_profile is not None and str(user.id) in previous:
                user.faculty_profile.availability_status = AvailabilityStatus(previous[str(user.id)])
        await db_session.commit()
        await delete_user(db_session, email)


@pytest.mark.asyncio
async def test_recommendation_history_persisted_in_db(client: AsyncClient, db_session: AsyncSession):
    email, token, _ = await make_user(client)
    admin_email, admin_token = await make_admin(client, db_session)
    try:
        body = await create(client, token, ML_PAYLOAD)
        assert (
            await client.post(
                f"/api/v1/admin/problems/{body['id']}/recommendations/team/recalculate",
                json={},
                headers=bearer(admin_token),
            )
        ).status_code == 200
        team_rows = (
            await db_session.execute(
                select(func.count()).select_from(TeamRecommendation).where(TeamRecommendation.problem_id == body["id"])
            )
        ).scalar_one()
        assert team_rows >= 2  # create-time run + recalculation run
        mentor_rows = (
            await db_session.execute(
                select(func.count()).select_from(MentorRecommendation).where(MentorRecommendation.problem_id == body["id"])
            )
        ).scalar_one()
        assert mentor_rows >= 2
    finally:
        await delete_user(db_session, email)
        await delete_user(db_session, admin_email)
