"""Step 7 tests: embeddings, candidates, clusters, merges, permissions, negatives."""

from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.enums import UserRole
from app.main import app
from app.ml.duplicates.text import (
    category_support,
    final_match_score,
    location_support,
    normalize_location,
)
from app.models.problem_analysis import ProblemPriorityAnalysis
from app.models.problem_duplicate import ProblemEmbedding
from app.models.user import User

PASSWORD = "Step7_Test_pass"


def unique_email(prefix: str = "step7") -> str:
    return f"{prefix}_{uuid4().hex[:10]}@example.com"


def water_a() -> dict[str, object]:
    return {
        "title": "Drinking water unit near CSE block is empty",
        "description": "The drinking water unit near the CSE block has been empty since morning "
        "and students have no place to refill bottles.",
        "location_text": "CSE Block",
    }


def water_b() -> dict[str, object]:
    return {
        "title": "No water at CSE drinking station",
        "description": "No water is available at the CSE drinking station today, "
        "and students are struggling in this heat.",
        "location_text": "CSE Block",
    }


def wifi_a() -> dict[str, object]:
    return {
        "title": "Library WiFi keeps disconnecting",
        "description": "The WiFi in the central library keeps disconnecting every few minutes "
        "and students cannot attend online classes.",
        "location_text": "Central Library",
    }


def wifi_b() -> dict[str, object]:
    return {
        "title": "Internet drops inside library reading hall",
        "description": "Students cannot maintain a stable internet connection while sitting "
        "in the library reading hall during study hours.",
        "location_text": "Library Reading Hall",
    }


def hostel_clean() -> dict[str, object]:
    return {
        "title": "Hostel corridors not cleaned",
        "description": "The hostel corridors have not been cleaned for a week "
        "and garbage is piling up near the rooms.",
        "location_text": "Boys Hostel",
    }


def hostel_power() -> dict[str, object]:
    return {
        "title": "Hostel power cuts every evening",
        "description": "Hostel rooms face frequent power cuts every evening "
        "and students cannot study after dark.",
        "location_text": "Boys Hostel",
    }


# ---------------- Pure text utils ----------------


def test_location_support():
    assert location_support(set(), set()) == 0.5
    assert location_support({"library"}, set()) == 0.0
    assert location_support({"library"}, {"library"}) == 1.0
    assert 0.0 < location_support({"central", "library"}, {"library", "reading", "hall"}) < 1.0
    # Generic tokens are ignored: "Main Campus Block" carries no signal.
    assert normalize_location("Main Campus Block", None, None) == set()


def test_category_support_never_vetoes():
    assert category_support("IT_NETWORK", "IT_NETWORK") == 1.0
    assert category_support("IT_NETWORK", "LIBRARY") == 0.0
    assert category_support(None, "LIBRARY") == 0.0


def test_final_match_semantic_dominates():
    assert final_match_score(0.9, 1.0, 1.0) == round(0.9 * 0.85 + 0.10 + 0.05, 4)
    assert final_match_score(0.5, 1.0, 1.0) < 0.6


# ---------------- API ----------------


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def register(ac: AsyncClient, email: str, role: str = "REPORTER"):
    return await ac.post(
        "/api/v1/auth/register",
        json={"full_name": "Step7 User", "email": email, "password": PASSWORD, "role": role},
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


async def create(ac: AsyncClient, token: str, payload: dict[str, object]) -> dict[str, object]:
    resp = await ac.post("/api/v1/problems", json=payload, headers=bearer(token))
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert isinstance(body, dict)
    return body


@pytest.mark.asyncio
async def test_embedding_persisted_and_idempotent(client: AsyncClient, db_session: AsyncSession):
    email, token, _ = await make_user(client)
    try:
        pid = (await create(client, token, water_a()))["id"]
        assert isinstance(pid, str)
        rows = (
            (
                await db_session.execute(
                    select(ProblemEmbedding).where(ProblemEmbedding.problem_id == pid)
                )
            )
            .scalars()
            .all()
        )
        assert len(rows) == 1
        assert len(rows[0].embedding) == 384
        assert rows[0].model_version == settings.PROBLEM_EMBEDDING_VERSION
        first_hash = rows[0].source_text_hash
        # Admin reanalyze must not duplicate the embedding row.
        admin_email, admin_token = await make_admin(client, db_session)
        try:
            assert (
                await client.post(
                    f"/api/v1/admin/problems/{pid}/duplicates/reanalyze",
                    headers=bearer(admin_token),
                )
            ).status_code == 200
            count = (
                await db_session.execute(
                    select(func.count())
                    .select_from(ProblemEmbedding)
                    .where(ProblemEmbedding.problem_id == pid)
                )
            ).scalar_one()
            assert count == 1
        finally:
            await delete_user(db_session, admin_email)
        # Detail shows duplicate analysis state.
        detail = (await client.get(f"/api/v1/problems/{pid}", headers=bearer(token))).json()
        assert detail["duplicate_status"] in ("NO_MATCHES", "POSSIBLE_DUPLICATES")
        _ = first_hash
    finally:
        await delete_user(db_session, email)


@pytest.mark.asyncio
async def test_edit_recomputes_embedding(client: AsyncClient, db_session: AsyncSession):
    email, token, _ = await make_user(client)
    try:
        pid = (await create(client, token, water_a()))["id"]
        assert isinstance(pid, str)
        before = (
            (
                await db_session.execute(
                    select(ProblemEmbedding).where(ProblemEmbedding.problem_id == pid)
                )
            )
            .scalars()
            .one()
            .source_text_hash
        )
        resp = await client.patch(
            f"/api/v1/problems/{pid}",
            json={
                "description": "The drinking water unit near the CSE block is completely dry and the queue is huge."
            },
            headers=bearer(token),
        )
        assert resp.status_code == 200, resp.text
        after = (
            (
                await db_session.execute(
                    select(ProblemEmbedding).where(ProblemEmbedding.problem_id == pid)
                )
            )
            .scalars()
            .one()
            .source_text_hash
        )
        assert after != before
    finally:
        await delete_user(db_session, email)


@pytest.mark.asyncio
async def test_paraphrase_candidate_and_self_excluded(
    client: AsyncClient, db_session: AsyncSession
):
    email_a, token_a, _ = await make_user(client)
    email_b, token_b, _ = await make_user(client)
    try:
        a_id = (await create(client, token_a, water_a()))["id"]
        b_body = await create(client, token_b, water_b())
        b_id = b_body["id"]
        assert isinstance(a_id, str)
        assert isinstance(b_id, str)
        dupes = await client.get(f"/api/v1/problems/{b_id}/duplicates", headers=bearer(token_b))
        assert dupes.status_code == 200, dupes.text
        body = dupes.json()
        assert body["analysis_status"] == "POSSIBLE_DUPLICATES"
        assert len(body["candidates"]) >= 1
        match = next(c for c in body["candidates"] if c["candidate"]["id"] == a_id)
        assert 0.0 <= match["semantic_similarity"] <= 1.0
        assert match["semantic_similarity"] >= 0.60
        assert 0.0 <= match["final_match_score"] <= 1.0
        assert match["decision_status"] == "PENDING"
        assert match["candidate"]["ticket_number"]
        # No reporter identity leaks.
        assert "email" not in match["candidate"]
        assert "reporter" not in match["candidate"]
        # Self never suggested; A (created first) has no suggestion for B yet.
        assert all(c["candidate"]["id"] != b_id for c in body["candidates"])
        a_dupes = (
            await client.get(f"/api/v1/problems/{a_id}/duplicates", headers=bearer(token_a))
        ).json()
        assert all(c["candidate"]["id"] != b_id for c in a_dupes["candidates"])
    finally:
        await delete_user(db_session, email_a)
        await delete_user(db_session, email_b)


@pytest.mark.asyncio
async def test_pair_uniqueness_and_stale(client: AsyncClient, db_session: AsyncSession):
    email_a, token_a, _ = await make_user(client)
    email_b, token_b, _ = await make_user(client)
    admin_email, admin_token = await make_admin(client, db_session)
    try:
        a_id = (await create(client, token_a, wifi_a()))["id"]
        b_id = (await create(client, token_b, wifi_b()))["id"]
        assert isinstance(a_id, str)
        assert isinstance(b_id, str)
        first = (
            await client.get(f"/api/v1/problems/{b_id}/duplicates", headers=bearer(token_b))
        ).json()
        assert len([c for c in first["candidates"] if c["candidate"]["id"] == a_id]) == 1
        # Reanalyze: old PENDING goes STALE, exactly one live suggestion remains.
        assert (
            await client.post(
                f"/api/v1/admin/problems/{b_id}/duplicates/reanalyze", headers=bearer(admin_token)
            )
        ).status_code == 200
        second = (
            await client.get(f"/api/v1/problems/{b_id}/duplicates", headers=bearer(token_b))
        ).json()
        live = [c for c in second["candidates"] if c["candidate"]["id"] == a_id]
        assert len(live) == 1
        assert live[0]["decision_status"] == "PENDING"
    finally:
        await delete_user(db_session, email_a)
        await delete_user(db_session, email_b)
        await delete_user(db_session, admin_email)


@pytest.mark.asyncio
async def test_duplicates_permissions(client: AsyncClient, db_session: AsyncSession):
    email, token, _ = await make_user(client)
    stranger_email, stranger_token, _ = await make_user(client)
    try:
        pid = (await create(client, token, water_a()))["id"]
        assert isinstance(pid, str)
        assert (await client.get(f"/api/v1/problems/{pid}/duplicates")).status_code == 401
        assert (
            await client.get(f"/api/v1/problems/{pid}/duplicates", headers=bearer(stranger_token))
        ).status_code == 404
        assert (
            await client.post(
                f"/api/v1/admin/problems/{pid}/duplicates/reanalyze", headers=bearer(token)
            )
        ).status_code == 403
    finally:
        await delete_user(db_session, email)
        await delete_user(db_session, stranger_email)


@pytest.mark.asyncio
async def test_confirm_creates_cluster_and_recounts(client: AsyncClient, db_session: AsyncSession):
    email_a, token_a, _ = await make_user(client)
    email_b, token_b, _ = await make_user(client)
    admin_email, admin_token = await make_admin(client, db_session)
    try:
        a_body = await create(client, token_a, water_a())
        b_body = await create(client, token_b, water_b())
        a_id, b_id = a_body["id"], b_body["id"]
        assert isinstance(a_id, str)
        assert isinstance(b_id, str)
        before = (await client.get(f"/api/v1/problems/{a_id}", headers=bearer(token_a))).json()[
            "priority_score"
        ]
        cand = next(
            c
            for c in (
                await client.get(f"/api/v1/problems/{b_id}/duplicates", headers=bearer(token_b))
            ).json()["candidates"]
            if c["candidate"]["id"] == a_id
        )
        # Reporter cannot confirm.
        assert (
            await client.post(
                f"/api/v1/admin/duplicate-candidates/{cand['id']}/confirm",
                json={},
                headers=bearer(token_b),
            )
        ).status_code == 403
        confirmed = await client.post(
            f"/api/v1/admin/duplicate-candidates/{cand['id']}/confirm",
            json={"review_note": "Same water unit"},
            headers=bearer(admin_token),
        )
        assert confirmed.status_code == 200, confirmed.text
        cluster = confirmed.json()
        assert cluster["cluster_number"].startswith("DC-")
        assert len(cluster["members"]) == 2
        # Oldest report (A) is canonical.
        canonical = next(m for m in cluster["members"] if m["is_canonical"])
        assert canonical["problem_id"] == a_id
        # Member points at canonical with DUPLICATE status.
        b_detail = (await client.get(f"/api/v1/problems/{b_id}", headers=bearer(token_b))).json()
        assert b_detail["status"] == "DUPLICATE"
        assert b_detail["canonical"]["ticket_number"] == a_body["ticket_number"]
        # Priority recounted with real duplicate count.
        a_detail = (await client.get(f"/api/v1/problems/{a_id}", headers=bearer(token_a))).json()
        assert a_detail["priority_score"] is not None
        assert before is not None
        assert a_detail["priority_score"] >= before
        dup_comp = a_detail["priority"]["component_details"]["components"]
        dup = next(c for c in dup_comp if c["component"] == "duplicate_impact")
        assert dup["contribution"] == 2
        assert dup["raw_value"] == 1
        # Activity trail recorded.
        acts = (
            await client.get(f"/api/v1/problems/{b_id}/activity", headers=bearer(token_b))
        ).json()
        events = [a["event_type"] for a in acts]
        assert "DUPLICATE_CONFIRMED" in events
        assert "JOINED_DUPLICATE_CLUSTER" in events
        assert "STATUS_CHANGED" in events
    finally:
        await delete_user(db_session, email_a)
        await delete_user(db_session, email_b)
        await delete_user(db_session, admin_email)


@pytest.mark.asyncio
async def test_pending_does_not_move_priority(client: AsyncClient, db_session: AsyncSession):
    email_a, token_a, _ = await make_user(client)
    email_b, token_b, _ = await make_user(client)
    try:
        a_body = await create(client, token_a, water_a())
        await create(client, token_b, water_b())
        a_detail = (
            await client.get(f"/api/v1/problems/{a_body['id']}", headers=bearer(token_a))
        ).json()
        dup = next(
            c
            for c in a_detail["priority"]["component_details"]["components"]
            if c["component"] == "duplicate_impact"
        )
        assert dup["contribution"] == 0
        assert dup["raw_value"] == 0
    finally:
        await delete_user(db_session, email_a)
        await delete_user(db_session, email_b)


@pytest.mark.asyncio
async def test_reject_preserves_record(client: AsyncClient, db_session: AsyncSession):
    email_a, token_a, _ = await make_user(client)
    email_b, token_b, _ = await make_user(client)
    admin_email, admin_token = await make_admin(client, db_session)
    try:
        a_id = (await create(client, token_a, wifi_a()))["id"]
        b_id = (await create(client, token_b, wifi_b()))["id"]
        assert isinstance(a_id, str)
        assert isinstance(b_id, str)
        before = (await client.get(f"/api/v1/problems/{a_id}", headers=bearer(token_a))).json()[
            "priority_score"
        ]
        cand = next(
            c
            for c in (
                await client.get(f"/api/v1/problems/{b_id}/duplicates", headers=bearer(token_b))
            ).json()["candidates"]
            if c["candidate"]["id"] == a_id
        )
        rejected = await client.post(
            f"/api/v1/admin/duplicate-candidates/{cand['id']}/reject",
            json={"review_note": "Different floors"},
            headers=bearer(admin_token),
        )
        assert rejected.status_code == 200, rejected.text
        assert rejected.json()["decision_status"] == "REJECTED"
        assert rejected.json()["reviewed_by"] is not None
        # B keeps its own lifecycle; A priority untouched by rejection.
        b_detail = (await client.get(f"/api/v1/problems/{b_id}", headers=bearer(token_b))).json()
        assert b_detail["status"] == "SUBMITTED"
        assert b_detail["canonical"] is None
        a_detail = (await client.get(f"/api/v1/problems/{a_id}", headers=bearer(token_a))).json()
        assert a_detail["priority_score"] == before
        # Confirming a rejected pair is refused.
        assert (
            await client.post(
                f"/api/v1/admin/duplicate-candidates/{cand['id']}/confirm",
                json={},
                headers=bearer(admin_token),
            )
        ).status_code == 409
    finally:
        await delete_user(db_session, email_a)
        await delete_user(db_session, email_b)
        await delete_user(db_session, admin_email)


@pytest.mark.asyncio
async def test_join_existing_cluster(client: AsyncClient, db_session: AsyncSession):
    emails = []
    try:
        toks = []
        for _ in range(3):
            email, token, _ = await make_user(client)
            emails.append(email)
            toks.append(token)
        bodies = [
            await create(client, toks[0], water_a()),
            await create(client, toks[1], water_b()),
            await create(
                client,
                toks[2],
                {
                    "title": "CSE block has no drinking water",
                    "description": "Students near the CSE block cannot find any drinking water today.",
                    "location_text": "CSE Block",
                },
            ),
        ]
        ids = [b["id"] for b in bodies]
        admin_email, admin_token = await make_admin(client, db_session)
        emails.append(admin_email)
        first_pair = next(
            c
            for c in (
                await client.get(f"/api/v1/problems/{ids[1]}/duplicates", headers=bearer(toks[1]))
            ).json()["candidates"]
            if c["candidate"]["id"] == ids[0]
        )
        cluster_number = (
            await client.post(
                f"/api/v1/admin/duplicate-candidates/{first_pair['id']}/confirm",
                json={},
                headers=bearer(admin_token),
            )
        ).json()["cluster_number"]
        # Third report joins the same cluster; canonical preserved.
        third_cands = (
            await client.get(f"/api/v1/problems/{ids[2]}/duplicates", headers=bearer(toks[2]))
        ).json()["candidates"]
        assert third_cands, "expected a candidate for the third report"
        join_pair = third_cands[0]
        joined = await client.post(
            f"/api/v1/admin/duplicate-candidates/{join_pair['id']}/confirm",
            json={},
            headers=bearer(admin_token),
        )
        assert joined.status_code == 200, joined.text
        assert joined.json()["cluster_number"] == cluster_number
        assert len(joined.json()["members"]) == 3
        canonical = next(m for m in joined.json()["members"] if m["is_canonical"])
        assert canonical["problem_id"] == ids[0]
        # Canonical now counts 2 additional confirmed reports (+4 points).
        a_detail = (await client.get(f"/api/v1/problems/{ids[0]}", headers=bearer(toks[0]))).json()
        dup = next(
            c
            for c in a_detail["priority"]["component_details"]["components"]
            if c["component"] == "duplicate_impact"
        )
        assert dup["raw_value"] == 2
        assert dup["contribution"] == 4
    finally:
        for email in emails:
            await delete_user(db_session, email)


@pytest.mark.asyncio
async def test_merge_two_clusters(client: AsyncClient, db_session: AsyncSession):
    emails: list[str] = []
    try:
        toks = []
        for _ in range(4):
            email, token, _ = await make_user(client)
            emails.append(email)
            toks.append(token)
        payloads = [water_a(), water_b(), wifi_a(), wifi_b()]
        ids = [(await create(client, toks[i], payloads[i]))["id"] for i in range(4)]
        admin_email, admin_token = await make_admin(client, db_session)
        emails.append(admin_email)

        async def confirm_pair(from_idx: int, to_id: str, tok: str) -> dict[str, object]:
            cands = (
                await client.get(
                    f"/api/v1/problems/{ids[from_idx]}/duplicates", headers=bearer(tok)
                )
            ).json()["candidates"]
            pair = next(c for c in cands if c["candidate"]["id"] == to_id)
            resp = await client.post(
                f"/api/v1/admin/duplicate-candidates/{pair['id']}/confirm",
                json={},
                headers=bearer(admin_token),
            )
            assert resp.status_code == 200, resp.text
            result = resp.json()
            assert isinstance(result, dict)
            return result

        cluster1 = await confirm_pair(1, ids[0], toks[1])
        cluster2 = await confirm_pair(3, ids[2], toks[3])
        assert cluster1["cluster_number"] != cluster2["cluster_number"]
        # Bridge: edit C (wifi) into water wording; reanalysis suggests A.
        edit = await client.patch(
            f"/api/v1/problems/{ids[2]}",
            json={
                "title": "No drinking water near CSE block",
                "description": "There is no drinking water available anywhere near the CSE block today.",
            },
            headers=bearer(toks[2]),
        )
        assert edit.status_code == 200, edit.text
        bridge_cands = (
            await client.get(f"/api/v1/problems/{ids[2]}/duplicates", headers=bearer(toks[2]))
        ).json()["candidates"]
        bridge = next((c for c in bridge_cands if c["candidate"]["id"] == ids[0]), None)
        assert bridge is not None, "expected a cross-cluster candidate after edit"
        merged = await client.post(
            f"/api/v1/admin/duplicate-candidates/{bridge['id']}/confirm",
            json={},
            headers=bearer(admin_token),
        )
        assert merged.status_code == 200, merged.text
        body = merged.json()
        assert len(body["members"]) == 4
        # Oldest cluster survives; oldest report overall (A) stays canonical.
        assert body["cluster_number"] in (cluster1["cluster_number"], cluster2["cluster_number"])
        canonical = next(m for m in body["members"] if m["is_canonical"])
        assert canonical["problem_id"] == ids[0]
        assert sum(1 for m in body["members"] if m["is_canonical"]) == 1
        # Dropped cluster is gone.
        dropped = (
            cluster2["cluster_number"]
            if body["cluster_number"] == cluster1["cluster_number"]
            else cluster1["cluster_number"]
        )
        all_clusters = [
            c
            for c in (
                await client.get("/api/v1/admin/duplicate-clusters", headers=bearer(admin_token))
            ).json()
            # Member-less clusters are residue of earlier tests' user cleanup
            # (problems/members cascade, empty clusters remain): only live
            # clusters with confirmed members count here.
            if c["members"]
        ]
        assert dropped not in [c["cluster_number"] for c in all_clusters]
        assert len(all_clusters) == 1
        # Every member links the surviving canonical issue.
        for i in (1, 2, 3):
            detail = (
                await client.get(f"/api/v1/problems/{ids[i]}", headers=bearer(toks[i]))
            ).json()
            assert detail["status"] == "DUPLICATE"
            assert detail["canonical"]["ticket_number"] == body["canonical"]["ticket_number"]
    finally:
        for email in emails:
            await delete_user(db_session, email)


@pytest.mark.asyncio
async def test_negative_same_location_no_candidate(client: AsyncClient, db_session: AsyncSession):
    email_a, token_a, _ = await make_user(client)
    email_b, token_b, _ = await make_user(client)
    try:
        a_id = (await create(client, token_a, hostel_clean()))["id"]
        b_body = await create(client, token_b, hostel_power())
        assert isinstance(a_id, str)
        cands = (
            await client.get(f"/api/v1/problems/{b_body['id']}/duplicates", headers=bearer(token_b))
        ).json()["candidates"]
        assert all(c["candidate"]["id"] != a_id for c in cands)
    finally:
        await delete_user(db_session, email_a)
        await delete_user(db_session, email_b)


@pytest.mark.asyncio
async def test_failure_safety_missing_model(
    client: AsyncClient, db_session: AsyncSession, monkeypatch
):
    def _boom() -> object:
        raise RuntimeError("no model")

    monkeypatch.setattr("app.services.duplicate_service.get_embedding_model", _boom)
    email, token, _ = await make_user(client)
    try:
        body = await create(client, token, water_a())
        assert body["status"] == "SUBMITTED"
        assert body["duplicate_status"] == "FAILED"
        # Other subsystems intact.
        assert body["classification_status"] in ("COMPLETED", "LOW_CONFIDENCE", "FAILED")
        assert body["priority_status"] == "COMPLETED"
        assert body["required_skills_status"] in ("COMPLETED", "FAILED")
    finally:
        await delete_user(db_session, email)


@pytest.mark.asyncio
async def test_admin_recalculate_preserves_duplicate_contribution(
    client: AsyncClient, db_session: AsyncSession
):
    """Admin priority recalculation must resolve the real confirmed count.

    A naive recalc with duplicate_count=0 would silently wipe the canonical's
    +2-per-duplicate contribution; history rows must also be preserved.
    """
    email_a, token_a, _ = await make_user(client)
    email_b, token_b, _ = await make_user(client)
    admin_email, admin_token = await make_admin(client, db_session)
    try:
        a_id = (await create(client, token_a, water_a()))["id"]
        b_id = (await create(client, token_b, water_b()))["id"]
        assert isinstance(a_id, str)
        assert isinstance(b_id, str)
        cand = next(
            c
            for c in (
                await client.get(f"/api/v1/problems/{b_id}/duplicates", headers=bearer(token_b))
            ).json()["candidates"]
            if c["candidate"]["id"] == a_id
        )
        assert (
            await client.post(
                f"/api/v1/admin/duplicate-candidates/{cand['id']}/confirm",
                json={},
                headers=bearer(admin_token),
            )
        ).status_code == 200
        rows_before = (
            await db_session.execute(
                select(func.count())
                .select_from(ProblemPriorityAnalysis)
                .where(ProblemPriorityAnalysis.problem_id == a_id)
            )
        ).scalar_one()
        recalc = await client.post(
            f"/api/v1/admin/problems/{a_id}/priority/recalculate",
            json={"reason": "Step 7 regression check"},
            headers=bearer(admin_token),
        )
        assert recalc.status_code == 200, recalc.text
        dup = next(
            c
            for c in recalc.json()["component_details"]["components"]
            if c["component"] == "duplicate_impact"
        )
        assert dup["contribution"] == 2
        assert dup["raw_value"] == 1
        rows_after = (
            await db_session.execute(
                select(func.count())
                .select_from(ProblemPriorityAnalysis)
                .where(ProblemPriorityAnalysis.problem_id == a_id)
            )
        ).scalar_one()
        assert rows_after == rows_before + 1
    finally:
        await delete_user(db_session, email_a)
        await delete_user(db_session, email_b)
        await delete_user(db_session, admin_email)


@pytest.mark.asyncio
async def test_admin_cluster_pages(client: AsyncClient, db_session: AsyncSession):
    email_a, token_a, _ = await make_user(client)
    email_b, token_b, _ = await make_user(client)
    admin_email, admin_token = await make_admin(client, db_session)
    try:
        a_id = (await create(client, token_a, water_a()))["id"]
        b_id = (await create(client, token_b, water_b()))["id"]
        assert isinstance(a_id, str)
        assert isinstance(b_id, str)
        assert (
            await client.get("/api/v1/admin/duplicate-clusters", headers=bearer(token_a))
        ).status_code == 403
        # Member-less clusters are residue of earlier tests' user cleanup
        # (problems/members cascade, empty clusters remain): only live
        # clusters with confirmed members count here.
        live_before = [
            c
            for c in (
                await client.get(
                    "/api/v1/admin/duplicate-clusters", headers=bearer(admin_token)
                )
            ).json()
            if c["members"]
        ]
        assert not live_before
        cand = next(
            c
            for c in (
                await client.get(f"/api/v1/problems/{b_id}/duplicates", headers=bearer(token_b))
            ).json()["candidates"]
            if c["candidate"]["id"] == a_id
        )
        cluster_number = (
            await client.post(
                f"/api/v1/admin/duplicate-candidates/{cand['id']}/confirm",
                json={},
                headers=bearer(admin_token),
            )
        ).json()["cluster_number"]
        clusters = [
            c
            for c in (
                await client.get(
                    "/api/v1/admin/duplicate-clusters", headers=bearer(admin_token)
                )
            ).json()
            if c["members"]
        ]
        assert len(clusters) == 1
        assert clusters[0]["cluster_number"] == cluster_number
        assert clusters[0]["canonical"]["ticket_number"]
        assert len(clusters[0]["members"]) == 2
        one = await client.get(
            f"/api/v1/admin/duplicate-clusters/{clusters[0]['id']}", headers=bearer(admin_token)
        )
        assert one.status_code == 200
        assert one.json()["cluster_number"] == cluster_number
        assert (
            await client.get(
                "/api/v1/admin/duplicate-clusters/00000000-0000-0000-0000-000000000000",
                headers=bearer(admin_token),
            )
        ).status_code == 404
    finally:
        await delete_user(db_session, email_a)
        await delete_user(db_session, email_b)
        await delete_user(db_session, admin_email)
