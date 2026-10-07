"""Step 10 tests: workspace tasks, milestones, progress, files, discussion, access."""

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

PASSWORD = "Step10_Test_pass"


def unique_email(prefix: str = "w10") -> str:
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


async def register(ac, email, role="REPORTER"):
    return await ac.post(
        "/api/v1/auth/register",
        json={"full_name": f"W10 {role}", "email": email, "password": PASSWORD, "role": role},
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
            student_identifier=f"STX{uuid4().hex[:8]}",
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
            employee_identifier=f"FCX{uuid4().hex[:8]}",
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
    """Reporter + 2 solvers + mentor + admin, problem approved and assigned."""
    rep_email, rep_token, _ = await make_user(ac)
    s1_email, s1_token, s1_id = await make_solver(ac, session)
    s2_email, s2_token, s2_id = await make_solver(ac, session)
    m_email, m_token, m_id = await make_mentor(ac, session)
    admin_email, admin_token = await make_admin(ac, session)
    created = await ac.post("/api/v1/problems", json=NETWORK_PAYLOAD, headers=bearer(rep_token))
    assert created.status_code == 201, created.text
    pid = created.json()["id"]
    start = await ac.post(f"/api/v1/admin/problems/{pid}/review/start", headers=bearer(admin_token))
    assert start.status_code == 200, start.text
    ok = await ac.post(f"/api/v1/admin/problems/{pid}/approve", json={}, headers=bearer(admin_token))
    assert ok.status_code == 200, ok.text
    assign = await ac.post(
        f"/api/v1/admin/problems/{pid}/assign",
        json={
            "solver_user_ids": [s1_id, s2_id],
            "mentor_user_id": m_id,
            "team_name": "Net Fixers",
            "team_override_reason": "Manual team for workspace tests",
            "mentor_override_reason": "Manual mentor for workspace tests",
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
    # Only reporters/admins are safe to delete: solver/mentor rows are
    # referenced by NOT NULL recommendation FKs. Deleting the reporter
    # cascades their problems, assignments, teams, and workspace rows.
    for key in ("rep", "admin"):
        await delete_user(session, ctx[key][0])


async def _cleanup_users(session, emails):
    for email in emails:
        result = await session.execute(select(User).where(User.email == email.lower()))
        user = result.scalar_one_or_none()
        if user is not None:
            await session.delete(user)
    await session.commit()


# ---------------- tasks ----------------


@pytest.mark.asyncio
async def test_member_create_self_assigned_task(client, db_session):
    ctx = await setup_assigned(client, db_session)
    try:
        pid = ctx["pid"]
        s1_token = ctx["s1"][1]
        s1_id = ctx["s1"][2]
        resp = await client.post(
            f"/api/v1/problems/{pid}/tasks",
            json={"title": "Inspect the lab switch", "assigned_to_user_id": s1_id},
            headers=bearer(s1_token),
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["status"] == "TODO"
        assert body["assigned_to_user_id"] == s1_id
        assert body["assignee_name"] is not None
    finally:
        await cleanup(db_session, ctx)


@pytest.mark.asyncio
async def test_member_cannot_peer_assign(client, db_session):
    ctx = await setup_assigned(client, db_session)
    try:
        pid = ctx["pid"]
        resp = await client.post(
            f"/api/v1/problems/{pid}/tasks",
            json={"title": "Peer task", "assigned_to_user_id": ctx["s2"][2]},
            headers=bearer(ctx["s1"][1]),
        )
        assert resp.status_code == 403, resp.text
    finally:
        await cleanup(db_session, ctx)


@pytest.mark.asyncio
async def test_mentor_can_assign_any_member(client, db_session):
    ctx = await setup_assigned(client, db_session)
    try:
        pid = ctx["pid"]
        resp = await client.post(
            f"/api/v1/problems/{pid}/tasks",
            json={"title": "Mentor assigned", "assigned_to_user_id": ctx["s2"][2]},
            headers=bearer(ctx["mentor"][1]),
        )
        assert resp.status_code == 201, resp.text
    finally:
        await cleanup(db_session, ctx)


@pytest.mark.asyncio
async def test_task_assignee_validations(client, db_session):
    ctx = await setup_assigned(client, db_session)
    try:
        pid = ctx["pid"]
        outsider_email, outsider_token, outsider_id = await make_solver(client, db_session)
        ctx["extra"] = (outsider_email, outsider_token, outsider_id)
        # Non-team solver rejected.
        resp = await client.post(
            f"/api/v1/problems/{pid}/tasks",
            json={"title": "Outsider task", "assigned_to_user_id": outsider_id},
            headers=bearer(ctx["mentor"][1]),
        )
        assert resp.status_code == 422, resp.text
        # Mentor cannot be an assignee.
        resp = await client.post(
            f"/api/v1/problems/{pid}/tasks",
            json={"title": "Mentor task", "assigned_to_user_id": ctx["mentor"][2]},
            headers=bearer(ctx["admin"][1]),
        )
        assert resp.status_code == 422, resp.text
        # Reporter cannot be an assignee.
        rep_id = (
            await db_session.execute(select(User).where(User.email == ctx["rep"][0].lower()))
        ).scalar_one().id
        resp = await client.post(
            f"/api/v1/problems/{pid}/tasks",
            json={"title": "Reporter task", "assigned_to_user_id": str(rep_id)},
            headers=bearer(ctx["admin"][1]),
        )
        assert resp.status_code == 422, resp.text
    finally:
        await cleanup(db_session, ctx)


@pytest.mark.asyncio
async def test_task_status_transitions(client, db_session):
    ctx = await setup_assigned(client, db_session)
    try:
        pid = ctx["pid"]
        tok = ctx["s1"][1]
        created = await client.post(
            f"/api/v1/problems/{pid}/tasks", json={"title": "Transition me"}, headers=bearer(tok)
        )
        assert created.status_code == 201, created.text
        tid = created.json()["id"]
        # TODO -> DONE directly is invalid.
        bad = await client.patch(
            f"/api/v1/problems/{pid}/tasks/{tid}", json={"status": "DONE"}, headers=bearer(tok)
        )
        assert bad.status_code == 409, bad.text
        # TODO -> IN_PROGRESS starts real work.
        started = await client.patch(
            f"/api/v1/problems/{pid}/tasks/{tid}", json={"status": "IN_PROGRESS"}, headers=bearer(tok)
        )
        assert started.status_code == 200, started.text
        assert started.json()["started_at"] is not None
        detail = (await client.get(f"/api/v1/problems/{pid}", headers=bearer(tok))).json()
        assert detail["status"] == "IN_PROGRESS"
        # IN_PROGRESS -> BLOCKED requires a reason.
        blocked = await client.patch(
            f"/api/v1/problems/{pid}/tasks/{tid}", json={"status": "BLOCKED"}, headers=bearer(tok)
        )
        assert blocked.status_code == 422, blocked.text
        blocked = await client.patch(
            f"/api/v1/problems/{pid}/tasks/{tid}",
            json={"status": "BLOCKED", "blocker_reason": "Waiting on replacement switch"},
            headers=bearer(tok),
        )
        assert blocked.status_code == 200, blocked.text
        assert blocked.json()["blocker_reason"] == "Waiting on replacement switch"
        # BLOCKED -> IN_PROGRESS keeps the reason (never silently lost).
        back = await client.patch(
            f"/api/v1/problems/{pid}/tasks/{tid}", json={"status": "IN_PROGRESS"}, headers=bearer(tok)
        )
        assert back.status_code == 200, back.text
        assert back.json()["blocker_reason"] == "Waiting on replacement switch"
        # Complete it.
        done = await client.patch(
            f"/api/v1/problems/{pid}/tasks/{tid}", json={"status": "DONE"}, headers=bearer(tok)
        )
        assert done.status_code == 200, done.text
        assert done.json()["completed_at"] is not None
    finally:
        await cleanup(db_session, ctx)


@pytest.mark.asyncio
async def test_done_reopen_mentor_only(client, db_session):
    ctx = await setup_assigned(client, db_session)
    try:
        pid = ctx["pid"]
        created = await client.post(
            f"/api/v1/problems/{pid}/tasks",
            json={"title": "Reopen me", "assigned_to_user_id": ctx["s1"][2]},
            headers=bearer(ctx["s1"][1]),
        )
        tid = created.json()["id"]
        for target in ("IN_PROGRESS", "DONE"):
            resp = await client.patch(
                f"/api/v1/problems/{pid}/tasks/{tid}", json={"status": target},
                headers=bearer(ctx["s1"][1]),
            )
            assert resp.status_code == 200, resp.text
        # Member cannot reopen.
        reopen = await client.patch(
            f"/api/v1/problems/{pid}/tasks/{tid}", json={"status": "TODO"},
            headers=bearer(ctx["s1"][1]),
        )
        assert reopen.status_code == 403, reopen.text
        # Mentor can.
        reopen = await client.patch(
            f"/api/v1/problems/{pid}/tasks/{tid}", json={"status": "IN_PROGRESS"},
            headers=bearer(ctx["mentor"][1]),
        )
        assert reopen.status_code == 200, reopen.text
        # Cancel via DELETE.
        cancelled = await client.delete(
            f"/api/v1/problems/{pid}/tasks/{tid}", headers=bearer(ctx["mentor"][1])
        )
        assert cancelled.status_code == 200, cancelled.text
        assert cancelled.json()["status"] == "CANCELLED"
    finally:
        await cleanup(db_session, ctx)


@pytest.mark.asyncio
async def test_cross_problem_task_idor(client, db_session):
    ctx = await setup_assigned(client, db_session)
    ctx2 = await setup_assigned(client, db_session)
    try:
        created = await client.post(
            f"/api/v1/problems/{ctx['pid']}/tasks",
            json={"title": "Foreign task"},
            headers=bearer(ctx["s1"][1]),
        )
        tid = created.json()["id"]
        # Same member is not on problem 2's team, and the task belongs to problem 1.
        resp = await client.patch(
            f"/api/v1/problems/{ctx2['pid']}/tasks/{tid}",
            json={"status": "IN_PROGRESS"},
            headers=bearer(ctx2["s1"][1]),
        )
        assert resp.status_code == 404, resp.text
    finally:
        await cleanup(db_session, ctx)
        await cleanup(db_session, ctx2)


# ---------------- milestones ----------------


@pytest.mark.asyncio
async def test_milestone_permissions_and_flow(client, db_session):
    ctx = await setup_assigned(client, db_session)
    try:
        pid = ctx["pid"]
        # Member cannot create milestones.
        denied = await client.post(
            f"/api/v1/problems/{pid}/milestones",
            json={"title": "Member milestone"},
            headers=bearer(ctx["s1"][1]),
        )
        assert denied.status_code == 403, denied.text
        # Mentor creates + starts (triggers IN_PROGRESS).
        created = await client.post(
            f"/api/v1/problems/{pid}/milestones",
            json={"title": "Problem Analysis"},
            headers=bearer(ctx["mentor"][1]),
        )
        assert created.status_code == 201, created.text
        mid = created.json()["id"]
        started = await client.patch(
            f"/api/v1/problems/{pid}/milestones/{mid}",
            json={"status": "IN_PROGRESS"},
            headers=bearer(ctx["mentor"][1]),
        )
        assert started.status_code == 200, started.text
        detail = (await client.get(f"/api/v1/problems/{pid}", headers=bearer(ctx["mentor"][1]))).json()
        assert detail["status"] == "IN_PROGRESS"
        # Member cannot complete.
        denied = await client.patch(
            f"/api/v1/problems/{pid}/milestones/{mid}",
            json={"status": "COMPLETED"},
            headers=bearer(ctx["s1"][1]),
        )
        assert denied.status_code == 403, denied.text
        done = await client.patch(
            f"/api/v1/problems/{pid}/milestones/{mid}",
            json={"status": "COMPLETED"},
            headers=bearer(ctx["mentor"][1]),
        )
        assert done.status_code == 200, done.text
        assert done.json()["completed_at"] is not None
        # Invalid: COMPLETED -> IN_PROGRESS.
        bad = await client.patch(
            f"/api/v1/problems/{pid}/milestones/{mid}",
            json={"status": "IN_PROGRESS"},
            headers=bearer(ctx["mentor"][1]),
        )
        assert bad.status_code == 409, bad.text
    finally:
        await cleanup(db_session, ctx)


# ---------------- progress formula ----------------


async def _complete_task(client, pid, token, tid):
    for target in ("IN_PROGRESS", "DONE"):
        resp = await client.patch(
            f"/api/v1/problems/{pid}/tasks/{tid}", json={"status": target}, headers=bearer(token)
        )
        assert resp.status_code == 200, resp.text


@pytest.mark.asyncio
async def test_progress_formula_mixed(client, db_session):
    ctx = await setup_assigned(client, db_session)
    try:
        pid = ctx["pid"]
        mtok = ctx["mentor"][1]
        tids = []
        for i in range(4):
            created = await client.post(
                f"/api/v1/problems/{pid}/tasks", json={"title": f"Task {i}"}, headers=bearer(mtok)
            )
            assert created.status_code == 201, created.text
            tids.append(created.json()["id"])
        mids = []
        for i in range(2):
            created = await client.post(
                f"/api/v1/problems/{pid}/milestones", json={"title": f"Phase {i}"}, headers=bearer(mtok)
            )
            mids.append(created.json()["id"])
        # 2/4 tasks done, 1/2 milestones done -> 0.7*0.5 + 0.3*0.5 = 50%.
        await _complete_task(client, pid, mtok, tids[0])
        await _complete_task(client, pid, mtok, tids[1])
        done_ms = await client.patch(
            f"/api/v1/problems/{pid}/milestones/{mids[0]}",
            json={"status": "COMPLETED"},
            headers=bearer(mtok),
        )
        assert done_ms.status_code == 200, done_ms.text
        overview = (await client.get(f"/api/v1/problems/{pid}/workspace", headers=bearer(mtok))).json()
        assert overview["progress"]["done_tasks"] == 2
        assert overview["progress"]["total_tasks"] == 4
        assert overview["progress"]["done_milestones"] == 1
        assert overview["progress"]["total_milestones"] == 2
        assert overview["progress"]["percent"] == 50.0
        detail = (await client.get(f"/api/v1/problems/{pid}", headers=bearer(mtok))).json()
        assert detail["progress_percent"] == 50.0
    finally:
        await cleanup(db_session, ctx)


@pytest.mark.asyncio
async def test_progress_weighting_edge_cases(client, db_session):
    ctx = await setup_assigned(client, db_session)
    try:
        pid = ctx["pid"]
        mtok = ctx["mentor"][1]

        async def get_ws():
            return await client.get(f"/api/v1/problems/{pid}/workspace", headers=bearer(mtok))

        # Neither -> 0%.
        assert (await get_ws()).json()["progress"]["percent"] == 0.0
        # Tasks only: 1/2 -> 50%.
        tids = []
        for i in range(2):
            created = await client.post(
                f"/api/v1/problems/{pid}/tasks", json={"title": f"Edge task {i}"}, headers=bearer(mtok)
            )
            tids.append(created.json()["id"])
        await _complete_task(client, pid, mtok, tids[0])
        assert (await get_ws()).json()["progress"]["percent"] == 50.0
        # Cancelled excluded: cancel the open task -> 1/1 -> 100%.
        cancelled = await client.delete(
            f"/api/v1/problems/{pid}/tasks/{tids[1]}", headers=bearer(mtok)
        )
        assert cancelled.status_code == 200
        body = (await get_ws()).json()["progress"]
        assert body["total_tasks"] == 1
        assert body["percent"] == 100.0
    finally:
        await cleanup(db_session, ctx)


@pytest.mark.asyncio
async def test_progress_update_snapshot_and_work_start_once(client, db_session):
    ctx = await setup_assigned(client, db_session)
    try:
        pid = ctx["pid"]
        stok = ctx["s1"][1]
        posted = await client.post(
            f"/api/v1/problems/{pid}/progress-updates",
            json={"summary": "Surveyed the lab, switch identified"},
            headers=bearer(stok),
        )
        assert posted.status_code == 201, posted.text
        assert posted.json()["progress_snapshot"] == 0.0
        detail = (await client.get(f"/api/v1/problems/{pid}", headers=bearer(stok))).json()
        assert detail["status"] == "IN_PROGRESS"
        events = [a["event_type"] for a in detail["activity"]]
        assert events.count("WORK_STARTED") == 1
        # A second trigger does not duplicate WORK_STARTED.
        posted = await client.post(
            f"/api/v1/problems/{pid}/progress-updates",
            json={"summary": "Ordered replacement parts"},
            headers=bearer(stok),
        )
        assert posted.status_code == 201, posted.text
        detail = (await client.get(f"/api/v1/problems/{pid}", headers=bearer(stok))).json()
        assert [a["event_type"] for a in detail["activity"]].count("WORK_STARTED") == 1
    finally:
        await cleanup(db_session, ctx)


# ---------------- files ----------------


def _png_bytes() -> bytes:
    return b"\x89PNG\r\n\x1a\n" + b"\x00" * 100


def _pdf_bytes() -> bytes:
    return b"%PDF-1.4 fake" + b"\x00" * 100


@pytest.mark.asyncio
async def test_work_file_flow(client, db_session):
    ctx = await setup_assigned(client, db_session)
    try:
        pid = ctx["pid"]
        stok = ctx["s1"][1]
        up = await client.post(
            f"/api/v1/problems/{pid}/work-files",
            files={"file": ("evidence.png", _png_bytes(), "image/png")},
            data={"description": "Switch photo"},
            headers=bearer(stok),
        )
        assert up.status_code == 201, up.text
        fid = up.json()["id"]
        listed = (await client.get(f"/api/v1/problems/{pid}/work-files", headers=bearer(stok))).json()
        assert len(listed) == 1
        # Mentor can download.
        dl = await client.get(
            f"/api/v1/problems/{pid}/work-files/{fid}/download", headers=bearer(ctx["mentor"][1])
        )
        assert dl.status_code == 200, dl.text
        assert dl.content == _png_bytes()
        # Reporter cannot see or download internal files.
        assert (await client.get(
            f"/api/v1/problems/{pid}/work-files", headers=bearer(ctx["rep"][1])
        )).status_code == 403
        assert (await client.get(
            f"/api/v1/problems/{pid}/work-files/{fid}/download", headers=bearer(ctx["rep"][1])
        )).status_code == 403
        # Uploader can delete; file gone afterwards.
        assert (await client.delete(
            f"/api/v1/problems/{pid}/work-files/{fid}", headers=bearer(stok)
        )).status_code == 204
        assert (await client.get(f"/api/v1/problems/{pid}/work-files", headers=bearer(stok))).json() == []
    finally:
        await cleanup(db_session, ctx)


@pytest.mark.asyncio
async def test_work_file_validations(client, db_session):
    ctx = await setup_assigned(client, db_session)
    try:
        pid = ctx["pid"]
        stok = ctx["s1"][1]
        # Declared type not allowed.
        bad = await client.post(
            f"/api/v1/problems/{pid}/work-files",
            files={"file": ("notes.txt", b"hello", "text/plain")},
            headers=bearer(stok),
        )
        assert bad.status_code == 415, bad.text
        # Content does not match declared type.
        bad = await client.post(
            f"/api/v1/problems/{pid}/work-files",
            files={"file": ("fake.png", b"not an image", "image/png")},
            headers=bearer(stok),
        )
        assert bad.status_code == 415, bad.text
        # Oversize.
        big = _pdf_bytes() + b"\x00" * (10 * 1024 * 1024)
        bad = await client.post(
            f"/api/v1/problems/{pid}/work-files",
            files={"file": ("big.pdf", big, "application/pdf")},
            headers=bearer(stok),
        )
        assert bad.status_code == 413, bad.text
    finally:
        await cleanup(db_session, ctx)


# ---------------- access matrix ----------------


@pytest.mark.asyncio
async def test_workspace_access_matrix(client, db_session):
    ctx = await setup_assigned(client, db_session)
    try:
        pid = ctx["pid"]
        outsider_email, outsider_token, _ = await make_user(client, role="SOLVER")
        ctx["extra"] = (outsider_email, outsider_token, "x")
        other_mentor_email, other_mentor_token, _ = await make_mentor(client, db_session)
        ctx["other"] = (other_mentor_email, other_mentor_token, "x")
        ws_url = f"/api/v1/problems/{pid}/workspace"
        assert (await client.get(ws_url, headers=bearer(ctx["s1"][1]))).status_code == 200
        assert (await client.get(ws_url, headers=bearer(ctx["mentor"][1]))).status_code == 200
        assert (await client.get(ws_url, headers=bearer(ctx["admin"][1]))).status_code == 200
        # Reporter: safe progress only, no workspace.
        assert (await client.get(ws_url, headers=bearer(ctx["rep"][1]))).status_code == 403
        pub = await client.get(f"/api/v1/problems/{pid}/public-progress", headers=bearer(ctx["rep"][1]))
        assert pub.status_code == 200, pub.text
        body = pub.json()
        assert body["progress_percent"] == 0.0
        assert body["team_name"] == "Net Fixers"
        assert len(body["team_member_names"]) == 2
        assert body["mentor_name"] is not None
        assert body["assignment_active"] is True
        payload = pub.text
        for forbidden in ("blocker_reason", "assigned_to_user_id", "original_filename", "current_workload"):
            assert forbidden not in payload
        # Outsiders see nothing.
        assert (await client.get(ws_url, headers=bearer(outsider_token))).status_code == 404
        assert (await client.get(ws_url, headers=bearer(other_mentor_token))).status_code == 404
        assert (await client.get(
            f"/api/v1/problems/{pid}/public-progress", headers=bearer(outsider_token)
        )).status_code == 404
    finally:
        await cleanup(db_session, ctx)


@pytest.mark.asyncio
async def test_discussion_is_internal(client, db_session):
    ctx = await setup_assigned(client, db_session)
    try:
        pid = ctx["pid"]
        posted = await client.post(
            f"/api/v1/problems/{pid}/discussion",
            json={"content": "Plan: rewire rack 3 tomorrow"},
            headers=bearer(ctx["s1"][1]),
        )
        assert posted.status_code == 201, posted.text
        assert posted.json()["is_internal"] is True
        # Mentor reads it; reporter cannot access discussion at all.
        listed = (await client.get(
            f"/api/v1/problems/{pid}/discussion", headers=bearer(ctx["mentor"][1])
        )).json()
        assert len(listed) == 1
        assert (await client.get(
            f"/api/v1/problems/{pid}/discussion", headers=bearer(ctx["rep"][1])
        )).status_code == 403
        # Reporter problem detail never leaks internal discussion.
        detail = (await client.get(f"/api/v1/problems/{pid}", headers=bearer(ctx["rep"][1]))).json()
        assert all(c["is_internal"] is False for c in detail["comments"])
        assert all("rewire rack" not in c["content"] for c in detail["comments"])
    finally:
        await cleanup(db_session, ctx)


# ---------------- reassignment & cancellation ----------------


@pytest.mark.asyncio
async def test_reassignment_unassigns_removed_member_tasks(client, db_session):
    ctx = await setup_assigned(client, db_session)
    try:
        pid = ctx["pid"]
        created = await client.post(
            f"/api/v1/problems/{pid}/tasks",
            json={"title": "Doomed task", "assigned_to_user_id": ctx["s2"][2]},
            headers=bearer(ctx["mentor"][1]),
        )
        tid = created.json()["id"]
        s3_email, _, s3_id = await make_solver(client, db_session)
        ctx["extra"] = (s3_email, "tok", s3_id)
        reassign = await client.post(
            f"/api/v1/admin/problems/{pid}/assignment/reassign",
            json={
                "solver_user_ids": [ctx["s1"][2], s3_id],
                "mentor_user_id": ctx["mentor"][2],
                "reason": "Rotate member for workspace test",
            },
            headers=bearer(ctx["admin"][1]),
        )
        assert reassign.status_code == 200, reassign.text
        # Removed member loses workspace access immediately.
        assert (await client.get(
            f"/api/v1/problems/{pid}/workspace", headers=bearer(ctx["s2"][1])
        )).status_code == 404
        assert (await client.post(
            f"/api/v1/problems/{pid}/tasks", json={"title": "Nope"}, headers=bearer(ctx["s2"][1])
        )).status_code == 404
        # Their unfinished task is unassigned, not silently stuck.
        tasks = (await client.get(
            f"/api/v1/problems/{pid}/tasks", headers=bearer(ctx["admin"][1])
        )).json()
        doomed = next(t for t in tasks if t["id"] == tid)
        assert doomed["assigned_to_user_id"] is None
        # New member gains access immediately.
        s3_login = await login(client, s3_email)
        s3_token = s3_login.json()["access_token"]
        assert (await client.get(
            f"/api/v1/problems/{pid}/workspace", headers=bearer(s3_token)
        )).status_code == 200
        detail = (await client.get(
            f"/api/v1/problems/{pid}", headers=bearer(ctx["admin"][1])
        )).json()
        assert "TASK_REASSIGNED" in [a["event_type"] for a in detail["activity"]]
    finally:
        await cleanup(db_session, ctx)


@pytest.mark.asyncio
async def test_cancelled_assignment_blocks_new_work_preserves_history(client, db_session):
    ctx = await setup_assigned(client, db_session)
    try:
        pid = ctx["pid"]
        created = await client.post(
            f"/api/v1/problems/{pid}/tasks", json={"title": "Keep me"}, headers=bearer(ctx["s1"][1])
        )
        assert created.status_code == 201
        cancel = await client.post(
            f"/api/v1/admin/problems/{pid}/assignment/cancel",
            json={"reason": "Pausing work for test"},
            headers=bearer(ctx["admin"][1]),
        )
        assert cancel.status_code == 200, cancel.text
        # New work blocked.
        blocked = await client.post(
            f"/api/v1/problems/{pid}/tasks", json={"title": "Too late"}, headers=bearer(ctx["s1"][1])
        )
        assert blocked.status_code in (404, 409), blocked.text
        # History preserved for admin.
        tasks = await client.get(f"/api/v1/problems/{pid}/tasks", headers=bearer(ctx["admin"][1]))
        assert tasks.status_code == 200, tasks.text
        assert any(t["title"] == "Keep me" for t in tasks.json())
    finally:
        await cleanup(db_session, ctx)


@pytest.mark.asyncio
async def test_reporter_public_progress_hides_internals(client, db_session):
    ctx = await setup_assigned(client, db_session)
    try:
        pid = ctx["pid"]
        # Internal-heavy state: blocked task + internal discussion + file.
        created = await client.post(
            f"/api/v1/problems/{pid}/tasks",
            json={"title": "Secret task with sensitive details"},
            headers=bearer(ctx["mentor"][1]),
        )
        tid = created.json()["id"]
        await client.patch(
            f"/api/v1/problems/{pid}/tasks/{tid}",
            json={"status": "IN_PROGRESS"},
            headers=bearer(ctx["mentor"][1]),
        )
        await client.patch(
            f"/api/v1/problems/{pid}/tasks/{tid}",
            json={"status": "BLOCKED", "blocker_reason": "Internal vendor failure"},
            headers=bearer(ctx["mentor"][1]),
        )
        await client.post(
            f"/api/v1/problems/{pid}/discussion",
            json={"content": "Internal debate about blame"},
            headers=bearer(ctx["mentor"][1]),
        )
        await client.post(
            f"/api/v1/problems/{pid}/progress-updates",
            json={"summary": "Hit an internal snag", "blockers": "Secret blocker"},
            headers=bearer(ctx["mentor"][1]),
        )
        pub = (await client.get(
            f"/api/v1/problems/{pid}/public-progress", headers=bearer(ctx["rep"][1])
        )).json()
        assert pub["completed_tasks"] == 0
        assert pub["total_tasks"] == 1
        blob = str(pub)
        assert "Secret task" not in blob
        assert "Internal vendor failure" not in blob
        assert "Internal debate" not in blob
        assert "Secret blocker" not in blob
        # Summaries are public-safe.
        assert any("internal snag" in u["summary"] for u in pub["recent_updates"])
        assert all(set(u.keys()) <= {"summary", "progress_snapshot", "author_role", "created_at"}
                   for u in pub["recent_updates"])
    finally:
        await cleanup(db_session, ctx)


@pytest.mark.asyncio
async def test_dashboards_expose_workspace_problems(client, db_session):
    ctx = await setup_assigned(client, db_session)
    try:
        assigned = (await client.get(
            "/api/v1/problems/assigned/me", headers=bearer(ctx["s1"][1])
        )).json()
        assert any(p["id"] == ctx["pid"] for p in assigned)
        mentored = (await client.get(
            "/api/v1/problems/mentored/me", headers=bearer(ctx["mentor"][1])
        )).json()
        assert any(p["id"] == ctx["pid"] for p in mentored)
        # Workspace reachable from the worklist entry.
        ws = await client.get(f"/api/v1/problems/{ctx['pid']}/workspace", headers=bearer(ctx["s1"][1]))
        assert ws.status_code == 200
        assert ws.json()["ticket_number"]
    finally:
        await cleanup(db_session, ctx)
