"""Step 4 tests: problem reporting, tickets, ownership/IDOR, attachments, activity, admin."""

import asyncio
import re
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.enums import UserRole
from app.main import app
from app.models.user import User

PASSWORD = "Step4_Test_pass"
TICKET_RE = re.compile(r"^CX-\d{4}-\d{6}$")

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 200
JPEG_BYTES = b"\xff\xd8\xff\xe0" + b"\x00" * 200
PDF_BYTES = b"%PDF-1.4\n" + b"\x00" * 200
TEXT_BYTES = b"just some plain text, not an image"


def unique_email(prefix: str = "step4") -> str:
    return f"{prefix}_{uuid4().hex[:10]}@example.com"


def problem_payload(**overrides):  # type: ignore[no-untyped-def]
    payload = {
        "title": "Leaking water pipe near library entrance",
        "description": "There is a continuous water leak from the pipe next to the "
        "main library entrance. The floor stays wet all day.",
        "location_text": "Central Library, Ground Floor",
        "building": "Central Library",
        "area": "North Campus",
        "affected_people_count": 150,
    }
    payload.update(overrides)
    return payload


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def tmp_storage(tmp_path, monkeypatch):
    """Isolate attachment files per test."""
    monkeypatch.setattr(settings, "STORAGE_DIR", str(tmp_path / "attachments"))
    return tmp_path / "attachments"


async def register(ac: AsyncClient, email: str, role: str = "REPORTER"):
    return await ac.post(
        "/api/v1/auth/register",
        json={"full_name": "Step4 User", "email": email, "password": PASSWORD, "role": role},
    )


async def login(ac: AsyncClient, email: str):
    return await ac.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def make_user(ac: AsyncClient, role: str = "REPORTER") -> tuple[str, str, str]:
    """Register + login. Returns (email, token, user_id)."""
    email = unique_email(role.lower())
    reg = await register(ac, email, role=role)
    assert reg.status_code == 201, reg.text
    token = reg.json()["access_token"]
    user_id = reg.json()["user"]["id"]
    return email, token, user_id


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


async def create_problem(ac: AsyncClient, token: str, **overrides):  # type: ignore[no-untyped-def]
    return await ac.post(
        "/api/v1/problems", json=problem_payload(**overrides), headers=bearer(token)
    )


# ---------------- Creation / tickets ----------------


@pytest.mark.asyncio
async def test_create_problem_success(client: AsyncClient, db_session: AsyncSession):
    email, token, user_id = await make_user(client)
    try:
        resp = await create_problem(client, token)
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert TICKET_RE.match(body["ticket_number"]), body["ticket_number"]
        assert body["status"] == "SUBMITTED"
        assert body["reporter_id"] == user_id
        assert body["reporter"]["full_name"] == "Step4 User"
        # Step 5: real AI classification runs on creation (never faked).
        assert body["classification_status"] in ("COMPLETED", "LOW_CONFIDENCE")
        assert body["predicted_category"] in (
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
        )
        # Step 6: real priority analysis runs on creation (never faked).
        assert body["priority_status"] == "COMPLETED"
        assert 0 <= body["priority_score"] <= 100
        assert body["priority_level"] in ("LOW", "MEDIUM", "HIGH", "CRITICAL")
        # Submitted activity recorded.
        acts = await client.get(f"/api/v1/problems/{body['id']}/activity", headers=bearer(token))
        assert acts.status_code == 200
        assert [a["event_type"] for a in acts.json()] == ["SUBMITTED"]
    finally:
        await delete_user(db_session, email)


@pytest.mark.asyncio
async def test_create_problem_requires_auth(client: AsyncClient):
    resp = await client.post("/api/v1/problems", json=problem_payload())
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_create_problem_ignores_spoofed_reporter(
    client: AsyncClient, db_session: AsyncSession
):
    email, token, user_id = await make_user(client)
    other = unique_email("other")
    await register(client, other)
    try:
        other_id = (await login(client, other)).json()
        resp = await client.post(
            "/api/v1/problems",
            json=problem_payload(reporter_id=other_id),
            headers=bearer(token),
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["reporter_id"] == user_id
    finally:
        await delete_user(db_session, email)
        await delete_user(db_session, other)


@pytest.mark.asyncio
async def test_ticket_numbers_unique(client: AsyncClient, db_session: AsyncSession):
    email, token, _ = await make_user(client)
    try:
        tickets = set()
        for _ in range(3):
            resp = await create_problem(client, token)
            assert resp.status_code == 201, resp.text
            tickets.add(resp.json()["ticket_number"])
        assert len(tickets) == 3
    finally:
        await delete_user(db_session, email)


@pytest.mark.asyncio
async def test_ticket_numbers_concurrent_safe(client: AsyncClient, db_session: AsyncSession):
    email, token, _ = await make_user(client)
    try:
        responses = await asyncio.gather(*[create_problem(client, token) for _ in range(10)])
        assert all(r.status_code == 201 for r in responses), [
            r.text for r in responses if r.status_code != 201
        ]
        tickets = [r.json()["ticket_number"] for r in responses]
        assert len(set(tickets)) == 10
        assert all(TICKET_RE.match(t) for t in tickets)
    finally:
        await delete_user(db_session, email)


# ---------------- Validation ----------------


@pytest.mark.asyncio
async def test_create_validation(client: AsyncClient, db_session: AsyncSession):
    email, token, _ = await make_user(client)
    try:
        cases = [
            problem_payload(title=""),
            problem_payload(title="abc"),
            problem_payload(title="   "),
            problem_payload(description="too short"),
            problem_payload(description=" " * 25),
            problem_payload(location_text=""),
            problem_payload(affected_people_count=0),
            problem_payload(affected_people_count=-5),
        ]
        for payload in cases:
            resp = await client.post("/api/v1/problems", json=payload, headers=bearer(token))
            assert resp.status_code == 422, (payload, resp.text)
    finally:
        await delete_user(db_session, email)


@pytest.mark.asyncio
async def test_update_rejects_protected_fields(client: AsyncClient, db_session: AsyncSession):
    email, token, _ = await make_user(client)
    try:
        created = (await create_problem(client, token)).json()
        pid = created["id"]
        for payload in [
            {"status": "APPROVED"},
            {"ticket_number": "CX-2026-999999"},
            {"reporter_id": str(uuid4())},
            {"priority_score": 9.9},
            {"predicted_category": "Plumbing"},
        ]:
            resp = await client.patch(
                f"/api/v1/problems/{pid}", json=payload, headers=bearer(token)
            )
            assert resp.status_code == 422, (payload, resp.text)
    finally:
        await delete_user(db_session, email)


# ---------------- Ownership / IDOR ----------------


@pytest.mark.asyncio
async def test_ownership_idor(client: AsyncClient, db_session: AsyncSession):
    email_a, token_a, _ = await make_user(client)
    email_b, token_b, _ = await make_user(client)
    try:
        created = (await create_problem(client, token_a)).json()
        pid = created["id"]
        # Owner can view.
        assert (
            await client.get(f"/api/v1/problems/{pid}", headers=bearer(token_a))
        ).status_code == 200
        # Another reporter gets nothing (no existence oracle).
        assert (
            await client.get(f"/api/v1/problems/{pid}", headers=bearer(token_b))
        ).status_code == 404
        assert (
            await client.patch(
                f"/api/v1/problems/{pid}",
                json={"title": "Hijacked title here"},
                headers=bearer(token_b),
            )
        ).status_code == 404
        assert (
            await client.delete(f"/api/v1/problems/{pid}", headers=bearer(token_b))
        ).status_code == 404
        # Report unchanged.
        fresh = (await client.get(f"/api/v1/problems/{pid}", headers=bearer(token_a))).json()
        assert fresh["title"] == created["title"]
    finally:
        await delete_user(db_session, email_a)
        await delete_user(db_session, email_b)


@pytest.mark.asyncio
async def test_admin_can_view_any_report(client: AsyncClient, db_session: AsyncSession):
    email, token, _ = await make_user(client)
    admin_email, admin_token, _ = await make_user(client, role="SOLVER")
    await promote_to_admin(db_session, admin_email)
    admin_token = (await login(client, admin_email)).json()["access_token"]
    try:
        pid = (await create_problem(client, token)).json()["id"]
        resp = await client.get(f"/api/v1/problems/{pid}", headers=bearer(admin_token))
        assert resp.status_code == 200
        assert resp.json()["reporter"]["full_name"] == "Step4 User"
    finally:
        await delete_user(db_session, email)
        await delete_user(db_session, admin_email)


# ---------------- Edit / withdraw ----------------


@pytest.mark.asyncio
async def test_owner_can_edit_submitted(client: AsyncClient, db_session: AsyncSession):
    email, token, _ = await make_user(client)
    try:
        pid = (await create_problem(client, token)).json()["id"]
        resp = await client.patch(
            f"/api/v1/problems/{pid}",
            json={"title": "Updated leaking pipe title", "affected_people_count": 200},
            headers=bearer(token),
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["title"] == "Updated leaking pipe title"
        acts = (await client.get(f"/api/v1/problems/{pid}/activity", headers=bearer(token))).json()
        assert "EDITED" in [a["event_type"] for a in acts]
    finally:
        await delete_user(db_session, email)


@pytest.mark.asyncio
async def test_withdraw_soft_delete(client: AsyncClient, db_session: AsyncSession):
    email, token, _ = await make_user(client)
    try:
        pid = (await create_problem(client, token)).json()["id"]
        resp = await client.delete(f"/api/v1/problems/{pid}", headers=bearer(token))
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "WITHDRAWN"
        # History preserved: still visible to owner + admin.
        assert (
            await client.get(f"/api/v1/problems/{pid}", headers=bearer(token))
        ).status_code == 200
        acts = (await client.get(f"/api/v1/problems/{pid}/activity", headers=bearer(token))).json()
        assert [a["event_type"] for a in acts] == ["SUBMITTED", "STATUS_CHANGED"]
        # Editing a withdrawn report is rejected.
        edit = await client.patch(
            f"/api/v1/problems/{pid}",
            json={"title": "Trying to edit withdrawn"},
            headers=bearer(token),
        )
        assert edit.status_code == 409
        # Withdrawing twice is rejected.
        assert (
            await client.delete(f"/api/v1/problems/{pid}", headers=bearer(token))
        ).status_code == 409
    finally:
        await delete_user(db_session, email)


@pytest.mark.asyncio
async def test_admin_can_withdraw_other_report(client: AsyncClient, db_session: AsyncSession):
    email, token, _ = await make_user(client)
    admin_email, _, _ = await make_user(client, role="SOLVER")
    await promote_to_admin(db_session, admin_email)
    admin_token = (await login(client, admin_email)).json()["access_token"]
    try:
        pid = (await create_problem(client, token)).json()["id"]
        resp = await client.delete(f"/api/v1/problems/{pid}", headers=bearer(admin_token))
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "WITHDRAWN"
    finally:
        await delete_user(db_session, email)
        await delete_user(db_session, admin_email)


# ---------------- Listing / search / stats ----------------


@pytest.mark.asyncio
async def test_my_reports_listing_search_pagination(client: AsyncClient, db_session: AsyncSession):
    email, token, _ = await make_user(client)
    other_email, other_token, _ = await make_user(client)
    try:
        for i in range(3):
            r = await create_problem(client, token, title=f"Library leak issue number {i}")
            assert r.status_code == 201
        await create_problem(client, other_token, title="Someone else hostel problem")
        # Only own reports.
        mine = await client.get("/api/v1/problems/me", headers=bearer(token))
        assert mine.status_code == 200
        assert mine.json()["total"] == 3
        # Pagination.
        page = await client.get("/api/v1/problems/me?limit=2", headers=bearer(token))
        assert len(page.json()["items"]) == 2
        assert page.json()["total"] == 3
        page2 = await client.get("/api/v1/problems/me?limit=2&skip=2", headers=bearer(token))
        assert len(page2.json()["items"]) == 1
        # Search by title / description / ticket.
        ticket = mine.json()["items"][0]["ticket_number"]
        for query in ["leak issue", "continuous water leak", ticket.lower()]:
            found = await client.get(f"/api/v1/problems/me?q={query}", headers=bearer(token))
            assert found.json()["total"] >= 1, query
        nomatch = await client.get("/api/v1/problems/me?q=zzz-no-such-thing", headers=bearer(token))
        assert nomatch.json()["total"] == 0
        # Status filter.
        sub = await client.get("/api/v1/problems/me?status=SUBMITTED", headers=bearer(token))
        assert sub.json()["total"] == 3
        # Withdraw one, filter again.
        await client.delete(
            f"/api/v1/problems/{mine.json()['items'][0]['id']}", headers=bearer(token)
        )
        sub2 = await client.get("/api/v1/problems/me?status=SUBMITTED", headers=bearer(token))
        assert sub2.json()["total"] == 2
        wd = await client.get("/api/v1/problems/me?status=WITHDRAWN", headers=bearer(token))
        assert wd.json()["total"] == 1
    finally:
        await delete_user(db_session, email)
        await delete_user(db_session, other_email)


@pytest.mark.asyncio
async def test_my_stats(client: AsyncClient, db_session: AsyncSession):
    email, token, _ = await make_user(client)
    try:
        assert (await client.get("/api/v1/problems/me/stats", headers=bearer(token))).json() == {
            "total": 0,
            "by_status": {},
        }
        p1 = (await create_problem(client, token)).json()
        await create_problem(client, token)
        await client.delete(f"/api/v1/problems/{p1['id']}", headers=bearer(token))
        stats = (await client.get("/api/v1/problems/me/stats", headers=bearer(token))).json()
        assert stats["total"] == 2
        assert stats["by_status"] == {"SUBMITTED": 1, "WITHDRAWN": 1}
    finally:
        await delete_user(db_session, email)


# ---------------- Attachments ----------------


async def upload(ac: AsyncClient, token: str, pid: str, filename: str, data: bytes, mime: str):  # type: ignore[no-untyped-def]
    return await ac.post(
        f"/api/v1/problems/{pid}/attachments",
        files={"file": (filename, data, mime)},
        headers=bearer(token),
    )


@pytest.mark.asyncio
async def test_attachment_valid_upload_and_metadata(
    client: AsyncClient, db_session: AsyncSession, tmp_storage
):
    email, token, _ = await make_user(client)
    try:
        pid = (await create_problem(client, token)).json()["id"]
        resp = await upload(client, token, pid, "leak.png", PNG_BYTES, "image/png")
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["original_filename"] == "leak.png"
        assert body["mime_type"] == "image/png"
        assert body["size_bytes"] == len(PNG_BYTES)
        # No internal paths leak.
        assert "stored_filename" not in body
        assert "storage" not in str(body).lower()
        assert "problem-attachments" not in str(body)
        listed = await client.get(f"/api/v1/problems/{pid}/attachments", headers=bearer(token))
        assert len(listed.json()) == 1
        # File actually on disk under tmp storage.
        assert any(tmp_storage.iterdir())
        # Activity recorded.
        acts = (await client.get(f"/api/v1/problems/{pid}/activity", headers=bearer(token))).json()
        assert "ATTACHMENT_ADDED" in [a["event_type"] for a in acts]
        # Owner can delete while SUBMITTED.
        delete = await client.delete(
            f"/api/v1/problems/{pid}/attachments/{body['id']}", headers=bearer(token)
        )
        assert delete.status_code == 204
        assert (
            await client.get(f"/api/v1/problems/{pid}/attachments", headers=bearer(token))
        ).json() == []
    finally:
        await delete_user(db_session, email)


@pytest.mark.asyncio
async def test_attachment_security(client: AsyncClient, db_session: AsyncSession, tmp_storage):
    email, token, _ = await make_user(client)
    try:
        pid = (await create_problem(client, token)).json()["id"]
        # Unsupported MIME.
        bad = await upload(client, token, pid, "notes.txt", TEXT_BYTES, "text/plain")
        assert bad.status_code == 415, bad.text
        # Sniff mismatch: declared PNG but actually text.
        spoof = await upload(client, token, pid, "evil.png", TEXT_BYTES, "image/png")
        assert spoof.status_code == 415, spoof.text
        # Executable disguised as PDF.
        exe = await upload(client, token, pid, "run.pdf", b"MZ" + b"\x00" * 200, "application/pdf")
        assert exe.status_code == 415, exe.text
        # Empty file.
        empty = await upload(client, token, pid, "empty.png", b"", "image/png")
        assert empty.status_code == 422, empty.text
        # Oversized (limit + 1, valid PNG header).
        big = await upload(
            client,
            token,
            pid,
            "big.png",
            b"\x89PNG\r\n\x1a\n" + b"\x00" * (10 * 1024 * 1024),
            "image/png",
        )
        assert big.status_code == 413, big.status_code
        # Path traversal filename is sanitized, upload still safe.
        trav = await upload(client, token, pid, "../../etc/passwd.png", PNG_BYTES, "image/png")
        assert trav.status_code == 201, trav.text
        assert trav.json()["original_filename"] == "passwd.png"
        assert ".." not in trav.json()["original_filename"]
    finally:
        await delete_user(db_session, email)


@pytest.mark.asyncio
async def test_attachment_ownership_and_limits(
    client: AsyncClient, db_session: AsyncSession, tmp_storage
):
    email_a, token_a, _ = await make_user(client)
    email_b, token_b, _ = await make_user(client)
    try:
        pid = (await create_problem(client, token_a)).json()["id"]
        # Stranger cannot attach to someone else's report.
        assert (
            await upload(client, token_b, pid, "x.png", PNG_BYTES, "image/png")
        ).status_code == 404
        # Stranger cannot delete either.
        mine = await upload(client, token_a, pid, "mine.png", PNG_BYTES, "image/png")
        assert mine.status_code == 201
        assert (
            await client.delete(
                f"/api/v1/problems/{pid}/attachments/{mine.json()['id']}", headers=bearer(token_b)
            )
        ).status_code == 404
        # Fill to the limit (5), 6th rejected.
        for i in range(4):
            r = await upload(client, token_a, pid, f"f{i}.png", PNG_BYTES, "image/png")
            assert r.status_code == 201, r.text
        over = await upload(client, token_a, pid, "sixth.png", PNG_BYTES, "image/png")
        assert over.status_code == 409
        # Deleting unknown attachment → 404.
        assert (
            await client.delete(
                f"/api/v1/problems/{pid}/attachments/{uuid4()}", headers=bearer(token_a)
            )
        ).status_code == 404
    finally:
        await delete_user(db_session, email_a)
        await delete_user(db_session, email_b)


# ---------------- Comments ----------------


@pytest.mark.asyncio
async def test_comments_visibility(client: AsyncClient, db_session: AsyncSession):
    email, token, _ = await make_user(client)
    admin_email, _, _ = await make_user(client, role="SOLVER")
    await promote_to_admin(db_session, admin_email)
    admin_token = (await login(client, admin_email)).json()["access_token"]
    try:
        pid = (await create_problem(client, token)).json()["id"]
        # Owner comment.
        c1 = await client.post(
            f"/api/v1/problems/{pid}/comments",
            json={"content": "Any update on this leak?"},
            headers=bearer(token),
        )
        assert c1.status_code == 201, c1.text
        assert c1.json()["is_internal"] is False
        # Admin internal comment.
        c2 = await client.post(
            f"/api/v1/problems/{pid}/comments",
            json={"content": "Assigned for review internally", "is_internal": True},
            headers=bearer(admin_token),
        )
        assert c2.status_code == 201, c2.text
        assert c2.json()["is_internal"] is True
        # Reporter cannot force internal.
        c3 = await client.post(
            f"/api/v1/problems/{pid}/comments",
            json={"content": "Trying internal flag", "is_internal": True},
            headers=bearer(token),
        )
        assert c3.json()["is_internal"] is False
        # Owner sees 2 public comments; admin sees all 3.
        owner_list = (
            await client.get(f"/api/v1/problems/{pid}/comments", headers=bearer(token))
        ).json()
        assert len(owner_list) == 2
        assert all(not c["is_internal"] for c in owner_list)
        admin_list = (
            await client.get(f"/api/v1/problems/{pid}/comments", headers=bearer(admin_token))
        ).json()
        assert len(admin_list) == 3
        # Stranger cannot comment.
        stranger_email, stranger_token, _ = await make_user(client)
        try:
            assert (
                await client.post(
                    f"/api/v1/problems/{pid}/comments",
                    json={"content": "hi"},
                    headers=bearer(stranger_token),
                )
            ).status_code == 404
        finally:
            await delete_user(db_session, stranger_email)
        # Empty comment rejected.
        assert (
            await client.post(
                f"/api/v1/problems/{pid}/comments", json={"content": "   "}, headers=bearer(token)
            )
        ).status_code == 422
    finally:
        await delete_user(db_session, email)
        await delete_user(db_session, admin_email)


# ---------------- Admin ----------------


@pytest.mark.asyncio
async def test_admin_list_and_filters(client: AsyncClient, db_session: AsyncSession):
    email, token, user_id = await make_user(client)
    admin_email, _, _ = await make_user(client, role="SOLVER")
    await promote_to_admin(db_session, admin_email)
    admin_token = (await login(client, admin_email)).json()["access_token"]
    try:
        p1 = (await create_problem(client, token, title="Canteen food quality concern here")).json()
        await create_problem(client, token, title="Library leak issue", affected_people_count=500)
        # Normal user forbidden.
        assert (
            await client.get("/api/v1/admin/problems", headers=bearer(token))
        ).status_code == 403
        assert (
            await client.get(f"/api/v1/admin/problems/{p1['id']}", headers=bearer(token))
        ).status_code == 403
        # Admin sees all with reporter info.
        all_resp = await client.get("/api/v1/admin/problems", headers=bearer(admin_token))
        assert all_resp.status_code == 200
        assert all_resp.json()["total"] >= 2
        assert all_resp.json()["items"][0]["reporter_email"] == email
        # Filters.
        by_status = await client.get(
            "/api/v1/admin/problems?status=SUBMITTED", headers=bearer(admin_token)
        )
        assert by_status.json()["total"] >= 2
        by_search = await client.get(
            "/api/v1/admin/problems?q=canteen food", headers=bearer(admin_token)
        )
        assert by_search.json()["total"] == 1
        by_reporter = await client.get(
            f"/api/v1/admin/problems?reporter_id={user_id}", headers=bearer(admin_token)
        )
        assert by_reporter.json()["total"] == 2
        by_affected = await client.get(
            "/api/v1/admin/problems?min_affected=400", headers=bearer(admin_token)
        )
        assert by_affected.json()["total"] == 1
        # Admin detail includes reporter + activity.
        detail = await client.get(f"/api/v1/admin/problems/{p1['id']}", headers=bearer(admin_token))
        assert detail.status_code == 200
        assert detail.json()["ticket_number"] == p1["ticket_number"]
        assert detail.json()["reporter"]["full_name"] == "Step4 User"
    finally:
        await delete_user(db_session, email)
        await delete_user(db_session, admin_email)


# ---------------- Regression (Steps 1-3) ----------------


@pytest.mark.asyncio
async def test_regression_auth_profile_skills_health(client: AsyncClient, db_session: AsyncSession):
    email = unique_email("regress")
    try:
        reg = await register(client, email, role="SOLVER")
        assert reg.status_code == 201
        token = reg.json()["access_token"]
        me = await client.get("/api/v1/auth/me", headers=bearer(token))
        assert me.status_code == 200
        profile = await client.get("/api/v1/profile/me", headers=bearer(token))
        assert profile.status_code == 200
        skills = await client.get("/api/v1/skills", headers=bearer(token))
        assert skills.status_code == 200
        assert len(skills.json()) >= 46
        health = await client.get("/api/v1/health")
        assert health.json()["status"] == "healthy"
        assert health.json()["pgvector_available"] is True
    finally:
        await delete_user(db_session, email)
