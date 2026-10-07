"""Step 9 tests: review workflow, transactional assignment, workloads, access."""

import asyncio
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, func, select
from sqlalchemy.orm import selectinload

from app.core.enums import (
    AvailabilityStatus,
    Department,
    ProficiencyLevel,
    UserRole,
)
from app.main import app
from app.models.assignment import ProblemAssignment
from app.models.faculty_profile import FacultyProfile
from app.models.skill import Skill
from app.models.student_profile import StudentProfile
from app.models.user import User
from app.models.user_skill import UserSkill

PASSWORD = "Step9_Test_pass"


def unique_email(prefix: str = "step9") -> str:
    return f"{prefix}_{uuid4().hex[:10]}@example.com"


NETWORK_PAYLOAD = {
    "title": "Campus WiFi network keeps disconnecting in the computer lab",
    "description": "Students cannot access the internet in the computer lab because the WiFi "
    "network and Linux lab systems keep disconnecting during practical hours. "
    "The network switch may need inspection.",
    "location_text": "Computer Lab",
}


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture(autouse=True)
async def _clean_model_residue(db_session):
    # Snapshot solver/mentor workloads: assignments increment real seed
    # workloads by design, so restore them after each test.
    async def snapshot():
        rows = (
            await db_session.execute(
                select(User.id, StudentProfile.current_workload, FacultyProfile.current_workload)
                .outerjoin(StudentProfile, StudentProfile.user_id == User.id)
                .outerjoin(FacultyProfile, FacultyProfile.user_id == User.id)
            )
        ).all()
        return {str(r[0]): (r[1], r[2]) for r in rows}

    before = await snapshot()
    await db_session.execute(
        delete(UserSkill).where(
            UserSkill.user_id.in_(select(User.id).where(User.email.startswith("rel_")))
        )
    )
    await db_session.execute(
        delete(StudentProfile).where(
            StudentProfile.user_id.in_(select(User.id).where(User.email.startswith("rel_")))
        )
    )
    await db_session.execute(delete(User).where(User.email.startswith("rel_")))
    await db_session.commit()
    yield
    current = await snapshot()
    for uid, (s_before, f_before) in before.items():
        s_now, f_now = current.get(uid, (None, None))
        if s_before is not None and s_now != s_before:
            await db_session.execute(
                StudentProfile.__table__.update()
                .where(StudentProfile.user_id == uid)
                .values(current_workload=s_before)
            )
        if f_before is not None and f_now != f_before:
            await db_session.execute(
                FacultyProfile.__table__.update()
                .where(FacultyProfile.user_id == uid)
                .values(current_workload=f_before)
            )
    await db_session.commit()


async def register(ac, email, role="REPORTER"):
    return await ac.post(
        "/api/v1/auth/register",
        json={"full_name": f"Step9 {role}", "email": email, "password": PASSWORD, "role": role},
    )


async def login(ac, email):
    return await ac.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


async def make_user(ac, role="REPORTER"):
    email = unique_email(role.lower())
    reg = await register(ac, email, role=role)
    assert reg.status_code == 201, reg.text
    return email, reg.json()["access_token"], reg.json()["user"]["id"]


async def make_admin(ac, session):
    email, _, _ = await make_user(ac, role="SOLVER")
    result = await session.execute(select(User).where(User.email == email.lower()))
    user = result.scalar_one()
    user.role = UserRole.ADMIN
    await session.commit()
    token = (await login(ac, email)).json()["access_token"]
    return email, token


async def delete_user(session, email):
    result = await session.execute(select(User).where(User.email == email.lower()))
    user = result.scalar_one_or_none()
    if user is not None:
        await session.delete(user)
        await session.commit()


async def skill_id(session, name):
    result = await session.execute(select(Skill).where(Skill.name == name))
    return result.scalar_one().id


async def make_solver(ac, session, *, skills=(), availability=AvailabilityStatus.AVAILABLE,
                      current=0, maximum=3, active=True):
    email, token, user_id = await make_user(ac, role="SOLVER")
    result = await session.execute(select(User).where(User.email == email.lower()))
    user = result.scalar_one()
    user.is_active = active
    session.add(
        StudentProfile(
            user_id=user.id,
            student_identifier=f"ST9{uuid4().hex[:8]}",
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


async def make_mentor(ac, session, *, skills=(), specialization="General Mentoring",
                      availability=AvailabilityStatus.AVAILABLE, current=0, maximum=5, active=True):
    email, token, user_id = await make_user(ac, role="SOLVER")
    result = await session.execute(select(User).where(User.email == email.lower()))
    user = result.scalar_one()
    user.role = UserRole.MENTOR
    user.is_active = active
    session.add(
        FacultyProfile(
            user_id=user.id,
            employee_identifier=f"FAC9{uuid4().hex[:8]}",
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


async def create(ac, token, payload=None):
    resp = await ac.post("/api/v1/problems", json=payload or NETWORK_PAYLOAD, headers=bearer(token))
    assert resp.status_code == 201, resp.text
    return resp.json()


async def approve(client, admin_token, problem_id):
    start = await client.post(
        f"/api/v1/admin/problems/{problem_id}/review/start", headers=bearer(admin_token)
    )
    assert start.status_code == 200, start.text
    ok = await client.post(
        f"/api/v1/admin/problems/{problem_id}/approve", json={}, headers=bearer(admin_token)
    )
    assert ok.status_code == 200, ok.text
    return ok.json()


async def workload(session, email, profile_attr):
    result = await session.execute(
        select(User)
        .options(selectinload(User.student_profile), selectinload(User.faculty_profile))
        .where(User.email == email.lower())
    )
    user = result.scalar_one()
    profile = getattr(user, profile_attr, None)
    if profile is None:
        raise AssertionError(f"missing profile for {email}")
    return profile.current_workload, profile.max_workload


# ---------------- Workflow ----------------


@pytest.mark.asyncio
async def test_start_review_and_approve(client, db_session):
    email, token, _ = await make_user(client)
    admin_email, admin_token = await make_admin(client, db_session)
    try:
        body = await create(client, token)
        start = await client.post(
            f"/api/v1/admin/problems/{body['id']}/review/start", headers=bearer(admin_token)
        )
        assert start.status_code == 200
        assert start.json()["status"] == "UNDER_REVIEW"
        assert start.json()["reviewed_by"] is not None
        # Idempotent repeat.
        again = await client.post(
            f"/api/v1/admin/problems/{body['id']}/review/start", headers=bearer(admin_token)
        )
        assert again.status_code == 200
        assert again.json()["already_in_state"] is True
        approved = await client.post(
            f"/api/v1/admin/problems/{body['id']}/approve",
            json={"note": "Looks valid"},
            headers=bearer(admin_token),
        )
        assert approved.status_code == 200
        assert approved.json()["status"] == "APPROVED"
        assert approved.json()["approved_by"] is not None
        events = [a["event_type"] for a in (await client.get(
            f"/api/v1/problems/{body['id']}", headers=bearer(token))).json()["activity"]]
        assert "REVIEW_STARTED" in events
        assert "PROBLEM_APPROVED" in events
    finally:
        await delete_user(db_session, email)
        await delete_user(db_session, admin_email)


@pytest.mark.asyncio
async def test_invalid_transitions_rejected(client, db_session):
    email, token, _ = await make_user(client)
    admin_email, admin_token = await make_admin(client, db_session)
    try:
        body = await create(client, token)
        # Approve straight from SUBMITTED.
        assert (await client.post(
            f"/api/v1/admin/problems/{body['id']}/approve", json={}, headers=bearer(admin_token)
        )).status_code == 409
        # Reject then try review/approve on terminal state.
        assert (await client.post(
            f"/api/v1/admin/problems/{body['id']}/reject",
            json={"reason": "Duplicate test report"},
            headers=bearer(admin_token),
        )).status_code == 200
        for action in ("review/start", "approve"):
            assert (await client.post(
                f"/api/v1/admin/problems/{body['id']}/{action}", json={},
                headers=bearer(admin_token),
            )).status_code == 409
        assert (await client.post(
            f"/api/v1/admin/problems/{body['id']}/reject",
            json={"reason": "again"},
            headers=bearer(admin_token),
        )).status_code == 409
    finally:
        await delete_user(db_session, email)
        await delete_user(db_session, admin_email)


@pytest.mark.asyncio
async def test_reject_requires_reason_and_is_visible(client, db_session):
    email, token, _ = await make_user(client)
    admin_email, admin_token = await make_admin(client, db_session)
    try:
        body = await create(client, token)
        assert (await client.post(
            f"/api/v1/admin/problems/{body['id']}/reject", json={"reason": "   "},
            headers=bearer(admin_token),
        )).status_code == 422
        ok = await client.post(
            f"/api/v1/admin/problems/{body['id']}/reject",
            json={"reason": "Not a campus issue"},
            headers=bearer(admin_token),
        )
        assert ok.status_code == 200
        assert ok.json()["status"] == "REJECTED"
        detail = (await client.get(f"/api/v1/problems/{body['id']}", headers=bearer(token))).json()
        assert detail["status"] == "REJECTED"
        assert detail["rejection_reason"] == "Not a campus issue"
    finally:
        await delete_user(db_session, email)
        await delete_user(db_session, admin_email)


@pytest.mark.asyncio
async def test_workflow_rbac(client, db_session):
    email, token, _ = await make_user(client)
    solver_email, solver_token, _ = await make_user(client, role="SOLVER")
    mentor_email, mentor_token, _ = await make_mentor(client, db_session)
    try:
        body = await create(client, token)
        pid = body["id"]
        for tok in (token, solver_token, mentor_token):
            assert (await client.post(
                f"/api/v1/admin/problems/{pid}/review/start", headers=bearer(tok))).status_code == 403
            assert (await client.post(
                f"/api/v1/admin/problems/{pid}/approve", json={}, headers=bearer(tok))).status_code == 403
            assert (await client.post(
                f"/api/v1/admin/problems/{pid}/reject", json={"reason": "x"}, headers=bearer(tok))).status_code == 403
            assert (await client.post(
                f"/api/v1/admin/problems/{pid}/assign",
                json={"solver_user_ids": [str(uuid4())], "mentor_user_id": str(uuid4())},
                headers=bearer(tok))).status_code == 403
    finally:
        await delete_user(db_session, email)
        await delete_user(db_session, solver_email)
        await delete_user(db_session, mentor_email)


# ---------------- Assignment ----------------


async def _rec_ids(client, admin_token, problem_id):
    teams = (await client.get(
        f"/api/v1/problems/{problem_id}/team-recommendations", headers=bearer(admin_token))).json()
    mentors = (await client.get(
        f"/api/v1/problems/{problem_id}/mentor-recommendations", headers=bearer(admin_token))).json()
    return teams["options"], mentors["mentors"]


@pytest.mark.asyncio
async def test_accept_recommended_team_and_mentor(client, db_session):
    email, token, _ = await make_user(client)
    admin_email, admin_token = await make_admin(client, db_session)
    try:
        body = await create(client, token)
        await approve(client, admin_token, body["id"])
        options, mentors = await _rec_ids(client, admin_token, body["id"])
        assert options
        assert mentors
        option = options[0]
        team_ids = [m["user_id"] for m in option["members"]]
        assert all(team_ids)
        mentor_row = mentors[0]
        before = {mid: await workload(db_session, (await db_session.execute(
            select(User).where(User.id == mid))).scalar_one().email, "student_profile") for mid in team_ids}
        resp = await client.post(
            f"/api/v1/admin/problems/{body['id']}/assign",
            json={
                "solver_user_ids": team_ids,
                "mentor_user_id": mentor_row["mentor_user_id"],
                "team_recommendation_id": option["id"],
                "mentor_recommendation_id": mentor_row["id"],
            },
            headers=bearer(admin_token),
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["team_was_overridden"] is False
        assert data["mentor_was_overridden"] is False
        assert data["status"] == "ACTIVE"
        detail = (await client.get(f"/api/v1/problems/{body['id']}", headers=bearer(token))).json()
        assert detail["status"] == "ASSIGNED"
        assert detail["assignment"]["team"]["members"]
        for mid in team_ids:
            user = (await db_session.execute(select(User).where(User.id == mid))).scalar_one()
            after = await workload(db_session, user.email, "student_profile")
            assert after[0] == before[mid][0] + 1
        mentor_user = (await db_session.execute(
            select(User).where(User.id == mentor_row["mentor_user_id"]))).scalar_one()
        assert (await workload(db_session, mentor_user.email, "faculty_profile"))[0] == 1
        events = [a["event_type"] for a in detail["activity"]]
        for expected in ("TEAM_CREATED", "TEAM_ASSIGNED", "MENTOR_ASSIGNED", "ASSIGNMENT_CREATED"):
            assert expected in events
    finally:
        await delete_user(db_session, email)
        await delete_user(db_session, admin_email)


@pytest.mark.asyncio
async def test_manual_team_override_requires_reason(client, db_session):
    email, token, _ = await make_user(client)
    admin_email, admin_token = await make_admin(client, db_session)
    try:
        body = await create(client, token)
        await approve(client, admin_token, body["id"])
        options, mentors = await _rec_ids(client, admin_token, body["id"])
        extra_a_email, _, extra_a = await make_solver(
            client, db_session, skills=[("Linux", ProficiencyLevel.ADVANCED)])
        extra_b_email, _, extra_b = await make_solver(
            client, db_session, skills=[("Linux", ProficiencyLevel.ADVANCED)])
        manual = [extra_a, extra_b]
        mentor_id = mentors[0]["mentor_user_id"]
        # No reason → 422.
        assert (await client.post(
            f"/api/v1/admin/problems/{body['id']}/assign",
            json={"solver_user_ids": manual, "mentor_user_id": mentor_id,
                  "mentor_recommendation_id": mentors[0]["id"]},
            headers=bearer(admin_token),
        )).status_code == 422
        # With reason → 201, audited, recommendation rows untouched.
        before_count = (await db_session.execute(
            select(func.count()).select_from(ProblemAssignment)
            .where(ProblemAssignment.problem_id == body["id"]))).scalar_one()
        resp = await client.post(
            f"/api/v1/admin/problems/{body['id']}/assign",
            json={"solver_user_ids": manual, "mentor_user_id": mentor_id,
                  "mentor_recommendation_id": mentors[0]["id"],
                  "team_override_reason": "Chose backend-heavy pair for switch work"},
            headers=bearer(admin_token),
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["team_was_overridden"] is True
        assert data["team_override_reason"] == "Chose backend-heavy pair for switch work"
        assert data["mentor_was_overridden"] is False
        assert data["source_team_recommendation_id"] is None
        after_count = (await db_session.execute(
            select(func.count()).select_from(ProblemAssignment)
            .where(ProblemAssignment.problem_id == body["id"]))).scalar_one()
        assert after_count == before_count + 1
        # Admin can inspect AI vs final.
        admin_view = (await client.get(
            f"/api/v1/admin/problems/{body['id']}/assignment", headers=bearer(admin_token))).json()
        assert admin_view["active"]["team_was_overridden"] is True
    finally:
        await delete_user(db_session, email)
        await delete_user(db_session, admin_email)
        await delete_user(db_session, extra_a_email)
        await delete_user(db_session, extra_b_email)


@pytest.mark.asyncio
async def test_mentor_override_requires_reason(client, db_session):
    email, token, _ = await make_user(client)
    admin_email, admin_token = await make_admin(client, db_session)
    try:
        body = await create(client, token)
        await approve(client, admin_token, body["id"])
        options, mentors = await _rec_ids(client, admin_token, body["id"])
        assert len(mentors) >= 2
        other = mentors[1]
        team_ids = [m["user_id"] for m in options[0]["members"]]
        assert (await client.post(
            f"/api/v1/admin/problems/{body['id']}/assign",
            json={"solver_user_ids": team_ids, "mentor_user_id": other["mentor_user_id"],
                  "team_recommendation_id": options[0]["id"]},
            headers=bearer(admin_token),
        )).status_code == 422
        resp = await client.post(
            f"/api/v1/admin/problems/{body['id']}/assign",
            json={"solver_user_ids": team_ids, "mentor_user_id": other["mentor_user_id"],
                  "team_recommendation_id": options[0]["id"],
                  "mentor_override_reason": "Second mentor knows this lab personally"},
            headers=bearer(admin_token),
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["mentor_was_overridden"] is True
        assert resp.json()["mentor_override_reason"] == "Second mentor knows this lab personally"
    finally:
        await delete_user(db_session, email)
        await delete_user(db_session, admin_email)


@pytest.mark.asyncio
async def test_assignment_rejects_bad_members(client, db_session):
    email, token, _ = await make_user(client)
    admin_email, admin_token = await make_admin(client, db_session)
    ghost_email, _, _ = await make_solver(
        client, db_session, skills=[("Linux", ProficiencyLevel.EXPERT)],
        availability=AvailabilityStatus.UNAVAILABLE)
    full_email, _, _ = await make_solver(
        client, db_session, skills=[("Linux", ProficiencyLevel.EXPERT)], current=3, maximum=3)
    dead_email, _, _ = await make_solver(
        client, db_session, skills=[("Linux", ProficiencyLevel.EXPERT)], active=False)
    reporter_email, _, reporter_id = await make_user(client)
    try:
        body = await create(client, token)
        await approve(client, admin_token, body["id"])
        options, mentors = await _rec_ids(client, admin_token, body["id"])
        good = [m["user_id"] for m in options[0]["members"]]
        mentor_id = mentors[0]["mentor_user_id"]

        async def uid(email):
            return str((await db_session.execute(
                select(User).where(User.email == email.lower()))).scalar_one().id)

        bad_cases = [
            [good[0], good[0]],  # duplicate member
            [reporter_id],  # non-solver + too small
            [await uid(ghost_email), good[0]],  # unavailable
            [await uid(full_email), good[0]],  # maxed workload
            [await uid(dead_email), good[0]],  # inactive
        ]
        for bad in bad_cases:
            resp = await client.post(
                f"/api/v1/admin/problems/{body['id']}/assign",
                json={"solver_user_ids": bad, "mentor_user_id": mentor_id,
                      "team_override_reason": "test", "mentor_override_reason": "test"},
                headers=bearer(admin_token),
            )
            assert resp.status_code == 422, (bad, resp.text)
        # Too large: need 5 eligible solvers.
        extra = []
        for _ in range(2):
            e, _, i = await make_solver(client, db_session, skills=[("Linux", ProficiencyLevel.BASIC)])
            extra.append(i)
        try:
            big = good + extra
            assert len(big) >= 5
            resp = await client.post(
                f"/api/v1/admin/problems/{body['id']}/assign",
                json={"solver_user_ids": big, "mentor_user_id": mentor_id,
                      "team_override_reason": "test", "mentor_override_reason": "test"},
                headers=bearer(admin_token),
            )
            assert resp.status_code == 422, resp.text
        finally:
            for em in extra:
                user = (await db_session.execute(select(User).where(User.id == em))).scalar_one()
                await delete_user(db_session, user.email)
        # Nothing persisted, status untouched.
        detail = (await client.get(f"/api/v1/problems/{body['id']}", headers=bearer(token))).json()
        assert detail["status"] == "APPROVED"
        assert detail["assignment"] is None
    finally:
        await delete_user(db_session, email)
        await delete_user(db_session, admin_email)
        await delete_user(db_session, ghost_email)
        await delete_user(db_session, full_email)
        await delete_user(db_session, dead_email)
        await delete_user(db_session, reporter_email)


@pytest.mark.asyncio
async def test_bad_mentor_rejected_and_rolled_back(client, db_session):
    email, token, _ = await make_user(client)
    admin_email, admin_token = await make_admin(client, db_session)
    ghost_email, _, _ = await make_mentor(
        client, db_session, skills=[("Linux", ProficiencyLevel.EXPERT)],
        specialization="Networks", availability=AvailabilityStatus.UNAVAILABLE)
    try:
        body = await create(client, token)
        await approve(client, admin_token, body["id"])
        options, _ = await _rec_ids(client, admin_token, body["id"])
        team_ids = [m["user_id"] for m in options[0]["members"]]
        ghost_id = str((await db_session.execute(
            select(User).where(User.email == ghost_email.lower()))).scalar_one().id)
        async def _wl(uid):
            user = (
                await db_session.execute(
                    select(User)
                    .options(selectinload(User.student_profile), selectinload(User.faculty_profile))
                    .where(User.id == uid)
                )
            ).scalar_one()
            profile = user.student_profile or user.faculty_profile
            assert profile is not None
            return profile.current_workload

        before = {mid: await _wl(mid) for mid in team_ids}
        resp = await client.post(
            f"/api/v1/admin/problems/{body['id']}/assign",
            json={"solver_user_ids": team_ids, "mentor_user_id": ghost_id,
                  "team_override_reason": "t", "mentor_override_reason": "m"},
            headers=bearer(admin_token),
        )
        assert resp.status_code == 422, resp.text
        for mid in team_ids:
            assert await _wl(mid) == before[mid]
        count = (await db_session.execute(
            select(func.count()).select_from(ProblemAssignment)
            .where(ProblemAssignment.problem_id == body["id"]))).scalar_one()
        assert count == 0
        detail = (await client.get(f"/api/v1/problems/{body['id']}", headers=bearer(token))).json()
        assert detail["status"] == "APPROVED"
    finally:
        await delete_user(db_session, email)
        await delete_user(db_session, admin_email)
        await delete_user(db_session, ghost_email)


@pytest.mark.asyncio
async def test_duplicate_member_assignment_rejected(client, db_session):
    email_a, token_a, _ = await make_user(client)
    email_b, token_b, _ = await make_user(client)
    admin_email, admin_token = await make_admin(client, db_session)
    try:
        a_body = await create(client, token_a)
        b_body = await create(client, token_b)
        # Canonical can be assigned normally.
        await approve(client, admin_token, a_body["id"])
        options, mentors = await _rec_ids(client, admin_token, a_body["id"])
        resp = await client.post(
            f"/api/v1/admin/problems/{a_body['id']}/assign",
            json={"solver_user_ids": [m["user_id"] for m in options[0]["members"]],
                  "mentor_user_id": mentors[0]["mentor_user_id"],
                  "team_recommendation_id": options[0]["id"],
                  "mentor_recommendation_id": mentors[0]["id"]},
            headers=bearer(admin_token),
        )
        assert resp.status_code == 201, resp.text
        # Confirm B as duplicate of A, then try assigning B.
        cand = next(
            c for c in (await client.get(
                f"/api/v1/problems/{b_body['id']}/duplicates", headers=bearer(token_b))).json()["candidates"]
            if c["candidate"]["id"] == a_body["id"]
        )
        assert (await client.post(
            f"/api/v1/admin/duplicate-candidates/{cand['id']}/confirm",
            json={}, headers=bearer(admin_token))).status_code == 200
        bad = await client.post(
            f"/api/v1/admin/problems/{b_body['id']}/assign",
            json={"solver_user_ids": [m["user_id"] for m in options[0]["members"]],
                  "mentor_user_id": mentors[0]["mentor_user_id"]},
            headers=bearer(admin_token),
        )
        assert bad.status_code == 409, bad.text
        assert a_body["ticket_number"] in bad.json()["detail"]
    finally:
        await delete_user(db_session, email_a)
        await delete_user(db_session, email_b)
        await delete_user(db_session, admin_email)


@pytest.mark.asyncio
async def test_assign_requires_approved(client, db_session):
    email, token, _ = await make_user(client)
    admin_email, admin_token = await make_admin(client, db_session)
    try:
        body = await create(client, token)
        options, mentors = await _rec_ids(client, admin_token, body["id"])
        resp = await client.post(
            f"/api/v1/admin/problems/{body['id']}/assign",
            json={"solver_user_ids": [m["user_id"] for m in options[0]["members"]],
                  "mentor_user_id": mentors[0]["mentor_user_id"]},
            headers=bearer(admin_token),
        )
        assert resp.status_code == 409, resp.text
    finally:
        await delete_user(db_session, email)
        await delete_user(db_session, admin_email)


@pytest.mark.asyncio
async def test_idempotent_retry_no_double_increment(client, db_session):
    email, token, _ = await make_user(client)
    admin_email, admin_token = await make_admin(client, db_session)
    try:
        body = await create(client, token)
        await approve(client, admin_token, body["id"])
        options, mentors = await _rec_ids(client, admin_token, body["id"])
        payload = {
            "solver_user_ids": [m["user_id"] for m in options[0]["members"]],
            "mentor_user_id": mentors[0]["mentor_user_id"],
            "team_recommendation_id": options[0]["id"],
            "mentor_recommendation_id": mentors[0]["id"],
        }
        first = await client.post(
            f"/api/v1/admin/problems/{body['id']}/assign", json=payload, headers=bearer(admin_token))
        assert first.status_code == 201, first.text

        async def wl(uid):
            user = (
                await db_session.execute(
                    select(User)
                    .options(selectinload(User.student_profile), selectinload(User.faculty_profile))
                    .where(User.id == uid)
                )
            ).scalar_one()
            profile = user.student_profile or user.faculty_profile
            assert profile is not None
            return profile.current_workload

        workloads_after_first = {mid: await wl(mid) for mid in payload["solver_user_ids"]}
        workloads_after_first[payload["mentor_user_id"]] = await wl(payload["mentor_user_id"])
        second = await client.post(
            f"/api/v1/admin/problems/{body['id']}/assign", json=payload, headers=bearer(admin_token))
        assert second.status_code == 200, second.text
        assert second.json()["idempotent_replay"] is True
        assert second.json()["id"] == first.json()["id"]
        for uid, before in workloads_after_first.items():
            assert await wl(uid) == before
        count = (await db_session.execute(
            select(func.count()).select_from(ProblemAssignment)
            .where(ProblemAssignment.problem_id == body["id"],
                   ProblemAssignment.status == "ACTIVE"))).scalar_one()
        assert count == 1
    finally:
        await delete_user(db_session, email)
        await delete_user(db_session, admin_email)


@pytest.mark.asyncio
async def test_concurrent_assign_single_winner(client, db_session):
    email, token, _ = await make_user(client)
    admin_email, admin_token = await make_admin(client, db_session)
    try:
        body = await create(client, token)
        await approve(client, admin_token, body["id"])
        options, mentors = await _rec_ids(client, admin_token, body["id"])
        payload = {
            "solver_user_ids": [m["user_id"] for m in options[0]["members"]],
            "mentor_user_id": mentors[0]["mentor_user_id"],
            "team_recommendation_id": options[0]["id"],
            "mentor_recommendation_id": mentors[0]["id"],
        }

        async def attempt():
            return await client.post(
                f"/api/v1/admin/problems/{body['id']}/assign", json=payload,
                headers=bearer(admin_token))

        async def wl(uid):
            user = (
                await db_session.execute(
                    select(User)
                    .options(selectinload(User.student_profile), selectinload(User.faculty_profile))
                    .where(User.id == uid)
                )
            ).scalar_one()
            profile = user.student_profile or user.faculty_profile
            assert profile is not None
            return profile.current_workload

        before_wl = {uid: await wl(uid) for uid in payload["solver_user_ids"] + [payload["mentor_user_id"]]}
        first, second = await asyncio.gather(attempt(), attempt())
        assert {first.status_code, second.status_code} <= {200, 201, 409}
        assert {first.status_code, second.status_code} & {200, 201}
        count = (await db_session.execute(
            select(func.count()).select_from(ProblemAssignment)
            .where(ProblemAssignment.problem_id == body["id"],
                   ProblemAssignment.status == "ACTIVE"))).scalar_one()
        assert count == 1
        # Exactly one increment per person across both racing requests.
        for uid, before in before_wl.items():
            assert await wl(uid) == before + 1
    finally:
        await delete_user(db_session, email)
        await delete_user(db_session, admin_email)


# ---------------- Reassign / cancel ----------------


async def _assign_seed_team(client, admin_token, problem_id):
    options, mentors = await _rec_ids(client, admin_token, problem_id)
    resp = await client.post(
        f"/api/v1/admin/problems/{problem_id}/assign",
        json={"solver_user_ids": [m["user_id"] for m in options[0]["members"]],
              "mentor_user_id": mentors[0]["mentor_user_id"],
              "team_recommendation_id": options[0]["id"],
              "mentor_recommendation_id": mentors[0]["id"]},
        headers=bearer(admin_token),
    )
    assert resp.status_code == 201, resp.text
    return resp.json(), options, mentors


@pytest.mark.asyncio
async def test_reassign_swaps_with_correct_workloads(client, db_session):
    email, token, _ = await make_user(client)
    admin_email, admin_token = await make_admin(client, db_session)
    try:
        body = await create(client, token)
        await approve(client, admin_token, body["id"])
        assigned, _, mentors = await _assign_seed_team(client, admin_token, body["id"])
        old_members = [m["user_id"] for m in assigned["team"]["members"]]
        # Extra solver created after assignment: guaranteed not a member.
        extra_email, _, extra_id = await make_solver(
            client, db_session, skills=[("Linux", ProficiencyLevel.ADVANCED)])
        keep = old_members[0]
        new_team = [keep, extra_id]

        async def wl(uid):
            user = (
                await db_session.execute(
                    select(User)
                    .options(selectinload(User.student_profile), selectinload(User.faculty_profile))
                    .where(User.id == uid)
                )
            ).scalar_one()
            profile = user.student_profile or user.faculty_profile
            assert profile is not None
            return profile.current_workload

        before = {uid: await wl(uid) for uid in old_members + [extra_id]}
        resp = await client.post(
            f"/api/v1/admin/problems/{body['id']}/assignment/reassign",
            json={"solver_user_ids": new_team, "mentor_user_id": assigned["mentor"]["user_id"] or mentors[0]["mentor_user_id"],
                  "reason": "Swap in Linux specialist"},
            headers=bearer(admin_token),
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["status"] == "ACTIVE"
        assert data["team_was_overridden"] is True
        # Removed member released, added incremented, staying untouched.
        removed = [m for m in old_members if m not in new_team]
        assert removed
        for mid in removed:
            assert await wl(mid) == before[mid] - 1
        assert await wl(extra_id) == before[extra_id] + 1
        assert await wl(keep) == before[keep]
        history = (await client.get(
            f"/api/v1/admin/problems/{body['id']}/assignment", headers=bearer(admin_token))).json()
        assert len(history["history"]) == 2
        assert {h["status"] for h in history["history"]} == {"ACTIVE", "REASSIGNED"}
        detail = (await client.get(f"/api/v1/problems/{body['id']}", headers=bearer(token))).json()
        assert detail["status"] == "ASSIGNED"
        # Identical reassign refused.
        assert (await client.post(
            f"/api/v1/admin/problems/{body['id']}/assignment/reassign",
            json={"solver_user_ids": new_team, "mentor_user_id": data["mentor"]["user_id"],
                  "reason": "no-op"},
            headers=bearer(admin_token))).status_code == 409
    finally:
        await delete_user(db_session, email)
        await delete_user(db_session, admin_email)
        await delete_user(db_session, extra_email)


@pytest.mark.asyncio
async def test_cancel_releases_once_and_returns_to_approved(client, db_session):
    email, token, _ = await make_user(client)
    admin_email, admin_token = await make_admin(client, db_session)
    try:
        body = await create(client, token)
        await approve(client, admin_token, body["id"])
        assigned, _, _ = await _assign_seed_team(client, admin_token, body["id"])
        member_ids = [m["user_id"] for m in assigned["team"]["members"]]
        mentor_id = assigned["mentor"]["user_id"]

        async def wl(uid):
            user = (
                await db_session.execute(
                    select(User)
                    .options(selectinload(User.student_profile), selectinload(User.faculty_profile))
                    .where(User.id == uid)
                )
            ).scalar_one()
            profile = user.student_profile or user.faculty_profile
            assert profile is not None
            return profile.current_workload

        before = {uid: await wl(uid) for uid in member_ids + [mentor_id]}
        resp = await client.post(
            f"/api/v1/admin/problems/{body['id']}/assignment/cancel",
            json={"reason": "Reporter withdrew context"},
            headers=bearer(admin_token),
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "CANCELLED"
        for uid in member_ids + [mentor_id]:
            assert await wl(uid) == before[uid] - 1
        detail = (await client.get(f"/api/v1/problems/{body['id']}", headers=bearer(token))).json()
        assert detail["status"] == "APPROVED"
        assert detail["assignment"] is None
        # Double cancel refused (no double release).
        assert (await client.post(
            f"/api/v1/admin/problems/{body['id']}/assignment/cancel",
            json={"reason": "again"},
            headers=bearer(admin_token))).status_code == 409
        for uid in member_ids + [mentor_id]:
            assert await wl(uid) == before[uid] - 1
        # Re-assign after cancel works (status is already APPROVED).
        options, mentors = await _rec_ids(client, admin_token, body["id"])
        again = await client.post(
            f"/api/v1/admin/problems/{body['id']}/assign",
            json={"solver_user_ids": [m["user_id"] for m in options[0]["members"]],
                  "mentor_user_id": mentors[0]["mentor_user_id"],
                  "team_recommendation_id": options[0]["id"],
                  "mentor_recommendation_id": mentors[0]["id"]},
            headers=bearer(admin_token),
        )
        assert again.status_code in (200, 201), again.text
    finally:
        await delete_user(db_session, email)
        await delete_user(db_session, admin_email)


# ---------------- Access ----------------


@pytest.mark.asyncio
async def test_assignment_access_rules(client, db_session):
    email, token, _ = await make_user(client)
    admin_email, admin_token = await make_admin(client, db_session)
    try:
        body = await create(client, token)
        await approve(client, admin_token, body["id"])
        assigned, _, _ = await _assign_seed_team(client, admin_token, body["id"])
        # Outsiders are created AFTER the assignment so they cannot be members.
        outsider_email, outsider_token, _ = await make_solver(client, db_session)
        other_mentor_email, other_mentor_token, _ = await make_mentor(
            client, db_session, specialization="Other")
        other_mentor = (await db_session.execute(
            select(User).where(User.email == other_mentor_email.lower()))).scalar_one()
        assert str(other_mentor.id) != assigned["mentor"]["user_id"]
        # Non-member solver denied.
        assert (await client.get(
            f"/api/v1/problems/{body['id']}", headers=bearer(outsider_token))).status_code == 404
        # Other mentor denied.
        other_login = other_mentor_token
        assert (await client.get(
            f"/api/v1/problems/{body['id']}", headers=bearer(other_login))).status_code == 404
        assert (await client.get(
            "/api/v1/problems/assigned/me", headers=bearer(outsider_token))).status_code == 200
        assert (await client.get(
            "/api/v1/problems/assigned/me", headers=bearer(outsider_token))).json() == []
        assert (await client.get(
            "/api/v1/problems/mentored/me", headers=bearer(other_login))).json() == []
    finally:
        await delete_user(db_session, email)
        await delete_user(db_session, admin_email)
        await delete_user(db_session, outsider_email)
        await delete_user(db_session, other_mentor_email)


@pytest.mark.asyncio
async def test_assigned_member_and_mentor_can_view(client, db_session):
    email, token, _ = await make_user(client)
    admin_email, admin_token = await make_admin(client, db_session)
    member_email, member_token, member_id = await make_solver(
        client, db_session, skills=[("Linux", ProficiencyLevel.EXPERT)])
    mentor_email, mentor_token, mentor_id = await make_mentor(
        client, db_session, skills=[("Linux", ProficiencyLevel.EXPERT)],
        specialization="Access Test Networks")
    try:
        body = await create(client, token)
        await approve(client, admin_token, body["id"])
        options, _ = await _rec_ids(client, admin_token, body["id"])
        mentor_user = (await db_session.execute(
            select(User).where(User.id == mentor_id))).scalar_one()
        # Assign the dedicated solver + mentor via documented manual overrides.
        resp = await client.post(
            f"/api/v1/admin/problems/{body['id']}/assign",
            json={"solver_user_ids": [member_id, options[0]["members"][0]["user_id"]]
                  if member_id not in [m["user_id"] for m in options[0]["members"]]
                  else [m["user_id"] for m in options[0]["members"]],
                  "mentor_user_id": mentor_id,
                  "team_override_reason": "Include dedicated solver for access test",
                  "mentor_override_reason": "Use dedicated mentor for access test"},
            headers=bearer(admin_token),
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["team_was_overridden"] is True
        assert resp.json()["mentor_was_overridden"] is True
        member_login = member_token
        detail = await client.get(f"/api/v1/problems/{body['id']}", headers=bearer(member_login))
        assert detail.status_code == 200, detail.text
        assert detail.json()["assignment"]["team"]["members"]
        assert "email" not in detail.text
        assigned_list = (await client.get(
            "/api/v1/problems/assigned/me", headers=bearer(member_login))).json()
        assert [p["id"] for p in assigned_list] == [body["id"]]
        assert assigned_list[0]["mentor_name"] == mentor_user.full_name
        mentor_login = mentor_token
        mdetail = await client.get(f"/api/v1/problems/{body['id']}", headers=bearer(mentor_login))
        assert mdetail.status_code == 200, mdetail.text
        mentored = (await client.get(
            "/api/v1/problems/mentored/me", headers=bearer(mentor_login))).json()
        assert [p["id"] for p in mentored] == [body["id"]]
        # Reporter sees safe assignment summary.
        rep = (await client.get(f"/api/v1/problems/{body['id']}", headers=bearer(token))).json()
        assert rep["assignment"]["team"]["members"]
        assert all(m["user_id"] is None for m in rep["assignment"]["team"]["members"])
        assert rep["assignment"]["mentor"]["name"] == mentor_user.full_name
        assert "example.com" not in str(rep["assignment"])
    finally:
        await delete_user(db_session, email)
        await delete_user(db_session, admin_email)
        await delete_user(db_session, member_email)
        await delete_user(db_session, mentor_email)
