"""Step 13 tests: real admin analytics, access control, CSV, privacy, perf."""

import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ProblemStatus
from app.main import app
from app.models.problem import Problem
from app.models.user import User

sys.path.insert(0, str(Path(__file__).parent))

from test_knowledge import (  # noqa: E402
    CCTV_PAYLOAD,
    CCTV_SOLUTION,
    NETWORK_PAYLOAD,
    SOLUTION_PAYLOAD,
    bearer,
    cleanup_crew,
    cleanup_ctx,
    create_problem,
    delete_user,
    drive_from_created,
    full_flow,
    make_admin,
    make_crew,
    make_mentor,
    make_solver,
    register,
    unique_email,
)

LOC = "K13 Analytics Hall"


def k13_payload(title: str) -> dict:
    return {
        "title": title,
        "description": "K13 analytics probe report with enough detail words to pass validation checks here.",
        "location_text": LOC,
    }


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def admin_token(ac: AsyncClient, session: AsyncSession) -> tuple[str, str]:
    email, token = await make_admin(ac, session)
    return email, token


async def dashboard(ac: AsyncClient, token: str, **params) -> dict:
    resp = await ac.get("/api/v1/admin/analytics/dashboard", params=params, headers=bearer(token))
    assert resp.status_code == 200, resp.text
    return resp.json()


# ---------------- access control ----------------


@pytest.mark.asyncio
async def test_analytics_access_matrix(client: AsyncClient, db_session: AsyncSession):
    admin_email, admin_tok = await admin_token(client, db_session)
    rep = await register(client, unique_email("k13rep"), "REPORTER", "K13 Reporter")
    solver = await register(client, unique_email("k13sol"), "SOLVER", "K13 Solver")
    mentor_email, mentor_tok, _ = await make_mentor(client, db_session)
    try:
        for path in (
            "/api/v1/admin/analytics/dashboard",
            "/api/v1/admin/analytics/trends",
            "/api/v1/admin/analytics/export/problems.csv",
            "/api/v1/admin/analytics/export/skills.csv",
        ):
            assert (await client.get(path, headers=bearer(admin_tok))).status_code == 200, path
            assert (await client.get(path, headers=bearer(rep["access_token"]))).status_code == 403, path
            assert (await client.get(path, headers=bearer(solver["access_token"]))).status_code == 403, path
            assert (await client.get(path, headers=bearer(mentor_tok))).status_code == 403, path
            assert (await client.get(path)).status_code == 401, path
    finally:
        for email in (admin_email, rep["user"]["email"], solver["user"]["email"], mentor_email):
            await delete_user(db_session, email)


# ---------------- overview / definitions ----------------


@pytest.mark.asyncio
async def test_overview_exact_counts_with_location_filter(
    client: AsyncClient, db_session: AsyncSession
):
    admin_email, admin_tok = await admin_token(client, db_session)
    rep = await register(client, unique_email("k13rep"), "REPORTER", "K13 Reporter")
    try:
        before = await dashboard(client, admin_tok, location=LOC)
        assert before["overview"]["total_problems"] == 0
        for i in range(2):
            r = await client.post(
                "/api/v1/problems",
                json=k13_payload(f"K13 probe report number {i} filed today"),
                headers=bearer(rep["access_token"]),
            )
            assert r.status_code == 201, r.text
        after = await dashboard(client, admin_tok, location=LOC)
        assert after["overview"]["total_problems"] == 2
        assert after["overview"]["open_problems"] == 2
        assert after["overview"]["status_counts"].get("SUBMITTED", 0) == 2
        # Open = sum of open statuses; terminal never counted as open.
        open_statuses = {
            "SUBMITTED", "UNDER_REVIEW", "APPROVED", "ASSIGNED", "IN_PROGRESS",
            "AWAITING_VERIFICATION",
        }
        assert after["overview"]["open_problems"] == sum(
            v for k, v in after["overview"]["status_counts"].items() if k in open_statuses
        )
    finally:
        await delete_user(db_session, rep["user"]["email"])
        await delete_user(db_session, admin_email)


@pytest.mark.asyncio
async def test_trends_buckets_and_zero_fill(client: AsyncClient, db_session: AsyncSession):
    admin_email, admin_tok = await admin_token(client, db_session)
    rep = await register(client, unique_email("k13rep"), "REPORTER", "K13 Reporter")
    try:
        r = await client.post(
            "/api/v1/problems",
            json=k13_payload("K13 trend probe report filed today"),
            headers=bearer(rep["access_token"]),
        )
        assert r.status_code == 201, r.text
        resp = await client.get(
            "/api/v1/admin/analytics/trends",
            params={"preset": "7d"},
            headers=bearer(admin_tok),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["granularity"] == "day"
        assert len(body["buckets"]) >= 7
        for bucket in body["buckets"]:
            assert "reported" in bucket
            assert "resolved" in bucket
        assert sum(b["reported"] for b in body["buckets"]) >= 1
    finally:
        await delete_user(db_session, rep["user"]["email"])
        await delete_user(db_session, admin_email)


@pytest.mark.asyncio
async def test_categories_percentages_sum(client: AsyncClient, db_session: AsyncSession):
    ctx = await full_flow(client, db_session, NETWORK_PAYLOAD, SOLUTION_PAYLOAD)
    try:
        body = await dashboard(client, ctx["admin"][1])
        total = body["categories"]["total"]
        assert total >= 1
        items = body["categories"]["items"]
        assert abs(sum(i["percentage"] for i in items) - 100.0) < 0.6 or total == 0
        assert all(i["count"] >= 1 for i in items)
    finally:
        await cleanup_ctx(db_session, ctx)


@pytest.mark.asyncio
async def test_location_normalization_groups_variants(
    client: AsyncClient, db_session: AsyncSession
):
    admin_email, admin_tok = await admin_token(client, db_session)
    rep = await register(client, unique_email("k13rep"), "REPORTER", "K13 Reporter")
    variants = ["K13 Library", " k13 library ", "K13 LIBRARY"]
    try:
        for i, loc in enumerate(variants):
            payload = k13_payload(f"K13 location probe report {i}")
            payload["location_text"] = loc
            r = await client.post(
                "/api/v1/problems", json=payload, headers=bearer(rep["access_token"])
            )
            assert r.status_code == 201, r.text
        body = await dashboard(client, admin_tok, location="k13 library")
        found = list(body.get("locations", {}).get("items", []))
        assert found, "normalized hotspot missing"
        assert found[0]["count"] == 3
        assert "open_count" in found[0]
        assert "resolved_count" in found[0]
        assert "common_categories" in found[0]
    finally:
        await delete_user(db_session, rep["user"]["email"])
        await delete_user(db_session, admin_email)


# ---------------- priority / resolution ----------------


@pytest.mark.asyncio
async def test_priority_counts_shape(client: AsyncClient, db_session: AsyncSession):
    admin_email, admin_tok = await admin_token(client, db_session)
    rep = await register(client, unique_email("k13rep"), "REPORTER", "K13 Reporter")
    try:
        r = await client.post(
            "/api/v1/problems",
            json=k13_payload("K13 priority probe report filed today"),
            headers=bearer(rep["access_token"]),
        )
        assert r.status_code == 201, r.text
        body = await dashboard(client, admin_tok, location=LOC)
        counts = body["priorities"]["counts"]
        assert set(counts) <= {"LOW", "MEDIUM", "HIGH", "CRITICAL"}
        assert sum(counts.values()) >= 1
        avg = body["priorities"]["average_score"]
        assert avg is None or 0 <= avg <= 100
        assert isinstance(body["priorities"]["high_critical_open"], list)
    finally:
        await delete_user(db_session, rep["user"]["email"])
        await delete_user(db_session, admin_email)


@pytest.mark.asyncio
async def test_resolution_single_problem_exact(client: AsyncClient, db_session: AsyncSession):
    payload = dict(NETWORK_PAYLOAD)
    payload["location_text"] = "K13 Resolution Hall"
    ctx = await full_flow(client, db_session, payload, SOLUTION_PAYLOAD)
    try:
        body = await dashboard(client, ctx["admin"][1], location="K13 Resolution Hall")
        res = body["resolution"]
        assert res["count"] == 1
        for key in ("average_seconds", "median_seconds", "min_seconds", "max_seconds", "p90_seconds"):
            assert res[key] is not None
            assert res[key] >= 0
        assert res["min_seconds"] <= res["average_seconds"] <= res["max_seconds"]
        assert res["median_seconds"] <= res["max_seconds"]
        assert res["p90_seconds"] >= res["median_seconds"]
    finally:
        await cleanup_ctx(db_session, ctx)


# ---------------- overrides ----------------


@pytest.mark.asyncio
async def test_override_rates_from_real_flows(client: AsyncClient, db_session: AsyncSession):
    from test_knowledge import make_admin as _make_admin

    seed_admin_email, seed_admin_tok = await _make_admin(client, db_session)
    seed_admin = bearer(seed_admin_tok)
    try:
        team_before = (
            await client.get("/api/v1/admin/analytics/dashboard", headers=seed_admin)
        ).json()["assignments"]["team_override_count"]
        class_before = (
            await client.get("/api/v1/admin/analytics/dashboard", headers=seed_admin)
        ).json()["classification"]["override_count"]
        ctx = await full_flow(client, db_session, NETWORK_PAYLOAD, SOLUTION_PAYLOAD)
        try:
            admin = bearer(ctx["admin"][1])
            after_flow = (
                await client.get("/api/v1/admin/analytics/dashboard", headers=admin)
            ).json()
            # full_flow assigns manually => one more override; accepted+override == total.
            assert after_flow["assignments"]["team_override_count"] == team_before + 1
            total = after_flow["assignments"]["total"]
            assert (
                after_flow["assignments"]["team_accepted_count"]
                + after_flow["assignments"]["team_override_count"]
                == total
            )
            # Force a classification override on a fresh report.
            rep = await register(client, unique_email("k13rep"), "REPORTER", "K13 Reporter")
            created = await client.post(
                "/api/v1/problems", json=k13_payload("K13 override probe"), headers=bearer(rep["access_token"])
            )
            pid = created.json()["id"]
            predicted = (
                await client.get(f"/api/v1/problems/{pid}/classification", headers=bearer(rep["access_token"]))
            ).json()["predicted_category"]
            other = "OTHER" if predicted != "OTHER" else "LIBRARY"
            review = await client.post(
                f"/api/v1/admin/problems/{pid}/classification/review",
                json={"accept": False, "final_category": other, "review_note": "k13 test"},
                headers=admin,
            )
            assert review.status_code == 200, review.text
            after = (await client.get("/api/v1/admin/analytics/dashboard", headers=admin)).json()
            assert after["classification"]["override_count"] == class_before + 1
            assert after["classification"]["override_rate"] is not None
            await delete_user(db_session, rep["user"]["email"])
        finally:
            await cleanup_ctx(db_session, ctx)
    finally:
        await delete_user(db_session, seed_admin_email)


# ---------------- verification / revisions ----------------


@pytest.mark.asyncio
async def test_verification_and_reopen_rate(client: AsyncClient, db_session: AsyncSession):
    ctx = await full_flow(client, db_session, NETWORK_PAYLOAD, SOLUTION_PAYLOAD)
    try:
        admin = bearer(ctx["admin"][1])
        before = (await client.get("/api/v1/admin/analytics/dashboard", headers=admin)).json()[
            "verification"
        ]
        # Second report: drive to AWAITING_VERIFICATION, then reporter rejects.
        rep = await register(client, unique_email("k13rep"), "REPORTER", "K13 Reporter")
        s1 = await make_solver(client, db_session, skills=[])
        s2 = await make_solver(client, db_session, skills=[])
        m = await make_mentor(client, db_session)
        created = await client.post(
            "/api/v1/problems", json=k13_payload("K13 reopen probe report"), headers=bearer(rep["access_token"])
        )
        pid = created.json()["id"]
        admin_email2, admin_tok2 = await make_admin(client, db_session)
        a2 = bearer(admin_tok2)
        assert (
            await client.post(f"/api/v1/admin/problems/{pid}/review/start", headers=a2)
        ).status_code == 200
        assert (
            await client.post(f"/api/v1/admin/problems/{pid}/approve", json={}, headers=a2)
        ).status_code == 200
        assign = await client.post(
            f"/api/v1/admin/problems/{pid}/assign",
            json={
                "solver_user_ids": [s1[2], s2[2]],
                "mentor_user_id": m[2],
                "team_name": "K13 Reopen Crew",
                "team_override_reason": "reopen test",
                "mentor_override_reason": "reopen test",
            },
            headers=a2,
        )
        assert assign.status_code == 201, assign.text
        task = await client.post(
            f"/api/v1/problems/{pid}/tasks", json={"title": "Do the fix well"}, headers=bearer(s1[1])
        )
        tid = task.json()["id"]
        for state in ("IN_PROGRESS", "DONE"):
            assert (
                await client.patch(
                    f"/api/v1/problems/{pid}/tasks/{tid}", json={"status": state}, headers=bearer(s1[1])
                )
            ).status_code == 200
        sub = await client.post(
            f"/api/v1/problems/{pid}/solutions", json=SOLUTION_PAYLOAD, headers=bearer(s1[1])
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
                json={"decision": "NOT_RESOLVED", "reason": "Still broken in the evening"},
                headers=bearer(rep["access_token"]),
            )
        ).status_code == 201
        after = (await client.get("/api/v1/admin/analytics/dashboard", headers=admin)).json()[
            "verification"
        ]
        assert after["not_resolved_responses"] == before["not_resolved_responses"] + 1
        assert after["resolved_confirmations"] == before["resolved_confirmations"]
        expected_rate = after["not_resolved_responses"] / (
            after["resolved_confirmations"] + after["not_resolved_responses"]
        )
        assert abs(after["reopen_rate"] - expected_rate) < 1e-9
        assert after["average_revisions"] is not None
        for email in (rep["user"]["email"], s1[0], s2[0], m[0], admin_email2):
            await delete_user(db_session, email)
    finally:
        await cleanup_ctx(db_session, ctx)


# ---------------- skills / workloads / duplicates ----------------


@pytest.mark.asyncio
async def test_skill_demand_no_double_count(client: AsyncClient, db_session: AsyncSession):
    ctx = await full_flow(client, db_session, NETWORK_PAYLOAD, SOLUTION_PAYLOAD)
    try:
        admin = bearer(ctx["admin"][1])
        # Re-run extraction: history grows, demand must still count the problem once.
        assert (
            await client.post(
                f"/api/v1/admin/problems/{ctx['pid']}/skills/reanalyze", headers=admin
            )
        ).status_code in (200, 201)
        body = await dashboard(client, ctx["admin"][1])
        names = {item["name"]: item["problems"] for item in body["skill_demand"]["items"]}
        assert names, "expected skill demand rows"
        assert all(count >= 1 for count in names.values())
        linux = next((i for i in body["skill_demand"]["items"] if i["name"] == "Linux"), None)
        if linux is not None:
            assert linux["problems"] == 1
    finally:
        await cleanup_ctx(db_session, ctx)


@pytest.mark.asyncio
async def test_workload_aggregates(client: AsyncClient, db_session: AsyncSession):
    admin_email, admin_tok = await admin_token(client, db_session)
    s1 = await make_solver(client, db_session, skills=[])
    try:
        result = await db_session.execute(select(User).where(User.email == s1[0].lower()))
        result.scalar_one()
        body = await dashboard(client, admin_tok)
        solvers = body["workloads"]["solvers"]
        assert solvers["total_capacity"] >= solvers["total_used"]
        assert 0.0 <= solvers["utilization"] <= 1.0
        assert "AVAILABLE" in solvers["by_availability"]
        assert isinstance(body["workloads"]["busiest_solvers"], list)
        for row in body["workloads"]["busiest_solvers"]:
            assert "@" not in row["name"]
    finally:
        await delete_user(db_session, s1[0])
        await delete_user(db_session, admin_email)


@pytest.mark.asyncio
async def test_duplicate_metrics_from_confirm(client: AsyncClient, db_session: AsyncSession):
    # A stays open while B is confirmed as its duplicate (closed reports are
    # excluded from duplicate analysis), then A is driven to CLOSED.
    ctx = await make_crew(client, db_session)
    rep_b = None
    admin_extra = None
    try:
        ctx["pid"] = await create_problem(client, ctx, CCTV_PAYLOAD)
        rep_b = await register(client, unique_email("k13rep"), "REPORTER", "K13 Reporter B")
        admin_extra, admin_extra_tok = await make_admin(client, db_session)
        admin = bearer(admin_extra_tok)
        before = (await client.get("/api/v1/admin/analytics/dashboard", headers=admin)).json()[
            "duplicates"
        ]
        created = await client.post(
            "/api/v1/problems", json=CCTV_PAYLOAD, headers=bearer(rep_b["access_token"])
        )
        pid_b = created.json()["id"]
        dups = (
            await client.get(
                f"/api/v1/problems/{pid_b}/duplicates", headers=bearer(rep_b["access_token"])
            )
        ).json()
        assert dups["candidates"], "expected a duplicate candidate for identical CCTV reports"
        cand = dups["candidates"][0]
        assert (
            await client.post(
                f"/api/v1/admin/duplicate-candidates/{cand['id']}/confirm", json={}, headers=admin
            )
        ).status_code == 200
        await drive_from_created(client, ctx, CCTV_SOLUTION, close=True)
        after = (await client.get("/api/v1/admin/analytics/dashboard", headers=admin)).json()[
            "duplicates"
        ]
        assert after["confirmed_candidates"] == before["confirmed_candidates"] + 1
        assert after["active_clusters"] >= 1
        assert after["average_reports_per_cluster"] >= 1.0
        assert after["largest_cluster_size"] >= 2
    finally:
        await cleanup_crew(db_session, ctx)
        if rep_b is not None:
            await delete_user(db_session, rep_b["user"]["email"])
        if admin_extra is not None:
            await delete_user(db_session, admin_extra)


@pytest.mark.asyncio
async def test_knowledge_metrics_follow_publication(
    client: AsyncClient, db_session: AsyncSession
):
    admin_email, admin_tok = await admin_token(client, db_session)
    try:
        before = (await client.get("/api/v1/admin/analytics/dashboard", headers=bearer(admin_tok))).json()[
            "knowledge"
        ]
        ctx = await full_flow(client, db_session, NETWORK_PAYLOAD, SOLUTION_PAYLOAD)
        try:
            after = (
                await client.get("/api/v1/admin/analytics/dashboard", headers=bearer(admin_tok))
            ).json()["knowledge"]
            assert after["published"] == before["published"] + 1
            assert any(c["count"] >= 1 for c in after["top_categories"])
        finally:
            await cleanup_ctx(db_session, ctx)
    finally:
        await delete_user(db_session, admin_email)


# ---------------- operations ----------------


@pytest.mark.asyncio
async def test_operations_overdue_and_blocked(client: AsyncClient, db_session: AsyncSession):
    rep = await register(client, unique_email("k13rep"), "REPORTER", "K13 Reporter")
    s1 = await make_solver(client, db_session, skills=[])
    s2 = await make_solver(client, db_session, skills=[])
    m = await make_mentor(client, db_session)
    admin_email, admin_tok = await make_admin(client, db_session)
    try:
        a = bearer(admin_tok)
        created = await client.post(
            "/api/v1/problems", json=k13_payload("K13 operations probe"), headers=bearer(rep["access_token"])
        )
        pid = created.json()["id"]
        assert (await client.post(f"/api/v1/admin/problems/{pid}/review/start", headers=a)).status_code == 200
        assert (await client.post(f"/api/v1/admin/problems/{pid}/approve", json={}, headers=a)).status_code == 200
        assign = await client.post(
            f"/api/v1/admin/problems/{pid}/assign",
            json={
                "solver_user_ids": [s1[2], s2[2]],
                "mentor_user_id": m[2],
                "team_name": "K13 Ops Crew",
                "team_override_reason": "ops test",
                "mentor_override_reason": "ops test",
            },
            headers=a,
        )
        assert assign.status_code == 201, assign.text
        past = (datetime.now(UTC) - timedelta(days=2)).isoformat()
        future = (datetime.now(UTC) + timedelta(days=3)).isoformat()
        overdue_task = await client.post(
            f"/api/v1/problems/{pid}/tasks",
            json={"title": "Overdue k13 task", "due_date": past},
            headers=bearer(s1[1]),
        )
        assert overdue_task.status_code == 201, overdue_task.text
        blocked_task = await client.post(
            f"/api/v1/problems/{pid}/tasks",
            json={"title": "Blocked k13 task"},
            headers=bearer(s1[1]),
        )
        bid = blocked_task.json()["id"]
        assert (
            await client.patch(
                f"/api/v1/problems/{pid}/tasks/{bid}", json={"status": "IN_PROGRESS"}, headers=bearer(s1[1])
            )
        ).status_code == 200
        assert (
            await client.patch(
                f"/api/v1/problems/{pid}/tasks/{bid}",
                json={"status": "BLOCKED", "blocker_reason": "Waiting on parts delivery"},
                headers=bearer(s1[1]),
            )
        ).status_code == 200
        ms = await client.post(
            f"/api/v1/problems/{pid}/milestones",
            json={"title": "Overdue k13 milestone", "target_date": past},
            headers=bearer(m[1]),
        )
        assert ms.status_code == 201, ms.text
        upcoming = await client.post(
            f"/api/v1/problems/{pid}/milestones",
            json={"title": "Upcoming k13 milestone", "target_date": future},
            headers=bearer(m[1]),
        )
        assert upcoming.status_code == 201, upcoming.text
        ops = (await client.get("/api/v1/admin/analytics/dashboard", headers=a)).json()["operations"]
        assert any(t["title"] == "Overdue k13 task" for t in ops["overdue_tasks"])
        assert any(t["title"] == "Blocked k13 task" for t in ops["blocked_tasks"])
        assert any(t["title"] == "Overdue k13 milestone" for t in ops["overdue_milestones"])
        assert any(t["title"] == "Upcoming k13 milestone" for t in ops["upcoming_milestones"])
        assert ops["pending_duplicate_reviews"] >= 0
    finally:
        for email in (rep["user"]["email"], s1[0], s2[0], m[0], admin_email):
            await delete_user(db_session, email)


# ---------------- model quality / privacy / empty / csv / perf ----------------


@pytest.mark.asyncio
async def test_model_quality_matches_artifacts(client: AsyncClient, db_session: AsyncSession):
    admin_email, admin_tok = await admin_token(client, db_session)
    try:
        quality = (await client.get("/api/v1/admin/analytics/dashboard", headers=bearer(admin_tok))).json()[
            "classification"
        ]["model_quality"]
        assert quality["available"] is True
        assert quality["model_version"] == "campusxolve-problem-classifier-v1"
        assert quality["base_model"] == "distilbert-base-uncased"
        assert quality["test_accuracy"] == 0.6591
        assert quality["macro_f1"] == 0.63
        assert quality["test_samples"] == 44
        assert "not production accuracy" in quality["label"].lower()
        assert quality["label"].startswith("Development")
        assert quality["per_class_f1"][0]["label"] == "SAFETY_SECURITY"
        assert quality["per_class_f1"][0]["f1"] == 0.0
    finally:
        await delete_user(db_session, admin_email)


@pytest.mark.asyncio
async def test_analytics_privacy_no_internals(client: AsyncClient, db_session: AsyncSession):
    admin_email, admin_tok = await admin_token(client, db_session)
    try:
        body = (await client.get("/api/v1/admin/analytics/dashboard", headers=bearer(admin_tok))).json()
        text = str(body).lower()
        for marker in ("@example.com", "@campusxolve.local", "password", "access_token", "refresh_token"):
            assert marker not in text, marker
    finally:
        await delete_user(db_session, admin_email)


@pytest.mark.asyncio
async def test_empty_filters_render_zeros(client: AsyncClient, db_session: AsyncSession):
    admin_email, admin_tok = await admin_token(client, db_session)
    try:
        body = await dashboard(client, admin_tok, location="NoSuchPlaceZZZ")
        assert body["overview"]["total_problems"] == 0
        assert body["overview"]["open_problems"] == 0
        assert body["categories"]["total"] == 0
        assert body["resolution"]["count"] == 0
        assert body["resolution"]["average_seconds"] is None
        assert body["resolution"]["median_seconds"] is None
    finally:
        await delete_user(db_session, admin_email)


@pytest.mark.asyncio
async def test_csv_problems_headers_rows_filters(client: AsyncClient, db_session: AsyncSession):
    admin_email, admin_tok = await admin_token(client, db_session)
    rep = await register(client, unique_email("k13rep"), "REPORTER", "K13 Reporter")
    try:
        r = await client.post(
            "/api/v1/problems",
            json=k13_payload("K13 csv probe report filed today"),
            headers=bearer(rep["access_token"]),
        )
        assert r.status_code == 201, r.text
        resp = await client.get(
            "/api/v1/admin/analytics/export/problems.csv",
            params={"location": LOC},
            headers=bearer(admin_tok),
        )
        assert resp.status_code == 200, resp.text
        assert "text/csv" in resp.headers["content-type"]
        lines = resp.text.strip().splitlines()
        assert lines[0].split(",") == [
            "ticket_number", "title", "category", "priority_level", "priority_score",
            "status", "location_text", "building", "area", "submitted_at", "resolved_at",
            "closed_at", "resolution_seconds",
        ]
        assert len(lines) == 2
        assert "K13 csv probe" in lines[1]
        lowered = resp.text.lower()
        for marker in ("@example.com", "password", "access_token", "student_identifier"):
            assert marker not in lowered, marker
        empty = await client.get(
            "/api/v1/admin/analytics/export/problems.csv",
            params={"location": "NoSuchPlaceZZZ"},
            headers=bearer(admin_tok),
        )
        assert len(empty.text.strip().splitlines()) == 1
    finally:
        await delete_user(db_session, rep["user"]["email"])
        await delete_user(db_session, admin_email)


@pytest.mark.asyncio
async def test_csv_skills_export(client: AsyncClient, db_session: AsyncSession):
    ctx = await full_flow(client, db_session, NETWORK_PAYLOAD, SOLUTION_PAYLOAD)
    try:
        resp = await client.get(
            "/api/v1/admin/analytics/export/skills.csv", headers=bearer(ctx["admin"][1])
        )
        assert resp.status_code == 200, resp.text
        assert "text/csv" in resp.headers["content-type"]
        lines = resp.text.strip().splitlines()
        assert lines[0].split(",") == ["skill_name", "category", "problems", "avg_relevance"]
        assert len(lines) >= 2
    finally:
        await cleanup_ctx(db_session, ctx)


@pytest.mark.asyncio
async def test_dashboard_performance_with_bulk_rows(
    client: AsyncClient, db_session: AsyncSession
):
    admin_email, admin_tok = await admin_token(client, db_session)
    rep = await register(client, unique_email("k13rep"), "REPORTER", "K13 Reporter")
    try:
        result = await db_session.execute(select(User).where(User.email == rep["user"]["email"].lower()))
        reporter = result.scalar_one()
        for i in range(25):
            db_session.add(
                Problem(
                    ticket_number=f"CX-K13-{uuid4().hex[:6]}",
                    title=f"K13 bulk performance probe report {i}",
                    description="Bulk performance probe report with sufficient descriptive words here.",
                    reporter_id=reporter.id,
                    location_text="K13 Bulk Hall",
                    status=ProblemStatus.SUBMITTED,
                )
            )
        await db_session.commit()
        started = time.perf_counter()
        resp = await client.get("/api/v1/admin/analytics/dashboard", headers=bearer(admin_tok))
        elapsed = time.perf_counter() - started
        print(f"\nanalytics dashboard (25 bulk rows): {elapsed:.2f}s")
        assert resp.status_code == 200, resp.text
        assert elapsed < 8.0
        started = time.perf_counter()
        trends = await client.get(
            "/api/v1/admin/analytics/trends", params={"preset": "90d"}, headers=bearer(admin_tok)
        )
        elapsed_trends = time.perf_counter() - started
        print(f"analytics trends 90d: {elapsed_trends:.2f}s")
        assert trends.status_code == 200
        assert elapsed_trends < 8.0
    finally:
        bulk = (
            await db_session.execute(select(Problem).where(Problem.ticket_number.like("CX-K13-%")))
        ).scalars().all()
        for problem in bulk:
            await db_session.delete(problem)
        await db_session.commit()
        await delete_user(db_session, rep["user"]["email"])
        await delete_user(db_session, admin_email)
