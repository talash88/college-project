"""Step 11 tests: solution submission, mentor review, verification, closure, workloads."""

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

PASSWORD = "Step11_Test_pass"


def unique_email(prefix: str = "v11") -> str:
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
    "testing_performed": "Ping and iperf runs from every lab terminal for one hour.",
}


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def register(ac, email, role="REPORTER"):
    return await ac.post(
        "/api/v1/auth/register",
        json={"full_name": f"V11 {role}", "email": email, "password": PASSWORD, "role": role},
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
            student_identifier=f"STV{uuid4().hex[:8]}",
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
            employee_identifier=f"FCV{uuid4().hex[:8]}",
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
    start = await ac.post(f"/api/v1/admin/problems/{pid}/review/start", headers=bearer(admin_token))
    assert start.status_code == 200, start.text
    ok = await ac.post(f"/api/v1/admin/problems/{pid}/approve", json={}, headers=bearer(admin_token))
    assert ok.status_code == 200, ok.text
    assign = await ac.post(
        f"/api/v1/admin/problems/{pid}/assign",
        json={
            "solver_user_ids": [s1_id, s2_id],
            "mentor_user_id": m_id,
            "team_name": "Verify Crew",
            "team_override_reason": "Manual team for verification tests",
            "mentor_override_reason": "Manual mentor for verification tests",
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


async def complete_task(ac, pid, token, title="Fix it", priority="LOW"):
    created = await ac.post(
        f"/api/v1/problems/{pid}/tasks",
        json={"title": title, "priority": priority},
        headers=bearer(token),
    )
    assert created.status_code == 201, created.text
    tid = created.json()["id"]
    for target in ("IN_PROGRESS", "DONE"):
        resp = await ac.patch(
            f"/api/v1/problems/{pid}/tasks/{tid}", json={"status": target}, headers=bearer(token)
        )
        assert resp.status_code == 200, resp.text
    return tid


async def setup_ready(ac, session):
    """Assigned problem, IN_PROGRESS, all work complete (readiness passes)."""
    ctx = await setup_assigned(ac, session)
    await complete_task(ac, ctx["pid"], ctx["s1"][1], title="Replace the switch")
    await complete_task(ac, ctx["pid"], ctx["s1"][1], title="Test every terminal")
    return ctx


async def submit(ac, ctx, token=None, payload=None):
    return await ac.post(
        f"/api/v1/problems/{ctx['pid']}/solutions",
        json=payload or SOLUTION_PAYLOAD,
        headers=bearer(token or ctx["s1"][1]),
    )


async def workloads(session, ctx):
    """Current workloads keyed by role: s1, s2, mentor."""
    from sqlalchemy.orm import selectinload

    out = {}
    for key, profile in (("s1", "student"), ("s2", "student"), ("mentor", "faculty")):
        result = await session.execute(
            select(User)
            .options(selectinload(User.student_profile), selectinload(User.faculty_profile))
            .where(User.email == ctx[key][0].lower())
        )
        user = result.scalar_one()
        prof = user.student_profile if profile == "student" else user.faculty_profile
        assert prof is not None
        out[key] = prof.current_workload
    return out


# ---------------- submission ----------------


@pytest.mark.asyncio
async def test_submit_requires_readiness(client, db_session):
    ctx = await setup_assigned(client, db_session)
    try:
        pid = ctx["pid"]
        # No work done yet: readiness fails openly (not 409: still ASSIGNED).
        resp = await submit(client, ctx)
        assert resp.status_code == 409, resp.text
        # Start work but leave a task open.
        created = await client.post(
            f"/api/v1/problems/{pid}/tasks", json={"title": "Half done"}, headers=bearer(ctx["s1"][1])
        )
        tid = created.json()["id"]
        await client.patch(
            f"/api/v1/problems/{pid}/tasks/{tid}", json={"status": "IN_PROGRESS"},
            headers=bearer(ctx["s1"][1]),
        )
        ready = (
            await client.get(f"/api/v1/problems/{pid}/solution/readiness", headers=bearer(ctx["s1"][1]))
        ).json()
        assert ready["ready"] is False
        assert ready["reasons"]
        resp = await submit(client, ctx)
        assert resp.status_code == 422, resp.text
        assert "not ready" in resp.json()["detail"]
    finally:
        await cleanup(db_session, ctx)


@pytest.mark.asyncio
async def test_submit_success_and_mentor_notified(client, db_session):
    ctx = await setup_ready(client, db_session)
    try:
        resp = await submit(client, ctx)
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["revision_number"] == 1
        assert body["status"] == "SUBMITTED"
        notifs = (
            await client.get("/api/v1/notifications", headers=bearer(ctx["mentor"][1]))
        ).json()
        assert any(
            n["type"] == "SOLUTION_SUBMITTED" and n["problem_id"] == ctx["pid"] for n in notifs["items"]
        ), notifs
        # Double submit while pending review is rejected.
        again = await submit(client, ctx)
        assert again.status_code == 409, again.text
    finally:
        await cleanup(db_session, ctx)


@pytest.mark.asyncio
async def test_submit_permissions(client, db_session):
    ctx = await setup_ready(client, db_session)
    try:
        # Reporter denied.
        assert (await submit(client, ctx, token=ctx["rep"][1])).status_code == 403
        # Assigned mentor cannot submit as a student.
        assert (await submit(client, ctx, token=ctx["mentor"][1])).status_code == 403
        # Unrelated solver sees nothing.
        outsider_email, outsider_token, _ = await make_user(client, role="SOLVER")
        try:
            assert (await submit(client, ctx, token=outsider_token)).status_code == 404
        finally:
            await delete_user(db_session, outsider_email)
        # Admin may submit when readiness passes (audited without override).
        resp = await submit(client, ctx, token=ctx["admin"][1])
        assert resp.status_code == 201, resp.text
        assert resp.json()["readiness_override_reason"] is None
    finally:
        await cleanup(db_session, ctx)


@pytest.mark.asyncio
async def test_admin_override_submit_audited(client, db_session):
    ctx = await setup_assigned(client, db_session)
    try:
        pid = ctx["pid"]
        # Force IN_PROGRESS with incomplete work (readiness fails).
        created = await client.post(
            f"/api/v1/problems/{pid}/tasks", json={"title": "Unfinished"}, headers=bearer(ctx["s1"][1])
        )
        tid = created.json()["id"]
        await client.patch(
            f"/api/v1/problems/{pid}/tasks/{tid}", json={"status": "IN_PROGRESS"},
            headers=bearer(ctx["s1"][1]),
        )
        payload = dict(SOLUTION_PAYLOAD, override_reason="Demo deadline override by admin")
        resp = await submit(client, ctx, token=ctx["admin"][1], payload=payload)
        assert resp.status_code == 201, resp.text
        assert resp.json()["readiness_override_reason"] == "Demo deadline override by admin"
        detail = (await client.get(f"/api/v1/problems/{pid}", headers=bearer(ctx["admin"][1]))).json()
        assert any(
            "overridden" in (a["message"] or "") for a in detail["activity"] if a["event_type"] == "SOLUTION_SUBMITTED"
        )
        # Non-admin cannot use the override.
        payload = dict(SOLUTION_PAYLOAD, override_reason="Sneaky")
        assert (await submit(client, ctx, payload=payload)).status_code in (403, 409)
    finally:
        await cleanup(db_session, ctx)


# ---------------- mentor review ----------------


@pytest.mark.asyncio
async def test_mentor_approve_flow(client, db_session):
    ctx = await setup_ready(client, db_session)
    try:
        pid = ctx["pid"]
        sub = (await submit(client, ctx)).json()
        review = await client.post(
            f"/api/v1/problems/{pid}/solutions/{sub['id']}/review",
            json={"decision": "APPROVED", "review_comment": "Solid fix, verified logs."},
            headers=bearer(ctx["mentor"][1]),
        )
        assert review.status_code == 201, review.text
        assert review.json()["decision"] == "APPROVED"
        detail = (await client.get(f"/api/v1/problems/{pid}", headers=bearer(ctx["mentor"][1]))).json()
        assert detail["status"] == "AWAITING_VERIFICATION"
        events = [a["event_type"] for a in detail["activity"]]
        assert "MENTOR_SOLUTION_APPROVED" in events
        assert "REPORTER_VERIFICATION_REQUESTED" in events
        # Reporter was notified.
        notifs = (await client.get("/api/v1/notifications", headers=bearer(ctx["rep"][1]))).json()
        assert any(n["type"] == "REPORTER_VERIFICATION_REQUIRED" for n in notifs["items"])
        # Already reviewed: second review rejected.
        again = await client.post(
            f"/api/v1/problems/{pid}/solutions/{sub['id']}/review",
            json={"decision": "APPROVED"},
            headers=bearer(ctx["mentor"][1]),
        )
        assert again.status_code == 409, again.text
    finally:
        await cleanup(db_session, ctx)


@pytest.mark.asyncio
async def test_request_changes_needs_comment_and_new_revision(client, db_session):
    ctx = await setup_ready(client, db_session)
    try:
        pid = ctx["pid"]
        sub = (await submit(client, ctx)).json()
        # Comment required.
        assert (
            await client.post(
                f"/api/v1/problems/{pid}/solutions/{sub['id']}/review",
                json={"decision": "CHANGES_REQUESTED"},
                headers=bearer(ctx["mentor"][1]),
            )
        ).status_code == 422
        review = await client.post(
            f"/api/v1/problems/{pid}/solutions/{sub['id']}/review",
            json={"decision": "CHANGES_REQUESTED", "review_comment": "Add load-test evidence."},
            headers=bearer(ctx["mentor"][1]),
        )
        assert review.status_code == 201, review.text
        detail = (await client.get(f"/api/v1/problems/{pid}", headers=bearer(ctx["s1"][1]))).json()
        assert detail["status"] == "IN_PROGRESS"
        # Team notified.
        notifs = (await client.get("/api/v1/notifications", headers=bearer(ctx["s1"][1]))).json()
        assert any(n["type"] == "CHANGES_REQUESTED" for n in notifs["items"])
        # New revision accepted; history preserved.
        sub2 = (await submit(client, ctx)).json()
        assert sub2["revision_number"] == 2
        history = (
            await client.get(f"/api/v1/problems/{pid}/solutions", headers=bearer(ctx["mentor"][1]))
        ).json()
        assert [s["revision_number"] for s in history] == [1, 2]
        assert history[0]["reviews"][0]["decision"] == "CHANGES_REQUESTED"
    finally:
        await cleanup(db_session, ctx)


@pytest.mark.asyncio
async def test_review_permissions(client, db_session):
    ctx = await setup_ready(client, db_session)
    try:
        pid = ctx["pid"]
        sub = (await submit(client, ctx)).json()
        other_email, other_token, _ = await make_mentor(client, db_session)
        try:
            resp = await client.post(
                f"/api/v1/problems/{pid}/solutions/{sub['id']}/review",
                json={"decision": "APPROVED"},
                headers=bearer(other_token),
            )
            assert resp.status_code in (403, 404), resp.text
        finally:
            await delete_user(db_session, other_email)
        # Team member cannot review.
        resp = await client.post(
            f"/api/v1/problems/{pid}/solutions/{sub['id']}/review",
            json={"decision": "APPROVED"},
            headers=bearer(ctx["s1"][1]),
        )
        assert resp.status_code == 403, resp.text
        # Admin override without comment is rejected; with comment it is audited.
        resp = await client.post(
            f"/api/v1/problems/{pid}/solutions/{sub['id']}/review",
            json={"decision": "APPROVED"},
            headers=bearer(ctx["admin"][1]),
        )
        assert resp.status_code == 422, resp.text
        resp = await client.post(
            f"/api/v1/problems/{pid}/solutions/{sub['id']}/review",
            json={"decision": "APPROVED", "review_comment": "Admin override: mentor unavailable."},
            headers=bearer(ctx["admin"][1]),
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["is_admin_override"] is True
    finally:
        await cleanup(db_session, ctx)


# ---------------- reporter verification ----------------


async def _to_awaiting(client, ctx):
    sub = (await submit(client, ctx)).json()
    review = await client.post(
        f"/api/v1/problems/{ctx['pid']}/solutions/{sub['id']}/review",
        json={"decision": "APPROVED"},
        headers=bearer(ctx["mentor"][1]),
    )
    assert review.status_code == 201, review.text
    return sub


@pytest.mark.asyncio
async def test_reporter_confirm_resolves(client, db_session):
    ctx = await setup_ready(client, db_session)
    try:
        pid = ctx["pid"]
        before = await workloads(db_session, ctx)
        await _to_awaiting(client, ctx)
        verify = await client.post(
            f"/api/v1/problems/{pid}/verifications",
            json={"decision": "RESOLVED"},
            headers=bearer(ctx["rep"][1]),
        )
        assert verify.status_code == 201, verify.text
        detail = (await client.get(f"/api/v1/problems/{pid}", headers=bearer(ctx["rep"][1]))).json()
        assert detail["status"] == "RESOLVED"
        assert detail["resolved_at"] is not None
        # Workloads NOT released at verify time.
        assert await workloads(db_session, ctx) == before
        # Team + mentor notified.
        for token in (ctx["s1"][1], ctx["mentor"][1]):
            notifs = (await client.get("/api/v1/notifications", headers=bearer(token))).json()
            assert any(n["type"] == "PROBLEM_RESOLVED" for n in notifs["items"])
    finally:
        await cleanup(db_session, ctx)


@pytest.mark.asyncio
async def test_reporter_reject_reopens(client, db_session):
    ctx = await setup_ready(client, db_session)
    try:
        pid = ctx["pid"]
        before = await workloads(db_session, ctx)
        await _to_awaiting(client, ctx)
        # Reason required.
        assert (
            await client.post(
                f"/api/v1/problems/{pid}/verifications",
                json={"decision": "NOT_RESOLVED"},
                headers=bearer(ctx["rep"][1]),
            )
        ).status_code == 422
        verify = await client.post(
            f"/api/v1/problems/{pid}/verifications",
            json={"decision": "NOT_RESOLVED", "reason": "WiFi still drops every afternoon."},
            headers=bearer(ctx["rep"][1]),
        )
        assert verify.status_code == 201, verify.text
        detail = (await client.get(f"/api/v1/problems/{pid}", headers=bearer(ctx["s1"][1]))).json()
        assert detail["status"] == "IN_PROGRESS"
        # Assignment stays ACTIVE, workloads stay allocated, workspace writable.
        assert await workloads(db_session, ctx) == before
        task = await client.post(
            f"/api/v1/problems/{pid}/tasks", json={"title": "Rework uplink"}, headers=bearer(ctx["s1"][1])
        )
        assert task.status_code == 201, task.text
        latest = (
            await client.get(f"/api/v1/problems/{pid}/solutions/latest", headers=bearer(ctx["mentor"][1]))
        ).json()
        assert latest["status"] == "REPORTER_REJECTED"
    finally:
        await cleanup(db_session, ctx)


@pytest.mark.asyncio
async def test_verification_permissions(client, db_session):
    ctx = await setup_ready(client, db_session)
    try:
        pid = ctx["pid"]
        await _to_awaiting(client, ctx)
        # Another reporter cannot verify someone else's report.
        other_email, other_token, _ = await make_user(client)
        try:
            resp = await client.post(
                f"/api/v1/problems/{pid}/verifications",
                json={"decision": "RESOLVED"},
                headers=bearer(other_token),
            )
            assert resp.status_code in (403, 404), resp.text
        finally:
            await delete_user(db_session, other_email)
        # Team member cannot verify.
        resp = await client.post(
            f"/api/v1/problems/{pid}/verifications",
            json={"decision": "RESOLVED"},
            headers=bearer(ctx["s1"][1]),
        )
        assert resp.status_code == 403, resp.text
        # Cannot verify twice: already RESOLVED after confirm... first confirm:
        ok = await client.post(
            f"/api/v1/problems/{pid}/verifications",
            json={"decision": "RESOLVED"},
            headers=bearer(ctx["rep"][1]),
        )
        assert ok.status_code == 201, ok.text
        again = await client.post(
            f"/api/v1/problems/{pid}/verifications",
            json={"decision": "RESOLVED"},
            headers=bearer(ctx["rep"][1]),
        )
        assert again.status_code == 409, again.text
    finally:
        await cleanup(db_session, ctx)


# ---------------- closure + workloads ----------------


async def _to_resolved(client, ctx):
    await _to_awaiting(client, ctx)
    verify = await client.post(
        f"/api/v1/problems/{ctx['pid']}/verifications",
        json={"decision": "RESOLVED"},
        headers=bearer(ctx["rep"][1]),
    )
    assert verify.status_code == 201, verify.text


@pytest.mark.asyncio
async def test_close_releases_workloads_exactly_once(client, db_session):
    ctx = await setup_ready(client, db_session)
    try:
        pid = ctx["pid"]
        # Close only allowed from RESOLVED.
        assert (
            await client.post(f"/api/v1/admin/problems/{pid}/close", json={}, headers=bearer(ctx["admin"][1]))
        ).status_code == 409
        before = await workloads(db_session, ctx)
        assert before == {"s1": 1, "s2": 1, "mentor": 1}
        await _to_resolved(client, ctx)
        assert await workloads(db_session, ctx) == before
        close = await client.post(
            f"/api/v1/admin/problems/{pid}/close",
            json={"reason": "Verified fix holding for a week."},
            headers=bearer(ctx["admin"][1]),
        )
        assert close.status_code == 200, close.text
        assert close.json()["status"] == "CLOSED"
        assert await workloads(db_session, ctx) == {"s1": 0, "s2": 0, "mentor": 0}
        # Retry close: rejected, no second decrement (floors at 0 anyway).
        again = await client.post(
            f"/api/v1/admin/problems/{pid}/close", json={}, headers=bearer(ctx["admin"][1])
        )
        assert again.status_code == 409, again.text
        assert await workloads(db_session, ctx) == {"s1": 0, "s2": 0, "mentor": 0}
        detail = (await client.get(f"/api/v1/problems/{pid}", headers=bearer(ctx["admin"][1]))).json()
        assert detail["closed_at"] is not None
        assert "PROBLEM_CLOSED" in [a["event_type"] for a in detail["activity"]]
    finally:
        await cleanup(db_session, ctx)


@pytest.mark.asyncio
async def test_workspace_readonly_after_close_but_history_kept(client, db_session):
    ctx = await setup_ready(client, db_session)
    try:
        pid = ctx["pid"]
        await _to_resolved(client, ctx)
        await client.post(f"/api/v1/admin/problems/{pid}/close", json={}, headers=bearer(ctx["admin"][1]))
        # New work blocked for the team...
        assert (
            await client.post(
                f"/api/v1/problems/{pid}/tasks", json={"title": "Too late"}, headers=bearer(ctx["s1"][1])
            )
        ).status_code == 409
        assert (
            await client.post(
                f"/api/v1/problems/{pid}/solutions", json=SOLUTION_PAYLOAD, headers=bearer(ctx["s1"][1])
            )
        ).status_code == 409
        # ...but history stays readable for team, mentor, admin.
        for token in (ctx["s1"][1], ctx["mentor"][1], ctx["admin"][1]):
            ws = await client.get(f"/api/v1/problems/{pid}/workspace", headers=bearer(token))
            assert ws.status_code == 200, (token, ws.text)
            sols = await client.get(f"/api/v1/problems/{pid}/solutions", headers=bearer(token))
            assert sols.status_code == 200
            assert len(sols.json()) >= 1
        # Reporter keeps the safe view, never the workspace.
        pub = (
            await client.get(f"/api/v1/problems/{pid}/public-progress", headers=bearer(ctx["rep"][1]))
        ).json()
        assert pub["status"] == "CLOSED"
        assert pub["solution"] is not None
        assert pub["solution"]["status"] == "VERIFIED"
        assert (
            await client.get(f"/api/v1/problems/{pid}/workspace", headers=bearer(ctx["rep"][1]))
        ).status_code == 403
    finally:
        await cleanup(db_session, ctx)


@pytest.mark.asyncio
async def test_safe_solution_hides_internals(client, db_session):
    ctx = await setup_ready(client, db_session)
    try:
        pid = ctx["pid"]
        await _to_awaiting(client, ctx)
        safe = (
            await client.get(f"/api/v1/problems/{pid}/solution/safe", headers=bearer(ctx["rep"][1]))
        ).json()
        assert "Replaced the faulty lab switch" in safe["solution_summary"]
        blob = str(safe)
        for forbidden in ("blocker_reason", "assigned_to_user_id", "original_filename", "current_workload"):
            assert forbidden not in blob
        # Before approval there is nothing safe to show.
        ctx2 = await setup_ready(client, db_session)
        try:
            missing = await client.get(
                f"/api/v1/problems/{ctx2['pid']}/solution/safe", headers=bearer(ctx2["rep"][1])
            )
            assert missing.status_code == 404, missing.text
        finally:
            await cleanup(db_session, ctx2)
    finally:
        await cleanup(db_session, ctx)


@pytest.mark.asyncio
async def test_verification_history_preserved(client, db_session):
    ctx = await setup_ready(client, db_session)
    try:
        pid = ctx["pid"]
        await _to_awaiting(client, ctx)
        no = await client.post(
            f"/api/v1/problems/{pid}/verifications",
            json={"decision": "NOT_RESOLVED", "reason": "Still dropping."},
            headers=bearer(ctx["rep"][1]),
        )
        assert no.status_code == 201
        sub2 = (await submit(client, ctx)).json()
        assert sub2["revision_number"] == 2
        await client.post(
            f"/api/v1/problems/{pid}/solutions/{sub2['id']}/review",
            json={"decision": "APPROVED"},
            headers=bearer(ctx["mentor"][1]),
        )
        yes = await client.post(
            f"/api/v1/problems/{pid}/verifications",
            json={"decision": "RESOLVED"},
            headers=bearer(ctx["rep"][1]),
        )
        assert yes.status_code == 201
        history = (
            await client.get(f"/api/v1/problems/{pid}/verifications", headers=bearer(ctx["mentor"][1]))
        ).json()
        assert [v["decision"] for v in history] == ["NOT_RESOLVED", "RESOLVED"]
    finally:
        await cleanup(db_session, ctx)
