"""Step 11 tests: notification hooks, listing, read states, IDOR."""

from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.core.enums import AvailabilityStatus, UserRole
from app.main import app
from app.models.faculty_profile import FacultyProfile
from app.models.student_profile import StudentProfile
from app.models.user import User

PASSWORD = "Step11N_Test_pass"


def unique_email(prefix: str = "n11") -> str:
    return f"{prefix}_{uuid4().hex[:10]}@example.com"


NETWORK_PAYLOAD = {
    "title": "Campus WiFi network keeps disconnecting in the computer lab",
    "description": "Students cannot access the internet in the computer lab because the WiFi "
    "network and Linux lab systems keep disconnecting during practical hours. "
    "The network switch may need inspection.",
    "location_text": "Computer Lab",
}

SOLUTION_PAYLOAD = {
    "solution_summary": "Replaced the faulty lab switch and verified connectivity across the lab",
    "root_cause": "An aging access switch was dropping packets under load in the computer lab",
    "work_performed": "Diagnosed port errors, replaced the switch, re-terminated two uplinks, "
    "and load-tested the lab network through a full practical session.",
}


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def register(ac, email, role="REPORTER"):
    return await ac.post(
        "/api/v1/auth/register",
        json={"full_name": f"N11 {role}", "email": email, "password": PASSWORD, "role": role},
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


async def make_solver(ac, session):
    email, token, user_id = await make_user(ac, role="SOLVER")
    result = await session.execute(select(User).where(User.email == email.lower()))
    user = result.scalar_one()
    session.add(
        StudentProfile(
            user_id=user.id,
            student_identifier=f"STN{uuid4().hex[:8]}",
            department="Computer Science & Engineering",
            academic_year=3,
            availability_status=AvailabilityStatus.AVAILABLE,
            current_workload=0,
            max_workload=5,
        )
    )
    await session.commit()
    return email, token, user_id


async def make_mentor(ac, session):
    email, _, _ = await make_user(ac, role="SOLVER")
    result = await session.execute(select(User).where(User.email == email.lower()))
    user = result.scalar_one()
    user.role = UserRole.MENTOR
    session.add(
        FacultyProfile(
            user_id=user.id,
            employee_identifier=f"FCN{uuid4().hex[:8]}",
            department="Computer Science & Engineering",
            designation="Assistant Professor",
            specialization="Networks",
            availability_status=AvailabilityStatus.AVAILABLE,
            current_workload=0,
            max_workload=5,
        )
    )
    await session.commit()
    token = (await login(ac, email)).json()["access_token"]
    result = await session.execute(select(User).where(User.email == email.lower()))
    return email, token, str(result.scalar_one().id)


async def setup_assigned(ac, session):
    rep_email, rep_token, _ = await make_user(ac)
    s1_email, s1_token, s1_id = await make_solver(ac, session)
    s2_email, s2_token, s2_id = await make_solver(ac, session)
    m_email, m_token, m_id = await make_mentor(ac, session)
    admin_email, admin_token = await make_admin(ac, session)
    created = await ac.post("/api/v1/problems", json=NETWORK_PAYLOAD, headers=bearer(rep_token))
    assert created.status_code == 201, created.text
    pid = created.json()["id"]
    await ac.post(f"/api/v1/admin/problems/{pid}/review/start", headers=bearer(admin_token))
    await ac.post(f"/api/v1/admin/problems/{pid}/approve", json={}, headers=bearer(admin_token))
    assign = await ac.post(
        f"/api/v1/admin/problems/{pid}/assign",
        json={
            "solver_user_ids": [s1_id, s2_id],
            "mentor_user_id": m_id,
            "team_name": "Notify Crew",
            "team_override_reason": "Manual team for notification tests",
            "mentor_override_reason": "Manual mentor for notification tests",
        },
        headers=bearer(admin_token),
    )
    assert assign.status_code == 201, assign.text
    return {
        "pid": pid,
        "rep": (rep_email, rep_token),
        "s1": (s1_email, s1_token, s1_id),
        "s2": (s2_email, s2_token, s2_id),
        "mentor": (m_email, m_token, m_id),
        "admin": (admin_email, admin_token),
    }


async def cleanup(session, ctx):
    for key in ("rep", "admin"):
        await delete_user(session, ctx[key][0])


async def types_for(ac, token, unread_only=False):
    params = "?unread_only=true&limit=100" if unread_only else "?limit=100"
    body = (await ac.get(f"/api/v1/notifications{params}", headers=bearer(token))).json()
    return body["items"]


@pytest.mark.asyncio
async def test_assignment_notifications(client, db_session):
    ctx = await setup_assigned(client, db_session)
    try:
        pid = ctx["pid"]
        s1_types = [n["type"] for n in await types_for(client, ctx["s1"][1])]
        assert "TEAM_ASSIGNED" in s1_types
        team_notif = next(n for n in await types_for(client, ctx["s1"][1]) if n["type"] == "TEAM_ASSIGNED")
        assert team_notif["problem_id"] == pid
        assert team_notif["read_at"] is None
        mentor_types = [n["type"] for n in await types_for(client, ctx["mentor"][1])]
        assert "MENTOR_ASSIGNED" in mentor_types
        # Reporter gets no assignment spam.
        rep_types = [n["type"] for n in await types_for(client, ctx["rep"][1])]
        assert "TEAM_ASSIGNED" not in rep_types
    finally:
        await cleanup(db_session, ctx)


@pytest.mark.asyncio
async def test_task_assignment_and_blocked_notifications(client, db_session):
    ctx = await setup_assigned(client, db_session)
    try:
        pid = ctx["pid"]
        created = await client.post(
            f"/api/v1/problems/{pid}/tasks",
            json={"title": "Check ports", "assigned_to_user_id": ctx["s2"][2]},
            headers=bearer(ctx["mentor"][1]),
        )
        assert created.status_code == 201
        tid = created.json()["id"]
        s2_types = [n["type"] for n in await types_for(client, ctx["s2"][1])]
        assert "TASK_ASSIGNED" in s2_types
        # Blocker notifies the rest of the team + mentor, not the actor.
        await client.patch(
            f"/api/v1/problems/{pid}/tasks/{tid}", json={"status": "IN_PROGRESS"},
            headers=bearer(ctx["s2"][1]),
        )
        blocked = await client.patch(
            f"/api/v1/problems/{pid}/tasks/{tid}",
            json={"status": "BLOCKED", "blocker_reason": "No spare switch"},
            headers=bearer(ctx["s2"][1]),
        )
        assert blocked.status_code == 200
        s1_types = [n["type"] for n in await types_for(client, ctx["s1"][1])]
        assert "TASK_BLOCKED" in s1_types
        mentor_types = [n["type"] for n in await types_for(client, ctx["mentor"][1])]
        assert "TASK_BLOCKED" in mentor_types
        s2_blocked = [
            n for n in await types_for(client, ctx["s2"][1])
            if n["type"] == "TASK_BLOCKED" and n.get("related_entity_id") == tid
        ]
        assert s2_blocked == []
    finally:
        await cleanup(db_session, ctx)


async def _drive_to_close(ac, ctx):
    pid = ctx["pid"]
    for title in ("Replace the switch", "Test every terminal"):
        created = await ac.post(
            f"/api/v1/problems/{pid}/tasks", json={"title": title}, headers=bearer(ctx["s1"][1])
        )
        tid = created.json()["id"]
        for target in ("IN_PROGRESS", "DONE"):
            await ac.patch(
                f"/api/v1/problems/{pid}/tasks/{tid}", json={"status": target},
                headers=bearer(ctx["s1"][1]),
            )
    sub = (
        await ac.post(f"/api/v1/problems/{pid}/solutions", json=SOLUTION_PAYLOAD, headers=bearer(ctx["s1"][1]))
    ).json()
    await ac.post(
        f"/api/v1/problems/{pid}/solutions/{sub['id']}/review",
        json={"decision": "APPROVED"},
        headers=bearer(ctx["mentor"][1]),
    )
    await ac.post(
        f"/api/v1/problems/{pid}/verifications", json={"decision": "RESOLVED"},
        headers=bearer(ctx["rep"][1]),
    )
    await ac.post(f"/api/v1/admin/problems/{pid}/close", json={}, headers=bearer(ctx["admin"][1]))


@pytest.mark.asyncio
async def test_step11_lifecycle_notifications(client, db_session):
    ctx = await setup_assigned(client, db_session)
    try:
        await _drive_to_close(client, ctx)
        mentor_types = [n["type"] for n in await types_for(client, ctx["mentor"][1])]
        assert "SOLUTION_SUBMITTED" in mentor_types
        rep_types = [n["type"] for n in await types_for(client, ctx["rep"][1])]
        assert "REPORTER_VERIFICATION_REQUIRED" in rep_types
        assert "PROBLEM_CLOSED" in rep_types
        s1_types = [n["type"] for n in await types_for(client, ctx["s1"][1])]
        assert "PROBLEM_RESOLVED" in s1_types
        assert "PROBLEM_CLOSED" in s1_types
    finally:
        await cleanup(db_session, ctx)


@pytest.mark.asyncio
async def test_changes_requested_and_rejection_notifications(client, db_session):
    ctx = await setup_assigned(client, db_session)
    try:
        pid = ctx["pid"]
        for title in ("Replace the switch", "Test every terminal"):
            created = await client.post(
                f"/api/v1/problems/{pid}/tasks", json={"title": title}, headers=bearer(ctx["s1"][1])
            )
            tid = created.json()["id"]
            for target in ("IN_PROGRESS", "DONE"):
                await client.patch(
                    f"/api/v1/problems/{pid}/tasks/{tid}", json={"status": target},
                    headers=bearer(ctx["s1"][1]),
                )
        sub = (
            await client.post(
                f"/api/v1/problems/{pid}/solutions", json=SOLUTION_PAYLOAD, headers=bearer(ctx["s1"][1])
            )
        ).json()
        await client.post(
            f"/api/v1/problems/{pid}/solutions/{sub['id']}/review",
            json={"decision": "CHANGES_REQUESTED", "review_comment": "Add photos."},
            headers=bearer(ctx["mentor"][1]),
        )
        s1_types = [n["type"] for n in await types_for(client, ctx["s1"][1])]
        assert "CHANGES_REQUESTED" in s1_types
        sub2 = (
            await client.post(
                f"/api/v1/problems/{pid}/solutions", json=SOLUTION_PAYLOAD, headers=bearer(ctx["s1"][1])
            )
        ).json()
        await client.post(
            f"/api/v1/problems/{pid}/solutions/{sub2['id']}/review",
            json={"decision": "APPROVED"},
            headers=bearer(ctx["mentor"][1]),
        )
        await client.post(
            f"/api/v1/problems/{pid}/verifications",
            json={"decision": "NOT_RESOLVED", "reason": "Still down."},
            headers=bearer(ctx["rep"][1]),
        )
        mentor_types = [n["type"] for n in await types_for(client, ctx["mentor"][1])]
        assert "REPORTER_REJECTED_RESOLUTION" in mentor_types
    finally:
        await cleanup(db_session, ctx)


@pytest.mark.asyncio
async def test_list_unread_read_flow(client, db_session):
    ctx = await setup_assigned(client, db_session)
    try:
        token = ctx["s1"][1]
        count = (await client.get("/api/v1/notifications/unread-count", headers=bearer(token))).json()
        assert count["unread_count"] >= 1
        page = (await client.get("/api/v1/notifications?limit=1&offset=0", headers=bearer(token))).json()
        assert page["total"] >= 1
        assert len(page["items"]) == 1
        first_id = page["items"][0]["id"]
        marked = (
            await client.patch(f"/api/v1/notifications/{first_id}/read", headers=bearer(token))
        ).json()
        assert marked["read_at"] is not None
        unread = (
            await client.get("/api/v1/notifications?unread_only=true&limit=100", headers=bearer(token))
        ).json()
        assert all(n["read_at"] is None for n in unread["items"])
        assert all(n["id"] != first_id for n in unread["items"])
        all_read = (await client.post("/api/v1/notifications/read-all", headers=bearer(token))).json()
        assert all_read["marked_read"] >= 0
        count = (await client.get("/api/v1/notifications/unread-count", headers=bearer(token))).json()
        assert count["unread_count"] == 0
    finally:
        await cleanup(db_session, ctx)


@pytest.mark.asyncio
async def test_notification_idor(client, db_session):
    ctx = await setup_assigned(client, db_session)
    try:
        s1_items = await types_for(client, ctx["s1"][1])
        assert s1_items
        victim_id = s1_items[0]["id"]
        # Another user cannot read, mark, or even see it.
        resp = await client.patch(f"/api/v1/notifications/{victim_id}/read", headers=bearer(ctx["s2"][1]))
        assert resp.status_code == 404, resp.text
        s2_ids = {n["id"] for n in await types_for(client, ctx["s2"][1])}
        assert victim_id not in s2_ids
        outsider_email, outsider_token, _ = await make_user(client, role="SOLVER")
        try:
            resp = await client.patch(
                f"/api/v1/notifications/{victim_id}/read", headers=bearer(outsider_token)
            )
            assert resp.status_code == 404, resp.text
            count = (
                await client.get("/api/v1/notifications/unread-count", headers=bearer(outsider_token))
            ).json()
            assert count["unread_count"] == 0
        finally:
            await delete_user(db_session, outsider_email)
    finally:
        await cleanup(db_session, ctx)
