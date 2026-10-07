"""Step 12 tests: Knowledge Repository + semantic search + related solutions."""

from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import AvailabilityStatus, Department, ProficiencyLevel, UserRole
from app.main import app
from app.models.knowledge import KnowledgeEmbedding, KnowledgeEntry
from app.models.skill import Skill
from app.models.student_profile import StudentProfile
from app.models.user import User
from app.models.user_skill import UserSkill

PASSWORD = "Step12_Test_pass"

NETWORK_PAYLOAD = {
    "title": "Campus WiFi network keeps disconnecting in the computer lab",
    "description": "Students cannot access the internet in the computer lab because the WiFi "
    "network and Linux lab systems keep disconnecting during practical hours. "
    "The network switch may need inspection.",
    "location_text": "Computer Lab",
}

CCTV_PAYLOAD = {
    "title": "Main entrance CCTV camera stopped recording footage",
    "description": "The security camera at the college main gate is offline and has not "
    "recorded any footage for two days. The gate needs monitoring for student safety.",
    "location_text": "Main Gate",
}

SOLUTION_PAYLOAD = {
    "solution_summary": "Replaced the faulty lab switch and verified connectivity across the lab",
    "root_cause": "An aging access switch was dropping packets under load in the computer lab",
    "work_performed": "Diagnosed port errors, replaced the switch, re-terminated two uplinks, "
    "and load-tested the lab network through a full practical session.",
    "testing_performed": "Ping and iperf runs from every lab terminal for one hour.",
}

CCTV_SOLUTION = {
    "solution_summary": "Replaced the failed power adapter and re-aimed the gate camera",
    "root_cause": "The CCTV power supply unit had failed and the camera mount had slipped",
    "work_performed": "Installed a new 12V adapter, re-aimed the camera at the gate, "
    "and verified night recording for two evenings.",
    "testing_performed": "Reviewed two nights of footage; motion alerts firing correctly.",
}

PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\x0f"
    b"\x00\x01\x01\x01\x00\x1b\xb4\x0e\x9c\x00\x00\x00\x00IEND\xaeB`\x82"
)


def unique_email(prefix: str = "k12") -> str:
    return f"{prefix}_{uuid4().hex[:10]}@example.com"


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def register(ac: AsyncClient, email: str, role: str, name: str) -> dict:
    resp = await ac.post(
        "/api/v1/auth/register",
        json={"full_name": name, "email": email, "password": PASSWORD, "role": role},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def delete_user(session: AsyncSession, email: str) -> None:
    result = await session.execute(select(User).where(User.email == email.lower()))
    user = result.scalar_one_or_none()
    if user is not None:
        await session.delete(user)
        await session.commit()


async def skill_id(session: AsyncSession, name: str) -> UUID:
    result = await session.execute(select(Skill).where(Skill.name == name))
    return result.scalar_one().id


async def make_solver(ac, session, *, skills=()) -> tuple[str, str, str]:
    email = unique_email("k12solver")
    reg = await register(ac, email, "SOLVER", "K12 Solver")
    result = await session.execute(select(User).where(User.email == email.lower()))
    user = result.scalar_one()
    session.add(
        StudentProfile(
            user_id=user.id,
            student_identifier=f"K12{uuid4().hex[:8]}",
            department=Department.COMPUTER_SCIENCE_ENGINEERING,
            academic_year=3,
            availability_status=AvailabilityStatus.AVAILABLE,
            current_workload=0,
            max_workload=5,
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
    return email, reg["access_token"], str(user.id)


async def make_mentor(ac, session, *, skills=(), specialization="Networks") -> tuple[str, str, str]:
    from app.models.faculty_profile import FacultyProfile

    email = unique_email("k12mentor")
    await register(ac, email, "SOLVER", "K12 Mentor")
    result = await session.execute(select(User).where(User.email == email.lower()))
    user = result.scalar_one()
    user.role = UserRole.MENTOR
    session.add(
        FacultyProfile(
            user_id=user.id,
            employee_identifier=f"K12{uuid4().hex[:8]}",
            department=Department.COMPUTER_SCIENCE_ENGINEERING,
            designation="Assistant Professor",
            specialization=specialization,
            availability_status=AvailabilityStatus.AVAILABLE,
            current_workload=0,
            max_workload=5,
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
    token = (
        await ac.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    ).json()["access_token"]
    return email, token, str(user.id)


async def make_admin(ac, session) -> tuple[str, str]:
    email = unique_email("k12admin")
    await register(ac, email, "SOLVER", "K12 Admin")
    result = await session.execute(select(User).where(User.email == email.lower()))
    user = result.scalar_one()
    user.role = UserRole.ADMIN
    await session.commit()
    token = (
        await ac.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    ).json()["access_token"]
    return email, token


async def make_crew(ac, session) -> dict:
    """Reporter + solvers + mentor + admin, no problem yet."""
    rep = await register(ac, unique_email("k12rep"), "REPORTER", "K12 Reporter")
    s1 = await make_solver(
        ac, session, skills=[("Computer Networking", ProficiencyLevel.EXPERT)]
    )
    s2 = await make_solver(ac, session, skills=[("Linux", ProficiencyLevel.EXPERT)])
    m = await make_mentor(
        ac, session, skills=[("Computer Networking", ProficiencyLevel.EXPERT)], specialization="Networks"
    )
    admin_email, admin_token = await make_admin(ac, session)
    return {"rep": rep, "s1": s1, "s2": s2, "mentor": m, "admin": (admin_email, admin_token)}


async def cleanup_crew(session, ctx) -> None:
    for key in ("rep", "s1", "s2", "mentor", "admin"):
        entry = ctx[key]
        email = entry["user"]["email"] if isinstance(entry, dict) else entry[0]
        await delete_user(session, email)


async def create_problem(ac, ctx, payload) -> str:
    created = await ac.post(
        "/api/v1/problems", json=payload, headers=bearer(ctx["rep"]["access_token"])
    )
    assert created.status_code == 201, created.text
    return created.json()["id"]


async def drive_from_created(ac, ctx, solution, *, close=True) -> None:
    """Review → approve → assign → tasks → solution → approve → verify → close."""
    pid = ctx["pid"]
    admin_token = ctx["admin"][1]
    assert (
        await ac.post(
            f"/api/v1/admin/problems/{pid}/review/start", headers=bearer(admin_token)
        )
    ).status_code == 200
    assert (
        await ac.post(
            f"/api/v1/admin/problems/{pid}/approve", json={}, headers=bearer(admin_token)
        )
    ).status_code == 200
    assign = await ac.post(
        f"/api/v1/admin/problems/{pid}/assign",
        json={
            "solver_user_ids": [ctx["s1"][2], ctx["s2"][2]],
            "mentor_user_id": ctx["mentor"][2],
            "team_name": "K12 Crew",
            "team_override_reason": "Manual team for knowledge tests",
            "mentor_override_reason": "Manual mentor for knowledge tests",
        },
        headers=bearer(admin_token),
    )
    assert assign.status_code == 201, assign.text
    task = await ac.post(
        f"/api/v1/problems/{pid}/tasks",
        json={"title": "Fix the root cause fully"},
        headers=bearer(ctx["s1"][1]),
    )
    assert task.status_code == 201, task.text
    tid = task.json()["id"]
    for state in ("IN_PROGRESS", "DONE"):
        r = await ac.patch(
            f"/api/v1/problems/{pid}/tasks/{tid}",
            json={"status": state},
            headers=bearer(ctx["s1"][1]),
        )
        assert r.status_code == 200, r.text
    sub = await ac.post(
        f"/api/v1/problems/{pid}/solutions", json=solution, headers=bearer(ctx["s1"][1])
    )
    assert sub.status_code == 201, sub.text
    review = await ac.post(
        f"/api/v1/problems/{pid}/solutions/{sub.json()['id']}/review",
        json={"decision": "APPROVED", "comment": "Verified fix works"},
        headers=bearer(ctx["mentor"][1]),
    )
    assert review.status_code == 201, review.text
    verify = await ac.post(
        f"/api/v1/problems/{pid}/verifications",
        json={"decision": "RESOLVED"},
        headers=bearer(ctx["rep"]["access_token"]),
    )
    assert verify.status_code == 201, verify.text
    if close:
        await close_ctx(ac, ctx)


async def full_flow(ac, session, payload, solution, *, close=True) -> dict:
    """Drive a genuine report through the whole workflow to CLOSED."""
    ctx = await make_crew(ac, session)
    try:
        ctx["pid"] = await create_problem(ac, ctx, payload)
        await drive_from_created(ac, ctx, solution, close=close)
        return ctx
    except Exception:
        await cleanup_crew(session, ctx)
        raise


async def close_ctx(ac, ctx) -> None:
    close_resp = await ac.post(
        f"/api/v1/admin/problems/{ctx['pid']}/close",
        json={"reason": "Knowledge test closure"},
        headers=bearer(ctx["admin"][1]),
    )
    assert close_resp.status_code == 200, close_resp.text
    assert close_resp.json()["status"] == "CLOSED"


async def cleanup_ctx(session, ctx) -> None:
    for key in ("rep", "s1", "s2", "mentor", "admin"):
        entry = ctx[key]
        email = entry["user"]["email"] if isinstance(entry, dict) else entry[0]
        await delete_user(session, email)


async def entry_for_problem(session: AsyncSession, pid: str) -> KnowledgeEntry | None:
    result = await session.execute(
        select(KnowledgeEntry).where(KnowledgeEntry.problem_id == UUID(pid))
    )
    return result.scalar_one_or_none()


# ---------------- publication ----------------


@pytest.mark.asyncio
async def test_close_publishes_knowledge_entry(client: AsyncClient, db_session: AsyncSession):
    ctx = await full_flow(client, db_session, NETWORK_PAYLOAD, SOLUTION_PAYLOAD)
    try:
        entry = await entry_for_problem(db_session, ctx["pid"])
        assert entry is not None
        assert entry.publication_status == "PUBLISHED"
        assert entry.is_published is True
        assert entry.public_id.startswith("KB-")
        assert entry.published_at is not None
        # Snapshot fields come from the real objects, nothing invented.
        assert "WiFi" in entry.title
        assert "computer lab" in entry.problem_summary
        assert entry.final_category is not None
        assert entry.root_cause is not None
        assert "switch" in entry.root_cause
        assert entry.solution_summary is not None
        assert "switch" in entry.solution_summary
        assert entry.work_performed is not None
        assert "uplinks" in entry.work_performed
        assert entry.testing_performed is not None
        assert "iperf" in entry.testing_performed
        assert entry.resolution_duration_minutes is not None
        assert entry.resolution_duration_minutes >= 0
        assert entry.source_text_hash is not None
        assert len(entry.source_text_hash) == 64
        # Safe attribution only.
        assert entry.team_names
        assert all("@" not in n for n in entry.team_names)
        assert entry.mentor_name is not None
        assert "@" not in entry.mentor_name
        assert entry.mentor_designation == "Assistant Professor"
        # Skills copied from the real extraction.
        result = await db_session.execute(select(func.count()).select_from(KnowledgeEntry))
        assert result.scalar_one() >= 1
        # Embedding present, 384 dims, single row.
        emb = (
            await db_session.execute(
                select(KnowledgeEmbedding).where(KnowledgeEmbedding.knowledge_entry_id == entry.id)
            )
        ).scalar_one()
        assert len(list(emb.embedding)) == 384
        assert emb.embedding_version == "campusxolve-knowledge-embedding-v1"
    finally:
        await cleanup_ctx(db_session, ctx)


@pytest.mark.asyncio
async def test_ineligible_open_problem_has_no_entry(
    client: AsyncClient, db_session: AsyncSession
):
    email = unique_email("k12rep")
    reg = await register(client, email, "REPORTER", "K12 Reporter")
    try:
        created = await client.post(
            "/api/v1/problems", json=NETWORK_PAYLOAD, headers=bearer(reg["access_token"])
        )
        assert created.status_code == 201, created.text
        assert await entry_for_problem(db_session, created.json()["id"]) is None
        listed = (
            await client.get("/api/v1/admin/knowledge", headers=bearer(reg["access_token"]))
        )
        assert listed.status_code == 403
    finally:
        await delete_user(db_session, email)


@pytest.mark.asyncio
async def test_publication_idempotent(client: AsyncClient, db_session: AsyncSession):
    ctx = await full_flow(client, db_session, NETWORK_PAYLOAD, SOLUTION_PAYLOAD)
    try:
        from app.services.knowledge_service import KnowledgeService

        service = KnowledgeService(db_session)
        first = await entry_for_problem(db_session, ctx["pid"])
        assert first is not None
        assert await service.publish_for_problem(UUID(ctx["pid"])) == "PUBLISHED"
        assert await service.publish_for_problem(UUID(ctx["pid"])) == "PUBLISHED"
        rows = (
            await db_session.execute(
                select(KnowledgeEntry).where(KnowledgeEntry.problem_id == UUID(ctx["pid"]))
            )
        ).scalars().all()
        assert len(rows) == 1
        embs = (
            await db_session.execute(
                select(KnowledgeEmbedding).where(KnowledgeEmbedding.knowledge_entry_id == first.id)
            )
        ).scalars().all()
        assert len(embs) == 1
    finally:
        await cleanup_ctx(db_session, ctx)


@pytest.mark.asyncio
async def test_duplicate_member_excluded_canonical_publishes(
    client: AsyncClient, db_session: AsyncSession
):
    # A is still SUBMITTED (visible to duplicate analysis) when B is
    # confirmed as its duplicate; only the canonical closed issue may publish.
    ctx_a = await make_crew(client, db_session)
    rep_b = None
    admin_email = None
    try:
        ctx_a["pid"] = await create_problem(client, ctx_a, NETWORK_PAYLOAD)
        rep_b = await register(client, unique_email("k12rep"), "REPORTER", "K12 Reporter B")
        admin_email, admin_token = await make_admin(client, db_session)
        created = await client.post(
            "/api/v1/problems", json=NETWORK_PAYLOAD, headers=bearer(rep_b["access_token"])
        )
        assert created.status_code == 201, created.text
        pid_b = created.json()["id"]
        dups = (
            await client.get(
                f"/api/v1/problems/{pid_b}/duplicates", headers=bearer(rep_b["access_token"])
            )
        ).json()
        cand = next(
            c for c in dups["candidates"] if c["candidate"]["id"] == ctx_a["pid"]
        )
        confirm = await client.post(
            f"/api/v1/admin/duplicate-candidates/{cand['id']}/confirm",
            json={},
            headers=bearer(admin_token),
        )
        assert confirm.status_code == 200, confirm.text
        await drive_from_created(client, ctx_a, SOLUTION_PAYLOAD, close=True)
        # Canonical publishes; the duplicate member must not.
        assert await entry_for_problem(db_session, ctx_a["pid"]) is not None
        assert await entry_for_problem(db_session, pid_b) is None
    finally:
        await cleanup_crew(db_session, ctx_a)
        if rep_b is not None:
            await delete_user(db_session, rep_b["user"]["email"])
        if admin_email is not None:
            await delete_user(db_session, admin_email)


@pytest.mark.asyncio
async def test_only_shareable_evidence_published(
    client: AsyncClient, db_session: AsyncSession
):
    rep = await register(client, unique_email("k12rep"), "REPORTER", "K12 Reporter")
    s1 = await make_solver(
        client, db_session, skills=[("Computer Networking", ProficiencyLevel.EXPERT)]
    )
    s2 = await make_solver(client, db_session, skills=[("Linux", ProficiencyLevel.EXPERT)])
    m = await make_mentor(client, db_session, skills=[], specialization="Networks")
    admin_email, admin_token = await make_admin(client, db_session)
    try:
        created = await client.post(
            "/api/v1/problems", json=NETWORK_PAYLOAD, headers=bearer(rep["access_token"])
        )
        pid = created.json()["id"]
        assert (
            await client.post(
                f"/api/v1/admin/problems/{pid}/review/start", headers=bearer(admin_token)
            )
        ).status_code == 200
        assert (
            await client.post(
                f"/api/v1/admin/problems/{pid}/approve", json={}, headers=bearer(admin_token)
            )
        ).status_code == 200
        assign = await client.post(
            f"/api/v1/admin/problems/{pid}/assign",
            json={
                "solver_user_ids": [s1[2], s2[2]],
                "mentor_user_id": m[2],
                "team_name": "K12 Ev Crew",
                "team_override_reason": "evidence test",
                "mentor_override_reason": "evidence test",
            },
            headers=bearer(admin_token),
        )
        assert assign.status_code == 201, assign.text
        task = await client.post(
            f"/api/v1/problems/{pid}/tasks",
            json={"title": "Fix it all"},
            headers=bearer(s1[1]),
        )
        tid = task.json()["id"]
        for state in ("IN_PROGRESS", "DONE"):
            assert (
                await client.patch(
                    f"/api/v1/problems/{pid}/tasks/{tid}",
                    json={"status": state},
                    headers=bearer(s1[1]),
                )
            ).status_code == 200
        private_up = await client.post(
            f"/api/v1/problems/{pid}/work-files",
            files={"file": ("private.png", PNG, "image/png")},
            data={"description": "internal only"},
            headers=bearer(s1[1]),
        )
        assert private_up.status_code == 201, private_up.text
        assert private_up.json()["is_knowledge_shareable"] is False
        shared_up = await client.post(
            f"/api/v1/problems/{pid}/work-files",
            files={"file": ("shared.png", PNG, "image/png")},
            data={"description": "safe to share", "is_knowledge_shareable": "true"},
            headers=bearer(s1[1]),
        )
        assert shared_up.status_code == 201, shared_up.text
        assert shared_up.json()["is_knowledge_shareable"] is True
        payload = dict(
            SOLUTION_PAYLOAD,
            evidence_attachment_ids=[private_up.json()["id"], shared_up.json()["id"]],
        )
        sub = await client.post(
            f"/api/v1/problems/{pid}/solutions", json=payload, headers=bearer(s1[1])
        )
        assert sub.status_code == 201, sub.text
        assert (
            await client.post(
                f"/api/v1/problems/{pid}/solutions/{sub.json()['id']}/review",
                json={"decision": "APPROVED"},
                headers=bearer(m[1]),
            )
        ).status_code == 201
        assert (
            await client.post(
                f"/api/v1/problems/{pid}/verifications",
                json={"decision": "RESOLVED"},
                headers=bearer(rep["access_token"]),
            )
        ).status_code == 201
        assert (
            await client.post(
                f"/api/v1/admin/problems/{pid}/close", json={}, headers=bearer(admin_token)
            )
        ).status_code == 200
        entry = await entry_for_problem(db_session, pid)
        assert entry is not None
        assert len(entry.evidence_files) == 1
        assert entry.evidence_files[0]["original_filename"] == "shared.png"
        # Download works for the flagged file only.
        dl = await client.get(
            f"/api/v1/knowledge/{entry.public_id}/evidence/{shared_up.json()['id']}/download",
            headers=bearer(rep["access_token"]),
        )
        assert dl.status_code == 200, dl.text
        assert dl.content == PNG
        missing = await client.get(
            f"/api/v1/knowledge/{entry.public_id}/evidence/{private_up.json()['id']}/download",
            headers=bearer(rep["access_token"]),
        )
        assert missing.status_code == 404
    finally:
        for email in (rep["user"]["email"], s1[0], s2[0], m[0], admin_email):
            await delete_user(session=db_session, email=email)


# ---------------- search ----------------


@pytest.mark.asyncio
async def test_keyword_search_case_insensitive_and_pagination(
    client: AsyncClient, db_session: AsyncSession
):
    ctx = await full_flow(client, db_session, NETWORK_PAYLOAD, SOLUTION_PAYLOAD)
    try:
        token = ctx["rep"]["access_token"]
        upper = await client.get(
            "/api/v1/knowledge",
            params={"q": "WIFI", "search_mode": "KEYWORD"},
            headers=bearer(token),
        )
        assert upper.status_code == 200, upper.text
        assert upper.json()["total"] >= 1
        assert any("WiFi" in item["title"] for item in upper.json()["items"])
        page = await client.get(
            "/api/v1/knowledge",
            params={"q": "wifi", "search_mode": "KEYWORD", "page": 1, "page_size": 1},
            headers=bearer(token),
        )
        assert page.json()["page_size"] == 1
        assert page.json()["total"] >= 1
        unauth = await client.get("/api/v1/knowledge", headers=bearer("bad"))
        assert unauth.status_code == 401
    finally:
        await cleanup_ctx(db_session, ctx)


@pytest.mark.asyncio
async def test_semantic_search_returns_real_scores(
    client: AsyncClient, db_session: AsyncSession
):
    ctx = await full_flow(client, db_session, NETWORK_PAYLOAD, SOLUTION_PAYLOAD)
    try:
        resp = await client.get(
            "/api/v1/knowledge",
            params={
                "q": "internet keeps dropping where students study in library",
                "search_mode": "SEMANTIC",
            },
            headers=bearer(ctx["rep"]["access_token"]),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["semantic_available"] is True
        assert body["total"] >= 1
        top = body["items"][0]
        assert top["semantic_similarity"] >= 0.35
        assert top["semantic_similarity"] <= 1.0
    finally:
        await cleanup_ctx(db_session, ctx)


@pytest.mark.asyncio
async def test_negative_semantic_result_not_relevant(
    client: AsyncClient, db_session: AsyncSession
):
    ctx = await full_flow(client, db_session, NETWORK_PAYLOAD, SOLUTION_PAYLOAD)
    try:
        resp = await client.get(
            "/api/v1/knowledge",
            params={"q": "washroom water leakage plumbing repair", "search_mode": "SEMANTIC"},
            headers=bearer(ctx["rep"]["access_token"]),
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["items"] == []
    finally:
        await cleanup_ctx(db_session, ctx)


@pytest.mark.asyncio
async def test_filters_combined(client: AsyncClient, db_session: AsyncSession):
    ctx = await full_flow(client, db_session, NETWORK_PAYLOAD, SOLUTION_PAYLOAD)
    try:
        token = ctx["rep"]["access_token"]
        entry = await entry_for_problem(db_session, ctx["pid"])
        assert entry is not None
        assert entry.final_category is not None
        by_cat = await client.get(
            "/api/v1/knowledge",
            params={"category": entry.final_category},
            headers=bearer(token),
        )
        assert by_cat.json()["total"] >= 1
        assert (
            await client.get(
                "/api/v1/knowledge", params={"category": "NO_SUCH_CATEGORY"}, headers=bearer(token)
            )
        ).json()["total"] == 0
        by_loc = await client.get(
            "/api/v1/knowledge", params={"location": "Computer Lab"}, headers=bearer(token)
        )
        assert by_loc.json()["total"] >= 1
        assert (
            await client.get(
                "/api/v1/knowledge", params={"location": "Nowhere Hall"}, headers=bearer(token)
            )
        ).json()["total"] == 0
        linux_id = await skill_id(db_session, "Linux")
        by_skill = await client.get(
            "/api/v1/knowledge", params={"skill_id": str(linux_id)}, headers=bearer(token)
        )
        assert by_skill.json()["total"] >= 1
        by_date = await client.get(
            "/api/v1/knowledge",
            params={"published_from": "2000-01-01T00:00:00Z", "published_to": "2100-01-01T00:00:00Z"},
            headers=bearer(token),
        )
        assert by_date.json()["total"] >= 1
        assert (
            await client.get(
                "/api/v1/knowledge",
                params={"published_from": "2100-01-01T00:00:00Z"},
                headers=bearer(token),
            )
        ).json()["total"] == 0
    finally:
        await cleanup_ctx(db_session, ctx)


# ---------------- detail / related ----------------


@pytest.mark.asyncio
async def test_detail_and_related(client: AsyncClient, db_session: AsyncSession):
    ctx_a = await full_flow(client, db_session, NETWORK_PAYLOAD, SOLUTION_PAYLOAD)
    ctx_b = await full_flow(client, db_session, CCTV_PAYLOAD, CCTV_SOLUTION)
    try:
        token = ctx_a["rep"]["access_token"]
        entry_a = await entry_for_problem(db_session, ctx_a["pid"])
        assert entry_a is not None
        detail = await client.get(
            f"/api/v1/knowledge/{entry_a.public_id}", headers=bearer(token)
        )
        assert detail.status_code == 200, detail.text
        body = detail.json()
        assert body["solution_summary"] is not None
        assert "switch" in body["solution_summary"]
        assert body["team_names"]
        assert all("@" not in n for n in body["team_names"])
        assert body["mentor_designation"] == "Assistant Professor"
        assert len(body["related"]) >= 1
        assert all(r["entry"]["public_id"] != entry_a.public_id for r in body["related"])
        rel = await client.get(
            f"/api/v1/knowledge/{entry_a.public_id}/related", headers=bearer(token)
        )
        assert rel.status_code == 200, rel.text
        for item in rel.json()["items"]:
            assert item["entry"]["id"] != str(entry_a.id)
        assert (
            await client.get("/api/v1/knowledge/KB-999999", headers=bearer(token))
        ).status_code == 404
    finally:
        await cleanup_ctx(db_session, ctx_a)
        await cleanup_ctx(db_session, ctx_b)


@pytest.mark.asyncio
async def test_related_solutions_for_open_problem(
    client: AsyncClient, db_session: AsyncSession
):
    ctx = await full_flow(client, db_session, NETWORK_PAYLOAD, SOLUTION_PAYLOAD)
    rep_b = await register(client, unique_email("k12rep"), "REPORTER", "K12 Reporter B")
    outsider = await register(client, unique_email("k12rep"), "REPORTER", "K12 Outsider")
    try:
        created = await client.post(
            "/api/v1/problems", json=NETWORK_PAYLOAD, headers=bearer(rep_b["access_token"])
        )
        assert created.status_code == 201, created.text
        pid = created.json()["id"]
        related = await client.get(
            f"/api/v1/problems/{pid}/related-solutions",
            headers=bearer(rep_b["access_token"]),
        )
        assert related.status_code == 200, related.text
        assert related.json()["semantic_available"] is True
        assert related.json()["items"], "open wifi report should match the wifi article"
        assert all(
            "duplicate" not in (item["entry"]["title"] or "").lower()
            for item in related.json()["items"]
        )
        forbidden = await client.get(
            f"/api/v1/problems/{pid}/related-solutions",
            headers=bearer(outsider["access_token"]),
        )
        assert forbidden.status_code == 404
    finally:
        await cleanup_ctx(db_session, ctx)
        await delete_user(db_session, rep_b["user"]["email"])
        await delete_user(db_session, outsider["user"]["email"])


# ---------------- privacy ----------------


@pytest.mark.asyncio
async def test_no_private_data_leaks(client: AsyncClient, db_session: AsyncSession):
    ctx = await full_flow(client, db_session, NETWORK_PAYLOAD, SOLUTION_PAYLOAD)
    try:
        token = ctx["rep"]["access_token"]
        entry = await entry_for_problem(db_session, ctx["pid"])
        assert entry is not None
        bodies = [
            (await client.get("/api/v1/knowledge", params={"q": "wifi"}, headers=bearer(token))).text,
            (
                await client.get(f"/api/v1/knowledge/{entry.public_id}", headers=bearer(token))
            ).text,
            (
                await client.get(
                    f"/api/v1/knowledge/{entry.public_id}/related", headers=bearer(token)
                )
            ).text,
            (
                await client.get(
                    "/api/v1/admin/knowledge", headers=bearer(ctx["admin"][1])
                )
            ).text,
        ]
        banned = [
            "@example.com",
            "student_identifier",
            "employee_identifier",
            "current_workload",
            "password",
            "access_token",
            "refresh_token",
        ]
        for body in bodies:
            lowered = body.lower()
            for marker in banned:
                assert marker not in lowered, marker
    finally:
        await cleanup_ctx(db_session, ctx)


# ---------------- admin lifecycle ----------------


@pytest.mark.asyncio
async def test_archive_hides_and_unarchive_restores(
    client: AsyncClient, db_session: AsyncSession
):
    ctx = await full_flow(client, db_session, NETWORK_PAYLOAD, SOLUTION_PAYLOAD)
    try:
        admin = bearer(ctx["admin"][1])
        entry = await entry_for_problem(db_session, ctx["pid"])
        assert entry is not None
        listed = await client.get("/api/v1/admin/knowledge", headers=admin)
        assert listed.status_code == 200
        assert any(e["public_id"] == entry.public_id for e in listed.json())
        assert (
            await client.patch(
                f"/api/v1/admin/knowledge/{entry.id}/archive", headers=admin
            )
        ).status_code == 200
        assert (
            await client.get("/api/v1/knowledge", params={"q": "wifi"}, headers=admin)
        ).json()["total"] == 0
        assert (
            await client.get(f"/api/v1/knowledge/{entry.public_id}", headers=admin)
        ).status_code == 404
        un = await client.patch(
            f"/api/v1/admin/knowledge/{entry.id}/unarchive", headers=admin
        )
        assert un.status_code == 200, un.text
        assert un.json()["publication_status"] == "PUBLISHED"
        assert (
            await client.get("/api/v1/knowledge", params={"q": "wifi"}, headers=admin)
        ).json()["total"] >= 1
    finally:
        await cleanup_ctx(db_session, ctx)


@pytest.mark.asyncio
async def test_retry_failed_publication(client: AsyncClient, db_session: AsyncSession):
    ctx = await full_flow(client, db_session, NETWORK_PAYLOAD, SOLUTION_PAYLOAD)
    try:
        admin = bearer(ctx["admin"][1])
        entry = await entry_for_problem(db_session, ctx["pid"])
        assert entry is not None
        entry.publication_status = "FAILED"
        entry.is_published = False
        entry.failure_reason = "simulated outage"
        await db_session.commit()
        retry = await client.post(
            f"/api/v1/admin/knowledge/{entry.id}/retry", headers=admin
        )
        assert retry.status_code == 200, retry.text
        assert retry.json()["publication_status"] == "PUBLISHED"
        refreshed = await entry_for_problem(db_session, ctx["pid"])
        assert refreshed is not None
        await db_session.refresh(refreshed)
        assert refreshed.is_published is True
    finally:
        await cleanup_ctx(db_session, ctx)


@pytest.mark.asyncio
async def test_semantic_failure_falls_back_to_keyword(
    client: AsyncClient, db_session: AsyncSession, monkeypatch
):
    ctx = await full_flow(client, db_session, NETWORK_PAYLOAD, SOLUTION_PAYLOAD)
    try:
        token = ctx["rep"]["access_token"]
        import app.ml.skills.embeddings as emb

        def _boom(*args, **kwargs):
            raise RuntimeError("model down")

        monkeypatch.setattr(emb, "get_embedding_model", _boom)
        sem = await client.get(
            "/api/v1/knowledge",
            params={"q": "wifi", "search_mode": "SEMANTIC"},
            headers=bearer(token),
        )
        assert sem.status_code == 200, sem.text
        assert sem.json()["semantic_available"] is False
        assert sem.json()["items"] == []
        kw = await client.get(
            "/api/v1/knowledge",
            params={"q": "wifi", "search_mode": "KEYWORD"},
            headers=bearer(token),
        )
        assert kw.status_code == 200, kw.text
        assert kw.json()["total"] >= 1
    finally:
        await cleanup_ctx(db_session, ctx)


@pytest.mark.asyncio
async def test_admin_knowledge_requires_admin(
    client: AsyncClient, db_session: AsyncSession
):
    ctx = await full_flow(client, db_session, NETWORK_PAYLOAD, SOLUTION_PAYLOAD)
    try:
        entry = await entry_for_problem(db_session, ctx["pid"])
        assert entry is not None
        solver = bearer(ctx["s1"][1])
        assert (await client.get("/api/v1/admin/knowledge", headers=solver)).status_code == 403
        assert (
            await client.post(f"/api/v1/admin/knowledge/{entry.id}/retry", headers=solver)
        ).status_code == 403
        assert (
            await client.patch(f"/api/v1/admin/knowledge/{entry.id}/archive", headers=solver)
        ).status_code == 403
    finally:
        await cleanup_ctx(db_session, ctx)
